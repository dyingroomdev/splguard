from __future__ import annotations

from redis.asyncio import Redis


async def is_rate_limited(
    redis: Redis | None, scope: str, key: str, ttl_seconds: int
) -> bool:
    """Return True if the call is rate limited, else mark call and return False."""
    if redis is None:
        return False

    redis_key = f"rate:{scope}:{key}"
    was_set = await redis.set(redis_key, "1", ex=ttl_seconds, nx=True)
    return was_set is None
