import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

@pytest.mark.timeout(300)
def test_e2e_heavy_duty_charter_api_load():
    """
    Testes E2E de Integração (Test-to-Break) para o cenário Extremo de Fretamento via API REST.
    Prova que a Stack Python + Solver não derruba workers com carga pesada.
    """
    trips = []
    trip_id = 1
    # 1000 de manhã
    for i in range(100):
        start = 300 + (i % 120)  # 05:00 AM
        trips.append({
            "id": trip_id,
            "line_id": 1,
            "start_time": start,
            "end_time": start + 45,
            "origin_id": 1,
            "destination_id": 2
        })
        trip_id += 1
    
    # 1000 de tarde/noite
    for i in range(100):
        start = 960 + (i % 120)  # 16:00 PM
        trips.append({
            "id": trip_id,
            "line_id": 1,
            "start_time": start,
            "end_time": start + 45,
            "origin_id": 2,
            "destination_id": 1
        })
        trip_id += 1

    payload = {
        "algorithm": "hybrid_pipeline",
        "time_budget_s": 5.0,
        "trips": trips,
        "cct_params": {
            "max_shift_minutes": 900,
            "max_work_minutes": 600,
            "max_driving_minutes": 270,
            "min_break_minutes": 60,
            "max_unpaid_break_minutes": 600,
            "long_unpaid_break_limit_minutes": 600,
            "waiting_time_pay_pct": 0.3,
            "idle_time_is_paid": True,
            "allow_relief_points": False,
        },
        "vsp_params": {
            "max_vehicle_shift_minutes": 1440,
            "allow_vehicle_split_shifts": True,
            "pricing_enabled": True,
            "use_set_covering": True,
            "strict_hard_validation": True
        }
    }

    response = client.post("/optimize/", json=payload)
    
    assert response.status_code == 200, f"A API colapsou sob carga: {response.text}"
    
    data = response.json()
    assert data["status"] == "ok"
    assert data["vehicles"] > 0
    assert data["cct_violations"] == 0, "A API injetou falsos CCT Violations no Fretamento"
