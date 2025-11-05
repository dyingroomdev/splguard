import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from splguard.db import Base
from splguard.models import ZealyGrantStatus
from splguard.services import zealy
from splguard.services.presale_verifier import PresaleVerifier

TEST_WALLET = "9" * 44


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
async def test_process_event_handles_known_quest_event() -> None:
    handled = await zealy.process_event(
        "quest.claimed",
        {"questId": "quest-123", "userId": "user-456"},
    )
    assert handled is True


@pytest.mark.asyncio
async def test_process_event_handles_user_event() -> None:
    handled = await zealy.process_event(
        "user.joined",
        {"userId": "user-789"},
    )
    assert handled is True


@pytest.mark.asyncio
async def test_process_event_returns_false_for_unknown_event() -> None:
    handled = await zealy.process_event("something.else", {})
    assert handled is False


@pytest.mark.asyncio
async def test_bind_wallet_creates_member(memory_session) -> None:
    member, status = await zealy.bind_wallet(memory_session, telegram_id=1, wallet=TEST_WALLET)
    assert status == "created"
    assert member.wallet == TEST_WALLET

    member_repeat, repeat_status = await zealy.bind_wallet(memory_session, telegram_id=1, wallet=TEST_WALLET)
    assert repeat_status == "unchanged"
    assert member_repeat.wallet == TEST_WALLET

    with pytest.raises(ValueError):
        await zealy.bind_wallet(memory_session, telegram_id=2, wallet=TEST_WALLET)


@pytest.mark.asyncio
async def test_get_member_summary(memory_session) -> None:
    await zealy.bind_wallet(memory_session, telegram_id=42, wallet=TEST_WALLET)
    summary = await zealy.get_member_summary(memory_session, telegram_id=42)
    assert summary is not None
    assert summary["wallet"] == TEST_WALLET
    assert summary["tier_label"] == zealy.tier_label(summary["tier"])
    assert isinstance(summary["privileges"], list)


@pytest.mark.asyncio
async def test_record_grant_enforces_uniqueness(memory_session) -> None:
    member, _ = await zealy.bind_wallet(memory_session, telegram_id=55, wallet="A" * 44)
    quest = await zealy.get_or_create_quest(memory_session, slug="presale_submission", xp_value=50)
    result = await zealy.record_grant(
        memory_session,
        member=member,
        quest=quest,
        status=ZealyGrantStatus.COMPLETED,
        tx_ref="sig123",
        xp_awarded=50,
    )
    assert result.grant.tx_ref == "sig123"
    assert member.xp == 50
    assert isinstance(result.level_changed, bool)
    assert isinstance(result.tier_changed, bool)

    with pytest.raises(ValueError):
        await zealy.record_grant(
            memory_session,
            member=member,
            quest=quest,
            status=ZealyGrantStatus.COMPLETED,
            tx_ref="sig123",
            xp_awarded=50,
        )


def test_determine_tier_and_privileges() -> None:
    assert zealy.determine_tier(0) == "member"
    assert zealy.determine_tier(600) == "wl"
    assert zealy.determine_tier(2000) == "alpha"
    privileges = zealy.tier_privileges("wl")
    assert isinstance(privileges, list)
    assert privileges


@pytest.mark.asyncio
async def test_dlq_snapshot_without_redis() -> None:
    snapshot = await zealy.dlq_snapshot(None)
    assert snapshot["size"] == 0


@pytest.mark.asyncio
async def test_presale_verifier_requires_wallet() -> None:
    verifier = PresaleVerifier(rpc_url="http://localhost")
    outcome = await verifier.verify("sig", None)
    assert outcome.ok is False
    assert outcome.reason == "wallet_not_linked"
