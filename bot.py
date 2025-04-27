import asyncio
import os
import re
from aiohttp import web
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
import eng_to_ipa as ipa

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from database import create_db, get_words_by_category, update_word_category, add_word

# Завантаження змінних середовища
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Пам'ять для користувача
user_data = {}

# --- Стани ---
class Form(StatesGroup):
    waiting_for_text = State()

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

# --- Старт ---
@dp.message(CommandStart())
async def start_handler(message: Message):
    create_db()
    user_data[message.from_user.id] = {"words": [], "index": 0, "learned": 0, "skipped": 0, "mode": None}
    await message.answer("👋 Вітаю! Оберіть дію:", reply_markup=main_menu())

# --- Обробка кнопок меню ---
@dp.callback_query(lambda c: c.data in ["send_text", "learn_words", "repeat_words"])
async def handle_menu(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    if callback.data == "send_text":
        await callback.message.answer("✏️ Надішліть англійський текст для додавання нових слів:")
        await state.set_state(Form.waiting_for_text)
    else:
        mode = "new" if callback.data == "learn_words" else "learned"
        db_words = get_words_by_category(mode)
        words = [{"id": w[0], "word": w[1], "transcription": w[2], "translation": w[3]} for w in db_words]

        if not words:
            await callback.message.answer("❌ Немає слів для цієї дії.", reply_markup=main_menu())
            await callback.answer()
            return

        user_data[user_id] = {"words": words, "index": 0, "learned": 0, "skipped": 0, "mode": mode}
        await send_next_word(callback.message, user_id)

    await callback.answer()

# --- Обробка тексту ---
@dp.message(Form.waiting_for_text)
async def handle_sent_text(message: Message, state: FSMContext):
    text = message.text.lower()

    # Витягуємо унікальні англійські слова
    words_in_text = set(re.findall(r'\b[a-zA-Z]{2,}\b', text))

    if not words_in_text:
        await message.answer("⚠️ Не знайдено слів для додавання.", reply_markup=main_menu())
        await state.clear()
        return

    # Перевіряємо існуючі слова
    existing_words = set()
    for category in ["new", "learned", "knew"]:
        rows = get_words_by_category(category)
        existing_words.update([row[1].lower() for row in rows])

    # Нові слова
    new_words = words_in_text - existing_words

    added = 0
    skipped = len(words_in_text) - len(new_words)

    for word in sorted(new_words):
        try:
            translation = GoogleTranslator(source='en', target='uk').translate(word)
        except Exception:
            translation = "-"
        try:
            transcription = ipa.convert(word)
            transcription = transcription if transcription else "-"
        except Exception:
            transcription = "-"

        add_word(word, transcription, translation, category="new")
        added += 1

    # Відповідь користувачу
    result = f"✅ Додано {added} нових слів."
    if skipped:
        result += f"\n⚠️ Пропущено {skipped} слів (вже існують у базі)."

    await message.answer(result, reply_markup=main_menu())
    await state.clear()

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

# --- Обробка кнопок ---
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