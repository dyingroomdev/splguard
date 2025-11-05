from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import text

from .db import AsyncSessionMaker
from .redis import get_redis_client
from .config import settings
from .services import zealy as zealy_service


def create_app() -> FastAPI:
    """Create FastAPI application that exposes basic health endpoint."""
    app = FastAPI(title="SplGuard Health")

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

    @app.post("/webhooks/zealy", tags=["webhooks"])
    async def zealy_webhook(request: Request, token: str) -> dict[str, bool]:
        expected = settings.zealy_webhook_token
        if not expected:
            raise HTTPException(status_code=503, detail="Zealy webhook token not configured")
        if token != expected:
            raise HTTPException(status_code=401, detail="Invalid token")

        event_name = request.headers.get("x-zealy-event")
        if not event_name:
            raise HTTPException(status_code=400, detail="Missing x-zealy-event header")

        try:
            payload = await request.json()
        except Exception:
            payload = {}

        handled = await zealy_service.process_event(event_name, payload)
        return {"ok": handled}

    return app


app = create_app()
