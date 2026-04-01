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

user_notifications = {} 

class NotifyStates(StatesGroup):
    choosing_type = State()
    choosing_interval = State()

def get_live_market_data():
    headers = {'User-Agent': 'Mozilla/5.0'} # Чтобы API не блокировало запросы
    data_str = ""
    
    # 1. Получаем Крипту
    try:
        crypto_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"
        res = requests.get(crypto_url, headers=headers, timeout=10).json()
        data_str += f"BTC: ${res['bitcoin']['usd']}, ETH: ${res['ethereum']['usd']}. "
    except:
        data_str += "BTC: $69200, ETH: $3520 (тестовые данные). "

    # 2. Получаем Мосбиржу
    try:
        moex_url = "https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json?iss.meta=off&iss.only=marketdata"
        res = requests.get(moex_url, headers=headers, timeout=10).json()
        data_str += f"IMOEX: {res['marketdata']['data'][0][0]} пт."
    except:
        data_str += "IMOEX: 3250 пт (тестовые данные)."
        
    return data_str

async def send_market_report(user_id):
    market_context = get_live_market_data()
    
    try:
        response = ai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system", 
                    "content": (
                        "Ты финансовый аналитик. Твоя задача — сделать КРАТКИЙ дайджест. "
                        "Используй ТОЛЬКО HTML теги (<b> для жирного). Запрещено использовать **. "
                        "Формат строго по образцу:\n\n"
                        "📊 <b>Краткий рыночный дайджест</b>\n\n"
                        "Крипта:\n"
                        "- BTC 🚀: $цена — короткая суть.\n"
                        "- ETH ⚡: $цена — короткая суть.\n\n"
                        "Мосбиржа (данные с задержкой):\n"
                        "- IMOEX 📉: значение — кратко тренд.\n\n"
                        "<b>Вывод:</b> одно предложение с эмодзи."
                    )
                },
                {"role": "user", "content": f"Данные: {market_context}"}
            ],
            temperature=0.3
        )
        ai_text = response.choices[0].message.content.replace("**", "") 
    except:
        ai_text = "📊 <b>Краткий рыночный дайджест</b>\n\nДанные временно обновляются. Попробуйте нажать кнопку ещё раз через минуту! ⏳"

    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Детали в приложении", web_app=types.WebAppInfo(url=BASE_URL))
    
    await bot.send_message(user_id, ai_text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ЛОГИКА МЕНЮ ---

@dp.message(CommandStart())
async def start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Открыть Mini App", web_app=types.WebAppInfo(url=BASE_URL))
    builder.button(text="🔔 Настроить уведомления", callback_data="manage_notifications")
    builder.button(text="🧠 Анализ DeepSeek", callback_data="get_report_now")
    builder.adjust(1)
    await message.answer("<b>Главное меню CryptoPulse ⚡️</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "manage_notifications")
async def list_notifications(callback: types.CallbackQuery):
    uid = callback.from_user.id
    notes = user_notifications.get(uid, [])
    builder = InlineKeyboardBuilder()
    text = "<b>🔔 Ваши настройки:</b>\n\n"
    
    if not notes:
        text += "У вас пока нет активных подписок."
    else:
        types_map = {"morning": "10:00", "evening": "18:00", "both": "10:00 и 18:00"}
        int_map = {1: "Каждый день", 3: "Раз в 3 дня", 7: "Раз в неделю"}
        for i, n in enumerate(notes):
            text += f"{i+1}. ⏰ <b>{types_map[n['type']]}</b> — {int_map[n['interval']]}\n"
            builder.button(text=f"❌ Удалить #{i+1}", callback_data=f"del_{i}")

    builder.button(text="➕ Добавить", callback_data="setup_type")
    builder.button(text="⬅️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "setup_type")
async def setup_type(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="☀️ Утро (10:00)", callback_data="set_t_morning")
    builder.button(text="🌙 Вечер (18:00)", callback_data="set_t_evening")
    builder.button(text="🌗 Утро и Вечер", callback_data="set_t_both")
    builder.adjust(1)
    await callback.message.edit_text("<b>Выберите время:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(NotifyStates.choosing_type)

@dp.callback_query(F.data.startswith("set_t_"))
async def setup_interval(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(time_type=callback.data.replace("set_t_", ""))
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Каждый день", callback_data="set_i_1")
    builder.button(text="🗓 Раз в 3 дня", callback_data="set_i_3")
    builder.button(text="📆 Раз в неделю", callback_data="set_i_7")
    builder.adjust(1)
    await callback.message.edit_text("<b>Как часто присылать?</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
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
        "last_run": datetime.now() - timedelta(days=interval)
    })
    await callback.answer("Настроено!")
    await state.clear()
    await list_notifications(callback)

@dp.callback_query(F.data.startswith("del_"))
async def delete_note(callback: types.CallbackQuery):
    idx = int(callback.data.split("_")[1])
    if callback.from_user.id in user_notifications:
        user_notifications[callback.from_user.id].pop(idx)
    await list_notifications(callback)

async def check_fixed_times():
    now = datetime.now()
    time_str = now.strftime("%H:%M")
    for uid, notes in user_notifications.items():
        for n in notes:
            is_time = (n['type'] == "morning" and time_str == "10:00") or \
                      (n['type'] == "evening" and time_str == "18:00") or \
                      (n['type'] == "both" and time_str in ["10:00", "18:00"])
            if is_time and (now - n['last_run']).total_seconds() > 3600:
                await send_market_report(uid)
                n['last_run'] = now

@dp.callback_query(F.data == "get_report_now")
async def instant_report(callback: types.CallbackQuery):
    await callback.answer("Загрузка...")
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
