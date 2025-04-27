import os
import re
import logging

from dotenv import load_dotenv
from aiohttp import web

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiogram.fsm.storage.memory import MemoryStorage

from database import Database
import translator

# 1) Завантажуємо налаштування
load_dotenv("config.env")
BOT_TOKEN    = os.getenv("BOT_TOKEN")
DB_PATH      = os.getenv("DB_PATH", "./words.db")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")               # тільки домен
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_URL  = os.getenv("WEBHOOK_URL", f"{WEBHOOK_HOST}{WEBHOOK_PATH}")
PORT         = int(os.getenv("PORT", "8443"))

if not BOT_TOKEN or not WEBHOOK_HOST:
    raise RuntimeError("У config.env мають бути BOT_TOKEN і WEBHOOK_HOST")

# 2) Ініціалізація
logging.basicConfig(level=logging.INFO)
bot     = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp      = Dispatcher(storage=storage)
db      = Database(DB_PATH)

# для відслідковування контексту кожного юзера
user_states: dict[int, dict] = {}

# 3) Клавіатури
def main_menu_kb() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Надіслати текст",      callback_data="send_text")],
        [types.InlineKeyboardButton(text="Learn new words",      callback_data="learn")],
        [types.InlineKeyboardButton(text="Repeat learned words", callback_data="repeat")],
    ])

def word_cycle_kb() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="Знаю",   callback_data="know"),
            types.InlineKeyboardButton(text="Вивчив", callback_data="learned"),
            types.InlineKeyboardButton(text="Next",   callback_data="next"),
        ],
        [types.InlineKeyboardButton(text="Назад у меню", callback_data="back")],
    ])

# 4) /start
@dp.message(CommandStart())
async def on_start(message: types.Message):
    await message.answer("Оберіть дію:", reply_markup=main_menu_kb())

# 5) Обробка кнопок
@dp.callback_query()
async def on_callback(callback: types.CallbackQuery):
    await callback.answer()
    uid    = callback.from_user.id
    action = callback.data
    state  = user_states.get(uid, {})

    if action == "send_text":
        user_states[uid] = {"mode": "waiting_text"}
        await callback.message.answer("Надішліть текст англійською:")
        return

    if action == "learn":
        recs = db.get_words_by_status("new")
        if not recs:
            await callback.message.answer("Нових слів немає.", reply_markup=main_menu_kb())
            return
        user_states[uid] = {"mode": "learn", "words": recs, "index": 0}
        _id, w, tr, ts = recs[0]
        await callback.message.answer(f"{w}\n{tr}\n/{ts}/", reply_markup=word_cycle_kb())
        return

    if action == "repeat":
        recs = db.get_words_by_status("learned")
        if not recs:
            await callback.message.answer("Вивчених слів немає.", reply_markup=main_menu_kb())
            return
        user_states[uid] = {"mode": "repeat", "words": recs, "index": 0}
        _id, w, tr, ts = recs[0]
        await callback.message.answer(f"{w}\n{tr}\n/{ts}/", reply_markup=word_cycle_kb())
        return

    if action == "back":
        user_states.pop(uid, None)
        await callback.message.answer("Повернулися в меню.", reply_markup=main_menu_kb())
        return

    if action == "next" and state.get("mode") in ("learn", "repeat"):
        idx   = state["index"] + 1
        words = state["words"]
        if idx < len(words):
            user_states[uid]["index"] = idx
            _id, w, tr, ts = words[idx]
            await callback.message.answer(f"{w}\n{tr}\n/{ts}/", reply_markup=word_cycle_kb())
        else:
            await callback.message.answer("Кінець списку.", reply_markup=main_menu_kb())
            user_states.pop(uid, None)
        return

    if action in ("know", "learned") and state.get("mode") in ("learn", "repeat"):
        idx   = state["index"]
        words = state["words"]
        word_id = words[idx][0]
        db.update_status(word_id, "learned")
        idx += 1
        if idx < len(words):
            user_states[uid]["index"] = idx
            _id, w, tr, ts = words[idx]
            await callback.message.answer(f"{w}\n{tr}\n/{ts}/", reply_markup=word_cycle_kb())
        else:
            await callback.message.answer("Список завершено.", reply_markup=main_menu_kb())
            user_states.pop(uid, None)
        return

# 6) Обробка тексту
@dp.message()
async def on_message(message: types.Message):
    uid   = message.from_user.id
    state = user_states.get(uid)
    if not state or state.get("mode") != "waiting_text":
        return

    text  = message.text or ""
    words = re.findall(r"[A-Za-z']+", text)
    uniq  = set(w.lower() for w in words)
    added = 0

    for w in uniq:
        if not db.word_exists(w):
            tr = translator.translate_word(w)
            ts = translator.get_transcription(w)
            if db.add_word(w, tr, ts):
                added += 1

    await message.answer(f"Додано нових слів: {added}", reply_markup=main_menu_kb())
    user_states.pop(uid, None)

# ——————— Debug-хендлери ———————
@dp.message(Command("debug_add"))
async def cmd_debug_add(message: types.Message):
    uid   = message.from_user.id
    state = user_states.get(uid)
    await message.answer(f"DEBUG: user_states[{uid}] = {state!r}")

    new_words = db.get_words_by_status("new")
    await message.answer(f"DEBUG: в БД words NEW = {len(new_words)}")

@dp.message(Command("debug_list"))
async def cmd_debug_list(message: types.Message):
    new_words = db.get_words_by_status("new")
    if not new_words:
        await message.answer("DEBUG: нових слів у БД немає.")
    else:
        lines = [f"{wid}: {w}" for wid, w, tr, ts in new_words]
        await message.answer("DEBUG: ось нові слова:\n" + "\n".join(lines))

# 7) Webhook через aiohttp
async def _on_startup(app: web.Application):
    await bot.delete_webhook()
    await bot.set_webhook(WEBHOOK_URL)

async def _on_shutdown(app: web.Application):
    await bot.delete_webhook()

if __name__ == "__main__":
    app = web.Application()
    handler = SimpleRequestHandler(dp, bot=bot, handle_in_background=True)
    handler.register(app, path=WEBHOOK_PATH)

    app.on_startup.append(_on_startup)
    app.on_shutdown.append(_on_shutdown)

    web.run_app(app, host="0.0.0.0", port=PORT)