import sqlite3
from contextlib import contextmanager
from datetime import datetime
from config import DB_FILE


@contextmanager
def _conn():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id     INTEGER PRIMARY KEY,
                first_seen  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active   INTEGER DEFAULT 1,
                promo_shown INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS exports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER REFERENCES users(chat_id),
                file_path   TEXT,
                exported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_exports_exported_at ON exports(exported_at);
            PRAGMA journal_mode=WAL;
        """)


# ── Users ──────────────────────────────────────────────────────────────────────

def add_user(chat_id: int) -> bool:
    """Возвращает True если пользователь новый, False если уже существовал."""
    with _conn() as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO users (chat_id) VALUES (?)",
            (chat_id,)
        )
    return cur.rowcount == 1


def set_user_active(chat_id: int, is_active: bool):
    with _conn() as con:
        con.execute(
            "UPDATE users SET is_active = ? WHERE chat_id = ?",
            (1 if is_active else 0, chat_id)
        )


def get_all_user_ids() -> list[int]:
    with _conn() as con:
        rows = con.execute("SELECT chat_id FROM users").fetchall()
    return [row["chat_id"] for row in rows]


def get_active_user_ids() -> list[int]:
    with _conn() as con:
        rows = con.execute("SELECT chat_id FROM users WHERE is_active = 1").fetchall()
    return [row["chat_id"] for row in rows]


def get_inactive_user_ids() -> list[int]:
    with _conn() as con:
        rows = con.execute("SELECT chat_id FROM users WHERE is_active = 0").fetchall()
    return [row["chat_id"] for row in rows]


# ── Promo ──────────────────────────────────────────────────────────────────────

def is_promo_shown(chat_id: int) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT promo_shown FROM users WHERE chat_id = ?", (chat_id,)
        ).fetchone()
    return bool(row["promo_shown"]) if row else False


def mark_promo_shown(chat_id: int):
    with _conn() as con:
        con.execute(
            "UPDATE users SET promo_shown = 1 WHERE chat_id = ?", (chat_id,)
        )


def reset_promo_shown(chat_id: int):
    with _conn() as con:
        con.execute(
            "UPDATE users SET promo_shown = 0 WHERE chat_id = ?", (chat_id,)
        )


# ── Exports ────────────────────────────────────────────────────────────────────

def record_export(chat_id: int, file_path: str):
    with _conn() as con:
        con.execute(
            "INSERT INTO exports (chat_id, file_path) VALUES (?, ?)",
            (chat_id, file_path)
        )


def get_export_timestamps() -> list[datetime]:
    with _conn() as con:
        rows = con.execute("SELECT exported_at FROM exports").fetchall()
    result = []
    for row in rows:
        val = row["exported_at"]
        if isinstance(val, str):
            result.append(datetime.fromisoformat(val))
        elif isinstance(val, datetime):
            result.append(val)
    return result
