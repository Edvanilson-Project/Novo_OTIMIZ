import hashlib
import json

from src.api.routes.optimize import _build_cache_fingerprint_payload


def _fingerprint(payload: dict) -> str:
    canonical = _build_cache_fingerprint_payload(payload)
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()


def test_cache_fingerprint_ignores_run_specific_metadata():
    base_payload = {
        "company_id": 16,
        "algorithm": "hybrid_pipeline",
        "depot_ids": [6],
        "trips": [{"id": 1, "start_time": 320, "end_time": 365, "distance_km": 13.1}],
        "vehicle_types": [],
        "cct_params": {"min_break_minutes": 30},
        "vsp_params": {},
        "optimization_params": {"random_seed": 42},
        "run_id": 1,
        "request_metadata": {"run_id": 1, "scenario_id": "schedule-1"},
    }
    same_problem_other_run = {
        **base_payload,
        "run_id": 2,
        "request_metadata": {"run_id": 2, "scenario_id": "schedule-2"},
    }

    assert _fingerprint(base_payload) == _fingerprint(same_problem_other_run)


def test_cache_fingerprint_changes_when_trip_payload_changes():
    base_payload = {
        "company_id": 16,
        "algorithm": "hybrid_pipeline",
        "depot_ids": [6],
        "trips": [{"id": 1, "start_time": 320, "end_time": 365, "distance_km": 13.1}],
        "vehicle_types": [],
        "cct_params": {"min_break_minutes": 30},
        "vsp_params": {},
        "optimization_params": {"random_seed": 42},
    }
    changed_trip_payload = {
        **base_payload,
        "trips": [{"id": 1, "start_time": 320, "end_time": 365, "distance_km": 20.0}],
    }

    assert _fingerprint(base_payload) != _fingerprint(changed_trip_payload)