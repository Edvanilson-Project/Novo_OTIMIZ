import json
import sys

def main():
    with open("ops_validation_balanced_result.json", "r") as f:
        data = json.load(f)
        
    s_meta = data.get("resultSummary", {})
    if "chosen_scenario" not in s_meta:
        print("FAIL: chosen_scenario missing in schedule resultSummary")
        sys.exit(1)
        
    if "operational_quality_decision" not in s_meta:
        print("FAIL: operational_quality_decision missing in schedule resultSummary")
        sys.exit(1)

    duties = s_meta.get("duties", [])
    if not duties:
        print("FAIL: No duties found in resultSummary")
        sys.exit(1)
        
    for i, d in enumerate(duties):
        if "duty_time_segments" not in d:
            print(f"FAIL: duty_time_segments missing in duty {i}")
            sys.exit(1)
            
        if "operational_time_report" not in d:
            print(f"FAIL: operational_time_report missing in duty {i}")
            sys.exit(1)

    print("latest-schedule json Validation: SUCCESS")

main()
