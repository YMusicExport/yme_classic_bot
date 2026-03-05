import re
import time
from datetime import datetime
from telebot import types
from config import ADMIN_ID, IDS_FILE, ACTIVE_USERS_FILE, INACTIVE_USERS_FILE
from stats import get_stats
from export import export_playlist

RE_ADMIN_CHAT = re.compile(r"/chat\s+(\d+)\s+([\s\S]+)")
RE_ADMIN_CHAT_ALL = re.compile(r"/chat_all\s+([\s\S]+)")
RE_UUID_PLAYLIST = re.compile(r"https://music\.yandex\.(ru|com|kz|by|uz)/playlists/\S+")
RE_IFRAME_SRC = re.compile(r'src="https://music\.yandex\.(?:ru|com|kz|by|uz)/iframe/playlist/([^/]+)/([^"]+)"')
RE_OLD_PLAYLIST_URL = re.compile(r"https://music\.yandex\..+/users/.+/playlists/.+")

user_feedback = {}


def print_error(e, chat_id=0):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "|", "chat id is", chat_id, ">>>", e)


def _send_export_error(bot, message, e, bad_input_msg):
    error_str = str(e).lower()
    if 'tracks' in error_str or 'artists' in error_str:
        bot.reply_to(
            message,
            "⚠️ К сожалению, Яндекс заблокировал экспорт этого плейлиста сейчас. Попробуйте чуть позже.\n\n"
            "Дело в том, что бот работает без входа в аккаунт, и по этой причине Яндекс иногда запрещает "
            "просматривать некоторые плейлисты (в основном «Любимое») таким образом.\n\n"
            "💡 Если не хотите ждать, можно попробовать экспортировать плейлист, запустив скрипт на вашем ПК. "
            "О том, как это сделать: https://teletype.in/@qleqs/yme"
        )
    else:
        bot.reply_to(message, f"Ошибка! {bad_input_msg} Инструкция /start\n\nInfo: {e}")
    bot.send_message(message.chat.id, "📨 Вопросы, идеи, предложения? /feedback")


def _send_progress(bot, prev_msg_id, done, total):
    if prev_msg_id:
        try:
            bot.delete_message(ADMIN_ID, prev_msg_id)
        except Exception:
            pass
    msg = bot.send_message(ADMIN_ID, f"⚡ Прогресс {(done * 100) // total}%")
    time.sleep(0.5)
    return msg.message_id


def register_handlers(bot):

    # ── Admin ─────────────────────────────────────────────────────────────────

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '/clean_ids')
    def clean_ids_file(message):
        with open(IDS_FILE, 'r', encoding='utf-8') as f:
            unique_ids = set(line.strip() for line in f)
        with open(IDS_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(unique_ids) + "\n")
        bot.send_message(message.chat.id, "📊 <b>Количество уникальных юзеров</b>", parse_mode="HTML")
        with open(IDS_FILE, 'rb') as f:
            bot.send_document(message.chat.id, f)

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '/admin_stats')
    def admin_stats(message):
        bot.send_message(message.chat.id, f"📊 <b>Статистика успешных экспортов (с 01.03.26)</b>\n\n{get_stats()}", parse_mode="HTML")

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and RE_ADMIN_CHAT.match(m.text))
    def chat_with_user(message):
        match = RE_ADMIN_CHAT.match(message.text)
        chat_id, text = match.group(1), match.group(2)
        try:
            bot.send_message(chat_id, f"<b>📩 Сообщение от админа</b>\n\n{text}", parse_mode="HTML")
            bot.send_message(message.chat.id, f"<b>Было отправлено сообщение:</b>\n\n{text}", parse_mode="HTML")
        except Exception as e:
            print_error(e, message.chat.id)
            bot.send_message(message.chat.id, f"<b>Ошибка!</b> {e}", parse_mode="HTML")

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and RE_ADMIN_CHAT_ALL.match(m.text))
    def chat_all_users(message):
        text = RE_ADMIN_CHAT_ALL.match(message.text).group(1).strip()
        if not text:
            bot.send_message(message.chat.id, "Пожалуйста, введите сообщение для отправки.")
            return

        with open(IDS_FILE, 'r', encoding='utf-8') as f:
            user_ids = [line.strip() for line in f]

        sent = failed = 0
        total = len(user_ids)
        progress_msg_id = None

        for user_id in user_ids:
            if (sent + failed) % 100 == 0:
                progress_msg_id = _send_progress(bot, progress_msg_id, sent + failed, total)
            try:
                bot.send_message(user_id, f"<b>📩 Сообщение от админа</b>\n\n{text}", parse_mode="HTML")
                sent += 1
            except Exception as e:
                print_error(e, user_id)
                failed += 1

        if progress_msg_id:
            try:
                bot.delete_message(ADMIN_ID, progress_msg_id)
            except Exception:
                pass
        bot.send_message(ADMIN_ID, f"✅ Сообщение отправлено:\n\n- Успешно: {sent}\n- Не удалось отправить: {failed}")

    @bot.message_handler(func=lambda m: m.chat.id == ADMIN_ID and m.text == '/user_stats')
    def user_stats(message):
        open(ACTIVE_USERS_FILE, 'w').close()
        open(INACTIVE_USERS_FILE, 'w').close()
        progress_msg_id = None

        try:
            with open(IDS_FILE, 'r', encoding='utf-8') as f:
                user_ids = [line.strip() for line in f]

            active = inactive = 0
            total = len(user_ids)

            for user_id in user_ids:
                if (active + inactive) % 100 == 0:
                    progress_msg_id = _send_progress(bot, progress_msg_id, active + inactive, total)
                try:
                    temp = bot.send_message(user_id, "Информация", timeout=2)
                    bot.delete_message(user_id, temp.message_id)
                    active += 1
                    with open(ACTIVE_USERS_FILE, 'a', encoding='utf-8') as f:
                        f.write(f"{user_id}\n")
                except Exception:
                    inactive += 1
                    with open(INACTIVE_USERS_FILE, 'a', encoding='utf-8') as f:
                        f.write(f"{user_id}\n")

            if progress_msg_id:
                try:
                    bot.delete_message(ADMIN_ID, progress_msg_id)
                except Exception:
                    pass

            with open(ACTIVE_USERS_FILE, 'rb') as f:
                bot.send_document(ADMIN_ID, f, caption="Список активных пользователей")
            with open(INACTIVE_USERS_FILE, 'rb') as f:
                bot.send_document(ADMIN_ID, f, caption="Список неактивных пользователей")
            bot.send_message(ADMIN_ID, f"Всего: {active + inactive}\nАктивно: {active}\nЗаблокировали: {inactive}")

        except Exception as e:
            print_error(e, message.chat.id)
            bot.send_message(message.chat.id, f"<b>Ошибка!</b> {e}", parse_mode="HTML")

    # ── User ──────────────────────────────────────────────────────────────────

    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        with open(IDS_FILE, "a") as f:
            f.write("\n" + str(message.chat.id))
        bot.send_message(
            message.chat.id,
            "<b>🎵 Экспорт Яндекс Музыки</b>\n\n"
            "Бот экспортирует любой плейлист Яндекс Музыки в текстовый файл "
            "в формате: ИСПОЛНИТЕЛЬ - НАЗВАНИЕ ТРЕКА.\n\n"
            "<b>📝 Как пользоваться:</b>\n"
            "1. Скопируйте ссылку на плейлист вида:\n"
            "<code>https://music.yandex.ru/users/USERNAME/playlists/ID</code>\n"
            "Либо используйте HTML-код (подробнее: https://link.u-pov.ru/ymelnk)\n\n"
            "2. Отправьте ссылку боту\n\n"
            "<b>⚠️ Важно:</b>\n"
            "• Плейлист должен быть <u>публичным</u> (не приватным)\n"
            "• Если некоторые треки не появились в файле — они запрещены для просмотра без авторизации. Бот работает без авторизации, решение в разработке\n"
            "• Некоторые плейлисты (особенно «Любимое») могут быть полностью недоступны без входа в аккаунт\n\n"
            "<b>💬 Связь:</b>\n"
            "Фидбек, предложения: /feedback или https://t.me/aleqsanbr",
            parse_mode="HTML"
        )
        time.sleep(1)
        bot.send_message(message.chat.id, "❗️❗️❗️ Если бот не работает, то используйте веб-версию: https://ymusicexport.ru или скрипт: https://teletype.in/@qleqs/yme")
        bot.send_message(message.chat.id, "👇 Отправьте ссылку на плейлист")

    @bot.message_handler(commands=['feedback'])
    def feedback_start(message):
        user_feedback[message.chat.id] = []
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("Отправить"), types.KeyboardButton("Отмена"))
        bot.send_message(
            message.chat.id,
            "📝 Напишите сообщение и прикрепите файлы (если нужно).\n\n"
            "⚠️ <b>Когда закончите — нажмите кнопку «Отправить»</b>\n\n"
            "<i>Не видите кнопку? Нажмите на значок клавиатуры (☰) внизу экрана</i>",
            reply_markup=markup,
            parse_mode="HTML"
        )

    @bot.message_handler(
        func=lambda m: m.chat.id in user_feedback and m.text not in ["Отправить", "Отмена"],
        content_types=['text', 'photo', 'document', 'audio', 'video', 'voice', 'sticker', 'location', 'contact']
    )
    def collect_feedback(message):
        user_feedback[message.chat.id].append(message)

    @bot.message_handler(func=lambda m: m.text == "Отмена")
    def cancel_feedback(message):
        user_feedback.pop(message.chat.id, None)
        bot.send_message(message.chat.id, "Отправка отменена", reply_markup=types.ReplyKeyboardRemove())

    @bot.message_handler(func=lambda m: m.text == "Отправить" and m.chat.id in user_feedback)
    def send_feedback(message):
        if not user_feedback[message.chat.id]:
            bot.send_message(message.chat.id, "Вы ничего не написали, фидбек не отправлен 🤔", reply_markup=types.ReplyKeyboardRemove())
            del user_feedback[message.chat.id]
            return

        user_link = f"@{message.from_user.username}" if message.from_user.username else f"tg://user?id={message.chat.id}"
        bot.send_message(ADMIN_ID, f"<b>Пришел фидбек от {user_link}</b> [id: <code>{message.chat.id}</code>]", parse_mode="HTML")

        for item in user_feedback[message.chat.id]:
            caption = item.caption or ""
            ct = item.content_type
            if ct == 'text':
                bot.send_message(ADMIN_ID, item.text)
            elif ct == 'photo':
                bot.send_photo(ADMIN_ID, item.photo[-1].file_id, caption=caption)
            elif ct == 'document':
                bot.send_document(ADMIN_ID, item.document.file_id, caption=caption)
            elif ct == 'audio':
                bot.send_audio(ADMIN_ID, item.audio.file_id, caption=caption)
            elif ct == 'video':
                bot.send_video(ADMIN_ID, item.video.file_id, caption=caption)
            elif ct == 'voice':
                bot.send_voice(ADMIN_ID, item.voice.file_id, caption=caption)
            elif ct == 'sticker':
                bot.send_sticker(ADMIN_ID, item.sticker.file_id)
            elif ct == 'location':
                bot.send_location(ADMIN_ID, latitude=item.location.latitude, longitude=item.location.longitude)
            elif ct == 'contact':
                bot.send_contact(ADMIN_ID, phone_number=item.contact.phone_number, first_name=item.contact.first_name)

        bot.send_message(message.chat.id, "✅ Сообщение отправлено! Спасибо за обратную связь 💜", reply_markup=types.ReplyKeyboardRemove())
        del user_feedback[message.chat.id]

    # ── Export ────────────────────────────────────────────────────────────────

    @bot.message_handler(func=lambda m: RE_UUID_PLAYLIST.match(m.text))
    def handle_uuid_playlist(message):
        bot.send_message(
            message.chat.id,
            "🔍 <b>Ссылка нового формата</b>\n\n"
            "Такие ссылки нужно конвертировать. Это просто:\n\n"
            "1. Откройте ссылку в браузере\n"
            "2. Нажмите «Поделиться» → «HTML код»\n"
            "3. Скопируйте код и отправьте сюда\n\n"
            "Должно получиться примерно так:\n"
            "<code>&lt;iframe src=\"https://music.yandex.ru/iframe/...\"&gt;</code>\n\n"
            "📖 Подробная инструкция: https://u-pov.ru/instructions/aleqs/1377",
            parse_mode="HTML"
        )

    @bot.message_handler(func=lambda m: 'iframe' in m.text and 'music.yandex.' in m.text and 'iframe/playlist' in m.text)
    def handle_iframe(message):
        try:
            match = RE_IFRAME_SRC.search(message.text)
            if not match:
                raise ValueError("Не удалось найти ссылку на плейлист в iframe")
            owner, kinds = match.group(1), match.group(2)
            bot.send_message(message.chat.id, "⏳ Экспортирую плейлист...")
            export_playlist(owner, kinds, message, bot)
        except Exception as e:
            print_error(e, message.chat.id)
            _send_export_error(bot, message, e, "Проверьте правильность HTML кода и попробуйте ещё раз.")

    @bot.message_handler(func=lambda m: True)
    def handle_url(message):
        try:
            if not RE_OLD_PLAYLIST_URL.match(message.text):
                raise IndexError("Invalid URL")
            parts = message.text.strip().split('?')[0].split('/')
            owner, kinds = parts[4], parts[6]
            bot.send_message(message.chat.id, "⏳ Экспортирую плейлист...")
            export_playlist(owner, kinds, message, bot)
        except Exception as e:
            print_error(e, message.chat.id)
            _send_export_error(bot, message, e, "Проверьте правильность ссылки и попробуйте ещё раз.")
