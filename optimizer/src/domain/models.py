"""
Modelos de domínio centrais do OTIMIZ Optimizer.
Representam os dados do problema VSP/CSP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AlgorithmType(str, Enum):
    GREEDY = "greedy"
    GENETIC = "genetic"
    SIMULATED_ANNEALING = "simulated_annealing"
    TABU_SEARCH = "tabu_search"
    SET_PARTITIONING = "set_partitioning"
    MCNF = "mcnf"
    JOINT_SOLVER = "joint_solver"
    HYBRID_PIPELINE = "hybrid_pipeline"


class SolverPhase(str, Enum):
    VSP = "vsp"
    CSP = "csp"
    INTEGRATED = "integrated"


@dataclass
class Trip:
    id: int
    line_id: int
    start_time: int
    end_time: int
    origin_id: int
    destination_id: int
    trip_group_id: Optional[int] = None
    direction: Optional[str] = None  # 'outbound' | 'return' — sent by backend
    duration: int = 0
    distance_km: float = 0.0
    depot_id: Optional[int] = None
    relief_point_id: Optional[int] = None
    is_relief_point: bool = False
    mid_trip_relief_point_id: Optional[int] = None
    mid_trip_relief_offset_minutes: Optional[int] = None
    mid_trip_relief_distance_ratio: Optional[float] = None
    mid_trip_relief_elevation_ratio: Optional[float] = None
    original_trip_id: Optional[int] = None
    segment_index: int = 0
    segment_count: int = 1
    energy_kwh: float = 0.0
    elevation_gain_m: float = 0.0
    service_day: Optional[int] = None
    is_holiday: bool = False
    origin_latitude: Optional[float] = None
    origin_longitude: Optional[float] = None
    destination_latitude: Optional[float] = None
    destination_longitude: Optional[float] = None
    sent_to_driver_terminal: Optional[bool] = None
    gps_valid: Optional[bool] = None
    deadhead_times: Dict[int, int] = field(default_factory=dict)
    idle_before_minutes: int = 0
    idle_after_minutes: int = 0
    is_pull_out: bool = False
    is_pull_back: bool = False

    def __post_init__(self):
        if self.duration == 0:
            self.duration = max(0, self.end_time - self.start_time)
        if self.service_day is None:
            self.service_day = self.start_time // 1440

    def can_precede(self, other: "Trip", default_deadhead: int = 0) -> bool:
        if other.is_continuation_of(self):
            return True
        gap = other.start_time - self.end_time
        needed = self.deadhead_times.get(other.origin_id, default_deadhead)
        return gap >= needed

    def fmt_time(self, minutes: int) -> str:
        h, m = divmod(minutes, 60)
        return f"{h:02d}:{m:02d}"

    @property
    def start_fmt(self) -> str:
        return self.fmt_time(self.start_time)

    @property
    def end_fmt(self) -> str:
        return self.fmt_time(self.end_time)

    @property
    def public_id(self) -> int:
        return int(self.original_trip_id or self.id)

    @property
    def is_mid_trip_segment(self) -> bool:
        return self.original_trip_id is not None and self.segment_count > 1

    @property
    def ends_at_mid_trip_relief(self) -> bool:
        return self.is_mid_trip_segment and self.segment_index < self.segment_count - 1

    @property
    def starts_at_mid_trip_relief(self) -> bool:
        return self.is_mid_trip_segment and self.segment_index > 0

    def is_continuation_of(self, other: "Trip") -> bool:
        if self.original_trip_id is None or other.original_trip_id is None:
            return False
        if self.original_trip_id != other.original_trip_id:
            return False
        if self.segment_index != other.segment_index + 1:
            return False
        return self.start_time == other.end_time and self.origin_id == other.destination_id


@dataclass
class VehicleType:
    id: int
    name: str
    passenger_capacity: int
    cost_per_km: float = 0.0
    cost_per_hour: float = 0.0
    fixed_cost: float = 800.0
    is_electric: bool = False
    battery_capacity_kwh: float = 0.0
    minimum_soc: float = 0.15
    charge_rate_kw: float = 0.0
    energy_cost_per_kwh: float = 0.0
    depot_id: Optional[int] = None

    def trip_cost(self, trip: Trip) -> float:
        return (
            self.cost_per_km * trip.distance_km
            + self.cost_per_hour * (trip.duration / 60)
        )


@dataclass
class DutySegment:
    block_id: int
    trips: List[Trip] = field(default_factory=list)

    @property
    def start_time(self) -> int:
        return self.trips[0].start_time if self.trips else 0

    @property
    def end_time(self) -> int:
        return self.trips[-1].end_time if self.trips else 0

    @property
    def drive_minutes(self) -> int:
        return sum(t.duration for t in self.trips)


@dataclass
class Block:
    id: int
    trips: List[Trip] = field(default_factory=list)
    vehicle_type_id: Optional[int] = None
    warnings: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def start_time(self) -> int:
        return self.trips[0].start_time if self.trips else 0

    @property
    def end_time(self) -> int:
        return self.trips[-1].end_time if self.trips else 0

    @property
    def total_duration(self) -> int:
        return self.end_time - self.start_time

    @property
    def total_drive_minutes(self) -> int:
        return sum(t.duration for t in self.trips)

    @property
    def idle_minutes(self) -> int:
        return self.total_duration - self.total_drive_minutes

    def total_deadhead_minutes(self) -> int:
        total = 0
        for i in range(len(self.trips) - 1):
            t1, t2 = self.trips[i], self.trips[i + 1]
            total += t1.deadhead_times.get(t2.origin_id, 0)
        return total

    def verify_no_overlap(self) -> List[str]:
        issues = []
        for i in range(len(self.trips) - 1):
            a, b = self.trips[i], self.trips[i + 1]
            if b.start_time < a.end_time:
                issues.append(
                    f"Sobreposição: viagem#{a.id} termina {a.end_fmt} > viagem#{b.id} inicia {b.start_fmt}"
                )
        return issues


@dataclass
class Duty:
    id: int
    tasks: List[Block] = field(default_factory=list)
    segments: List[DutySegment] = field(default_factory=list)
    spread_time: int = 0
    work_time: int = 0
    rest_violations: int = 0
    shift_violations: int = 0
    continuous_driving_violation: bool = False
    warnings: List[str] = field(default_factory=list)
    paid_minutes: int = 0
    overtime_minutes: int = 0
    nocturnal_minutes: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def all_trips(self) -> List[Trip]:
        return [t for seg in self.segments for t in seg.trips]

    @property
    def start_time(self) -> int:
        return self.segments[0].start_time if self.segments else 0

    @property
    def end_time(self) -> int:
        return self.segments[-1].end_time if self.segments else 0

    def add_task(self, block: Block) -> None:
        self.tasks.append(block)
        self.segments.append(DutySegment(block_id=block.id, trips=list(block.trips)))
        self._recalculate()

    def _recalculate(self) -> None:
        if not self.segments:
            return
        self.work_time = sum(t.duration for seg in self.segments for t in seg.trips)
        self.spread_time = self.end_time - self.start_time
        if self.paid_minutes == 0:
            self.paid_minutes = self.work_time


@dataclass
class VSPSolution:
    blocks: List[Block] = field(default_factory=list)
    total_cost: float = 0.0
    unassigned_trips: List[Trip] = field(default_factory=list)
    algorithm: str = ""
    iterations: int = 0
    elapsed_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def num_vehicles(self) -> int:
        return len(self.blocks)

    def is_feasible(self) -> bool:
        return len(self.unassigned_trips) == 0


@dataclass
class CSPSolution:
    duties: List[Duty] = field(default_factory=list)
    total_cost: float = 0.0
    uncovered_blocks: List[Block] = field(default_factory=list)
    cct_violations: int = 0
    algorithm: str = ""
    elapsed_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def num_crew(self) -> int:
        roster_count = self.meta.get("roster_count") if isinstance(self.meta, dict) else None
        return int(roster_count) if roster_count is not None else len(self.duties)

    def is_feasible(self) -> bool:
        return len(self.uncovered_blocks) == 0 and self.cct_violations == 0


@dataclass
class OptimizationResult:
    vsp: VSPSolution
    csp: CSPSolution
    total_cost: float = 0.0
    algorithm: AlgorithmType = AlgorithmType.HYBRID_PIPELINE
    total_elapsed_ms: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        merged_meta = {**(self.vsp.meta or {}), **(self.csp.meta or {}), **(self.meta or {})}
        cost_breakdown = merged_meta.get("cost_breakdown") or {}
        vsp_breakdown = cost_breakdown.get("vsp") or {}
        csp_breakdown = cost_breakdown.get("csp") or {}
        block_costs = {
            int(item.get("block_id")): item
            for item in (vsp_breakdown.get("blocks") or [])
            if item.get("block_id") is not None
        }
        duty_costs = {
            int(item.get("duty_id")): item
            for item in (csp_breakdown.get("duties") or [])
            if item.get("duty_id") is not None
        }
        return {
            "vehicles": self.vsp.num_vehicles,
            "crew": self.csp.num_crew,
            "total_trips": sum(len(b.trips) for b in self.vsp.blocks),
            "total_cost": round(self.total_cost, 2),
            "cct_violations": self.csp.cct_violations,
            "unassigned_trips": len(self.vsp.unassigned_trips),
            "uncovered_blocks": len(self.csp.uncovered_blocks),
            "vsp_algorithm": self.vsp.algorithm,
            "csp_algorithm": self.csp.algorithm,
            "elapsed_ms": round(self.total_elapsed_ms, 1),
            "warnings": [*self.vsp.warnings, *self.csp.warnings],
            "cost_breakdown": cost_breakdown,
            "solver_explanation": merged_meta.get("solver_explanation"),
            "phase_summary": merged_meta.get("phase_summary"),
            "trip_group_audit": merged_meta.get("trip_group_audit"),
            "reproducibility": merged_meta.get("reproducibility"),
            "meta": merged_meta,
            "blocks": [
                {
                    "block_id": b.id,
                    "trips": [
                        {
                            "id": t.id,
                            "start_time": t.start_time,
                            "end_time": t.end_time,
                            "origin_id": t.origin_id,
                            "destination_id": t.destination_id,
                            "line_id": t.line_id,
                            "is_pull_out": t.is_pull_out,
                            "is_pull_back": t.is_pull_back,
                            "duration": t.duration,
                        }
                        for t in b.trips
                    ],
                    "num_trips": len(b.trips),
                    "start_time": b.start_time,
                    "end_time": b.end_time,
                    "warnings": b.warnings,
                    "meta": b.meta,
                    **{
                        "activation_cost": round(float(block_costs.get(int(b.id), {}).get("activation", 0.0) or 0.0), 2),
                        "connection_cost": round(float(block_costs.get(int(b.id), {}).get("connection", 0.0) or 0.0), 2),
                        "distance_cost": round(float(block_costs.get(int(b.id), {}).get("distance", 0.0) or 0.0), 2),
                        "time_cost": round(float(block_costs.get(int(b.id), {}).get("time", 0.0) or 0.0), 2),
                        "idle_cost": round(float(block_costs.get(int(b.id), {}).get("idle_cost", 0.0) or 0.0), 2),
                        "total_cost": round(float(block_costs.get(int(b.id), {}).get("total", 0.0) or 0.0), 2),
                    },
                }
                for b in self.vsp.blocks
            ],
            "duties": [
                {
                    "duty_id": d.id,
                    "start_time": d.start_time,
                    "end_time": d.end_time,
                    "blocks": list(dict.fromkeys(int(b.meta.get("source_block_id", b.id)) for b in d.tasks)),
                    "trip_ids": list(
                        dict.fromkeys(
                            int(tid)
                            for tid in (
                                d.meta.get("covered_original_trip_ids")
                                or [getattr(trip, "public_id", trip.id) for trip in d.all_trips]
                            )
                        )
                    ),
                    "trips": [
                        {
                            "id": t.id,
                            "trip_id": t.public_id,
                            "segment_index": t.segment_index,
                            "segment_count": t.segment_count,
                            "start_time": t.start_time,
                            "end_time": t.end_time,
                            "origin_id": t.origin_id,
                            "destination_id": t.destination_id,
                            "line_id": t.line_id,
                            "block_id": int(next((task.meta.get("source_block_id", task.id) for task in d.tasks if t in task.trips), 0) or 0),
                            "is_pull_out": t.is_pull_out,
                            "is_pull_back": t.is_pull_back,
                            "duration": t.duration,
                        }
                        for t in d.all_trips
                    ],
                    "segments": [
                        {
                            "block_id": int(task.meta.get("source_block_id", task.id)),
                            "drive_minutes": sum(t.duration for t in task.trips),
                            "trip_ids": list(dict.fromkeys(int(getattr(t, "public_id", t.id)) for t in task.trips)),
                            "trips": [
                                {
                                    "id": t.id,
                                    "trip_id": t.public_id,
                                    "segment_index": t.segment_index,
                                    "segment_count": t.segment_count,
                                    "start_time": t.start_time,
                                    "end_time": t.end_time,
                                    "origin_id": t.origin_id,
                                    "destination_id": t.destination_id,
                                    "line_id": t.line_id,
                                    "block_id": int(task.meta.get("source_block_id", task.id)),
                                    "is_pull_out": t.is_pull_out,
                                    "is_pull_back": t.is_pull_back,
                                    "duration": t.duration,
                                }
                                for t in task.trips
                            ],
                        }
                        for task in d.tasks
                    ],
                    "work_time": d.work_time,
                    "spread_time": d.spread_time,
                    "rest_violations": d.rest_violations,
                    "warnings": d.warnings,
                    "paid_minutes": d.paid_minutes,
                    "overtime_minutes": d.overtime_minutes,
                    "nocturnal_minutes": d.nocturnal_minutes,
                    "meta": d.meta,
                    **{
                        "work_cost": round(float(duty_costs.get(int(d.id), {}).get("work_cost", 0.0) or 0.0), 2),
                        "guaranteed_cost": round(float(duty_costs.get(int(d.id), {}).get("guaranteed_cost", 0.0) or 0.0), 2),
                        "waiting_cost": round(float(duty_costs.get(int(d.id), {}).get("waiting_cost", 0.0) or 0.0), 2),
                        "overtime_cost": round(float(duty_costs.get(int(d.id), {}).get("overtime_cost", 0.0) or 0.0), 2),
                        "long_unpaid_break_penalty": round(float(duty_costs.get(int(d.id), {}).get("long_unpaid_break_penalty", 0.0) or 0.0), 2),
                        "nocturnal_extra_cost": round(float(duty_costs.get(int(d.id), {}).get("nocturnal_extra", 0.0) or 0.0), 2),
                        "holiday_extra_cost": round(float(duty_costs.get(int(d.id), {}).get("holiday_extra", 0.0) or 0.0), 2),
                        "cct_penalties_cost": round(float(duty_costs.get(int(d.id), {}).get("cct_penalties", 0.0) or 0.0), 2),
                        "total_cost": round(float(duty_costs.get(int(d.id), {}).get("total", 0.0) or 0.0), 2),
                    },
                }
                for d in self.csp.duties
            ],
        }


class RuleType(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"


@dataclass
class RosteringRule:
    rule_id: str
    type: RuleType
    weight: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OperatorProfile:
    id: str
    name: str
    cp: str
    last_shift_end: int = 0  # Timestamp em minutos desde meia-noite (D-1 ou D)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NominalAssignment:
    operator_id: str
    duty_id: int
    score: float = 0.0
    explanations: List[str] = field(default_factory=list)


@dataclass
class NominalRosteringSolution:
    assignments: List[NominalAssignment] = field(default_factory=list)
    unassigned_duties: List[int] = field(default_factory=list)
    total_utility: float = 0.0
    elapsed_ms: float = 0.0
    logs: List[str] = field(default_factory=list)
    algorithm: str = "nominal_assignment_pulp"
