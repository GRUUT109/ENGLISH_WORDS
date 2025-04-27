import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from database import Database
from translator import translate_word, get_transcription

# Завантаження змінних
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
db = Database()
dp = Dispatcher()
router = Router()
dp.include_router(router)

user_states = {}

# --- Клавіатури ---
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton(text="1. Send Text", callback_data="send_text")],
        [InlineKeyboardButton(text="2. Learn New Words", callback_data="learn_words")],
        [InlineKeyboardButton(text="3. Repeat Words", callback_data="repeat_words")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def word_keyboard():
    keyboard = [
        [
            InlineKeyboardButton(text="✅ Вивчив", callback_data="learned"),
            InlineKeyboardButton(text="🤔 Знаю", callback_data="know"),
            InlineKeyboardButton(text="➡️ Наступне", callback_data="next_word")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# --- Обробник /start ---
@router.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer("Оберіть опцію:", reply_markup=main_menu_keyboard())

# --- Обробка Callback кнопок ---
@router.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    action = callback.data
    user_id = callback.from_user.id

    if action == "send_text":
        user_states[user_id] = {"mode": "waiting_text"}
        await callback.message.answer("Надішліть текст англійською:")

    elif action == "learn_words":
        words = db.get_words_by_status('new')
        if not words:
            await callback.message.answer("❌ Немає нових слів для вивчення.", reply_markup=main_menu_keyboard())
            return
        user_states[user_id] = {"mode": "learn", "words": words, "index": 0}
        await send_next_word(callback.message, user_id)

    elif action == "repeat_words":
        words = db.get_words_by_status('know')
        if not words:
            await callback.message.answer("❌ Немає слів для повторення.", reply_markup=main_menu_keyboard())
            return
        user_states[user_id] = {"mode": "repeat", "words": words, "index": 0}
        await send_next_word(callback.message, user_id)

    elif action in ("learned", "know", "next_word"):
        if user_id not in user_states:
            await callback.message.answer("⚠️ Спочатку оберіть опцію з меню.")
            return
        state = user_states[user_id]
        words = state["words"]
        index = state["index"]

        if index >= len(words):
            await callback.message.answer("✅ Всі слова пройдено!", reply_markup=main_menu_keyboard())
            user_states.pop(user_id, None)
            return

        word_id = words[index][0]

        if action == "learned":
            db.update_status(word_id, "learned")
        elif action == "know":
            db.update_status(word_id, "know")

        state["index"] += 1

        if state["index"] >= len(words):
            await callback.message.answer("✅ Ви пройшли всі слова!", reply_markup=main_menu_keyboard())
            user_states.pop(user_id, None)
        else:
            await send_next_word(callback.message, user_id)

    elif action == "back_to_menu":
        user_states.pop(user_id, None)
        await callback.message.answer("⬅️ Повернення у головне меню.", reply_markup=main_menu_keyboard())

    await callback.answer()

# --- Обробка тексту ---
@router.message()
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_states or user_states[user_id]["mode"] != "waiting_text":
        await message.answer("Будь ласка, скористайтесь кнопкою 'Send Text' у меню.")
        return

    text = message.text.lower()
    words = set(word.strip('.,!?') for word in text.split() if word.isalpha())

    added_count = 0
    for word in words:
        if not db.word_exists(word):
            translation = translate_word(word)
            transcription = get_transcription(word)
            db.add_word(word, translation, transcription)
            added_count += 1

    await message.answer(f"✅ Додано {added_count} нових слів.", reply_markup=main_menu_keyboard())
    user_states.pop(user_id, None)

# --- Відправка наступного слова ---
async def send_next_word(message: types.Message, user_id: int):
    state = user_states[user_id]
    words = state["words"]
    index = state["index"]

    word_id, word, translation, transcription = words[index]
    total = len(words)

    text = f"<b>{index+1}/{total}</b>\n\n<b>{word}</b>\n[{transcription}]\nПереклад: {translation}"
    await message.answer(text, reply_markup=word_keyboard())

# --- Webhook ---
async def handle_webhook(request):
    data = await request.json()
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return web.Response()

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()

app = web.Application()
app.router.add_post("/webhook", handle_webhook)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    web.run_app(app, port=int(os.getenv("PORT", 8080)))