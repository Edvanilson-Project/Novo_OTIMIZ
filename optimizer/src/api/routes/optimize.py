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
import hashlib
import json
import logging
import time
from typing import Union

import redis.asyncio as aioredis
from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException

from ...core.config import get_settings
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
    AiChatRequest,
    AiChatResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()
CACHE_VERSION = "v2.0"

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
    meta = dict(raw.get("meta") or {})
    reproducibility = raw.get("reproducibility") or meta.get("reproducibility") or {}
    performance = raw.get("performance") or meta.get("performance") or {}
    meta.setdefault("reproducibility", reproducibility)
    meta.setdefault("performance", performance)
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
        operational_time_reports=raw.get("operational_time_reports") or meta.get("operational_time_reports") or {},
        reproducibility=reproducibility,
        performance=performance,
        parameter_effect_report=raw.get("parameter_effect_report") or meta.get("parameter_effect_report") or {},
        chosen_scenario=raw.get("chosen_scenario") or meta.get("chosen_scenario"),
        rejected_scenarios=raw.get("rejected_scenarios") or meta.get("rejected_scenarios") or [],
        justification=raw.get("justification") or meta.get("justification") or [],
        trade_offs=raw.get("trade_offs") or meta.get("trade_offs") or [],
        operational_quality_decision=raw.get("operational_quality_decision") or meta.get("operational_quality_decision") or {},
        meta=meta,
    )


# ── POST /optimize/ — Enfileira tarefa e retorna task_id imediatamente ─────────

@router.post(
    "/",
    response_model=Union[TaskSubmittedResponse, OptimizeResponse],
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["optimization"],
    summary="Enfileira otimização VSP+CSP no worker Celery",
)
async def optimize(body: OptimizeRequest) -> Union[TaskSubmittedResponse, OptimizeResponse]:
    """
    Valida o payload, verifica se há cache da execução (Smart Caching de 12 horas)
    e enfileira no Celery caso seja um cenário inédito.
    """
    if not body.trips:
        raise HTTPException(status_code=400, detail="trips list cannot be empty")

    # Validação básica dos parâmetros
    if not isinstance(body.trips, list) or len(body.trips) == 0:
        raise HTTPException(status_code=400, detail="Lista de viagens inválida ou vazia")
    
    if not isinstance(body.vehicle_types, list) or len(body.vehicle_types) == 0:
        raise HTTPException(status_code=400, detail="Lista de tipos de veículo inválida ou vazia")
    
    if body.time_budget_s is not None and (body.time_budget_s <= 0 or body.time_budget_s > 3600):
        raise HTTPException(status_code=400, detail="time_budget_s deve estar entre 1 e 3600 segundos")

    # Construir payload com validação adicional
    try:
        payload = {
            "trips": [t.model_dump(mode="json") for t in body.trips],
            "vehicle_types": [v.model_dump(mode="json") for v in body.vehicle_types],
            "algorithm": body.algorithm.value if hasattr(body.algorithm, "value") else str(body.algorithm),
            "depot_id": body.depot_id,
            "time_budget_s": body.time_budget_s,
            "line_id": body.line_id,
            "company_id": body.company_id,
            "run_id": body.run_id,
            "cct_params": body.cct_params.model_dump(mode="json", exclude_none=True, exclude_unset=True) if body.cct_params else {},
            "vsp_params": body.vsp_params.model_dump(mode="json", exclude_none=True, exclude_unset=True) if body.vsp_params else {},
            "optimization_params": body.optimization_params.model_dump(mode="json", exclude_none=True, exclude_unset=True) if body.optimization_params else {},
            "request_metadata": body.request_metadata or {},
            "algorithm_preference": body.algorithm_preference,
            "version": CACHE_VERSION,
        }
    except Exception as e:
        logger.error(f"Erro ao construir payload: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Erro ao processar parâmetros: {str(e)}")

    if body.wait_for_completion:
        try:
            # Execução síncrona direta (ignora fila Celery/Redis para resposta imediata)
            # Útil para testes, depuração e cenários de 'what-if' ultra-rápidos
            result_raw = run_optimization_task(payload)

            if isinstance(result_raw, dict) and result_raw.get("_is_error"):
                err = result_raw.get("error_payload", {})
                raise HTTPException(status_code=400, detail=err.get("message", "Erro na execução da otimização"))

            final_result = result_raw.get("result", result_raw)
            return _build_optimize_response(final_result, len(body.trips))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erro na execução síncrona: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Erro ao processar otimização síncrona: {str(e)}")

    # Calcula Fingerprint Determinístico para o Smart Cache com versionamento
    try:
        cache_payload = {
            **payload,
            "cache_version": CACHE_VERSION,
            "cache_bucket_hour": int(time.time() // 3600),
        }
        payload_str = json.dumps(cache_payload, sort_keys=True)
        fingerprint = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        cache_key = f"optimizer:cache:{CACHE_VERSION}:{fingerprint}"
    except Exception as e:
        logger.error(f"Erro ao calcular fingerprint do cache: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno ao processar requisição: {str(e)}"
        )

    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    try:
        cached_task_id = await redis_client.get(cache_key)
        if cached_task_id:
            # Verificar estado da task com segurança (evita erro se backend estiver desabilitado)
            task_state = "UNKNOWN"
            try:
                task_state = AsyncResult(cached_task_id).state
            except Exception as e:
                logger.warning(f"Não foi possível verificar estado da task {cached_task_id}: {str(e)}")

            task_timestamp = await redis_client.get(f"optimizer:task_timestamp:{cached_task_id}")
            
            # Validação adicional: garantir que a task não é muito antiga
            if task_timestamp and int(time.time()) - int(task_timestamp) > 43200:  # 12 horas
                logger.info(f"Cache expirado para task {cached_task_id}")
                await redis_client.delete(cache_key)
            elif task_state in ("PENDING", "STARTED", "SUCCESS"):
                logger.info(
                    "optimization_cache_hit: task_id=%s fingerprint=%s state=%s",
                    cached_task_id, fingerprint, task_state
                )
                await redis_client.aclose()
                return TaskSubmittedResponse(status="processing", task_id=cached_task_id)
    except Exception as exc:
        logger.error(f"Falha ao ler cache do Redis: {str(exc)}", exc_info=True)
        # Continuar sem cache em caso de erro

    try:
        task = run_optimization_task.delay(payload)
        try:
            # Retenção do cache por 12 horas (43200s) com timestamp
            await redis_client.setex(cache_key, 43200, task.id)
            await redis_client.setex(
                f"optimizer:task_timestamp:{task.id}", 
                43200, 
                int(time.time())
            )
        except Exception as exc:
            logger.error(f"Falha ao salvar cache no Redis: {str(exc)}", exc_info=True)
            # Continuar sem cache em caso de erro
    except Exception as exc:
        logger.exception("Falha ao enfileirar tarefa no Celery")
        await redis_client.aclose()
        raise HTTPException(
            status_code=503,
            detail=f"Fila de tarefas indisponível (Redis/Celery): {exc}",
        ) from exc

    await redis_client.aclose()
    
    logger.info(
        "optimization_queued: task_id=%s run_id=%s trips=%d",
        task.id,
        body.run_id,
        len(body.trips),
    )
    return TaskSubmittedResponse(status="processing", task_id=task.id)


# ── POST /optimize/chat — Chat interativo com a IA ────────────────────────────

@router.post(
    "/chat",
    response_model=AiChatResponse,
    tags=["optimization"],
    summary="Chat interativo com o Copiloto de IA",
)
async def chat_with_ai(body: AiChatRequest) -> AiChatResponse:
    """
    Recebe as métricas da otimização e a pergunta do usuário.
    Retorna a resposta gerada pela IA (DeepSeek/Llama/fallback).
    """
    from ...services.ai_service import AiService
    service = AiService()
    
    answer = await service.chat_async(body.metrics, body.question)
    
    return AiChatResponse(
        answer=answer,
        status="ok" if answer else "error"
    )


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

    # ── Em processamento (inclui PROGRESS com fases do pipeline) ────────────
    if state in ("PENDING", "STARTED", "RETRY", "PROGRESS"):
        progress_meta = {}
        if state == "PROGRESS" and isinstance(task_result.info, dict):
            progress_meta = {
                "phase": task_result.info.get("phase", "processing"),
                "phase_label": task_result.info.get("phase_label", "Processando..."),
                "progress_pct": task_result.info.get("progress_pct", 0),
            }
        return TaskStatusResponse(status="processing", task_id=task_id, **progress_meta)

    # ── Concluído: verificar se é sucesso ou erro de negócio ─────────────────
    if state == "SUCCESS":
        task_return = task_result.result  # Dict retornado pela task

        # AJUSTE 1: A task pode ter retornado um erro estruturado em vez de fazer raise
        if isinstance(task_return, dict) and task_return.get("_is_error"):
            error_payload = task_return.get("error_payload") or {}
            error_code = task_return.get("error_code", "OPTIMIZER_ERROR")
            error_message = task_return.get("message") or task_return.get("error_message") or error_payload.get("message") or "Erro no solver"
            error_type = task_return.get("error_type", error_payload.get("error_type", "system"))
            details = task_return.get("details", error_payload.get("details", error_payload))

            logger.warning(
                "optimization_task_failed: task_id=%s type=%s code=%s",
                task_id, error_type, error_code,
            )
            return TaskStatusResponse(
                status="failed",
                task_id=task_id,
                error_type=error_type,
                error_code=error_code,
                message=error_message,
                details=details,
                error={
                    "error_type": error_type,
                    "error_code": error_code,
                    "message": error_message,
                    "details": details,
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
