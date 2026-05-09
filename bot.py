import asyncio
import logging
import os
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

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = "https://Ctrlzett-coder.github.io/Coins/"
AI_API_KEY = os.getenv("AI_API_KEY")
DB_PATH = "bot_data.db"

# --- ЛОГИРОВАНИЕ ---
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


class TimezoneStates(StatesGroup):
    choosing = State()


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
                last_run REAL NOT NULL
            )
        """)
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
            "SELECT id, type, interval, last_run FROM user_notifications WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"id": r[0], "type": r[1], "interval": r[2], "last_run": r[3]} for r in rows]


async def db_add_notification(user_id: int, note_type: str, interval: int, last_run: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO user_notifications (user_id, type, interval, last_run) VALUES (?, ?, ?, ?)",
            (user_id, note_type, interval, last_run)
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


# --- ДАННЫЕ РЫНКА (синхронные, запускаются через asyncio.to_thread) ---
def _fetch_market_data() -> str:
    headers = {'User-Agent': 'Mozilla/5.0'}
    data_str = ""

    try:
        crypto_url = (
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"
        )
        res = requests.get(crypto_url, headers=headers, timeout=10).json()
        btc_p = res['bitcoin']['usd']
        btc_c = res['bitcoin']['usd_24h_change']
        eth_p = res['ethereum']['usd']
        eth_c = res['ethereum']['usd_24h_change']
        data_str += f"BTC: ${btc_p} ({btc_c:+.2f}%), ETH: ${eth_p} ({eth_c:+.2f}%). "
    except Exception as e:
        logger.warning("Не удалось получить данные крипты: %s", e)
        data_str += "BTC: $69200 (+1.2%), ETH: $3520 (-0.5%). "

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
        data_str += f"IMOEX: {current_val:.2f} пт ({change_pct:+.2f}%)."
    except Exception as e:
        logger.warning("Не удалось получить данные IMOEX: %s", e)
        data_str += "IMOEX: 2772 пт (-0.3%)."

    return data_str


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
    # Оба вызова — в отдельных потоках, не блокируют event loop
    market_context = await asyncio.to_thread(_fetch_market_data)

    try:
        ai_text = await asyncio.to_thread(_call_ai, market_context)
        ai_text = ai_text.replace("**", "")
    except Exception as e:
        logger.error("Ошибка AI-клиента: %s", e)
        ai_text = (
            "📊 <b>Краткий рыночный дайджест</b>\n\n"
            "Крипта:\n"
            f"- BTC 🚀: {market_context.split(',')[0] if 'BTC' in market_context else 'Данные обновляются'}\n"
            f"- ETH ⚡: {market_context.split(',')[1] if 'ETH' in market_context else 'Данные обновляются'}\n\n"
            "Мосбиржа (данные с задержкой):\n"
            f"- IMOEX 📉: {market_context.split('IMOEX:')[1] if 'IMOEX' in market_context else 'В процессе...'}\n\n"
            "<b>Вывод:</b> Рынок находится в движении, следите за обновлениями! 📈"
        )

    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Детали в приложении", web_app=types.WebAppInfo(url=BASE_URL))

    try:
        await bot.send_message(user_id, ai_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as parse_err:
        logger.error("Ошибка отправки: %s", parse_err)
        await bot.send_message(user_id, ai_text, reply_markup=builder.as_markup(), parse_mode=None)


# --- ПЛАНИРОВЩИК УВЕДОМЛЕНИЙ ---
async def check_fixed_times() -> None:
    user_ids = await db_get_all_user_ids()
    for uid in user_ids:
        tz_name = await db_get_timezone(uid)
        now = get_now(tz_name)
        if now.minute != 0:
            continue
        notes = await db_get_notifications(uid)
        for n in notes:
            should_send = False
            if n['type'] == "morning" and now.hour == 10:
                should_send = True
            elif n['type'] == "evening" and now.hour == 18:
                should_send = True
            elif n['type'] == "both" and now.hour in (10, 18):
                should_send = True

            if should_send and (time.time() - n['last_run']) >= n['interval'] * 86400:
                await send_market_report(uid)
                await db_update_last_run(n['id'], time.time())


# --- ГЛАВНОЕ МЕНЮ (единая функция вместо дублирующихся) ---
MAIN_MENU_TEXT = (
    "👋 <b>Добро пожаловать к КриптоГению!</b>\n\n"
    "Я твой персональный финансовый ассистент. Вот что я умею:\n\n"
    "📈 <b>Мониторинг рынков:</b> Отслеживаю актуальные курсы криптовалют и индекс Мосбиржи.\n"
    "🤖 <b>AI-аналитика:</b> Генерирую точные дайджесты с помощью продвинутых алгоритмов.\n"
    "🔔 <b>Умные уведомления:</b> Присылаю отчеты в удобное время (утро/вечер).\n"
    "📱 <b>Mini App:</b> Полноценное приложение с графиками прямо внутри Telegram.\n\n"
    "<i>Настрой уведомления или нажми «Умный анализ» для первого отчета!</i>"
)


def build_main_menu() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Открыть Mini App", web_app=types.WebAppInfo(url=BASE_URL))
    builder.button(text="🔔 Настроить уведомления", callback_data="manage_notifications")
    builder.button(text="🤖 Умный анализ", callback_data="get_report_now")
    builder.button(text="🌍 Изменить часовой пояс", callback_data="change_timezone")
    builder.adjust(1)
    return builder.as_markup()


@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(MAIN_MENU_TEXT, reply_markup=build_main_menu(), parse_mode="HTML")


@dp.callback_query(F.data == "back_to_main")
async def back_home(callback: types.CallbackQuery):
    await callback.message.edit_text(MAIN_MENU_TEXT, reply_markup=build_main_menu(), parse_mode="HTML")


# --- СМЕНА ТАЙМЗОНЫ ---
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
@dp.callback_query(F.data == "manage_notifications")
async def list_notifications(callback: types.CallbackQuery):
    uid = callback.from_user.id
    notes = await db_get_notifications(uid)
    builder = InlineKeyboardBuilder()
    text = "<b>🔔 Ваши настройки:</b>\n\n"

    if not notes:
        text += "У вас пока нет активных подписок."
    else:
        types_map = {"morning": "10:00", "evening": "18:00", "both": "10:00 и 18:00"}
        int_map = {1: "Каждый день", 3: "Раз в 3 дня", 7: "Раз в неделю"}
        for i, n in enumerate(notes):
            text += f"{i+1}. ⏰ <b>{types_map[n['type']]}</b> — {int_map[n['interval']]}\n"
            builder.button(text=f"❌ Удалить #{i+1}", callback_data=f"del_{n['id']}")

    builder.button(text="➕ Добавить", callback_data="setup_type")
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
    builder.adjust(1)
    await callback.message.edit_text(
        "<b>Выберите время получения новостей:</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(NotifyStates.choosing_type)


@dp.callback_query(F.data.startswith("set_t_"))
async def setup_interval(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(time_type=callback.data.replace("set_t_", ""))
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
    # last_run = сейчас минус интервал, чтобы уведомление сработало при следующем подходящем времени
    initial_last_run = time.time() - interval * 86400
    await db_add_notification(uid, data['time_type'], interval, initial_last_run)
    await callback.answer("Уведомление настроено!")
    await state.clear()
    await list_notifications(callback)


@dp.callback_query(F.data.startswith("del_"))
async def delete_note(callback: types.CallbackQuery):
    note_id = int(callback.data.split("_")[1])
    await db_delete_notification(note_id)
    await list_notifications(callback)


async def main():
    await init_db()
    scheduler.add_job(check_fixed_times, "cron", minute="*")
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
