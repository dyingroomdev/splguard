from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from aiogram.enums import ChatMemberStatus, ChatType, ContentType
from aiogram.types import Chat, ChatMemberUpdated, Message, User


def make_user(user_id: int, *, is_bot: bool = False, username: str | None = None) -> User:
    return User(
        id=user_id,
        is_bot=is_bot,
        first_name=f"User{user_id}",
        username=username,
    )


def make_chat(chat_id: int, *, type_: ChatType = ChatType.GROUP) -> Chat:
    return Chat(id=chat_id, type=type_, title="Test Chat")


def make_message(
    chat_id: int,
    user_id: int,
    text: str,
    *,
    entities: list[Any] | None = None,
    content_type: ContentType = ContentType.TEXT,
) -> Message:
    chat = make_chat(chat_id)
    user = make_user(user_id)
    return Message(
        message_id=1,
        date=None,
        chat=chat,
        from_user=user,
        text=text,
        content_type=content_type,
        entities=entities,
    )


def make_chat_member_update(chat_id: int, user_id: int) -> ChatMemberUpdated:
    chat = make_chat(chat_id)
    user = make_user(user_id)
    return ChatMemberUpdated(
        update_id=0,
        chat=chat,
        from_user=make_user(999, is_bot=True),
        date=None,
        old_chat_member={"status": ChatMemberStatus.LEFT},
        new_chat_member={
            "user": user.model_dump(),
            "status": ChatMemberStatus.MEMBER,
        },
    )
