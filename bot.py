import asyncio
import logging
import requests
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
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

# База уведомлений теперь хранит: {uid: [{"id": 1, "type": "morning", "interval": 1, "next_run": dt}]}
user_notifications = {} 

class NotifyStates(StatesGroup):
    choosing_type = State()
    choosing_interval = State()

def get_live_market_data():
    try:
        crypto_res = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,ton&vs_currencies=usd&include_24hr_change=true", timeout=5).json()
        moex_res = requests.get("https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json?iss.meta=off&iss.only=marketdata&marketdata.columns=LAST", timeout=5).json()
        imoex = moex_res['marketdata']['data'][0][0]
        return f"BTC: ${crypto_res['bitcoin']['usd']}, ETH: ${crypto_res['ethereum']['usd']}, IMOEX: {imoex} пт."
    except:
        return "BTC: $69000, ETH: $3500, IMOEX: 3200"

async def send_market_report(user_id):
    market_context = get_live_market_data()
    try:
        response = ai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты финансовый аналитик. Пиши кратко, дерзко, с эмодзи."},
                {"role": "user", "content": f"Сделай отчет: {market_context}"}
            ]
        )
        text = response.choices[0].message.content
    except:
        text = "🤖 Рынки в движении! Загляни в приложение."
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Детали", web_app=types.WebAppInfo(url=BASE_URL))
    await bot.send_message(user_id, text, reply_markup=builder.as_markup())

# --- ГЛАВНОЕ МЕНЮ ---
@dp.message(CommandStart())
async def start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Приложение", web_app=types.WebAppInfo(url=BASE_URL))
    builder.button(text="🔔 Уведомления", callback_data="manage_notifications")
    builder.button(text="🧠 Анализ", callback_data="get_report_now")
    builder.adjust(1)
    await message.answer("CryptoGenius Pro ⚡️", reply_markup=builder.as_markup())

# --- СПИСОК С КНОПКОЙ УДАЛЕНИЯ ---
@dp.callback_query(F.data == "manage_notifications")
async def list_notifications(callback: types.CallbackQuery):
    uid = callback.from_user.id
    notes = user_notifications.get(uid, [])
    
    builder = InlineKeyboardBuilder()
    text = "🔔 **Ваши настройки:**\n\n"
    
    if not notes:
        text += "Нет активных уведомлений."
    else:
        types_map = {"morning": "10:00", "evening": "18:00", "both": "10:00 & 18:00"}
        int_map = {1: "Ежедневно", 3: "Раз в 3 дня", 7: "Раз в неделю"}
        
        for i, n in enumerate(notes):
            text += f"{i+1}. ⏰ {types_map[n['type']]} — {int_map[n['interval']]}\n"
            builder.button(text=f"❌ Удалить #{i+1}", callback_data=f"del_{i}")

    builder.button(text="➕ Добавить", callback_data="setup_type")
    builder.button(text="⬅️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

# --- ДОБАВЛЕНИЕ (ФИКСИРОВАННОЕ ВРЕМЯ) ---
@dp.callback_query(F.data == "setup_type")
async def setup_type(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="☀️ Утро (10:00)", callback_data="set_t_morning")
    builder.button(text="🌙 Вечер (18:00)", callback_data="set_t_evening")
    builder.button(text="🌗 Утро и Вечер", callback_data="set_t_both")
    builder.adjust(1)
    await callback.message.edit_text("Выберите время получения новостей:", reply_markup=builder.as_markup())
    await state.set_state(NotifyStates.choosing_type)

@dp.callback_query(F.data.startswith("set_t_"))
async def setup_interval(callback: types.CallbackQuery, state: FSMContext):
    time_type = callback.data.replace("set_t_", "")
    await state.update_data(time_type=time_type)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Каждый день", callback_data="set_i_1")
    builder.button(text="🗓 Через 3 дня", callback_data="set_i_3")
    builder.button(text="📆 Через неделю", callback_data="set_i_7")
    builder.adjust(1)
    await callback.message.edit_text("Как часто присылать отчеты?", reply_markup=builder.as_markup())
    await state.set_state(NotifyStates.choosing_interval)

@dp.callback_query(F.data.startswith("set_i_"))
async def finish_setup(callback: types.CallbackQuery, state: FSMContext):
    interval = int(callback.data.replace("set_i_", ""))
    data = await state.get_data()
    uid = callback.from_user.id
    
    if uid not in user_notifications: user_notifications[uid] = []
    user_notifications[uid].append({
        "type": data['time_type'],
        "interval": interval,
        "last_run": datetime.now() - timedelta(days=interval) # Чтобы сработало сразу в ближайшее время
    })
    
    await callback.answer("✅ Уведомление настроено!")
    await state.clear()
    await list_notifications(callback)

# --- УДАЛЕНИЕ ---
@dp.callback_query(F.data.startswith("del_"))
async def delete_note(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    uid = callback.from_user.id
    if uid in user_notifications and len(user_notifications[uid]) > idx:
        user_notifications[uid].pop(idx)
    await callback.answer("Удалено")
    await list_notifications(callback)

# --- ПЛАНИРОВЩИК (ПРОВЕРКА КАЖДУЮ МИНУТУ) ---
async def check_fixed_times():
    now = datetime.now()
    time_str = now.strftime("%H:%M")
    
    for uid, notes in user_notifications.items():
        for n in notes:
            # Проверка времени
            is_time = False
            if n['type'] == "morning" and time_str == "10:00": is_time = True
            elif n['type'] == "evening" and time_str == "18:00": is_time = True
            elif n['type'] == "both" and time_str in ["10:00", "18:00"]: is_time = True
            
            if is_time:
                # Проверка интервала дней
                if (now - n['last_run']).days >= n['interval']:
                    await send_market_report(uid)
                    n['last_run'] = now # Обновляем дату последнего запуска

@dp.callback_query(F.data == "get_report_now")
async def instant_report(callback: types.CallbackQuery):
    await callback.answer("Анализирую...")
    await send_market_report(callback.from_user.id)

@dp.callback_query(F.data == "back_to_main")
async def back_home(callback: types.CallbackQuery):
    await start(callback.message)

async def main():
    scheduler.add_job(check_fixed_times, "interval", minutes=1)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
