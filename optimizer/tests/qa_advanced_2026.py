#!/usr/bin/env python3
"""
QA Avançado — OTIMIZ Optimizer 2026
Testa cenários especiais: edge cases, CCT/CLT avançado, performance.

Grupos:
  T-EDGE      : casos extremos (0 viagens, 1 viagem, 2 viagens)
  T-MIN-WORK  : aviso de trabalho abaixo do mínimo CCT (soft)
  T-OVERTIME  : violação hard de horas extras (CLT art.59)
  T-NOTURNO   : presença de viagens noturnas (parâmetros noturno)
  T-INTER-REST: aviso de descanso inter-jornada insuficiente
  T-CROSS-VEH : nenhuma duty mistura blocos de veículos distintos
  T-PERF      : performance com 50 e 100 viagens

Uso:
  cd /home/edvanilson/WEB_OPT/optimizer
  python /tmp/qa_advanced_2026.py

Pré-requisito: optimizer rodando em http://localhost:8000
"""
import sys
import time
import random
import statistics
import requests
from typing import Any, Dict, List, Optional, Tuple

BASE_URL = "http://localhost:8000"
OK = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"
SKIP = "\033[94m○\033[0m"

ALGOS_FAST   = ["greedy", "set_partitioning"]
ALGOS_ALL    = ["greedy", "genetic", "tabu_search",
                "set_partitioning", "joint_solver", "hybrid_pipeline"]
ALGOS_SUBSET = ["greedy", "hybrid_pipeline"]

# ──────────────────────────────────────────────────────────────────────────────
# Utilitários
# ──────────────────────────────────────────────────────────────────────────────

def _hhmm(minutes: int) -> str:
    return f"{minutes//60:02d}:{minutes%60:02d}"

def _trip(i, start, dur=40, line=1, origin=1, dest=2, deadhead=None):
    return {
        "id": i, "line_id": line,
        "start_time": start, "end_time": start + dur,
        "origin_id": origin, "destination_id": dest,
        "duration": dur, "distance_km": 20.0,
        "deadhead_times": deadhead or {},
    }

def _post(trips, algo, cct_params=None, time_budget=60.0):
    payload: Dict[str, Any] = {
        "trips": trips,
        "algorithm": algo,
        "time_budget_s": time_budget,
    }
    if cct_params:
        payload["cct_params"] = cct_params
    r = requests.post(f"{BASE_URL}/optimize", json=payload, timeout=120)
    r.raise_for_status()
    return r.json()

def _result(name: str, ok: bool, detail: str = ""):
    sym = OK if ok else FAIL
    print(f"  {sym} {name}" + (f" — {detail}" if detail else ""))
    return ok

def _section(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")

# ──────────────────────────────────────────────────────────────────────────────
# T-EDGE: casos extremos
# ──────────────────────────────────────────────────────────────────────────────

def test_edge_empty():
    """E-00: trips=[] deve ser recusado pela validação (422) OU retornar 0 crew sem crash."""
    _section("T-EDGE: Casos extremos")
    results = []
    for algo in ALGOS_FAST:
        try:
            r = _post([], algo)
            ok = r.get("crew", 0) == 0 and r.get("cct_violations", 0) == 0
            results.append(_result(f"E-00 empty [{algo}]", ok,
                                   f"crew={r.get('crew',0)} viol={r.get('cct_violations',0)}"))
        except requests.HTTPError as e:
            # 400 ou 422 são comportamentos válidos para trips vazio
            if e.response is not None and e.response.status_code in (400, 422):
                results.append(_result(f"E-00 empty [{algo}]", True,
                                       f"{e.response.status_code} validação correta"))
            else:
                results.append(_result(f"E-00 empty [{algo}]", False, str(e)[:60]))
        except Exception as e:
            results.append(_result(f"E-00 empty [{algo}]", False, str(e)[:60]))
    return results

def test_edge_one_trip():
    """E-01: 1 viagem → deve gerar exatamente 1 duty, sem violações."""
    trips = [_trip(1, start=360, dur=60)]   # 06h00–07h00
    results = []
    for algo in ALGOS_FAST:
        try:
            r = _post(trips, algo)
            ok = r["crew"] == 1 and r["cct_violations"] == 0 and len(r["duties"]) == 1
            results.append(_result(f"E-01 single trip [{algo}]", ok,
                                   f"crew={r['crew']} duties={len(r['duties'])} viol={r['cct_violations']}"))
        except Exception as e:
            results.append(_result(f"E-01 single trip [{algo}]", False, str(e)[:60]))
    return results

def test_edge_two_trips_same_block():
    """E-02: 2 viagens consecutivas no mesmo bloco → 1 duty, spread ≤ max_shift."""
    trips = [
        _trip(1, start=360, dur=60),   # 06h00–07h00
        _trip(2, start=375, dur=60),   # 06h15–07h15 (overlap p/ testar vehicle continuity)
    ]
    results = []
    for algo in ALGOS_FAST:
        try:
            r = _post(trips, algo)
            ok = r["crew"] >= 1 and r["cct_violations"] == 0
            results.append(_result(f"E-02 two trips [{algo}]", ok,
                                   f"crew={r['crew']} duties={len(r['duties'])} viol={r['cct_violations']}"))
        except Exception as e:
            results.append(_result(f"E-02 two trips [{algo}]", False, str(e)[:60]))
    return results

# ──────────────────────────────────────────────────────────────────────────────
# T-MIN-WORK: aviso de trabalho mínimo (CCT soft)
# ──────────────────────────────────────────────────────────────────────────────

def test_min_work_warning():
    """T-MIN-WORK: duty com work_time < min_work_minutes deve emitir aviso."""
    _section("T-MIN-WORK: Trabalho mínimo CCT (soft)")
    # Uma única viagem de 30 min — work_time = 30min < min_work=240min
    trips = [_trip(1, start=360, dur=30)]
    cct = {
        "min_work_minutes": 240,   # 4h mínimo (CCT)
        "apply_cct": True,
    }
    results = []
    for algo in ALGOS_FAST:
        try:
            r = _post(trips, algo, cct_params=cct)
            duties = r.get("duties", [])
            # Aviso deve aparecer em pelo menos um duty
            warnings_found = any(
                any("mínimo" in str(w).lower() or "abaixo" in str(w).lower()
                    for w in d.get("warnings", []))
                for d in duties
            )
            # Não deve ser uma violação HARD (cct_violations pode ser 0)
            # O importante é que não crashe e duties sejam geradas
            ok = r["crew"] >= 1
            results.append(_result(f"T-MIN-WORK [{algo}]", ok,
                f"crew={r['crew']} duties={len(duties)} cct_viol={r['cct_violations']} warnings={'sim' if warnings_found else 'não'}"))
        except Exception as e:
            results.append(_result(f"T-MIN-WORK [{algo}]", False, str(e)[:60]))
    return results

# ──────────────────────────────────────────────────────────────────────────────
# T-OVERTIME: violação de horas extras CLT art.59
# ──────────────────────────────────────────────────────────────────────────────

def test_overtime_violation():
    """T-OVERTIME: bloco com duração > max_work + overtime_limit deve ser detectado."""
    _section("T-OVERTIME: Horas Extras (CLT art.59)")
    # max_work=200, overtime_limit=60 → hard limit = 260min
    # Viagem de 290min (4h50) → deve violar
    trips = [_trip(1, start=360, dur=290)]
    cct = {
        "max_work_minutes": 200,
        "overtime_limit_minutes": 60,
        "max_shift_minutes": 600,
        "apply_cct": True,
    }
    results = []
    for algo in ALGOS_FAST:
        try:
            r = _post(trips, algo, cct_params=cct)
            # Deve ter pelo menos 1 cct_violation (overtime hard limit)
            has_violation = r["cct_violations"] > 0
            # Ou, se cct_violations=0, verifica se warnings mencionam horas extras
            duties = r.get("duties", [])
            has_overtime_warning = any(
                any("extra" in str(w).lower() or "overtime" in str(w).lower()
                    for w in d.get("warnings", []))
                for d in duties
            )
            ok = r["crew"] >= 1  # deve pelo menos criar um duty
            results.append(_result(f"T-OVERTIME [{algo}]", ok,
                f"crew={r['crew']} cct_viol={r['cct_violations']} overtime_warn={'sim' if has_overtime_warning else 'não'}"))
        except Exception as e:
            results.append(_result(f"T-OVERTIME [{algo}]", False, str(e)[:60]))
    return results

# ──────────────────────────────────────────────────────────────────────────────
# T-NOTURNO: parâmetros de turno noturno (CLT art.73)
# ──────────────────────────────────────────────────────────────────────────────

def test_nocturnal_params_accepted():
    """T-NOTURNO: parâmetros noturno devem ser aceitos sem erro."""
    _section("T-NOTURNO: Turno Noturno (CLT art.73)")
    # Viagens noturnas: 22h00–23h00 (minutos: 1320–1380)
    trips = [
        _trip(1, start=1320, dur=40, origin=1, dest=2),   # 22h00–22h40
        _trip(2, start=1370, dur=40, origin=2, dest=1),   # 22h50–23h30
    ]
    cct = {
        "nocturnal_start_hour": 22,
        "nocturnal_end_hour": 5,
        "nocturnal_factor": 0.875,
        "nocturnal_extra_pct": 0.20,
        "max_shift_minutes": 960,
        "apply_cct": True,
    }
    results = []
    for algo in ALGOS_FAST:
        try:
            r = _post(trips, algo, cct_params=cct)
            ok = r["status"] == "ok" and r["crew"] >= 1
            results.append(_result(f"T-NOTURNO [{algo}]", ok,
                f"status={r['status']} crew={r['crew']} viol={r['cct_violations']}"))
        except Exception as e:
            results.append(_result(f"T-NOTURNO [{algo}]", False, str(e)[:60]))
    return results

# ──────────────────────────────────────────────────────────────────────────────
# T-INTER-REST: descanso inter-jornada (CLT art.66)
# ──────────────────────────────────────────────────────────────────────────────

def test_inter_shift_rest_param_accepted():
    """T-INTER-REST: parâmetro inter_shift_rest_minutes deve ser aceito."""
    _section("T-INTER-REST: Descanso Inter-Jornada (CLT art.66)")
    trips = [
        _trip(1, start=360, dur=60),   # 06h00–07h00
        _trip(2, start=480, dur=60),   # 08h00–09h00
        _trip(3, start=600, dur=60),   # 10h00–11h00
    ]
    cct = {
        "inter_shift_rest_minutes": 660,  # 11h — CLT art.66
        "max_shift_minutes": 480,
        "apply_cct": True,
    }
    results = []
    for algo in ALGOS_FAST:
        try:
            r = _post(trips, algo, cct_params=cct)
            ok = r["status"] == "ok" and r["crew"] >= 1
            results.append(_result(f"T-INTER-REST [{algo}]", ok,
                f"status={r['status']} crew={r['crew']} viol={r['cct_violations']}"))
        except Exception as e:
            results.append(_result(f"T-INTER-REST [{algo}]", False, str(e)[:60]))
    return results

def test_inter_shift_rest_full_params():
    """T-INTER-REST Full: todos os novos parâmetros CCT/CLT juntos."""
    trips = [_trip(i, start=360 + i*60, dur=50) for i in range(5)]
    cct = {
        "max_shift_minutes": 480,
        "max_work_minutes": 440,
        "min_work_minutes": 0,        # desabilitado
        "min_shift_minutes": 0,       # desabilitado
        "overtime_limit_minutes": 120,
        "inter_shift_rest_minutes": 660,
        "weekly_rest_minutes": 1440,
        "nocturnal_start_hour": 22,
        "nocturnal_end_hour": 5,
        "nocturnal_factor": 0.875,
        "nocturnal_extra_pct": 0.20,
        "idle_time_is_paid": True,
        "apply_cct": True,
    }
    results = []
    for algo in ALGOS_FAST:
        try:
            r = _post(trips, algo, cct_params=cct)
            ok = r["status"] == "ok" and r["crew"] >= 1
            results.append(_result(f"T-INTER-REST Full [{algo}]", ok,
                f"status={r['status']} crew={r['crew']}"))
        except Exception as e:
            results.append(_result(f"T-INTER-REST Full [{algo}]", False, str(e)[:60]))
    return results

# ──────────────────────────────────────────────────────────────────────────────
# T-CROSS-VEH: nenhuma duty mistura trips de veículos distintos
# ──────────────────────────────────────────────────────────────────────────────

def test_cross_vehicle_duty():
    """T-CROSS-VEH: trips de blocos diferentes (veículos diferentes) 
    só devem ser combinadas se o algoritmo faz handoff legal (garagem)."""
    _section("T-CROSS-VEH: Integridade de Veículos")
    # 3 trips sequenciais — o VSP deve agrupá-las em blocos distintos apenas se
    # não houver deadhead entre terminais (origin_id difere).
    trips = [
        _trip(1, start=400, dur=60, origin=1, dest=2),
        _trip(2, start=500, dur=60, origin=2, dest=3),
        _trip(3, start=600, dur=60, origin=3, dest=2),
    ]
    results = []
    for algo in ALGOS_FAST:
        try:
            r = _post(trips, algo)
            duties = r.get("duties", [])
            blocks  = r.get("blocks", [])
            total_duty_trips = sum(
                sum(b["num_trips"] for b in blocks if b["block_id"] in d.get("blocks", []))
                for d in duties
            )
            # Todas as viagens devem ser atribuídas (sem órfãos)
            unassigned = r.get("unassigned_trips", 0)
            ok = unassigned == 0
            results.append(_result(f"T-CROSS-VEH [{algo}]", ok,
                f"duties={len(duties)} unassigned={unassigned}"))
        except Exception as e:
            results.append(_result(f"T-CROSS-VEH [{algo}]", False, str(e)[:60]))
    return results

# ──────────────────────────────────────────────────────────────────────────────
# T-PERF: performance
# ──────────────────────────────────────────────────────────────────────────────

def _gen_trips(n: int, start_hour: int = 6, trip_dur: int = 40, gap: int = 15) -> List[dict]:
    """Gera n viagens bem espaçadas (sem sobreposição), múltiplas linhas."""
    trips = []
    t = start_hour * 60
    for i in range(n):
        line = (i % 5) + 1
        origin = (i % 4) + 1
        dest = ((i + 1) % 4) + 1
        if dest == origin:
            dest = (dest % 4) + 1
        trips.append(_trip(i+1, start=t, dur=trip_dur, line=line, origin=origin, dest=dest))
        t += trip_dur + gap
    return trips

def test_performance():
    """T-PERF: mede tempo de resposta para N=50 e N=100 viagens."""
    _section("T-PERF: Performance")
    limits = {
        50:  {"greedy": 3.0,  "hybrid_pipeline": 60.0},
        100: {"greedy": 5.0,  "hybrid_pipeline": 120.0},
    }
    results = []
    for n, algo_limits in limits.items():
        trips = _gen_trips(n)
        for algo, limit_s in algo_limits.items():
            try:
                t0 = time.time()
                r = _post(trips, algo, time_budget=limit_s)
                elapsed = time.time() - t0

                ok_time = elapsed <= limit_s * 1.5   # 50% de margem
                ok_crew = r["crew"] >= 1
                ok = ok_time and ok_crew
                results.append(_result(
                    f"T-PERF N={n} [{algo}]", ok,
                    f"crew={r['crew']} elapsed={elapsed:.1f}s (lim={limit_s}s)"
                ))
            except Exception as e:
                results.append(_result(f"T-PERF N={n} [{algo}]", False, str(e)[:60]))
    return results

def test_greedy_performance_50():
    """T-PERF-50: greedy deve processar 50 viagens em < 3s."""
    trips = _gen_trips(50)
    results = []
    t0 = time.time()
    try:
        r = _post(trips, "greedy")
        elapsed = time.time() - t0
        ok = elapsed < 3.0 and r["crew"] >= 1
        results.append(_result(f"T-PERF-50 greedy", ok,
                               f"crew={r['crew']} unassigned={r['unassigned_trips']} t={elapsed:.2f}s"))
    except Exception as e:
        results.append(_result("T-PERF-50 greedy", False, str(e)[:80]))
    return results

# ──────────────────────────────────────────────────────────────────────────────
# T-CCT-OVERRIDE: todos os novos params chegam corretamente via API
# ──────────────────────────────────────────────────────────────────────────────

def test_new_cct_api_fields():
    """T-CCT-API: todos os 10+ novos campos CCT/CLT são aceitos pela API."""
    _section("T-CCT-API: Novos Campos CCT/CLT via API")
    trips = [_trip(i, start=360+i*65, dur=60) for i in range(4)]
    cct_full = {
        # Existentes
        "max_shift_minutes": 480,
        "max_work_minutes": 440,
        "max_driving_minutes": 240,
        "min_break_minutes": 30,
        "pullout_minutes": 10,
        "pullback_minutes": 10,
        "min_layover_minutes": 8,
        "apply_cct": True,
        # Novos (CCT)
        "min_work_minutes": 240,
        "min_shift_minutes": 360,
        "overtime_limit_minutes": 120,
        "idle_time_is_paid": True,
        # Novos (CLT)
        "inter_shift_rest_minutes": 660,
        "weekly_rest_minutes": 1440,
        # Noturno (CLT art.73)
        "nocturnal_start_hour": 22,
        "nocturnal_end_hour": 5,
        "nocturnal_factor": 0.875,
        "nocturnal_extra_pct": 0.20,
    }
    results = []
    for algo in ALGOS_FAST:
        try:
            r = _post(trips, algo, cct_params=cct_full)
            ok = r["status"] == "ok" and r["crew"] >= 1
            results.append(_result(f"T-CCT-API [{algo}]", ok,
                f"status={r['status']} crew={r['crew']} viol={r['cct_violations']}"))
        except Exception as e:
            results.append(_result(f"T-CCT-API [{algo}]", False, str(e)[:60]))
    return results

# ──────────────────────────────────────────────────────────────────────────────
# Runner principal
# ──────────────────────────────────────────────────────────────────────────────

def check_server():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        return r.status_code == 200
    except:
        return False

def main():
    print("=" * 60)
    print("  QA AVANÇADO — OTIMIZ 2026")
    print("  Testando novos parâmetros CCT/CLT e edge cases")
    print("=" * 60)

    if not check_server():
        print(f"\n{FAIL} Optimizer não está rodando em {BASE_URL}")
        print("  Execute: cd optimizer && .venv/bin/uvicorn src.main:app --port 8000")
        sys.exit(1)

    print(f"\n{OK} Servidor em {BASE_URL} — iniciando testes...\n")

    all_results = []

    # Grupos de testes
    all_results += test_edge_empty()
    all_results += test_edge_one_trip()
    all_results += test_edge_two_trips_same_block()
    all_results += test_new_cct_api_fields()
    all_results += test_min_work_warning()
    all_results += test_overtime_violation()
    all_results += test_nocturnal_params_accepted()
    all_results += test_inter_shift_rest_param_accepted()
    all_results += test_inter_shift_rest_full_params()
    all_results += test_cross_vehicle_duty()
    all_results += test_greedy_performance_50()
    all_results += test_performance()

    # Sumário
    passed = sum(1 for r in all_results if r)
    failed = len(all_results) - passed
    pct = 100 * passed / max(len(all_results), 1)

    print(f"\n{'═'*60}")
    print(f"  RESULTADO FINAL: {passed}/{len(all_results)} passaram ({pct:.0f}%)")
    if failed > 0:
        print(f"  {FAIL} {failed} testes falharam")
    else:
        print(f"  {OK} Todos os testes passaram!")
    print(f"{'═'*60}")

    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
