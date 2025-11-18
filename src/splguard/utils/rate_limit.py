from __future__ import annotations

import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


async def is_rate_limited(
    redis: Redis | None, scope: str, key: str, ttl_seconds: int
) -> bool:
    """Return True if the call is rate limited, else mark call and return False."""
    if redis is None:
        return False

    redis_key = f"rate:{scope}:{key}"
    try:
        was_set = await redis.set(redis_key, "1", ex=ttl_seconds, nx=True)
    except RedisError as exc:
        logger.warning("Rate limit Redis write failed for %s: %s", redis_key, exc)
        return False
    return was_set is None
