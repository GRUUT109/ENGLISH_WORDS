import sqlite3

class Database:
    def __init__(self, db_path='words.db'):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.create_table()

    def create_table(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT UNIQUE,
                translation TEXT,
                transcription TEXT,
                status TEXT DEFAULT 'new'
            )
        ''')
        self.conn.commit()

    def add_word(self, word, translation, transcription):
        try:
            self.cursor.execute(
                "INSERT INTO words (word, translation, transcription) VALUES (?, ?, ?)",
                (word, translation, transcription)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_words_by_status(self, status):
        self.cursor.execute(
            "SELECT id, word, translation, transcription FROM words WHERE status = ?",
            (status,)
        )
        return self.cursor.fetchall()

    def update_status(self, word_id, new_status):
        self.cursor.execute(
            "UPDATE words SET status = ? WHERE id = ?",
            (new_status, word_id)
        )
        self.conn.commit()

    def word_exists(self, word):
        self.cursor.execute(
            "SELECT 1 FROM words WHERE word = ?",
            (word,)
        )
        return self.cursor.fetchone() is not None