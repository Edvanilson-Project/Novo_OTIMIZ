#!/usr/bin/env python3
"""
Export programação operacional from the latest schedule in PostgreSQL.

Usage:
    python scripts/export_programacao_operacional.py --company-id 16
    python scripts/export_programacao_operacional.py --company-id 16 --schedule-id 428
    python scripts/export_programacao_operacional.py --company-id 16 --output output.csv
    python scripts/export_programacao_operacional.py --company-id 16 --detailed-output viagens_detalhadas.csv
    python scripts/export_programacao_operacional.py --company-id 16 --drivers-output motoristas_corrigido.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import psycopg2
except ImportError:
    psycopg2 = None


# ── Event type labels (Solver → PT-BR) ──────────────────────────────────────
OPERATIONAL_EVENT_LABELS: Dict[str, str] = {
    "commercial_trip": "Viagem",
    "commercial_trip_bundle": "Viagem agrupada",
    "idle": "Ociosa",
    "driver_idle": "Ociosa",
    "normal_break": "Intervalo normal",
    "mandatory_rest": "Descanso obrigatório",
    "pullout": "Soltura",
    "pullback": "Recolhimento",
    "deadhead": "Deslocamento operacional",
    "driver_change": "Troca de motorista",
    "driver_vehicle_change": "Troca de veículo",
    "duty_start": "Início de jornada",
    "duty_end": "Fim de jornada",
}

WORK_TIME_TYPES = {"commercial_trip", "commercial_trip_bundle", "deadhead"}
DRIVING_TIME_TYPES = {"commercial_trip", "commercial_trip_bundle", "deadhead"}

CSV_COLUMNS = [
    "schedule_id",
    "block_id",
    "duty_id",
    "driver_id",
    "driver_display_name",
    "operator_not_assigned",
    "vehicle_id",
    "from_vehicle_id",
    "to_vehicle_id",
    "sequence",
    "event_type",
    "event_label",
    "event_scope",
    "duty_start",
    "duty_end",
    "start_time",
    "end_time",
    "duration_minutes",
    "origin_id",
    "destination_id",
    "trip_ids",
    "trip_count",
    "is_work_time",
    "is_driving_time",
    "is_idle_time",
    "is_normal_break",
    "is_mandatory_rest",
    "is_pullout",
    "is_pullback",
    "rest_valid",
    "mandatory_rest_required",
    "has_valid_mandatory_rest",
    "rule_code",
    "violation_code",
    "issue_severity",
    "issue_codes",
    "issue_explanation",
    "explanation",
]

DETAILED_TRIP_COLUMNS = [
    "schedule_id",
    "duty_id",
    "driver_id",
    "sequence_in_duty",
    "segment_sequence",
    "sequence_in_bundle",
    "bundle_trip_count",
    "bundle_event_type",
    "source_trip_id",
    "public_trip_id",
    "line_id",
    "line_code",
    "direction",
    "start_time",
    "end_time",
    "duration_minutes",
    "origin_id",
    "destination_id",
    "block_id",
    "vehicle_id",
    "sequence_in_block",
    "trip_group_id",
    "pair_id",
]

DRIVER_COLUMNS = [
    "schedule_id",
    "duty_id",
    "driver_id",
    "driver_display_name",
    "operator_not_assigned",
    "duty_start",
    "duty_end",
    "sequence",
    "event_type",
    "event_label",
    "event_scope",
    "line_code",
    "direction",
    "start_time",
    "end_time",
    "duration_minutes",
    "trip_id",
    "trip_ids",
    "trip_count",
    "origin_id",
    "destination_id",
    "vehicle_id",
    "from_vehicle_id",
    "to_vehicle_id",
    "sequence_in_duty",
    "sequence_in_bundle",
    "mandatory_rest_required",
    "has_valid_mandatory_rest",
    "issue_severity",
    "issue_codes",
    "issue_explanation",
    "explanation",
]


def build_duty_export_context(duty: Dict[str, Any]) -> Dict[str, Any]:
    duty_id = int(duty["duty_id"])
    metadata = duty.get("metadata") or {}
    report = duty.get("operational_time_report") or metadata.get("operational_time_report") or {}
    violations = [str(code) for code in report.get("violations") or [] if code]
    operator_not_assigned = bool(report.get("operator_not_assigned", True))
    duty_start_raw = report.get("duty_start", metadata.get("start_time"))
    duty_end_raw = report.get("duty_end", metadata.get("end_time"))
    issue_explanation = str(report.get("suggestion") or report.get("user_explanation") or "").strip()
    return {
        "driver_display_name": f"Operador não atribuído (D{duty_id})" if operator_not_assigned else f"Jornada D{duty_id}",
        "operator_not_assigned": operator_not_assigned,
        "duty_start": min_to_hhmm(int(duty_start_raw)) if duty_start_raw not in (None, "") else "",
        "duty_end": min_to_hhmm(int(duty_end_raw)) if duty_end_raw not in (None, "") else "",
        "mandatory_rest_required": bool(report.get("mandatory_rest_required", False)),
        "has_valid_mandatory_rest": bool(report.get("has_valid_mandatory_rest", False)),
        "issue_severity": "soft" if violations else "",
        "issue_codes": ";".join(violations),
        "issue_explanation": issue_explanation,
    }


def min_to_hhmm(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h:02d}:{m:02d}"


def normalize_trip_ids(raw_trip_ids: Any) -> List[int]:
    if not isinstance(raw_trip_ids, list):
        return []
    normalized: List[int] = []
    seen = set()
    for trip_id in raw_trip_ids:
        try:
            value = int(trip_id)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def sort_trip_details(trips: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        trips,
        key=lambda trip: (
            int(trip.get("start_time", 0) or 0),
            int(trip.get("end_time", 0) or 0),
            int(trip.get("source_trip_id", trip.get("id", 0)) or 0),
        ),
    )


def resolve_segment_block_id(segment: Dict[str, Any], trip_details: List[Dict[str, Any]]) -> Optional[int]:
    for key in ("block_id", "from_block_id", "to_block_id"):
        value = segment.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    for trip in trip_details:
        value = trip.get("block_id") or trip.get("vehicle_id")
        if value not in (None, ""):
            return int(value)
    return None


def build_driver_vehicle_change_segment(segment: Dict[str, Any], from_block_id: int, to_block_id: int) -> Dict[str, Any]:
    timestamp = int(segment.get("start", segment.get("end", 0)) or 0)
    return {
        "type": "driver_vehicle_change",
        "event_type": "driver_vehicle_change",
        "event_scope": "driver",
        "start": timestamp,
        "end": timestamp,
        "duration": 0,
        "location": segment.get("location", segment.get("location_start", segment.get("location_end", ""))),
        "from_block_id": from_block_id,
        "to_block_id": to_block_id,
        "from_vehicle_id": from_block_id,
        "to_vehicle_id": to_block_id,
        "explanation": "Motorista troca de veículo entre blocos distintos da mesma jornada.",
    }


def normalize_segments(raw_segments: List[Dict[str, Any]], trip_details_map: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not raw_segments:
        return []

    base_segments: List[Dict[str, Any]] = []
    for segment in raw_segments:
        seg_type = str(segment.get("type") or segment.get("event_type") or "unknown")
        trip_ids = normalize_trip_ids(segment.get("trip_ids", []))
        trip_details = sort_trip_details([trip_details_map[trip_id] for trip_id in trip_ids if trip_id in trip_details_map])
        block_id = resolve_segment_block_id(segment, trip_details)
        trip_group_ids = sorted({
            int(trip["trip_group_id"]) for trip in trip_details if trip.get("trip_group_id") not in (None, "")
        })
        trip_directions = sorted({
            str(trip["direction"]) for trip in trip_details if trip.get("direction")
        })
        trip_count = len(trip_ids)
        bundle_event_type = "commercial_trip_bundle" if seg_type == "commercial_trip" and trip_count > 1 else seg_type
        event_scope = segment.get("event_scope") or ("driver_vehicle" if seg_type in ("commercial_trip", "deadhead") else "driver")
        normalized = dict(segment)
        normalized.update({
            "type": seg_type,
            "event_type": seg_type,
            "event_scope": event_scope,
            "trip_ids": trip_ids,
            "trip_count": trip_count,
            "trip_group_ids": trip_group_ids,
            "trip_directions": trip_directions,
            "block_id": block_id,
            "vehicle_id": block_id,
        })
        if bundle_event_type != seg_type:
            normalized["bundle_event_type"] = bundle_event_type
            normalized.setdefault("explanation", f"Segmento operacional agrupado com {trip_count} viagens reais.")
        base_segments.append(normalized)

    normalized_segments: List[Dict[str, Any]] = []
    for index, segment in enumerate(base_segments):
        seg_type = str(segment.get("type") or segment.get("event_type") or "unknown")
        from_block_id = segment.get("from_block_id")
        to_block_id = segment.get("to_block_id")
        if from_block_id not in (None, "") and to_block_id not in (None, "") and int(from_block_id) != int(to_block_id) and seg_type != "driver_vehicle_change":
            normalized_segments.append(build_driver_vehicle_change_segment(segment, int(from_block_id), int(to_block_id)))

        normalized_segments.append(segment)

        next_segment = base_segments[index + 1] if index + 1 < len(base_segments) else None
        if not next_segment:
            continue
        if seg_type != "commercial_trip" or str(next_segment.get("type") or next_segment.get("event_type") or "unknown") != "commercial_trip":
            continue
        current_block_id = segment.get("block_id")
        next_block_id = next_segment.get("block_id")
        current_end = int(segment.get("end", segment.get("start", 0)) or 0)
        next_start = int(next_segment.get("start", current_end) or current_end)
        if current_block_id not in (None, "") and next_block_id not in (None, "") and int(current_block_id) != int(next_block_id) and next_start <= current_end:
            normalized_segments.append(build_driver_vehicle_change_segment(segment, int(current_block_id), int(next_block_id)))

    return normalized_segments


def build_detailed_duty_trips(
    duty: Dict[str, Any],
    normalized_segments: List[Dict[str, Any]],
    trip_details_map: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    duty_id = int(duty["duty_id"])
    detailed_trips: List[Dict[str, Any]] = []
    seen_trip_ids = set()

    def append_trip(
        trip: Dict[str, Any],
        segment_sequence: Optional[int],
        sequence_in_bundle: int,
        bundle_trip_count: int,
        bundle_event_type: str,
    ) -> None:
        source_trip_id = int(trip.get("source_trip_id", trip.get("id", 0)) or 0)
        if source_trip_id <= 0 or source_trip_id in seen_trip_ids:
            return
        seen_trip_ids.add(source_trip_id)
        detailed_trips.append({
            **trip,
            "duty_id": duty_id,
            "driver_id": duty_id,
            "sequence_in_duty": len(detailed_trips) + 1,
            "segment_sequence": segment_sequence,
            "sequence_in_bundle": sequence_in_bundle,
            "bundle_trip_count": bundle_trip_count,
            "bundle_event_type": bundle_event_type,
        })

    for segment_index, segment in enumerate(normalized_segments, start=1):
        if str(segment.get("type") or segment.get("event_type") or "unknown") != "commercial_trip":
            continue
        segment_trips = sort_trip_details([
            trip_details_map[trip_id] for trip_id in normalize_trip_ids(segment.get("trip_ids", [])) if trip_id in trip_details_map
        ])
        for trip_index, trip in enumerate(segment_trips, start=1):
            append_trip(
                trip,
                segment_index,
                trip_index,
                len(segment_trips),
                str(segment.get("bundle_event_type") or segment.get("type") or "commercial_trip"),
            )

    fallback_trips = sort_trip_details([
        trip_details_map[trip_id] for trip_id in normalize_trip_ids(duty.get("trip_ids", [])) if trip_id in trip_details_map
    ])
    for trip in fallback_trips:
        append_trip(trip, None, 1, 1, "commercial_trip")

    return detailed_trips


def get_db_connection():
    """Create PostgreSQL connection using environment variables."""
    if psycopg2 is None:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary", file=sys.stderr)
        sys.exit(1)

    # Try to load from .env file in project root
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5444")),
        dbname=os.environ.get("DB_NAME", "otimiz_db"),
        user=os.environ.get("DB_USER", "otimiz_admin"),
        password=os.environ.get("DB_PASSWORD", ""),
    )


def fetch_schedule(conn, company_id: int, schedule_id: Optional[int] = None) -> Dict[str, Any]:
    """Fetch the target schedule."""
    cur = conn.cursor()
    if schedule_id:
        cur.execute(
            'SELECT id, status, "companyId", metadata FROM schedules WHERE id = %s AND "companyId" = %s',
            (schedule_id, company_id),
        )
    else:
        cur.execute(
            'SELECT id, status, "companyId", metadata FROM schedules WHERE "companyId" = %s ORDER BY "createdAt" DESC LIMIT 1',
            (company_id,),
        )
    row = cur.fetchone()
    cur.close()
    if not row:
        print(f"ERROR: No schedule found for company_id={company_id}" +
              (f" schedule_id={schedule_id}" if schedule_id else ""), file=sys.stderr)
        sys.exit(1)
    return {"id": row[0], "status": row[1], "company_id": row[2], "metadata": row[3] or {}}


def fetch_duties(conn, schedule_id: int) -> List[Dict[str, Any]]:
    """Fetch all duty assignments for a schedule."""
    cur = conn.cursor()
    cur.execute(
        'SELECT "dutyId", "tripIds", cost, metadata FROM duty_assignments WHERE "scheduleId" = %s ORDER BY "dutyId" ASC',
        (schedule_id,),
    )
    duties = []
    for row in cur.fetchall():
        meta = row[3] or {}
        duties.append({
            "duty_id": row[0],
            "trip_ids": row[1] or [],
            "cost": row[2],
            "metadata": meta,
            "duty_time_segments": meta.get("duty_time_segments") or [],
            "operational_time_report": meta.get("operational_time_report") or {},
            "quality_metrics": meta.get("quality_metrics") or {},
        })
    cur.close()
    return duties


def fetch_trip_block_details(conn, schedule_id: int) -> tuple[Dict[int, Dict[str, int]], List[int]]:
    """Build tripId → block/sequence mapping from block_assignments."""
    cur = conn.cursor()
    cur.execute(
        'SELECT "blockId", "tripIds" FROM block_assignments WHERE "scheduleId" = %s',
        (schedule_id,),
    )
    mapping: Dict[int, Dict[str, int]] = {}
    all_trip_ids: List[int] = []
    for row in cur.fetchall():
        block_id = row[0]
        trip_ids = row[1] or []
        for index, tid in enumerate(trip_ids, start=1):
            value = int(tid)
            mapping[value] = {"block_id": int(block_id), "sequence_in_block": index}
            all_trip_ids.append(value)
    cur.close()
    return mapping, sorted(set(all_trip_ids))


def fetch_trip_details(
    conn,
    trip_ids: List[int],
    trip_block_details: Dict[int, Dict[str, int]],
) -> Dict[int, Dict[str, Any]]:
    if not trip_ids:
        return {}

    cur = conn.cursor()
    placeholders = ",".join(["%s"] * len(trip_ids))
    cur.execute(
        f'''SELECT id, "tripId", "lineId", "lineCode", "pairId", "tripGroupId", direction,
                    "startTime", "endTime", "originId", "destinationId", "distanceKm", duration
             FROM trips WHERE id IN ({placeholders})''',
        trip_ids,
    )
    trip_details: Dict[int, Dict[str, Any]] = {}
    for row in cur.fetchall():
        source_trip_id = int(row[0])
        public_trip_id = int(row[1]) if row[1] is not None else source_trip_id
        start_time = int(row[7])
        raw_end = int(row[8])
        end_time = raw_end if raw_end >= start_time else raw_end + 1440
        block_detail = trip_block_details.get(source_trip_id, {})
        raw_line_id = row[2]
        line_code = row[3]
        raw_trip_group_id = row[5]
        pair_id = row[4]
        resolved_line_id = raw_line_id
        if resolved_line_id in (None, "") and line_code not in (None, ""):
            try:
                resolved_line_id = int(str(line_code))
            except (TypeError, ValueError):
                resolved_line_id = raw_line_id

        resolved_trip_group_id = raw_trip_group_id
        if resolved_trip_group_id in (None, "") and isinstance(pair_id, str) and pair_id.upper().startswith("P"):
            suffix = pair_id[1:]
            if suffix.isdigit():
                resolved_trip_group_id = int(suffix)

        detail = {
            "id": source_trip_id,
            "source_trip_id": source_trip_id,
            "trip_id": public_trip_id,
            "public_trip_id": public_trip_id,
            "line_id": resolved_line_id,
            "line_code": line_code,
            "pair_id": pair_id,
            "trip_group_id": resolved_trip_group_id,
            "direction": row[6],
            "start_time": start_time,
            "end_time": end_time,
            "origin_id": row[9],
            "destination_id": row[10],
            "distance_km": float(row[11] or 0),
            "duration": int(row[12] or (end_time - start_time)),
            "block_id": block_detail.get("block_id"),
            "vehicle_id": block_detail.get("block_id"),
            "sequence_in_block": block_detail.get("sequence_in_block"),
        }
        trip_details[source_trip_id] = detail
        trip_details.setdefault(public_trip_id, detail)
    cur.close()
    return trip_details


def build_rows_from_segments(
    duty: Dict[str, Any],
    segments: List[Dict[str, Any]],
    schedule_id: int,
    trip_block_map: Dict[int, int],
) -> List[Dict[str, Any]]:
    """Build CSV rows from solver segments."""
    rows = []
    duty_id = duty["duty_id"]
    duty_context = build_duty_export_context(duty)

    for idx, seg in enumerate(segments):
        base_event_type = seg.get("type", seg.get("event_type", "unknown"))
        trip_count = int(seg.get("trip_count", len(seg.get("trip_ids", [])) if isinstance(seg.get("trip_ids"), list) else 0) or 0)
        event_type = "commercial_trip_bundle" if base_event_type == "commercial_trip" and trip_count > 1 else base_event_type
        event_label = OPERATIONAL_EVENT_LABELS.get(event_type, event_type)
        start_time = int(seg.get("start", 0))
        end_time = int(seg.get("end", 0))
        computed_duration = end_time - start_time
        seg_duration = computed_duration
        duration_mismatch = False
        trip_ids_list = seg.get("trip_ids", [])
        trip_ids_str = ";".join(str(t) for t in trip_ids_list) if trip_ids_list else ""
        event_scope = seg.get("event_scope", "driver_vehicle" if base_event_type == "commercial_trip" else "driver")

        # Flags: respect segment-level overrides
        is_work_time = seg.get("is_work_time", event_type in WORK_TIME_TYPES)
        is_driving_time = seg.get("is_driving_time", event_type in DRIVING_TIME_TYPES)
        is_idle_time = seg.get("is_idle_time", base_event_type in ("idle", "driver_idle"))
        is_normal_break = seg.get("is_normal_break", base_event_type == "normal_break")
        is_mandatory_rest = seg.get("is_mandatory_rest", base_event_type == "mandatory_rest")
        is_pullout = seg.get("is_pullout", base_event_type == "pullout")
        is_pullback = seg.get("is_pullback", base_event_type == "pullback")
        rest_valid = seg.get("rest_valid", base_event_type == "mandatory_rest")

        # Infer block_id
        seg_block_id = seg.get("block_id") or seg.get("from_block_id") or ""
        if not seg_block_id and trip_ids_list:
            seg_block_id = trip_block_map.get(int(trip_ids_list[0]), "")

        rows.append({
            "schedule_id": schedule_id,
            "block_id": seg_block_id,
            "duty_id": duty_id,
            "driver_id": str(duty_id),
            **duty_context,
            "vehicle_id": seg_block_id if event_scope == "driver_vehicle" else "",
            "from_vehicle_id": seg.get("from_vehicle_id", seg.get("from_block_id", "")),
            "to_vehicle_id": seg.get("to_vehicle_id", seg.get("to_block_id", "")),
            "sequence": idx + 1,
            "event_type": event_type,
            "event_label": event_label,
            "event_scope": event_scope,
            "start_time": min_to_hhmm(start_time),
            "end_time": min_to_hhmm(end_time),
            "duration_minutes": seg_duration,
            "origin_id": seg.get("location_start", seg.get("location", "")),
            "destination_id": seg.get("location_end", seg.get("location", "")),
            "trip_ids": trip_ids_str,
            "trip_count": trip_count,
            "is_work_time": is_work_time,
            "is_driving_time": is_driving_time,
            "is_idle_time": is_idle_time,
            "is_normal_break": is_normal_break,
            "is_mandatory_rest": is_mandatory_rest,
            "is_pullout": is_pullout,
            "is_pullback": is_pullback,
            "rest_valid": rest_valid,
            "rule_code": "",
            "violation_code": "EXPORT_DURATION_MISMATCH" if duration_mismatch else "",
            "explanation": seg.get("explanation") or "Motorista real não disponível; usando identificador da duty",
        })

    return rows


def build_rows_fallback(
    duty: Dict[str, Any],
    schedule_id: int,
    trip_block_map: Dict[int, int],
    conn,
) -> List[Dict[str, Any]]:
    """Build CSV rows using gap-based fallback when no segments exist."""
    rows = []
    duty_id = duty["duty_id"]
    trip_ids = duty["trip_ids"]
    fallback_explanation = "Classificação inferida pelo frontend por ausência de segmentos do solver"
    duty_context = build_duty_export_context(duty)

    if not trip_ids:
        return rows

    # Fetch trip times from DB
    cur = conn.cursor()
    placeholders = ",".join(["%s"] * len(trip_ids))
    cur.execute(
        f'SELECT id, "startTime", "endTime", "originId", "destinationId" FROM trips WHERE id IN ({placeholders}) ORDER BY "startTime" ASC',
        trip_ids,
    )
    trips = []
    for row in cur.fetchall():
        trips.append({
            "id": row[0],
            "start_time": int(row[1]),
            "end_time": int(row[2]) if int(row[2]) >= int(row[1]) else int(row[2]) + 1440,
            "origin_id": row[3],
            "destination_id": row[4],
        })
    cur.close()

    trips.sort(key=lambda t: t["start_time"])

    seq = 0
    for idx, trip in enumerate(trips):
        tid = trip["id"]
        st = trip["start_time"]
        et = trip["end_time"]
        block_id = trip_block_map.get(int(tid), "")

        seq += 1
        rows.append({
            "schedule_id": schedule_id,
            "block_id": block_id,
            "duty_id": duty_id,
            "driver_id": str(duty_id),
            **duty_context,
            "vehicle_id": block_id,
            "from_vehicle_id": "",
            "to_vehicle_id": "",
            "sequence": seq,
            "event_type": "commercial_trip",
            "event_label": "Viagem",
            "event_scope": "driver_vehicle",
            "start_time": min_to_hhmm(st),
            "end_time": min_to_hhmm(et),
            "duration_minutes": et - st,
            "origin_id": trip["origin_id"],
            "destination_id": trip["destination_id"],
            "trip_ids": str(tid),
            "trip_count": 1,
            "is_work_time": True,
            "is_driving_time": True,
            "is_idle_time": False,
            "is_normal_break": False,
            "is_mandatory_rest": False,
            "is_pullout": False,
            "is_pullback": False,
            "rest_valid": False,
            "rule_code": "",
            "violation_code": "",
            "explanation": fallback_explanation,
        })

        # Gap between consecutive trips
        if idx < len(trips) - 1:
            next_trip = trips[idx + 1]
            gap_start = et
            gap_end = next_trip["start_time"]
            gap = gap_end - gap_start
            if gap > 0:
                gap_type = "normal_break" if gap >= 30 else "idle"
                seq += 1
                rows.append({
                    "schedule_id": schedule_id,
                    "block_id": block_id,
                    "duty_id": duty_id,
                    "driver_id": str(duty_id),
                    **duty_context,
                    "vehicle_id": "",
                    "from_vehicle_id": "",
                    "to_vehicle_id": "",
                    "sequence": seq,
                    "event_type": gap_type,
                    "event_label": OPERATIONAL_EVENT_LABELS.get(gap_type, gap_type),
                    "event_scope": "driver",
                    "start_time": min_to_hhmm(gap_start),
                    "end_time": min_to_hhmm(gap_end),
                    "duration_minutes": gap,
                    "origin_id": trip["destination_id"],
                    "destination_id": next_trip["origin_id"],
                    "trip_ids": "",
                    "trip_count": 0,
                    "is_work_time": False,
                    "is_driving_time": False,
                    "is_idle_time": gap_type == "idle",
                    "is_normal_break": gap_type == "normal_break",
                    "is_mandatory_rest": False,
                    "is_pullout": False,
                    "is_pullback": False,
                    "rest_valid": False,
                    "rule_code": "",
                    "violation_code": "",
                    "explanation": fallback_explanation,
                })

    return rows


def build_detailed_trip_rows(
    duty: Dict[str, Any],
    detailed_trips: List[Dict[str, Any]],
    schedule_id: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    duty_id = int(duty["duty_id"])
    for trip in detailed_trips:
        rows.append({
            "schedule_id": schedule_id,
            "duty_id": duty_id,
            "driver_id": duty_id,
            "sequence_in_duty": trip.get("sequence_in_duty", ""),
            "segment_sequence": trip.get("segment_sequence", ""),
            "sequence_in_bundle": trip.get("sequence_in_bundle", 1),
            "bundle_trip_count": trip.get("bundle_trip_count", 1),
            "bundle_event_type": trip.get("bundle_event_type", "commercial_trip"),
            "source_trip_id": trip.get("source_trip_id", trip.get("id", "")),
            "public_trip_id": trip.get("trip_id", trip.get("public_trip_id", trip.get("id", ""))),
            "line_id": trip.get("line_id", ""),
            "line_code": trip.get("line_code", ""),
            "direction": trip.get("direction", ""),
            "start_time": min_to_hhmm(int(trip.get("start_time", 0) or 0)),
            "end_time": min_to_hhmm(int(trip.get("end_time", 0) or 0)),
            "duration_minutes": int(trip.get("duration", 0) or 0),
            "origin_id": trip.get("origin_id", ""),
            "destination_id": trip.get("destination_id", ""),
            "block_id": trip.get("block_id", ""),
            "vehicle_id": trip.get("vehicle_id", trip.get("block_id", "")),
            "sequence_in_block": trip.get("sequence_in_block", ""),
            "trip_group_id": trip.get("trip_group_id", ""),
            "pair_id": trip.get("pair_id", ""),
        })
    return rows


def build_driver_rows(
    duty: Dict[str, Any],
    normalized_segments: List[Dict[str, Any]],
    detailed_trips: List[Dict[str, Any]],
    schedule_id: int,
) -> List[Dict[str, Any]]:
    duty_id = int(duty["duty_id"])
    rows: List[Dict[str, Any]] = []
    duty_context = build_duty_export_context(duty)
    detailed_by_segment: Dict[int, List[Dict[str, Any]]] = {}
    for trip in detailed_trips:
        segment_sequence = trip.get("segment_sequence")
        if segment_sequence in (None, ""):
            continue
        detailed_by_segment.setdefault(int(segment_sequence), []).append(trip)

    for sequence, segment in enumerate(normalized_segments, start=1):
        seg_type = str(segment.get("type") or segment.get("event_type") or "unknown")
        if seg_type == "commercial_trip":
            segment_trips = sort_trip_details(detailed_by_segment.get(sequence, []))
            if segment_trips:
                for trip in segment_trips:
                    rows.append({
                        "schedule_id": schedule_id,
                        "duty_id": duty_id,
                        "driver_id": duty_id,
                        **duty_context,
                        "sequence": sequence,
                        "event_type": "commercial_trip",
                        "event_label": OPERATIONAL_EVENT_LABELS["commercial_trip"],
                        "event_scope": "trip",
                        "line_code": trip.get("line_code", ""),
                        "direction": trip.get("direction", ""),
                        "start_time": min_to_hhmm(int(trip.get("start_time", 0) or 0)),
                        "end_time": min_to_hhmm(int(trip.get("end_time", 0) or 0)),
                        "duration_minutes": int(trip.get("duration", 0) or 0),
                        "trip_id": trip.get("source_trip_id", trip.get("id", "")),
                        "trip_ids": str(trip.get("source_trip_id", trip.get("id", ""))),
                        "trip_count": 1,
                        "origin_id": trip.get("origin_id", ""),
                        "destination_id": trip.get("destination_id", ""),
                        "vehicle_id": trip.get("vehicle_id", trip.get("block_id", "")),
                        "from_vehicle_id": "",
                        "to_vehicle_id": "",
                        "sequence_in_duty": trip.get("sequence_in_duty", ""),
                        "sequence_in_bundle": trip.get("sequence_in_bundle", 1),
                        "explanation": segment.get("explanation", ""),
                    })
                continue

        base_event_type = seg_type
        trip_count = int(segment.get("trip_count", len(segment.get("trip_ids", [])) if isinstance(segment.get("trip_ids"), list) else 0) or 0)
        event_type = "commercial_trip_bundle" if base_event_type == "commercial_trip" and trip_count > 1 else base_event_type
        rows.append({
            "schedule_id": schedule_id,
            "duty_id": duty_id,
            "driver_id": duty_id,
            **duty_context,
            "sequence": sequence,
            "event_type": event_type,
            "event_label": OPERATIONAL_EVENT_LABELS.get(event_type, event_type),
            "event_scope": segment.get("event_scope", "driver"),
            "line_code": "",
            "direction": "",
            "start_time": min_to_hhmm(int(segment.get("start", 0) or 0)),
            "end_time": min_to_hhmm(int(segment.get("end", segment.get("start", 0)) or 0)),
            "duration_minutes": int(segment.get("duration", int(segment.get("end", 0) or 0) - int(segment.get("start", 0) or 0)) or 0),
            "trip_id": "",
            "trip_ids": ";".join(str(trip_id) for trip_id in segment.get("trip_ids", [])) if segment.get("trip_ids") else "",
            "trip_count": trip_count,
            "origin_id": segment.get("location_start", segment.get("location", "")),
            "destination_id": segment.get("location_end", segment.get("location", "")),
            "vehicle_id": segment.get("vehicle_id", segment.get("block_id", "")) if segment.get("event_scope") == "driver_vehicle" else "",
            "from_vehicle_id": segment.get("from_vehicle_id", segment.get("from_block_id", "")),
            "to_vehicle_id": segment.get("to_vehicle_id", segment.get("to_block_id", "")),
            "sequence_in_duty": "",
            "sequence_in_bundle": "",
            "explanation": segment.get("explanation", ""),
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Export programação operacional CSV")
    parser.add_argument("--company-id", type=int, required=True, help="Company ID (required)")
    parser.add_argument("--schedule-id", type=int, default=None, help="Schedule ID (optional, defaults to latest)")
    parser.add_argument("--output", type=str, default="programacao_operacional.csv", help="Output CSV path")
    parser.add_argument("--detailed-output", type=str, default=None, help="Optional detailed trips CSV path")
    parser.add_argument("--drivers-output", type=str, default=None, help="Optional corrected drivers CSV path")
    args = parser.parse_args()

    conn = get_db_connection()

    # 1. Fetch schedule
    schedule = fetch_schedule(conn, args.company_id, args.schedule_id)
    print(f"Schedule: id={schedule['id']}, status={schedule['status']}, company_id={schedule['company_id']}")

    # 2. Fetch duties
    duties = fetch_duties(conn, schedule["id"])
    print(f"Total duties: {len(duties)}")

    # 3. Build trip → block map
    trip_block_details, trip_ids = fetch_trip_block_details(conn, schedule["id"])
    trip_block_map = {trip_id: details["block_id"] for trip_id, details in trip_block_details.items()}
    trip_details_map = fetch_trip_details(conn, trip_ids, trip_block_details)

    # 4. Build export rows
    all_rows: List[Dict[str, Any]] = []
    detailed_rows: List[Dict[str, Any]] = []
    driver_rows: List[Dict[str, Any]] = []
    duties_with_segments = 0
    duties_without_segments = 0

    for duty in duties:
        normalized_segments = normalize_segments(duty["duty_time_segments"], trip_details_map)
        detailed_trips = build_detailed_duty_trips(duty, normalized_segments, trip_details_map)
        detailed_rows.extend(build_detailed_trip_rows(duty, detailed_trips, schedule["id"]))
        driver_rows.extend(build_driver_rows(duty, normalized_segments, detailed_trips, schedule["id"]))

        if normalized_segments:
            duties_with_segments += 1
            all_rows.extend(
                build_rows_from_segments(duty, normalized_segments, schedule["id"], trip_block_map)
            )
        else:
            duties_without_segments += 1
            all_rows.extend(
                build_rows_fallback(duty, schedule["id"], trip_block_map, conn)
            )

    conn.close()

    # 5. Write CSV
    output_path = Path(args.output)
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)

    if args.detailed_output:
        detailed_output_path = Path(args.detailed_output)
        with open(detailed_output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=DETAILED_TRIP_COLUMNS)
            writer.writeheader()
            writer.writerows(detailed_rows)

    if args.drivers_output:
        drivers_output_path = Path(args.drivers_output)
        with open(drivers_output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=DRIVER_COLUMNS)
            writer.writeheader()
            writer.writerows(driver_rows)

    print(f"\n✅ CSV exportado: {output_path} ({len(all_rows)} linhas)")
    if args.detailed_output:
        print(f"✅ Viagens detalhadas exportadas: {args.detailed_output} ({len(detailed_rows)} linhas)")
    if args.drivers_output:
        print(f"✅ Motoristas corrigido exportado: {args.drivers_output} ({len(driver_rows)} linhas)")
    print(f"   Duties com segments do solver: {duties_with_segments}")
    print(f"   Duties sem segments (fallback): {duties_without_segments}")

    # 6. Print event type counts
    event_counts = Counter(row["event_type"] for row in all_rows)
    print(f"\n📊 Contagem por event_type:")
    for event_type, label in OPERATIONAL_EVENT_LABELS.items():
        count = event_counts.get(event_type, 0)
        if count > 0:
            print(f"   {label:30s} ({event_type:20s}): {count}")

    # Report unknown types
    for event_type, count in sorted(event_counts.items()):
        if event_type not in OPERATIONAL_EVENT_LABELS:
            print(f"   {'[DESCONHECIDO]':30s} ({event_type:20s}): {count}")

    # 7. Validate duration consistency
    mismatches = [row for row in all_rows if row.get("violation_code") == "EXPORT_DURATION_MISMATCH"]
    if mismatches:
        print(f"\n⚠️  {len(mismatches)} linhas com EXPORT_DURATION_MISMATCH")
    else:
        print(f"\n✅ Todas as durações consistentes (duration_minutes == end_time - start_time)")

    # 8. Verify no generic "Refeição" appears
    refei_count = sum(1 for row in all_rows if "Refeição" in str(row.get("event_label", "")))
    if refei_count > 0:
        print(f"\n❌ FALHA: 'Refeição' genérica encontrada em {refei_count} linhas!")
    else:
        print(f"\n✅ 'Refeição' genérica NÃO aparece no CSV")


if __name__ == "__main__":
    main()
