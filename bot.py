import asyncio
import re
import sqlite3
import os
import logging
from deep_translator import GoogleTranslator
import eng_to_ipa as ipa
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv


# Завантаження змінних із файлу config.env
load_dotenv("config.env")

# Отримання токена бота
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not found in config.env")

# Логування
logging.basicConfig(level=logging.INFO)

# Ініціалізація бота
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# Створення бази
def create_db():
    conn = sqlite3.connect("words.db")
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT UNIQUE,
        translation TEXT,
        category TEXT,
        transcription TEXT
    )
    ''')
    conn.commit()
    conn.close()

create_db()

# Стани
class Form(StatesGroup):
    waiting_for_text = State()
    learning = State()
    repeating = State()

# Антифлуд
async def safe_send(chat_id, text, reply_markup=None):
    try:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Telegram API error: {e}")

# Клавіатури
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

# База даних операції
def add_word(word, translation, category, transcription):
    conn = sqlite3.connect("words.db")
    c = conn.cursor()
    try:
        c.execute('''
        INSERT INTO words (word, translation, category, transcription)
        VALUES (?, ?, ?, ?)
        ''', (word, translation, category, transcription))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_words_by_category(category):
    conn = sqlite3.connect("words.db")
    c = conn.cursor()
    c.execute('SELECT id, word, translation, transcription FROM words WHERE category = ?', (category,))
    result = [{"id": row[0], "word": row[1], "translation": row[2], "transcription": row[3]} for row in c.fetchall()]
    conn.close()
    return result

def update_word_category(word_id, new_category):
    conn = sqlite3.connect("words.db")
    c = conn.cursor()
    c.execute('UPDATE words SET category = ? WHERE id = ?', (new_category, word_id))
    conn.commit()
    conn.close()

# Старт
@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    await safe_send(message.chat.id, "Оберіть опцію:", reply_markup=main_menu())

# Меню
@dp.callback_query(lambda c: c.data in ["send_text", "learn_words", "repeat_words"])
async def handle_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data == "send_text":
        await safe_send(callback.message.chat.id, "Надішліть текст англійською:")
        await state.set_state(Form.waiting_for_text)
    else:
        mode = "new" if callback.data == "learn_words" else "learned"
        words = get_words_by_category(mode)
        if not words:
            await safe_send(callback.message.chat.id, "❌ Немає слів для цієї дії.", reply_markup=main_menu())
            await state.clear()
            return
        await state.update_data(words=words, index=0, mode=mode, learned=0, skipped=0)
        await state.set_state(Form.learning if mode == "new" else Form.repeating)
        await send_next_word(callback.message, state)

# Обробка тексту
@dp.message(Form.waiting_for_text)
async def handle_text(message: Message, state: FSMContext):
    text = message.text.lower()
    words = set(re.findall(r'\b[a-zA-Z]{2,}\b', text))

    existing_words = get_words_by_category("new") + get_words_by_category("learned") + get_words_by_category("knew")
    existing = {w["word"] for w in existing_words}

    new_words = words - existing
    added = 0

    for word in sorted(new_words):
        try:
            translation = GoogleTranslator(source='en', target='uk').translate(word)
        except:
            translation = "-"
        transcription = ipa.convert(word) or "-"
        if add_word(word, translation, "new", transcription):
            added += 1

    await safe_send(message.chat.id, f"✅ Додано {added} нових слів.", reply_markup=main_menu())
    await state.clear()

# Відправити наступне слово
async def send_next_word(message, state: FSMContext):
    data = await state.get_data()
    words = data.get("words", [])
    index = data.get("index", 0)
    mode = data.get("mode", "new")

    if index >= len(words):
        learned = data.get("learned", 0)
        skipped = data.get("skipped", 0)
        await safe_send(message.chat.id, f"✅ Всі слова пройдено!\n\n📈 Вивчено: {learned}\n🤔 Пропущено: {skipped}", reply_markup=main_menu())
        await state.clear()
        return

    word = words[index]
    total = len(words)
    await safe_send(
        message.chat.id,
        f"<b>({index + 1} з {total})</b>\n\n<b>{word['word']}</b>\nТранскрипція: {word['transcription']}\nПереклад: {word['translation']}",
        reply_markup=word_keyboard()
    )

# Кнопки навчання
@dp.callback_query(lambda c: c.data in ["learned", "knew", "next", "back"])
async def handle_learning(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    words = data.get("words", [])
    index = data.get("index", 0)
    mode = data.get("mode", "new")
    learned = data.get("learned", 0)
    skipped = data.get("skipped", 0)

    if callback.data == "back":
        await safe_send(callback.message.chat.id, f"⬅️ Повертаємось у меню.\n\n📈 Вивчено: {learned}\n🤔 Пропущено: {skipped}", reply_markup=main_menu())
        await state.clear()
        return

    if index >= len(words):
        await send_next_word(callback.message, state)
        return

    word_id = words[index]["id"]

    if callback.data == "learned":
        update_word_category(word_id, "learned")
        learned += 1
    elif callback.data == "knew":
        update_word_category(word_id, "knew")
        skipped += 1

    # Оновити слова після зміни категорії
    updated_words = get_words_by_category(mode)
    await state.update_data(words=updated_words, index=index + 1, mode=mode, learned=learned, skipped=skipped)
    await send_next_word(callback.message, state)

# Список слів
@dp.message(Command("list"))
async def list_words(message: Message, state: FSMContext):
    data = await state.get_data()
    mode = data.get("mode", "new")
    words = get_words_by_category(mode)
    if not words:
        await safe_send(message.chat.id, "❌ Список порожній.")
        return

    text = "\n".join([f"{i+1}. {w['word']} – {w['translation']}" for i, w in enumerate(words)])
    await safe_send(message.chat.id, f"🔹 Список слів ({mode}):\n\n{text}")

# Запуск
async def main():
    logging.info("✅ Бот запущено!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())