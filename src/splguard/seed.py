from __future__ import annotations

import asyncio

from sqlalchemy import delete, select

from .db import AsyncSessionMaker
from .models import Settings, TeamMember

INITIAL_SETTINGS = {
    "project_name": "SPL Shield",
    "token_ticker": "TDL",
    "contract_addresses": [
        "tdLS6cTi91yLm5BD5H2Ky5Wbs5YeTTHBqfGKjQX2hoz",
    ],
    "explorer_url": "https://solscan.io/token/tdLS6cTi91yLm5BD5H2Ky5Wbs5YeTTHBqfGKjQX2hoz",
    "website": "https://splshield.app",
    "docs": "https://docs.splshield.app",
    "social_links": {
        "twitter": "https://x.com/splshield",
        "telegram": "https://t.me/splshield",
        "github": "https://github.com/splshield",
    },
    "logo": "https://cdn.splshield.app/logo.png",
}

INITIAL_TEAM = [
    {
        "name": "Aragorn",
        "role": "Lead Developer",
        "contact": "@aragornspl",
        "avatar_url": "https://cdn.splshield.app/avatars/aragorn.png",
        "display_order": 1,
    },
    {
        "name": "Tom Harris",
        "role": "Marketing Head",
        "contact": "@tomharrisuk",
        "avatar_url": "https://cdn.splshield.app/avatars/tom.png",
        "display_order": 2,
    },
    {
        "name": "Ethan Miller",
        "role": "COO",
        "contact": "@ethanspl",
        "avatar_url": "https://cdn.splshield.app/avatars/ethan.png",
        "display_order": 3,
    },
]


async def seed() -> None:
    async with AsyncSessionMaker() as session:
        settings_row = await session.scalar(select(Settings))

        if settings_row is None:
            settings_row = Settings(**INITIAL_SETTINGS)
            session.add(settings_row)
            await session.flush()
        else:
            for field, value in INITIAL_SETTINGS.items():
                setattr(settings_row, field, value)

        await session.execute(
            delete(TeamMember).where(TeamMember.settings_id == settings_row.id)
        )
        session.add_all(
            [
                TeamMember(settings_id=settings_row.id, **member)
                for member in INITIAL_TEAM
            ]
        )

        await session.commit()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
