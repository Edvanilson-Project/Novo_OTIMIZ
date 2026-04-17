import asyncio
import httpx
import random
import time
import json
from typing import List, Dict, Any

BASE_URL = "http://127.0.0.1:8100"
CONCURRENCY = 4
N_TRIPS = 500

def generate_chaos_dataset(n: int) -> List[Dict[str, Any]]:
    trips = []
    for i in range(n):
        start = random.randint(300, 1200)
        duration = random.randint(30, 90)
        
        # Injetar caos propositalmente em 5% dos casos
        dice = random.random()
        if dice < 0.05:
            # Duração negativa
            end = start - 10
            duration = -10
        elif dice < 0.10:
            # Sobreposição no mesmo terminal (mesmo terminal, mesmo tempo)
            end = start + duration
        else:
            end = start + duration

        trips.append({
            "id": i + 1,
            "line_id": random.randint(1, 100),
            "start_time": start,
            "end_time": end,
            "origin_id": random.randint(1, 5),
            "destination_id": random.randint(1, 5),
            "duration": duration,
            "distance_km": round(random.uniform(5.0, 30.0), 2),
            "deadhead_times": {}
        })
    return trips

def generate_vehicles() -> List[Dict[str, Any]]:
    # Veículos com custo zero para testar divisão por zero e lógica de custos
    return [
        {
            "id": 1,
            "name": "Ghost Bus (Zero Cost)",
            "passenger_capacity": 50,
            "fixed_cost": 0.0,
            "cost_per_km": 0.0,
            "cost_per_hour": 0.0,
            "is_electric": False,
            "battery_capacity_kwh": 0.0,
            "minimum_soc": 0.0,
            "charge_rate_kw": 0.0,
            "energy_cost_per_kwh": 0.0
        },
        {
            "id": 2,
            "name": "Standard Bus",
            "passenger_capacity": 40,
            "fixed_cost": 500.0,
            "cost_per_km": 2.5,
            "cost_per_hour": 30.0,
            "is_electric": False,
            "battery_capacity_kwh": 0.0,
            "minimum_soc": 0.0,
            "charge_rate_kw": 0.0,
            "energy_cost_per_kwh": 0.0
        }
    ]

async def submit_and_poll(client: httpx.AsyncClient, algo: str, trips: List[Dict], idx: int):
    payload = {
        "algorithm": algo,
        "time_budget_s": 15,
        "trips": trips,
        "vehicle_types": generate_vehicles(),
        "cct_params": {
            "max_shift_minutes": 600,
            "max_work_minutes": 480,
            "strict_hard_validation": False  # Permitir dados sujos para ver o solver reagir
        }
    }

    t0 = time.perf_counter()
    try:
        resp = await client.post(f"{BASE_URL}/optimize/", json=payload, timeout=60)
        if resp.status_code != 200:
            return {"idx": idx, "algo": algo, "ok": False, "error": f"POST failed: {resp.status_code} {resp.text}"}
        
        task_data = resp.json()
        task_id = task_data["task_id"]
        submit_elapsed = time.perf_counter() - t0
        
        print(f"[{idx}] Tarefa {task_id} submetida em {submit_elapsed:.2f}s (Algo: {algo})")

        # Polling
        start_wait = time.time()
        while time.time() - start_wait < 180:
            await asyncio.sleep(2)
            poll_resp = await client.get(f"{BASE_URL}/optimize/status/{task_id}", timeout=10)
            if poll_resp.status_code != 200:
                return {"idx": idx, "algo": algo, "ok": False, "error": f"Poll failed: {poll_resp.status_code}"}
            
            data = poll_resp.json()
            status = data["status"]
            
            if status == "completed":
                total_time = time.time() - start_wait
                result = data["result"]
                return {"idx": idx, "algo": algo, "ok": True, "time": total_time, "result": result}
            elif status == "failed":
                return {"idx": idx, "algo": algo, "ok": False, "error": f"Worker task failed: {data.get('error')}"}
            
        return {"idx": idx, "algo": algo, "ok": False, "error": "Timeout no polling"}
    except Exception as e:
        return {"idx": idx, "algo": algo, "ok": False, "error": str(e)}

async def run_stress_test():
    print("=== INICIANDO TESTE DE STRESS PESADO (MODO TORTURA) ===")
    print(f"Concorrência: {CONCURRENCY} pedidos simultâneos")
    print(f"Volume por pedido: {N_TRIPS} trips")
    
    trips = generate_chaos_dataset(N_TRIPS)
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Check health
        try:
            h = await client.get(f"{BASE_URL}/health")
            print(f"Saúde da API: {h.json()}")
        except:
            print("API OFFLINE! Verifique uvicorn na porta 8100.")
            return

        tasks = []
        for i in range(CONCURRENCY):
            algo = "mcnf" if i < 5 else "hybrid_pipeline"
            tasks.append(submit_and_poll(client, algo, trips, i))
        
        print("\nDisparando ataque de concorrência...")
        start_attack = time.perf_counter()
        results = await asyncio.gather(*tasks)
        total_attack_time = time.perf_counter() - start_attack
        
        print(f"\nAtaque finalizado em {total_attack_time:.2f}s\n")
        
        success_count = 0
        all_passed_audit = True
        
        for r in results:
            prefix = f"[{r['idx']}] {r['algo']:<15}"
            if r["ok"]:
                res = r["result"]
                # Auditoria de Conservação de Viagens (Sugestão Edvanilson)
                assigned = res.get("total_trips", 0)
                unassigned = res.get("unassigned_trips", 0)
                total_accounted = assigned + unassigned
                
                if total_accounted == N_TRIPS:
                    audit_status = "✅ Audit: OK"
                    success_count += 1
                else:
                    audit_status = f"❌ Audit: FAIL ({total_accounted}/{N_TRIPS})"
                    all_passed_audit = False
                
                total_cost = res.get("total_cost", 0)
                print(f"✅ {prefix} | {audit_status} | Time: {r['time']:5.1f}s | Unassigned: {unassigned} | Cost: {total_cost}")
            else:
                print(f"❌ {prefix} | FALHA: {r['error']}")
                all_passed_audit = False

        print(f"\nResumo: {success_count}/{CONCURRENCY} pedidos completados com sucesso e auditados.")
        if success_count == CONCURRENCY and all_passed_audit:
            print("💪 O sistema aguentou o tranco e a conservação de trajetos é de 100%!")
        else:
            print("⚠️ Houve falhas ou erros de auditoria. Verifique os logs.")

if __name__ == "__main__":
    asyncio.run(run_stress_test())
