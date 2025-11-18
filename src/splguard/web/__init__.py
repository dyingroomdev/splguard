from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import text

from ..db import AsyncSessionMaker
from ..redis import get_redis_client
from .broadcast import router as broadcast_router


def create_app() -> FastAPI:
    """Create FastAPI application that exposes health, webhooks, and broadcast UI."""
    app = FastAPI(title="SplGuard API")

    @app.get("/healthz", tags=["health"])
    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    async def readiness_check() -> dict[str, bool | str]:
        db_ok = True
        redis_status: bool | str = True

        async with AsyncSessionMaker() as session:
            try:
                await session.execute(text("SELECT 1"))
            except Exception:  # pragma: no cover
                db_ok = False

        client = get_redis_client()
        if client is None:
            redis_status = "disabled"
        else:
            try:
                await client.ping()
            except Exception:  # pragma: no cover
                redis_status = False
            finally:
                await client.close()

        redis_ready = redis_status is True or redis_status == "disabled"

        return {
            "status": "ok" if (db_ok and redis_ready) else "degraded",
            "db": db_ok,
            "redis": redis_status,
        }

    app.include_router(broadcast_router)

    return app


app = create_app()
