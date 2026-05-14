"""Replay & reproducibility fingerprints.

Funções puras (sem estado de serviço) usadas para:
- Gerar hash determinístico de input/parâmetros de uma rodada (`build_replay_fingerprint`).
- Derivar seed determinística a partir do input (`derive_deterministic_seed`).
- Snapshot completo de execução (`build_run_snapshot`) e snapshot resumido de reprodutibilidade
  (`build_reproducibility_snapshot`).

Extraído de optimizer_service.py (Sprint I-4) — comportamento idêntico.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Union

from ..domain.models import AlgorithmType, Trip, VehicleType


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def build_replay_fingerprint(
    trips: List[Trip],
    algorithm: Union[AlgorithmType, str],
    cct_params: Dict[str, Any],
    vsp_params: Dict[str, Any],
    time_budget_s: float,
) -> Dict[str, Any]:
    algorithm_name = str(algorithm.value if hasattr(algorithm, "value") else algorithm)
    trips_snapshot = [
        {
            "id": int(trip.id),
            "line_id": int(trip.line_id),
            "trip_group_id": int(trip.trip_group_id) if trip.trip_group_id is not None else None,
            "start_time": int(trip.start_time),
            "end_time": int(trip.end_time),
            "origin_id": int(trip.origin_id),
            "destination_id": int(trip.destination_id),
            "duration": int(trip.duration),
            "distance_km": float(trip.distance_km),
            "direction": trip.direction,
            "is_pull_out": bool(trip.is_pull_out),
            "is_pull_back": bool(trip.is_pull_back),
        }
        for trip in sorted(trips, key=lambda item: (item.id, item.start_time, item.end_time))
    ]
    params_snapshot = {
        "algorithm": algorithm_name,
        "time_budget_s": float(time_budget_s),
        "cct_params": cct_params,
        "vsp_params": vsp_params,
    }
    input_hash = hashlib.sha256(stable_json(trips_snapshot).encode("ascii")).hexdigest()[:12]
    params_hash = hashlib.sha256(stable_json(params_snapshot).encode("ascii")).hexdigest()[:12]
    return {
        "input_hash": input_hash,
        "params_hash": params_hash,
        "trip_count": len(trips_snapshot),
        "line_ids": sorted({int(trip["line_id"]) for trip in trips_snapshot}),
        "time_budget_s": float(time_budget_s),
    }


def derive_deterministic_seed(
    trips: List[Trip],
    algorithm: Union[AlgorithmType, str],
    cct_params: Dict[str, Any],
    vsp_params: Dict[str, Any],
    time_budget_s: float,
) -> int:
    algorithm_name = str(algorithm.value if hasattr(algorithm, "value") else algorithm)
    trips_snapshot = [
        {
            "id": int(trip.id),
            "line_id": int(trip.line_id),
            "trip_group_id": int(trip.trip_group_id) if trip.trip_group_id is not None else None,
            "start_time": int(trip.start_time),
            "end_time": int(trip.end_time),
            "origin_id": int(trip.origin_id),
            "destination_id": int(trip.destination_id),
            "duration": int(trip.duration),
            "distance_km": float(trip.distance_km),
            "direction": trip.direction,
        }
        for trip in sorted(trips, key=lambda item: (item.id, item.start_time, item.end_time))
    ]
    vsp_snapshot = dict(vsp_params)
    vsp_snapshot.pop("random_seed", None)
    seed_source = {
        "algorithm": algorithm_name,
        "time_budget_s": float(time_budget_s),
        "trips": trips_snapshot,
        "cct_params": cct_params,
        "vsp_params": vsp_snapshot,
    }
    seed_hex = hashlib.sha256(stable_json(seed_source).encode("ascii")).hexdigest()[:8]
    return int(seed_hex, 16)


def build_vehicle_types_hash(vehicle_types: List[VehicleType]) -> str:
    snapshot = [
        {
            "id": int(vehicle.id),
            "name": str(vehicle.name),
            "passenger_capacity": int(vehicle.passenger_capacity),
            "cost_per_km": float(vehicle.cost_per_km),
            "cost_per_hour": float(vehicle.cost_per_hour),
            "fixed_cost": float(vehicle.fixed_cost),
            "is_electric": bool(vehicle.is_electric),
            "battery_capacity_kwh": float(vehicle.battery_capacity_kwh),
            "minimum_soc": float(vehicle.minimum_soc),
            "charge_rate_kw": float(vehicle.charge_rate_kw),
            "energy_cost_per_kwh": float(vehicle.energy_cost_per_kwh),
            "depot_id": int(vehicle.depot_id) if vehicle.depot_id is not None else None,
        }
        for vehicle in sorted(vehicle_types, key=lambda item: (item.id, item.name))
    ]
    return hashlib.sha256(stable_json(snapshot).encode("ascii")).hexdigest()[:12]


def build_run_snapshot(
    trips: List[Trip],
    vehicle_types: List[VehicleType],
    algorithm: Union[AlgorithmType, str],
    submitted_cct_params: Dict[str, Any],
    submitted_vsp_params: Dict[str, Any],
    submitted_optimization_params: Dict[str, Any],
    cct_params: Dict[str, Any],
    vsp_params: Dict[str, Any],
    optimization_params: Dict[str, Any],
    time_budget_s: float,
    replay_fingerprint: Dict[str, Any],
    group_inference_report: Dict[str, Any],
    request_metadata: Any = None,
) -> Dict[str, Any]:
    metadata = dict(request_metadata or {})
    algorithm_name = str(algorithm.value if hasattr(algorithm, "value") else algorithm)
    strict_flags = {
        "strict_hard_validation": bool(
            vsp_params.get("strict_hard_validation", cct_params.get("strict_hard_validation", False))
        ),
        "strict_zero_gap_validation": bool(
            vsp_params.get("strict_zero_gap_validation", cct_params.get("strict_zero_gap_validation", False))
        ),
        "strict_operational_mode": bool(
            vsp_params.get("strict_operational_mode", cct_params.get("strict_operational_mode", False))
        ),
        "strict_hard_constraints": bool(
            vsp_params.get("strict_hard_constraints", cct_params.get("strict_hard_constraints", False))
        ),
    }
    return {
        "schema_version": "optimization_run_snapshot_v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "algorithm": algorithm_name,
        "seed": vsp_params.get("random_seed", optimization_params.get("random_seed")),
        "time_budget_s": float(time_budget_s),
        "company_id": metadata.get("company_id"),
        "scenario_id": metadata.get("scenario_id") or metadata.get("run_id"),
        "run_id": metadata.get("run_id"),
        "strict_flags": strict_flags,
        "trips_hash": replay_fingerprint.get("input_hash"),
        "vehicle_types_hash": build_vehicle_types_hash(vehicle_types),
        "trip_count": len(trips),
        "vehicle_type_count": len(vehicle_types),
        "replay_fingerprint": dict(replay_fingerprint),
        "trip_group_inference_report": group_inference_report,
        "submitted_params": {
            "cct_params": submitted_cct_params,
            "vsp_params": submitted_vsp_params,
            "optimization_params": submitted_optimization_params,
        },
        "resolved_params": {
            "cct_params": cct_params,
            "vsp_params": vsp_params,
            "optimization_params": optimization_params,
        },
        "request_metadata": metadata,
    }


_STOCHASTIC_ALGORITHMS = {
    AlgorithmType.SIMULATED_ANNEALING.value,
    AlgorithmType.TABU_SEARCH.value,
    AlgorithmType.GENETIC.value,
    AlgorithmType.HYBRID_PIPELINE.value,
}


def build_reproducibility_snapshot(
    algorithm: AlgorithmType,
    trips: List[Trip],
    cct_params: Dict[str, Any],
    vsp_params: Dict[str, Any],
    time_budget_s: float,
) -> Dict[str, Any]:
    random_seed = vsp_params.get("random_seed")
    algorithm_name = str(algorithm.value if hasattr(algorithm, "value") else algorithm)
    stochastic = algorithm_name in _STOCHASTIC_ALGORITHMS
    deterministic_replay_possible = not stochastic
    replay_fingerprint = build_replay_fingerprint(
        trips,
        algorithm,
        cct_params,
        vsp_params,
        time_budget_s,
    )
    return {
        "algorithm": algorithm_name,
        "random_seed": random_seed,
        "stochastic_algorithm": stochastic,
        "deterministic_replay_possible": deterministic_replay_possible,
        "input_hash": replay_fingerprint["input_hash"],
        "params_hash": replay_fingerprint["params_hash"],
        "time_budget_s": replay_fingerprint["time_budget_s"],
        "note": (
            "Replicável se os mesmos dados e parâmetros forem reutilizados."
            if deterministic_replay_possible
            else (
                "Seed explícita reduz a variabilidade, mas o solver usa budget por tempo; execuções equivalentes podem divergir no número de iterações e no resultado final."
                if random_seed is not None
                else "Algoritmo estocástico sem seed explícita: execuções equivalentes podem divergir mesmo com o mesmo input."
            )
        ),
    }
