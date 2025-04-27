import os
import re
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.utils.executor import start_webhook

from database import Database
import translator

# ----------------------------
# 1) Завантаження налаштувань
# ----------------------------
# локально читаємо config.env; у Railway ці змінні будуть у середовищі
load_dotenv("config.env")

BOT_TOKEN    = os.getenv("BOT_TOKEN")
DB_PATH      = os.getenv("DB_PATH", "./words.db")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")      # https://<your-app>.up.railway.app
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_URL  = os.getenv("WEBHOOK_URL", f"{WEBHOOK_HOST}{WEBHOOK_PATH}")
PORT         = int(os.getenv("PORT", "8443"))

if not BOT_TOKEN or not WEBHOOK_HOST:
    raise RuntimeError("Потрібно задати BOT_TOKEN і WEBHOOK_HOST у config.env або середовищі")

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(bot)
db  = Database(DB_PATH)

# Стан користувачів: режим ("waiting_text", "learn", "repeat"), список слів, індекс
user_states: dict[int, dict] = {}

# ----------------------------
# 2) Клавіатури
# ----------------------------
def main_menu_kb() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton("Надіслати текст",    callback_data="send_text")],
        [types.InlineKeyboardButton("Learn new words",    callback_data="learn")],
        [types.InlineKeyboardButton("Repeat learned words", callback_data="repeat")],
    ])

def word_cycle_kb() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton("Знаю",     callback_data="know"),
            types.InlineKeyboardButton("Вивчив",   callback_data="learned"),
            types.InlineKeyboardButton("Next",     callback_data="next"),
        ],
        [types.InlineKeyboardButton("Назад у меню", callback_data="back")],
    ])

# ----------------------------
# 3) Обробники
# ----------------------------
@dp.message(CommandStart())
async def on_start(m: types.Message):
    await m.answer("Оберіть дію:", reply_markup=main_menu_kb())

@dp.callback_query()
async def on_callback(c: types.CallbackQuery):
    await c.answer()  # підтвердження натискання кнопки
    uid = c.from_user.id
    action = c.data
    state = user_states.get(uid, {})

    # ---- Надіслати текст ----
    if action == "send_text":
        user_states[uid] = {"mode": "waiting_text"}
        await c.message.answer("Надішліть, будь ласка, текст англійською:")
        return

    # ---- Learn new words ----
    if action == "learn":
        recs = db.get_words_by_status("new")
        if not recs:
            await c.message.answer("Нових слів немає.", reply_markup=main_menu_kb())
            return
        user_states[uid] = {"mode": "learn", "words": recs, "index": 0}
        _id, w, tr, ts = recs[0]
        await c.message.answer(f"{w}\n{tr}\n/{ts}/", reply_markup=word_cycle_kb())
        return

    # ---- Repeat learned words ----
    if action == "repeat":
        recs = db.get_words_by_status("learned")
        if not recs:
            await c.message.answer("Вивчених слів немає.", reply_markup=main_menu_kb())
            return
        user_states[uid] = {"mode": "repeat", "words": recs, "index": 0}
        _id, w, tr, ts = recs[0]
        await c.message.answer(f"{w}\n{tr}\n/{ts}/", reply_markup=word_cycle_kb())
        return

    # ---- Назад у меню ----
    if action == "back":
        user_states.pop(uid, None)
        await c.message.answer("Повернулися в меню.", reply_markup=main_menu_kb())
        return

    # ---- Next у циклі learn/repeat ----
    if action == "next" and state.get("mode") in ("learn", "repeat"):
        idx   = state["index"] + 1
        words = state["words"]
        if idx < len(words):
            user_states[uid]["index"] = idx
            _id, w, tr, ts = words[idx]
            await c.message.answer(f"{w}\n{tr}\n/{ts}/", reply_markup=word_cycle_kb())
        else:
            await c.message.answer("Кінець списку.", reply_markup=main_menu_kb())
            user_states.pop(uid, None)
        return

    # ---- Знаю / Вивчив ----
    if action in ("know", "learned") and state.get("mode") in ("learn", "repeat"):
        idx   = state["index"]
        words = state["words"]
        word_id = words[idx][0]
        # обидві кнопки переводять слово в статус learned
        db.update_status(word_id, "learned")
        # йдемо далі
        idx += 1
        if idx < len(words):
            user_states[uid]["index"] = idx
            _id, w, tr, ts = words[idx]
            await c.message.answer(f"{w}\n{tr}\n/{ts}/", reply_markup=word_cycle_kb())
        else:
            await c.message.answer("Ви завершили цей список.", reply_markup=main_menu_kb())
            user_states.pop(uid, None)
        return

@dp.message()
async def on_message(m: types.Message):
    uid = m.from_user.id
    state = user_states.get(uid)
    if not state or state.get("mode") != "waiting_text":
        return  # ігноруємо інші повідомлення

    text = m.text or ""
    # витягуємо лише слова, знижуємо регістр
    words = re.findall(r"[A-Za-z']+", text)
    uniq  = set(w.lower() for w in words)
    added = 0

    for w in uniq:
        if not db.word_exists(w):
            tr = translator.translate_word(w)
            ts = translator.get_transcription(w)  # локальна IPA
            if db.add_word(w, tr, ts):
                added += 1

    await m.answer(f"Додано нових слів: {added}", reply_markup=main_menu_kb())
    user_states.pop(uid, None)

# ----------------------------
# 4) Запуск через Webhook
# ----------------------------
async def on_startup(dp):
    await bot.delete_webhook()
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_webhook(
        dispatcher   = dp,
        webhook_path = WEBHOOK_PATH,
        on_startup   = on_startup,
        on_shutdown  = on_shutdown,
        skip_updates = True,
        host         = "0.0.0.0",
        port         = PORT,
    )