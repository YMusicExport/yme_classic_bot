import asyncio
import io
import re
from telebot import types
from yandex_music import ClientAsync
from yandex_music.exceptions import NotFoundError
from config import ADMIN_ID
from stats import get_stats
from export import export_playlist, RE_UUID_PLAYLIST, RE_OLD_PLAYLIST_URL
from promo import get_promo, set_promo, clear_promo
from logger import log
import db

RE_ADMIN_CHAT = re.compile(r"/chat\s+((?:\d+\s+)*\d+)\s+([\s\S]+)")
RE_ADMIN_CHAT_ALL = re.compile(r"/chat_all\s+([\s\S]+)")
RE_SET_PROMO = re.compile(r"/set_promo\s+([\s\S]+)")

user_feedback = {}


def print_error(e, chat_id=0):
    log.error(f"[{chat_id}] {e}")


async def _send_export_error(bot, message, e, bad_input_msg):
    error_str = str(e).lower()
    if 'tracks' in error_str or 'artists' in error_str:
        await bot.reply_to(
            message,
            "⚠️ К сожалению, Яндекс заблокировал экспорт этого плейлиста сейчас. Попробуйте чуть позже.\n\n"
            "Дело в том, что бот работает без входа в аккаунт, и по этой причине Яндекс иногда запрещает "
            "просматривать некоторые плейлисты (в основном «Любимое») таким образом.\n\n"
            "💡 Если не хотите ждать, можно попробовать экспортировать плейлист, запустив скрипт на вашем ПК. "
            "О том, как это сделать: https://teletype.in/@qleqs/yme"
        )
    elif any(kw in error_str for kw in ('ssl', 'connection', 'timeout', 'eof', 'max retries')):
        await bot.reply_to(
            message,
            "⚠️ Не удалось подключиться к Яндекс Музыке. Возможно, сервис временно недоступен.\n\n"
            "💡 Попробуйте чуть позже или экспортируйте плейлист напрямую со своего ПК: "
            "https://teletype.in/@qleqs/yme"
        )
    else:
        await bot.reply_to(message, f"Ошибка! {bad_input_msg} Инструкция /start\n\nInfo: {e}")
    await bot.send_message(message.chat.id, "📨 Вопросы, идеи, предложения? /feedback")


async def _send_progress(bot, prev_msg_id, done, total):
    if prev_msg_id:
        try:
            await bot.delete_message(ADMIN_ID, prev_msg_id)
        except Exception:
            pass
    msg = await bot.send_message(ADMIN_ID, f"⚡ Прогресс {(done * 100) // total}%")
    await asyncio.sleep(0.5)
    return msg.message_id


def register_handlers(bot):

    # ── Admin ─────────────────────────────────────────────────────────────────

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '/clean_ids')
    async def clean_ids_file(message):
        ids = await db.get_all_user_ids()
        await bot.send_message(message.chat.id, f"📊 <b>Количество уникальных юзеров: {len(ids)}</b>", parse_mode="HTML")

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '/admin_stats')
    async def admin_stats(message):
        await bot.send_message(message.chat.id, f"📊 <b>Статистика успешных экспортов (с 21.03.26)</b>\n\n{await get_stats()}", parse_mode="HTML")

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and RE_ADMIN_CHAT.match(m.text or ""))
    async def chat_with_user(message):
        match = RE_ADMIN_CHAT.match(message.text)
        ids_str, text = match.group(1), match.group(2)
        ids = [i for i in ids_str.split() if i.isdigit()]
        if not ids:
            await bot.send_message(message.chat.id, "Пожалуйста, укажите корректные id пользователей.")
            return
        sent = failed = 0
        for chat_id in ids:
            try:
                await bot.send_message(int(chat_id), f"<b>📩 Сообщение от админа</b>\n\n{text}", parse_mode="HTML")
                sent += 1
            except Exception as e:
                print_error(e, chat_id)
                failed += 1
        await bot.send_message(message.chat.id, f"<b>Было отправлено сообщений:</b> {sent}\n<b>Не удалось отправить:</b> {failed}", parse_mode="HTML")

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and RE_ADMIN_CHAT_ALL.match(m.text or ""))
    async def chat_all_users(message):
        text = RE_ADMIN_CHAT_ALL.match(message.text).group(1).strip()
        if not text:
            await bot.send_message(message.chat.id, "Пожалуйста, введите сообщение для отправки.")
            return

        user_ids = await db.get_all_user_ids()
        total = len(user_ids)
        progress_msg_id = None
        sent = failed = 0

        for i, user_id in enumerate(user_ids):
            if i % 100 == 0:
                progress_msg_id = await _send_progress(bot, progress_msg_id, i, total)
            try:
                await bot.send_message(user_id, f"<b>📩 Сообщение от админа</b>\n\n{text}", parse_mode="HTML")
                sent += 1
            except Exception as e:
                print_error(e, user_id)
                failed += 1

        if progress_msg_id:
            try:
                await bot.delete_message(ADMIN_ID, progress_msg_id)
            except Exception:
                pass
        await bot.send_message(ADMIN_ID, f"✅ Сообщение отправлено:\n\n- Успешно: {sent}\n- Не удалось отправить: {failed}")

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '/user_stats')
    async def user_stats(message):
        try:
            user_ids = await db.get_all_user_ids()
            log.info(f"user_stats started, total: {len(user_ids)}")

            async def check_user(user_id):
                try:
                    await bot.get_chat(user_id)
                    await db.set_user_active(user_id, True)
                    log.info(f"user_stats [{user_id}] active")
                except Exception as e:
                    await db.set_user_active(user_id, False)
                    log.info(f"user_stats [{user_id}] inactive: {e}")

            await asyncio.gather(*[check_user(uid) for uid in user_ids])

            active_ids = await db.get_active_user_ids()
            inactive_ids = await db.get_inactive_user_ids()

            active_file = io.BytesIO("\n".join(str(i) for i in active_ids).encode())
            active_file.name = "active_users.txt"
            inactive_file = io.BytesIO("\n".join(str(i) for i in inactive_ids).encode())
            inactive_file.name = "inactive_users.txt"

            await bot.send_document(ADMIN_ID, active_file, caption="Список активных пользователей")
            await bot.send_document(ADMIN_ID, inactive_file, caption="Список неактивных пользователей")

        except Exception as e:
            print_error(e, message.chat.id)
            await bot.send_message(message.chat.id, f"<b>Ошибка!</b> {e}", parse_mode="HTML")

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and RE_SET_PROMO.match(m.text or ""))
    async def admin_set_promo(message):
        text = RE_SET_PROMO.match(message.text).group(1).strip()
        await set_promo(text)
        await bot.send_message(message.chat.id, f"✅ Партнёрское сообщение установлено:\n\n{text}", parse_mode="HTML")

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '/clear_promo')
    async def admin_clear_promo(message):
        await clear_promo()
        await bot.send_message(message.chat.id, "🗑 Партнёрское сообщение удалено. Показывается сообщение о донате.")

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '/show_promo')
    async def admin_show_promo(message):
        promo = await get_promo()
        if promo:
            await bot.send_message(message.chat.id, f"📋 <b>Текущее партнёрское сообщение:</b>\n\n{promo}", parse_mode="HTML")
        else:
            await bot.send_message(message.chat.id, "Партнёрское сообщение не задано. Показывается сообщение о донате.")

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '/test_promo')
    async def admin_test_promo(message):
        promo = await get_promo()
        if promo:
            await bot.send_message(message.chat.id, promo, parse_mode="HTML")
        else:
            await bot.send_message(message.chat.id, "Партнёрское сообщение не задано — нечего тестировать.")

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '/reset_promo')
    async def admin_reset_promo(message):
        await db.reset_promo_shown(message.chat.id)
        await bot.send_message(message.chat.id, "🔄 Флаг promo_shown сброшен. Следующий экспорт покажет промо.")

    # ── User ──────────────────────────────────────────────────────────────────

    @bot.message_handler(commands=['start'])
    async def send_welcome(message):
        is_new = await db.add_user(message.chat.id)
        if is_new:
            log.info(f"new user [{message.chat.id}]")
        await bot.send_message(
            message.chat.id,
            "<b>🎵 Экспорт Яндекс Музыки</b>\n\n"
            "Бот экспортирует плейлисты Яндекс Музыки в текстовый файл "
            "в формате: ИСПОЛНИТЕЛЬ - НАЗВАНИЕ ТРЕКА.\n\n"
            "<b>📝 Без авторизации:</b>\n"
            "Отправьте ссылку на публичный плейлист:\n"
            "<code>https://music.yandex.ru/playlists/...</code>\n\n"
            "<b>🔐 С авторизацией (/login):</b>\n"
            "• Приватные плейлисты, а также те, которые не получается экспортировать без авторизации\n"
            "• Поиск по своим плейлистам — просто напишите название\n\n"
            "<b>💬 Связь:</b>\n"
            "Фидбек, предложения: /feedback или https://t.me/aleqsanbr",
            parse_mode="HTML"
        )
        await asyncio.sleep(1)
        await bot.send_message(message.chat.id, "👇 Отправьте ссылку на плейлист или войдите через /login")

    @bot.message_handler(commands=['feedback'])
    async def feedback_start(message):
        user_feedback[message.chat.id] = []
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("Отправить"), types.KeyboardButton("Отмена"))
        await bot.send_message(
            message.chat.id,
            "📝 Напишите сообщение и прикрепите файлы (если нужно). Пожалуйста, не присылайте голые ссылки без комментариев — я не знаю, что с ними делать)) Также по возможности присылайте полное сообщение об ошибке, если не получается экспортировать плейлист.\n\n"
            "⚠️ <b>Когда закончите — нажмите кнопку «Отправить»</b>\n\n"
            "<i>Не видите кнопку? Нажмите на значок клавиатуры (☰) внизу экрана</i>",
            reply_markup=markup,
            parse_mode="HTML"
        )

    @bot.message_handler(
        func=lambda m: m.chat.id in user_feedback and m.text not in ["Отправить", "Отмена"],
        content_types=['text', 'photo', 'document', 'audio', 'video', 'voice', 'sticker', 'location', 'contact']
    )
    async def collect_feedback(message):
        user_feedback[message.chat.id].append(message)

    @bot.message_handler(func=lambda m: m.text == "Отмена")
    async def cancel_feedback(message):
        user_feedback.pop(message.chat.id, None)
        await bot.send_message(message.chat.id, "Отправка отменена", reply_markup=types.ReplyKeyboardRemove())

    @bot.message_handler(func=lambda m: m.text == "Отправить" and m.chat.id in user_feedback)
    async def send_feedback(message):
        if not user_feedback[message.chat.id]:
            await bot.send_message(message.chat.id, "Вы ничего не написали, фидбек не отправлен 🤔", reply_markup=types.ReplyKeyboardRemove())
            del user_feedback[message.chat.id]
            return

        user_link = f"@{message.from_user.username}" if message.from_user.username else f"tg://user?id={message.chat.id}"
        await bot.send_message(ADMIN_ID, f"<b>Пришел фидбек от {user_link}</b> [id: <code>{message.chat.id}</code>]", parse_mode="HTML")

        for item in user_feedback[message.chat.id]:
            caption = item.caption or ""
            ct = item.content_type
            if ct == 'text':
                await bot.send_message(ADMIN_ID, item.text)
            elif ct == 'photo':
                await bot.send_photo(ADMIN_ID, item.photo[-1].file_id, caption=caption)
            elif ct == 'document':
                await bot.send_document(ADMIN_ID, item.document.file_id, caption=caption)
            elif ct == 'audio':
                await bot.send_audio(ADMIN_ID, item.audio.file_id, caption=caption)
            elif ct == 'video':
                await bot.send_video(ADMIN_ID, item.video.file_id, caption=caption)
            elif ct == 'voice':
                await bot.send_voice(ADMIN_ID, item.voice.file_id, caption=caption)
            elif ct == 'sticker':
                await bot.send_sticker(ADMIN_ID, item.sticker.file_id)
            elif ct == 'location':
                await bot.send_location(ADMIN_ID, latitude=item.location.latitude, longitude=item.location.longitude)
            elif ct == 'contact':
                await bot.send_contact(ADMIN_ID, phone_number=item.contact.phone_number, first_name=item.contact.first_name)

        await bot.send_message(message.chat.id, "✅ Сообщение отправлено! Спасибо за обратную связь 💜", reply_markup=types.ReplyKeyboardRemove())
        del user_feedback[message.chat.id]

    # ── Login ─────────────────────────────────────────────────────────────────

    @bot.message_handler(commands=['login'])
    async def login(message):
        chat_id = message.chat.id

        await bot.send_message(chat_id,
            "🔐 <b>Авторизация в Яндекс Музыке</b>\n\n"
            "Сейчас придёт ссылка и код — откройте ссылку, войдите в аккаунт и введите код.\n\n"
            "⚠️ Яндекс покажет длинный список разрешений — это нормально. Бот авторизуется "
            "через официальное приложение Яндекс.Музыки, которое имеет широкий набор прав. "
            "Используется только чтение плейлистов. Исходный код этого бота в <a href=\"https://github.com/YMusicExport/yme_classic_bot\">GitHub-репозитории</a>.\n\n"
            "Токен хранится в базе бота. Отозвать доступ можно в любой момент через /logout",
            parse_mode="HTML",
            link_preview_options=types.LinkPreviewOptions(is_disabled=True)
        )

        async def on_code(code):
            await bot.send_message(chat_id, f"🔗 Откройте {code.verification_url} и введите код <code>{code.user_code}</code>", parse_mode="HTML")

        try:
            client = ClientAsync()
            oauth = await client.device_auth(on_code=on_code)
            await db.set_ym_token(chat_id, oauth.access_token)
            await bot.send_message(chat_id,
                "✅ <b>Авторизация успешна</b>\n\n"
                "Теперь все плейлисты будут экспортироваться напрямую через ваш аккаунт. Выход из аккаунта /logout",
                parse_mode="HTML"
            )
            log.info(f"ym login success [{chat_id}]")
        except Exception as e:
            log.error(f"ym login error [{chat_id}]: {e}")
            await bot.send_message(chat_id, f"❌ Ошибка авторизации: {e}")

    @bot.message_handler(commands=['logout'])
    async def logout(message):
        chat_id = message.chat.id
        token = await db.get_ym_token(chat_id)
        if not token:
            await bot.send_message(chat_id, "Вы не авторизованы. Для авторизации /login")
            return
        await db.clear_ym_token(chat_id)
        log.info(f"ym logout [{chat_id}]")
        await bot.send_message(chat_id, "✅ Вы вышли из аккаунта Яндекс Музыки. Экспорт будет работать без авторизации")

    # ── Search ────────────────────────────────────────────────────────────────

    async def _do_search(chat_id: int, query: str):
        token = await db.get_ym_token(chat_id)
        if not token:
            await bot.send_message(chat_id,
                "🔍 Поиск по плейлистам доступен после авторизации. Используй /login чтобы войти в аккаунт Яндекс Музыки."
            )
            return

        client = await ClientAsync(token).init()
        playlists = await client.users_playlists_list()

        q = query.lower()
        matches = [p for p in (playlists or []) if q in (p.title or '').lower()]

        if not matches:
            await bot.send_message(chat_id, f"🔍 Плейлисты по запросу «{query}» не найдены")
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for p in matches[:10]:
            markup.add(types.InlineKeyboardButton(
                f"{p.title} (треков: {p.track_count})",
                callback_data=f"pl:{p.kind}:{p.owner.uid}"
            ))

        await bot.send_message(chat_id,
            f"🔍 Найдено плейлистов: {len(matches)}" + (" (показаны первые 10)" if len(matches) > 10 else ""),
            reply_markup=markup
        )

    @bot.callback_query_handler(func=lambda c: c.data.startswith("pl:"))
    async def handle_playlist_callback(call):
        await bot.answer_callback_query(call.id)
        _, kind, owner_uid = call.data.split(":")
        try:
            await export_playlist(bot, call.message.chat.id, kind=int(kind), owner_uid=int(owner_uid))
        except NotFoundError:
            log.warning(f"playlist not found [{call.message.chat.id}] kind={kind}")
            await bot.send_message(call.message.chat.id, "⚠️ Плейлист не найден")
        except Exception as e:
            print_error(e, call.message.chat.id)
            await bot.send_message(call.message.chat.id, f"❌ Ошибка экспорта: {e}")

    # ── Export ────────────────────────────────────────────────────────────────

    @bot.message_handler(func=lambda m: True)
    async def handle_url(message):
        text = message.text or ""
        is_url = RE_UUID_PLAYLIST.search(text) or RE_OLD_PLAYLIST_URL.match(text)

        if not is_url:
            await _do_search(message.chat.id, text)
            return

        try:
            await export_playlist(bot, message.chat.id, message=message)
        except NotFoundError:
            log.warning(f"playlist not found [{message.chat.id}] {message.text}")
            await bot.reply_to(message, "⚠️ Плейлист не найден. Проверьте ссылку или убедитесь, что плейлист не удалён")
        except Exception as e:
            print_error(e, message.chat.id)
            await _send_export_error(bot, message, e, "Проверьте правильность ссылки и попробуйте ещё раз")
