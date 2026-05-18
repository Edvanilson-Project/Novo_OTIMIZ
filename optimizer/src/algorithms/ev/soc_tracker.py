"""
EV State-of-Charge Tracker — simula SoC por viagem em cada bloco.

Entrada: VSPSolution + VehicleType (EV), parâmetros de consumo.
Saída: relatório por bloco com SoC inicial/final por viagem,
       necessidade de recarga, custo energético.

Usado pelo reports layer e pela resposta de otimização quando
o VehicleType é EV (is_electric=True).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ...domain.models import Block, VehicleType, VSPSolution

_DEFAULT_KWH_PER_KM = 1.8
_DEFAULT_CHARGE_EFFICIENCY = 0.90  # eficiência de recarga (90%)


@dataclass
class TripSoCEvent:
    trip_id: int
    start_time: int
    end_time: int
    distance_km: float
    soc_before_kwh: float
    energy_consumed_kwh: float
    gap_minutes: int  # gap para próxima trip (0 se última)
    energy_recharged_kwh: float  # energia recuperada no gap
    soc_after_kwh: float
    below_minimum: bool


@dataclass
class BlockSoCReport:
    block_id: int
    total_distance_km: float
    total_energy_kwh: float
    total_recharged_kwh: float
    total_energy_cost: float
    soc_start_kwh: float
    soc_end_kwh: float
    minimum_soc_reached_kwh: float
    needs_mid_block_charge: bool
    trips: List[TripSoCEvent] = field(default_factory=list)


@dataclass
class EVFleetSoCReport:
    is_ev: bool
    battery_kwh: float
    minimum_soc_kwh: float
    kwh_per_km: float
    energy_cost_per_kwh: float
    total_energy_kwh: float
    total_energy_cost: float
    total_recharged_kwh: float
    blocks_needing_mid_charge: int
    blocks: List[BlockSoCReport] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_ev": self.is_ev,
            "battery_kwh": self.battery_kwh,
            "minimum_soc_kwh": self.minimum_soc_kwh,
            "kwh_per_km": self.kwh_per_km,
            "energy_cost_per_kwh": self.energy_cost_per_kwh,
            "total_energy_kwh": round(self.total_energy_kwh, 2),
            "total_energy_cost": round(self.total_energy_cost, 2),
            "total_recharged_kwh": round(self.total_recharged_kwh, 2),
            "blocks_needing_mid_charge": self.blocks_needing_mid_charge,
            "blocks": [
                {
                    "block_id": b.block_id,
                    "total_distance_km": round(b.total_distance_km, 2),
                    "total_energy_kwh": round(b.total_energy_kwh, 2),
                    "total_recharged_kwh": round(b.total_recharged_kwh, 2),
                    "total_energy_cost": round(b.total_energy_cost, 2),
                    "soc_start_kwh": round(b.soc_start_kwh, 2),
                    "soc_end_kwh": round(b.soc_end_kwh, 2),
                    "minimum_soc_reached_kwh": round(b.minimum_soc_reached_kwh, 2),
                    "needs_mid_block_charge": b.needs_mid_block_charge,
                    "trips": [
                        {
                            "trip_id": e.trip_id,
                            "start_time": e.start_time,
                            "end_time": e.end_time,
                            "distance_km": round(e.distance_km, 2),
                            "soc_before_kwh": round(e.soc_before_kwh, 2),
                            "energy_consumed_kwh": round(e.energy_consumed_kwh, 2),
                            "energy_recharged_kwh": round(e.energy_recharged_kwh, 2),
                            "soc_after_kwh": round(e.soc_after_kwh, 2),
                            "below_minimum": e.below_minimum,
                        }
                        for e in b.trips
                    ],
                }
                for b in self.blocks
            ],
        }


class EVSoCTracker:
    """Simula SoC ao longo dos blocos de uma solução VSP para frota EV."""

    def __init__(
        self,
        vehicle: VehicleType,
        kwh_per_km: float = _DEFAULT_KWH_PER_KM,
        charge_efficiency: float = _DEFAULT_CHARGE_EFFICIENCY,
    ) -> None:
        self.vehicle = vehicle
        self.is_ev = bool(vehicle.is_electric)
        self.battery_kwh = float(vehicle.battery_capacity_kwh)
        self.minimum_soc_kwh = self.battery_kwh * float(vehicle.minimum_soc)
        self.charge_rate_kw = float(vehicle.charge_rate_kw)
        self.energy_cost_per_kwh = float(vehicle.energy_cost_per_kwh)
        self.kwh_per_km = float(kwh_per_km)
        self.charge_efficiency = float(charge_efficiency)
        # Depósitos/terminais com carregador → recarga completa independente de tempo
        self.charger_location_ids: set = set(getattr(vehicle, "charger_location_ids", []) or [])

    def track(self, solution: VSPSolution) -> EVFleetSoCReport:
        """Gera relatório SoC para todos os blocos da solução."""
        report = EVFleetSoCReport(
            is_ev=self.is_ev,
            battery_kwh=self.battery_kwh,
            minimum_soc_kwh=self.minimum_soc_kwh,
            kwh_per_km=self.kwh_per_km,
            energy_cost_per_kwh=self.energy_cost_per_kwh,
            total_energy_kwh=0.0,
            total_energy_cost=0.0,
            total_recharged_kwh=0.0,
            blocks_needing_mid_charge=0,
        )

        if not self.is_ev or not solution.blocks:
            return report

        for block in solution.blocks:
            block_report = self._track_block(block)
            report.blocks.append(block_report)
            report.total_energy_kwh += block_report.total_energy_kwh
            report.total_energy_cost += block_report.total_energy_cost
            report.total_recharged_kwh += block_report.total_recharged_kwh
            if block_report.needs_mid_block_charge:
                report.blocks_needing_mid_charge += 1

        return report

    def _track_block(self, block: Block) -> BlockSoCReport:
        trips = sorted(block.trips, key=lambda t: t.start_time)
        soc = self.battery_kwh  # começa com bateria cheia no depot
        total_distance = 0.0
        total_energy = 0.0
        total_recharged = 0.0
        min_soc_reached = soc
        needs_mid_charge = False
        events: List[TripSoCEvent] = []

        for i, trip in enumerate(trips):
            kwh_needed = trip.distance_km * self.kwh_per_km
            soc_before = soc
            soc_after_trip = soc - kwh_needed
            below_min = soc_after_trip < self.minimum_soc_kwh

            # Gap para próxima trip → recarregamento
            gap = 0
            recharged = 0.0
            if i < len(trips) - 1:
                nxt_trip = trips[i + 1]
                gap = nxt_trip.start_time - trip.end_time
                at_charger = bool(
                    self.charger_location_ids
                    and (
                        trip.destination_id in self.charger_location_ids
                        or nxt_trip.origin_id in self.charger_location_ids
                    )
                )
                if at_charger and gap > 0:
                    recharged = max(0.0, self.battery_kwh - soc_after_trip)
                elif gap > 0 and self.charge_rate_kw > 0:
                    max_charge = gap / 60.0 * self.charge_rate_kw * self.charge_efficiency
                    recharged = min(max_charge, self.battery_kwh - soc_after_trip)
                    recharged = max(0.0, recharged)

            soc_final = soc_after_trip + recharged

            events.append(
                TripSoCEvent(
                    trip_id=trip.id,
                    start_time=trip.start_time,
                    end_time=trip.end_time,
                    distance_km=trip.distance_km,
                    soc_before_kwh=soc_before,
                    energy_consumed_kwh=kwh_needed,
                    gap_minutes=gap,
                    energy_recharged_kwh=recharged,
                    soc_after_kwh=soc_final,
                    below_minimum=below_min,
                )
            )

            if soc_after_trip < min_soc_reached:
                min_soc_reached = soc_after_trip
            if below_min:
                needs_mid_charge = True

            total_distance += trip.distance_km
            total_energy += kwh_needed
            total_recharged += recharged
            soc = soc_final

        return BlockSoCReport(
            block_id=block.id,
            total_distance_km=total_distance,
            total_energy_kwh=total_energy,
            total_recharged_kwh=total_recharged,
            total_energy_cost=total_energy * self.energy_cost_per_kwh,
            soc_start_kwh=self.battery_kwh,
            soc_end_kwh=soc,
            minimum_soc_reached_kwh=min_soc_reached,
            needs_mid_block_charge=needs_mid_charge,
            trips=events,
        )
