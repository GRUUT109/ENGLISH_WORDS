import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram import types
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())

class Form(StatesGroup):
    learning = State()
    repeating = State()

# --- Клавіатури ---
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

# --- Пам'ять слів ---
WORDS_NEW = [{"id": i, "word": f"Word{i}"} for i in range(1, 6)]
WORDS_REPEAT = [{"id": i, "word": f"Repeat{i}"} for i in range(1, 4)]

# --- Команда /start ---
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Оберіть дію:", reply_markup=main_menu())

@dp.callback_query(lambda c: c.data in ["learn_words", "repeat_words"])
async def choose_mode(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data == "learn_words":
        words = WORDS_NEW
        await state.set_state(Form.learning)
    else:
        words = WORDS_REPEAT
        await state.set_state(Form.repeating)
    if not words:
        await callback.message.answer("❌ Немає слів для цієї дії.", reply_markup=main_menu())
        await state.clear()
        return
    await state.update_data(words=words, index=0, learned=0, skipped=0)
    await send_next_word(callback.message, state)

async def send_next_word(message: Message, state: FSMContext):
    data = await state.get_data()
    words = data.get("words", [])
    index = data.get("index", 0)
    learned = data.get("learned", 0)
    skipped = data.get("skipped", 0)

    if index >= len(words):
        await message.answer(
            f"✅ Ви пройшли всі слова!\n\n📈 Вивчено: {learned}\n🤔 Пропущено: {skipped}",
            reply_markup=main_menu()
        )
        await state.clear()
        return

    word = words[index]
    total = len(words)
    await message.answer(
        f"<b>({index + 1} з {total})</b>\n\n<b>{word['word']}</b>",
        reply_markup=word_keyboard()
    )

@dp.callback_query(lambda c: c.data in ["learned", "knew", "next", "back"])
async def word_actions(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    words = data.get("words", [])
    index = data.get("index", 0)
    learned = data.get("learned", 0)
    skipped = data.get("skipped", 0)

    if callback.data == "back":
        await callback.message.answer(
            f"⬅️ Повертаємось у меню.\n\n📈 Вивчено: {learned}\n🤔 Пропущено: {skipped}",
            reply_markup=main_menu()
        )
        await state.clear()
        return

    if index >= len(words):
        await send_next_word(callback.message, state)
        return

    if callback.data == "learned":
        learned += 1
    elif callback.data == "knew":
        skipped += 1

    await state.update_data(index=index + 1, learned=learned, skipped=skipped)
    await send_next_word(callback.message, state)

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