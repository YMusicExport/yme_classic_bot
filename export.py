import os
import requests
import time
from datetime import datetime
import db
from promo import get_promo
from logger import log

os.makedirs("exported", exist_ok=True)


def export_playlist(owner, kinds, message, bot):
    chat_id = message.chat.id
    log.info(f"export start [{chat_id}] {owner}/{kinds}")

    uri = f"https://music.yandex.ru/handlers/playlist.jsx?owner={owner}&kinds={kinds}"
    with requests.Session() as session:
        response = session.get(uri)
    response.raise_for_status()

    data = response.json()
    playlist_title = data['playlist']['title']
    tracks = data['playlist']['tracks']

    content = ""
    for track in tracks:
        artists = ", ".join(artist['name'] for artist in track['artists'])
        content += f"{artists} - {track['title']}\n"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"exported/{playlist_title}_{message.chat.id}_{timestamp}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)

    with open(filename, 'rb') as f:
        bot.send_document(message.chat.id, f)

    bot.send_message(
        message.chat.id,
        "✅ <b>Готово!</b> Если при открытии файла в браузере на мобильных устройствах он отображается неправильно, используйте другое приложение для открытия этого файла.\n\n"
        "📨 Оставить отзыв: /feedback\n\n"
        "Спасибо за использование!",
        parse_mode="HTML"
    )

    log.info(f"export success [{chat_id}] \"{playlist_title}\" {len(tracks)} tracks")
    db.record_export(chat_id, filename)

    time.sleep(2)

    promo = get_promo()
    if promo and not db.is_promo_shown(message.chat.id):
        bot.send_message(message.chat.id, promo, parse_mode="HTML")
        db.mark_promo_shown(message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "Это проект с открытым исходным кодом, который делает и поддерживает один человек. "
            "Без рекламы, без подписок — просто и удобно. Если он оказался полезным, небольшое "
            "пожертвование поможет ему жить и развиваться.\n\n"
            "💜 Поддержать можно тут: https://aleqsanbr.dev\n"
        )
