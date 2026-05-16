# Yandex Music Export Bot (classic)

Telegram bot for exporting Yandex Music playlists to `.txt` files in the format `ARTIST - TITLE`.

## Features

- Export any public playlist by URL
- Login with your Yandex Music account (`/login`) to export private playlists and "Liked tracks"
- Search your own playlists by name — just type the name, no command needed
- Logout at any time with `/logout`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:
```
TOKEN=your_bot_token
ADMIN_ID=your_telegram_id
PLAYLIST_API_URL=your_playlist_api_url
```

Run:
```bash
python3 yme_bot.py
```

## Usage

**Without account:**
Send a link to a public playlist:
```
https://music.yandex.ru/playlists/...
```

**With account:**
Use `/login` to authenticate via Yandex OAuth Device Flow. After that:
- Private playlists and "Liked tracks" become available
- Type any text to search your playlists by name

## Acknowledgements

- [yandex-music-api](https://github.com/MarshalX/yandex-music-api) — unofficial Python library for Yandex Music API, used for authenticated playlist export
