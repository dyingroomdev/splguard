import pytest
from types import SimpleNamespace

from splguard.services import affiliates
from splguard.models import InviteLink
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from splguard.db import Base


class DummyBot:
    def __init__(self, link: str):
        self._link = link
        self.calls = 0
        self.revoked = []

    async def create_chat_invite_link(self, *args, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            invite_link=self._link,
            name=kwargs.get("name"),
            creates_join_request=True,
        )

    async def revoke_chat_invite_link(self, chat_id, invite_link):
        self.revoked.append((chat_id, invite_link))


@pytest.fixture
async def memory_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_record_invite(memory_session, monkeypatch):
    from splguard import config

    monkeypatch.setattr(config.settings, "splshield_chat_id", -1001234567890)
    monkeypatch.setattr(config.settings, "affiliates_enabled", True)
    monkeypatch.setattr(config.settings, "affiliates_max_links_per_user", 1)
    monkeypatch.setattr(config.settings, "affiliates_rotate_expiry_days", 0)
    monkeypatch.setattr(config.settings, "affiliates_notify_shiller", False)

    bot = DummyBot("https://t.me/+abcdef")

    link = await affiliates.ensure_link(memory_session, bot, owner_id=42, name="promo")
    assert isinstance(link, InviteLink)
    assert link.invite_link == "https://t.me/+abcdef"
    assert bot.calls == 1

    count = await affiliates.invite_count(memory_session, link.invite_link)
    assert count == 0

    stored = await affiliates.record_join(memory_session, link.invite_link, joined_user_id=1001)
    assert stored is True

    # repeat join ignored
    stored_again = await affiliates.record_join(memory_session, link.invite_link, joined_user_id=1001)
    assert stored_again is False

    count = await affiliates.invite_count(memory_session, link.invite_link)
    assert count == 1

    top = await affiliates.top_inviters(memory_session, days=7, limit=5)
    assert top and top[0]["owner_id"] == 42 and top[0]["joins"] == 1

    # rotation generates new link and revokes previous
    bot._link = "https://t.me/+xyz"
    new_link = await affiliates.rotate_link(memory_session, bot, owner_id=42, name="promo2")
    assert new_link.invite_link == "https://t.me/+xyz"
    assert bot.revoked  # previous link revoked
