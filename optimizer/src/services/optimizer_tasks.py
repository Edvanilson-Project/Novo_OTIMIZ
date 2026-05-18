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
import time
from typing import Any, Dict, List, Tuple

from ..core.celery_app import celery_app
from ..core.exceptions import OptimizerError, HardConstraintViolationError
from ..domain.models import AlgorithmType, Trip, VehicleType
from ..services.optimizer_service import OptimizerService

logger = logging.getLogger(__name__)

# Removido singleton global para evitar estado compartilhado entre tasks


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
        charger_location_ids=list(d.get("charger_location_ids") or []),
        depot_id=d.get("depot_id"),
    )


def _vehicle_type_cache_key(d: Dict[str, Any]) -> Tuple[int, Tuple[Tuple[str, str], ...]]:
    return (int(d["id"]), tuple(sorted((str(k), str(v)) for k, v in d.items())))


def _reconstruct_vehicle_types(vehicle_types_raw: List[Dict[str, Any]]) -> List[VehicleType]:
    cache: Dict[Tuple[int, Tuple[Tuple[str, str], ...]], VehicleType] = {}
    vehicle_types: List[VehicleType] = []
    for raw in vehicle_types_raw:
        key = _vehicle_type_cache_key(raw)
        vehicle_type = cache.get(key)
        if vehicle_type is None:
            vehicle_type = _reconstruct_vehicle_type(raw)
            cache[key] = vehicle_type
        vehicle_types.append(vehicle_type)
    return vehicle_types


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
    depot_ids = payload.get("depot_ids") or None
    time_budget_s = payload.get("time_budget_s")
    cct_params = payload.get("cct_params") or {}
    vsp_params = dict(payload.get("vsp_params") or {})
    optimization_params = payload.get("optimization_params") or {}
    request_metadata = payload.get("request_metadata") or {}
    algorithm_preference = payload.get("algorithm_preference")
    if algorithm_preference:
        vsp_params["algorithm_preference"] = algorithm_preference

    # Metadados para o payload de erro (se necessário)
    run_id = payload.get("run_id")
    line_id = payload.get("line_id")
    company_id = payload.get("company_id")

    # Variáveis para throttle de progress updates
    _last_update_time = 0
    UPDATE_INTERVAL = 5  # segundos

    def _update_prog(progress: float, message: str = ""):
        nonlocal _last_update_time
        task_id = getattr(getattr(self, "request", None), "id", None)
        if not task_id:
            return
        now = time.time()
        if now - _last_update_time >= UPDATE_INTERVAL or progress >= 1.0:
            self.update_state(state="PROGRESS", meta={"progress": progress, "message": message})
            _last_update_time = now

    try:
        # Reconstrução dos objetos de domínio
        trips = [_reconstruct_trip(t) for t in trips_raw]
        vehicle_types = _reconstruct_vehicle_types(vehicle_types_raw)

        # Execução do serviço de otimização
        service = OptimizerService()
        result = service.run(
            trips=trips,
            vehicle_types=vehicle_types,
            algorithm=AlgorithmType(algorithm_str),
            depot_id=depot_id,
            depot_ids=depot_ids,
            time_budget_s=time_budget_s,
            cct_params=cct_params,
            vsp_params=vsp_params,
            optimization_params=optimization_params,
            request_metadata=request_metadata,
        )
        # Usa uma representação compacta para reduzir o pico de memória e o
        # tamanho do payload no Celery/Redis. O resultado completo continua
        # disponível via `as_dict()` para testes e diagnósticos locais.
        result_dict = result.as_compact_dict()
        result_dict.setdefault("meta", {})
        result_dict["meta"].update(
            {
                "run_id": run_id,
                "line_id": line_id,
                "company_id": company_id,
            }
        )
        logger.info(
            "[OP-QUALITY] task completed run_id=%s mode=%s chosen_scenario=%s",
            run_id,
            ((result_dict.get("operational_quality_decision") or {}).get("mode"))
            or ((result_dict.get("meta") or {}).get("operational_quality_decision") or {}).get("mode")
            or (optimization_params or {}).get("operational_quality_mode")
            or "balanced",
            result_dict.get("chosen_scenario") or ((result_dict.get("meta") or {}).get("chosen_scenario")),
        )
        _update_prog(1.0, "Otimização concluída")

        return {"_is_error": False, "result": result_dict}

    except OptimizerError as e:
        logger.exception("Erro de negocio durante a execução da otimização")
        issues = list(getattr(e, "issues", []) or [])
        error_code = getattr(e, "code", "OPTIMIZER_ERROR")
        if isinstance(e, HardConstraintViolationError) and any(
            str(issue).startswith("MANDATORY_GROUP_SPLIT") for issue in issues
        ):
            error_code = "MANDATORY_GROUP_SPLIT"
        details = dict(getattr(e, "details", {}) or {})
        details.update(
            {
                "issues": issues,
                "run_id": run_id,
                "line_id": line_id,
                "company_id": company_id,
                "algorithm": algorithm_str,
            }
        )
        return {
            "_is_error": True,
            "status": "failed",
            "error_type": "business",
            "error_code": error_code,
            "message": str(e),
            "details": details,
            "error_payload": {
                "status": "failed",
                "error_type": "business",
                "error_code": error_code,
                "message": str(e),
                "details": details,
            },
            "http_status": 200,
        }

    except Exception as e:
        logger.exception("Erro durante a execução da otimização")
        return {
            "_is_error": True,
            "status": "failed",
            "error_type": "system",
            "error_code": "INTERNAL_ERROR",
            "message": str(e),
            "details": {"run_id": run_id, "algorithm": algorithm_str},
            "error_payload": {"message": str(e), "code": "INTERNAL_ERROR", "run_id": run_id},
            "http_status": 500,
        }
