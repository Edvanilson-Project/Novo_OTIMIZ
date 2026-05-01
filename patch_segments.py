import re

file_path = "optimizer/src/services/operational_time_service.py"
with open(file_path, "r") as f:
    content = f.read()

# Replace 'idle' with 'driver_idle'
content = content.replace('segment_type = "idle"', 'segment_type = "driver_idle"')
# Find segment generation for start_buffer to add duty_start
# And also add conditions for pullout

old_pullout = """    if start_buffer > 0:
        segments.append(
            {
                "type": "pullout",
                "start": duty_start,
                "end": tasks[0].start_time,
                "duration": start_buffer,
                "location": tasks[0].trips[0].origin_id,
            }
        )"""

new_pullout = """    segments.append(
        {
            "type": "duty_start",
            "start": duty_start,
            "end": duty_start,
            "duration": 0,
            "location": tasks[0].trips[0].origin_id,
        }
    )

    if start_buffer > 0 and pullout_counts_in_driver_shift:
        segments.append(
            {
                "type": "pullout",
                "start": tasks[0].start_time - start_buffer,
                "end": tasks[0].start_time,
                "duration": start_buffer,
                "location": tasks[0].trips[0].origin_id,
            }
        )"""
content = content.replace(old_pullout, new_pullout)

old_pullback = """    if end_buffer > 0:
        segments.append(
            {
                "type": "pullback",
                "start": tasks[-1].end_time,
                "end": duty_end,
                "duration": end_buffer,
                "location": tasks[-1].trips[-1].destination_id,
            }
        )"""

new_pullback = """    if end_buffer > 0 and pullback_counts_in_driver_shift:
        segments.append(
            {
                "type": "pullback",
                "start": tasks[-1].end_time,
                "end": tasks[-1].end_time + end_buffer,
                "duration": end_buffer,
                "location": tasks[-1].trips[-1].destination_id,
            }
        )

    segments.append(
        {
            "type": "duty_end",
            "start": duty_end,
            "end": duty_end,
            "duration": 0,
            "location": tasks[-1].trips[-1].destination_id,
        }
    )"""
content = content.replace(old_pullback, new_pullback)

with open(file_path, "w") as f:
    f.write(content)

