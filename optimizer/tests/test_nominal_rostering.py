import httpx
import json

BASE_URL = "http://127.0.0.1:8100"

def test_sentimental_priority_assignment():
    """
    Valida se o sistema prioriza o motorista correto baseado em Tags e Pesos
    sem nenhuma alteração no código, apenas via JSON (Regra Sentimental).
    """
    print("\n--- INICIANDO TESTE DE ROSTERING NOMINAL (CERTIFICAÇÃO) ---")
    
    # 1. Definir 3 Motoristas, 1 deles prioritário (VIP)
    operators = [
        {
            "id": "OP_001",
            "name": "Motorista Comum 1",
            "cp": "C001",
            "last_shift_end": 0,
            "metadata": {}
        },
        {
            "id": "OP_EDVANILSON",
            "name": "Edvanilson (Prioritário)",
            "cp": "E001",
            "last_shift_end": 0,
            "metadata": {"is_vip": True, "loyalty_score": 100}
        },
        {
            "id": "OP_003",
            "name": "Motorista Comum 2",
            "cp": "C003",
            "last_shift_end": 0,
            "metadata": {}
        }
    ]

    # 2. Definir 2 Jornadas (Duties)
    duties = [
        {
            "duty_id": 101,
            "blocks": [1],
            "start_time": 480, # 08:00
            "end_time": 960,   # 16:00
            "work_time": 480,
            "spread_time": 480,
            "rest_violations": 0,
            "trips": [{"id": 1, "line_id": 10, "start_time": 480, "end_time": 540, "origin_id": 1, "destination_id": 2}]
        },
        {
            "duty_id": 102,
            "blocks": [2],
            "start_time": 600, # 10:00
            "end_time": 1080,  # 18:00
            "work_time": 480,
            "spread_time": 480,
            "rest_violations": 0,
            "trips": [{"id": 2, "line_id": 20, "start_time": 600, "end_time": 660, "origin_id": 2, "destination_id": 1}]
        }
    ]

    # 3. Definir a Regra "Sentimental" via JSON
    rules = [
        {
            "rule_id": "is_vip",
            "type": "SOFT",
            "weight": 5000 # Peso massivo para garantir a prioridade do motorista
        }
    ]

    payload = {
        "operators": operators,
        "duties": duties,
        "rules": rules,
        "inter_shift_rest_minutes": 0 # Desabilitar descanso para este teste isolado
    }

    try:
        with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
            print(f"Enviando payload para {BASE_URL}/optimize/rostering/ ...")
            response = client.post("/optimize/rostering/", json=payload)
            
            if response.status_code != 200:
                print(f"❌ ERRO: Status {response.status_code}")
                print(response.text)
                return False
            
            data = response.json()
            assignments = data["assignments"]
            
            print(f"Processamento concluído em {data['elapsed_ms']:.2f}ms")
            
            # Verificação do Motorista Prioritário
            found_ed = False
            for assign in assignments:
                op_name = assign["operator_name"]
                duty_id = assign["duty_id"]
                score = assign["score"]
                expl = assign["explanations"]
                
                print(f"  -> {op_name} (ID: {assign['operator_id']}) atribuído ao Duty #{duty_id} | Score: {score}")
                
                if assign["operator_id"] == "OP_EDVANILSON":
                    found_ed = True
                    if score >= 5000:
                        print(f"     ✅ Sucesso: Regra Sentimental [is_vip] aplicada corretamente!")
                    else:
                        print(f"     ❌ Falha: Score {score} não reflete a prioridade VIP.")
                    
                    print(f"     Motivo Log: {expl}")

            if not found_ed:
                print("❌ Falha: Edvanilson não foi escalado em nenhuma jornada.")
                return False

            print("\n--- TESTE FINALIZADO COM SUCESSO ---")
            return True

    except Exception as e:
        print(f"❌ Erro de conexão/execução: {str(e)}")
        return False

if __name__ == "__main__":
    test_sentimental_priority_assignment()
