# Quick Start - Running SplGuard with SQLite

## Current Status ✓
Your SplGuard bot is now configured to use SQLite instead of PostgreSQL!

## What Changed?
1. ✓ `docker-compose.yml` - Removed PostgreSQL network, added SQLite volume mounts
2. ✓ `pyproject.toml` - Replaced `asyncpg` with `aiosqlite`
3. ✓ `.env` - Already configured with `DATABASE_URL=sqlite+aiosqlite:///./splguard.db`
4. ✓ Database migrations - Already applied (version: 20240505_0002)

## Run the Bot (Choose One)

### Option 1: Local Development
```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Run the bot
.venv/bin/splguard-bot
```

### Option 2: Docker
```bash
# 1. Build and start services
docker-compose up --build -d

# 2. Check logs
docker-compose logs -f bot

# 3. Stop services
docker-compose down
```

## Verify It's Working

### Check Database Connection
```bash
.venv/bin/python -c "
import asyncio
import sys
sys.path.insert(0, 'src')
from splguard.db import engine
from sqlalchemy import text

async def test():
    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT COUNT(*) FROM settings'))
        print(f'✓ SQLite connected! Settings count: {result.scalar()}')

asyncio.run(test())
"
```

### Check Web Service
```bash
# Local
curl http://localhost:8101/healthz

# Docker
docker-compose exec web curl http://localhost:8101/healthz
```

## Next Steps
1. Update your `.env` file with actual bot credentials
2. Start the bot using one of the options above
3. Test the bot in your Telegram group

For detailed information, see [SQLITE_MIGRATION.md](SQLITE_MIGRATION.md)
