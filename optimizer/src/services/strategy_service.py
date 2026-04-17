"""
Serviços estratégicos (Macro LP, What-if e Feedback planejado vs realizado).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from ..algorithms.evaluator import CostEvaluator
from ..domain.models import Trip, VehicleType

try:
    import pulp  # type: ignore

    _PULP_AVAILABLE = True
except Exception:  # pragma: no cover
    _PULP_AVAILABLE = False


@dataclass
class MacroEstimate:
    estimated_vehicles: int
    estimated_crew: int
    estimated_total_cost: float
    estimated_vehicle_cost: float
    estimated_crew_cost: float
    notes: List[str]
    assumptions: Dict[str, Any]


class StrategyService:
    def __init__(self) -> None:
        self.evaluator = CostEvaluator()

    def macro_estimate(
        self,
        trips: Sequence[Trip],
        cct_params: Dict[str, Any] | None = None,
        vsp_params: Dict[str, Any] | None = None,
        optimization_params: Any | None = None,
    ) -> MacroEstimate:
        cct = dict(cct_params or {})
        vsp = dict(vsp_params or {})

        if not trips:
            return MacroEstimate(
                estimated_vehicles=0,
                estimated_crew=0,
                estimated_total_cost=0.0,
                estimated_vehicle_cost=0.0,
                estimated_crew_cost=0.0,
                notes=["Nenhuma viagem recebida para estimativa macro."],
                assumptions={"lp_used": _PULP_AVAILABLE},
            )

        total_service_minutes = sum(max(0, trip.end_time - trip.start_time) for trip in trips)
        operating_span = max(trip.end_time for trip in trips) - min(trip.start_time for trip in trips)

        max_shift = int(cct.get("max_shift_minutes", 480) or 480)
        max_work = int(cct.get("max_work_minutes", 440) or 440)
        max_vehicle_shift = int(vsp.get("max_vehicle_shift_minutes", 960) or 960)
        max_vehicles = int(vsp.get("max_vehicles", vsp.get("maxVehicles", 0)) or 0)

        # Pesos de custo dinâmicos
        cost_vehicle = 1000.0
        cost_km = 1.0
        cost_duty = 500.0
        if optimization_params:
            if hasattr(optimization_params, "cost_vehicle"):
                # Se for objeto (pydantic)
                cost_vehicle = optimization_params.cost_vehicle
                cost_km = optimization_params.cost_km
                cost_duty = optimization_params.cost_duty
            elif isinstance(optimization_params, dict):
                # Se for dicionário
                cost_vehicle = optimization_params.get("cost_vehicle", 1000.0)
                cost_km = optimization_params.get("cost_km", 1.0)
                cost_duty = optimization_params.get("cost_duty", 500.0)

        if _PULP_AVAILABLE:
            estimate = self._lp_estimate(
                total_service_minutes=total_service_minutes,
                operating_span=operating_span,
                max_shift=max_shift,
                max_work=max_work,
                max_vehicle_shift=max_vehicle_shift,
                max_vehicles=max_vehicles,
                cost_vehicle=cost_vehicle,
                cost_duty=cost_duty,
            )
        else:
            estimate = self._heuristic_estimate(
                total_service_minutes=total_service_minutes,
                operating_span=operating_span,
                max_shift=max_shift,
                max_work=max_work,
                max_vehicle_shift=max_vehicle_shift,
                max_vehicles=max_vehicles,
                cost_vehicle=cost_vehicle,
                cost_duty=cost_duty,
            )

        return estimate

    def what_if(
        self,
        trips: Sequence[Trip],
        scenarios: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for scenario in scenarios:
            name = str(scenario.get("name") or "scenario")
            cct = scenario.get("cct_params") or {}
            vsp = scenario.get("vsp_params") or {}
            opt = scenario.get("optimization_params") or {}
            estimate = self.macro_estimate(trips, cct, vsp, opt)
            results.append(
                {
                    "name": name,
                    "estimated_vehicles": estimate.estimated_vehicles,
                    "estimated_crew": estimate.estimated_crew,
                    "estimated_total_cost": estimate.estimated_total_cost,
                    "estimated_vehicle_cost": estimate.estimated_vehicle_cost,
                    "estimated_crew_cost": estimate.estimated_crew_cost,
                    "assumptions": estimate.assumptions,
                }
            )
        return results

    def plan_vs_real(
        self,
        planned_trips: Sequence[Trip],
        actual_trips: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        planned_by_id = {trip.id: trip for trip in planned_trips}
        actual_by_id = {int(item.get("trip_id")): item for item in actual_trips if item.get("trip_id") is not None}

        delays: List[int] = []
        ghost_bus = 0
        missing_actual = 0
        gps_invalid = 0

        for trip_id, planned in planned_by_id.items():
            actual = actual_by_id.get(trip_id)
            if actual is None:
                missing_actual += 1
                continue
            if actual.get("sent_to_driver_terminal") is False:
                ghost_bus += 1
            if actual.get("gps_valid") is False:
                gps_invalid += 1
            if actual.get("actual_start_time") is not None:
                delays.append(int(actual["actual_start_time"]) - planned.start_time)

        compared = len(delays)
        avg_delay = round(sum(delays) / compared, 2) if compared else 0.0
        p95_delay = 0.0
        if delays:
            ordered = sorted(delays)
            index = max(0, min(len(ordered) - 1, int(0.95 * (len(ordered) - 1))))
            p95_delay = float(ordered[index])

        alerts: List[str] = []
        recommendations: List[str] = []

        if ghost_bus > 0:
            alerts.append(f"GHOST_BUS_DETECTED count={ghost_bus}")
            recommendations.append("Integrar feed AVL/GTFS-RT contínuo e bloquear alocação sem confirmação de terminal.")
        if gps_invalid > 0:
            alerts.append(f"GPS_INVALID count={gps_invalid}")
            recommendations.append("Aplicar validação de telemetria por veículo e fallback de posicionamento por terminal.")
        if p95_delay > 10:
            alerts.append(f"HIGH_P95_DELAY minutes={p95_delay}")
            recommendations.append("Recalibrar tempos planejados por faixa horária e corredor com histórico de atraso.")

        kpis = {
            "planned_trips": len(planned_trips),
            "actual_trips": len(actual_by_id),
            "missing_actual": missing_actual,
            "ghost_bus_count": ghost_bus,
            "gps_invalid_count": gps_invalid,
            "avg_start_delay_minutes": avg_delay,
            "p95_start_delay_minutes": p95_delay,
        }

        return {
            "kpis": kpis,
            "alerts": alerts,
            "recommendations": recommendations,
        }

    def _lp_estimate(
        self,
        total_service_minutes: int,
        operating_span: int,
        max_shift: int,
        max_work: int,
        max_vehicle_shift: int,
        max_vehicles: int,
        cost_vehicle: float = 800.0,
        cost_duty: float = 500.0,
    ) -> MacroEstimate:
        problem = pulp.LpProblem("macro_estimate", pulp.LpMinimize)
        vehicles = pulp.LpVariable("vehicles", lowBound=1, cat="Integer")
        crew = pulp.LpVariable("crew", lowBound=1, cat="Integer")

        # Custo por hora da tripulação derivado do cost_duty (jornada de 8h/480min como base)
        # Se cost_duty=500, crew_hour_cost = 500 / 8 = 62.5
        crew_hour_cost = cost_duty / 8.0

        problem += cost_vehicle * vehicles + crew_hour_cost * (total_service_minutes / 60.0)
        problem += vehicles * max_vehicle_shift >= total_service_minutes
        problem += crew * max_work >= total_service_minutes
        problem += crew * max_shift >= operating_span
        if max_vehicles > 0:
            problem += vehicles <= max_vehicles

        problem.solve(pulp.PULP_CBC_CMD(timeLimit=2, msg=False))

        est_vehicles = int(round(float(pulp.value(vehicles) or 1)))
        est_crew = int(round(float(pulp.value(crew) or 1)))

        vehicle_cost = est_vehicles * cost_vehicle
        crew_cost = (total_service_minutes / 60.0) * crew_hour_cost
        total_cost = round(vehicle_cost + crew_cost, 2)

        notes = ["Estimativa Macro com relaxamento LP para suporte à decisão."]
        if max_vehicles > 0:
            notes.append(f"Limite de frota aplicado: max_vehicles={max_vehicles}.")

        return MacroEstimate(
            estimated_vehicles=est_vehicles,
            estimated_crew=est_crew,
            estimated_total_cost=total_cost,
            estimated_vehicle_cost=round(vehicle_cost, 2),
            estimated_crew_cost=round(crew_cost, 2),
            notes=notes,
            assumptions={
                "lp_used": True,
                "max_shift_minutes": max_shift,
                "max_work_minutes": max_work,
                "max_vehicle_shift_minutes": max_vehicle_shift,
            },
        )

    def _heuristic_estimate(
        self,
        total_service_minutes: int,
        operating_span: int,
        max_shift: int,
        max_work: int,
        max_vehicle_shift: int,
        max_vehicles: int,
        cost_vehicle: float = 800.0,
        cost_duty: float = 500.0,
    ) -> MacroEstimate:
        from math import ceil

        est_vehicles = max(1, ceil(total_service_minutes / max(1, max_vehicle_shift)))
        est_crew = max(1, ceil(total_service_minutes / max(1, max_work)), ceil(operating_span / max(1, max_shift)))
        if max_vehicles > 0:
            est_vehicles = min(est_vehicles, max_vehicles)

        crew_hour_cost = cost_duty / 8.0
        vehicle_cost = est_vehicles * cost_vehicle
        crew_cost = (total_service_minutes / 60.0) * crew_hour_cost

        return MacroEstimate(
            estimated_vehicles=est_vehicles,
            estimated_crew=est_crew,
            estimated_total_cost=round(vehicle_cost + crew_cost, 2),
            estimated_vehicle_cost=round(vehicle_cost, 2),
            estimated_crew_cost=round(crew_cost, 2),
            notes=["Estimativa Macro heurística (PuLP indisponível)."],
            assumptions={
                "lp_used": False,
                "max_shift_minutes": max_shift,
                "max_work_minutes": max_work,
                "max_vehicle_shift_minutes": max_vehicle_shift,
            },
        )
