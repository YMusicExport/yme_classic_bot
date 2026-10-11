import asyncio
import os
import re
from datetime import datetime

import aiofiles
import requests
from yandex_music import ClientAsync
from yandex_music.exceptions import NotFoundError

import db
from config import PLAYLIST_API_CLOUDRU_URL, PLAYLIST_API_URL
from logger import log
from promo import get_promo

RE_UUID_PLAYLIST = re.compile(r"(https?://)?music\.yandex\.[a-z]{2,}/playlists/([^/?]+)")
RE_OLD_PLAYLIST_URL = re.compile(r"(https?://)?music\.yandex\.[a-z]{2,}/users/.+/playlists/.+")

os.makedirs("exported", exist_ok=True)


def _safe_title(title: str | None) -> str:
    return re.sub(r"[^\w\s\-]", "", title or "playlist").strip()


async def export_playlist(bot, chat_id: int, *, message=None, kind=None, owner_uid=None):
    token = await db.get_ym_token(chat_id)
    settings = await db.get_user_settings(chat_id)
    need_duration = bool(settings.get("need_duration") or 0)
    need_numbering = bool(settings.get("need_numbering") or 0)

    if message is not None:
        text = message.text or ""

        if RE_UUID_PLAYLIST.search(text):
            await bot.send_message(chat_id, "⏳ Экспортирую плейлист...")
            log.info(f"export start [{chat_id}] {text}")
            playlist_uuid = RE_UUID_PLAYLIST.search(text).group(2)
            filename = await (
                _fetch_by_url_api(playlist_uuid, token, chat_id, need_duration, need_numbering)
                if token
                else _fetch_by_url_anon(playlist_uuid, chat_id, need_duration, need_numbering)
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
        filename = await _fetch_by_kind(kind, owner_uid, token, chat_id, need_duration, need_numbering)

    await _finish_export(chat_id, bot, filename)


PLAYLIST_APIS = {"yandex": PLAYLIST_API_URL, "cloudru": PLAYLIST_API_CLOUDRU_URL}
PLAYLIST_API_PRIMARY_SETTING = "playlist_api_primary"
# Big playlists take a function 5–10 s to read. Connecting gets less: a dead
# primary should hand over to the fallback quickly.
PRIMARY_CONNECT_TIMEOUT = 4
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
# The playlist itself is missing or private — the other function would
# answer the same.
RE_FINAL_ERROR = re.compile(r"404|not found", re.IGNORECASE)


class PlaylistApiError(Exception):
    """The playlist function refused; the message carries its own error text."""


async def playlist_api_primary() -> str:
    name = await db.get_setting(PLAYLIST_API_PRIMARY_SETTING, "yandex")
    return name if name in PLAYLIST_APIS else "yandex"


async def _playlist_api_order() -> list[str]:
    primary = await playlist_api_primary()
    return [name for name in (primary, *(n for n in PLAYLIST_APIS if n != primary)) if PLAYLIST_APIS[name]]


# The playlist function (shared with the website) returns
# {title, tracks: [{artist, title, durationMs}]}; formatting is ours. The
# primary function goes first, the other one if it fails on its side.
async def _fetch_by_url_anon(playlist_uuid: str, chat_id: int, need_duration: bool, need_numbering: bool) -> str:
    names = await _playlist_api_order()
    failures = []
    for i, name in enumerate(names):
        last = i == len(names) - 1
        try:
            data = await _request_playlist(name, playlist_uuid, PRIMARY_CONNECT_TIMEOUT if not last else CONNECT_TIMEOUT)
        except (PlaylistApiError, requests.RequestException, ValueError) as e:
            log.warning(f"anon fetch [{chat_id}] {name} failed: {e}")
            failures.append(e)
            if RE_FINAL_ERROR.search(str(e)):
                break
            continue

        if i > 0:
            log.info(f"anon fetch [{chat_id}] served by fallback {name}")
        tracks = [(t["artist"], t["title"], t.get("durationMs")) for t in data["tracks"]]
        return await _write_tracks(data["title"], tracks, chat_id, need_duration, need_numbering)

    if not failures:
        raise PlaylistApiError("no playlist function configured")
    # A function that answered knows more than one that didn't connect.
    error = next((e for e in failures if not isinstance(e, requests.RequestException)), failures[-1])
    # Missing or private playlist: the handlers' "not found" message, not an error report.
    if RE_FINAL_ERROR.search(str(error)):
        raise NotFoundError(str(error)) from error
    raise error


async def _request_playlist(name: str, playlist_uuid: str, connect_timeout: int) -> dict:
    response = await asyncio.to_thread(
        requests.get, PLAYLIST_APIS[name], params={"uuid": playlist_uuid}, timeout=(connect_timeout, READ_TIMEOUT)
    )
    if not response.ok:
        try:
            detail = response.json().get("error") or response.text
        except ValueError:
            detail = response.text
        raise PlaylistApiError(f"HTTP {response.status_code}: {detail[:300]}")

    return response.json()


async def _fetch_by_url_api(playlist_uuid: str, token: str, chat_id: int, need_duration: bool, need_numbering: bool) -> str:
    client = await ClientAsync(token).init()
    playlist = await client.playlist(playlist_uuid)

    if not playlist:
        raise NotFoundError

    return await _playlist_to_file(playlist, chat_id, need_duration, need_numbering)


async def _fetch_by_kind(kind: int, owner_uid: int, token: str, chat_id: int, need_duration: bool, need_numbering: bool) -> str:
    client = await ClientAsync(token).init()
    playlist = await client.users_playlists(kind, owner_uid)

    if not playlist:
        raise NotFoundError

    return await _playlist_to_file(playlist, chat_id, need_duration, need_numbering)


async def _playlist_to_file(playlist, chat_id: int, need_duration: bool, need_numbering: bool) -> str:
    tracks = []
    for ts in playlist.tracks or []:
        track = ts.track
        if track is None:
            continue
        artists = ", ".join(a.name for a in (track.artists or []))
        # "Title (version)" — Live / Cover / Remastered, same as the website.
        title = f"{track.title} ({track.version})" if track.version else track.title
        tracks.append((artists, title, track.duration_ms))

    return await _write_tracks(playlist.title, tracks, chat_id, need_duration, need_numbering)


async def _write_tracks(playlist_title: str | None, tracks: list, chat_id: int, need_duration: bool, need_numbering: bool) -> str:
    track_lines = []
    for i, (artists, title, duration_ms) in enumerate(tracks, 1):
        line = f"{artists} - {title}"
        if need_duration:
            dur_s = (duration_ms or 0) // 1000
            line += f" [{dur_s // 60}:{dur_s % 60:02d}]"
        if need_numbering:
            line = f"{i}. {line}"
        track_lines.append(line)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"exported/{_safe_title(playlist_title)}_{chat_id}_{timestamp}.txt"
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
            "Вы также можете экспортировать все свои плейлисты и лайки разом на сайте YMusicExport.com!\n\n"
            "Поддержать проект можно тут: https://yoomoney.ru/to/4100118478520818\n\n"
            "Спасибо 💜",
        )
