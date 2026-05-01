import re

file_path = "optimizer/src/services/operational_time_service.py"
with open(file_path, "r") as f:
    content = f.read()

# duty_start and duty_end
content = re.sub(
    r'duty_start = int\(duty.meta.get\("duty_start_minutes", tasks\[0\].start_time - start_buffer\)\)',
    'duty_start = int(duty.meta.get("duty_start_minutes", tasks[0].start_time - (start_buffer if pullout_counts_in_driver_shift else 0)))',
    content
)
content = re.sub(
    r'duty_end = int\(duty.meta.get\("duty_end_minutes", tasks\[-1\].end_time \+ end_buffer\)\)',
    'duty_end = int(duty.meta.get("duty_end_minutes", tasks[-1].end_time + (end_buffer if pullback_counts_in_driver_shift else 0)))',
    content
)

with open(file_path, "w") as f:
    f.write(content)

