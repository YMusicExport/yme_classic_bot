# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup and Running

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 yme_bot.py
```

Requires a `.env` file with `TOKEN` (Telegram bot token) and `ADMIN_ID` (admin's Telegram user ID).

`bot.db` (SQLite) is created automatically on first run via `db.init_db()`. WAL mode is enabled at init.

No build step, no test suite.

## First Deploy / Migration

If migrating from the legacy `ids_yme.txt` file, run once before starting the bot:

```bash
python3 migrate.py
```

## Architecture

The bot is a polling Telegram bot built with **pyTelegramBotAPI** that exports Yandex Music playlists to `.txt` files.

**Module responsibilities:**
- `yme_bot.py` — entry point; calls `db.init_db()`, registers handlers, starts infinity polling with a custom exception handler that silently drops 403 "bot blocked" errors
- `config.py` — loads `.env` and defines file path constants
- `db.py` — all SQLite operations (users, exports, promo flags); single `_conn()` context manager with explicit rollback
- `promo.py` — read/write partner message text from `promo.txt`
- `handlers.py` — all Telegram message/command handlers (user commands, admin commands, feedback flow, URL parsing)
- `export.py` — fetches playlist JSON from `music.yandex.ru/handlers/playlist.jsx`, builds `ARTIST - TITLE` lines, writes to `exported/` with timestamp in filename, records export in DB, shows promo or donate message
- `stats.py` — queries `exports` table and computes export rates over rolling time windows (hour/day/week/month/year)

**Runtime files** (gitignored):
- `bot.db` — SQLite database (+ `bot.db-wal`, `bot.db-shm` WAL sidecar files)
- `promo.txt` — current partner message text; empty or absent = disabled
- `exported/` — generated `.txt` playlist files sent to users

## Database Schema

```sql
users  (chat_id PK, first_seen, is_active, promo_shown)
exports (id PK, chat_id FK, file_path, exported_at)  -- index on exported_at
```

## Partner Message Logic

After a successful export, `export.py` checks `db.is_promo_shown(chat_id)`:
- **Not shown yet + promo active** → sends `promo.txt` content, marks `promo_shown = 1`
- **Already shown or no promo** → sends donate message

## URL Formats Handled

Three playlist link formats are detected via regex in `handlers.py`:
1. Old-style: `https://music.yandex.{tld}/users/{owner}/playlists/{kinds}` // DEPRECATED, NOT SUPPORTED
2. UUID playlist: `https://music.yandex.{tld}/playlists/{uuid}`
3. HTML iframe embed: `<iframe src="https://music.yandex.{tld}/iframe/playlist/{owner}/{kinds}">`  // DEPRECATED, NOT SUPPORTED

## Admin Commands

Available only to the user whose ID matches `ADMIN_ID`:
- `/clean_ids` — show total unique user count from DB
- `/admin_stats` — show export rate statistics
- `/chat {user_id} {message}` — send message to a specific user
- `/chat_all {message}` — broadcast to all users in DB
- `/user_stats` — probe all users for reachability, update `is_active` in DB, send result files
- `/set_promo <text>` — set partner message (HTML supported)
- `/clear_promo` — disable partner message (reverts to donate message)
- `/show_promo` — preview current partner message
