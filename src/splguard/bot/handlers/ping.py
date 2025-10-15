from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ...metrics import increment as metrics_increment


router = Router(name="ping-handler")


@router.message(Command("ping"))
async def handle_ping(message: Message) -> None:
    """Reply with pong when /ping is received."""
    metrics_increment("command_usage.ping")
    await message.reply("pong")
