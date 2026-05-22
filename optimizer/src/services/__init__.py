from __future__ import annotations

from typing import Any

from .strategy_worker_state import worker_state

__all__ = ["OptimizerService", "StrategyService", "StrategyPersistenceService", "worker_state"]


def __getattr__(name: str) -> Any:
    if name == "OptimizerService":
        from .optimizer_service import OptimizerService

        return OptimizerService
    if name == "StrategyService":
        from .strategy_service import StrategyService

        return StrategyService
    if name == "StrategyPersistenceService":
        from .strategy_persistence_service import StrategyPersistenceService

        return StrategyPersistenceService
    raise AttributeError(name)
