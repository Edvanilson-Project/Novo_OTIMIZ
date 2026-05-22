import requests
import time
import json
import os

BASE_URL = "http://localhost:3001/api/v1"
EMAIL = "admin@otimiz.com"
PASSWORD = "admin123"

def login():
    print(f"Logging in as {EMAIL}...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    resp.raise_for_status()
    token = resp.json()["access_token"]
    print("Login successful.")
    return token

def run_optimization(token, mode, seed=None):
    print(f"Starting optimization in mode: {mode} (seed: {seed})...")
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "algorithm": "hybrid_pipeline",
        "operational_quality_mode": mode
    }
    # Note: If seed is needed, it should be in company parameters, 
    # but some implementations allow it in the payload.
    # Checking backend optimization.service.ts, it doesn't seem to take random_seed from the body,
    # but rather from paramsRepo. I will assume for now it uses the DB params.
    
    resp = requests.post(f"{BASE_URL}/operations/optimize", json=payload, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    print(f"Optimization started. Schedule ID: {data['scheduleId']}, Task ID: {data['taskId']}")
    return data["scheduleId"], data["taskId"]

def poll_latest_schedule(token, schedule_id):
    headers = {"Authorization": f"Bearer {token}"}
    print("Polling latest schedule...")
    while True:
        resp = requests.get(f"{BASE_URL}/operations/latest-schedule", headers=headers)
        resp.raise_for_status()
        data = resp.json()
        
        # In this system, getLatestSchedule returns the latest schedule data.
        # If the status is still PROCESSING, we wait.
        if data["status"] == "processing":
            print(f"Still processing... (Schedule {data['id']})")
            time.sleep(5)
            continue
        
        if data["id"] != schedule_id:
            print(f"Warning: Expected Schedule {schedule_id}, but got {data['id']}. Waiting...")
            time.sleep(5)
            continue
            
        print(f"Optimization finished with status: {data['status']}")
        return data

def validate_scenario(mode, seed=None):
    token = login()
    schedule_id, task_id = run_optimization(token, mode, seed)
    result = poll_latest_schedule(token, schedule_id)
    
    filename = f"ops_validation_{mode}_result.json"
    with open(filename, "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"Results saved to {filename}")
    
    # Validation checks
    errors = []
    if result["status"] != "completed":
        errors.append(f"Status is {result['status']}, expected completed")
    
    decision = result.get("operational_quality_decision")
    if not decision:
        errors.append("operational_quality_decision block missing")
    else:
        if decision.get("chosen_scenario") is None:
            errors.append("chosen_scenario missing in decision")
            
    if not result.get("chosen_scenario"):
         errors.append("chosen_scenario missing in root")
         
    if errors:
        print(f"FAIL: {errors}")
    else:
        print("SUCCESS: All criteria met.")
    
    return result

if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "balanced"
    validate_scenario(mode)
