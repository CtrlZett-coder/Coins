import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Токен твоего нового бота
TOKEN = "8698978039:AAGJnlo6wdHE8k7I1Jie8XMKE8Di0EmRshw"
# Ссылка на твой будущий GitHub Pages с графиками
BASE_URL = "https://yourusername.github.io/crypto_charts/" 

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: types.Message):
    text = (
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "📈 Добро пожаловать в **CryptoPulse**.\n"
        "Я твой персональный финансовый трекер.\n\n"
        "Ты можешь найти любую криптовалюту, посмотреть интерактивный график её стоимости за разные периоды и узнать пиковые значения.\n\n"
        "Нажимай кнопку ниже, чтобы начать!"
    )
    
    # Кнопка WebApp, открывающая наше окно с графиками
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Открыть CryptoPulse", web_app=types.WebAppInfo(url=BASE_URL))
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
