#!/usr/bin/env python3
"""Populate initial settings, team, and presale data."""
import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, '/app/src')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from splguard.models import Settings, Presale, PresaleStatus, TeamMember


async def populate_data():
    engine = create_async_engine("sqlite+aiosqlite:////app/splguard.db")
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Check if settings exist
        result = await session.execute(select(Settings).limit(1))
        settings = result.scalar_one_or_none()

        if not settings:
            print("Creating initial settings...")
            settings = Settings(
                project_name="SPL Shield",
                token_ticker="TDL",
                contract_addresses=["tdLS6cTi91yLm5BD5H2Ky5Wbs5YeTTHBqfGKjQX2hoz"],
                explorer_url="https://solscan.io/token/tdLS6cTi91yLm5BD5H2Ky5Wbs5YeTTHBqfGKjQX2hoz",
                website="https://splshield.com/",
                docs="https://docs.splshield.com/",
                social_links={
                    "Twitter": "https://twitter.com/splshield",
                    "Risk Scanner App": "https://app.splshield.com/",
                    "Dapp": "https://ex.splshield.com",
                    "Telegram": "https://t.me/splshield",
                }
            )
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
            print("✓ Settings created")
        else:
            print("✓ Settings already exist")

        # Check if team members exist
        result = await session.execute(
            select(TeamMember).where(TeamMember.settings_id == settings.id)
        )
        team_count = len(result.scalars().all())

        if team_count == 0:
            print("Creating team members...")
            team_members = [
                TeamMember(
                    settings_id=settings.id,
                    name="Aragorn",
                    role="Lead Developer",
                    contact="@aragornspl",
                    bio="Building SPL Shield's AI Risk Engine and overseeing the TDL ecosystem's core smart contracts.",
                    display_order=1
                ),
                TeamMember(
                    settings_id=settings.id,
                    name="Tom Harris",
                    role="Marketing Head",
                    contact="@tomharrisuk",
                    bio="Driving global exposure, partnerships, and community growth for SPL Shield and $TDL.",
                    display_order=2
                ),
                TeamMember(
                    settings_id=settings.id,
                    name="Ethan Miller",
                    role="Chief Operating Officer",
                    contact="@ethanspl",
                    bio="Managing operations, presale strategy, and ecosystem expansion.",
                    display_order=3
                )
            ]
            for member in team_members:
                session.add(member)
            await session.commit()
            print(f"✓ Created {len(team_members)} team members")
        else:
            print(f"✓ Team members already exist ({team_count} members)")

        # Check if presale exists
        result = await session.execute(
            select(Presale).where(Presale.settings_id == settings.id).limit(1)
        )
        presale = result.scalar_one_or_none()

        if not presale:
            print("Creating presale record...")
            presale = Presale(
                settings_id=settings.id,
                status=PresaleStatus.UPCOMING,
                platform="SPL Shield Platform",
                links={"presale": "https://presale.splshield.com/"},
                start_time=datetime(2025, 10, 26, 18, 0, 0, tzinfo=timezone.utc),
                hardcap=Decimal('500000'),
                softcap=Decimal('250000'),
                faqs=[
                    {"question": "What is the presale price?", "answer": "$0.002 per TDL"},
                    {"question": "What is the total supply?", "answer": "1 Billion TDL tokens"},
                    {"question": "When does the presale start?", "answer": "6 PM UTC (00+), 26th October 2025"}
                ]
            )
            session.add(presale)
            await session.commit()
            print("✓ Presale created")
        else:
            print("✓ Presale already exists")

    await engine.dispose()
    print("\n✓ All initial data populated successfully!")


if __name__ == "__main__":
    asyncio.run(populate_data())
