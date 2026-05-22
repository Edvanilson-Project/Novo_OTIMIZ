from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "export_programacao_operacional.py"
SPEC = importlib.util.spec_from_file_location("export_programacao_operacional", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_bundle_rows_are_explicit_and_detailed_rows_expand_each_trip():
    trip_details_map = {
        101: {
            "id": 101,
            "source_trip_id": 101,
            "trip_id": 5101,
            "public_trip_id": 5101,
            "line_id": 10,
            "line_code": "L10",
            "direction": "IDA",
            "start_time": 360,
            "end_time": 380,
            "duration": 20,
            "origin_id": 1,
            "destination_id": 2,
            "distance_km": 10.0,
            "block_id": 1,
            "vehicle_id": 1,
            "sequence_in_block": 1,
            "trip_group_id": 900,
            "pair_id": "P900",
        },
        102: {
            "id": 102,
            "source_trip_id": 102,
            "trip_id": 5102,
            "public_trip_id": 5102,
            "line_id": 10,
            "line_code": "L10",
            "direction": "VOLTA",
            "start_time": 380,
            "end_time": 400,
            "duration": 20,
            "origin_id": 2,
            "destination_id": 1,
            "distance_km": 10.0,
            "block_id": 1,
            "vehicle_id": 1,
            "sequence_in_block": 2,
            "trip_group_id": 900,
            "pair_id": "P900",
        },
        103: {
            "id": 103,
            "source_trip_id": 103,
            "trip_id": 5103,
            "public_trip_id": 5103,
            "line_id": 20,
            "line_code": "L20",
            "direction": "IDA",
            "start_time": 430,
            "end_time": 450,
            "duration": 20,
            "origin_id": 1,
            "destination_id": 2,
            "distance_km": 11.0,
            "block_id": 2,
            "vehicle_id": 2,
            "sequence_in_block": 1,
            "trip_group_id": 901,
            "pair_id": "P901",
        },
    }

    raw_segments = [
        {
            "type": "commercial_trip",
            "start": 360,
            "end": 400,
            "trip_ids": [101, 102],
            "block_id": 1,
            "location_start": 1,
            "location_end": 1,
        },
        {
            "type": "driver_idle",
            "start": 400,
            "end": 430,
            "duration": 30,
            "location": 1,
            "from_block_id": 1,
            "to_block_id": 2,
        },
        {
            "type": "commercial_trip",
            "start": 430,
            "end": 450,
            "trip_ids": [103],
            "block_id": 2,
            "location_start": 1,
            "location_end": 2,
        },
    ]
    duty = {"duty_id": 7, "trip_ids": [101, 102, 103]}

    normalized_segments = MODULE.normalize_segments(raw_segments, trip_details_map)
    assert normalized_segments[0]["bundle_event_type"] == "commercial_trip_bundle"
    assert any(segment["type"] == "driver_vehicle_change" for segment in normalized_segments)

    detailed_trips = MODULE.build_detailed_duty_trips(duty, normalized_segments, trip_details_map)
    assert [trip["source_trip_id"] for trip in detailed_trips] == [101, 102, 103]
    assert [trip["sequence_in_duty"] for trip in detailed_trips] == [1, 2, 3]

    trip_block_map = {101: 1, 102: 1, 103: 2}
    operational_rows = MODULE.build_rows_from_segments(duty, normalized_segments, 501, trip_block_map)
    bundle_row = next(row for row in operational_rows if row["event_type"] == "commercial_trip_bundle")
    assert bundle_row["trip_count"] == 2
    assert bundle_row["trip_ids"] == "101;102"
    assert bundle_row["event_scope"] == "driver_vehicle"

    driver_rows = MODULE.build_driver_rows(duty, normalized_segments, detailed_trips, 501)
    trip_rows = [row for row in driver_rows if row["event_type"] == "commercial_trip"]
    assert [row["trip_id"] for row in trip_rows] == [101, 102, 103]
    assert any(row["event_type"] == "driver_vehicle_change" for row in driver_rows)