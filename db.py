import secrets
import aiosqlite
from contextlib import asynccontextmanager
from datetime import datetime
from config import DB_FILE


@asynccontextmanager
async def _conn():
    async with aiosqlite.connect(DB_FILE) as con:
        con.row_factory = aiosqlite.Row
        try:
            yield con
            await con.commit()
        except Exception:
            await con.rollback()
            raise


async def init_db():
    async with _conn() as con:
        await con.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id     INTEGER PRIMARY KEY,
                first_seen  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active   INTEGER DEFAULT 1,
                promo_shown INTEGER DEFAULT 0,
                ym_token    TEXT
            );
            CREATE TABLE IF NOT EXISTS exports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER REFERENCES users(chat_id),
                file_path   TEXT,
                exported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_exports_exported_at ON exports(exported_at);
            CREATE TABLE IF NOT EXISTS errors (
                error_id   TEXT PRIMARY KEY,
                chat_id    INTEGER,
                message    TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            PRAGMA journal_mode=WAL;
        """)
        try:
            await con.execute("ALTER TABLE users ADD COLUMN ym_token TEXT")
            await con.commit()
        except Exception:
            pass


# ── Users ──────────────────────────────────────────────────────────────────────

async def add_user(chat_id: int) -> bool:
    async with _conn() as con:
        cur = await con.execute(
            "INSERT OR IGNORE INTO users (chat_id) VALUES (?)",
            (chat_id,)
        )
    return cur.rowcount == 1


async def set_user_active(chat_id: int, is_active: bool):
    async with _conn() as con:
        await con.execute(
            "UPDATE users SET is_active = ? WHERE chat_id = ?",
            (1 if is_active else 0, chat_id)
        )


async def get_all_user_ids() -> list[int]:
    async with _conn() as con:
        rows = await con.execute("SELECT chat_id FROM users")
        return [row["chat_id"] for row in await rows.fetchall()]


async def get_active_user_ids() -> list[int]:
    async with _conn() as con:
        rows = await con.execute("SELECT chat_id FROM users WHERE is_active = 1")
        return [row["chat_id"] for row in await rows.fetchall()]


async def get_inactive_user_ids() -> list[int]:
    async with _conn() as con:
        rows = await con.execute("SELECT chat_id FROM users WHERE is_active = 0")
        return [row["chat_id"] for row in await rows.fetchall()]


# ── Promo ──────────────────────────────────────────────────────────────────────

async def is_promo_shown(chat_id: int) -> bool:
    async with _conn() as con:
        rows = await con.execute(
            "SELECT promo_shown FROM users WHERE chat_id = ?", (chat_id,)
        )
        row = await rows.fetchone()
    return bool(row["promo_shown"]) if row else False


async def mark_promo_shown(chat_id: int):
    async with _conn() as con:
        await con.execute(
            "UPDATE users SET promo_shown = 1 WHERE chat_id = ?", (chat_id,)
        )


async def reset_promo_shown(chat_id: int):
    async with _conn() as con:
        await con.execute(
            "UPDATE users SET promo_shown = 0 WHERE chat_id = ?", (chat_id,)
        )


# ── YM Token ──────────────────────────────────────────────────────────────────

async def set_ym_token(chat_id: int, token: str):
    async with _conn() as con:
        await con.execute(
            "UPDATE users SET ym_token = ? WHERE chat_id = ?",
            (token, chat_id)
        )


async def clear_ym_token(chat_id: int):
    async with _conn() as con:
        await con.execute(
            "UPDATE users SET ym_token = NULL WHERE chat_id = ?", (chat_id,)
        )


async def get_ym_token(chat_id: int) -> str | None:
    async with _conn() as con:
        rows = await con.execute(
            "SELECT ym_token FROM users WHERE chat_id = ?", (chat_id,)
        )
        row = await rows.fetchone()
    return row["ym_token"] if row else None


# ── Exports ────────────────────────────────────────────────────────────────────

async def record_export(chat_id: int, file_path: str):
    async with _conn() as con:
        await con.execute(
            "INSERT INTO exports (chat_id, file_path) VALUES (?, ?)",
            (chat_id, file_path)
        )


async def get_export_timestamps() -> list[datetime]:
    async with _conn() as con:
        rows = await con.execute("SELECT exported_at FROM exports")
        result = []
        for row in await rows.fetchall():
            val = row["exported_at"]
            if isinstance(val, str):
                result.append(datetime.fromisoformat(val))
            elif isinstance(val, datetime):
                result.append(val)
    return result


# ── Errors ─────────────────────────────────────────────────────────────────────

async def save_error(chat_id: int, message: str, context: str = "") -> str:
    error_id = secrets.token_hex(3).upper()
    full = f"{message}\n\n--- context ---\n{context}" if context else message
    async with _conn() as con:
        await con.execute(
            "INSERT INTO errors (error_id, chat_id, message) VALUES (?, ?, ?)",
            (error_id, chat_id, full)
        )
    return error_id


async def get_error(error_id: str) -> dict | None:
    async with _conn() as con:
        rows = await con.execute(
            "SELECT error_id, chat_id, message, created_at FROM errors WHERE error_id = ?",
            (error_id.upper(),)
        )
        row = await rows.fetchone()
    return dict(row) if row else None
