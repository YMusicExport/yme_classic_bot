import telebot
import telebot.apihelper
from telebot import TeleBot
from config import TOKEN
from handlers import register_handlers, print_error
import db


class MyExceptionHandler(telebot.ExceptionHandler):
    def handle(self, exception):
        if isinstance(exception, telebot.apihelper.ApiTelegramException):
            if exception.error_code == 403 and "bot was blocked by the user" in exception.description:
                print(f"Blocked user ignored: {exception}")
                return True
        print_error(exception)
        return False


db.init_db()

bot = TeleBot(TOKEN, threaded=True, exception_handler=MyExceptionHandler())
register_handlers(bot)

try:
    bot.infinity_polling()
except KeyboardInterrupt:
    bot.stop_polling()
