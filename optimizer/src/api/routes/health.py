"""
GET /health — status do microserviço.
"""
from fastapi import APIRouter
from ..schemas import HealthResponse

router = APIRouter()


@router.get("/", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    return HealthResponse()
