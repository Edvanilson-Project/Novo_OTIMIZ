"""
evaluator.py — Cálculo de custos com precisão decimal.
"""

from decimal import Decimal, ROUND_HALF_UP
import math
from typing import Any, Dict, List

from ..domain.models import CSPSolution, OptimizationResult, VehicleType, VSPSolution
from .interfaces import ICostEvaluator


class CostEvaluator(ICostEvaluator):
    """Calcula o custo total de uma solução com precisão decimal."""

    def __init__(self):
        self.crew_cost_per_hour = 25.0  # Exemplo: R$ 25,00 por hora
        self.vehicle_cost_per_km = 2.5  # Exemplo: R$ 2,50 por km
        self._decimal_context = Decimal("0.00")

    def _to_decimal(self, value: float) -> Decimal:
        """Converte float para Decimal de forma segura."""
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value)).quantize(self._decimal_context, rounding=ROUND_HALF_UP)

    def csp_cost_breakdown(self, solution: CSPSolution) -> Dict[str, Any]:
        """Cálculo com precisão decimal para custos de tripulação."""
        total = Decimal("0")
        breakdown = {"base": Decimal("0"), "overtime": Decimal("0"), "penalties": Decimal("0")}

        for duty in solution.duties:
            # Custo base por hora (com precisão decimal)
            hours = self._to_decimal(duty.duration_minutes) / Decimal("60")
            base_cost = hours * self._to_decimal(self.crew_cost_per_hour)
            breakdown["base"] += base_cost

            # Horas extras (se aplicável)
            if hasattr(duty, "overtime_minutes") and duty.overtime_minutes > 0:
                overtime_hours = self._to_decimal(duty.overtime_minutes) / Decimal("60")
                overtime_cost = overtime_hours * self._to_decimal(self.crew_cost_per_hour) * Decimal("1.5")
                breakdown["overtime"] += overtime_cost

            # Penalidades por violações CCT
            if duty.meta.get("illegal_relief", False):
                penalty = Decimal("1000.00")  # Penalidade fixa por violação
                breakdown["penalties"] += penalty

        total = breakdown["base"] + breakdown["overtime"] + breakdown["penalties"]

        return {"total": float(total), "breakdown": {k: float(v) for k, v in breakdown.items()}, "currency": "BRL"}

    def vsp_cost_breakdown(self, solution: VSPSolution, vehicle_types: List[VehicleType]) -> Dict[str, Any]:
        """Cálculo com precisão decimal para custos de frota."""
        total = Decimal("0")
        breakdown = {"fixed": Decimal("0"), "distance": Decimal("0"), "time": Decimal("0")}

        for block in solution.blocks:
            # Custo fixo por veículo
            breakdown["fixed"] += Decimal("800.00")  # Custo fixo exemplo

            # Custo por distância e tempo
            for trip in block.trips:
                if hasattr(trip, "distance_km"):
                    breakdown["distance"] += self._to_decimal(trip.distance_km) * self._to_decimal(
                        self.vehicle_cost_per_km
                    )

                # Custo por tempo de operação
                time_hours = self._to_decimal(trip.duration) / Decimal("60")
                breakdown["time"] += time_hours * Decimal("15.00")  # Custo por hora exemplo

        total = breakdown["fixed"] + breakdown["distance"] + breakdown["time"]

        return {"total": float(total), "breakdown": {k: float(v) for k, v in breakdown.items()}, "currency": "BRL"}

    def total_cost_breakdown(
        self,
        result: OptimizationResult,
        vehicle_types: List[VehicleType],
    ) -> Dict[str, Any]:
        """Cálculo total com precisão decimal."""
        csp_cost = self.csp_cost_breakdown(result.csp)
        vsp_cost = self.vsp_cost_breakdown(result.vsp, vehicle_types)

        total_decimal = self._to_decimal(csp_cost["total"]) + self._to_decimal(vsp_cost["total"])

        return {"total": float(total_decimal), "csp": csp_cost, "vsp": vsp_cost, "currency": "BRL"}

    def _validate_cost_consistency(self, internal_cost: float, api_cost: float) -> bool:
        """Valida se os custos internos e da API são consistentes."""
        # Tolerância de 0.01% ou R$ 1.00, o que for maior
        tolerance = max(internal_cost * 0.0001, 1.0)
        return math.isclose(internal_cost, api_cost, rel_tol=0.0001, abs_tol=tolerance)

    def infeasibility_penalty(self, solution: VSPSolution) -> float:
        """Penalidade por inviabilidade - mantido como float para compatibilidade."""
        penalty = Decimal("0")
        for trip in solution.unassigned_trips:
            penalty += Decimal("10000.00")  # Penalidade alta por viagem não atribuída
        return float(penalty)
