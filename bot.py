import asyncio
import logging
import requests  # Добавь этот импорт
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from openai import OpenAI

# --- НАСТРОЙКИ ---
# ВАЖНО: Срочно перевыпусти токены, так как ты опубликовал их в чате!
TOKEN = "8698978039:AAGJnlo6wdHE8k7I1Jie8XMKE8Di0EmRshw"
BASE_URL = "https://Ctrlzett-coder.github.io/Coins/"
DEEPSEEK_API_KEY = "sk-b0241be117b0481e99ecb1446330f8f6"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()
ai_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

user_notifications = {} 
DAYS_NAME = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

class NotifyStates(StatesGroup):
    choosing_days = State()
    setting_time = State()

# --- НОВАЯ ФУНКЦИЯ ДИНАМИЧЕСКИХ ДАННЫХ ---
def get_live_market_data():
    """Собирает реальные цифры с бирж перед отправкой в DeepSeek"""
    try:
        # 1. Криптовалюты (CoinGecko)
        crypto_res = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,ton&vs_currencies=usd&include_24hr_change=true",
            timeout=5
        ).json()
        
        btc = crypto_res['bitcoin']['usd']
        btc_ch = crypto_res['bitcoin']['usd_24h_change']
        eth = crypto_res['ethereum']['usd']
        ton = crypto_res['ton']['usd']

        # 2. Индекс Мосбиржи (MOEX ISS API)
        moex_res = requests.get(
            "https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json?iss.meta=off&iss.only=marketdata&marketdata.columns=LAST",
            timeout=5
        ).json()
        imoex = moex_res['marketdata']['data'][0][0]

        # 3. Курс валют (примерные данные, можно расширить)
        # Для простоты берем базовый контекст или доп. API
        
        return (f"BTC: ${btc} ({btc_ch:.2f}%), ETH: ${eth}, TON: ${ton}. "
                f"IMOEX (Мосбиржа): {imoex} пт.")
    except Exception as e:
        logging.error(f"Data error: {e}")
        return "BTC: $69000, ETH: $3500, IMOEX: 3200 (данные задерживаются)"

async def get_crypto_report(user_id):
    # Получаем СВЕЖИЕ данные вместо статичной строки
    market_context = get_live_market_data()
    
    try:
        response = ai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты финансовый аналитик. Пиши кратко, дерзко, используй эмодзи. Анализируй крипту и Мосбиржу на основе свежих цифр."},
                {"role": "user", "content": f"Сделай отчет по рынку на основе этих цифр: {market_context}"}
            ],
            temperature=0.7 # Немного креатива для прогнозов
        )
        ai_text = response.choices[0].message.content
    except Exception as e:
        logging.error(f"AI Error: {e}")
        ai_text = "🤖 Дипсик временно оффлайн, но графики шепчут: пора заглянуть в Mini App! 🚀"

    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Детали в приложении", web_app=types.WebAppInfo(url=BASE_URL))
    await bot.send_message(user_id, ai_text, reply_markup=builder.as_markup(), parse_mode="Markdown")

# --- ОСТАЛЬНАЯ ЧАСТЬ КОДА (БЕЗ ИЗМЕНЕНИЙ) ---
@dp.message(CommandStart())
async def start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Открыть Mini App", web_app=types.WebAppInfo(url=BASE_URL))
    builder.button(text="🔔 Настроить уведомления", callback_data="manage_notifications")
    builder.button(text="🧠 Анализ DeepSeek", callback_data="get_report_now")
    builder.adjust(1)
    await message.answer("Главное меню CryptoPulse ⚡️", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "manage_notifications")
async def list_notifications(callback: types.CallbackQuery):
    uid = callback.from_user.id
    notes = user_notifications.get(uid, [])
    text = "🔔 **Ваши уведомления:**\n\n"
    if not notes:
        text += "У вас пока нет активных уведомлений."
    else:
        for i, n in enumerate(notes):
            days_str = ", ".join([DAYS_NAME[d] for d in n['days']])
            if len(n['days']) == 7: days_str = "Каждый день"
            text += f"{i+1}. ⏰ {n['time']} — {days_str}\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить", callback_data="setup_notify")
    if notes:
        builder.button(text="🗑 Очистить всё", callback_data="clear_notify")
    builder.button(text="⬅️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "setup_notify")
async def start_setup(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(selected_days=[])
    await callback.message.edit_text("Выберите дни недели:", reply_markup=get_days_kb([]))
    await state.set_state(NotifyStates.choosing_days)

def get_days_kb(selected_days):
    builder = InlineKeyboardBuilder()
    for i, n in enumerate(DAYS_NAME):
        text = f"{n} ✅" if i in selected_days else n
        builder.button(text=text, callback_data=f"toggle_{i}")
    builder.button(text="📅 Каждый день", callback_data="toggle_all")
    builder.button(text="Далее ➡️", callback_data="days_ready")
    builder.adjust(3, 3, 1, 1)
    return builder.as_markup()

@dp.callback_query(F.data.startswith("toggle_"))
async def handle_day_selection(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get('selected_days', [])
    if callback.data == "toggle_all":
        selected = [0,1,2,3,4,5,6] if len(selected) < 7 else []
    else:
        day_val = int(callback.data.split("_")[1])
        if day_val in selected: selected.remove(day_val)
        else: selected.append(day_val)
    await state.update_data(selected_days=selected)
    await callback.message.edit_reply_markup(reply_markup=get_days_kb(selected))

@dp.callback_query(F.data == "days_ready")
async def ask_time(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('selected_days'):
        return await callback.answer("Выберите хотя бы один день!", show_alert=True)
    await callback.message.edit_text("Введите время в формате ЧЧ:ММ (например, 09:30):")
    await state.set_state(NotifyStates.setting_time)

@dp.message(NotifyStates.setting_time)
async def save_notification(message: types.Message, state: FSMContext):
    try:
        time_text = message.text.strip()
        datetime.strptime(time_text, "%H:%M")
        data = await state.get_data()
        uid = message.from_user.id
        if uid not in user_notifications: user_notifications[uid] = []
        user_notifications[uid].append({"days": data['selected_days'], "time": time_text})
        await message.answer(f"✅ Уведомление на {time_text} успешно добавлено!")
        await state.clear()
        await list_notifications_message(message)
    except:
        await message.answer("❌ Ошибка формата! Введите время как 08:00")

async def list_notifications_message(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ К списку", callback_data="manage_notifications")
    await message.answer("Настройки обновлены.", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "back_to_main")
async def back_home(callback: types.CallbackQuery):
    await start(callback.message)

@dp.callback_query(F.data == "get_report_now")
async def instant_report(callback: types.CallbackQuery):
    await callback.answer("Дипсик анализирует рынки...")
    await get_crypto_report(callback.from_user.id)

@dp.callback_query(F.data == "clear_notify")
async def clear_all(callback: types.CallbackQuery):
    user_notifications[callback.from_user.id] = []
    await callback.answer("Все уведомления удалены")
    await list_notifications(callback)

async def check_and_send():
    now = datetime.now()
    c_day, c_time = now.weekday(), now.strftime("%H:%M")
    for uid, notes in user_notifications.items():
        for n in notes:
            if c_day in n['days'] and c_time == n['time']:
                await get_crypto_report(uid)

async def main():
    scheduler.add_job(check_and_send, "interval", minutes=1)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
