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

# --- НАСТРОЙКИ ---
TOKEN = "8698978039:AAGJnlo6wdHE8k7I1Jie8XMKE8Di0EmRshw"
BASE_URL = "https://Ctrlzett-coder.github.io/Coins/"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()

# Имитация базы данных
user_notifications = {} # {user_id: {"days": [0,1], "time": "10:00"}}
DAYS_NAME = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

class NotifyStates(StatesGroup):
    choosing_days = State()
    setting_time = State()
    confirm_time = State()

# --- КЛАВИАТУРЫ ---

def get_days_kb(selected_days):
    builder = InlineKeyboardBuilder()
    for i, name in enumerate(DAYS_NAME):
        text = f"{name} ✅" if i in selected_days else name
        builder.button(text=text, callback_data=f"toggle_{i}")
    builder.button(text="Ежедневно 📅", callback_data="toggle_all")
    builder.button(text="Готово ➡️", callback_data="days_ready")
    builder.adjust(3, 3, 1, 1)
    return builder.as_markup()

# --- ОБРАБОТЧИКИ УВЕДОМЛЕНИЙ ---

@dp.message(Command("notifies"))
async def cmd_notifies(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_notifications:
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Добавить уведомление", callback_data="setup_notify")
        await message.answer("🔔 У вас пока нет настроенных уведомлений.", reply_markup=builder.as_markup())
    else:
        settings = user_notifications[user_id]
        days_str = ", ".join([DAYS_NAME[i] for i in settings['days']])
        builder = InlineKeyboardBuilder()
        builder.button(text="✏️ Изменить", callback_data="setup_notify")
        builder.button(text="❌ Удалить", callback_data="delete_notify")
        await message.answer(
            f"⚙️ **Ваши уведомления:**\n\nДни: `{days_str}`\nВремя: `{settings['time']}`",
            reply_markup=builder.as_markup(), parse_mode="Markdown"
        )

@dp.callback_query(F.data == "setup_notify")
async def start_setup(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(selected_days=[])
    await callback.message.edit_text("Выбери дни для получения сводки:", reply_markup=get_days_kb([]))
    await state.set_state(NotifyStates.choosing_days)

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_day(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get('selected_days', [])
    day_val = callback.data.split("_")[1]

    if day_val == "all":
        selected = list(range(7)) if len(selected) < 7 else []
    else:
        day_idx = int(day_val)
        if day_idx in selected: selected.remove(day_idx)
        else: selected.append(day_idx)

    await state.update_data(selected_days=selected)
    await callback.message.edit_reply_markup(reply_markup=get_days_kb(selected))

@dp.callback_query(F.data == "days_ready")
async def days_ready(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('selected_days'):
        await callback.answer("Выберите хотя бы один день!", show_alert=True)
        return
    await callback.message.answer("Введите время в формате ЧЧ:ММ (например, 09:00):")
    await state.set_state(NotifyStates.setting_time)

@dp.message(NotifyStates.setting_time)
async def process_time(message: types.Message, state: FSMContext):
    try:
        datetime.strptime(message.text, "%H:%M")
        await state.update_data(temp_time=message.text)
        builder = InlineKeyboardBuilder()
        builder.button(text="Да ✅", callback_data="confirm_ok")
        builder.button(text="Нет ❌", callback_data="setup_notify")
        await message.answer(f"Вы выбрали {message.text}. Всё верно?", reply_markup=builder.as_markup())
        await state.set_state(NotifyStates.confirm_time)
    except ValueError:
        await message.answer("Ошибка! Введите время корректно (например, 20:15):")

@dp.callback_query(F.data == "confirm_ok")
async def finish_setup(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_notifications[callback.from_user.id] = {
        "days": data['selected_days'],
        "time": data['temp_time']
    }
    await callback.message.edit_text("✅ Уведомления успешно настроены!")
    await state.clear()

@dp.callback_query(F.data == "delete_notify")
async def delete_notify(callback: types.CallbackQuery):
    user_notifications.pop(callback.from_user.id, None)
    await callback.message.edit_text("❌ Уведомления удалены.")

# --- ФУНКЦИЯ РАССЫЛКИ (3 ПУНКТА) ---

async def send_daily_updates():
    now = datetime.now()
    current_day = now.weekday()
    current_time = now.strftime("%H:%M")

    for user_id, settings in user_notifications.items():
        if current_day in settings['days'] and current_time == settings['time']:
            # Предложение 1: Красивая карточка (данные для примера)
            text = (
                "📈 **Утренний отчет CryptoPulse**\n\n"
                "💎 **TON:** $5.24 (`+1.2%`)\n"
                "₿ **BTC:** $64,120 (`-0.5%`)\n"
                "🇷🇺 **USD/RUB:** 91.40\n\n"
                "🔥 **Новости:** Разработчики TON анонсировали новые функции для Mini Apps!"
            )
            
            # Предложение 2: Ссылка сразу на нужный график (например, на TON)
            # Мы можем передать параметр в WebApp, если твой JS умеет его читать
            builder = InlineKeyboardBuilder()
            builder.button(text="📊 Открыть график TON", web_app=types.WebAppInfo(url=f"{BASE_URL}"))
            
            try:
                await bot.send_message(user_id, text, reply_markup=builder.as_markup(), parse_mode="Markdown")
            except Exception:
                pass

# --- СТАНДАРТНЫЕ КОМАНДЫ ---

@dp.message(CommandStart())
async def start(message: types.Message):
    text = (
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "📈 Добро пожаловать в **CryptoPulse**.\n"
        "Я твой финансовый трекер.\n\n"
        "Используй /notifies, чтобы настроить ежедневные отчеты.\n"
        "Нажимай кнопку ниже, чтобы войти!"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Открыть CryptoPulse", web_app=types.WebAppInfo(url=BASE_URL))
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

async def main():
    # Запуск планировщика (проверка каждую минуту)
    scheduler.add_job(send_daily_updates, "interval", minutes=1)
    scheduler.start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
