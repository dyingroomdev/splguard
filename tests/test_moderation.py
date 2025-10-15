from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from splguard.models import UserInfraction
from splguard.services.moderation import (
    ModerationAction,
    ModerationProfile,
    ModerationService,
)
from splguard.metrics import reset_counters


@pytest.fixture
async def engine() -> AsyncEngine:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda conn: UserInfraction.__table__.create(conn, checkfirst=True))
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncSession:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest.fixture
def redis_mocker(monkeypatch):
    class DummyRedis:
        def __init__(self):
            self.store = {}

        async def set(self, key, value, ex=None):
            self.store[key] = value

        async def incr(self, key):
            self.store[key] = int(self.store.get(key, 0)) + 1
            return self.store[key]

        async def expire(self, key, ttl):
            return True

        async def ttl(self, key):
            return -1

        async def exists(self, key):
            return key in self.store

        async def get(self, key):
            return self.store.get(key)

        async def smembers(self, key):
            return set()

        async def sadd(self, key, value):
            return 1

        async def ping(self):
            return True

    dummy = DummyRedis()
    monkeypatch.setattr("splguard.redis.get_redis_client", lambda: dummy)
    return dummy


@pytest.fixture(autouse=True)
def reset_metrics():
    reset_counters()
    yield
    reset_counters()


def make_profile() -> ModerationProfile:
    return ModerationProfile(
        settings_id=1,
        allowed_domains=set(),
        probation_seconds=600,
        media_probation_seconds=600,
        max_mentions=3,
        ad_keywords=[],
        thresholds={"warn": 1, "mute": 3, "ban": 5},
        strike_ttl=3600,
        mute_seconds=900,
        admin_channel_id=None,
    )


@pytest.mark.asyncio
async def test_first_offense_warns(session: AsyncSession, redis_mocker):
    service = ModerationService(session, redis_mocker)
    profile = make_profile()

    decision = await service.increment_strike(
        profile=profile,
        user_id=123,
        chat_id=456,
        reason="Unauthorized link",
        username="tester",
    )

    assert decision.action == ModerationAction.WARN


@pytest.mark.asyncio
async def test_escalation_to_mute(session: AsyncSession, redis_mocker):
    service = ModerationService(session, redis_mocker)
    profile = make_profile()

    for _ in range(profile.thresholds["mute"]):
        decision = await service.increment_strike(
            profile=profile,
            user_id=321,
            chat_id=654,
            reason="Repeated offense",
            username="tester",
        )

    assert decision.action in {ModerationAction.MUTE, ModerationAction.BAN}


@pytest.mark.asyncio
async def test_probation_blocks_links(session: AsyncSession, redis_mocker):
    service = ModerationService(session, redis_mocker)
    profile = make_profile()

    await service.set_probation(
        profile=profile,
        chat_id=1,
        user_id=999,
        username="probation_user",
        probation_seconds=600,
    )

    assert await service.is_user_in_probation(
        profile=profile,
        chat_id=1,
        user_id=999,
    )
