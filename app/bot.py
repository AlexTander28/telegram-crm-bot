from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import ConfigurationError, Settings
from app.database import Database
from app.handlers import client_router, manager_router
from app.services.lead_service import LeadService


async def run() -> None:
    settings = Settings.from_env()
    database = Database(settings.database_path)
    await database.initialize()
    service = LeadService(database)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(client_router)
    dispatcher.include_router(manager_router)
    dispatcher["lead_service"] = service
    dispatcher["manager_chat_id"] = settings.manager_chat_id
    dispatcher["manager_ids"] = settings.manager_ids
    dispatcher["export_path"] = settings.export_path
    await dispatcher.start_polling(bot)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    try:
        asyncio.run(run())
    except ConfigurationError as error:
        logging.error("Configuration error: %s", error)
        return 2
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

