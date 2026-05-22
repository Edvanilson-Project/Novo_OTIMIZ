import requests
import json
import time

BASE_URL = "http://localhost:3001/api/v1"

def login():
    # Attempt login with the common testing credentials
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@otimiz.com",
        "password": "password"
    })
    resp.raise_for_status()
    return resp.json()["token"]

TOKEN = login()

print(f"Logged in, token: {TOKEN[:20]}...")

def run_optimization(mode, seed):
    print(f"Starting optimization in mode: {mode} (seed: {seed})...")
    headers = {"Authorization": f"Bearer {TOKEN}"}
    payload = {
        "algorithm": "hybrid_pipeline",
        "operational_quality_mode": mode,
        "optimization_params": {
            "random_seed": seed,
            "group_infeasibility_mode": "production"
        }
    }
    resp = requests.post(f"{BASE_URL}/operations/optimize", json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    print(f"Optimization started. Schedule ID: {data['scheduleId']}, Task ID: {data['taskId']}")
    return data["scheduleId"]

def poll_latest_schedule():
    headers = {"Authorization": f"Bearer {TOKEN}"}
    while True:
        resp = requests.get(f"{BASE_URL}/operations/latest-schedule", headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "processing":
            print(f"Still processing... (Schedule {data.get('id')})")
            time.sleep(5)
            continue
        print(f"Optimization finished with status: {data.get('status')}")
        return data

schedule_id = run_optimization("balanced", 20260429)
result = poll_latest_schedule()

filename = f"ops_validation_balanced_result.json"
with open(filename, "w") as f:
    json.dump(result, f, indent=2)
print(f"Results saved to {filename}")

