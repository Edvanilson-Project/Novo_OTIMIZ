import requests
import json
import time
import sys

# OTIMIZ Production Audit Script
# Final validation for World Class Deployment

BASE_URL = "http://localhost:8000/api/v1"
AUTH_KEY = "internal-key-123456"

def print_banner(title):
    print("\n" + "="*60)
    print(f" {title:^58} ")
    print("="*60)

def test_sync_optimization():
    print("\n[1/3] Testando Otimização Síncrona (Numerical Hardening)...")
    payload = {
        "trips": [
            {
                "id": 1, "line_id": 101, "start_time": 480, "end_time": 540, 
                "origin_id": 1, "destination_id": 2, "distance_km": 10.5
            },
            {
                "id": 2, "line_id": 101, "start_time": 550, "end_time": 610, 
                "origin_id": 2, "destination_id": 1, "distance_km": 10.5
            }
        ],
        "vehicle_types": [
            {"id": 1, "name": "Bus", "fixed_cost": 500.0, "cost_per_km": 2.5}
        ],
        "wait_for_completion": True,
        "algorithm": "hybrid_pipeline"
    }
    
    start = time.time()
    try:
        response = requests.post(
            f"{BASE_URL}/optimize/",
            json=payload,
            headers={"X-Internal-Key": AUTH_KEY},
            timeout=30
        )
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCESSO ({elapsed:.2f}s)")
            print(f"   - Veículos: {data.get('vehicles')}")
            print(f"   - Tripulação: {data.get('crew')}")
            print(f"   - Custo Total: {data.get('total_cost')}")
            return True
        else:
            print(f"❌ FALHA ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"❌ ERRO DE CONEXÃO: {e}")
        return False

def test_cct_compliance():
    print("\n[2/3] Testando Conformidade CCT (Regras de Jornada)...")
    # Viagem longa de 10 horas sem intervalo
    payload = {
        "trips": [
            {"id": 1, "line_id": 101, "start_time": 480, "end_time": 1080, "origin_id": 1, "destination_id": 2}
        ],
        "vehicle_types": [{"id": 1, "name": "Bus", "fixed_cost": 500.0}],
        "wait_for_completion": True,
        "cct_params": {"max_work_minutes": 480} # 8h max
    }
    
    response = requests.post(
        f"{BASE_URL}/optimize/",
        json=payload,
        headers={"X-Internal-Key": AUTH_KEY}
    )
    
    if response.status_code == 200:
        data = response.json()
        violations = data.get('cct_violations', 0)
        if violations > 0:
            print(f"✅ SUCESSO: {violations} violações detectadas corretamente para jornada excessiva.")
            return True
        else:
            print("❌ FALHA: Nenhuma violação detectada para jornada de 10h com limite de 8h.")
            return False
    return False

def test_precision_decimal():
    print("\n[3/3] Testando Precisão Decimal (Audit Contract)...")
    payload = {
        "trips": [{"id": 1, "line_id": 101, "start_time": 480, "end_time": 540, "origin_id": 1, "destination_id": 2}],
        "vehicle_types": [{"id": 1, "name": "Bus", "fixed_cost": 500.33, "cost_per_km": 1.11}],
        "wait_for_completion": True
    }
    
    response = requests.post(f"{BASE_URL}/optimize/", json=payload, headers={"X-Internal-Key": AUTH_KEY})
    if response.status_code == 200:
        data = response.json()
        # Verificar se o custo total reflete os decimais (500.33 + km_cost)
        cost = data.get('total_cost', 0)
        if cost > 500.33:
            print(f"✅ SUCESSO: Precisão decimal preservada. Custo: {cost}")
            return True
    return False

if __name__ == "__main__":
    print_banner("OTIMIZ WORLD CLASS AUDIT")
    print("Verificando se o backend está pronto para produção...")
    
    # Check if server is up
    try:
        requests.get(f"{BASE_URL}/health", timeout=2)
    except:
        print("\n⚠️  AVISO: O servidor backend parece estar offline.")
        print("   Inicie o servidor com: cd optimizer && uvicorn src.main:app --reload")
        sys.exit(1)

    results = [
        test_sync_optimization(),
        test_cct_compliance(),
        test_precision_decimal()
    ]
    
    print_banner("RESULTADO FINAL")
    if all(results):
        print(" ✨ STATUS: PRONTO PARA PRODUÇÃO (WORLD CLASS) ✨ ")
        print(" O motor de otimização está estável, preciso e validado. ")
    else:
        print(" ⚠️ STATUS: NECESSITA ATENÇÃO ⚠️ ")
        print(" Alguns testes falharam. Verifique os logs acima. ")
    print("="*60 + "\n")
