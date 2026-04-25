"""
Stress Capacity Audit — descobre o ponto de ruptura do sistema.

Gera trips sintéticas em escala 1k, 2k, 3k, 5k e mede:
  - Tempo de resolução por fase (VSP / CSP)
  - Memória pico (RSS) — psutil opcional
  - Falhas (timeout, OOM, exceções)

Não é coletado por pytest (não tem prefixo test_).
Rode manualmente: python tests/stress_capacity_audit.py
"""
from __future__ import annotations

import gc
import os
import random
import resource
import sys
import time
from typing import List, Tuple

# Permite rodar a partir da raiz do projeto
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.algorithms.csp.greedy import GreedyCSP
from src.algorithms.csp.set_partitioning_optimized import SetPartitioningOptimizedCSP
from src.algorithms.vsp.greedy import GreedyVSP
from src.algorithms.vsp.mcnf import MCNFVSP
from src.domain.models import Trip, VehicleType


def _current_rss_mb() -> float:
    """Retorna RSS atual em MB lendo /proc/self/status (Linux)."""
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _peak_rss_mb() -> float:
    """Pico histórico (highwater) em MB."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _gen_trips(n: int, seed: int = 42) -> List[Trip]:
    """Gera n trips sintéticas espalhadas em 18 horas operacionais.

    Distribui:
      - 4 linhas (line_id ∈ {1,2,3,4})
      - 3 origens/destinos por linha (rotativo)
      - Início entre 04:00 e 22:00 (240..1320 min)
      - Duração entre 25 e 75 min
      - Distância proporcional à duração
      - Deadhead matrix dense entre todos os terminais (gerada em O(L²))
    """
    rng = random.Random(seed)
    locations = [101, 102, 103, 201, 202, 203, 301, 302, 303, 401, 402, 403]
    deadhead_pairs = {
        loc: {other: rng.randint(5, 20) for other in locations if other != loc}
        for loc in locations
    }

    trips: List[Trip] = []
    for i in range(n):
        line = (i % 4) + 1
        line_locs = locations[(line - 1) * 3:line * 3]
        if i % 2 == 0:
            origin, dest = line_locs[0], line_locs[2]
        else:
            origin, dest = line_locs[2], line_locs[0]
        start = rng.randint(240, 1320)
        duration = rng.randint(25, 75)
        trips.append(
            Trip(
                id=i + 1,
                line_id=line,
                start_time=start,
                end_time=start + duration,
                origin_id=origin,
                destination_id=dest,
                duration=duration,
                distance_km=duration * 0.4,
                depot_id=line,
                deadhead_times=deadhead_pairs[origin],
            )
        )
    return trips


def _vehicle_types() -> List[VehicleType]:
    return [VehicleType(id=1, name="Padrão", passenger_capacity=40, fixed_cost=800.0, cost_per_km=1.5, cost_per_hour=40.0)]


def _run_phase(label: str, fn, *args, time_budget_s: float = 60.0) -> Tuple[bool, float, float, str]:
    """Executa uma função e retorna (ok, elapsed_s, delta_rss_mb, error_msg).

    delta_rss_mb usa /proc/self/status (decresce após GC), não o highwater.
    """
    gc.collect()
    rss_before = _current_rss_mb()
    t0 = time.perf_counter()
    try:
        result = fn(*args)
        elapsed = time.perf_counter() - t0
        rss_after = _current_rss_mb()
        ok = result is not None
        return ok, elapsed, rss_after - rss_before, ""
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        rss_after = _current_rss_mb()
        return False, elapsed, rss_after - rss_before, f"{type(exc).__name__}: {exc}"


def stress_audit(sizes=(1000, 2000, 3000, 5000), time_budget_s: float = 60.0):
    print(f"\n{'='*78}")
    print(f"  STRESS CAPACITY AUDIT — OTIMIZ")
    print(f"  Sizes: {sizes}  |  Budget por fase: {time_budget_s}s")
    print(f"{'='*78}\n")

    rows = []
    for n in sizes:
        print(f"━━━ N = {n} trips ━━━")
        trips = _gen_trips(n)
        vts = _vehicle_types()

        # ── VSP Greedy (baseline) ──
        ok_g, t_g, m_g, err_g = _run_phase(
            "GreedyVSP",
            lambda: GreedyVSP(vsp_params={"time_budget_s": time_budget_s}).solve(trips, vts),
        )
        print(f"  GreedyVSP        : ok={ok_g} t={t_g:7.2f}s ΔRSS={m_g:6.1f}MB {err_g}")

        # ── VSP MCNF (PuLP/CBC) ──
        ok_m, t_m, m_m, err_m = _run_phase(
            "MCNFVSP",
            lambda: MCNFVSP(vsp_params={"time_budget_s": time_budget_s}).solve(trips, vts),
        )
        print(f"  MCNFVSP          : ok={ok_m} t={t_m:7.2f}s ΔRSS={m_m:6.1f}MB {err_m}")

        # ── CSP Greedy ──
        if ok_g:
            vsp_sol = GreedyVSP(vsp_params={"time_budget_s": time_budget_s}).solve(trips, vts)
            ok_c, t_c, m_c, err_c = _run_phase(
                "GreedyCSP",
                lambda: GreedyCSP().solve(vsp_sol.blocks, trips),
            )
            print(f"  GreedyCSP        : ok={ok_c} t={t_c:7.2f}s ΔRSS={m_c:6.1f}MB blocks={len(vsp_sol.blocks)} {err_c}")

            # ── CSP Set Partitioning Optimized (só se Greedy passou) ──
            if ok_c and len(vsp_sol.blocks) <= 500:  # poda agressiva acima de 500 blocos
                ok_sp, t_sp, m_sp, err_sp = _run_phase(
                    "SetPartOpt",
                    lambda: SetPartitioningOptimizedCSP(
                        vsp_params={"time_budget_s": time_budget_s, "max_generated_columns": 1500}
                    ).solve(vsp_sol.blocks, trips),
                )
                print(f"  SetPartOptCSP    : ok={ok_sp} t={t_sp:7.2f}s ΔRSS={m_sp:6.1f}MB {err_sp}")
            else:
                print(f"  SetPartOptCSP    : SKIPPED (blocos={len(vsp_sol.blocks) if ok_c else 'N/A'} > 500)")

        rows.append({
            "n": n,
            "greedy_vsp_ok": ok_g, "greedy_vsp_s": round(t_g, 2),
            "mcnf_vsp_ok": ok_m, "mcnf_vsp_s": round(t_m, 2),
        })
        print()

    print("="*78)
    print("Resumo:")
    for r in rows:
        print(f"  N={r['n']:5d}: GreedyVSP={r['greedy_vsp_s']:7.2f}s  MCNF={r['mcnf_vsp_s']:7.2f}s")
    print("="*78)


if __name__ == "__main__":
    sizes = (1000, 2000, 3000)
    if len(sys.argv) > 1:
        sizes = tuple(int(s) for s in sys.argv[1].split(","))
    stress_audit(sizes=sizes, time_budget_s=120.0)
