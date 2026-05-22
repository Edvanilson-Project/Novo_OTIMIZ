"""
GET /health — status do microserviço.
"""

import asyncio
from typing import Optional, Tuple

import redis
from fastapi import APIRouter, Response, status
from ..schemas import HealthResponse
from ...core.celery_app import celery_app
from ...core.config import get_settings

router = APIRouter()
settings = get_settings()


def _probe_redis() -> Tuple[str, Optional[int]]:
    """Sync probe: ping + tamanho da fila optimizer."""
    r = redis.Redis.from_url(settings.redis_url, socket_timeout=1)
    r.ping()
    return "ok", r.llen("optimizer")


def _probe_celery() -> Tuple[str, int]:
    """Sync probe: conta workers ativos via inspect.ping()."""
    inspector = celery_app.control.inspect(timeout=1.0)
    pings = inspector.ping()
    if pings:
        return "ok", len(pings)
    return "no_workers", 0


@router.get("/", response_model=HealthResponse, tags=["system"])
async def health_check(response: Response) -> HealthResponse:
    health_data = HealthResponse(
        status="ok", version=settings.app_version, redis_status="unknown", celery_status="unknown", active_workers=0
    )

    # redis-py e celery.control.inspect são síncronos: isolar do event loop.
    try:
        redis_status, pending = await asyncio.to_thread(_probe_redis)
        health_data.redis_status = redis_status
        health_data.pending_tasks = pending
    except Exception:
        health_data.redis_status = "down"
        health_data.status = "error"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    try:
        celery_status, workers = await asyncio.to_thread(_probe_celery)
        health_data.celery_status = celery_status
        health_data.active_workers = workers
        if celery_status != "ok":
            health_data.status = "error"
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    except Exception:
        health_data.celery_status = "down"
        health_data.status = "error"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return health_data
