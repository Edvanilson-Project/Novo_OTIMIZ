"""
Regressão: /health não pode bloquear o event loop e deve responder mesmo
quando Redis ou Celery estão down (com status http coerente).
"""

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    # FastAPI app lives at optimizer/main.py (not src/api/main.py)
    from main import app
    return TestClient(app)


def _patch_redis_ok():
    fake = MagicMock()
    fake.ping.return_value = True
    fake.llen.return_value = 3
    return patch("src.api.routes.health.redis.Redis.from_url", return_value=fake)


def _patch_celery_ok(n_workers: int = 2):
    fake_inspector = MagicMock()
    fake_inspector.ping.return_value = {f"w{i}": {"ok": "pong"} for i in range(n_workers)}
    return patch(
        "src.api.routes.health.celery_app.control.inspect",
        return_value=fake_inspector,
    )


def test_health_ok_when_redis_and_celery_up(client):
    with _patch_redis_ok(), _patch_celery_ok(n_workers=2):
        r = client.get("/health/")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["redis_status"] == "ok"
    assert body["celery_status"] == "ok"
    assert body["active_workers"] == 2
    assert body["pending_tasks"] == 3


def test_health_503_when_redis_down(client):
    with patch(
        "src.api.routes.health.redis.Redis.from_url",
        side_effect=Exception("redis down"),
    ), _patch_celery_ok(n_workers=1):
        r = client.get("/health/")
    assert r.status_code == 503
    body = r.json()
    assert body["redis_status"] == "down"
    assert body["status"] == "error"


def test_health_503_when_no_celery_workers(client):
    fake_inspector = MagicMock()
    fake_inspector.ping.return_value = None
    with _patch_redis_ok(), patch(
        "src.api.routes.health.celery_app.control.inspect",
        return_value=fake_inspector,
    ):
        r = client.get("/health/")
    assert r.status_code == 503
    body = r.json()
    assert body["celery_status"] == "no_workers"
    assert body["active_workers"] == 0
