import sqlite3
import json
import os

DB_PATH = os.environ.get("DB_PATH", "bot_data.db")


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS targets (
                user_id     INTEGER,
                chat_id     INTEGER,
                title       TEXT,
                PRIMARY KEY (user_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS active_targets (
                user_id     INTEGER PRIMARY KEY,
                chat_id     INTEGER
            );

            CREATE TABLE IF NOT EXISTS queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                position    INTEGER,
                item_json   TEXT
            );
        """)
        self.conn.commit()

    # ── Targets ──────────────────────────────────────────────────────────────

    def save_target(self, user_id: int, chat_id: int, title: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO targets (user_id, chat_id, title) VALUES (?, ?, ?)",
            (user_id, chat_id, title)
        )
        self.conn.commit()

    def list_saved_targets(self, user_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT chat_id, title FROM targets WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def set_active_target(self, user_id: int, chat_id: int):
        self.conn.execute(
            "INSERT OR REPLACE INTO active_targets (user_id, chat_id) VALUES (?, ?)",
            (user_id, chat_id)
        )
        self.conn.commit()

    def get_target(self, user_id: int) -> dict | None:
        row = self.conn.execute(
            """
            SELECT t.chat_id, t.title FROM active_targets a
            JOIN targets t ON a.user_id = t.user_id AND a.chat_id = t.chat_id
            WHERE a.user_id = ?
            """,
            (user_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── Queue ─────────────────────────────────────────────────────────────────

    def add_to_queue(self, user_id: int, item: dict):
        max_pos = self.conn.execute(
            "SELECT COALESCE(MAX(position), 0) FROM queue WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        self.conn.execute(
            "INSERT INTO queue (user_id, position, item_json) VALUES (?, ?, ?)",
            (user_id, max_pos + 1, json.dumps(item))
        )
        self.conn.commit()

    def get_queue(self, user_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT item_json FROM queue WHERE user_id = ? ORDER BY position", (user_id,)
        ).fetchall()
        return [json.loads(r["item_json"]) for r in rows]

    def queue_count(self, user_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM queue WHERE user_id = ?", (user_id,)
        ).fetchone()[0]

    def clear_queue(self, user_id: int):
        self.conn.execute("DELETE FROM queue WHERE user_id = ?", (user_id,))
        self.conn.commit()
