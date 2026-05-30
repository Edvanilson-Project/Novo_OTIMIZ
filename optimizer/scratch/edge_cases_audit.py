"""Auditoria de robustez: cenários de borda x todos os algoritmos.

Caça bugs reais: crash, cobertura errada, overlaps, invariantes violados.
Cada cenário é construído à mão com propriedade esperada conhecida.
"""
import sys, os, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from src.domain.models import Trip, VehicleType, AlgorithmType
from src.services.optimizer_service import OptimizerService

VT = [VehicleType(id=1, name="BUS", passenger_capacity=60, fixed_cost=800, cost_per_km=2.5, cost_per_hour=30)]
ALGOS = ["greedy", "mcnf", "hybrid_pipeline", "simulated_annealing", "set_partitioning",
         "branch_and_price", "assignment_vsp", "joint_timetable", "regional", "alns"]


def T(i, s, e, o=1, d=1, grp=None, dh=None):
    return Trip(id=i, line_id=1, start_time=s, end_time=e, origin_id=o, destination_id=d,
                duration=e - s, distance_km=max(1.0, (e - s) * 0.4), trip_group_id=grp,
                deadhead_times=dh or {})


def scenarios():
    return {
        "vazio": ([], 0),
        "1_viagem": ([T(1, 0, 60)], 1),
        "2_sobrepostas": ([T(1, 0, 60), T(2, 10, 70)], 2),           # min blocos = 2
        "10_concorrentes": ([T(i, 0, 60) for i in range(1, 11)], 10),  # min blocos = 10
        "cadeia_5_mesmo_terminal": ([T(i, (i-1)*70, (i-1)*70+60) for i in range(1, 6)], 1),  # 1 bloco
        "overnight": ([T(1, 1380, 1440), T(2, 1450, 1510), T(3, 1520, 1580)], 1),  # cruza meia-noite
        "duracao_zero": ([T(1, 100, 100), T(2, 100, 160)], None),
        "deadhead_impossivel": ([T(1, 0, 60, o=1, d=2, dh={1: 9999}),
                                  T(2, 70, 130, o=1, d=2, dh={1: 9999})], 2),  # não encadeia (dh enorme)
        "pares_ida_volta": ([T(1, 0, 60, o=1, d=2, grp=10), T(2, 70, 130, o=2, d=1, grp=10)], 1),
    }


def overlaps(blocks):
    n = 0
    for b in blocks:
        ts = sorted(b.trips, key=lambda t: t.start_time)
        n += sum(1 for a, c in zip(ts, ts[1:]) if c.start_time < a.end_time)
    return n


def main():
    svc = OptimizerService()
    bugs = []
    for name, (trips, min_blocks) in scenarios().items():
        n = len(trips)
        for algo in ALGOS:
            try:
                res = svc.run(trips=list(trips), vehicle_types=VT, algorithm=AlgorithmType(algo),
                              time_budget_s=10, vsp_params={"min_break_minutes": 30, "min_layover_minutes": 10},
                              cct_params={})
                blocks = res.vsp.blocks if res.vsp else []
                covered = len({t.id for b in blocks for t in b.trips})
                ovl = overlaps(blocks)
                cost = res.total_cost or 0
                problems = []
                if covered != n:
                    problems.append(f"cobertura {covered}/{n}")
                if ovl:
                    problems.append(f"overlaps={ovl}")
                if n > 0 and cost < 0:
                    problems.append(f"custo<0 ({cost})")
                if min_blocks is not None and n > 0 and len(blocks) < min_blocks:
                    problems.append(f"blocos {len(blocks)}<min{min_blocks}")
                # bloco com viagens duplicadas?
                allt = [t.id for b in blocks for t in b.trips]
                if len(allt) != len(set(allt)):
                    problems.append(f"DUPLICATA (trips={len(allt)} unicos={len(set(allt))})")
                if problems:
                    bugs.append(f"[{name} / {algo}] " + ", ".join(problems))
            except Exception as e:
                bugs.append(f"[{name} / {algo}] CRASH: {type(e).__name__}: {str(e)[:100]}")
    print(f"cenarios={len(scenarios())} algoritmos={len(ALGOS)} combinacoes={len(scenarios())*len(ALGOS)}")
    if bugs:
        print(f"\n*** {len(bugs)} PROBLEMA(S) ENCONTRADO(S) ***")
        for b in bugs:
            print("  -", b)
    else:
        print("\nOK: nenhum problema (sem crash, cobertura correta, 0 overlaps, sem duplicata).")


if __name__ == "__main__":
    main()
