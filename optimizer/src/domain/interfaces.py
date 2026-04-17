"""
Interfaces abstratas (Protocols) do OTIMIZ Optimizer.
Define os contratos que todos os algoritmos devem cumprir.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import (
    Block,
    CSPSolution,
    OptimizationResult,
    Trip,
    VehicleType,
    VSPSolution,
)


class IVSPAlgorithm(ABC):
    """Contrato para qualquer algoritmo de Programação de Veículos."""

    @abstractmethod
    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int] = None,
    ) -> VSPSolution:
        """Resolve o VSP e devolve uma solução de blocos."""
        ...


class ICSPAlgorithm(ABC):
    """Contrato para qualquer algoritmo de Programação de Tripulantes."""

    # Parâmetros CCT (defaults seguros — podem ser sobrescritos via Settings)
    MAX_SHIFT_MINUTES: int = 480          # 8 horas
    MAX_DRIVING_MINUTES: int = 240        # 4h
    MIN_BREAK_MINUTES: int = 30

    @abstractmethod
    def solve(
        self,
        blocks: List[Block],
        trips: List[Trip],
    ) -> CSPSolution:
        """Resolve o CSP sobre os blocos vindos do VSP."""
        ...


class IIntegratedSolver(ABC):
    """Contrato para um solver integrado VSP+CSP."""

    @abstractmethod
    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
    ) -> OptimizationResult:
        """Resolve VSP e CSP em conjunto."""
        ...


class ICostEvaluator(ABC):
    """Contrato para o avaliador de custo de uma solução."""

    @abstractmethod
    def vsp_cost(self, solution: VSPSolution, vehicle_types: List[VehicleType]) -> float:
        ...

    @abstractmethod
    def csp_cost(self, solution: CSPSolution) -> float:
        ...

    @abstractmethod
    def total_cost(self, result: OptimizationResult, vehicle_types: List[VehicleType]) -> float:
        ...
