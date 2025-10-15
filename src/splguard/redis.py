from __future__ import annotations

import redis.asyncio as redis

from .config import settings


def get_redis_client() -> redis.Redis:
    """Return a shared Redis client instance."""
    return redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
