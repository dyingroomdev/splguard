from __future__ import annotations

from typing import Optional

import redis.asyncio as redis

from .config import settings


def get_redis_client() -> Optional[redis.Redis]:
    """Return a shared Redis client instance, if configured."""
    if not settings.redis_url:
        return None
    return redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
