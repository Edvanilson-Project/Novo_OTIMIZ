"""
Relief Vehicle Estimator — analisa jornadas CSP para identificar
rendições de motoristas e estimar a frota mínima de veículos de apoio.

Uma "rendição" ocorre quando dois motoristas distintos cobrem partes
diferentes do mesmo bloco de veículo.  O veículo de apoio leva o
motorista substituto ao ponto de rendição e, opcionalmente, retorna
com o motorista rendido ao depósito.

Estimativa de frota:  greedy earliest-deadline — um veículo de apoio
pode cobrir várias rendições consecutivas se terminar cada uma a
tempo de chegar na próxima (usando travel_minutes como deslocamento).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...domain.models import CSPSolution, Duty

_DEFAULT_TRAVEL_MINUTES = 15  # deslocamento assumido entre rendições (sem geodados)
_DEFAULT_RELIEF_COST_PER_EVENT = 50.0  # custo fixo por rendição (veículo de apoio)


@dataclass
class ReliefEvent:
    block_id: int
    from_duty_id: int
    to_duty_id: int
    handoff_time: int  # minutos desde meia-noite
    location_id: int  # origin_id do 1º trip do segmento substituto
    from_duty_end: int  # fim do segmento cedente
    to_duty_start: int  # início do segmento substituto (≈ handoff_time)


@dataclass
class ReliefVehicleEstimate:
    total_events: int
    min_vehicles: int
    peak_hour: Optional[int]  # hora do pico de rendições (0-23)
    total_cost: float
    events: List[ReliefEvent] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        by_hour: Dict[int, int] = {}
        for e in self.events:
            h = e.handoff_time // 60
            by_hour[h] = by_hour.get(h, 0) + 1
        return {
            "total_events": self.total_events,
            "min_vehicles": self.min_vehicles,
            "peak_hour": self.peak_hour,
            "total_cost": round(self.total_cost, 2),
            "hourly_distribution": {str(h): c for h, c in sorted(by_hour.items())},
            "events": [
                {
                    "block_id": e.block_id,
                    "from_duty_id": e.from_duty_id,
                    "to_duty_id": e.to_duty_id,
                    "handoff_time": e.handoff_time,
                    "location_id": e.location_id,
                }
                for e in self.events
            ],
        }


class ReliefVehicleEstimator:
    """Identifica rendições em CSPSolution e estima frota de apoio."""

    def __init__(
        self,
        travel_minutes: int = _DEFAULT_TRAVEL_MINUTES,
        cost_per_event: float = _DEFAULT_RELIEF_COST_PER_EVENT,
    ) -> None:
        self.travel_minutes = int(travel_minutes)
        self.cost_per_event = float(cost_per_event)

    def estimate(self, csp: CSPSolution) -> ReliefVehicleEstimate:
        if not csp or not csp.duties:
            return ReliefVehicleEstimate(total_events=0, min_vehicles=0, peak_hour=None, total_cost=0.0)

        events = self._find_relief_events(csp.duties)
        min_vehicles = self._min_fleet(events)
        peak_hour = self._peak_hour(events)
        total_cost = len(events) * self.cost_per_event

        return ReliefVehicleEstimate(
            total_events=len(events),
            min_vehicles=min_vehicles,
            peak_hour=peak_hour,
            total_cost=total_cost,
            events=events,
        )

    def _find_relief_events(self, duties: List[Duty]) -> List[ReliefEvent]:
        """Para cada bloco VSP original, detecta transições entre motoristas distintos.

        Usa `duty.tasks` com `meta["source_block_id"]` para identificar o bloco VSP
        original, ignorando os IDs sintéticos criados pelo CSP durante o run-cutting.
        """
        # source_block_id → [(start_time, end_time, duty_id, location_id)]
        block_segments: Dict[int, List] = {}

        for duty in duties:
            # Usa tasks (Block objects) que preservam source_block_id do VSP
            for task in duty.tasks:
                if not task.trips:
                    continue
                source_bid = int(task.meta.get("source_block_id", task.id))
                task_trips_sorted = sorted(task.trips, key=lambda t: t.start_time)
                start_t = task_trips_sorted[0].start_time
                end_t = task_trips_sorted[-1].end_time
                loc_id = task_trips_sorted[0].origin_id
                block_segments.setdefault(source_bid, []).append(
                    (start_t, end_t, duty.id, loc_id)
                )

        events: List[ReliefEvent] = []
        for block_id, segs in block_segments.items():
            # Ordenar por start_time; múltiplos segmentos = há rendição
            segs.sort(key=lambda s: s[0])
            for i in range(len(segs) - 1):
                prev_start, prev_end, prev_duty, _ = segs[i]
                next_start, next_end, next_duty, loc_id = segs[i + 1]
                if prev_duty == next_duty:
                    # mesmo motorista — não é rendição
                    continue
                events.append(
                    ReliefEvent(
                        block_id=block_id,
                        from_duty_id=prev_duty,
                        to_duty_id=next_duty,
                        handoff_time=next_start,
                        location_id=loc_id,
                        from_duty_end=prev_end,
                        to_duty_start=next_start,
                    )
                )

        events.sort(key=lambda e: e.handoff_time)
        return events

    def _min_fleet(self, events: List[ReliefEvent]) -> int:
        """Greedy earliest-finish: conta veículos de apoio mínimos."""
        if not events:
            return 0

        # available[i] = tempo em que o i-ésimo veículo de apoio fica livre
        available: List[int] = []

        for ev in events:
            # O veículo precisa estar no ponto antes de handoff_time
            # após cobrir a rendição, fica livre em handoff_time + travel_minutes
            earliest_free = ev.handoff_time + self.travel_minutes
            reused = False
            for i, free_at in enumerate(available):
                if free_at <= ev.handoff_time:
                    available[i] = earliest_free
                    reused = True
                    break
            if not reused:
                available.append(earliest_free)

        return len(available)

    def _peak_hour(self, events: List[ReliefEvent]) -> Optional[int]:
        if not events:
            return None
        by_hour: Dict[int, int] = {}
        for e in events:
            h = e.handoff_time // 60
            by_hour[h] = by_hour.get(h, 0) + 1
        return max(by_hour, key=lambda h: by_hour[h])
