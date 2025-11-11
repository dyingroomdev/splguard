# SQLite Migration Guide

This guide explains how to run SplGuard with SQLite instead of PostgreSQL.

## Changes Made

### 1. Dependencies Updated
- **Removed**: `asyncpg` (PostgreSQL driver)
- **Added**: `aiosqlite` (SQLite async driver)

Updated in [pyproject.toml](pyproject.toml#L17)

### 2. Docker Configuration Updated
The [docker-compose.yml](docker-compose.yml) has been updated to:
- Remove PostgreSQL network dependency (`pg-network`)
- Add volume mounts for SQLite database file
- Both `bot` and `web` services now mount `./splguard.db:/app/splguard.db`

### 3. Database Configuration
The `.env` file is already configured for SQLite:
```bash
DATABASE_URL=sqlite+aiosqlite:///./splguard.db
```

## Running Locally (Development)

### 1. Ensure Virtual Environment is Set Up
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .[dev]
```

Or use the Makefile:
```bash
make dev
```

### 2. Configure Environment Variables
Your `.env` file should contain:
```bash
BOT_TOKEN=your_bot_token_here
DATABASE_URL=sqlite+aiosqlite:///./splguard.db
REDIS_URL=  # Leave empty to disable Redis
OWNER_ID=your_telegram_user_id
ADMIN_CHANNEL_ID=your_channel_id
ADMIN_IDS="user_id_1,user_id_2"
```

### 3. Run Database Migrations
```bash
.venv/bin/python -m alembic upgrade head
```

### 4. Run the Bot
```bash
.venv/bin/python -m splguard.main
```

Or using the installed command:
```bash
.venv/bin/splguard-bot
```

## Running with Docker

### 1. Build the Docker Images
```bash
docker-compose build
```

### 2. Start the Services
```bash
docker-compose up -d
```

### 3. Check Logs
```bash
# Bot logs
docker-compose logs -f bot

# Web service logs
docker-compose logs -f web

# All logs
docker-compose logs -f
```

### 4. Run Migrations in Docker
If you need to run migrations inside the container:
```bash
docker-compose exec bot python -m alembic upgrade head
```

## Important Notes

### SQLite File Location
- **Local development**: `./splguard.db` (current directory)
- **Docker**: `/app/splguard.db` (mounted from host `./splguard.db`)

### Database Backup
Since you're using SQLite, backing up is simple:
```bash
# Backup
cp splguard.db splguard.db.backup

# Or with timestamp
cp splguard.db "splguard_backup_$(date +%Y%m%d_%H%M%S).db"
```

### Concurrent Access
SQLite has limitations with concurrent writes. For production use with high traffic:
- Consider using PostgreSQL instead
- Or ensure only one bot instance is running
- The current setup with `bot` and `web` services sharing the same SQLite file should work fine for moderate traffic

### Database Persistence
The SQLite database file is stored on your host machine, so data persists even if containers are removed.

## Troubleshooting

### "Database is locked" errors
This can happen if multiple processes try to write simultaneously:
1. Ensure only one bot instance is running
2. Check if any migrations are running
3. Restart the services: `docker-compose restart`

### Missing `aiosqlite` module
```bash
# In virtual environment
pip install aiosqlite

# Or reinstall all dependencies
pip install -e .
```

### Database schema issues
Reset and recreate the database:
```bash
# Backup first!
cp splguard.db splguard.db.backup

# Remove database
rm splguard.db

# Run migrations
.venv/bin/python -m alembic upgrade head
```

## Migration from PostgreSQL

If you have existing data in PostgreSQL and want to migrate to SQLite:

### Option 1: Fresh Start (Recommended for development)
1. Backup any important data from PostgreSQL
2. Delete the SQLite database file: `rm splguard.db`
3. Run migrations: `.venv/bin/python -m alembic upgrade head`
4. Reconfigure your bot settings through the admin commands

### Option 2: Export/Import Data
1. Export data from PostgreSQL:
```bash
pg_dump -h your_host -U your_user -d your_db --data-only --inserts > data.sql
```

2. Convert PostgreSQL SQL to SQLite-compatible format (manual editing required)
3. Import into SQLite:
```bash
sqlite3 splguard.db < data_converted.sql
```

Note: This requires manual SQL conversion and is error-prone. Option 1 is recommended.

## Health Checks

### Local
```bash
# Check if bot is running
ps aux | grep splguard-bot

# Test web service
curl http://localhost:8105/healthz
curl http://localhost:8105/readyz
```

### Docker
```bash
# Check service health
docker-compose ps

# Manual health check
docker-compose exec web curl http://localhost:8105/healthz
```

## Redis Configuration

Redis is optional but recommended for:
- Rate limiting
- Strike tracking with TTL
- User probation caching

To enable Redis:
1. Ensure Redis container is running: `docker-compose up -d redis`
2. Update `.env`: `REDIS_URL=redis://localhost:56379/0`
3. For Docker: `REDIS_URL=redis://redis:6379/0`

To disable Redis:
1. Set `REDIS_URL=` (empty) in `.env`
2. The bot will fall back to database-only operations
