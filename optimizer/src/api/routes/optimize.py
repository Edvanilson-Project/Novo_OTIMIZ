"""
POST /optimize  — enfileira execução no Celery e retorna task_id imediatamente.
GET  /optimize/status/{task_id} — polling do resultado (NestJS chama a cada 5s).

ARQUITETURA:
  NestJS → POST /optimize/ → FastAPI valida + enfileira no Celery → retorna {task_id}
  NestJS → GET  /optimize/status/{task_id} → FastAPI consulta Redis → retorna resultado

TRATAMENTO DE ERROS (Ajuste 1):
  A task Celery NUNCA faz raise de exceções customizadas — retorna dicts estruturados
  com {"_is_error": True, "error_payload": {...}} para preservar os diagnósticos ricos
  (hints, codes, recommendations) que o frontend exibe ao utilizador.
"""
import logging
from typing import Union

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException

from ...core.exceptions import OptimizerError
from ...domain.models import VehicleType
from ...services.optimizer_tasks import run_optimization_task
from ..converters import to_trip as _to_trip
from ..schemas import (
    BlockOutput,
    DutyOutput,
    ErrorResponse,
    OptimizeRequest,
    OptimizeResponse,
    TaskStatusResponse,
    TaskSubmittedResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _to_vt(v) -> VehicleType:
    return VehicleType(
        id=v.id,
        name=v.name,
        passenger_capacity=v.passenger_capacity,
        cost_per_km=v.cost_per_km,
        cost_per_hour=v.cost_per_hour,
        fixed_cost=v.fixed_cost,
        is_electric=v.is_electric,
        battery_capacity_kwh=v.battery_capacity_kwh,
        minimum_soc=v.minimum_soc,
        charge_rate_kw=v.charge_rate_kw,
        energy_cost_per_kwh=v.energy_cost_per_kwh,
        depot_id=v.depot_id,
    )


def _build_optimize_response(raw: dict, trips_count: int) -> OptimizeResponse:
    """Constrói OptimizeResponse a partir do dict retornado pela task Celery."""
    return OptimizeResponse(
        status="ok",
        vehicles=raw["vehicles"],
        crew=raw["crew"],
        total_trips=raw.get("total_trips", trips_count),
        total_cost=raw["total_cost"],
        cct_violations=raw["cct_violations"],
        unassigned_trips=raw["unassigned_trips"],
        uncovered_blocks=raw["uncovered_blocks"],
        vsp_algorithm=raw["vsp_algorithm"],
        csp_algorithm=raw["csp_algorithm"],
        elapsed_ms=raw["elapsed_ms"],
        blocks=[
            BlockOutput(**{
                **b,
                "trips": [t["id"] if isinstance(t, dict) else t for t in b.get("trips", [])],
            })
            for b in raw["blocks"]
        ],
        duties=[DutyOutput(**d) for d in raw["duties"]],
        warnings=raw.get("warnings", []),
        cost_breakdown=raw.get("cost_breakdown") or {},
        solver_explanation=raw.get("solver_explanation") or {},
        phase_summary=raw.get("phase_summary") or {},
        trip_group_audit=raw.get("trip_group_audit") or {},
        reproducibility=raw.get("reproducibility") or {},
        performance=(raw.get("meta") or {}).get("performance") or {},
        meta=raw.get("meta") or {},
    )


# ── POST /optimize/ — Enfileira tarefa e retorna task_id imediatamente ─────────

@router.post(
    "/",
    response_model=TaskSubmittedResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["optimization"],
    summary="Enfileira otimização VSP+CSP no worker Celery",
)
async def optimize(body: OptimizeRequest) -> TaskSubmittedResponse:
    """
    Valida o payload, converte para dict JSON-safe e enfileira no Celery.
    Retorna imediatamente com {status: "processing", task_id: "..."}.
    """
    if not body.trips:
        raise HTTPException(status_code=400, detail="trips list cannot be empty")

    # Serializar para dict JSON-safe (sem objetos Pydantic — fronteira do Celery)
    payload = {
        "trips": [t.model_dump(mode="json") for t in body.trips],
        "vehicle_types": [v.model_dump(mode="json") for v in body.vehicle_types],
        "algorithm": body.algorithm.value if hasattr(body.algorithm, "value") else str(body.algorithm),
        "depot_id": body.depot_id,
        "time_budget_s": body.time_budget_s,
        "line_id": body.line_id,
        "company_id": body.company_id,
        "run_id": body.run_id,
        "cct_params": body.cct_params.model_dump(mode="json", exclude_none=True) if body.cct_params else {},
        "vsp_params": body.vsp_params.model_dump(mode="json", exclude_none=True) if body.vsp_params else {},
        "optimization_params": body.optimization_params.model_dump(mode="json", exclude_none=True) if body.optimization_params else {},
    }

    try:
        task = run_optimization_task.delay(payload)
    except Exception as exc:
        logger.exception("Falha ao enfileirar tarefa no Celery")
        raise HTTPException(
            status_code=503,
            detail=f"Fila de tarefas indisponível (Redis/Celery): {exc}",
        ) from exc

    logger.info(
        "optimization_queued: task_id=%s run_id=%s trips=%d",
        task.id,
        body.run_id,
        len(body.trips),
    )
    return TaskSubmittedResponse(status="processing", task_id=task.id)


# ── GET /optimize/status/{task_id} — Polling do resultado ──────────────────────

@router.get(
    "/status/{task_id}",
    response_model=Union[TaskStatusResponse, OptimizeResponse],
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["optimization"],
    summary="Consulta estado de uma tarefa de otimização",
)
async def get_optimization_status(task_id: str) -> TaskStatusResponse:
    """
    Consulta o estado de uma tarefa pelo task_id.

    - PENDING/STARTED/RETRY → {status: "processing"}
    - SUCCESS → {status: "completed", result: OptimizeResponse}
      (ou {status: "failed"} se a task retornou _is_error=True)
    - FAILURE → {status: "failed", error: {...}}

    O NestJS chama este endpoint a cada 5 segundos até obter "completed" ou "failed".
    """
    task_result = AsyncResult(task_id)
    state = task_result.state

    # ── Em processamento ────────────────────────────────────────────────────
    if state in ("PENDING", "STARTED", "RETRY"):
        return TaskStatusResponse(status="processing", task_id=task_id)

    # ── Concluído: verificar se é sucesso ou erro de negócio ─────────────────
    if state == "SUCCESS":
        task_return = task_result.result  # Dict retornado pela task

        # AJUSTE 1: A task pode ter retornado um erro estruturado em vez de fazer raise
        if isinstance(task_return, dict) and task_return.get("_is_error"):
            http_status = int(task_return.get("http_status", 400))
            error_payload = task_return.get("error_payload") or {}
            error_code = task_return.get("error_code", "OPTIMIZER_ERROR")
            error_message = task_return.get("error_message", "Erro no solver")

            logger.warning(
                "optimization_business_error: task_id=%s code=%s",
                task_id,
                error_code,
            )
            raise HTTPException(
                status_code=http_status,
                detail={
                    "code": error_code,
                    "message": error_message,
                    "diagnostics": error_payload,
                },
            )

        # Sucesso real: construir OptimizeResponse a partir do dict
        if isinstance(task_return, dict) and not task_return.get("_is_error"):
            raw = task_return.get("result") or task_return
            try:
                # trips_count do payload original não está disponível aqui,
                # usamos total_trips do próprio resultado
                response = _build_optimize_response(raw, raw.get("total_trips", 0))
                logger.info(
                    "optimization_completed: task_id=%s vehicles=%d crew=%d",
                    task_id,
                    response.vehicles,
                    response.crew,
                )
                return TaskStatusResponse(
                    status="completed",
                    task_id=task_id,
                    result=response,
                )
            except Exception as exc:
                logger.exception("Falha ao serializar resultado da task %s", task_id)
                raise HTTPException(
                    status_code=500,
                    detail=f"Falha ao processar resultado da otimização: {exc}",
                ) from exc

        # Formato inesperado
        raise HTTPException(
            status_code=500,
            detail=f"Formato de resultado da task inesperado: {type(task_return).__name__}",
        )

    # ── Falha do próprio Celery (crash do worker, OOM, etc.) ─────────────────
    if state == "FAILURE":
        exc_info = task_result.info  # A exceção original (se não capturada)
        error_str = str(exc_info) if exc_info else "Falha desconhecida no worker"
        logger.error("optimization_worker_failure: task_id=%s error=%s", task_id, error_str)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "WORKER_FAILURE",
                "message": f"O worker Celery falhou inesperadamente: {error_str}",
                "diagnostics": {},
            },
        )

    # ── Estado desconhecido (REVOKED, etc.) ──────────────────────────────────
    return TaskStatusResponse(status="failed", task_id=task_id, error={"state": state})
