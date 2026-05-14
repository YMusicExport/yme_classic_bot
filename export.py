import os
import requests
import time
import re
from datetime import datetime
import db
from promo import get_promo
from logger import log

RE_UUID_PLAYLIST = re.compile(r"(https?://)?music\.yandex\.[a-z]{2,}/playlists/([^/?]+)")
RE_IFRAME_SRC = re.compile(r'src="(https?://)?music\.yandex\.[a-z]{2,}/iframe/playlist/([^/]+)/([^"]+)"')
RE_OLD_PLAYLIST_URL = re.compile(r"(https?://)?music\.yandex\.[a-z]{2,}/users/.+/playlists/.+")

os.makedirs("exported", exist_ok=True)


def export_playlist(message, bot):
    chat_id = message.chat.id
    filename = ""

    if RE_UUID_PLAYLIST.match(message.text or ""):
        bot.send_message(message.chat.id, "⏳ Экспортирую плейлист...")
        log.info(f"export start [{chat_id}] {message.text}")
        filename = export_playlist_uuid(message)
    elif RE_OLD_PLAYLIST_URL.match(message.text or ""):
        bot.send_message(message.chat.id,
            "🔍 <b>Ссылка нового формата</b>\n\n"
            "Для работы бота важно получить ссылку нового формата. Это просто:\n\n"
            "1. Откройте ссылку в браузере\n"
            "2. Дождитесь полной загрузки страницы\n"
            "3. Из адресной строки скопируйте ссылку вида `https://music.yandex.ru/playlists/...`\n\n"
            "Спасибо!",
            parse_mode="HTML"
        )
    else:
        raise IndexError("Invalid URL")

    with open(filename, 'rb') as f:
        bot.send_document(message.chat.id, f)

    bot.send_message(
        message.chat.id,
        "✅ <b>Готово!</b> Если при открытии файла в браузере на мобильных устройствах он отображается неправильно, используйте другое приложение для открытия этого файла.\n\n"
        "📨 Оставить отзыв: /feedback\n\n"
        "Спасибо за использование!",
        parse_mode="HTML"
    )

    log.info(f"export success [{chat_id}] - {message.text}")
    db.record_export(chat_id, filename)

    time.sleep(2)

    promo = get_promo()
    if promo and not db.is_promo_shown(message.chat.id):
        bot.send_message(message.chat.id, promo, parse_mode="HTML")
        db.mark_promo_shown(message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "Это бесплатный проект, который делает и поддерживает один человек. Если оказался полезным — буду рад поддержке 💜 https://aleqsanbr.dev"
        )


def export_playlist_uuid(message):
    m = RE_UUID_PLAYLIST.search(message.text)

    if not m:
        raise IndexError("Invalid URL")

    playlist_uuid = m.group(2)

    response = requests.get(f'https://api.music.yandex.ru/playlist/{playlist_uuid}')
    response.raise_for_status()

    data = response.json()
    playlist_title = data['result']['title']
    tracks = data['result']['tracks']

    tracks_lines = [
        f"{', '.join(artist['name'] for artist in track['track']['artists'])} - {track['track']['title']}"
        for track in tracks
    ]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"exported/{playlist_title}_{message.chat.id}_{timestamp}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        for track in tracks_lines:
            f.write(track + "\n")

    return filename
