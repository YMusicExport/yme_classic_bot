import asyncio
import telebot
import telebot.apihelper
from telebot.async_telebot import AsyncTeleBot, ExceptionHandler
from config import TOKEN
from handlers import register_handlers, print_error
import db


class MyExceptionHandler(ExceptionHandler):
    async def handle(self, exception):
        if isinstance(exception, telebot.apihelper.ApiTelegramException):
            if exception.error_code == 403 and "bot was blocked by the user" in exception.description:
                print(f"Blocked user ignored: {exception}")
                return True
        print_error(exception)
        return False


async def main():
    await db.init_db()
    bot = AsyncTeleBot(TOKEN, exception_handler=MyExceptionHandler())
    register_handlers(bot)
    await bot.infinity_polling()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
