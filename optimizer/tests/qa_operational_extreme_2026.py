#!/usr/bin/env python3
"""
QA Operacional Extremo 2026 — OTIMIZ

Foco:
- validar coerência dos modelos matemáticos do VSP/CSP
- estressar pricing/set covering/goal weights
- procurar erros operacionais fora do padrão
- exercitar cenário multi-linha com EV, depósito, deadhead e atrasos em cascata

Uso:
  cd /home/edvanilson/WEB_OPT/optimizer
  /home/edvanilson/WEB_OPT/.venv/bin/python tests/qa_operational_extreme_2026.py
"""
from __future__ import annotations

import argparse
import math
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

ROOT = __import__('pathlib').Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.domain.models import AlgorithmType, Trip, VehicleType
from src.services.optimizer_service import OptimizerService
from src.algorithms.vsp.greedy import build_preferred_pairs
from src.core.exceptions import HardConstraintViolationError

OK = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m!\033[0m"

LINE_TERMINALS: Dict[int, Tuple[int, int]] = {
    815: (101, 102),
    819: (201, 202),
    820: (301, 302),
    826: (401, 402),
    869: (501, 502),
    872: (601, 602),
    873: (701, 702),
}
LINE_DEPOT: Dict[int, int] = {
    815: 1,
    819: 1,
    820: 1,
    826: 2,
    869: 1,
    872: 2,
    873: 2,
}


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    elapsed_s: float = 0.0


@dataclass(frozen=True)
class QAModeConfig:
    name: str
    strict_cycles: int
    setcover_cycles: int
    ev_cycles: int
    cascade_cycles: int
    cost_cycles: int
    pair_cycles: int
    bruteforce_seeds: int
    include_bruteforce: bool
    vsp_tuning: Dict[str, int]


QA_MODES: Dict[str, QAModeConfig] = {
    "smoke": QAModeConfig(
        name="smoke",
        strict_cycles=6,
        setcover_cycles=5,
        ev_cycles=4,
        cascade_cycles=5,
        cost_cycles=4,
        pair_cycles=4,
        bruteforce_seeds=0,
        include_bruteforce=False,
        vsp_tuning={
            "max_candidate_successors_per_task": 4,
            "max_generated_columns": 1200,
            "max_pricing_iterations": 0,
            "max_pricing_additions": 128,
        },
    ),
    "heavy": QAModeConfig(
        name="heavy",
        strict_cycles=10,
        setcover_cycles=8,
        ev_cycles=8,
        cascade_cycles=7,
        cost_cycles=6,
        pair_cycles=6,
        bruteforce_seeds=0,
        include_bruteforce=False,
        vsp_tuning={
            "max_candidate_successors_per_task": 5,
            "max_generated_columns": 2500,
            "max_pricing_iterations": 1,
            "max_pricing_additions": 192,
        },
    ),
    "bruteforce": QAModeConfig(
        name="bruteforce",
        strict_cycles=12,
        setcover_cycles=10,
        ev_cycles=8,
        cascade_cycles=8,
        cost_cycles=7,
        pair_cycles=8,
        bruteforce_seeds=8,
        include_bruteforce=True,
        vsp_tuning={
            "max_candidate_successors_per_task": 6,
            "max_generated_columns": 3200,
            "max_pricing_iterations": 1,
            "max_pricing_additions": 256,
        },
    ),
}


def get_mode() -> QAModeConfig:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mode", choices=sorted(QA_MODES.keys()), default=os.getenv("OTIMIZ_QA_MODE", "heavy"))
    args, _ = parser.parse_known_args()
    return QA_MODES[args.mode]


MODE = get_mode()


def tuned_vsp(extra: Dict | None = None) -> Dict:
    base = dict(MODE.vsp_tuning)
    if extra:
        base.update(extra)
    return base


def hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def print_result(result: CheckResult) -> None:
    symbol = OK if result.ok else FAIL
    extra = f" [{result.elapsed_s:.2f}s]" if result.elapsed_s else ""
    print(f"{symbol} {result.name}{extra} — {result.detail}")


def build_dataset(cycles_per_line: int = 16, include_ev: bool = False, seed: int = 2026) -> List[Trip]:
    rnd = random.Random(seed)
    trips: List[Trip] = []
    trip_id = 1
    for line_id, (origin_a, origin_b) in LINE_TERMINALS.items():
        base_start = 4 * 60 + rnd.randint(0, 30)
        duration = 48 + (line_id % 5) * 4
        headway = max(28, duration // 2)
        for cycle in range(cycles_per_line):
            out_start = base_start + cycle * headway
            ret_start = out_start + duration + 10 + rnd.randint(0, 6)
            elevation = 30.0 + (cycle % 4) * 12.0
            energy = 18.0 + (line_id % 4) * 1.8 if include_ev else 0.0
            shared = {
                origin_b: 8,
                origin_a: 8,
            }
            trips.append(
                Trip(
                    id=trip_id,
                    line_id=line_id,
                    start_time=out_start,
                    end_time=out_start + duration,
                    origin_id=origin_a,
                    destination_id=origin_b,
                    distance_km=22 + (line_id % 7),
                    depot_id=LINE_DEPOT[line_id],
                    energy_kwh=energy,
                    elevation_gain_m=elevation,
                    deadhead_times=shared,
                )
            )
            trip_id += 1
            trips.append(
                Trip(
                    id=trip_id,
                    line_id=line_id,
                    start_time=ret_start,
                    end_time=ret_start + duration,
                    origin_id=origin_b,
                    destination_id=origin_a,
                    distance_km=22 + (line_id % 7),
                    depot_id=LINE_DEPOT[line_id],
                    energy_kwh=energy * 0.95,
                    elevation_gain_m=elevation * 0.8,
                    deadhead_times=shared,
                )
            )
            trip_id += 1
    return sorted(trips, key=lambda t: (t.start_time, t.line_id, t.id))


def perturb_delays(trips: Sequence[Trip], delay_trip_ids: Iterable[int], delay_minutes: int) -> List[Trip]:
    chosen = set(delay_trip_ids)
    delayed: List[Trip] = []
    for trip in trips:
        shift = delay_minutes if trip.id in chosen else 0
        delayed.append(
            Trip(
                id=trip.id,
                line_id=trip.line_id,
                start_time=trip.start_time + shift,
                end_time=trip.end_time + shift,
                origin_id=trip.origin_id,
                destination_id=trip.destination_id,
                duration=trip.duration,
                distance_km=trip.distance_km,
                depot_id=trip.depot_id,
                relief_point_id=trip.relief_point_id,
                is_relief_point=trip.is_relief_point,
                energy_kwh=trip.energy_kwh,
                elevation_gain_m=trip.elevation_gain_m,
                service_day=trip.service_day,
                is_holiday=trip.is_holiday,
                deadhead_times=dict(trip.deadhead_times),
            )
        )
    return sorted(delayed, key=lambda t: (t.start_time, t.line_id, t.id))


def build_pair_pressure_dataset(cycles_per_line: int = 10, seed: int = 404) -> List[Trip]:
    rnd = random.Random(seed)
    line_defs = {
        911: (901, 902, 1),
        912: (903, 904, 1),
        913: (905, 906, 2),
    }
    trips: List[Trip] = []
    trip_id = 1
    for line_id, (origin_a, origin_b, depot_id) in line_defs.items():
        base_start = 5 * 60 + rnd.randint(0, 10)
        for cycle in range(cycles_per_line):
            anchor = base_start + cycle * 70
            duration = 28 + (cycle % 2) * 2
            outbound_1 = anchor
            outbound_2 = anchor + 10
            return_1 = anchor + 44
            return_2 = anchor + 54
            for start, origin, dest in (
                (outbound_1, origin_a, origin_b),
                (outbound_2, origin_a, origin_b),
                (return_1, origin_b, origin_a),
                (return_2, origin_b, origin_a),
            ):
                trips.append(
                    Trip(
                        id=trip_id,
                        line_id=line_id,
                        start_time=start,
                        end_time=start + duration,
                        origin_id=origin,
                        destination_id=dest,
                        duration=duration,
                        distance_km=12.0,
                        depot_id=depot_id,
                        deadhead_times={origin_a: 8, origin_b: 8},
                    )
                )
                trip_id += 1
    return sorted(trips, key=lambda t: (t.start_time, t.line_id, t.id))


def audit_vsp(blocks, min_layover: int, same_depot: bool = False) -> List[str]:
    issues: List[str] = []
    for block in blocks:
        trips = list(block.trips)
        for idx in range(len(trips) - 1):
            cur, nxt = trips[idx], trips[idx + 1]
            gap = nxt.start_time - cur.end_time
            need = cur.deadhead_times.get(nxt.origin_id, min_layover if cur.destination_id == nxt.origin_id else 999999)
            if gap < 0:
                issues.append(f"OVERLAP B{block.id}: T{cur.id}->{nxt.id} gap={gap}")
            if gap < need:
                issues.append(f"DEADHEAD B{block.id}: T{cur.id}->{nxt.id} gap={gap}<need={need}")
        if same_depot:
            start_depot = trips[0].depot_id if trips else None
            end_depot = trips[-1].depot_id if trips else None
            if start_depot is not None and end_depot is not None and start_depot != end_depot:
                issues.append(f"DEPOT B{block.id}: {start_depot}!={end_depot}")
    return issues


def audit_csp(duties, max_shift: int) -> List[str]:
    issues: List[str] = []
    for duty in duties:
        if duty.spread_time > max_shift:
            issues.append(f"SPREAD P{duty.id}: {duty.spread_time}>{max_shift}")
        if duty.rest_violations > 0:
            issues.append(f"REST P{duty.id}: {duty.rest_violations}")
        if duty.shift_violations > 0:
            issues.append(f"SHIFT P{duty.id}: {duty.shift_violations}")
    return issues


def audit_preferred_pairing(blocks, trips: Sequence[Trip], min_layover: int, max_pair_window: int = 120) -> Tuple[List[str], Dict[str, int]]:
    preferred_pairs = build_preferred_pairs(list(trips), min_layover, max_pair_window)
    unique_pairs = {
        tuple(sorted((trip_id, pair_id)))
        for trip_id, pair_id in preferred_pairs.items()
        if trip_id < pair_id
    }
    consecutive_pairs = {
        tuple(sorted((block.trips[index].id, block.trips[index + 1].id)))
        for block in blocks
        for index in range(len(block.trips) - 1)
        if preferred_pairs.get(block.trips[index].id) == block.trips[index + 1].id
    }
    issues = [f"PAIR_BREAK {a}->{b}" for a, b in sorted(unique_pairs - consecutive_pairs)]
    return issues, {
        "preferred_pair_count": len(unique_pairs),
        "paired_connections_followed": len(unique_pairs & consecutive_pairs),
        "preferred_pair_breaks": len(unique_pairs - consecutive_pairs),
    }


def audit_operator_pairing(duties, trips: Sequence[Trip], min_layover: int, max_pair_window: int = 120) -> List[str]:
    preferred_pairs = build_preferred_pairs(list(trips), min_layover, max_pair_window)
    duty_by_trip: Dict[int, int] = {}
    for duty in duties:
        for task in getattr(duty, "tasks", []):
            for trip in task.trips:
                duty_by_trip[trip.id] = duty.id
    issues: List[str] = []
    seen: set[Tuple[int, int]] = set()
    for trip_id, pair_id in preferred_pairs.items():
        signature = tuple(sorted((trip_id, pair_id)))
        if signature in seen:
            continue
        seen.add(signature)
        if duty_by_trip.get(trip_id) != duty_by_trip.get(pair_id):
            issues.append(f"DUTY_PAIR_SPLIT {trip_id}->{pair_id}")
    return issues


def run_service(
    *,
    trips: List[Trip],
    algorithm: AlgorithmType,
    vehicle_types: List[VehicleType],
    cct_params: Dict,
    vsp_params: Dict,
):
    svc = OptimizerService()
    t0 = time.perf_counter()
    result = svc.run(
        trips=trips,
        vehicle_types=vehicle_types,
        algorithm=algorithm,
        cct_params=cct_params,
        vsp_params=vsp_params,
    )
    elapsed = time.perf_counter() - t0
    return result, elapsed


def scenario_hybrid_multiline_strict() -> CheckResult:
    trips = build_dataset(cycles_per_line=MODE.strict_cycles, include_ev=False)
    cct = {
        "apply_cct": True,
        "max_shift_minutes": 480,
        "max_work_minutes": 420,
        "max_driving_minutes": 240,
        "min_break_minutes": 30,
        "min_layover_minutes": 10,
        "pullout_minutes": 10,
        "pullback_minutes": 10,
        "mandatory_break_after_minutes": 240,
        "meal_break_minutes": 30,
        "daily_driving_limit_minutes": 480,
        "weekly_driving_limit_minutes": 3360,
        "fortnight_driving_limit_minutes": 5400,
        "enforce_same_depot_start_end": True,
    }
    vsp = tuned_vsp({
        "same_depot_required": True,
        "pricing_enabled": True,
        "use_set_covering": True,
        "min_workpiece_minutes": 120,
        "max_workpiece_minutes": 420,
        "min_trips_per_piece": 1,
        "max_trips_per_piece": 4,
    })
    result, elapsed = run_service(
        trips=trips,
        algorithm=AlgorithmType.HYBRID_PIPELINE,
        vehicle_types=[],
        cct_params=cct,
        vsp_params=vsp,
    )
    vsp_issues = audit_vsp(result.vsp.blocks, min_layover=10, same_depot=True)
    csp_issues = audit_csp(result.csp.duties, max_shift=480)
    ok = not vsp_issues and result.csp.cct_violations == 0 and not csp_issues
    detail = (
        f"trips={len(trips)} veh={result.vsp.num_vehicles} crew={len(result.csp.duties)} "
        f"cost={result.total_cost:.2f} viol={result.csp.cct_violations} "
        f"workpieces={result.csp.meta.get('workpieces_generated', 0)}"
    )
    if not ok:
        detail += f" | sample={(vsp_issues + csp_issues)[:3]}"
    return CheckResult("Híbrido multi-linha estrito", ok, detail, elapsed)


def scenario_set_covering_goal_programming() -> CheckResult:
    trips = build_dataset(cycles_per_line=MODE.setcover_cycles, include_ev=False, seed=77)
    cct = {
        "apply_cct": True,
        "max_shift_minutes": 500,
        "max_work_minutes": 440,
        "min_work_minutes": 240,
        "min_break_minutes": 20,
        "min_layover_minutes": 8,
        "pullout_minutes": 10,
        "pullback_minutes": 10,
    }
    vsp = tuned_vsp({
        "pricing_enabled": True,
        "use_set_covering": True,
        "min_workpiece_minutes": 180,
        "max_workpiece_minutes": 440,
        "min_trips_per_piece": 2,
        "max_trips_per_piece": 4,
        "goal_weights": {
            "min_work": 0.8,
            "spread": 0.6,
            "fairness": 0.4,
        },
    })
    result, elapsed = run_service(
        trips=trips,
        algorithm=AlgorithmType.SET_PARTITIONING,
        vehicle_types=[],
        cct_params=cct,
        vsp_params=vsp,
    )
    covered = {
        int(block.meta.get("source_block_id", block.id))
        for duty in result.csp.duties
        for block in duty.tasks
    }
    all_blocks = {block.id for block in result.vsp.blocks}
    ok = covered == all_blocks and result.csp.meta.get("pricing_enabled") is True and result.csp.meta.get("objective") == "min sum(c_j * x_j)"
    detail = (
        f"blocks={len(all_blocks)} covered={len(covered)} workpieces={result.csp.meta.get('workpieces_generated', 0)} "
        f"objective={result.csp.meta.get('objective')} pricing={result.csp.meta.get('pricing_enabled')}"
    )
    return CheckResult("Set covering + pricing + metas", ok, detail, elapsed)


def scenario_ev_charger_capacity() -> CheckResult:
    trips = build_dataset(cycles_per_line=MODE.ev_cycles, include_ev=True, seed=99)
    vehicle_types = [
        VehicleType(
            id=1,
            name="eBus",
            passenger_capacity=70,
            fixed_cost=700.0,
            is_electric=True,
            battery_capacity_kwh=210.0,
            minimum_soc=0.12,
            charge_rate_kw=180.0,
            energy_cost_per_kwh=1.1,
        )
    ]
    cct = {
        "apply_cct": True,
        "max_shift_minutes": 520,
        "max_work_minutes": 450,
        "min_break_minutes": 25,
        "min_layover_minutes": 12,
        "pullout_minutes": 10,
        "pullback_minutes": 10,
    }
    vsp = tuned_vsp({
        "same_depot_required": True,
        "max_simultaneous_chargers": 1,
        "peak_energy_cost_per_kwh": 1.4,
        "offpeak_energy_cost_per_kwh": 0.7,
        "pricing_enabled": False,
        "strict_hard_validation": False,
    })
    result, elapsed = run_service(
        trips=trips,
        algorithm=AlgorithmType.GREEDY,
        vehicle_types=vehicle_types,
        cct_params=cct,
        vsp_params=vsp,
    )
    warnings = list(result.vsp.warnings)
    ok = any("CHARGER_CAPACITY_EXCEEDED" in item for item in warnings) or len(result.vsp.unassigned_trips) > 0
    detail = f"veh={result.vsp.num_vehicles} unassigned={len(result.vsp.unassigned_trips)} warnings={warnings[:2]}"
    return CheckResult("EV + gargalo de carregador", ok, detail, elapsed)


def scenario_cascade_delay_resilience() -> CheckResult:
    base = build_dataset(cycles_per_line=MODE.cascade_cycles, include_ev=False, seed=123)
    delayed = perturb_delays(base, [trip.id for trip in base[:18]], 12)
    cct = {
        "apply_cct": True,
        "max_shift_minutes": 500,
        "max_work_minutes": 430,
        "min_break_minutes": 20,
        "min_layover_minutes": 8,
        "pullout_minutes": 10,
        "pullback_minutes": 10,
    }
    vsp = tuned_vsp({
        "same_depot_required": False,
        "pricing_enabled": True,
        "use_set_covering": True,
        "min_workpiece_minutes": 120,
        "max_workpiece_minutes": 420,
        "min_trips_per_piece": 1,
        "max_trips_per_piece": 4,
    })
    result, elapsed = run_service(
        trips=delayed,
        algorithm=AlgorithmType.HYBRID_PIPELINE,
        vehicle_types=[],
        cct_params=cct,
        vsp_params=vsp,
    )
    vsp_issues = audit_vsp(result.vsp.blocks, min_layover=8, same_depot=False)
    ok = not any(issue.startswith("OVERLAP") for issue in vsp_issues) and result.csp.cct_violations == 0
    detail = (
        f"trips={len(delayed)} veh={result.vsp.num_vehicles} crew={len(result.csp.duties)} "
        f"maxSpread={max((d.spread_time for d in result.csp.duties), default=0)}"
    )
    if not ok:
        detail += f" | sample={vsp_issues[:2]}"
    return CheckResult("Resiliência a atrasos em cascata", ok, detail, elapsed)


def scenario_cost_consistency() -> CheckResult:
    trips = build_dataset(cycles_per_line=MODE.cost_cycles, include_ev=False, seed=321)
    cct = {
        "apply_cct": True,
        "max_shift_minutes": 520,
        "max_work_minutes": 460,
        "min_break_minutes": 20,
        "min_layover_minutes": 8,
        "pullout_minutes": 10,
        "pullback_minutes": 10,
    }
    vsp = tuned_vsp({
        "pricing_enabled": True,
        "use_set_covering": True,
        "fixed_vehicle_activation_cost": 800.0,
        "deadhead_cost_per_minute": 1.0,
        "idle_cost_per_minute": 0.25,
    })
    result, elapsed = run_service(
        trips=trips,
        algorithm=AlgorithmType.HYBRID_PIPELINE,
        vehicle_types=[],
        cct_params=cct,
        vsp_params=vsp,
    )
    block_cost = sum(float(block.meta.get("activation_cost", 0.0)) + float(block.meta.get("connection_cost", 0.0)) for block in result.vsp.blocks)
    ok = (
        math.isfinite(result.total_cost)
        and result.vsp.meta.get("objective", {}).get("formula") == "sum(f_k) + sum(c_ij * x_ij)"
        and result.total_cost >= block_cost
        and block_cost > 0
    )
    detail = f"total={result.total_cost:.2f} lower_bound_vsp={block_cost:.2f}"
    return CheckResult("Consistência da função objetivo VSP", ok, detail, elapsed)


def scenario_pairing_integrity_stress() -> CheckResult:
    trips = build_pair_pressure_dataset(cycles_per_line=MODE.pair_cycles)
    cct = {
        "apply_cct": True,
        "max_shift_minutes": 480,
        "max_work_minutes": 420,
        "max_driving_minutes": 240,
        "min_break_minutes": 30,
        "min_layover_minutes": 8,
        "pullout_minutes": 10,
        "pullback_minutes": 10,
        "mandatory_break_after_minutes": 240,
        "meal_break_minutes": 30,
        "enforce_same_depot_start_end": True,
    }
    guarded_vsp = tuned_vsp({
        "same_depot_required": True,
        "pricing_enabled": True,
        "use_set_covering": True,
        "preserve_preferred_pairs": True,
        "preferred_pair_window_minutes": 120,
    })
    unguarded_vsp = {
        **guarded_vsp,
        "preserve_preferred_pairs": False,
    }
    guarded, elapsed = run_service(
        trips=trips,
        algorithm=AlgorithmType.HYBRID_PIPELINE,
        vehicle_types=[],
        cct_params=cct,
        vsp_params=guarded_vsp,
    )
    unguarded, _ = run_service(
        trips=trips,
        algorithm=AlgorithmType.HYBRID_PIPELINE,
        vehicle_types=[],
        cct_params=cct,
        vsp_params=unguarded_vsp,
    )
    vsp_issues, guarded_stats = audit_preferred_pairing(guarded.vsp.blocks, trips, min_layover=8)
    unguarded_issues, unguarded_stats = audit_preferred_pairing(unguarded.vsp.blocks, trips, min_layover=8)
    duty_issues = audit_operator_pairing(guarded.csp.duties, trips, min_layover=8)
    pairing_improvement_observable = unguarded_stats["preferred_pair_breaks"] > 0
    ok = (
        not vsp_issues
        and not duty_issues
        and (
            guarded_stats["preferred_pair_breaks"] < unguarded_stats["preferred_pair_breaks"]
            if pairing_improvement_observable
            else guarded_stats["preferred_pair_breaks"] == 0
        )
        and guarded.csp.cct_violations == 0
    )
    detail = (
        f"pairs={guarded_stats['preferred_pair_count']} matched={guarded_stats['paired_connections_followed']} "
        f"broken_guarded={guarded_stats['preferred_pair_breaks']} broken_off={unguarded_stats['preferred_pair_breaks']} "
        f"duty_split={len(duty_issues)}"
    )
    if not ok:
        detail += f" | sample={(vsp_issues + duty_issues + unguarded_issues)[:3]}"
    return CheckResult("Integridade ida-volta sob pressão", ok, detail, elapsed)


def scenario_hard_input_integrity_rejection() -> CheckResult:
    trips = [
        Trip(
            id=1,
            line_id=700,
            start_time=360,
            end_time=420,
            origin_id=1,
            destination_id=2,
            duration=60,
            origin_latitude=-12.9,
            origin_longitude=-38.5,
            destination_latitude=120.0,
            destination_longitude=-38.4,
            sent_to_driver_terminal=False,
            deadhead_times={1: 8, 2: 8},
        )
    ]
    t0 = time.perf_counter()
    try:
        OptimizerService().run(trips=trips, vehicle_types=[], algorithm=AlgorithmType.GREEDY)
        ok = False
        detail = "optimizer aceitou entrada inválida"
    except HardConstraintViolationError as exc:
        ok = "GHOST_BUS_TERMINAL_SYNC" in str(exc) and "GPS_LATITUDE_INVALID_DESTINATION" in str(exc)
        detail = str(exc)
    elapsed = time.perf_counter() - t0
    return CheckResult("Rejeição fatal de integridade de dados", ok, detail, elapsed)


def scenario_hard_ev_conflict_rejection() -> CheckResult:
    trips = build_dataset(cycles_per_line=MODE.ev_cycles, include_ev=True, seed=99)
    vehicle_types = [
        VehicleType(
            id=1,
            name="eBus",
            passenger_capacity=70,
            fixed_cost=700.0,
            is_electric=True,
            battery_capacity_kwh=210.0,
            minimum_soc=0.12,
            charge_rate_kw=180.0,
            energy_cost_per_kwh=1.1,
        )
    ]
    cct = {
        "apply_cct": True,
        "max_shift_minutes": 520,
        "max_work_minutes": 450,
        "min_break_minutes": 25,
        "min_layover_minutes": 12,
        "pullout_minutes": 10,
        "pullback_minutes": 10,
    }
    vsp = tuned_vsp({
        "same_depot_required": True,
        "max_simultaneous_chargers": 1,
    })
    t0 = time.perf_counter()
    try:
        OptimizerService().run(
            trips=trips,
            vehicle_types=vehicle_types,
            algorithm=AlgorithmType.GREEDY,
            cct_params=cct,
            vsp_params=vsp,
        )
        ok = False
        detail = "optimizer aceitou conflito crítico de carregamento"
    except HardConstraintViolationError as exc:
        ok = "EV_CHARGER_CAPACITY_EXCEEDED" in str(exc)
        detail = str(exc)
    elapsed = time.perf_counter() - t0
    return CheckResult("Rejeição fatal de conflito EV", ok, detail, elapsed)


def scenario_bruteforce_hard_constraints() -> CheckResult:
    t0 = time.perf_counter()
    seeds = list(range(11, 11 + MODE.bruteforce_seeds))
    failures: List[str] = []
    checked = 0
    for seed in seeds:
        base = build_dataset(cycles_per_line=3, include_ev=False, seed=seed)
        trips: List[Trip] = []
        for trip in base[:18]:
            trips.append(
                Trip(
                    id=trip.id,
                    line_id=trip.line_id,
                    start_time=trip.start_time,
                    end_time=trip.end_time,
                    origin_id=trip.origin_id,
                    destination_id=trip.destination_id,
                    duration=trip.duration,
                    distance_km=trip.distance_km,
                    depot_id=trip.depot_id,
                    origin_latitude=-12.9,
                    origin_longitude=-38.5,
                    destination_latitude=-12.8,
                    destination_longitude=-38.4,
                    sent_to_driver_terminal=True,
                    gps_valid=True,
                    deadhead_times=dict(trip.deadhead_times),
                )
            )

        pair_map = build_preferred_pairs(trips, min_layover=8, max_pair_window=120)
        preferred_group = None
        for trip_id, pair_id in sorted(pair_map.items()):
            if trip_id < pair_id:
                preferred_group = [trip_id, pair_id]
                break

        cct = {
            "apply_cct": True,
            "max_shift_minutes": 480,
            "max_work_minutes": 420,
            "max_driving_minutes": 240,
            "min_break_minutes": 30,
            "mandatory_break_after_minutes": 240,
            "inter_shift_rest_minutes": 660,
            "allow_relief_points": True,
            "mandatory_trip_groups_same_duty": [preferred_group] if preferred_group else [],
        }
        vsp = tuned_vsp({
            "preserve_preferred_pairs": True,
            "pricing_enabled": True,
            "use_set_covering": True,
            "strict_hard_validation": True,
        })

        try:
            result, _ = run_service(
                trips=trips,
                algorithm=AlgorithmType.HYBRID_PIPELINE,
                vehicle_types=[],
                cct_params=cct,
                vsp_params=vsp,
            )
        except HardConstraintViolationError as exc:
            failures.append(f"seed={seed}:{exc}")
            continue

        output_report = result.meta.get("hard_constraint_report", {}).get("output", {})
        checked += 1
        if not output_report.get("ok", False):
            failures.append(f"seed={seed}:report={output_report.get('issues', [])[:2]}")
            continue
        if result.csp.cct_violations != 0:
            failures.append(f"seed={seed}:cct={result.csp.cct_violations}")
            continue
    elapsed = time.perf_counter() - t0
    ok = not failures and checked == len(seeds)
    detail = f"seeds={len(seeds)} checked={checked} failures={len(failures)}"
    if failures:
        detail += f" | sample={failures[:3]}"
    return CheckResult("Força bruta hard constraints", ok, detail, elapsed)


def main() -> int:
    print(f"\nQA Operacional Extremo 2026 — OTIMIZ [{MODE.name}]\n")
    scenario_builders = [
        scenario_hybrid_multiline_strict,
        scenario_set_covering_goal_programming,
        scenario_ev_charger_capacity,
        scenario_cascade_delay_resilience,
        scenario_cost_consistency,
        scenario_pairing_integrity_stress,
        scenario_hard_input_integrity_rejection,
        scenario_hard_ev_conflict_rejection,
    ]
    if MODE.include_bruteforce:
        scenario_builders.append(scenario_bruteforce_hard_constraints)

    checks: List[CheckResult] = []
    for builder in scenario_builders:
        try:
            checks.append(builder())
        except Exception as exc:
            checks.append(
                CheckResult(
                    name=builder.__name__,
                    ok=False,
                    detail=f"exception={type(exc).__name__}: {exc}",
                    elapsed_s=0.0,
                )
            )
    for item in checks:
        print_result(item)

    failures = [item for item in checks if not item.ok]
    avg_time = statistics.mean(item.elapsed_s for item in checks)
    print(f"\nResumo: {len(checks) - len(failures)}/{len(checks)} cenários aprovados | tempo médio {avg_time:.2f}s")
    if failures:
        print(f"{WARN} Falhas encontradas: {[item.name for item in failures]}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
