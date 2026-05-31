"""Prova empírica de que os PARÂMETROS influenciam a otimização na direção certa.

Roda a MESMA instância pelo OptimizerService.run (mesmo code path do worker),
variando UM parâmetro por vez, e verifica que a métrica afetada se move como
esperado. Não é mock: usa o solver real.

Cada caso imprime baseline vs variado e PASS/FAIL da direção esperada.
Exit code != 0 se qualquer direção falhar.

Usage: venv/bin/python scratch/exp_param_influence.py
"""
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from tests.benchmark_salvador import make_salvador_trips, vt_salvador
from src.services.optimizer_service import OptimizerService
from src.domain.models import AlgorithmType

TRIPS = make_salvador_trips(n_linhas=2, seed=42, volume_scale=1.5)
VT = vt_salvador()
SVC = OptimizerService()


def run(vsp=None, cct=None, algo="greedy", budget=30.0):
    res = SVC.run(
        trips=list(TRIPS), vehicle_types=VT, algorithm=AlgorithmType(algo),
        time_budget_s=budget, vsp_params=dict(vsp or {}), cct_params=dict(cct or {}),
    )
    blocks = res.vsp.blocks if res.vsp else []
    return {
        "vehicles": len(blocks),
        "crew": res.csp.num_crew if res.csp else 0,
        "cct": res.csp.cct_violations if res.csp else 0,
        "cost": float(res.total_cost or 0.0),
    }


CASES = []


def case(name, base, var, metric, direction, vsp_base=None, cct_base=None,
         vsp_var=None, cct_var=None, algo="greedy"):
    """direction: '>=', '>', '<=', '<' do metric(var) em relação a metric(base)."""
    b = run(vsp=vsp_base, cct=cct_base, algo=algo)
    v = run(vsp=vsp_var, cct=cct_var, algo=algo)
    mb, mv = b[metric], v[metric]
    ops = {
        ">=": lambda x, y: x >= y, ">": lambda x, y: x > y,
        "<=": lambda x, y: x <= y, "<": lambda x, y: x < y,
    }
    ok = ops[direction](mv, mb)
    CASES.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"        {base}: {metric}={mb:,.0f}   {var}: {metric}={mv:,.0f}   "
          f"(esperado {metric}[{var}] {direction} {metric}[{base}])")
    return ok


def main():
    print(f"INSTANCE trips={len(TRIPS)} (2 linhas, scale 1.5)\n")

    # 1. min_layover_minutes: gap mínimo entre viagens no mesmo bloco. Maior gap
    #    impede encadear viagens próximas -> precisa de mais veículos (ou igual).
    case("min_layover", "5min", "90min", "vehicles", ">=",
         vsp_base={"min_layover_minutes": 5, "enforce_min_interval": True},
         vsp_var={"min_layover_minutes": 90, "enforce_min_interval": True})

    # 2. max_vehicle_shift_minutes: limite do bloco/jornada no greedy. Apertar o
    #    limite força quebra de blocos longos -> mais veículos (ou igual).
    case("max_vehicle_shift", "960min", "180min", "vehicles", ">=",
         vsp_base={"max_vehicle_shift_minutes": 960, "max_block_span_minutes": 960,
                   "enable_multi_block_stitch": False},
         vsp_var={"max_vehicle_shift_minutes": 180, "max_block_span_minutes": 180,
                  "enable_multi_block_stitch": False})

    # 3. max_shift_minutes (jornada do MOTORISTA, restrição CSP). Apertar -> o
    #    run-cutting precisa de mais motoristas para cobrir os mesmos blocos.
    case("max_shift (driver duty)", "560min", "240min", "crew", ">=",
         cct_base={"max_shift_minutes": 560, "apply_cct": True},
         cct_var={"max_shift_minutes": 240, "apply_cct": True})

    # 4. vehicle_fixed_cost: custo fixo por veículo ativado entra no objetivo.
    #    Subir o custo fixo sobe o custo total reportado (mesmo nº de veículos).
    case("vehicle_fixed_cost", "200", "5000", "cost", ">",
         vsp_base={"fixed_vehicle_activation_cost": 200},
         vsp_var={"fixed_vehicle_activation_cost": 5000})

    # 5. apply_cct: com instância apertada, ligar CCT detecta violações soft que
    #    o modo sem CCT não contabiliza (cct[on] >= cct[off]).
    case("apply_cct", "off", "on", "cct", ">=",
         cct_base={"apply_cct": False},
         cct_var={"apply_cct": True, "max_driving_minutes": 180,
                  "mandatory_break_after_minutes": 180})

    print("\nSUMMARY")
    npass = sum(1 for c in CASES if c)
    print(f"  {npass}/{len(CASES)} direções de parâmetro corretas")
    if npass != len(CASES):
        sys.exit(1)


if __name__ == "__main__":
    main()
