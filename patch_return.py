import re

file_path = "optimizer/src/services/operational_time_service.py"
with open(file_path, "r") as f:
    content = f.read()

# Add operator_not_assigned
old_return = """    return {
        "duty_id": int(duty.id),
        "duty_start": duty_start,"""

new_return = """    return {
        "duty_id": int(duty.id),
        "operator_not_assigned": not getattr(duty, "operator_id", None),
        "duty_start": duty_start,"""

content = content.replace(old_return, new_return)

with open(file_path, "w") as f:
    f.write(content)

