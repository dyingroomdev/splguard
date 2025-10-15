from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    """Declarative base for SQLAlchemy models."""


def _create_engine() -> AsyncEngine:
    return create_async_engine(settings.database_url, echo=False, future=True)


engine: AsyncEngine = _create_engine()
AsyncSessionMaker = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator:
    """Yield an async SQLAlchemy session."""
    async with AsyncSessionMaker() as session:
        yield session
