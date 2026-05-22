"""
Benchmark GTFS Real — SUNT Salvador-BA.

Usa os fixtures reais do dataset SUNT (LabIA-UFBA, CC-BY 4.0):
  - stops.txt:     2975 paradas reais de Salvador
  - routes.txt:    412 linhas reais de Salvador
  - trips.txt:     20 viagens da linha 1230 (rota 4089)
  - stop_times.txt: horários reais da viagem 1046761_D_1_0 (Sussuarana→Barra, 55 min)

Estratégia:
  1. Carrega as paradas e rotas reais.
  2. A partir do único par de horários reais (08:30→09:25, 55 min),
     extrapola um dia operacional completo (05:00–23:00) com headway de 30 min
     para as 10 primeiras rotas reais — produzindo ~360 viagens estruturalmente reais.
  3. Roda Greedy e JointSolver (tabu, 3 rounds).
  4. Reporta: blocos, violações CCT, custo, redução.

Objetivo: garantir que o optimizer lida corretamente com dados derivados de GTFS reais
(IDs reais de paradas, linhas reais de Salvador).
"""
from __future__ import annotations

import os
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import csv
import io
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "src"
    / "modules"
    / "gtfs"
    / "fixtures"
    / "sunt_salvador"
)

import sys
sys.path.insert(0, str(ROOT))

from src.domain.models import Trip, VehicleType
from src.algorithms.integrated.joint_solver import JointSolver
from src.algorithms.vsp.greedy import GreedyVSP
from src.algorithms.csp.greedy import GreedyCSP


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_csv(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(
        io.StringIO(text),
        quoting=csv.QUOTE_ALL,
    )
    return [
        {k.strip().strip('"'): v.strip().strip('"') for k, v in row.items()}
        for row in reader
    ]


def _hhmmss_to_minutes(t: str) -> int:
    parts = t.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def build_real_salvador_trips(max_routes: int = 10) -> tuple[list[Trip], list[dict], list[dict]]:
    """
    Gera viagens baseadas em dados SUNT reais.

    - Stop IDs reais do Salvador (amostra dos 2975 disponíveis)
    - Route IDs reais (primeiros max_routes de 412)
    - Timing base real: 08:30→09:25 (55 min), extrapolado para dia completo (headway 30 min)
    - Retorno: trip_id alternando IDA/VOLTA entre as 2 terminais reais da rota

    Retorna (trips, stops_sample, routes_sample).
    """
    stops = _load_csv(FIXTURE_DIR / "stops.txt")
    routes = _load_csv(FIXTURE_DIR / "routes.txt")

    # Sampleamos os stops reais como possíveis terminais
    stop_ids = [s["stop_id"] for s in stops if s.get("stop_id")]
    # Mapeamos stop_id de string para int (índice único)
    stop_id_map = {sid: idx + 1 for idx, sid in enumerate(stop_ids)}

    routes_sample = routes[:max_routes]
    trips: list[Trip] = []
    trip_id = 1

    # Timing base real (SUNT trip 1046761_D_1_0)
    BASE_DURATION = 55   # minutos (Sussuarana→Barra)
    TURNAROUND   = 10    # minutos no terminal antes de retornar
    HEADWAY      = 30    # minutos entre partidas (headway típico Salvador)
    DAY_START    = 300   # 05:00
    DAY_END      = 1380  # 23:00

    for r_idx, route in enumerate(routes_sample):
        route_id = int(route["route_id"])
        # Seleciona 2 terminais reais para esta rota (baseado em posição no array de stops)
        base_stop_a = stop_ids[(r_idx * 7) % len(stop_ids)]
        base_stop_b = stop_ids[(r_idx * 7 + 100) % len(stop_ids)]
        origin_db   = stop_id_map[base_stop_a]
        dest_db     = stop_id_map[base_stop_b]

        # Duration varia por linha: ±10 min do base real
        duration = BASE_DURATION + (r_idx % 5) * 5 - 10  # 45–65 min

        t = DAY_START
        while t + duration <= DAY_END:
            # IDA
            trips.append(Trip(
                id=trip_id,
                line_id=route_id,
                origin_id=origin_db,
                destination_id=dest_db,
                start_time=t,
                end_time=t + duration,
                duration=duration,
            ))
            trip_id += 1

            ret_start = t + duration + TURNAROUND
            if ret_start + duration <= DAY_END:
                # VOLTA
                trips.append(Trip(
                    id=trip_id,
                    line_id=route_id,
                    origin_id=dest_db,
                    destination_id=origin_db,
                    start_time=ret_start,
                    end_time=ret_start + duration,
                    duration=duration,
                ))
                trip_id += 1

            t += HEADWAY

    return trips, stops, routes_sample


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def salvador_trips_and_vt():
    trips, stops, routes = build_real_salvador_trips(max_routes=10)
    vt = [VehicleType(id=1, name="BUS", passenger_capacity=60, fixed_cost=800)]
    return trips, vt, stops, routes


def test_fixtures_loaded(salvador_trips_and_vt):
    trips, _, stops, routes = salvador_trips_and_vt
    # stops.txt SUNT completo: 2975 paradas reais de Salvador
    assert len(stops) == 2975, f"Expected 2975 stops, got {len(stops)}"
    # routes: sample das 10 primeiras linhas reais usadas no benchmark
    assert len(routes) == 10, f"Expected 10 sampled routes, got {len(routes)}"
    # 10 rotas × ~36 headways × 2 (IDA+VOLTA) ≈ ~600+ trips
    assert len(trips) >= 200, f"Too few trips generated: {len(trips)}"
    assert all(t.start_time < t.end_time for t in trips), "All trips must have start < end"
    assert all(t.origin_id != t.destination_id for t in trips), "All trips must have distinct terminals"


def test_trip_times_are_real_derived(salvador_trips_and_vt):
    """Durations are based on real SUNT timing (45–65 min range from 55 min base)."""
    trips, _, _, _ = salvador_trips_and_vt
    durations = [t.duration for t in trips]
    assert min(durations) >= 40, f"Min duration too short: {min(durations)}"
    assert max(durations) <= 70, f"Max duration too long: {max(durations)}"
    # All trips within 05:00–23:00
    assert all(300 <= t.start_time < 1380 for t in trips)
    assert all(t.end_time <= 1440 for t in trips)


def test_greedy_solver_real_data(salvador_trips_and_vt):
    trips, vt, _, _ = salvador_trips_and_vt
    t0 = time.time()
    vsp = GreedyVSP()
    vsp_sol = vsp.solve(trips, vt)
    csp = GreedyCSP()
    csp_sol = csp.solve(vsp_sol.blocks, trips)
    elapsed = time.time() - t0

    print(f"\n[Greedy] trips={len(trips)} blocks={len(vsp_sol.blocks)} "
          f"duties={len(csp_sol.duties)} cct_violations={csp_sol.cct_violations} "
          f"elapsed={elapsed:.1f}s")

    assert len(vsp_sol.blocks) > 0
    assert len(csp_sol.duties) > 0
    # All input trips should be covered
    covered = {t.id for block in vsp_sol.blocks for t in block.trips}
    assert len(covered) == len(trips), f"Uncovered trips: {len(trips) - len(covered)}"


def test_joint_solver_real_data(salvador_trips_and_vt):
    trips, vt, _, _ = salvador_trips_and_vt
    t0 = time.time()
    solver = JointSolver(
        time_budget_s=60,
        vsp_algorithm="tabu",
        csp_algorithm="greedy",
        max_rounds=3,
    )
    result = solver.solve(trips, vt)
    elapsed = time.time() - t0

    vsp_sol = result.vsp
    csp_sol = result.csp

    print(f"\n[Joint] trips={len(trips)} blocks={len(vsp_sol.blocks)} "
          f"duties={len(csp_sol.duties)} cct_violations={csp_sol.cct_violations} "
          f"cost={result.total_cost:.0f} elapsed={elapsed:.1f}s")

    assert len(vsp_sol.blocks) > 0
    assert len(csp_sol.duties) > 0
    assert result.total_cost > 0
    # All trips must be assigned (no orphans)
    covered = {t.id for block in vsp_sol.blocks for t in block.trips}
    assert len(covered) == len(trips), f"Unassigned trips: {len(trips) - len(covered)}"


def test_joint_vs_greedy_improvement(salvador_trips_and_vt):
    """Joint solver must not be worse than greedy on CCT violations with real data."""
    trips, vt, _, _ = salvador_trips_and_vt

    vsp_g = GreedyVSP()
    vsp_sol_g = vsp_g.solve(trips, vt)
    csp_g = GreedyCSP()
    csp_sol_g = csp_g.solve(vsp_sol_g.blocks, trips)
    greedy_violations = csp_sol_g.cct_violations

    solver = JointSolver(time_budget_s=60, vsp_algorithm="tabu", csp_algorithm="greedy", max_rounds=3)
    result = solver.solve(trips, vt)
    joint_violations = result.csp.cct_violations

    print(f"\n[Comparison] greedy_viol={greedy_violations} joint_viol={joint_violations} "
          f"delta={greedy_violations - joint_violations:+d}")

    # Joint must not be significantly worse (allow ≤10% regression on larger violations)
    max_allowed = max(greedy_violations, int(greedy_violations * 1.1) + 1)
    assert joint_violations <= max_allowed, (
        f"Joint solver regressed on real data: {joint_violations} > {max_allowed}"
    )


def test_real_stop_ids_used(salvador_trips_and_vt):
    """Verify that trips use real Salvador stop IDs (mapped from SUNT stops.txt)."""
    trips, _, stops, _ = salvador_trips_and_vt
    stop_ids_set = {i + 1 for i in range(len(stops))}  # mapped IDs 1..N
    for t in trips[:20]:
        assert t.origin_id in stop_ids_set, f"origin_id {t.origin_id} not in real stop range"
        assert t.destination_id in stop_ids_set, f"destination_id {t.destination_id} not in real stop range"


def test_real_route_ids_used(salvador_trips_and_vt):
    """Verify trips use real Salvador route IDs from SUNT routes.txt."""
    trips, _, _, routes = salvador_trips_and_vt
    real_route_ids = {int(r["route_id"]) for r in routes}
    for t in trips[:20]:
        assert t.line_id in real_route_ids, f"line_id {t.line_id} not a real Salvador route ID"
