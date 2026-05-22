"""
Benchmark EV-aware B&P vs não-EV B&P vs Greedy.

Mede impacto do SoC como recurso duro no pricing:
- Custo (fixo + energia)
- Número de blocos
- Tempo de execução

Uso:
    cd optimizer
    INTERNAL_OPTIMIZER_KEY=test-strong-key-for-pytest-32chars-ok python -m tests.benchmark_ev_bp

Interpreta resultado:
    ev_cost > nev_cost → correto (custo EV inclui energia)
    ev_blocks ≈ nev_blocks → EV-awareness não infla frota
    ev_time_s  tempo aceitável mesmo com 6D label
"""
import os, random, time
from dataclasses import dataclass
from typing import List

os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")

from src.domain.models import AlgorithmType, Trip, VehicleType
from src.services.optimizer_service import OptimizerService

SEED = 42
SIZES = [30, 80, 150]
BUDGET = {30: 20, 80: 40, 150: 60}

# EV params — ônibus elétrico típico
EV_BATTERY_KWH = 300.0
EV_MIN_SOC = 0.10
EV_CHARGE_RATE_KW = 150.0
EV_ENERGY_COST_PER_KWH = 2.5
EV_KWH_PER_KM = 1.8


def make_trips(n: int, seed: int = SEED) -> List[Trip]:
    rng = random.Random(seed)
    terminals = list(range(1, 6))
    trips: List[Trip] = []
    for i in range(1, n + 1):
        start = rng.randint(300, 1200)
        dur = rng.randint(20, 90)
        orig = rng.choice(terminals)
        dest = rng.choice([t for t in terminals if t != orig])
        dist = rng.uniform(5.0, 40.0)
        t = Trip(
            id=i, line_id=rng.randint(1, 5),
            start_time=start, end_time=start + dur, duration=dur,
            origin_id=orig, destination_id=dest, distance_km=dist,
        )
        t.deadhead_times = {}
        trips.append(t)
    return trips


def make_ev_vt() -> VehicleType:
    return VehicleType(
        id=1, name="EV-Bus", passenger_capacity=60,
        fixed_cost=1200.0, is_electric=True,
        battery_capacity_kwh=EV_BATTERY_KWH,
        minimum_soc=EV_MIN_SOC,
        charge_rate_kw=EV_CHARGE_RATE_KW,
        energy_cost_per_kwh=EV_ENERGY_COST_PER_KWH,
    )


def make_nev_vt() -> VehicleType:
    return VehicleType(
        id=1, name="Diesel", passenger_capacity=60, fixed_cost=1200.0,
    )


@dataclass
class Row:
    n: int
    alg: str
    blocks: int
    cost: float
    time_s: float
    ev_soc_blocks_mid_charge: int = 0


def run(trips: List[Trip], vts: List[VehicleType], alg: str,
        budget: int, ev_kwh: float = 0.0) -> Row:
    svc = OptimizerService()
    vsp_params = {
        "bp_max_pricing_iterations": 4,
        "bp_max_pricing_columns": 500,
        "ev_kwh_per_km": ev_kwh or EV_KWH_PER_KM,
    }
    t0 = time.perf_counter()
    result = svc.run(
        trips=trips,
        vehicle_types=vts,
        algorithm=AlgorithmType(alg),
        time_budget_s=budget,
        vsp_params=vsp_params,
        cct_params={},
    )
    elapsed = time.perf_counter() - t0
    blocks = len(result.vsp.blocks) if result.vsp else 0
    cost = result.total_cost
    ev_mid = (result.meta.get("ev_soc_report") or {}).get("blocks_needing_mid_charge", 0)
    return Row(n=len(trips), alg=alg, blocks=blocks, cost=cost,
               time_s=elapsed, ev_soc_blocks_mid_charge=ev_mid)


def main():
    svc = OptimizerService()
    print(f"\n{'n':>5} {'alg':<20} {'blocks':>7} {'cost':>12} {'time_s':>8} {'mid_charge':>11}")
    print("-" * 72)
    for n in SIZES:
        trips = make_trips(n)
        budget = BUDGET[n]
        for label, vts, extra_kwh in [
            ("greedy/non-EV",   [make_nev_vt()], 0.0),
            ("bp/non-EV",       [make_nev_vt()], 0.0),
            ("bp/EV",           [make_ev_vt()],  EV_KWH_PER_KM),
        ]:
            alg_key = "greedy" if "greedy" in label else "branch_and_price"
            r = run(trips, vts, alg_key, budget, extra_kwh)
            print(f"{n:>5} {label:<20} {r.blocks:>7} {r.cost:>12.2f} {r.time_s:>8.1f} {r.ev_soc_blocks_mid_charge:>11}")
    print()


if __name__ == "__main__":
    main()
