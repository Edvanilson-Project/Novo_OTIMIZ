"""
Joint VSP+CSP via Branch-and-Price com CCT constraints no pricing.

Diferença vs JointSolver:
  JointSolver: VSP (tabu/greedy) → CSP, com retry se violações CCT.
  JointBP: B&P com driving_continuous como recurso duro no pricing →
           blocos já CCT-viáveis produzidos pelo solver →
           CSP mais simples com menos violações a corrigir.

Parâmetros:
  cct_params: extraídos para configurar max_driving_minutes no pricing B&P.
  vsp_params: repassados ao BranchAndPrice (inclui EV params se aplicável).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ...domain.interfaces import IIntegratedSolver
from ...domain.models import OptimizationResult, Trip, VehicleType
from ..base import BaseAlgorithm
from ..csp.greedy import GreedyCSP
from ..vsp.branch_and_price import BranchAndPrice

_log = logging.getLogger(__name__)

_CLT_MAX_DRIVING_MINUTES = 330   # art. 71 §1º CLT: 5h30 de condução contínua
_CLT_MIN_BREAK_MINUTES = 30      # pausa mínima para reset


class JointBP(BaseAlgorithm, IIntegratedSolver):
    """Joint VSP+CSP: B&P CCT-constrained para VSP, GreedyCSP para CSP.

    O pricing SPPRC rejeita extensões que ultrapassem max_driving_minutes
    sem uma pausa de min_break_minutes — os blocos entregues ao CSP já
    satisfazem a restrição de condução contínua CLT/CCT.
    """

    def __init__(
        self,
        time_budget_s: float = 120.0,
        cct_params: Optional[Dict[str, Any]] = None,
        vsp_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(name="joint_bp", time_budget_s=float(time_budget_s))
        self.cct_params: Dict[str, Any] = dict(cct_params or {})
        self.vsp_params: Dict[str, Any] = dict(vsp_params or {})

    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int] = None,
    ) -> OptimizationResult:
        self._start_timer()
        if not trips:
            return OptimizationResult(vsp=None, csp=None)

        # Extrair limites CLT do cct_params e injetar no B&P via vsp_params
        # Usa "max_driving_minutes" (mesma chave que GreedyCSP/CctParamsInput)
        max_driving = int(
            self.cct_params.get("max_driving_minutes", _CLT_MAX_DRIVING_MINUTES)
        )
        min_break = int(
            self.cct_params.get("min_break_minutes", _CLT_MIN_BREAK_MINUTES)
        )

        bp_vsp_params = {
            **self.vsp_params,
            "bp_max_driving_minutes": max_driving,
            "bp_min_break_minutes": min_break,
        }

        # 70% do orçamento para VSP (B&P), 30% para CSP
        vsp_budget = max(5.0, self.time_budget_s * 0.70)
        csp_budget = max(2.0, self.time_budget_s * 0.30)

        bp = BranchAndPrice(vsp_params=bp_vsp_params)
        bp.time_budget_s = vsp_budget
        vsp_sol = bp.solve(trips, vehicle_types, depot_id)

        if not vsp_sol.blocks:
            _log.warning("JointBP: B&P não produziu blocos — retornando sem CSP")
            return OptimizationResult(vsp=vsp_sol, csp=None)

        csp = GreedyCSP(vsp_params=self.vsp_params, **self.cct_params)
        csp.time_budget_s = csp_budget
        csp_sol = csp.solve(vsp_sol.blocks, trips)

        result = OptimizationResult(vsp=vsp_sol, csp=csp_sol)
        result.meta = {
            "joint_bp": {
                "cct_max_driving_minutes": max_driving,
                "cct_min_break_minutes": min_break,
                "vsp_blocks": len(vsp_sol.blocks),
                "csp_duties": len(csp_sol.duties) if csp_sol else 0,
                "bp_meta": (vsp_sol.meta or {}).get("branch_and_price", {}),
            }
        }
        return result
