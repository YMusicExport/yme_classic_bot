# Yandex Music Export Bot (classic)

Telegram bot for exporting Yandex Music playlists to `.txt` files in the format `ARTIST - TITLE`.

## Launching

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Add to `.env` file your bot token and Telegram ID:
```
TOKEN=your_bot_token
ADMIN_ID=your_telegram_id
```

## Usage

Send the bot a link to a Yandex Music playlist in one of the following formats:
```
https://music.yandex.ru/users/USERNAME/playlists/ID
```
or HTML code from the playlist page:
```html
<iframe src="https://music.yandex.ru/iframe/...">
```
