from fastapi.testclient import TestClient

from splguard.config import settings
from splguard.web import app


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_zealy_webhook_returns_ok() -> None:
    client = TestClient(app)

    original_token = settings.zealy_webhook_token
    try:
        settings.zealy_webhook_token = "expected-token"

        response = client.post(
            "/webhooks/zealy",
            params={"token": "expected-token"},
            headers={"x-zealy-event": "quest.claimed"},
            json={"event": "quest_claimed"},
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
    finally:
        settings.zealy_webhook_token = original_token
