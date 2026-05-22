import requests
import time
import json
import sys

BASE_URL = "http://localhost:3001/api/v1"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOjE1LCJlbWFpbCI6ImFkbWluQG90aW1pei5jb20iLCJjb21wYW55SWQiOjE2LCJyb2xlIjoiYWRtaW4iLCJpYXQiOjE3Nzc2MzI2MTUsImV4cCI6MTc3NzcxOTAxNX0.ydbz5vPrQ6kcyGBbK5TCCglbtzjalb5Y0wu-5g1bnAo"

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

mode = sys.argv[1] if len(sys.argv) > 1 else "balanced"
schedule_id = run_optimization(mode, 20260429)
result = poll_latest_schedule()

filename = f"ops_validation_{mode}_result.json"
with open(filename, "w") as f:
    json.dump(result, f, indent=2)
print(f"Results saved to {filename}")
