import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from config import config
from database.db import init_db
from llm.yandex_client import YandexGPTClient
from bot.handlers import start, profile, message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():


    await init_db()
    logger.info("Database initialized")

    #Используется tg-ws-proxy
    if config.USE_PROXY and config.PROXY_URL:
        try:
            logger.info(f"Подключение через SOCKS5 прокси: {config.PROXY_URL}")
            session = AiohttpSession(proxy=config.PROXY_URL)

            bot = Bot(
                token=config.BOT_TOKEN,
                session=session,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
            )
            logger.info("Прокси успешно настроен")

        except Exception as e:
            logger.error(f"Ошибка подключения прокси: {e}")
            logger.info("Запуск без прокси")
            bot = Bot(
                token=config.BOT_TOKEN,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
            )
    else:
        logger.info("Запуск без прокси")
        bot = Bot(
            token=config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp["llm_client"] = YandexGPTClient()

    dp.include_router(start.router)
    dp.include_router(profile.router)
    dp.include_router(message.router)

    logger.info("Bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
