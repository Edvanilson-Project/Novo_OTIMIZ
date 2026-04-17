"""Estado em memória do worker estratégico (polling/reconciliação/cleanup)."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict


class StrategyWorkerState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {
            "status": "idle",
            "started_at": None,
            "last_poll_at": None,
            "last_ingest_at": None,
            "last_ingest_file": None,
            "last_ingest_records": 0,
            "last_reconcile_at": None,
            "last_reconcile_scenario_id": None,
            "last_reconcile_snapshot_id": None,
            "last_cleanup_at": None,
            "last_cleanup_stats": {},
            "last_error": None,
        }

    def update(self, **kwargs: Any) -> None:
        with self._lock:
            self._state.update(kwargs)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    @staticmethod
    def utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()


worker_state = StrategyWorkerState()
