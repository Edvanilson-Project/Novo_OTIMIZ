"""
Benchmark com dados representativos de Salvador-BA.

DADOS DE REFERÊNCIA (fontes públicas):
- Salvador tem ~2.600 ônibus, ~136 linhas (SEMOB-Salvador, relatório 2023)
- Frota operante estimada: ~1.800/dia (65% da frota total)
- Estimativa de viagens/dia por linha: 10-25 (linhas radiais e transversais)
- Estimativa total de viagens/dia: ~1.400-1.800
- Terminais principais: Lapa (0), Iguatemi (1), Mussurunga (2), Pirajá (3),
  Bom Despacho (4), Ribeira (5), Acesso Norte (6), Shopping Bela Vista (7)
- Horário de pico: 5h-9h (manhã) e 17h-21h (tarde)
- Distância média por linha: 8-22 km
- Duração média de viagem: 35-70 min (tráfego Salvador)

NÃO são dados reais GTFS — são dados sintéticos realistas baseados em
características públicas conhecidas da rede de Salvador.
"""
from __future__ import annotations

import os
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import random
import time
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from src.domain.models import AlgorithmType, Trip, VehicleType
from src.services.optimizer_service import OptimizerService

# Terminais reais de Salvador (id, nome, característica operacional)
TERMINAIS = [
    (0, "Lapa", "central"),
    (1, "Iguatemi", "shopping_integrado"),
    (2, "Mussurunga", "periferia_norte"),
    (3, "Pirajá", "periferia_norte"),
    (4, "Bom Despacho", "ferries_ilha"),
    (5, "Ribeira", "orla"),
    (6, "Acesso Norte", "saida_cidade"),
    (7, "Bela Vista", "shopping_integrado"),
    (8, "Lapa_Orla", "orla_central"),
    (9, "Cajazeiras", "periferia_leste"),
]

# Linhas de Salvador com características aproximadas (origem, destino, distância, frq_pico)
LINHAS = [
    # Linhas radiais (Centro ↔ Periferia)
    (0, 2, 18.5),   # Lapa-Mussurunga
    (0, 3, 16.0),   # Lapa-Pirajá
    (0, 9, 22.0),   # Lapa-Cajazeiras
    (0, 5, 12.0),   # Lapa-Ribeira (orla)
    (0, 6, 25.0),   # Lapa-Acesso Norte
    # Linhas transversais (Periferia ↔ Periferia)
    (1, 2, 14.0),   # Iguatemi-Mussurunga
    (1, 3, 12.5),   # Iguatemi-Pirajá
    (1, 9, 18.0),   # Iguatemi-Cajazeiras
    (7, 2, 11.0),   # Bela Vista-Mussurunga
    (7, 3, 10.5),   # Bela Vista-Pirajá
    # Linhas de orla e especiais
    (5, 8, 8.0),    # Ribeira-Lapa Orla
    (4, 0, 9.0),    # Bom Despacho-Lapa (via ferry area)
    (6, 1, 15.0),   # Acesso Norte-Iguatemi
    (3, 2, 7.0),    # Pirajá-Mussurunga (transversal norte)
    (9, 2, 11.0),   # Cajazeiras-Mussurunga
]


def make_salvador_trips(
    n_linhas: int = 15,
    seed: int = 42,
    volume_scale: float = 1.0,
) -> list[Trip]:
    """
    Gera viagens com características de Salvador-BA.

    volume_scale: 1.0 = ~1400 viagens (escala real diária estimada)
                  0.5 = ~700 viagens
                  0.2 = ~280 viagens
    """
    rng = random.Random(seed)
    trips = []
    trip_id = 0

    linhas = LINHAS[:n_linhas]

    for line_id, (orig, dest, dist_km) in enumerate(linhas):
        # Frequência por linha varia: radiais têm mais viagens
        base_trips = int(rng.randint(12, 25) * volume_scale)

        # Janela operacional: 5h (300min) até 23h (1380min)
        # Picos: 5h-9h e 17h-21h → frequência 2× maior nesses períodos
        intervals = []
        # Pico manhã: 5h-9h (300-540)
        for _ in range(int(base_trips * 0.4)):
            intervals.append(rng.randint(300, 540))
        # Entrepico: 9h-17h (540-1020)
        for _ in range(int(base_trips * 0.35)):
            intervals.append(rng.randint(540, 1020))
        # Pico tarde: 17h-21h (1020-1260)
        for _ in range(int(base_trips * 0.25)):
            intervals.append(rng.randint(1020, 1260))

        intervals.sort()

        for start in intervals:
            # Duração varia com congestionamento de Salvador (30-70min)
            dur = int(dist_km * rng.uniform(2.5, 4.5))  # min/km variável
            dur = max(25, min(dur, 90))
            end = start + dur

            # IDA
            trips.append(Trip(
                id=trip_id, line_id=line_id,
                origin_id=orig, destination_id=dest,
                start_time=start, end_time=end, duration=dur,
                distance_km=dist_km,
            ))
            trip_id += 1

            # VOLTA (com pequeno intervalo de terminal)
            volta_start = end + rng.randint(5, 15)
            volta_dur = int(dur * rng.uniform(0.85, 1.15))
            trips.append(Trip(
                id=trip_id, line_id=line_id,
                origin_id=dest, destination_id=orig,
                start_time=volta_start, end_time=volta_start + volta_dur, duration=volta_dur,
                distance_km=dist_km,
            ))
            trip_id += 1

    trips.sort(key=lambda t: t.start_time)
    return trips


def vt_salvador() -> list[VehicleType]:
    """Frota típica de Salvador: micro-ônibus e ônibus padrão."""
    return [
        VehicleType(
            id=1, name="Ônibus Padrão", passenger_capacity=80,
            cost_per_km=2.8, cost_per_hour=35.0, fixed_cost=350.0,
        ),
        VehicleType(
            id=2, name="Micro-ônibus", passenger_capacity=25,
            cost_per_km=1.8, cost_per_hour=20.0, fixed_cost=180.0,
        ),
    ]


def run_benchmark():
    service = OptimizerService()
    vsp_params = {
        "min_break_minutes": 30,
        "min_layover_minutes": 10,
        "force_round_trip": False,
    }

    print(f"\n{'='*70}")
    print("BENCHMARK SALVADOR-BA — Dados sintéticos representativos")
    print(f"{'='*70}")
    print(f"Referência: ~136 linhas, ~1.400-1.800 viagens/dia (SEMOB 2023)")
    print()

    scenarios = [
        ("Pequena operadora (280v)", 0.2, 15, 42),
        ("Média operadora (700v)", 0.5, 15, 42),
        ("Grande operadora (1.400v)", 1.0, 15, 42),
        ("Frota total estimada (1.400v, seed alt)", 1.0, 15, 99),
    ]

    results = []
    for label, scale, n_linhas, seed in scenarios:
        trips = make_salvador_trips(n_linhas=n_linhas, seed=seed, volume_scale=scale)
        n = len(trips)
        print(f"--- {label} ({n} viagens) ---")

        row = {"label": label, "n_trips": n}
        # B&P params calibrados com dados bimodais Salvador (benchmark 2026-05-15):
        # a 518v empata blocos com greedy mas vence em custo; mais iters/cols para >400v
        bp_iters = 5 if n < 300 else (5 if n < 600 else 3)
        bp_cols = 1000 if n < 300 else (2000 if n < 600 else 1000)
        bp_labels = 20 if n < 300 else (20 if n < 600 else 15)
        vsp_params_bp = {**vsp_params, "bp_max_pricing_iterations": bp_iters,
                         "bp_max_pricing_columns": bp_cols, "bp_max_labels_per_node": bp_labels}
        algo_configs = [
            ("greedy", 30, vsp_params),
            ("branch_and_price", min(300, n // 2 + 60), vsp_params_bp),
            ("mcnf", 60, vsp_params),
            ("hybrid_pipeline", 120, vsp_params),
        ]
        for algo, budget, ap in algo_configs:
            t0 = time.perf_counter()
            try:
                result = service.run(
                    trips=trips, vehicle_types=vt_salvador(),
                    algorithm=AlgorithmType(algo), time_budget_s=budget,
                    vsp_params=ap, cct_params={},
                )
                elapsed = time.perf_counter() - t0
                blocks = len(result.vsp.blocks) if result.vsp else 0
                duties = len(result.csp.duties) if result.csp else 0
                cost = result.total_cost or 0
                viols = result.csp.cct_violations if result.csp else -1
                uncov = len(result.vsp.unassigned_trips) if result.vsp else -1

                # CP-SAT polish ativou?
                perf = (result.meta or {}).get("performance", {})
                cpsat_ms = perf.get("phase_timings_ms", {}).get("csp_cpsat_ms")
                polish_tag = f" [CP-SAT={cpsat_ms:.0f}ms]" if cpsat_ms else ""

                print(f"  {algo:<18} {elapsed:>6.1f}s  blocos={blocks:>3}  jornadas={duties:>3}"
                      f"  custo=R${cost:>10,.0f}  viols={viols}  descobertas={uncov}{polish_tag}")
                row[algo] = {"elapsed_s": round(elapsed, 2), "blocks": blocks, "duties": duties,
                             "cost": round(cost, 2), "violations": viols, "uncovered": uncov,
                             "cpsat_activated": cpsat_ms is not None}
            except Exception as e:
                elapsed = time.perf_counter() - t0
                print(f"  {algo:<18} ERRO ({elapsed:.1f}s): {str(e)[:60]}")
                row[algo] = {"error": str(e)[:80]}
        results.append(row)
        print()

    # Análise de qualidade: todos os algoritmos vs greedy
    print(f"{'='*70}")
    print("ANÁLISE DE QUALIDADE: blocos e custo vs greedy")
    print(f"{'='*70}")
    ALGOS = ["branch_and_price", "mcnf", "hybrid_pipeline"]
    for row in results:
        g = row.get("greedy", {})
        if "error" in g or not g:
            continue
        g_cost, g_blocks = g["cost"], g["blocks"]
        parts = [f"  {row['label'][:28]:<28}  greedy={g_blocks}b/R${g_cost:>8,.0f}"]
        for algo in ALGOS:
            r = row.get(algo, {})
            if not r or "error" in r:
                parts.append(f"  {algo}=ERR")
                continue
            db = r["blocks"] - g_blocks
            dc = (r["cost"] - g_cost) / max(1, g_cost) * 100
            sign_b = "+" if db > 0 else ""
            sign_c = "+" if dc > 0 else ""
            parts.append(f"  {algo}={r['blocks']}b({sign_b}{db}) {sign_c}{dc:.1f}%")
        print("".join(parts))

    # Salvar resultado
    out_path = ROOT / "benchmark_salvador.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nResultados salvos em: {out_path}")
    return results


if __name__ == "__main__":
    run_benchmark()
