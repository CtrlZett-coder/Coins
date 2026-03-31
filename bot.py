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

# --- УЛУЧШЕННЫЙ ИИ-ОТЧЕТ (Крипта + Валюта + MOEX) ---

async def get_crypto_report(user_id):
    """Сборная аналитика от Дипсика"""
    market_context = (
        "КРИПТА: BTC $70,230 (+3.5%), TON $5.42, ETH $3,610. "
        "ВАЛЮТА: USD/RUB 92.45, CNY/RUB 12.75. "
        "МОСБИРЖА (MOEX): Индекс 3310.45 (+0.8%), Акции Газпром и Сбер в зеленой зоне."
    )

    try:
        response = ai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты — финансовый эксперт Дипсик. Проанализируй крипту, валюту и Мосбиржу. Пиши кратко, профессионально, но с долей хайпа. Используй MarkdownV2 для оформления. В конце позови в Mini App."},
                {"role": "user", "content": market_context}
            ],
            max_tokens=600
        )
        ai_text = response.choices[0].message.content
    except Exception:
        ai_text = "🤖 *Дипсик на связи\\!*\n\nРынки кипят: BTC пробил $70k, а Мосбиржа показывает рост\\. USD/RUB стабилен на 92\\.45\\. Все детали уже в приложении\\!"

    builder = InlineKeyboardBuilder()
    # Ссылка на Mini App (теперь упоминаем MOEX)
    builder.button(text="📊 Crypto & MOEX Dashboard", web_app=types.WebAppInfo(url=BASE_URL))
    
    await bot.send_message(user_id, ai_text, reply_markup=builder.as_markup(), parse_mode="MarkdownV2")

# --- ГЕНЕРАТОР КРАСИВОЙ КЛАВИАТУРЫ ДНЕЙ ---

def get_days_kb(selected_days):
    builder = InlineKeyboardBuilder()
    # Дни недели в сетке 3x3
    for i, name in enumerate(DAYS_NAME):
        text = f"✅ {name}" if i in selected_days else name
        builder.button(text=text, callback_data=f"toggle_{i}")
    
    builder.adjust(3) # Делаем по 3 кнопки в ряд (Пн Вт Ср)
    
    # Нижний ряд функциональных кнопок
    builder.row(types.InlineKeyboardButton(text="📅 Каждый день", callback_data="toggle_all"))
    builder.row(types.InlineKeyboardButton(text="Готово ➡️", callback_data="days_ready"))
    return builder.as_markup()

# --- ОБРАБОТЧИКИ МЕНЮ ---

@dp.message(CommandStart())
async def start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="📈 Открыть CryptoPulse (MOEX)", web_app=types.WebAppInfo(url=BASE_URL))
    builder.button(text="🔔 Мои уведомления", callback_data="view_notifies")
    builder.button(text="🧠 Анализ рынков", callback_data="get_report_now")
    builder.adjust(1)
    
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Я отслеживаю Крипту, Валюту и Индексы Мосбиржи.\n"
        "Выбери действие ниже:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "view_notifies")
async def view_notifies(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    builder = InlineKeyboardBuilder()
    
    if user_id in user_notifications:
        settings = user_notifications[user_id]
        days_str = ", ".join([DAYS_NAME[i] for i in settings['days']])
        text = f"⚙️ **Твои настройки:**\n\nДни: `{days_str}`\nВремя: `{settings['time']}`"
        builder.button(text="✏️ Изменить", callback_data="setup_notify")
        builder.button(text="❌ Удалить", callback_data="delete_notify")
    else:
        text = "🔔 У тебя пока нет активных уведомлений."
        builder.button(text="➕ Добавить уведомление", callback_data="setup_notify")
    
    builder.button(text="⬅️ Назад", callback_data="to_main")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "to_main")
async def to_main(callback: types.CallbackQuery):
    # Просто перевызываем старт (но в формате edit)
    builder = InlineKeyboardBuilder()
    builder.button(text="📈 Открыть CryptoPulse (MOEX)", web_app=types.WebAppInfo(url=BASE_URL))
    builder.button(text="🔔 Мои уведомления", callback_data="view_notifies")
    builder.button(text="🧠 Анализ рынков", callback_data="get_report_now")
    builder.adjust(1)
    await callback.message.edit_text("Выбери действие ниже:", reply_markup=builder.as_markup())

# --- ЛОГИКА НАСТРОЙКИ ---

@dp.callback_query(F.data == "setup_notify")
async def start_setup(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(selected_days=[])
    await callback.message.edit_text("Выбери дни для отчета:", reply_markup=get_days_kb([]))
    await state.set_state(NotifyStates.choosing_days)

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_day(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get('selected_days', [])
    
    call_data = callback.data.split("_")[1]
    
    if call_data == "all":
        selected = list(range(7)) if len(selected) < 7 else []
    else:
        day_idx = int(call_data)
        if day_idx in selected: selected.remove(day_idx)
        else: selected.append(day_idx)
        
    await state.update_data(selected_days=selected)
    await callback.message.edit_reply_markup(reply_markup=get_days_kb(selected))

@dp.callback_query(F.data == "days_ready")
async def days_ready(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('selected_days'):
        await callback.answer("⚠️ Выбери хотя бы один день!", show_alert=True)
        return
    await callback.message.answer("Введите время в формате ЧЧ:ММ (например, 08:30):")
    await state.set_state(NotifyStates.setting_time)

@dp.message(NotifyStates.setting_time)
async def process_time(message: types.Message, state: FSMContext):
    try:
        datetime.strptime(message.text, "%H:%M")
        await state.update_data(temp_time=message.text)
        builder = InlineKeyboardBuilder()
        builder.button(text="Да, всё верно ✅", callback_data="confirm_ok")
        builder.button(text="Изменить ❌", callback_data="setup_notify")
        await message.answer(f"Присылать отчет в {message.text}?", reply_markup=builder.as_markup())
        await state.set_state(NotifyStates.confirm_time)
    except:
        await message.answer("⚠️ Неверный формат! Введи время вот так: 14:00")

@dp.callback_query(F.data == "confirm_ok")
async def finish_setup(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_notifications[callback.from_user.id] = {
        "days": data['selected_days'],
        "time": data['temp_time']
    }
    await callback.message.edit_text("✅ Настройка завершена! Лови свежий анализ:")
    await get_crypto_report(callback.from_user.id)
    await state.clear()

@dp.callback_query(F.data == "delete_notify")
async def delete_notify(callback: types.CallbackQuery):
    user_notifications.pop(callback.from_user.id, None)
    await callback.answer("Уведомления удалены")
    await to_main(callback)

@dp.callback_query(F.data == "get_report_now")
async def report_now(callback: types.CallbackQuery):
    await callback.answer("Дипсик анализирует данные...")
    await get_crypto_report(callback.from_user.id)

# --- ПЛАНИРОВЩИК ---

async def check_and_send():
    now = datetime.now()
    c_day, c_time = now.weekday(), now.strftime("%H:%M")
    for uid, s in user_notifications.items():
        if c_day in s['days'] and c_time == s['time']:
            try:
                await get_crypto_report(uid)
            except: pass

async def main():
    scheduler.add_job(check_and_send, "interval", minutes=1)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
