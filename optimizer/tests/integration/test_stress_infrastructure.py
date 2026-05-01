import asyncio
import time
from typing import List

import httpx
import pytest

# Timeout um pouco maior para testes locais sob stress
HTTPX_TIMEOUT = 30.0

@pytest.mark.anyio
async def test_infrastructure_stress_queueing():
    """
    Bombardeia a API com dezenas de requisições simultâneas para garantir
    que o backend (FastAPI) e o Celery Broker (Redis) suportam o enfileiramento
    massivo sem deadlocks, falhas de conexão ou timeouts.
    """
    
    # 50 requests simultâneos
    num_requests = 50
    
    payload = {
        "algorithm": "greedy",
        "time_budget_s": 1.0, # Este serviço externo rejeita budgets menores que 1 segundo
        "trips": [
            {
                "id": 1,
                "line_id": 1,
                "start_time": 360,
                "end_time": 420,
                "origin_id": 1,
                "destination_id": 2,
                "duration": 60,
                "distance_km": 10.0,
            }
        ],
        "vehicle_types": [
            {
                "id": 1,
                "name": "Std",
                "passenger_capacity": 40,
                "cost_per_km": 1.0,
                "cost_per_hour": 10.0,
                "fixed_cost": 100.0,
            }
        ],
        "cct_params": {"strict_hard_validation": False},
        "vsp_params": {"time_budget_s": 1.0}
    }
    
    headers = {
        "X-Internal-Key": "internal-key-123456"
    }

    async def _send_request(client: httpx.AsyncClient, request_id: int) -> httpx.Response:
        request_payload = {
            **payload,
            "request_metadata": {"stress_request_id": request_id},
        }
        return await client.post("http://localhost:8000/optimize/", json=request_payload, headers=headers)
        
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
        # Verifica se o serviço está de pé primeiro
        try:
            health = await client.get("http://localhost:8000/health/")
            # Se não estiver online (rodando), o teste é pulado em vez de falhar a CI inteira.
            # Idealmente, a CI deve levantar os serviços antes de rodar os testes de integração.
            if health.status_code != 200:
                pytest.skip("Serviço principal /health não responde com 200. Execute o uvicorn e celery primeiro.")
        except httpx.ConnectError:
             pytest.skip("Serviço de testes não acessível no localhost:8000. Pular teste de integração.")
             
        # Dispara todas as tarefas de uma vez
        tasks = [_send_request(client, request_id) for request_id in range(num_requests)]
        responses: List[httpx.Response] = await asyncio.gather(*tasks)

    elapsed = time.time() - start_time
    
    # Verificar se TODAS as respostas foram 200 OK (Task accepted)
    failures = [r.status_code for r in responses if r.status_code != 200]
    
    assert len(failures) == 0, f"Ocorreram {len(failures)} falhas ao enfileirar tarefas. Códigos: {failures}"
    assert len(responses) == num_requests
    
    # Valida que todos retornaram um task_id
    task_ids = set()
    for resp in responses:
        data = resp.json()
        assert data["status"] == "processing"
        assert "task_id" in data
        task_ids.add(data["task_id"])
        
    # As tarefas devem ter IDs únicos
    assert len(task_ids) == num_requests
    print(f"\n[STRESS TEST] Sucesso: {num_requests} requisições enfileiradas em {elapsed:.2f} segundos.")
