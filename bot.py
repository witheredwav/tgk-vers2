import asyncio
import logging
import os
import sys

# Гарантируем, что папка со скриптом первая в sys.path —
# защищает от ModuleNotFoundError, если процесс запущен не из этой директории
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from handlers import user, admin, broadcast, referral

logging.basicConfig(level=logging.INFO)


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Порядок важен: более специфичные роутеры (admin/broadcast) первыми,
    # чтобы их FSM-состояния и callback'и не перехватывались общими хендлерами.
    dp.include_router(broadcast.router)
    dp.include_router(referral.router)
    dp.include_router(admin.router)
    dp.include_router(user.router)

    logging.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
