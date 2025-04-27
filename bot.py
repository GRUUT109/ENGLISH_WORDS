import asyncio
import os
import re
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv
from database import Database
from translator import translate_word, get_transcription
from aiohttp import web

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())
db = Database()

# --- Стани ---
class Form(StatesGroup):
    waiting_for_text = State()
    learning = State()
    repeating = State()

# --- Клавіатури ---
def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1. Send Text", callback_data="send_text")],
            [InlineKeyboardButton(text="2. Learn New Words", callback_data="learn_words")],
            [InlineKeyboardButton(text="3. Repeat Words", callback_data="repeat_words")]
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

# --- Команди ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Оберіть опцію:", reply_markup=main_menu())

@dp.callback_query(F.data.in_({"send_text", "learn_words", "repeat_words"}))
async def handle_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data == "send_text":
        await callback.message.answer("Надішліть текст англійською:")
        await state.set_state(Form.waiting_for_text)
    else:
        category = "new" if callback.data == "learn_words" else "learned"
        words = db.get_words_by_category(category)
        if not words:
            await callback.message.answer("❌ Немає слів для цієї дії.", reply_markup=main_menu())
            await state.clear()
            return
        await state.update_data(words=words, index=0, mode=category)
        await state.set_state(Form.learning if category == "new" else Form.repeating)
        await send_word(callback.message, state)

@dp.message(Form.waiting_for_text)
async def handle_text(message: Message, state: FSMContext):
    text = message.text.lower()
    words = set(re.findall(r'\b[a-zA-Z]{2,}\b', text))
    added = 0

    for word in words:
        if not db.word_exists(word):
            translation = translate_word(word)
            transcription = get_transcription(word)
            db.add_word(word, translation, "new", transcription)
            added += 1

    await message.answer(f"✅ Додано {added} нових слів", reply_markup=main_menu())
    await state.clear()

async def send_word(message, state: FSMContext):
    data = await state.get_data()
    words = data.get("words", [])
    index = data.get("index", 0)

    if index >= len(words):
        await message.answer("✅ Ви пройшли всі слова.", reply_markup=main_menu())
        await state.clear()
        return

    word = words[index]
    await message.answer(
        f"<b>({index + 1} з {len(words)})</b>\n\n<b>{word['word']}</b>\nТранскрипція: {word['transcription']}\nПереклад: {word['translation']}",
        reply_markup=word_keyboard()
    )

@dp.callback_query(F.data.in_({"learned", "knew", "next", "back"}))
async def handle_learning(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    words = data.get("words", [])
    index = data.get("index", 0)
    mode = data.get("mode", "new")

    if callback.data == "back":
        await callback.message.answer("⬅️ Повертаємось у меню.", reply_markup=main_menu())
        await state.clear()
        return

    if index >= len(words):
        await send_word(callback.message, state)
        return

    word_id = words[index]["id"]

    if callback.data == "learned":
        db.update_word_category(word_id, "learned")
    elif callback.data == "knew":
        db.update_word_category(word_id, "knew")

    await state.update_data(index=index + 1)
    await send_word(callback.message, state)

# --- WEBHOOK ---
async def handle_webhook(request):
    data = await request.json()
    await dp.feed_update(bot, data)
    return web.Response()

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    await bot.delete_webhook()

app = web.Application()
app.router.add_post("/", handle_webhook)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    web.run_app(app, port=int(os.getenv('PORT', 8080)))