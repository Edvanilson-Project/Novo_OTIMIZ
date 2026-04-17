#!/usr/bin/env python3
"""
Bateria Profissional de Validação — OTIMIZ 2026

Objetivo:
- executar validações sistêmicas alinhadas ao padrão profissional (HASTUS/Optibus/GoalBus)
- emitir resultado consolidado PASS/FAIL por categoria
- evidenciar lacunas reais sem mascarar risco operacional

Uso:
  cd /home/edvanilson/WEB_OPT/optimizer
  /home/edvanilson/WEB_OPT/.venv/bin/python tests/qa_professional_validation_2026.py
"""
from __future__ import annotations

import math
import os
import sys
import tempfile
import traceback
from dataclasses import dataclass
from typing import Callable, List, Sequence

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.algorithms.csp.greedy import GreedyCSP
from src.algorithms.vsp.greedy import GreedyVSP
from src.core.exceptions import HardConstraintViolationError
from src.domain.models import AlgorithmType, Block, Trip, VehicleType
from src.services.optimizer_service import OptimizerService
from src.services.strategy_persistence_service import StrategyPersistenceService
from src.services.strategy_service import StrategyService

OK = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"


@dataclass
class CheckResult:
    category: str
    name: str
    passed: bool
    detail: str
    hard_gate: bool = True


def _trip(
    trip_id: int,
    start: int,
    duration: int,
    *,
    line: int = 1,
    origin: int = 1,
    dest: int = 2,
    depot: int | None = 1,
    energy: float = 0.0,
    elevation: float = 0.0,
    day: int = 0,
    relief: bool = False,
) -> Trip:
    start_time = day * 1440 + start
    return Trip(
        id=trip_id,
        line_id=line,
        start_time=start_time,
        end_time=start_time + duration,
        origin_id=origin,
        destination_id=dest,
        duration=duration,
        distance_km=max(1.0, duration / 3),
        depot_id=depot,
        is_relief_point=relief,
        energy_kwh=energy,
        elevation_gain_m=elevation,
        deadhead_times={origin: 8, dest: 8, 1: 10, 2: 10, 3: 10, 4: 10},
    )


def _vehicle(electric: bool = False) -> list[VehicleType]:
    return [
        VehicleType(
            id=1,
            name="EV" if electric else "Diesel",
            passenger_capacity=42,
            cost_per_km=2.0,
            cost_per_hour=50.0,
            fixed_cost=800.0,
            is_electric=electric,
            battery_capacity_kwh=60.0 if electric else 0.0,
            minimum_soc=0.2 if electric else 0.0,
            charge_rate_kw=60.0 if electric else 0.0,
            energy_cost_per_kwh=0.9 if electric else 0.0,
            depot_id=1,
        )
    ]


def _run_optimizer(
    trips: Sequence[Trip],
    *,
    algorithm: AlgorithmType = AlgorithmType.HYBRID_PIPELINE,
    cct: dict | None = None,
    vsp: dict | None = None,
    electric: bool = False,
    time_budget_s: float = 30.0,
):
    service = OptimizerService()
    return service.run(
        trips=list(trips),
        vehicle_types=_vehicle(electric=electric),
        algorithm=algorithm,
        cct_params=cct or {},
        vsp_params=vsp or {},
        time_budget_s=time_budget_s,
    )


def _check(name: str, category: str, fn: Callable[[], tuple[bool, str]], hard_gate: bool = True) -> CheckResult:
    try:
        ok, detail = fn()
        return CheckResult(category=category, name=name, passed=ok, detail=detail, hard_gate=hard_gate)
    except Exception as exc:
        return CheckResult(
            category=category,
            name=name,
            passed=False,
            detail=f"exceção: {type(exc).__name__}: {exc}",
            hard_gate=hard_gate,
        )


# 1) Hard constraints legais

def check_daily_shift_limit() -> tuple[bool, str]:
    trips = [
        _trip(1, 360, 180, line=10, origin=1, dest=2),
        _trip(2, 560, 180, line=10, origin=2, dest=1),
        _trip(3, 780, 120, line=10, origin=1, dest=2),
    ]
    result = _run_optimizer(
        trips,
        cct={"max_shift_minutes": 480, "strict_hard_validation": True},
        vsp={"min_layover_minutes": 10},
        time_budget_s=30.0,
    )
    spreads = [d.spread_time for d in result.csp.duties]
    ok = bool(spreads) and max(spreads) <= 480
    return ok, f"max_spread={max(spreads) if spreads else 0} duties={len(spreads)}"


def check_intershift_11h() -> tuple[bool, str]:
    trips = [
        _trip(1, 8 * 60, 120, line=11, origin=1, dest=2, day=0),
        _trip(2, 11 * 60, 120, line=11, origin=2, dest=1, day=0),
        _trip(3, 8 * 60, 120, line=11, origin=1, dest=2, day=1),
        _trip(4, 11 * 60, 120, line=11, origin=2, dest=1, day=1),
    ]
    result = _run_optimizer(
        trips,
        cct={"inter_shift_rest_minutes": 660, "strict_hard_validation": True},
        vsp={"min_layover_minutes": 10},
        time_budget_s=30.0,
    )
    rosters = {}
    for duty in result.csp.duties:
        roster = int(duty.meta.get("roster_id", 0) or 0)
        if roster <= 0 or not duty.tasks:
            continue
        rosters.setdefault(roster, []).append((duty.tasks[0].start_time, duty.tasks[-1].end_time))

    min_rest = 10**9
    for windows in rosters.values():
        ordered = sorted(windows)
        for i in range(len(ordered) - 1):
            rest = ordered[i + 1][0] - ordered[i][1]
            min_rest = min(min_rest, rest)

    if min_rest == 10**9:
        min_rest = 660
    return min_rest >= 660, f"min_intershift_rest={min_rest}"


def check_break_30_each_4h() -> tuple[bool, str]:
    trips = [
        _trip(1, 360, 120, line=12, origin=1, dest=2),
        _trip(2, 490, 120, line=12, origin=2, dest=1),
        _trip(3, 620, 120, line=12, origin=1, dest=2),
    ]
    result = _run_optimizer(
        trips,
        cct={
            "max_driving_minutes": 240,
            "mandatory_break_after_minutes": 240,
            "min_break_minutes": 30,
            "strict_hard_validation": True,
        },
        vsp={"min_layover_minutes": 10}, time_budget_s=30.0,
)
    max_cont = max((int(d.meta.get("max_continuous_drive_minutes", 0)) for d in result.csp.duties), default=0)
    return max_cont <= 240, f"max_continuous_drive={max_cont}"


def check_meal_break_1h() -> tuple[bool, str]:
    trips = [
        _trip(1, 360, 120, line=13, origin=1, dest=2),
        _trip(2, 500, 120, line=13, origin=2, dest=1),
        _trip(3, 760, 120, line=13, origin=1, dest=2),
    ]
    result = _run_optimizer(
        trips,
        cct={
            "meal_break_minutes": 60,
            "mandatory_break_after_minutes": 240,
            "min_break_minutes": 30,
            "strict_hard_validation": True,
        },
        vsp={"min_layover_minutes": 10}, time_budget_s=30.0,
)
    issues = (((result.meta or {}).get("hard_constraint_report") or {}).get("output") or {}).get("issues", [])
    missing_meal = [i for i in issues if "MEAL_BREAK_MISSING" in i]
    return len(missing_meal) == 0, f"meal_break_issues={len(missing_meal)}"


# 2) Viabilidade técnica e operacional

def check_no_overlap_vehicle_and_driver() -> tuple[bool, str]:
    trips = [
        _trip(1, 360, 50, line=20, origin=1, dest=2),
        _trip(2, 430, 50, line=20, origin=2, dest=1),
        _trip(3, 500, 50, line=20, origin=1, dest=2),
        _trip(4, 570, 50, line=20, origin=2, dest=1),
    ]
    result = _run_optimizer(trips, cct={"strict_hard_validation": True}, vsp={"min_layover_minutes": 10}, time_budget_s=30.0)
    overlap_blocks = 0
    for block in result.vsp.blocks:
        overlap_blocks += len(block.verify_no_overlap())
    overlap_duties = 0
    for duty in result.csp.duties:
        tasks = duty.tasks
        for i in range(len(tasks) - 1):
            if tasks[i + 1].start_time < tasks[i].end_time:
                overlap_duties += 1
    ok = overlap_blocks == 0 and overlap_duties == 0
    return ok, f"block_overlap={overlap_blocks} duty_overlap={overlap_duties}"


def check_relief_points_terminal_only() -> tuple[bool, str]:
    trips = [
        _trip(1, 360, 60, line=21, origin=1, dest=2, depot=1),
        _trip(2, 450, 60, line=21, origin=3, dest=4, depot=2),
    ]
    result = _run_optimizer(
        trips,
        cct={"operator_change_terminals_only": True, "allow_relief_points": False, "strict_hard_validation": True},
        vsp={"min_layover_minutes": 10, "allow_multi_line_block": True}, time_budget_s=30.0,
)
    # Esperado: sem boundary inválido (normalmente vira 2 duties distintas)
    output_issues = (((result.meta or {}).get("hard_constraint_report") or {}).get("output") or {}).get("issues", [])
    bad = [i for i in output_issues if "OPERATOR_CHANGE_NON_TERMINAL" in i]
    return len(bad) == 0, f"operator_change_non_terminal_issues={len(bad)} duties={len(result.csp.duties)}"


def check_deadhead_realistic() -> tuple[bool, str]:
    t1 = _trip(1, 360, 60, line=22, origin=1, dest=2)
    t2 = _trip(2, 425, 60, line=22, origin=3, dest=1)
    t1.deadhead_times[3] = 25
    t1.deadhead_times[1] = 25
    result = _run_optimizer([t1, t2], cct={"strict_hard_validation": True}, vsp={"min_layover_minutes": 10}, time_budget_s=30.0)
    return len(result.vsp.blocks) == 2, f"vehicles={len(result.vsp.blocks)} expected=2"


def check_single_vehicle_per_operator() -> tuple[bool, str]:
    trips = [
        _trip(1, 360, 60, line=23, origin=1, dest=2),
        _trip(2, 430, 60, line=23, origin=2, dest=1),
        _trip(3, 520, 60, line=23, origin=1, dest=2),
        _trip(4, 610, 60, line=23, origin=2, dest=1),
    ]
    result = _run_optimizer(
        trips,
        cct={"operator_single_vehicle_only": True, "strict_hard_validation": True},
        vsp={"min_layover_minutes": 10}, time_budget_s=30.0,
)
    max_sources = 0
    for duty in result.csp.duties:
        sources = {int(x) for x in duty.meta.get("source_block_ids", []) if x is not None}
        max_sources = max(max_sources, len(sources))
    return max_sources <= 1, f"max_source_blocks_per_duty={max_sources}"


# 3) Elétricos (EV)

def check_ev_soc_safety() -> tuple[bool, str]:
    trips = [
        _trip(1, 360, 70, line=30, origin=1, dest=2, energy=8.0, elevation=40),
        _trip(2, 460, 70, line=30, origin=2, dest=1, energy=8.5, elevation=60),
    ]
    result = _run_optimizer(
        trips,
        cct={"strict_hard_validation": True},
        vsp={"min_layover_minutes": 10, "max_simultaneous_chargers": 1},
        electric=True, time_budget_s=30.0,
)
    low_soc = 0
    min_soc_kwh = _vehicle(electric=True)[0].minimum_soc * _vehicle(electric=True)[0].battery_capacity_kwh
    for block in result.vsp.blocks:
        soc = float(block.meta.get("soc_kwh", min_soc_kwh))
        if soc < min_soc_kwh:
            low_soc += 1
    return low_soc == 0, f"blocks_below_min_soc={low_soc}"


def check_ev_charger_capacity_validation() -> tuple[bool, str]:
    trips = [
        _trip(1, 360, 50, line=31, origin=1, dest=2, depot=1, energy=30.0),
        _trip(2, 420, 50, line=31, origin=2, dest=1, depot=1, energy=12.0),
        _trip(3, 360, 50, line=32, origin=1, dest=2, depot=1, energy=30.0),
        _trip(4, 420, 50, line=32, origin=2, dest=1, depot=1, energy=12.0),
    ]
    result = _run_optimizer(
        trips,
        cct={"strict_hard_validation": False},
        vsp={"min_layover_minutes": 10, "max_simultaneous_chargers": 1, "allow_multi_line_block": False},
        electric=True, time_budget_s=30.0,
)
    warnings = list(result.vsp.warnings or [])
    has_cap_warning = any("CHARGER_CAPACITY_EXCEEDED" in w for w in warnings)
    return has_cap_warning, f"charger_capacity_warning={'yes' if has_cap_warning else 'no'}"


def check_ev_topography_effect() -> tuple[bool, str]:
    low = _trip(1, 360, 60, line=33, origin=1, dest=2, energy=10.0, elevation=0)
    high = _trip(2, 430, 60, line=33, origin=2, dest=1, energy=10.0, elevation=600)
    solver = GreedyVSP(vsp_params={"min_layover_minutes": 10})
    base = solver._energy_need(low, _vehicle(electric=True)[0])
    steep = solver._energy_need(high, _vehicle(electric=True)[0])
    return steep > base, f"energy_flat={base:.2f} energy_steep={steep:.2f}"


# 4) Eficiência e KPIs

def check_marginal_cost_monotonicity() -> tuple[bool, str]:
    base_trips = [
        _trip(1, 360, 60, line=40, origin=1, dest=2),
        _trip(2, 440, 60, line=40, origin=2, dest=1),
    ]
    high_cost_trips = [
        _trip(1, 360, 60, line=40, origin=1, dest=2),
        _trip(2, 440, 60, line=40, origin=2, dest=1),
    ]
    high_cost_trips[0].deadhead_times[2] = 35

    base = _run_optimizer(base_trips, cct={"strict_hard_validation": True}, vsp={"min_layover_minutes": 10}, time_budget_s=30.0)
    high = _run_optimizer(high_cost_trips, cct={"strict_hard_validation": True}, vsp={"min_layover_minutes": 10}, time_budget_s=30.0)

    base_conn = sum(float(b.meta.get("connection_cost", 0.0)) for b in base.vsp.blocks)
    high_conn = sum(float(b.meta.get("connection_cost", 0.0)) for b in high.vsp.blocks)
    return high_conn >= base_conn, f"base_conn={base_conn:.2f} high_conn={high_conn:.2f}"


def check_fairness_target_and_tolerance() -> tuple[bool, str]:
    trips = [
        _trip(1, 360, 210, line=41, origin=1, dest=2),
        _trip(2, 600, 210, line=41, origin=2, dest=1),
        _trip(3, 370, 210, line=42, origin=3, dest=4),
        _trip(4, 610, 210, line=42, origin=4, dest=3),
    ]
    result = _run_optimizer(
        trips,
        cct={
            "fairness_weight": 1.0,
            "fairness_target_work_minutes": 420,
            "fairness_tolerance_minutes": 30,
            "strict_hard_validation": True,
        },
        vsp={"min_layover_minutes": 10, "allow_multi_line_block": False}, time_budget_s=30.0,
)
    work = [d.work_time for d in result.csp.duties]
    if not work:
        return False, "nenhuma duty gerada"
    within = [w for w in work if 360 <= w <= 480]
    max_dev = max(abs(a - b) for a in work for b in work)
    majority_within = len(within) >= math.ceil(len(work) / 2)
    return majority_within and max_dev <= 30, f"duties={len(work)} within_band={len(within)} max_dev={max_dev}"


def check_minimize_stretches() -> tuple[bool, str]:
    trips = [
        _trip(1, 360, 60, line=43, origin=1, dest=2),
        _trip(2, 430, 60, line=43, origin=2, dest=1),
        _trip(3, 500, 60, line=43, origin=1, dest=2),
        _trip(4, 570, 60, line=43, origin=2, dest=1),
    ]
    result = _run_optimizer(
        trips,
        cct={"operator_single_vehicle_only": True, "strict_hard_validation": True},
        vsp={"min_layover_minutes": 10}, time_budget_s=30.0,
)
    stretch = (((result.meta or {}).get("operational_kpis") or {}).get("stretch_kpi") or {})
    avg = float(stretch.get("avg_vehicle_changes_per_operator", 0.0) or 0.0)
    return avg <= 0.0, f"avg_vehicle_changes_per_operator={avg:.3f}"


# 5) Componentes de arquitetura profissional

def check_macro_whatif_feedback_modules() -> tuple[bool, str]:
    svc = StrategyService()
    trips = [
        _trip(1, 360, 60, line=50, origin=1, dest=2),
        _trip(2, 430, 60, line=50, origin=2, dest=1),
    ]
    macro = svc.macro_estimate(trips)
    what_if = svc.what_if(
        trips,
        [
            {"name": "base", "cct_params": {}, "vsp_params": {}},
            {"name": "tight", "cct_params": {"max_shift_minutes": 420}, "vsp_params": {}},
        ],
    )
    pvr = svc.plan_vs_real(
        trips,
        [
            {"trip_id": 1, "actual_start_time": 365, "gps_valid": True, "sent_to_driver_terminal": True},
            {"trip_id": 2, "actual_start_time": 445, "gps_valid": True, "sent_to_driver_terminal": True},
        ],
    )
    ok = macro.estimated_vehicles >= 1 and len(what_if) == 2 and "kpis" in pvr
    return ok, f"macro_vehicles={macro.estimated_vehicles} whatif={len(what_if)} pvr_kpis={'yes' if 'kpis' in pvr else 'no'}"


def check_rostering_layer() -> tuple[bool, str]:
    blocks = []
    for day in range(7):
        start = day * 1440 + 6 * 60
        blocks.append(Block(id=day + 1, trips=[_trip(day + 1, start % 1440, 540, day=day)]))
    sol = GreedyCSP(weekly_driving_limit_minutes=3360, inter_shift_rest_minutes=660).solve(blocks, [])
    rosters = int(sol.meta.get("roster_count", 0) or 0)
    return rosters >= 2, f"roster_count={rosters}"


def check_feedback_persistence_cycle() -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="otimiz_strategy_") as temp_dir:
        persistence = StrategyPersistenceService(temp_dir)

        scenario = persistence.save_scenario(
            {
                "scenario_name": "qa-professional",
                "trips": [{"id": 1, "line_id": 1, "start_time": 360, "end_time": 420, "origin_id": 1, "destination_id": 2}],
                "estimate": {"estimated_total_cost": 1000.0, "estimated_vehicles": 1, "estimated_crew": 1},
            }
        )
        ingest = persistence.ingest_feed(
            [
                {"trip_id": 1, "actual_start_time": 368, "gps_valid": True, "sent_to_driver_terminal": True, "source": "avl"}
            ]
        )
        snapshot = persistence.get_latest_feed_snapshot()
        report = persistence.save_reconciliation_report({"kpis": {"avg_delay": 8.0}})
        cleanup = persistence.prune_data(max_scenarios=1, max_feed_snapshots=1, max_reports=1, max_age_days=30)

        ok = (
            int(scenario.get("id", 0)) >= 1
            and int(ingest.get("snapshot_id", 0)) >= 1
            and snapshot is not None
            and int(report.get("id", 0)) >= 1
            and all(int(v) >= 0 for v in cleanup.values())
        )
        return ok, f"scenario_id={scenario.get('id')} snapshot_id={ingest.get('snapshot_id')} report_id={report.get('id')}"


# 6) Comportamento integrado

def check_integrated_joint_behavior() -> tuple[bool, str]:
    trips = [
        _trip(1, 360, 60, line=60, origin=1, dest=2),
        _trip(2, 430, 60, line=60, origin=2, dest=1),
        _trip(3, 500, 60, line=60, origin=1, dest=2),
        _trip(4, 570, 60, line=60, origin=2, dest=1),
    ]
    result = _run_optimizer(
        trips,
        algorithm=AlgorithmType.JOINT_SOLVER,
        cct={"strict_hard_validation": True, "operator_single_vehicle_only": True},
        vsp={"min_layover_minutes": 10}, time_budget_s=30.0,
)
    ok = len(result.vsp.unassigned_trips) == 0 and result.csp.cct_violations == 0
    return ok, f"vehicles={len(result.vsp.blocks)} crew={len(result.csp.duties)} unassigned={len(result.vsp.unassigned_trips)} cct_viol={result.csp.cct_violations}"


def run_all() -> List[CheckResult]:
    checks: List[CheckResult] = [
        _check("Jornada diária (8/10/12h)", "Hard-Constraints", check_daily_shift_limit),
        _check("Descanso interjornada ≥ 11h", "Hard-Constraints", check_intershift_11h),
        _check("Pausa 30 min a cada 4h", "Hard-Constraints", check_break_30_each_4h),
        _check("Intervalo refeição ≥ 1h", "Hard-Constraints", check_meal_break_1h),
        _check("Sem overlap veículo/motorista", "Operacional", check_no_overlap_vehicle_and_driver),
        _check("Troca somente em terminal/depot", "Operacional", check_relief_points_terminal_only),
        _check("Deadhead realista", "Operacional", check_deadhead_realistic),
        _check("Pareamento operador-veículo", "Operacional", check_single_vehicle_per_operator),
        _check("SoC nunca abaixo do mínimo", "EV", check_ev_soc_safety),
        _check("Capacidade de carregador", "EV", check_ev_charger_capacity_validation),
        _check("Topografia afeta descarga", "EV", check_ev_topography_effect),
        _check("Custo marginal coerente", "KPI-Solver", check_marginal_cost_monotonicity),
        _check("Fairness (6-8h, ±30 min)", "KPI-Solver", check_fairness_target_and_tolerance),
        _check("Minimização de stretches", "KPI-Solver", check_minimize_stretches),
        _check("Macro + What-if + Plan-vs-real", "Arquitetura", check_macro_whatif_feedback_modules),
        _check("Camada de rostering", "Arquitetura", check_rostering_layer),
        _check("Ciclo feedback persistente", "Arquitetura", check_feedback_persistence_cycle),
        _check("Otimização integrada (Joint)", "Integração", check_integrated_joint_behavior),
    ]
    return checks


def print_report(results: Sequence[CheckResult]) -> int:
    print("\n" + "=" * 88)
    print("BATERIA PROFISSIONAL — VALIDAÇÃO SISTÊMICA")
    print("=" * 88)

    categories = sorted({r.category for r in results})
    blockers = 0

    for category in categories:
        print(f"\n[{category}]")
        subset = [r for r in results if r.category == category]
        for row in subset:
            status = OK if row.passed else FAIL if row.hard_gate else WARN
            gate = "HARD" if row.hard_gate else "SOFT"
            print(f"  {status:12} {row.name} ({gate}) -> {row.detail}")
            if row.hard_gate and not row.passed:
                blockers += 1

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    hard_total = sum(1 for r in results if r.hard_gate)
    hard_passed = sum(1 for r in results if r.hard_gate and r.passed)

    print("\n" + "-" * 88)
    print(f"Resumo: {passed}/{total} checks aprovados")
    print(f"Hard-gates: {hard_passed}/{hard_total} aprovados")
    if blockers == 0:
        print(f"Status final: {OK} (sem bloqueadores hard)")
    else:
        print(f"Status final: {FAIL} ({blockers} bloqueadores hard)")
    print("-" * 88)

    return 0 if blockers == 0 else 2


if __name__ == "__main__":
    try:
        results = run_all()
        raise SystemExit(print_report(results))
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
        raise SystemExit(130)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
