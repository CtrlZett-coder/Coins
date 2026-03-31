import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from openai import OpenAI

# --- НАСТРОЙКИ ---
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
    confirm_time = State()

async def get_crypto_report(user_id):
    market_context = "BTC $64,580 (+2%), TON $5.42, ETH $3,450. USD/RUB 92.45."
    try:
        response = ai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты аналитик Дипсик. Пиши кратко и дерзко с эмодзи."},
                {"role": "user", "content": f"Сделай сводку: {market_context}"}
            ],
            max_tokens=500
        )
        ai_text = response.choices[0].message.content
    except Exception:
        ai_text = "🤖 Дипсик вне зоны доступа, но рынки работают! Чекай графики."

    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Открыть графики", web_app=types.WebAppInfo(url=BASE_URL))
    await bot.send_message(user_id, ai_text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.message(CommandStart())
async def start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Приложение", web_app=types.WebAppInfo(url=BASE_URL))
    builder.button(text="🔔 Уведомления", callback_data="setup_notify")
    builder.button(text="🧠 Сводка Дипсика", callback_data="get_report_now")
    builder.adjust(1)
    await message.answer("Привет! Я CryptoPulse с ИИ DeepSeek.", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "get_report_now")
async def report_now(callback: types.CallbackQuery):
    await callback.message.answer_chat_action("typing")
    await callback.answer("Дипсик думает...")
    await get_crypto_report(callback.from_user.id)

def get_days_kb(selected_days):
    builder = InlineKeyboardBuilder()
    for i, n in enumerate(DAYS_NAME):
        builder.button(text=f"{n} ✅" if i in selected_days else n, callback_data=f"toggle_{i}")
    builder.button(text="Готово ➡️", callback_data="days_ready")
    builder.adjust(3)
    return builder.as_markup()

@dp.callback_query(F.data == "setup_notify")
async def start_setup(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(selected_days=[])
    await callback.message.edit_text("Выбери дни:", reply_markup=get_days_kb([]))
    await state.set_state(NotifyStates.choosing_days)

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_day(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get('selected_days', [])
    day_val = int(callback.data.split("_")[1])
    if day_val in selected: selected.remove(day_val)
    else: selected.append(day_val)
    await state.update_data(selected_days=selected)
    await callback.message.edit_reply_markup(reply_markup=get_days_kb(selected))

@dp.callback_query(F.data == "days_ready")
async def days_ready(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Время (ЧЧ:ММ)?")
    await state.set_state(NotifyStates.setting_time)

@dp.message(NotifyStates.setting_time)
async def process_time(message: types.Message, state: FSMContext):
    try:
        datetime.strptime(message.text, "%H:%M")
        await state.update_data(temp_time=message.text)
        builder = InlineKeyboardBuilder()
        builder.button(text="Да ✅", callback_data="confirm_ok")
        await message.answer(f"Время {message.text}, верно?", reply_markup=builder.as_markup())
        await state.set_state(NotifyStates.confirm_time)
    except: await message.answer("Ошибка формата!")

@dp.callback_query(F.data == "confirm_ok")
async def finish_setup(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_notifications[callback.from_user.id] = {"days": data['selected_days'], "time": data['temp_time']}
    await callback.message.edit_text("✅ Готово!")
    await get_crypto_report(callback.from_user.id)
    await state.clear()

async def check_and_send():
    now = datetime.now()
    c_day, c_time = now.weekday(), now.strftime("%H:%M")
    for uid, s in user_notifications.items():
        if c_day in s['days'] and c_time == s['time']:
            await get_crypto_report(uid)

async def main():
    scheduler.add_job(check_and_send, "interval", minutes=1)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
