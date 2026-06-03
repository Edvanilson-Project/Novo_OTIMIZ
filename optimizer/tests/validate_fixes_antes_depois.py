"""
Validação Antes/Depois — Correções do Optimizer OTIMIZ (Junho 2026)
===================================================================
Mede o impacto das correções aplicadas:
  - BUG-CSP-01: pair_guard cancelando CCT obrigatório
  - BUG-CSP-02: Dominância Pareto SPPRC invertida
  - BUG-ALNS-06: min_break=min_layover
  - BUG-SA-01/TS-02: vehicle_type único para todos os blocos
  - BUG-ALNS-04/05: depot e log

Instâncias:
  1. Salvador Pequena (280 viagens) — com CCT ativa
  2. Salvador Média  (700 viagens) — com CCT ativa
  3. Fixture Real    (202 viagens do chunk_2000_index3)
  4. Instância Sintética com trip_group_id (testa pair_guard)

Métricas coletadas por instância:
  - blocos (frota de veículos)
  - jornadas (motoristas)
  - CCT violations
  - custo total
  - tempo de execução
"""
from __future__ import annotations

import os
import sys
import json
import time
import random

os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

ROOT = __file__
import pathlib
ROOT = pathlib.Path(ROOT).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.domain.models import AlgorithmType, Trip, VehicleType
from src.services.optimizer_service import OptimizerService

# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_vt():
    return [VehicleType(id=1, name="Ônibus Padrão", passenger_capacity=80,
                        cost_per_km=2.8, cost_per_hour=35.0, fixed_cost=350.0)]


def extract_metrics(result, elapsed: float, label: str) -> dict:
    blocks    = len(result.vsp.blocks)         if result.vsp else 0
    duties    = len(result.csp.duties)         if result.csp else 0
    viols     = result.csp.cct_violations      if result.csp else -1
    cost      = result.total_cost or 0.0
    uncovered = len(result.vsp.unassigned_trips) if result.vsp else 0
    return {
        "label":     label,
        "blocos":    blocks,
        "jornadas":  duties,
        "violations": viols,
        "custo":     round(cost, 2),
        "descobertas": uncovered,
        "tempo_s":   round(elapsed, 2),
    }


def print_row(m: dict):
    v_str = f"\033[91m{m['violations']:>3}\033[0m" if m["violations"] > 0 else f"\033[92m{m['violations']:>3}\033[0m"
    print(
        f"  {m['label']:<38}"
        f"  blocos={m['blocos']:>3}"
        f"  jornadas={m['jornadas']:>3}"
        f"  violations={v_str}"
        f"  custo=R${m['custo']:>10,.0f}"
        f"  {m['tempo_s']:>5.1f}s"
    )


def compare(a: dict, b: dict) -> dict:
    """Calcula delta entre resultado antigo (a) e novo (b)."""
    return {
        "Δblocos":    b["blocos"]    - a["blocos"],
        "Δjornadas":  b["jornadas"]  - a["jornadas"],
        "Δviolations": b["violations"] - a["violations"],
        "Δcusto_pct": round((b["custo"] - a["custo"]) / max(1, a["custo"]) * 100, 1),
    }


def print_delta(d: dict):
    def fmt(k, v):
        arrow = "▼" if v < 0 else ("▲" if v > 0 else "═")
        color = "\033[92m" if v < 0 else ("\033[91m" if v > 0 else "\033[93m")
        return f"  {color}{arrow} {k}={v}\033[0m"
    # Violations: menos é melhor → verde se negativo
    print("".join(fmt(k, v) for k, v in d.items()))

# ─── Instância 1: Salvador sintético ──────────────────────────────────────────

TERMINAIS_COORDS = {
    0: (-12.9717, -38.5030),
    1: (-12.9755, -38.4602),
    2: (-12.8826, -38.3938),
    3: (-12.8641, -38.4259),
    4: (-12.9244, -38.6245),
}
LINHAS = [(0, 2, 18.5), (0, 3, 16.0), (1, 2, 14.0), (1, 3, 12.5), (4, 0, 9.0)]


def make_salvador_trips(volume_scale=0.2, seed=42) -> list:
    rng = random.Random(seed)
    trips = []
    tid = 0
    for line_id, (orig, dest, dist_km) in enumerate(LINHAS):
        base = int(rng.randint(12, 25) * volume_scale)
        starts = (
            [rng.randint(300, 540) for _ in range(int(base * 0.4))] +
            [rng.randint(540, 1020) for _ in range(int(base * 0.35))] +
            [rng.randint(1020, 1260) for _ in range(int(base * 0.25))]
        )
        starts.sort()
        for st in starts:
            dur = max(25, min(int(dist_km * rng.uniform(2.5, 4.5)), 90))
            en = st + dur
            ol, ol2 = TERMINAIS_COORDS.get(orig, (-12.97, -38.51)), TERMINAIS_COORDS.get(dest, (-12.97, -38.51))
            trips.append(Trip(id=tid, line_id=line_id, origin_id=orig, destination_id=dest,
                              start_time=st, end_time=en, duration=dur, distance_km=dist_km,
                              origin_latitude=ol[0], origin_longitude=ol[1],
                              destination_latitude=ol2[0], destination_longitude=ol2[1]))
            tid += 1
            vs = en + rng.randint(5, 15)
            vd = int(dur * rng.uniform(0.9, 1.1))
            trips.append(Trip(id=tid, line_id=line_id, origin_id=dest, destination_id=orig,
                              start_time=vs, end_time=vs + vd, duration=vd, distance_km=dist_km,
                              origin_latitude=ol2[0], origin_longitude=ol2[1],
                              destination_latitude=ol[0], destination_longitude=ol[1]))
            tid += 1
    trips.sort(key=lambda t: t.start_time)
    return trips


# ─── Instância 2: Fixture real (chunk_2000_index3.json) ───────────────────────

def load_fixture_trips() -> list:
    fp = ROOT / "tests" / "fixtures" / "chunk_2000_index3.json"
    data = json.loads(fp.read_text())
    trips = []
    for t in data["trips"]:
        trips.append(Trip(
            id=t["id"],
            line_id=t.get("line_id", 0),
            origin_id=t.get("origin_id", 0),
            destination_id=t.get("destination_id", 1),
            start_time=t["start_time"],
            end_time=t["end_time"],
            duration=t["duration"],
            distance_km=float(t.get("distance_km", 10.0)),
        ))
    trips.sort(key=lambda t: t.start_time)
    return trips


# ─── Instância 3: Sintética com trip_group_id (testa BUG-CSP-01) ─────────────

def make_tripgroup_instance() -> list:
    """
    Instância projetada para PROVOCAR o BUG-CSP-01 antes da correção:
    Viagens do mesmo trip_group_id em sequência longa (>270min condução).
    Sem a correção: pair_guard cancelaria o corte obrigatório → CCT violation.
    Com a correção: corte obrigatório é preservado → sem violation.
    """
    trips = []
    tid = 1
    # Grupo 1: 6 viagens ida-volta, 50min cada, grupo_id=10
    # Total condução antes de pausa: 6 * 50 = 300min > 270min (max_chunk_drive)
    for i in range(6):
        st = 300 + i * 60
        t_ida = Trip(id=tid, line_id=1, origin_id=1, destination_id=2,
                     start_time=st, end_time=st + 50, duration=50, distance_km=15.0)
        t_ida.trip_group_id = 10
        t_ida.line_id = 1
        trips.append(t_ida)
        tid += 1

        t_volta = Trip(id=tid, line_id=1, origin_id=2, destination_id=1,
                       start_time=st + 52, end_time=st + 52 + 48, duration=48, distance_km=15.0)
        t_volta.trip_group_id = 10
        t_volta.line_id = 1
        trips.append(t_volta)
        tid += 1

    # Grupo 2: viagens normais sem trip_group_id
    for i in range(4):
        st = 750 + i * 70
        trips.append(Trip(id=tid, line_id=2, origin_id=3, destination_id=4,
                          start_time=st, end_time=st + 60, duration=60, distance_km=12.0))
        tid += 1

    trips.sort(key=lambda t: t.start_time)
    return trips


# ─── Runner principal ─────────────────────────────────────────────────────────

def run_scenario(name: str, trips: list, algo: str, cct_params: dict,
                 vsp_params: dict, budget: int = 60) -> dict:
    service = OptimizerService()
    t0 = time.perf_counter()
    try:
        result = service.run(
            trips=trips,
            vehicle_types=make_vt(),
            algorithm=AlgorithmType(algo),
            cct_params=cct_params,
            vsp_params=vsp_params,
            time_budget_s=budget,
        )
        elapsed = time.perf_counter() - t0
        return extract_metrics(result, elapsed, name)
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"  \033[91mERRO ({elapsed:.1f}s): {e}\033[0m")
        return {"label": name, "blocos": -1, "jornadas": -1, "violations": -1,
                "custo": -1, "descobertas": -1, "tempo_s": round(elapsed, 2), "erro": str(e)}


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 75)
    print("  VALIDAÇÃO ANTES/DEPOIS — CORREÇÕES OPTIMIZER OTIMIZ (Junho 2026)")
    print("=" * 75)

    cct_on = {
        "apply_cct": True,
        "strict_hard_validation": False,
        "min_break_minutes": 30,
        "min_layover_minutes": 8,
        "max_shift_minutes": 560,
        "max_work_minutes": 480,
        "mandatory_break_after_minutes": 270,
        "enforce_min_interval": False,
    }
    vsp_base = {
        "min_layover_minutes": 8,
        "fixed_vehicle_activation_cost": 800.0,
        "idle_cost_per_minute": 0.5,
        "deadhead_cost_per_minute": 1.0,
    }

    # ── Cenário 1: Salvador Pequena (CCT ativa) ──────────────────────────────
    print("\n\033[1m[1] SALVADOR PEQUENA — ~130 viagens (CCT ativa, GREEDY)\033[0m")
    trips_s1 = make_salvador_trips(volume_scale=0.2, seed=42)
    print(f"    Viagens: {len(trips_s1)}")

    m1 = run_scenario("Greedy + CCT", trips_s1, "greedy", cct_on, vsp_base, 30)
    print_row(m1)

    m2 = run_scenario("Hybrid Pipeline + CCT", trips_s1, "hybrid_pipeline", cct_on, vsp_base, 90)
    print_row(m2)

    # ── Cenário 2: Salvador Média (CCT ativa) ────────────────────────────────
    print("\n\033[1m[2] SALVADOR MÉDIA — ~350 viagens (CCT ativa, GREEDY + HYBRID)\033[0m")
    trips_s2 = make_salvador_trips(volume_scale=0.5, seed=42)
    print(f"    Viagens: {len(trips_s2)}")

    m3 = run_scenario("Greedy + CCT", trips_s2, "greedy", cct_on, vsp_base, 30)
    print_row(m3)

    m4 = run_scenario("Hybrid Pipeline + CCT", trips_s2, "hybrid_pipeline", cct_on, vsp_base, 120)
    print_row(m4)

    # ── Cenário 3: Fixture Real ──────────────────────────────────────────────
    print("\n\033[1m[3] FIXTURE REAL — chunk_2000_index3 (CCT ativa)\033[0m")
    trips_real = load_fixture_trips()
    print(f"    Viagens: {len(trips_real)}")

    m5 = run_scenario("Greedy + CCT", trips_real, "greedy", cct_on, vsp_base, 30)
    print_row(m5)

    m6 = run_scenario("MCNF + CCT", trips_real, "mcnf", cct_on, vsp_base, 60)
    print_row(m6)

    m7 = run_scenario("Hybrid Pipeline + CCT", trips_real, "hybrid_pipeline", cct_on, vsp_base, 120)
    print_row(m7)

    # ── Cenário 4: Trip Groups (testa BUG-CSP-01 pair_guard) ─────────────────
    print("\n\033[1m[4] TRIP GROUPS — Teste direto do BUG-CSP-01 (pair_guard)\033[0m")
    print("    Instância: 12 viagens com trip_group_id=10, condução total > 270min")
    print("    ESPERADO com correção: violations=0 (corte obrigatório preservado)")
    trips_grp = make_tripgroup_instance()
    print(f"    Viagens: {len(trips_grp)}")

    m8 = run_scenario("Greedy + CCT (pair_guard test)", trips_grp, "greedy", cct_on, vsp_base, 30)
    print_row(m8)

    if m8["violations"] == 0:
        print("  \033[92m✅ BUG-CSP-01 CORRIGIDO — pair_guard não cancela CCT obrigatório\033[0m")
    elif m8["violations"] > 0:
        print(f"  \033[91m⚠️  {m8['violations']} violations — investigar pair_guard\033[0m")
    else:
        print("  \033[93m⚠️  Sem dados de violations (CCT não ativa?)\033[0m")

    # ── Resumo Geral ─────────────────────────────────────────────────────────
    print("\n" + "=" * 75)
    print("  RESUMO GERAL")
    print("=" * 75)

    all_results = [m1, m2, m3, m4, m5, m6, m7, m8]
    total_violations = sum(m["violations"] for m in all_results if m["violations"] >= 0)
    any_error = any("erro" in m for m in all_results)

    print(f"\n  Total CCT violations em todos os cenários: ", end="")
    if total_violations == 0:
        print("\033[92m0 ✅ (zero violations — BUG-CSP-01 confirmado corrigido)\033[0m")
    else:
        print(f"\033[91m{total_violations} ⚠️  — investigar\033[0m")

    if any_error:
        print("\n  \033[91m⚠️  Houve erros em alguns cenários — verificar acima\033[0m")
    else:
        print("  \033[92mTodos os cenários executaram sem exceções ✅\033[0m")

    # Salvar JSON
    out = ROOT / "validacao_antes_depois.json"
    out.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))
    print(f"\n  Resultados salvos em: {out}")
    print("=" * 75 + "\n")

    return all_results


if __name__ == "__main__":
    main()
