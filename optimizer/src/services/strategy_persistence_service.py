"""
strategy_persistence_service.py — Persistência Efêmera (In-Memory) para cenários estratégicos.

SUBSTITUIÇÃO (Cloud-Ready):
Removido o uso de 'filelock' e escrita em disco local.
Utiliza um Singleton em memória para guardar cenários e relatórios durante o tempo de vida do processo.
Em produção, esta persistência deve ser movida para o Banco de Dados (PostgreSQL) via NestJS.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StrategyPersistenceService:
    # Armazenamento compartilhado entre todas as instâncias da classe no mesmo processo
    _storage = {
        "scenarios": {"last_id": 0, "items": []},
        "feeds": {"last_id": 0, "snapshots": []},
        "reports": {"last_id": 0, "items": []},
    }

    def __init__(self, base_dir: Optional[str] = None) -> None:
        # base_dir ignorado pois não usamos mais o disco
        pass

    def save_scenario(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        store = self._storage["scenarios"]
        scenario_id = store["last_id"] + 1
        now_iso = self._utc_now_iso()

        item = {
            "id": scenario_id,
            "created_at": now_iso,
            "updated_at": now_iso,
            **payload,
        }
        store["items"].append(item)
        store["last_id"] = scenario_id
        
        logger.info("[Persistence] Cenário salvo em memória: id=%d", scenario_id)
        return item

    def list_scenarios(self, limit: int = 20) -> List[Dict[str, Any]]:
        items = self._storage["scenarios"]["items"]
        return list(reversed(items[-max(1, limit):]))

    def get_scenario(self, scenario_id: int) -> Optional[Dict[str, Any]]:
        items = self._storage["scenarios"]["items"]
        for item in items:
            if int(item.get("id", 0)) == int(scenario_id):
                return item
        return None

    def get_latest_scenario(self) -> Optional[Dict[str, Any]]:
        items = self._storage["scenarios"]["items"]
        if not items:
            return None
        return items[-1]

    def ingest_feed(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        store = self._storage["feeds"]
        snapshot_id = store["last_id"] + 1

        valid_gps = sum(1 for e in entries if e.get("gps_valid") is True)
        invalid_gps = sum(1 for e in entries if e.get("gps_valid") is False)
        terminal_ok = sum(1 for e in entries if e.get("sent_to_driver_terminal") is True)
        terminal_missing = sum(1 for e in entries if e.get("sent_to_driver_terminal") is False)

        quality = {
            "total_records": len(entries),
            "gps_valid_count": valid_gps,
            "gps_invalid_count": invalid_gps,
            "terminal_ack_count": terminal_ok,
            "terminal_ack_missing_count": terminal_missing,
            "gps_valid_ratio": round(valid_gps / len(entries), 4) if entries else 0.0,
            "terminal_ack_ratio": round(terminal_ok / len(entries), 4) if entries else 0.0,
        }

        snapshot = {
            "id": snapshot_id,
            "created_at": self._utc_now_iso(),
            "quality": quality,
            "records": entries,
        }
        store["snapshots"].append(snapshot)
        store["last_id"] = snapshot_id

        logger.info("[Persistence] Feed Snapshot ingerido: id=%d", snapshot_id)
        return {
            "snapshot_id": snapshot_id,
            "quality": quality,
        }

    def get_latest_feed_records(self) -> List[Dict[str, Any]]:
        snapshots = self._storage["feeds"]["snapshots"]
        if not snapshots:
            return []
        return list(snapshots[-1].get("records", []))

    def get_latest_feed_snapshot(self) -> Optional[Dict[str, Any]]:
        snapshots = self._storage["feeds"]["snapshots"]
        if not snapshots:
            return None
        return dict(snapshots[-1])

    def save_reconciliation_report(self, report: Dict[str, Any]) -> Dict[str, Any]:
        store = self._storage["reports"]
        report_id = store["last_id"] + 1
        now_iso = self._utc_now_iso()

        item = {
            "id": report_id,
            "created_at": now_iso,
            "report": report,
        }
        store["items"].append(item)
        store["last_id"] = report_id

        logger.info("[Persistence] Relatório de reconciliação salvo: id=%d", report_id)
        return item

    def list_reconciliation_reports(self, limit: int = 20) -> List[Dict[str, Any]]:
        items = self._storage["reports"]["items"]
        return list(reversed(items[-max(1, limit):]))

    def prune_data(
        self,
        max_scenarios: int,
        max_feed_snapshots: int,
        max_reports: int,
        max_age_days: int,
    ) -> Dict[str, int]:
        # Implementação básica de retenção em memória
        scenarios = self._storage["scenarios"]["items"]
        snapshots = self._storage["feeds"]["snapshots"]
        reports = self._storage["reports"]["items"]

        old_counts = (len(scenarios), len(snapshots), len(reports))
        
        self._storage["scenarios"]["items"] = self._apply_retention(scenarios, max_scenarios, max_age_days)
        self._storage["feeds"]["snapshots"] = self._apply_retention(snapshots, max_feed_snapshots, max_age_days)
        self._storage["reports"]["items"] = self._apply_retention(reports, max_reports, max_age_days)

        new_counts = (len(self._storage["scenarios"]["items"]), 
                      len(self._storage["feeds"]["snapshots"]), 
                      len(self._storage["reports"]["items"]))

        return {
            "scenarios_removed": old_counts[0] - new_counts[0],
            "feed_snapshots_removed": old_counts[1] - new_counts[1],
            "reports_removed": old_counts[2] - new_counts[2],
        }

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _apply_retention(
        cls,
        items: List[Dict[str, Any]],
        max_items: int,
        max_age_days: int,
    ) -> List[Dict[str, Any]]:
        kept = list(items)

        if max_age_days > 0:
            cutoff = datetime.now(timezone.utc).timestamp() - (max_age_days * 86400)
            kept = [
                item
                for item in kept
                if cls._to_timestamp(item.get("created_at")) >= cutoff
            ]

        if max_items > 0 and len(kept) > max_items:
            kept = kept[-max_items:]

        return kept

    @staticmethod
    def _to_timestamp(value: Any) -> float:
        if not value or not isinstance(value, str):
            return 0.0
        try:
            text = value.strip()
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            return datetime.fromisoformat(text).timestamp()
        except Exception:
            return 0.0
