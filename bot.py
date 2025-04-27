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

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Пам'ять для поточного сеансу вивчення
user_data = {}

# Кнопки
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1. Send Text", callback_data="send_text")],
            [InlineKeyboardButton(text="2. Learn New Words", callback_data="learn_words")],
            [InlineKeyboardButton(text="3. Repeat Words", callback_data="repeat_words")],
        ]
    )

def word_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Вивчив", callback_data="learned"),
                InlineKeyboardButton(text="🤔 Знаю", callback_data="knew"),
                InlineKeyboardButton(text="➡️ Наступне", callback_data="next")
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
        ]
    )

# Обробник команди /start
@dp.message(CommandStart())
async def start_handler(message: Message):
    user_data[message.from_user.id] = {"words": [], "index": 0, "learned": 0, "skipped": 0, "mode": None}
    await message.answer("👋 Вітаю! Оберіть опцію:", reply_markup=main_menu())

# --- Тут ти підключиш свої функції для Send Text / Learn / Repeat ---
# (поки що це базова структура, ти сам напишеш функції завантаження слів)

# Обробник вебхуків від Telegram
async def handle_webhook(request):
    update = await request.json()
    await dp.feed_update(bot, update)
    return web.Response()

# При старті серверу
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

# При виключенні серверу
async def on_shutdown(app):
    await bot.delete_webhook()

# Ініціалізація сервера aiohttp
app = web.Application()
app.router.add_post("/webhook", handle_webhook)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

# Запуск
if __name__ == "__main__":
    web.run_app(app, port=int(os.getenv('PORT', 8080)))