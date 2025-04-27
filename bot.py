import asyncio
import os
import re
import sqlite3
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
from dotenv import load_dotenv
from translator import translate_word, get_transcription

# Завантаження змінних
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Ініціалізація бота
bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# База даних
conn = sqlite3.connect('words.db')
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT UNIQUE,
    translation TEXT,
    transcription TEXT,
    category TEXT
)
''')
conn.commit()

# Клавіатури
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1. Send Text", callback_data="send_text")],
        [InlineKeyboardButton(text="2. Learn New Words", callback_data="learn_words")],
        [InlineKeyboardButton(text="3. Repeat Words", callback_data="repeat_words")]
    ])

def word_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Вивчив", callback_data="learned"),
            InlineKeyboardButton(text="🤔 Знаю", callback_data="knew"),
            InlineKeyboardButton(text="➡️ Наступне", callback_data="next")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])

# Стани
user_sessions = {}

# Команди
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Оберіть опцію:", reply_markup=main_menu())

@dp.callback_query(lambda c: c.data in ["send_text", "learn_words", "repeat_words"])
async def handle_menu(callback: CallbackQuery):
    await callback.answer()
    chat_id = callback.message.chat.id

    if callback.data == "send_text":
        user_sessions[chat_id] = {"state": "waiting_text"}
        await bot.send_message(chat_id, "Надішліть текст англійською:")
    else:
        mode = "new" if callback.data == "learn_words" else "learned"
        cursor.execute("SELECT * FROM words WHERE category=?", (mode,))
        words = cursor.fetchall()

        if not words:
            await bot.send_message(chat_id, "❌ Немає слів для цієї дії.", reply_markup=main_menu())
            return

        user_sessions[chat_id] = {
            "state": "learning",
            "words": words,
            "index": 0,
            "mode": mode,
            "learned": 0,
            "skipped": 0
        }
        await send_word(chat_id)

@dp.message()
async def handle_text(message: Message):
    chat_id = message.chat.id

    if user_sessions.get(chat_id, {}).get("state") != "waiting_text":
        return

    text = message.text.lower()
    words = set(re.findall(r'\b[a-zA-Z]{2,}\b', text))

    cursor.execute("SELECT word FROM words")
    existing = {row[0] for row in cursor.fetchall()}
    new_words = words - existing

    added = 0
    for word in sorted(new_words):
        translation = translate_word(word)
        transcription = get_transcription(word)
        cursor.execute("INSERT INTO words (word, translation, transcription, category) VALUES (?, ?, ?, ?)",
                       (word, translation, transcription, "new"))
        added += 1
    conn.commit()

    await message.answer(f"✅ Додано {added} нових слів", reply_markup=main_menu())
    user_sessions.pop(chat_id, None)

async def send_word(chat_id):
    session = user_sessions.get(chat_id)
    words = session.get("words", [])
    index = session.get("index", 0)

    if index >= len(words):
        await bot.send_message(chat_id, f"✅ Ви пройшли всі слова!\n\n📈 Вивчено: {session['learned']}\n🤔 Пропущено: {session['skipped']}", reply_markup=main_menu())
        user_sessions.pop(chat_id, None)
        return

    word = words[index]
    total = len(words)

    await bot.send_message(chat_id,
        f"<b>({index + 1} з {total})</b>\n\n<b>{word[1]}</b>\nТранскрипція: {word[3]}\nПереклад: {word[2]}",
        reply_markup=word_keyboard()
    )

@dp.callback_query(lambda c: c.data in ["learned", "knew", "next", "back"])
async def handle_learning(callback: CallbackQuery):
    await callback.answer()
    chat_id = callback.message.chat.id
    session = user_sessions.get(chat_id)

    if not session or session.get("state") != "learning":
        return

    if callback.data == "back":
        await bot.send_message(chat_id, "⬅️ Повертаємось у меню.", reply_markup=main_menu())
        user_sessions.pop(chat_id, None)
        return

    index = session["index"]
    words = session["words"]
    word_id = words[index][0]

    if callback.data == "learned":
        cursor.execute("UPDATE words SET category='learned' WHERE id=?", (word_id,))
        session["learned"] += 1
    elif callback.data == "knew":
        cursor.execute("UPDATE words SET category='knew' WHERE id=?", (word_id,))
        session["skipped"] += 1
    conn.commit()

    session["index"] += 1
    await send_word(chat_id)

# Webhook
async def handle_webhook(request):
    update = await request.json()
    await dp.feed_update(bot, update)
    return web.Response()

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()

app = web.Application()
app.router.add_post('/webhook', handle_webhook)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    web.run_app(app, port=int(os.getenv("PORT", 8080)))