import asyncio
import os
import re
from datetime import datetime

import aiofiles
import requests
from yandex_music import ClientAsync
from yandex_music.exceptions import NotFoundError

import db
from config import PLAYLIST_API_URL
from logger import log
from promo import get_promo

RE_UUID_PLAYLIST = re.compile(r"(https?://)?music\.yandex\.[a-z]{2,}/playlists/([^/?]+)")
RE_OLD_PLAYLIST_URL = re.compile(r"(https?://)?music\.yandex\.[a-z]{2,}/users/.+/playlists/.+")

os.makedirs("exported", exist_ok=True)


async def export_playlist(bot, chat_id: int, *, message=None, kind=None, owner_uid=None):
    token = await db.get_ym_token(chat_id)

    if message is not None:
        text = message.text or ""

        if RE_UUID_PLAYLIST.search(text):
            await bot.send_message(chat_id, "⏳ Экспортирую плейлист...")
            log.info(f"export start [{chat_id}] {text}")
            playlist_uuid = RE_UUID_PLAYLIST.search(text).group(2)
            filename = await (
                _fetch_by_url_api(playlist_uuid, token, chat_id)
                if token
                else _fetch_by_url_anon(playlist_uuid, chat_id)
            )

        elif RE_OLD_PLAYLIST_URL.match(text):
            await bot.send_message(
                chat_id,
                "🔍 <b>Ссылка старого формата</b>\n\n"
                "Для работы бота важно получить ссылку нового формата. Это просто:\n\n"
                "1. Откройте ссылку в браузере\n"
                "2. Дождитесь полной загрузки страницы\n"
                "3. Из адресной строки скопируйте ссылку вида <code>https://music.yandex.ru/playlists/...</code>\n\n"
                "Спасибо!",
                parse_mode="HTML",
            )
            return

        else:
            raise IndexError(f"Invalid URL: {text}")

    else:
        await bot.send_message(chat_id, "⏳ Экспортирую плейлист...")
        log.info(f"export start [{chat_id}] kind={kind} owner={owner_uid}")
        filename = await _fetch_by_kind(kind, owner_uid, token, chat_id)

    await _finish_export(chat_id, bot, filename)


async def _fetch_by_url_anon(playlist_uuid: str, chat_id: int) -> str:
    response = await asyncio.to_thread(requests.get, f"{PLAYLIST_API_URL}?uuid={playlist_uuid}")
    response.raise_for_status()

    data = response.json()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"exported/{data['title']}_{chat_id}_{timestamp}.txt"
    async with aiofiles.open(filename, "w", encoding="utf-8") as f:
        await f.write("\n".join(data["tracks"]) + "\n")

    return filename


async def _fetch_by_url_api(playlist_uuid: str, token: str, chat_id: int) -> str:
    client = await ClientAsync(token).init()
    playlist = await client.playlist(playlist_uuid)

    if not playlist:
        raise NotFoundError

    return await _playlist_to_file(playlist, chat_id)


async def _fetch_by_kind(kind: int, owner_uid: int, token: str, chat_id: int) -> str:
    client = await ClientAsync(token).init()
    playlist = await client.users_playlists(kind, owner_uid)

    if not playlist:
        raise NotFoundError

    return await _playlist_to_file(playlist, chat_id)


async def _playlist_to_file(playlist, chat_id: int) -> str:
    track_lines = []
    for ts in playlist.tracks or []:
        track = ts.track
        if track is None:
            continue
        artists = ", ".join(a.name for a in (track.artists or []))
        track_lines.append(f"{artists} - {track.title}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = re.sub(r"[^\w\s\-]", "", playlist.title or "playlist").strip()
    filename = f"exported/{safe_title}_{chat_id}_{timestamp}.txt"
    async with aiofiles.open(filename, "w", encoding="utf-8") as f:
        await f.write("\n".join(track_lines) + "\n")

    return filename


async def _finish_export(chat_id: int, bot, filename: str):
    async with aiofiles.open(filename, "rb") as f:
        await bot.send_document(chat_id, f)

    await bot.send_message(
        chat_id,
        "✅ <b>Готово!</b> Если при открытии файла в браузере на мобильных устройствах он отображается неправильно, используйте другое приложение для открытия этого файла.\n\n"
        "📨 Оставить отзыв: /feedback\n\n"
        "Спасибо за использование!",
        parse_mode="HTML",
    )

    log.info(f"export success [{chat_id}] {filename}")
    await db.record_export(chat_id, filename)

    await asyncio.sleep(2)

    promo = await get_promo()
    if promo and not await db.is_promo_shown(chat_id):
        await bot.send_message(chat_id, promo, parse_mode="HTML")
        await db.mark_promo_shown(chat_id)
    else:
        await bot.send_message(
            chat_id,
            "Это бесплатный проект, который делает и поддерживает один человек. Если оказался полезным — буду рад поддержке 💜 https://aleqsanbr.dev",
        )
