"""
Classe base para todos os algoritmos com utilidades comuns.
"""

from __future__ import annotations

import itertools
import logging
import time
from typing import Optional

from ..core.config import get_settings
from ..core.exceptions import AlgorithmTimeoutError

logger = logging.getLogger(__name__)
settings = get_settings()

# Contadores globais thread-safe para evitar colisão de IDs entre algoritmos
_global_block_counter = itertools.count(1)
_global_duty_counter = itertools.count(1)


class BaseAlgorithm:
    """
    Mixin com utilidades compartilhadas:
    - controle de tempo / orçamento
    - geração de IDs sequenciais
    - compatibilidade de viagens
    - logging padronizado
    """

    def __init__(self, name: str, time_budget_s: Optional[float] = None):
        self.name = name
        self.time_budget_s = time_budget_s or settings.hybrid_time_budget_seconds
        self._start_time: float = 0.0

    # ── Controle de tempo ─────────────────────────────────────────────────────

    def _start_timer(self) -> None:
        self._start_time = time.perf_counter()

    def _elapsed(self) -> float:
        return time.perf_counter() - self._start_time

    def _elapsed_ms(self) -> float:
        return self._elapsed() * 1000

    def _check_timeout(self) -> bool:
        """Retorna True se o orçamento de tempo foi excedido (não lança, apenas avisa)."""
        if self._elapsed() >= self.time_budget_s:
            logger.warning(
                "time_budget_exceeded",
                extra={"algorithm": self.name, "budget_s": self.time_budget_s},
            )
            return True
        return False

    def _assert_no_timeout(self) -> None:
        """Lança AlgorithmTimeoutError se o orçamento estourou."""
        if self._elapsed() >= self.time_budget_s:
            raise AlgorithmTimeoutError(self.name, self.time_budget_s)

    # ── IDs ───────────────────────────────────────────────────────────────────

    def _next_block_id(self) -> int:
        return next(_global_block_counter)

    def _next_duty_id(self) -> int:
        return next(_global_duty_counter)

    # ── Rescoring via Evaluator (Fase 1: Unificar Objetivo) ───────────────────

    def _rescore_vsp_solution(self, solution, vehicle_types):
        """Rescora solução VSP com evaluator — fonte única de verdade.

        Chamado ao final de cada algoritmo VSP antes de retornar,
        para garantir que total_cost = evaluator.vsp_cost_breakdown().
        """
        try:
            from .evaluator import CostEvaluator
            from ..domain.models import OptimizationResult

            evaluator = CostEvaluator()
            breakdown = evaluator.vsp_cost_breakdown(solution, vehicle_types or [])
            solution.total_cost = float(breakdown.get("total", 0.0))
            solution.meta = solution.meta or {}
            solution.meta["cost_source"] = "evaluator_vsp"
            return solution
        except Exception as e:
            logger.warning(f"Falha ao rescore VSP: {e}. Mantendo total_cost original.")
            return solution

    def _rescore_csp_solution(self, solution, vehicle_types=None):
        """Rescora solução CSP com evaluator — fonte única de verdade.

        Chamado ao final de cada algoritmo CSP antes de retornar,
        para garantir que total_cost = evaluator.csp_cost_breakdown().
        """
        try:
            from .evaluator import CostEvaluator

            evaluator = CostEvaluator()
            breakdown = evaluator.csp_cost_breakdown(solution)
            solution.total_cost = float(breakdown.get("total", 0.0))
            solution.meta = solution.meta or {}
            solution.meta["cost_source"] = "evaluator_csp"
            return solution
        except Exception as e:
            logger.warning(f"Falha ao rescore CSP: {e}. Mantendo total_cost original.")
            return solution

    def _rescore_optimization_result(self, result, vehicle_types):
        """Rescora OptimizationResult completo (VSP + CSP) com evaluator.

        Usado por solucionadores integrados (VCSP) que retornam OptimizationResult.
        """
        try:
            from .evaluator import CostEvaluator

            evaluator = CostEvaluator()
            total_cost = evaluator.total_cost(result, vehicle_types or [])
            result.total_cost = total_cost
            result.meta = result.meta or {}
            result.meta["cost_source"] = "evaluator_integrated"
            return result
        except Exception as e:
            logger.warning(f"Falha ao rescore OptimizationResult: {e}. Mantendo total_cost original.")
            return result
