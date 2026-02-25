import sqlite3
import logging
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_path = DATABASE_PATH

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS posted_items (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    url TEXT,
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id INTEGER PRIMARY KEY,
                    title TEXT,
                    chat_type TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active INTEGER DEFAULT 1
                )
            """)
            conn.commit()
        logger.info("Database initialized")

    def is_posted(self, item_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT id FROM posted_items WHERE id = ?", (item_id,)).fetchone()
            return row is not None

    def mark_posted(self, item_id: str, title: str = "", url: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO posted_items (id, title, url) VALUES (?, ?, ?)",
                (item_id, title, url)
            )
            conn.commit()

    def add_chat(self, chat_id: int, title: str, chat_type: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO chats (chat_id, title, chat_type, active) VALUES (?, ?, ?, 1)",
                (chat_id, title, chat_type)
            )
            conn.commit()

    def remove_chat(self, chat_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
            conn.commit()

    def get_all_chats(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM chats WHERE active = 1").fetchall()
            return [dict(r) for r in rows]

    def get_post_count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM posted_items").fetchone()
            return row[0] if row else 0
