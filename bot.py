import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message
bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher()
from aiohttp import web
from dotenv import load_dotenv

# Завантаження змінних із config.env
load_dotenv()

# Ваш токен і вебхук URL
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # Приклад: https://your-app-name.up.railway.app
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Ініціалізація бота
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Обробник команди /start
@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer("Привіт! Бот працює через webhook 🚀")

# Функція обробки запитів від Telegram
async def handle_webhook(request):
    update = await request.json()
    await dp.feed_update(bot, update)
    return web.Response()

# Дії при старті
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

# Дії при зупинці
async def on_shutdown(app):
    await bot.delete_webhook()

# Налаштування сервера aiohttp
app = web.Application()
app.router.add_post(WEBHOOK_PATH, handle_webhook)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

# Запуск додатку
if __name__ == "__main__":
    web.run_app(app, port=int(os.getenv('PORT', 8080)))