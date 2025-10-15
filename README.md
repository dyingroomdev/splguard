# SplGuard

Skeleton for a Telegram moderation bot built with aiogram v3, FastAPI, SQLAlchemy, and Redis.

## Quickstart

1. Copy `.env.example` to `.env` and fill in your credentials.
2. Create a virtual environment and install dependencies with `make dev`.
3. Run the bot locally using `splguard-bot` or `python -m splguard`.
4. Optional: start the FastAPI health server with `uvicorn splguard.web:app --reload`.

## Environment Variables

| Variable      | Description                                |
| ------------- | ------------------------------------------ |
| `BOT_TOKEN`   | Telegram bot token from BotFather.         |
| `DATABASE_URL`| PostgreSQL DSN (e.g. `postgresql+asyncpg://`). |
| `REDIS_URL`   | Redis connection URL.                      |
| `OWNER_ID`    | Telegram user ID of the bot owner.         |
| `ADMIN_CHANNEL_ID` | Channel/chat ID for moderation audit logs. |
| `ADMIN_IDS` | Comma-separated list of Telegram user IDs allowed to run admin commands. |
| `SENTRY_DSN` | Optional Sentry DSN for error tracking. |
| `PRESALE_API_URL` | Optional external endpoint for presale stats. |
| `PRESALE_REFRESH_SECONDS` | Background poll interval (default 60). |

## Make Targets

- `make dev` — create `.venv` and install dependencies.
- `make test` — run pytest suite.
- `make fmt` — format and lint with Ruff.

## Docker

Build and launch the stack with Docker Compose:

```bash
docker-compose up --build
```

This starts the bot, FastAPI health endpoint, PostgreSQL, and Redis services.
Make sure the external Docker network `pg-network` exists (create it once with `docker network create pg-network`).

## Database & migrations

- Run migrations with `alembic upgrade head` (ensure `DATABASE_URL` is set).
- Generate a new migration after model changes via `alembic revision --autogenerate -m "message"`.
- Seed default SPL Shield settings and team entries with `python -m splguard.seed`.
