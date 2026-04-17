import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_optimize_success_response_exposes_audit_contract():
    payload = {
        "run_id": 901,
        "line_id": 44,
        "company_id": 7,
        "algorithm": "hybrid_pipeline",
        "time_budget_s": 4.0,
        "trips": [
            {
                "id": 1,
                "line_id": 44,
                "trip_group_id": 9001,
                "direction": "outbound",
                "start_time": 360,
                "end_time": 420,
                "origin_id": 1,
                "destination_id": 2,
                "duration": 60,
                "distance_km": 12.5,
            },
            {
                "id": 2,
                "line_id": 44,
                "trip_group_id": 9001,
                "direction": "inbound",
                "start_time": 435,
                "end_time": 495,
                "origin_id": 2,
                "destination_id": 1,
                "duration": 60,
                "distance_km": 12.5,
            },
        ],
        "vehicle_types": [
            {
                "id": 1,
                "name": "Standard",
                "passenger_capacity": 40,
                "cost_per_km": 3.0,
                "cost_per_hour": 60.0,
                "fixed_cost": 1000.0,
            }
        ],
        "cct_params": {
            "strict_hard_validation": True,
        },
        "vsp_params": {
            "random_seed": 123,
            "preserve_preferred_pairs": True,
        },
    }

    response = client.post("/optimize/", json=payload)

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["status"] == "ok"
    assert data["cost_breakdown"]["total"] == pytest.approx(data["total_cost"])
    assert data["solver_explanation"]["status"] == "feasible"
    assert data["phase_summary"]["vsp"]["vehicles"] >= 1
    assert data["trip_group_audit"]["groups_total"] == 1
    assert data["trip_group_audit"]["same_roster_groups"] == 1

    assert data["reproducibility"]["random_seed"] == 123
    assert data["reproducibility"]["input_hash"]
    assert data["reproducibility"]["params_hash"]
    assert data["reproducibility"]["time_budget_s"] == pytest.approx(4.0)
    assert data["reproducibility"]["deterministic_replay_possible"] is False
    assert "budget por tempo" in data["reproducibility"]["note"]

    assert data["performance"]["phase_timings_ms"]["input_validation_ms"] >= 0
    assert data["performance"]["phase_timings_ms"]["solver_ms"] >= 0
    assert data["performance"]["phase_timings_ms"]["output_validation_ms"] >= 0
    assert data["performance"]["phase_timings_ms"]["audit_enrichment_ms"] >= 0
    assert data["performance"]["total_elapsed_ms"] >= 0

    assert data["meta"]["run_id"] == 901
    assert data["meta"]["line_id"] == 44
    assert data["meta"]["company_id"] == 7
    assert data["meta"]["reproducibility"]["input_hash"] == data["reproducibility"]["input_hash"]
    assert data["meta"]["performance"]["phase_timings_ms"]["solver_ms"] == data["performance"]["phase_timings_ms"]["solver_ms"]