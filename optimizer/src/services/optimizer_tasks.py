"""
optimizer_tasks.py — Tasks Celery para o motor de otimização VSP/CSP.

PRINCÍPIO DE TRATAMENTO DE ERROS (Ajuste 1):
O Celery, por padrão, serializa exceções customizadas no Redis apenas como strings,
perdendo os dados ricos de diagnóstico (hints, codes, recommendations) que o frontend
usa para mostrar mensagens úteis ao utilizador.

SOLUÇÃO: Em vez de fazer `raise exc`, capturamos a exceção e retornamos um dicionário
estruturado com `{"_is_error": True, "error_payload": {...}}`. O endpoint
GET /optimize/status/{task_id} interpreta este marcador e devolve um HTTP 400
com o payload completo, preservando toda a informação de diagnóstico.

SERIALIZAÇÃO:
Todos os parâmetros recebidos são dicionários JSON-safe (nenhum objeto Pydantic ou
dataclass é passado pela fronteira Celery). A reconstrução dos objetos de domínio
(Trip, VehicleType, etc.) é feita internamente nesta task.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from ..core.celery_app import celery_app
from ..core.exceptions import OptimizerError
from ..domain.models import AlgorithmType, Trip, VehicleType
from ..services.optimizer_service import OptimizerService

logger = logging.getLogger(__name__)

# Singleton do serviço — reutilizado dentro do mesmo processo worker
_service = OptimizerService()


def _reconstruct_trip(d: Dict[str, Any]) -> Trip:
    """Reconstrói um objeto Trip de domínio a partir de um dicionário JSON."""
    return Trip(
        id=int(d["id"]),
        line_id=int(d["line_id"]),
        trip_group_id=d.get("trip_group_id"),
        direction=d.get("direction"),
        start_time=int(d["start_time"]),
        end_time=int(d["end_time"]),
        origin_id=int(d["origin_id"]),
        destination_id=int(d["destination_id"]),
        duration=int(d.get("duration", 0)),
        distance_km=float(d.get("distance_km", 0.0)),
        depot_id=d.get("depot_id"),
        relief_point_id=d.get("relief_point_id"),
        is_relief_point=bool(d.get("is_relief_point", False)),
        mid_trip_relief_point_id=d.get("mid_trip_relief_point_id"),
        mid_trip_relief_offset_minutes=d.get("mid_trip_relief_offset_minutes"),
        mid_trip_relief_distance_ratio=d.get("mid_trip_relief_distance_ratio"),
        mid_trip_relief_elevation_ratio=d.get("mid_trip_relief_elevation_ratio"),
        energy_kwh=float(d.get("energy_kwh", 0.0)),
        elevation_gain_m=float(d.get("elevation_gain_m", 0.0)),
        service_day=d.get("service_day"),
        is_holiday=bool(d.get("is_holiday", False)),
        origin_latitude=d.get("origin_latitude"),
        origin_longitude=d.get("origin_longitude"),
        destination_latitude=d.get("destination_latitude"),
        destination_longitude=d.get("destination_longitude"),
        sent_to_driver_terminal=d.get("sent_to_driver_terminal"),
        gps_valid=d.get("gps_valid"),
        deadhead_times={int(k): int(v) for k, v in (d.get("deadhead_times") or {}).items()},
        idle_before_minutes=int(d.get("idle_before_minutes", 0)),
        idle_after_minutes=int(d.get("idle_after_minutes", 0)),
        is_pull_out=bool(d.get("is_pull_out", False)),
        is_pull_back=bool(d.get("is_pull_back", False)),
    )


def _reconstruct_vehicle_type(d: Dict[str, Any]) -> VehicleType:
    """Reconstrói um objeto VehicleType de domínio a partir de um dicionário JSON."""
    return VehicleType(
        id=int(d["id"]),
        name=str(d.get("name", "")),
        passenger_capacity=int(d.get("passenger_capacity", 40)),
        cost_per_km=float(d.get("cost_per_km", 0.0)),
        cost_per_hour=float(d.get("cost_per_hour", 0.0)),
        fixed_cost=float(d.get("fixed_cost", 800.0)),
        is_electric=bool(d.get("is_electric", False)),
        battery_capacity_kwh=float(d.get("battery_capacity_kwh", 0.0)),
        minimum_soc=float(d.get("minimum_soc", 0.15)),
        charge_rate_kw=float(d.get("charge_rate_kw", 0.0)),
        energy_cost_per_kwh=float(d.get("energy_cost_per_kwh", 0.0)),
        depot_id=d.get("depot_id"),
    )


@celery_app.task(bind=True, name="run_optimization")
def run_optimization_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Task Celery principal: executa o pipeline VSP+CSP completo.

    Recebe um payload dict JSON-safe (sem objetos Pydantic) e retorna
    ou o resultado como dicionário, ou um marcador de erro estruturado.

    Retorno em caso de SUCESSO:
        {"_is_error": False, "result": {...}}  (dict completo do OptimizationResult)

    Retorno em caso de ERRO DE NEGÓCIO (HardConstraintViolationError, etc.):
        {"_is_error": True, "error_payload": {...}, "http_status": 400}

    Retorno em caso de ERRO INESPERADO:
        {"_is_error": True, "error_payload": {...}, "http_status": 500}

    NUNCA faz `raise` de exceções customizadas — preserva os dados ricos de diagnóstico.
    """
    trips_raw: List[Dict[str, Any]] = payload.get("trips", [])
    vehicle_types_raw: List[Dict[str, Any]] = payload.get("vehicle_types", [])
    algorithm_str: str = payload.get("algorithm", "hybrid_pipeline")
    depot_id = payload.get("depot_id")
    time_budget_s = payload.get("time_budget_s")
    cct_params = payload.get("cct_params") or {}
    vsp_params = payload.get("vsp_params") or {}
    optimization_params = payload.get("optimization_params") or {}

    # Metadados para o payload de erro (se necessário)
    run_id = payload.get("run_id")
    line_id = payload.get("line_id")
    company_id = payload.get("company_id")

    try:
        # Reconstruir objetos de domínio a partir dos dicts JSON
        trips = [_reconstruct_trip(t) for t in trips_raw]
        vehicle_types = [_reconstruct_vehicle_type(v) for v in vehicle_types_raw]

        # Mapear string do algoritmo para AlgorithmType enum
        try:
            algorithm = AlgorithmType(algorithm_str)
        except ValueError:
            algorithm = AlgorithmType.HYBRID_PIPELINE
            logger.warning(
                "[CeleryTask] Algoritmo desconhecido '%s', usando hybrid_pipeline.",
                algorithm_str,
            )

        logger.info(
            "[CeleryTask] Iniciando run_id=%s, trips=%d, algorithm=%s",
            run_id,
            len(trips),
            algorithm_str,
        )

        # ── Execução do pipeline matemático (NUNCA alterado) ────────────────
        result = _service.run(
            trips=trips,
            vehicle_types=vehicle_types,
            algorithm=algorithm,
            depot_id=depot_id,
            time_budget_s=time_budget_s,
            cct_params=cct_params,
            vsp_params=vsp_params,
            optimization_params=optimization_params,
        )

        raw = result.as_dict()

        # Enriquecer com metadados da requisição original
        meta = raw.get("meta") or {}
        meta.update({"run_id": run_id, "line_id": line_id, "company_id": company_id})
        raw["meta"] = meta

        logger.info(
            "[CeleryTask] Concluído run_id=%s: %d veículos, %d tripulantes, custo=%.2f",
            run_id,
            raw.get("vehicles", 0),
            raw.get("crew", 0),
            raw.get("total_cost", 0.0),
        )

        return {"_is_error": False, "result": raw}

    except OptimizerError as exc:
        # ── AJUSTE 1: Erro de negócio rico (HardConstraintViolationError, etc.) ──
        # Em vez de fazer raise (que o Celery serializa apenas como string),
        # extraímos o payload completo de diagnóstico e retornamos como dict.
        logger.warning("[CeleryTask] OptimizerError no run_id=%s: %s", run_id, exc)
        try:
            trips_for_payload = [_reconstruct_trip(t) for t in trips_raw]
        except Exception:
            trips_for_payload = []

        error_payload = exc.details or _service.build_failure_payload(
            exc=exc,
            trips=trips_for_payload,
            algorithm=algorithm_str,
            cct_params=cct_params,
            vsp_params=vsp_params,
            stage="celery_worker",
        )
        return {
            "_is_error": True,
            "http_status": 400,
            "error_code": getattr(exc, "code", exc.__class__.__name__),
            "error_message": str(exc),
            "error_payload": error_payload,
        }

    except Exception as exc:
        # ── Erro inesperado (bug, out-of-memory, etc.) ───────────────────────
        logger.exception("[CeleryTask] Erro inesperado no run_id=%s", run_id)
        return {
            "_is_error": True,
            "http_status": 500,
            "error_code": exc.__class__.__name__,
            "error_message": str(exc),
            "error_payload": {
                "code": exc.__class__.__name__,
                "message": str(exc),
                "kind": "internal_error",
                "stage": "celery_worker",
            },
        }
