import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from database import create_db, get_words_by_category, update_word_category

# Завантаження змінних середовища
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Пам'ять для користувача
user_data = {}

# --- Клавіатури ---
def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1. Learn New Words", callback_data="learn_words")],
            [InlineKeyboardButton(text="2. Repeat Words", callback_data="repeat_words")]
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

# --- Старт бота ---
@dp.message(CommandStart())
async def start_handler(message: Message):
    create_db()
    user_data[message.from_user.id] = {"words": [], "index": 0, "learned": 0, "skipped": 0, "mode": None}
    await message.answer("👋 Вітаю! Оберіть опцію:", reply_markup=main_menu())

# --- Вибір режиму ---
@dp.callback_query(lambda c: c.data in ["learn_words", "repeat_words"])
async def choose_mode(callback: CallbackQuery):
    user_id = callback.from_user.id

    if callback.data == "learn_words":
        db_words = get_words_by_category("new")
        user_data[user_id] = {
            "words": [{"id": w[0], "word": w[1], "transcription": w[2], "translation": w[3]} for w in db_words],
            "index": 0, "learned": 0, "skipped": 0, "mode": "learn"
        }
    else:
        db_words = get_words_by_category("learned")
        user_data[user_id] = {
            "words": [{"id": w[0], "word": w[1], "transcription": w[2], "translation": w[3]} for w in db_words],
            "index": 0, "learned": 0, "skipped": 0, "mode": "repeat"
        }

    if not user_data[user_id]["words"]:
        await callback.message.answer("❌ Немає слів для цієї дії.", reply_markup=main_menu())
        return

    await send_next_word(callback.message, user_id)

# --- Показ наступного слова ---
async def send_next_word(message: Message, user_id):
    data = user_data.get(user_id)
    words = data["words"]
    index = data["index"]

    if index >= len(words):
        await message.answer(
            f"✅ Ви пройшли всі слова!\n\n📈 Вивчено: {data['learned']}\n🤔 Пропущено: {data['skipped']}",
            reply_markup=main_menu()
        )
        user_data[user_id] = {"words": [], "index": 0, "learned": 0, "skipped": 0, "mode": None}
        return

    word = words[index]
    total = len(words)

    await message.answer(
        f"<b>({index + 1} з {total})</b>\n\n"
        f"📝 <b>{word['word']}</b>\n"
        f"🔊 Транскрипція: {word['transcription'] or '-' }\n"
        f"🇺🇸 Переклад: {word['translation'] or '-' }",
        reply_markup=word_keyboard()
    )

# --- Обробка натискань на кнопки ---
@dp.callback_query(lambda c: c.data in ["learned", "knew", "next", "back"])
async def handle_word_actions(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = user_data.get(user_id)

    if not data or not data["words"]:
        await callback.message.answer("⚠️ Немає активного списку слів.", reply_markup=main_menu())
        return

    if callback.data == "back":
        await callback.message.answer(
            f"⬅️ Повертаємось у меню.\n\n📈 Вивчено: {data['learned']}\n🤔 Пропущено: {data['skipped']}",
            reply_markup=main_menu()
        )
        user_data[user_id] = {"words": [], "index": 0, "learned": 0, "skipped": 0, "mode": None}
        await callback.answer()
        return

    word = data["words"][data["index"]]

    if callback.data == "learned":
        update_word_category(word["id"], "learned")
        data["learned"] += 1
    elif callback.data == "knew":
        update_word_category(word["id"], "knew")
        data["skipped"] += 1

    data["index"] += 1
    await send_next_word(callback.message, user_id)
    await callback.answer()

# --- Webhook ---
async def handle_webhook(request):
    update = await request.json()
    await dp.feed_update(bot, update)
    return web.Response()

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    await bot.delete_webhook()

app = web.Application()
app.router.add_post("/webhook", handle_webhook)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    web.run_app(app, port=int(os.getenv('PORT', 8080)))