import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from dotenv import load_dotenv
from database import Database
from translator import translate_word, get_transcription

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()

user_states = {}

def main_menu():
    keyboard = [
        [types.InlineKeyboardButton(text="1. Send Text", callback_data="send_text")],
        [types.InlineKeyboardButton(text="2. Learn New Words", callback_data="learn_words")],
        [types.InlineKeyboardButton(text="3. Repeat Words", callback_data="repeat_words")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

def learning_menu():
    keyboard = [
        [
            types.InlineKeyboardButton(text="✅ Вивчив", callback_data="learned"),
            types.InlineKeyboardButton(text="🤔 Знаю", callback_data="know"),
            types.InlineKeyboardButton(text="➡️ Наступне", callback_data="next_word")
        ],
        [types.InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_menu")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer("Оберіть опцію:", reply_markup=main_menu())

@dp.callback_query()
async def menu_handler(callback_query):
    action = callback_query.data
    user_id = callback_query.from_user.id

    if action == "send_text":
        user_states[user_id] = {"mode": "waiting_text"}
        await callback_query.message.answer("Надішліть текст англійською:")

    elif action == "learn_words":
        words = db.get_words_by_status('new')
        if not words:
            await callback_query.message.answer("Немає нових слів для вивчення.")
            return
        user_states[user_id] = {"mode": "learn", "words": words, "index": 0}
        await send_word(callback_query.message, user_id)

    elif action == "repeat_words":
        words = db.get_words_by_status('learned')
        if not words:
            await callback_query.message.answer("Немає слів для повторення.")
            return
        user_states[user_id] = {"mode": "repeat", "words": words, "index": 0}
        await send_word(callback_query.message, user_id)

    elif action in ("learned", "know", "next_word"):
        if user_id not in user_states:
            await callback_query.message.answer("Будь ласка, оберіть опцію спочатку.")
            return

        state = user_states[user_id]
        words = state["words"]
        index = state["index"]

        if action == "learned":
            db.update_status(words[index][0], 'learned')
        elif action == "know":
            db.update_status(words[index][0], 'known')

        state["index"] += 1

        if state["index"] >= len(words):
            await callback_query.message.answer("Слова закінчились ✅", reply_markup=main_menu())
            user_states.pop(user_id)
        else:
            await send_word(callback_query.message, user_id)

    elif action == "back_to_menu":
        user_states.pop(user_id, None)
        await callback_query.message.answer("Оберіть опцію:", reply_markup=main_menu())

@dp.message()
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_states or user_states[user_id]["mode"] != "waiting_text":
        await message.answer("Будь ласка, оберіть опцію через меню.")
        return

    text = message.text
    words = set(word.lower() for word in text.split())

    added_count = 0
    for word in words:
        if not db.word_exists(word):
            translation = translate_word(word)
            transcription = get_transcription(word)
            db.add_word(word, translation, transcription)
            added_count += 1

    await message.answer(f"Додано {added_count} нових слів ✅", reply_markup=main_menu())
    user_states.pop(user_id)

async def send_word(message, user_id):
    state = user_states[user_id]
    words = state["words"]
    index = state["index"]

    word_id, word, translation, transcription = words[index]
    total = len(words)
    text = f"<b>{index+1}/{total}</b>\n\n{word}\n{transcription}\nПереклад: {translation}"
    await message.answer(text, reply_markup=learning_menu())

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