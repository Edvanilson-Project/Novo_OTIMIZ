"""Conversores compartilhados entre rotas da API."""
from __future__ import annotations

from ..domain.models import Trip


def to_trip(t) -> Trip:
    """Converte schema Pydantic (ou objeto com atributos) em Trip de domínio."""
    return Trip(
        id=t.id,
        line_id=t.line_id,
        trip_group_id=t.trip_group_id,
        direction=getattr(t, "direction", None),
        start_time=t.start_time,
        end_time=t.end_time,
        origin_id=t.origin_id,
        destination_id=t.destination_id,
        duration=t.duration,
        distance_km=t.distance_km,
        depot_id=t.depot_id,
        relief_point_id=t.relief_point_id,
        is_relief_point=t.is_relief_point,
        mid_trip_relief_point_id=getattr(t, "mid_trip_relief_point_id", None),
        mid_trip_relief_offset_minutes=getattr(t, "mid_trip_relief_offset_minutes", None),
        mid_trip_relief_distance_ratio=getattr(t, "mid_trip_relief_distance_ratio", None),
        mid_trip_relief_elevation_ratio=getattr(t, "mid_trip_relief_elevation_ratio", None),
        energy_kwh=t.energy_kwh,
        elevation_gain_m=t.elevation_gain_m,
        service_day=t.service_day,
        is_holiday=t.is_holiday,
        origin_latitude=t.origin_latitude,
        origin_longitude=t.origin_longitude,
        destination_latitude=t.destination_latitude,
        destination_longitude=t.destination_longitude,
        sent_to_driver_terminal=t.sent_to_driver_terminal,
        gps_valid=t.gps_valid,
        deadhead_times={int(k): v for k, v in (t.deadhead_times or {}).items()},
        idle_before_minutes=getattr(t, "idle_before_minutes", 0),
        idle_after_minutes=getattr(t, "idle_after_minutes", 0),
        is_pull_out=getattr(t, "is_pull_out", False),
        is_pull_back=getattr(t, "is_pull_back", False),
    )
