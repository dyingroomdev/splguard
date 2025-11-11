from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums.parse_mode import ParseMode

from .bot import router
from .bot.middlewares import DatabaseSessionMiddleware, ModerationMiddleware, RedisMiddleware
from .config import settings
from .discordbot import DiscordBotRunner
from .logging_setup import configure_logging
from .tasks.presale_monitor import PresaleMonitor
from .version import get_version

try:
    import sentry_sdk
except ImportError:  # pragma: no cover
    sentry_sdk = None

logger = logging.getLogger(__name__)


async def _run_polling() -> None:
    configure_logging()

    if settings.sentry_dsn and sentry_sdk is not None:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.05)

    logger.info("splashield_bot_startup", extra={"version": get_version()})

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=None),
    )
    dp = Dispatcher()
    db_middleware = DatabaseSessionMiddleware()
    redis_middleware = RedisMiddleware()
    moderation_middleware = ModerationMiddleware()
    presale_monitor = PresaleMonitor()
    dp.message.middleware(db_middleware)
    dp.message.middleware(redis_middleware)
    dp.message.middleware(moderation_middleware)
    dp.callback_query.middleware(db_middleware)
    dp.callback_query.middleware(redis_middleware)
    dp.chat_member.middleware(db_middleware)
    dp.chat_member.middleware(redis_middleware)
    dp.chat_member.middleware(moderation_middleware)
    dp.chat_join_request.middleware(db_middleware)
    dp.chat_join_request.middleware(redis_middleware)
    dp.startup.register(presale_monitor.start)
    dp.shutdown.register(presale_monitor.stop)
    dp.include_router(router)
    discord_runner: DiscordBotRunner | None = None
    if settings.discord_bot_token:
        discord_runner = DiscordBotRunner()

    logger.info("Starting bot polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    # Enable chat_member updates to receive new member notifications
    tasks = [dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())]
    if discord_runner:
        tasks.append(discord_runner.start())
    try:
        await asyncio.gather(*tasks)
    finally:
        if discord_runner:
            await discord_runner.stop()


def run() -> None:
    """Entrypoint for launching the bot."""
    asyncio.run(_run_polling())


if __name__ == "__main__":
    run()
