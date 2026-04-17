import requests
import json
import time

API_URL = "http://localhost:8000/optimize/"

def get_base_payload():
    return {
      "trips": [
          {
              "id": 101, "line_id": 99, "start_time": 360, "end_time": 390,
              "origin_id": 1, "destination_id": 2, "duration": 30, "distance_km": 10.5
          },
          {
              "id": 102, "line_id": 99, "start_time": 400, "end_time": 430,
              "origin_id": 2, "destination_id": 1, "duration": 30, "distance_km": 10.5
          },
          {
              "id": 103, "line_id": 99, "start_time": 440, "end_time": 470,
              "origin_id": 1, "destination_id": 2, "duration": 30, "distance_km": 10.5
          }
      ],
      "vehicle_types": [
          {
              "id": 1, "name": "Standard Bus", "passenger_capacity": 40,
              "cost_per_km": 1.5, "cost_per_hour": 20.0, "fixed_cost": 100.0,
              "is_electric": False, "battery_capacity_kwh": 100.0,
              "minimum_soc": 10.0, "charge_rate_kw": 0.0, "energy_cost_per_kwh": 0.0,
              "depot_id": 1
          }
      ],
      "depot_id": 1,
      "time_budget_s": 5,
      "algorithm": "hybrid_pipeline", 
      "vsp_params": {
          "algorithm": "vsp_greedy"
      },
      "cct_params": {
          "csp_algorithm": "csp_heuristic",
          "maxShiftMinutes": 600,
          "maxDrivingMinutes": 240,
          "breakMinutes": 60
      }
    }

algorithms = [
    ("vsp_greedy", "csp_heuristic", "hybrid_pipeline"),
    ("vsp_local_search", "csp_only", "hybrid_pipeline"),
    ("hybrid_pipeline", "csp_column_generation", "hybrid_pipeline"),
    ("simulated_annealing", "csp_heuristic", "simulated_annealing"),
    ("tabu_search", "csp_heuristic", "tabu_search"),
    ("set_partitioning", "csp_only", "set_partitioning"),
    ("joint_solver", "csp_heuristic", "joint_solver"),
    ("greedy", "csp_heuristic", "greedy")
]

print("Iniciando auditoria focada no Otimizador (FastAPI)")
time.sleep(1)

results = []

for vsp_alg, csp_alg, top_alg in algorithms:
    print(f"\n--- Testando Combinação: Top={top_alg} | VSP={vsp_alg} | CSP={csp_alg} ---")
    payload = get_base_payload()
    payload["algorithm"] = top_alg
    payload["vsp_params"]["algorithm"] = vsp_alg
    payload["cct_params"]["csp_algorithm"] = csp_alg
    
    start_time = time.time()
    try:
        response = requests.post(API_URL, json=payload, timeout=10)
        duration = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            cost = data.get("total_cost", 0)
            vehicles = data.get("vehicles", 0)
            crew = data.get("crew", 0)
            violations = data.get("cct_violations", 0)
            
            print(f"[SUCCESS] {duration:.2f}s | Custo: R${cost} | V: {vehicles} | C: {crew} | Viol: {violations}")
            results.append({"vsp": vsp_alg, "csp": csp_alg, "success": True, "cost": cost, "violations": violations})
        else:
            print(f"[HTTP ERROR] Code {response.status_code} | {response.text}")
            results.append({"vsp": vsp_alg, "csp": csp_alg, "success": False, "error": f"HTTP {response.status_code}"})
    except Exception as e:
        print(f"[TIMEOUT/ERROR] {e}")
        results.append({"vsp": vsp_alg, "csp": csp_alg, "success": False, "error": "Exception"})

print("\n\n=== RESULTADO DA AUDITORIA GLOBAL ===")
for r in results:
    if r["success"]:
        print(f"✅ {r['vsp']} + {r['csp']} -> Custo: {r['cost']} | Viol: {r['violations']}")
    else:
        print(f"❌ {r['vsp']} + {r['csp']} -> ERRO: {r['error']}")

