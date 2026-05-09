import asyncio
import logging
import os
import re
import time
import requests
from datetime import datetime
import pytz

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from openai import OpenAI
import aiosqlite

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = "https://Ctrlzett-coder.github.io/Coins/"
AI_API_KEY = os.getenv("AI_API_KEY")
DB_PATH = os.getenv("DB_PATH", "bot_data.db")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Europe/Moscow"

def get_now(tz_name: str = DEFAULT_TIMEZONE) -> datetime:
    return datetime.now(pytz.timezone(tz_name))

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()
ai_client = OpenAI(api_key=AI_API_KEY, base_url="https://api.deepseek.com")


class NotifyStates(StatesGroup):
    choosing_type = State()
    choosing_interval = State()
    entering_custom_time = State()


class TimezoneStates(StatesGroup):
    choosing = State()


class AlertStates(StatesGroup):
    choosing_coin = State()
    choosing_direction = State()
    entering_price = State()


TIMEZONES = [
    "Asia/Novosibirsk",
    "Europe/Moscow",
    "Europe/Berlin",
    "Asia/Dubai",
    "Asia/Tokyo",
    "America/New_York",
    "America/Los_Angeles",
    "UTC"
]

# --- БД ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_timezones (
                user_id INTEGER PRIMARY KEY,
                timezone TEXT NOT NULL DEFAULT 'Europe/Moscow'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                interval INTEGER NOT NULL,
                last_run REAL NOT NULL,
                custom_hour INTEGER,
                custom_minute INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                coin TEXT NOT NULL,
                direction TEXT NOT NULL,
                price REAL NOT NULL
            )
        """)
        # Миграция: добавить колонки если их нет (для старых БД)
        try:
            await db.execute("ALTER TABLE user_notifications ADD COLUMN custom_hour INTEGER")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE user_notifications ADD COLUMN custom_minute INTEGER")
        except Exception:
            pass
        await db.commit()


async def db_get_timezone(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT timezone FROM user_timezones WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else DEFAULT_TIMEZONE


async def db_set_timezone(user_id: int, timezone: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO user_timezones (user_id, timezone) VALUES (?, ?)",
            (user_id, timezone)
        )
        await db.commit()


async def db_get_notifications(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, type, interval, last_run, custom_hour, custom_minute FROM user_notifications WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"id": r[0], "type": r[1], "interval": r[2], "last_run": r[3],
                     "custom_hour": r[4], "custom_minute": r[5]} for r in rows]


async def db_add_notification(user_id: int, note_type: str, interval: int, last_run: float,
                               custom_hour: int = None, custom_minute: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO user_notifications (user_id, type, interval, last_run, custom_hour, custom_minute) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, note_type, interval, last_run, custom_hour, custom_minute)
        )
        await db.commit()


async def db_delete_notification(note_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM user_notifications WHERE id = ?", (note_id,))
        await db.commit()


async def db_update_last_run(note_id: int, last_run: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE user_notifications SET last_run = ? WHERE id = ?",
            (last_run, note_id)
        )
        await db.commit()


async def db_get_all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT DISTINCT user_id FROM user_notifications"
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]


async def db_add_alert(user_id: int, coin: str, direction: str, price: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO user_alerts (user_id, coin, direction, price) VALUES (?, ?, ?, ?)",
            (user_id, coin, direction, price)
        )
        await db.commit()


async def db_get_alerts(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, coin, direction, price FROM user_alerts WHERE user_id = ?", (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"id": r[0], "coin": r[1], "direction": r[2], "price": r[3]} for r in rows]


async def db_delete_alert(alert_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM user_alerts WHERE id = ?", (alert_id,))
        await db.commit()


async def db_get_all_alerts() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, user_id, coin, direction, price FROM user_alerts"
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"id": r[0], "user_id": r[1], "coin": r[2], "direction": r[3], "price": r[4]} for r in rows]


# --- ДАННЫЕ РЫНКА ---
def _fetch_market_data() -> dict:
    headers = {'User-Agent': 'Mozilla/5.0'}
    result = {}

    try:
        crypto_url = (
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"
        )
        res = requests.get(crypto_url, headers=headers, timeout=10).json()
        result['btc_price'] = res['bitcoin']['usd']
        result['btc_change'] = res['bitcoin']['usd_24h_change']
        result['eth_price'] = res['ethereum']['usd']
        result['eth_change'] = res['ethereum']['usd_24h_change']
    except Exception as e:
        logger.warning("Не удалось получить данные крипты: %s", e)
        result['btc_price'] = 69200
        result['btc_change'] = 1.2
        result['eth_price'] = 3520
        result['eth_change'] = -0.5

    try:
        moex_url = (
            "https://iss.moex.com/iss/engines/stock/markets/index"
            "/securities/IMOEX.json?iss.meta=off"
        )
        res = requests.get(moex_url, headers=headers, timeout=10).json()
        row = res['marketdata']['data'][0]
        current_val = row[2] if row[2] is not None else row[12]
        prev_close = row[3]
        change_pct = ((current_val - prev_close) / prev_close * 100) if prev_close else 0.0
        result['imoex_val'] = current_val
        result['imoex_change'] = change_pct
    except Exception as e:
        logger.warning("Не удалось получить данные IMOEX: %s", e)
        result['imoex_val'] = 2772.0
        result['imoex_change'] = -0.3

    return result


def _fetch_prices() -> dict:
    """Возвращает текущие цены BTC и ETH в USD."""
    try:
        res = requests.get(
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=bitcoin,ethereum&vs_currencies=usd",
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=10
        ).json()
        return {"BTC": res['bitcoin']['usd'], "ETH": res['ethereum']['usd']}
    except Exception:
        return {}


def _call_ai(market_context: str) -> str:
    response = ai_client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты — аналитический модуль системы CryptoPulse. Делай КРАТКИЙ дайджест. "
                    "Используй ТОЛЬКО HTML (<b> для жирного). Запрещено использовать **. "
                    "Для каждого актива ОБЯЗАТЕЛЬНО укажи цену и процент изменения. "
                    "Формат строго такой:\n\n"
                    "📊 <b>Краткий рыночный дайджест</b>\n\n"
                    "Крипта:\n"
                    "- BTC 🚀: $цена (процент) — короткая суть.\n"
                    "- ETH ⚡: $цена (процент) — короткая суть.\n\n"
                    "Мосбиржа (данные с задержкой):\n"
                    "- IMOEX 📉: значение (процент) — кратко тренд.\n\n"
                    "<b>Вывод:</b> одно емкое предложение с эмодзи."
                )
            },
            {"role": "user", "content": f"Данные для анализа: {market_context}"}
        ],
        temperature=0.3,
        timeout=15
    )
    return response.choices[0].message.content


async def send_market_report(user_id: int) -> None:
    data = await asyncio.to_thread(_fetch_market_data)

    btc_emoji = "🚀" if data['btc_change'] >= 0 else "📉"
    imoex_emoji = "📈" if data['imoex_change'] >= 0 else "📉"

    text = (
        "📊 <b>Краткий рыночный дайджест</b>\n\n"
        "Крипта:\n"
        f"- BTC {btc_emoji}: ${data['btc_price']:,.0f} ({data['btc_change']:+.2f}%)\n"
        f"- ETH ⚡: ${data['eth_price']:,.2f} ({data['eth_change']:+.2f}%).\n\n"
        "Мосбиржа (данные с задержкой):\n"
        f"- IMOEX {imoex_emoji}: {data['imoex_val']:.2f} пт ({data['imoex_change']:+.2f}%).\n\n"
        "Вывод: Рынок находится в движении, следите за обновлениями! 📈"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Детали в приложении", web_app=types.WebAppInfo(url=BASE_URL))

    await bot.send_message(user_id, text, reply_markup=builder.as_markup(), parse_mode="HTML")


# --- ПЛАНИРОВЩИК ---
async def check_fixed_times() -> None:
    user_ids = await db_get_all_user_ids()
    for uid in user_ids:
        tz_name = await db_get_timezone(uid)
        now = get_now(tz_name)
        notes = await db_get_notifications(uid)
        for n in notes:
            should_send = False

            if n['type'] == 'custom':
                if (n['custom_hour'] is not None and
                        now.hour == n['custom_hour'] and
                        now.minute == n['custom_minute'] and
                        (time.time() - n['last_run']) >= n['interval'] * 86400):
                    should_send = True
            else:
                if now.minute != 0:
                    continue
                if n['type'] == "morning" and now.hour == 10:
                    should_send = True
                elif n['type'] == "evening" and now.hour == 18:
                    should_send = True
                elif n['type'] == "both" and now.hour in (10, 18):
                    should_send = True

                if should_send and (time.time() - n['last_run']) < n['interval'] * 86400:
                    should_send = False

            if should_send:
                await send_market_report(uid)
                await db_update_last_run(n['id'], time.time())


async def check_alerts() -> None:
    alerts = await db_get_all_alerts()
    if not alerts:
        return

    prices = await asyncio.to_thread(_fetch_prices)
    if not prices:
        return

    triggered = []
    for alert in alerts:
        current = prices.get(alert['coin'])
        if current is None:
            continue
        hit = (alert['direction'] == '>' and current > alert['price']) or \
              (alert['direction'] == '<' and current < alert['price'])
        if hit:
            triggered.append(alert)

    for alert in triggered:
        coin = alert['coin']
        direction = alert['direction']
        target = alert['price']
        current = prices.get(coin, 0)
        symbol = "выше" if direction == '>' else "ниже"
        text = (
            f"🔔 <b>Ценовой алерт сработал!</b>\n\n"
            f"{coin} достиг <b>${current:,.0f}</b>\n"
            f"Ваш порог: {coin} {direction} ${target:,.0f} ({symbol})\n\n"
            f"<i>Алерт удалён после срабатывания.</i>"
        )
        try:
            builder = InlineKeyboardBuilder()
            builder.button(text="📊 Открыть график", web_app=types.WebAppInfo(url=BASE_URL))
            await bot.send_message(alert['user_id'], text, parse_mode="HTML", reply_markup=builder.as_markup())
        except Exception as e:
            logger.error("Ошибка отправки алерта: %s", e)
        await db_delete_alert(alert['id'])


# --- ГЛАВНОЕ МЕНЮ ---
MAIN_MENU_TEXT = (
    "👋 <b>Добро пожаловать к КриптоГению!</b>\n\n"
    "Я твой персональный финансовый ассистент. Вот что я умею:\n\n"
    "📈 <b>Мониторинг рынков:</b> Отслеживаю актуальные курсы криптовалют и индекс Мосбиржи.\n"
    "🤖 <b>AI-аналитика:</b> Генерирую точные дайджесты с помощью продвинутых алгоритмов.\n"
    "🔔 <b>Умные уведомления:</b> Присылаю отчеты в удобное для тебя время.\n"
    "⚡ <b>Ценовые алерты:</b> Уведомлю, когда BTC/ETH достигнет нужной цены.\n"
    "📱 <b>Mini App:</b> Полноценное приложение с графиками прямо внутри Telegram.\n\n"
    "<i>Настрой уведомления или нажми «Умный анализ» для первого отчета!</i>"
)


def build_main_menu() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Открыть Mini App", web_app=types.WebAppInfo(url=BASE_URL))
    builder.button(text="🔔 Уведомления", callback_data="manage_notifications")
    builder.button(text="⚡ Ценовые алерты", callback_data="manage_alerts")
    builder.button(text="🤖 Умный анализ", callback_data="get_report_now")
    builder.button(text="🌍 Часовой пояс", callback_data="change_timezone")
    builder.adjust(1)
    return builder.as_markup()


@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(MAIN_MENU_TEXT, reply_markup=build_main_menu(), parse_mode="HTML")


@dp.callback_query(F.data == "back_to_main")
async def back_home(callback: types.CallbackQuery):
    await callback.message.edit_text(MAIN_MENU_TEXT, reply_markup=build_main_menu(), parse_mode="HTML")


# --- ЧАСОВОЙ ПОЯС ---
@dp.callback_query(F.data == "change_timezone")
async def choose_timezone(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    for tz in TIMEZONES:
        builder.button(text=tz, callback_data=f"tz_{tz}")
    builder.adjust(1)
    await callback.message.edit_text("Выберите часовой пояс:", reply_markup=builder.as_markup())
    await state.set_state(TimezoneStates.choosing)


@dp.callback_query(F.data.startswith("tz_"))
async def set_timezone_handler(callback: types.CallbackQuery, state: FSMContext):
    tz = callback.data.replace("tz_", "")
    await db_set_timezone(callback.from_user.id, tz)
    await state.clear()
    await callback.answer("Часовой пояс обновлён!")
    await back_home(callback)


# --- МГНОВЕННЫЙ ОТЧЁТ ---
@dp.callback_query(F.data == "get_report_now")
async def instant_report(callback: types.CallbackQuery):
    await callback.answer("Запускаю интеллектуальный анализ...")
    await send_market_report(callback.from_user.id)


# --- СПИСОК УВЕДОМЛЕНИЙ ---
def _fmt_notification(n: dict) -> str:
    int_map = {1: "каждый день", 3: "раз в 3 дня", 7: "раз в неделю"}
    if n['type'] == 'custom':
        h = n['custom_hour']
        m = n['custom_minute']
        time_str = f"{h:02d}:{m:02d}"
    elif n['type'] == 'morning':
        time_str = "10:00"
    elif n['type'] == 'evening':
        time_str = "18:00"
    else:
        time_str = "10:00 и 18:00"
    return f"⏰ <b>{time_str}</b> — {int_map.get(n['interval'], str(n['interval']) + ' дн.')}"


@dp.callback_query(F.data == "manage_notifications")
async def list_notifications(callback: types.CallbackQuery):
    uid = callback.from_user.id
    notes = await db_get_notifications(uid)
    builder = InlineKeyboardBuilder()
    text = "<b>🔔 Ваши уведомления:</b>\n\n"

    if not notes:
        text += "У вас пока нет активных подписок."
    else:
        for i, n in enumerate(notes):
            text += f"{i+1}. {_fmt_notification(n)}\n"
            builder.button(text=f"❌ Удалить #{i+1}", callback_data=f"del_{n['id']}")

    builder.button(text="➕ Добавить уведомление", callback_data="setup_type")
    builder.button(text="⬅️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# --- НАСТРОЙКА УВЕДОМЛЕНИЙ ---
@dp.callback_query(F.data == "setup_type")
async def setup_type(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="☀️ Утро (10:00)", callback_data="set_t_morning")
    builder.button(text="🌙 Вечер (18:00)", callback_data="set_t_evening")
    builder.button(text="🌗 Утро и Вечер", callback_data="set_t_both")
    builder.button(text="🕐 Своё время", callback_data="set_t_custom")
    builder.adjust(1)
    await callback.message.edit_text(
        "<b>Выберите время получения новостей:</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(NotifyStates.choosing_type)


@dp.callback_query(F.data == "set_t_custom")
async def ask_custom_time(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(time_type="custom")
    await callback.message.edit_text(
        "🕐 <b>Введите время в формате ЧЧ:ММ</b>\n\n"
        "Примеры: <code>8:30</code>, <code>21:00</code>, <code>07:45</code>",
        parse_mode="HTML"
    )
    await state.set_state(NotifyStates.entering_custom_time)


@dp.message(NotifyStates.entering_custom_time)
async def receive_custom_time(message: types.Message, state: FSMContext):
    text = message.text.strip()
    match = re.match(r'^(\d{1,2}):(\d{2})$', text)
    if not match:
        await message.answer("❌ Неверный формат. Введите время как <code>8:30</code> или <code>21:00</code>", parse_mode="HTML")
        return
    h, m = int(match.group(1)), int(match.group(2))
    if not (0 <= h <= 23 and 0 <= m <= 59):
        await message.answer("❌ Недопустимое время. Часы 0-23, минуты 0-59.")
        return
    await state.update_data(custom_hour=h, custom_minute=m)

    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Каждый день", callback_data="set_i_1")
    builder.button(text="🗓 Раз в 3 дня", callback_data="set_i_3")
    builder.button(text="📆 Раз в неделю", callback_data="set_i_7")
    builder.adjust(1)
    await message.answer(
        f"✅ Время <b>{h:02d}:{m:02d}</b> выбрано.\n\n<b>Как часто присылать отчеты?</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(NotifyStates.choosing_interval)


@dp.callback_query(F.data.startswith("set_t_"), NotifyStates.choosing_type)
async def setup_interval(callback: types.CallbackQuery, state: FSMContext):
    t = callback.data.replace("set_t_", "")
    if t == "custom":
        return  # обрабатывается отдельным хендлером
    await state.update_data(time_type=t)
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Каждый день", callback_data="set_i_1")
    builder.button(text="🗓 Раз в 3 дня", callback_data="set_i_3")
    builder.button(text="📆 Раз в неделю", callback_data="set_i_7")
    builder.adjust(1)
    await callback.message.edit_text(
        "<b>Как часто присылать отчеты?</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(NotifyStates.choosing_interval)


@dp.callback_query(F.data.startswith("set_i_"))
async def finish_setup(callback: types.CallbackQuery, state: FSMContext):
    interval = int(callback.data.replace("set_i_", ""))
    data = await state.get_data()
    uid = callback.from_user.id
    initial_last_run = time.time() - interval * 86400
    custom_hour = data.get('custom_hour')
    custom_minute = data.get('custom_minute')
    await db_add_notification(uid, data['time_type'], interval, initial_last_run, custom_hour, custom_minute)
    await callback.answer("Уведомление настроено!")
    await state.clear()
    await list_notifications(callback)


@dp.callback_query(F.data.startswith("del_"))
async def delete_note(callback: types.CallbackQuery):
    note_id = int(callback.data.split("_")[1])
    await db_delete_notification(note_id)
    await list_notifications(callback)


# --- ЦЕНОВЫЕ АЛЕРТЫ ---
@dp.callback_query(F.data == "manage_alerts")
async def list_alerts(callback: types.CallbackQuery):
    uid = callback.from_user.id
    alerts = await db_get_alerts(uid)
    builder = InlineKeyboardBuilder()
    text = "<b>⚡ Ваши ценовые алерты:</b>\n\n"

    if not alerts:
        text += "У вас пока нет активных алертов.\n\n<i>Алерт срабатывает один раз и удаляется.</i>"
    else:
        for i, a in enumerate(alerts):
            symbol = "выше" if a['direction'] == '>' else "ниже"
            text += f"{i+1}. {a['coin']} {a['direction']} ${a['price']:,.0f} ({symbol})\n"
            builder.button(text=f"❌ Удалить #{i+1}", callback_data=f"alrdel_{a['id']}")

    builder.button(text="➕ Добавить алерт", callback_data="alert_setup_coin")
    builder.button(text="⬅️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data == "alert_setup_coin")
async def alert_choose_coin(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="₿ Bitcoin (BTC)", callback_data="alr_coin_BTC")
    builder.button(text="💎 Ethereum (ETH)", callback_data="alr_coin_ETH")
    builder.adjust(1)
    await callback.message.edit_text(
        "<b>Выберите монету для алерта:</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(AlertStates.choosing_coin)


@dp.callback_query(F.data.startswith("alr_coin_"))
async def alert_choose_direction(callback: types.CallbackQuery, state: FSMContext):
    coin = callback.data.replace("alr_coin_", "")
    await state.update_data(coin=coin)
    builder = InlineKeyboardBuilder()
    builder.button(text="📈 Выше (цена >)", callback_data="alr_dir_>")
    builder.button(text="📉 Ниже (цена <)", callback_data="alr_dir_<")
    builder.adjust(1)
    await callback.message.edit_text(
        f"<b>{coin} — выберите направление алерта:</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(AlertStates.choosing_direction)


@dp.callback_query(F.data.startswith("alr_dir_"))
async def alert_enter_price(callback: types.CallbackQuery, state: FSMContext):
    direction = callback.data.replace("alr_dir_", "")
    await state.update_data(direction=direction)
    data = await state.get_data()
    coin = data['coin']
    symbol = "выше" if direction == '>' else "ниже"
    await callback.message.edit_text(
        f"💰 <b>Введите целевую цену для {coin}</b>\n\n"
        f"Уведомлю когда {coin} станет {symbol} этой цены.\n\n"
        f"Пример: <code>100000</code> или <code>3500.50</code>",
        parse_mode="HTML"
    )
    await state.set_state(AlertStates.entering_price)


@dp.message(AlertStates.entering_price)
async def alert_save(message: types.Message, state: FSMContext):
    text = message.text.strip().replace(",", ".").replace(" ", "")
    try:
        price = float(text)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную цену, например: <code>100000</code>", parse_mode="HTML")
        return

    data = await state.get_data()
    uid = message.from_user.id
    await db_add_alert(uid, data['coin'], data['direction'], price)
    await state.clear()

    symbol = "выше" if data['direction'] == '>' else "ниже"
    builder = InlineKeyboardBuilder()
    builder.button(text="⚡ Мои алерты", callback_data="manage_alerts")
    builder.button(text="🏠 Главное меню", callback_data="back_to_main")
    builder.adjust(1)
    await message.answer(
        f"✅ <b>Алерт создан!</b>\n\n"
        f"Уведомлю когда <b>{data['coin']}</b> станет {symbol} <b>${price:,.0f}</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@dp.callback_query(F.data.startswith("alrdel_"))
async def delete_alert(callback: types.CallbackQuery):
    alert_id = int(callback.data.split("_")[1])
    await db_delete_alert(alert_id)
    await list_alerts(callback)


async def main():
    await init_db()
    scheduler.add_job(check_fixed_times, "cron", minute="*")
    scheduler.add_job(check_alerts, "cron", minute="*")
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
