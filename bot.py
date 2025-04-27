import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

# Завантажуємо змінні середовища
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Обробка /start
@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer("Привіт! Бот працює через webhook 🚀")

# Обробник вебхуку
async def handle_webhook(request):
    update = await request.json()
    await dp.feed_update(bot, update)
    return web.Response()

# Старт
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

# Завершення
async def on_shutdown(app):
    await bot.delete_webhook()

# Створення сервера
app = web.Application()
app.router.add_post("/webhook", handle_webhook)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    web.run_app(app, port=int(os.getenv('PORT', 8080)))