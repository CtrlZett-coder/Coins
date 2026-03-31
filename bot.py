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
from openai import OpenAI  # Библиотека для работы с DeepSeek

# --- НАСТРОЙКИ ---
TOKEN = "8698978039:AAGJnlo6wdHE8k7I1Jie8XMKE8Di0EmRshw"
BASE_URL = "https://Ctrlzett-coder.github.io/Coins/"

# ВСТАВЬ СВОЙ КЛЮЧ DEEPSEEK НИЖЕ
DEEPSEEK_API_KEY = "sk-b0241be117b0481e99ecb1446330f8f6"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()

# Инициализация ИИ клиента (DeepSeek использует стандарт OpenAI)
ai_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

user_notifications = {} 
DAYS_NAME = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

class NotifyStates(StatesGroup):
    choosing_days = State()
    setting_time = State()
    confirm_time = State()

# --- УМНАЯ ГЕНЕРАЦИЯ ОТЧЕТА ЧЕРЕЗ AI ---

async def get_crypto_report(user_id):
    """DeepSeek анализирует рынок и пишет уникальный текст"""
    
    # 1. Скармливаем нейросети текущие цифры (можно обновлять вручную или через API)
    market_context = (
        "Данные: BTC $64,580 (+2%), TON $5.42, ETH $3,450. "
        "Курсы: USD/RUB 92.45, USD/UAH 39.10, USD/KZT 447.15."
    )

    try:
        # 2. Запрос к DeepSeek
        response = ai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты — финансовый аналитик Дипсик. Пиши краткие, дерзкие и профессиональные отчеты. Используй эмодзи и Markdown. Обращайся на 'ты'. В конце напомни заглянуть в графики."},
                {"role": "user", "content": f"Проанализируй эти данные и напиши сводку: {market_context}"}
            ],
            max_tokens=500
        )
        ai_text = response.choices[0].message.content
    except Exception as e:
        logging.error(f"Ошибка AI: {e}")
        ai_text = "⚠️ Дипсик временно вне сети, но рынки шумят! BTC в районе $64k, TON держится бодро. Загляни в графики, там всё наглядно!"

    # 3. Формируем сообщение
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Открыть графики CryptoPulse", web_app=types.WebAppInfo(url=BASE_URL))
    
    await bot.send_message(user_id, ai_text, reply_markup=builder.as_markup(), parse_mode="Markdown")

# --- ОБРАБОТЧИКИ (Остаются без изменений в логике, но связаны с новой функцией) ---

@dp.message(CommandStart())
async def start(message: types.Message):
    text = (
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Я — **CryptoPulse**, усиленный интеллектом DeepSeek.\n"
        "Я не просто показываю цифры, я объясняю, что происходит.\n\n"
        "Жми на кнопку, чтобы получить живой анализ!"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Войти в приложение", web_app=types.WebAppInfo(url=BASE_URL))
    builder.button(text="🔔 Настроить уведомления", callback_data="setup_notify")
    builder.button(text="🧠 Спросить Дипсика (Анализ)", callback_data="get_report_now")
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "get_report_now")
async def report_now(callback: types.CallbackQuery):
    # Показываем статус "печатает", пока AI думает
    await callback.message.answer_chat_action("typing")
    await callback.answer("Дипсик изучает графики...")
    await get_crypto_report(callback.from_user.id)

@dp.message(Command("notifies"))
async def cmd_notifies(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_notifications:
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Добавить уведомление", callback_data="setup_notify")
        await message.answer("🔔 Уведомления не настроены.", reply_markup=builder.as_markup())
    else:
        s = user_notifications[user_id]
        days_str = ", ".join([DAYS_NAME[i] for i in s['days']])
        builder = InlineKeyboardBuilder()
        builder.button(text="✏️ Изменить", callback_data="setup_notify")
        builder.button(text="❌ Удалить", callback_data="delete_notify")
        await message.answer(f"⚙️ **Твой график:**\n\nДни: `{days_str}`\nВремя: `{s['time']}`", 
                             reply_markup=builder.as_markup(), parse_mode="Markdown")

# --- ЛОГИКА НАСТРОЙКИ (Кратко) ---

@dp.callback_query(F.data == "setup_notify")
async def start_setup(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(selected_days=[])
    await callback.message.edit_text("Выбери дни:", reply_markup=get_days_kb([]))
    await state.set_state(NotifyStates.choosing_days)

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_day(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get('selected_days', [])
    day_val = callback.data.split("_")[1]
    if day_val == "all": selected = list(range(7)) if len(selected) < 7 else []
    else:
        idx = int(day_val)
        if idx in selected: selected.remove(idx)
        else: selected.append(idx)
    await state.update_data(selected_days=selected)
    await callback.message.edit_reply_markup(reply_markup=get_days_kb(selected))

@dp.callback_query(F.data == "days_ready")
async def days_ready(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("В какое время (ЧЧ:ММ)?")
    await state.set_state(NotifyStates.setting_time)

@dp.message(NotifyStates.setting_time)
async def process_time(message: types.Message, state: FSMContext):
    try:
        datetime.strptime(message.text, "%H:%M")
        await state.update_data(temp_time=message.text)
        builder = InlineKeyboardBuilder()
        builder.button(text="Да ✅", callback_data="confirm_ok")
        builder.button(text="Нет ❌", callback_data="setup_notify")
        await message.answer(f"Время {message.text}, верно?", reply_markup=builder.as_markup())
        await state.set_state(NotifyStates.confirm_time)
    except: await message.answer("Ошибка формата!")

@dp.callback_query(F.data == "confirm_ok")
async def finish_setup(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_notifications[callback.from_user.id] = {"days": data['selected_days'], "time": data['temp_time']}
    await callback.message.edit_text("✅ Готово! Твой первый AI-отчет:")
    await get_crypto_report(callback.from_user.id)
    await state.clear()

@dp.callback_query(F.data == "delete_notify")
async def delete_notify(callback: types.CallbackQuery):
    user_notifications.pop(callback.from_user.id, None)
    await callback.message.edit_text("❌ Удалено.")

def get_days_kb(selected_days):
    builder = InlineKeyboardBuilder()
    for i, n in enumerate(DAYS_NAME):
        builder.button(text=f"{n} ✅" if i in selected_days else n, callback_data=f"toggle_{i}")
    builder.button(text="Готово ➡️", callback_data="days_ready")
    builder.adjust(3)
    return builder.as_markup()

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
