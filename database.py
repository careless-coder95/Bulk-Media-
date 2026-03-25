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
                user_id  INTEGER,
                chat_id  INTEGER,
                title    TEXT,
                PRIMARY KEY (user_id, chat_id)
            );
            CREATE TABLE IF NOT EXISTS active_targets (
                user_id  INTEGER PRIMARY KEY,
                chat_id  INTEGER
            );
            CREATE TABLE IF NOT EXISTS album (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER,
                position  INTEGER,
                item_json TEXT
            );
            CREATE TABLE IF NOT EXISTS repeat_settings (
                user_id  INTEGER PRIMARY KEY,
                repeat   INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS sudo_users (
                user_id  INTEGER PRIMARY KEY,
                name     TEXT
            );
        """)
        self.conn.commit()

    # ── Targets ──────────────────────────────────────────────────────────────

    def save_target(self, user_id, chat_id, title):
        self.conn.execute(
            "INSERT OR REPLACE INTO targets (user_id, chat_id, title) VALUES (?, ?, ?)",
            (user_id, chat_id, title)
        )
        self.conn.commit()

    def list_saved_targets(self, user_id):
        rows = self.conn.execute(
            "SELECT chat_id, title FROM targets WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def set_active_target(self, user_id, chat_id):
        self.conn.execute(
            "INSERT OR REPLACE INTO active_targets (user_id, chat_id) VALUES (?, ?)",
            (user_id, chat_id)
        )
        self.conn.commit()

    def get_target(self, user_id):
        row = self.conn.execute(
            """SELECT t.chat_id, t.title FROM active_targets a
               JOIN targets t ON a.user_id = t.user_id AND a.chat_id = t.chat_id
               WHERE a.user_id = ?""",
            (user_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── Album ─────────────────────────────────────────────────────────────────

    def add_to_album(self, user_id, item):
        max_pos = self.conn.execute(
            "SELECT COALESCE(MAX(position), 0) FROM album WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        self.conn.execute(
            "INSERT INTO album (user_id, position, item_json) VALUES (?, ?, ?)",
            (user_id, max_pos + 1, json.dumps(item))
        )
        self.conn.commit()

    def get_album(self, user_id):
        rows = self.conn.execute(
            "SELECT item_json FROM album WHERE user_id = ? ORDER BY position", (user_id,)
        ).fetchall()
        return [json.loads(r["item_json"]) for r in rows]

    def clear_album(self, user_id):
        self.conn.execute("DELETE FROM album WHERE user_id = ?", (user_id,))
        self.conn.commit()

    # ── Repeat ────────────────────────────────────────────────────────────────

    def set_repeat(self, user_id, repeat):
        self.conn.execute(
            "INSERT OR REPLACE INTO repeat_settings (user_id, repeat) VALUES (?, ?)",
            (user_id, repeat)
        )
        self.conn.commit()

    def get_repeat(self, user_id):
        row = self.conn.execute(
            "SELECT repeat FROM repeat_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["repeat"] if row else 1

    # ── Sudo ──────────────────────────────────────────────────────────────────

    def add_sudo(self, user_id, name=None):
        self.conn.execute(
            "INSERT OR REPLACE INTO sudo_users (user_id, name) VALUES (?, ?)",
            (user_id, name)
        )
        self.conn.commit()

    def remove_sudo(self, user_id):
        self.conn.execute("DELETE FROM sudo_users WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def is_sudo(self, user_id):
        row = self.conn.execute(
            "SELECT 1 FROM sudo_users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row is not None

    def list_sudo(self):
        rows = self.conn.execute(
            "SELECT user_id, name FROM sudo_users ORDER BY rowid"
        ).fetchall()
        return [dict(r) for r in rows]
