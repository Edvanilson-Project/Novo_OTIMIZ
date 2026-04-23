"""
GET /health — status do microserviço.
"""
import redis
from fastapi import APIRouter, Response, status
from ..schemas import HealthResponse
from ...core.celery_app import celery_app
from ...core.config import get_settings

router = APIRouter()
settings = get_settings()

@router.get("/", response_model=HealthResponse, tags=["system"])
async def health_check(response: Response) -> HealthResponse:
    health_data = HealthResponse(
        status="ok",
        redis_status="unknown",
        celery_status="unknown",
        active_workers=0
    )
    
    # Check Redis Connectivity & Queue Size
    try:
        r = redis.Redis.from_url(settings.redis_url, socket_timeout=1)
        r.ping()
        health_data.redis_status = "ok"
        
        # Obter tamanho da fila (default=optimizer)
        health_data.pending_tasks = r.llen("optimizer")
    except Exception:
        health_data.redis_status = "down"
        health_data.status = "error"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    # Check Celery Workers Connectivity
    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        pings = inspector.ping()
        if pings:
            health_data.celery_status = "ok"
            health_data.active_workers = len(pings)
        else:
            health_data.celery_status = "no_workers"
            health_data.status = "error"
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    except Exception:
        health_data.celery_status = "down"
        health_data.status = "error"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return health_data
