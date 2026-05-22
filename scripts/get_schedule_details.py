import requests
import json
import os

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6MTUsInN1YiI6MTUsImVtYWlsIjoiYWRtaW5Ab3RpbWl6LmNvbSIsImNvbXBhbnlJZCI6MTYsInJvbGUiOiJzdXBlcl9hZG1pbiIsImlhdCI6MTc3NzYzMzExNywiZXhwIjoxNzc3NzE5NTE3fQ.Yp69fseeB0aJkuW7HFpCRgViHKJNppiAwLJp0K6yzTY"
BASE_URL = "http://localhost:3001/api/v1"

headers = {"Authorization": f"Bearer {TOKEN}"}
resp = requests.get(f"{BASE_URL}/operations/schedules/434", headers=headers)
resp.raise_for_status()
data = resp.json()

with open("ops_validation_balanced_result_full.json", "w") as f:
    json.dump(data, f, indent=2)

print(f"Schedule keys: {data.keys()}")
print(f"Metadata keys: {data.get('metadata', {}).keys()}")
if data.get('duties'):
    print(f"Duty 0 metadata keys: {data['duties'][0].get('metadata', {}).keys()}")
