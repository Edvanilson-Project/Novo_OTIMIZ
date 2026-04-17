"""
test_celery_rules.py — Teste E2E: Celery + Dynamic Rule Engine
Simula exatamente o comportamento do NestJS _callOptimizerService().
"""
import json
import sys
import time

import requests

BASE_URL = "http://localhost:8000"
POLL_INTERVAL_S = 2
TIMEOUT_S = 120

PAYLOAD = {
    "algorithm": "hybrid_pipeline",
    "vsp_params": {"time_budget_s": 5.0},
    "cct_params": {
        "max_shift_minutes": 480,
        "max_work_minutes": 400,
        "dynamic_rules": [
            {
                "condition": {"field": "is_holiday", "op": "==", "value": True},
                "action": {"target": "work_cost", "type": "multiply", "value": 2.0},
            }
        ],
    },
    "vehicle_types": [
        {
            "id": 1,
            "name": "Padrao",
            "passenger_capacity": 40,
            "fixed_cost": 500.0,
            "cost_per_km": 2.5,
            "cost_per_hour": 30.0,
            "is_electric": False,
            "battery_capacity_kwh": 0.0,
            "minimum_soc": 0.15,
            "charge_rate_kw": 0.0,
            "energy_cost_per_kwh": 0.0,
        }
    ],
    "trips": [
        {
            "id": 101,
            "line_id": 10,
            "start_time": 360,
            "end_time": 420,
            "origin_id": 1,
            "destination_id": 2,
            "distance_km": 15.0,
            "duration": 60,
            "is_holiday": True,
            "deadhead_times": {},
            "energy_kwh": 0.0,
            "elevation_gain_m": 0.0,
            "is_relief_point": False,
            "is_pull_out": False,
            "is_pull_back": False,
            "sent_to_driver_terminal": None,
            "gps_valid": None,
        },
        {
            "id": 102,
            "line_id": 10,
            "start_time": 450,
            "end_time": 510,
            "origin_id": 2,
            "destination_id": 1,
            "distance_km": 15.0,
            "duration": 60,
            "is_holiday": True,
            "deadhead_times": {},
            "energy_kwh": 0.0,
            "elevation_gain_m": 0.0,
            "is_relief_point": False,
            "is_pull_out": False,
            "is_pull_back": False,
            "sent_to_driver_terminal": None,
            "gps_valid": None,
        },
    ],
}


def sep(char="─", n=60):
    print(char * n)


def run_e2e_test():
    sep("═")
    print("  🚀  TESTE E2E: Celery + Dynamic Rule Engine")
    sep("═")

    # ── PASSO 1: Health check ────────────────────────────────────────────────
    print("\n[1/4] Health check...")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=3)
        r.raise_for_status()
        print(f"      ✅ FastAPI disponível — status: {r.json().get('status', 'ok')}")
    except Exception as e:
        print(f"      ❌ FastAPI não responde em {BASE_URL}: {e}")
        print("         Certifique-se de que o FastAPI está a correr:")
        print("         cd optimizer && source .venv/bin/activate && uvicorn main:app --reload")
        sys.exit(1)

    # ── PASSO 2: POST /optimize/ ─────────────────────────────────────────────
    print("\n[2/4] POST /optimize/ → enfileirar no Celery...")
    try:
        t0 = time.perf_counter()
        post_resp = requests.post(f"{BASE_URL}/optimize/", json=PAYLOAD, timeout=10)
        elapsed_post = (time.perf_counter() - t0) * 1000
        post_resp.raise_for_status()
        data = post_resp.json()
    except Exception as e:
        print(f"      ❌ Erro no POST: {e}")
        sys.exit(1)

    task_id = data.get("task_id")
    status = data.get("status")

    if not task_id or status != "processing":
        print(f"      ❌ Resposta inesperada: {data}")
        sys.exit(1)

    print(f"      ✅ Tarefa aceite em {elapsed_post:.0f}ms (< 200ms esperado)")
    print(f"         task_id : {task_id}")
    print(f"         status  : {status}")

    # ── PASSO 3: Polling GET /optimize/status/{task_id} ──────────────────────
    print(f"\n[3/4] Polling a cada {POLL_INTERVAL_S}s (timeout={TIMEOUT_S}s)...")
    status_url = f"{BASE_URL}/optimize/status/{task_id}"
    start = time.time()
    poll_count = 0
    result = None

    while True:
        time.sleep(POLL_INTERVAL_S)
        poll_count += 1
        elapsed_total = time.time() - start

        if elapsed_total >= TIMEOUT_S:
            print(f"      ❌ Timeout após {TIMEOUT_S}s — Celery worker a correr?")
            sys.exit(1)

        try:
            poll_resp = requests.get(status_url, timeout=5)
        except Exception as e:
            print(f"      ⚠️  Erro de rede no polling #{poll_count} (tentando novamente): {e}")
            continue

        if poll_resp.status_code >= 400:
            detail = poll_resp.json().get("detail", poll_resp.text)
            print(f"      ❌ HTTP {poll_resp.status_code} no polling: {json.dumps(detail, indent=2, ensure_ascii=False)}")
            sys.exit(1)

        poll_data = poll_resp.json()
        poll_status = poll_data.get("status", "unknown")

        print(f"      [{elapsed_total:5.1f}s] poll #{poll_count} → {poll_status}")

        if poll_status == "completed":
            result = poll_data.get("result", {})
            break
        elif poll_status == "failed":
            print(f"      ❌ Tarefa falhou no worker:")
            print(json.dumps(poll_data.get("error", {}), indent=2, ensure_ascii=False))
            sys.exit(1)

    # ── PASSO 4: Validar resultados ──────────────────────────────────────────
    print(f"\n[4/4] Validando resultados...")
    sep()

    vehicles    = result.get("vehicles", 0)
    crew        = result.get("crew", 0)
    total_cost  = result.get("total_cost", 0.0)
    csp_bd      = result.get("cost_breakdown", {}).get("csp", {})
    work_cost   = csp_bd.get("work_cost", 0.0)
    n_duties    = csp_bd.get("num_duties", 0)

    dynamic_applied = csp_bd.get("dynamic_rules_applied", 0)
    dynamic_delta   = csp_bd.get("dynamic_adjustments_total", 0.0)
    rule_warnings   = csp_bd.get("dynamic_rules_warnings", [])

    print(f"  🚌  Veículos           : {vehicles}")
    print(f"  👷  Tripulantes        : {crew}")
    print(f"  📋  Deveres (duties)   : {n_duties}")
    print(f"  💰  Custo total        : R$ {total_cost:.2f}")
    print(f"  💼  Custo trabalho CSP : R$ {work_cost:.2f}")
    sep()
    print(f"  🎯  Regras dinâmicas aplicadas : {dynamic_applied}")
    print(f"  📈  Delta introduzido          : R$ {dynamic_delta:.2f}")
    if rule_warnings:
        print(f"  ⚠️   Avisos de compilação:")
        for w in rule_warnings:
            print(f"       - {w}")
    sep()

    # Asserções
    ok = True

    if vehicles == 0 and crew == 0:
        print("  ❌ FALHA: Nenhum veículo/tripulante — solver não produziu resultado")
        ok = False

    if dynamic_applied > 0:
        print("  ✅ SUCESSO: Motor de Regras aplicou as regras dinâmicas")
    else:
        print("  ❌ FALHA: dynamic_rules_applied == 0 — regras não foram executadas")
        ok = False

    if dynamic_delta > 0:
        print(f"  ✅ SUCESSO: work_cost foi multiplicado (delta = R$ {dynamic_delta:.2f})")
    elif n_duties == 0:
        print("  ⚠️   Sem duties → nenhuma regra a aplicar (esperado com payload mínimo)")
    else:
        print("  ❌ FALHA: Delta = 0 apesar de duties existirem")
        ok = False

    sep("═")
    if ok:
        print("  🎉  TODOS OS TESTES E2E PASSARAM!")
    else:
        print("  ❌  ALGUNS TESTES FALHARAM — veja relatório acima")
    sep("═")


if __name__ == "__main__":
    run_e2e_test()
