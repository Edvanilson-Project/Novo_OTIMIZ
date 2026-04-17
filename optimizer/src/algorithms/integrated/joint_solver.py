"""
Solver Integrado VSP+CSP.

Estratégia de iteração:
  1. Resolve VSP com o algoritmo configurado.
  2. Resolve CSP sobre os blocos resultantes.
  3. Usa o custo total como sinal de feedback:
     se violações CCT > 0, relança o VSP pedindo blocos menores
     (prefere blocos curtos que facilitem deveres viáveis).
  4. Repete até orçamento de tempo ou 0 violações.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ...core.config import get_settings
from ...core.exceptions import InfeasibleProblemError
from ...domain.interfaces import IIntegratedSolver
from ...domain.models import OptimizationResult, Trip, VehicleType
from ..csp.greedy import GreedyCSP
from ..csp.set_partitioning import SetPartitioningCSP
from ..vsp.greedy import GreedyVSP
from ..vsp.simulated_annealing import SimulatedAnnealingVSP
from ..vsp.tabu_search import TabuSearchVSP
from ..base import BaseAlgorithm
from ..evaluator import CostEvaluator

settings = get_settings()
logger = logging.getLogger(__name__)
evaluator = CostEvaluator()


class JointSolver(BaseAlgorithm, IIntegratedSolver):
    """
    Solver VSP+CSP com loop de feedback iterativo.
    """

    def __init__(
        self,
        time_budget_s: Optional[float] = None,
        vsp_algorithm: str = "tabu",
        csp_algorithm: str = "set_partitioning",
        max_rounds: int = 3,
        cct_params: Optional[Dict[str, Any]] = None,
        vsp_params: Optional[Dict[str, Any]] = None,
    ):
        merged_vsp_params = dict(vsp_params or {})
        requested_budget = time_budget_s
        if requested_budget is None:
            raw_budget = merged_vsp_params.get("time_budget_s", settings.hybrid_time_budget_seconds)
            try:
                requested_budget = float(raw_budget)
            except (TypeError, ValueError):
                requested_budget = float(settings.hybrid_time_budget_seconds)
        super().__init__(name="joint_solver", time_budget_s=requested_budget)
        self.vsp_algorithm = vsp_algorithm
        self.csp_algorithm = csp_algorithm
        self.max_rounds = max_rounds
        self.cct_params = dict(cct_params or {})
        self.vsp_params = merged_vsp_params

    def _remaining_budget_s(self) -> float:
        return max(0.0, float(self.time_budget_s) - self._elapsed())

    def _configure_solver_budget(self, solver: Any, budget_s: float) -> float:
        applied_budget = max(1.0, min(float(budget_s), self._remaining_budget_s()))
        solver.time_budget_s = applied_budget
        greedy = getattr(solver, "greedy", None)
        if greedy is not None:
            greedy.time_budget_s = applied_budget
        return applied_budget

    # ── Seleção de algoritmos por nome ────────────────────────────────────────

    def _vsp_solver(self):
        mapping = {
            "greedy": lambda: GreedyVSP(vsp_params=self.vsp_params),
            "sa": lambda: SimulatedAnnealingVSP(vsp_params=self.vsp_params),
            "tabu": lambda: TabuSearchVSP(vsp_params=self.vsp_params),
        }
        factory = mapping.get(self.vsp_algorithm, TabuSearchVSP)
        return factory() if callable(factory) else factory()

    def _csp_solver(self):
        if self.csp_algorithm == "ilp":
            return SetPartitioningCSP(vsp_params=self.vsp_params, **self.cct_params)
        return GreedyCSP(vsp_params=self.vsp_params, **self.cct_params)

    # ── Solver principal ───────────────────────────────────────────────────────

    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int] = None,
    ) -> OptimizationResult:
        self._start_timer()
        if not trips:
            raise InfeasibleProblemError("No trips provided")

        best_result: Optional[OptimizationResult] = None

        for round_n in range(self.max_rounds):
            if self._check_timeout():
                break

            rounds_left = max(1, self.max_rounds - round_n)
            round_budget = max(1.0, self._remaining_budget_s() / rounds_left)
            vsp_budget = max(1.0, round_budget * 0.45)
            csp_budget = max(1.0, round_budget * 0.45)

            logger.info("joint_solver round=%d/%d", round_n + 1, self.max_rounds)

            # 1) VSP
            vsp_solver = self._vsp_solver()
            self._configure_solver_budget(vsp_solver, vsp_budget)
            vsp_sol = vsp_solver.solve(trips, vehicle_types, depot_id)

            if not vsp_sol.blocks:
                continue

            # 2) CSP
            csp_solver = self._csp_solver()
            self._configure_solver_budget(csp_solver, csp_budget)
            csp_sol = csp_solver.solve(vsp_sol.blocks, trips)

            # 3) Custo total
            result = OptimizationResult(
                vsp=vsp_sol,
                csp=csp_sol,
                algorithm=self.name,  # type: ignore[arg-type]
                total_elapsed_ms=self._elapsed_ms(),
            )
            result.total_cost = evaluator.total_cost(result, vehicle_types)

            if best_result is None or result.total_cost < best_result.total_cost:
                best_result = result

            # Se sem violações, para cedo
            if csp_sol.cct_violations == 0 and not vsp_sol.unassigned_trips:
                break

        if best_result is None:
            raise InfeasibleProblemError("JointSolver could not find any feasible solution")

        best_result.total_elapsed_ms = self._elapsed_ms()
        return best_result
