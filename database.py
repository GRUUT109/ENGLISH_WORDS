import sqlite3

DB_PATH = "words.db"

def create_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE,
            transcription TEXT,
            translation TEXT,
            category TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_word(word, transcription, translation, category="new"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR IGNORE INTO words (word, transcription, translation, category)
        VALUES (?, ?, ?, ?)
    ''', (word, transcription, translation, category))
    conn.commit()
    conn.close()

def get_words_by_category(category):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, word, transcription, translation FROM words WHERE category=?
    ''', (category,))
    result = c.fetchall()
    conn.close()
    return result

def update_word_category(word_id, new_category):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        UPDATE words SET category=? WHERE id=?
    ''', (new_category, word_id))
    conn.commit()
    conn.close()