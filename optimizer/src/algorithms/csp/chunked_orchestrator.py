"""

Chunked CSP Orchestrator — Decomposição Geográfica + Temporal.

Resolve o problema de Set Partitioning para mega-instâncias (30k-40k viagens)
quebrando-as em sub-problemas isolados (clusters) que cabem na RAM, e depois
faz o STITCH (merge) das escalas resultantes.

Critérios de chunking (em ordem de prioridade):
    1. Por depot/terminal (clusters geográficos disjuntos)
    2. Por janela temporal de 4h (clusters temporais disjuntos)

Cada chunk é resolvido pelo SetPartitioningOptimizedCSP isoladamente.
O merge final renumera duties e propaga métricas.

GARANTIAS:
    - Cada bloco aparece em exatamente UM chunk (partição estrita)
    - Restrições duras (CLT) são respeitadas dentro de cada chunk
    - Boundary stitching é feito por joint_opt_boundary (não aqui)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from ...domain.interfaces import ICSPAlgorithm
from ...domain.models import Block, CSPSolution, Duty, Trip
from ..base import BaseAlgorithm

_log = logging.getLogger(__name__)


class ChunkedCSPOrchestrator(BaseAlgorithm, ICSPAlgorithm):
    """
    Orquestra Set Partitioning em chunks geográficos+temporais.

    Quando len(blocks) <= chunk_threshold, delega direto ao base_solver.
    Caso contrário, particiona, resolve cada chunk em sequência (ou paralelo
    quando max_workers > 1), e faz o merge das duties.
    """

    def __init__(
        self,
        base_solver: Optional[ICSPAlgorithm] = None,
        vsp_params: Optional[Dict[str, Any]] = None,
        chunk_threshold: int = 1500,
        temporal_window_minutes: int = 240,
        chunk_by_depot: bool = True,
        max_workers: int = 1,
        **params: Any,
    ):
        super().__init__(name="chunked_csp_orchestrator", time_budget_s=600.0)
        self.vsp_params = vsp_params or {}
        self.params = params
        self.chunk_threshold = chunk_threshold
        self.temporal_window_minutes = temporal_window_minutes
        self.chunk_by_depot = chunk_by_depot
        self.max_workers = max(1, int(max_workers))
        self._base_solver_factory = base_solver

    def _make_solver(self) -> ICSPAlgorithm:
        # BUG-CHUNK-02 fix: solver reutilizado com estado mutável entre chunks.
        # Se é classe (type), instanciar nova a cada chunk. Se é instância, deepcopy.
        if self._base_solver_factory is not None:
            if isinstance(self._base_solver_factory, type):
                return self._base_solver_factory(vsp_params=self.vsp_params, **self.params)
            import copy
            return copy.deepcopy(self._base_solver_factory)
        # Lazy import para evitar circular dep
        from .set_partitioning_optimized import SetPartitioningOptimizedCSP

        return SetPartitioningOptimizedCSP(vsp_params=self.vsp_params, **self.params)

    def solve(
        self,
        blocks: List[Block],
        trips: Optional[List[Trip]] = None,
    ) -> CSPSolution:
        self._start_timer()
        if not blocks:
            return CSPSolution(algorithm=self.name, meta={"roster_count": 0})

        n_blocks = len(blocks)
        _log.info(f"ChunkedCSP iniciado: {n_blocks} blocos (threshold={self.chunk_threshold})")

        if n_blocks <= self.chunk_threshold:
            _log.info("Abaixo do threshold — execução direta sem chunking")
            solver = self._make_solver()
            return solver.solve(blocks, trips)

        chunks = self._partition(blocks)
        _log.info(f"ChunkedCSP: {len(chunks)} chunks gerados")

        chunk_solutions: List[CSPSolution] = []
        chunk_meta: List[Dict[str, Any]] = []
        t0 = time.perf_counter()

        for idx, chunk_blocks in enumerate(chunks):
            if not chunk_blocks:
                continue
            chunk_trip_ids = {t.id for b in chunk_blocks for t in b.trips}
            chunk_trips = [t for t in trips if t.id in chunk_trip_ids] if trips else None
            ts = time.perf_counter()
            solver = self._make_solver()
            try:
                sol = solver.solve(chunk_blocks, chunk_trips)
            except Exception as exc:
                _log.exception("Chunk %d falhou: %s — marcando blocos como descobertos", idx, exc)
                sol = CSPSolution(
                    uncovered_blocks=list(chunk_blocks),
                    cct_violations=len(chunk_blocks),
                    algorithm=self.name,
                    warnings=[f"chunk_{idx}_failed: {exc}"],
                    meta={
                        "chunk_failed": True,
                        "chunk_idx": idx,
                        "failed_blocks": len(chunk_blocks),
                    },
                )
            elapsed = (time.perf_counter() - ts) * 1000
            chunk_solutions.append(sol)
            chunk_meta.append(
                {
                    "chunk_idx": idx,
                    "blocks": len(chunk_blocks),
                    "duties": len(sol.duties),
                    "uncovered_blocks": len(sol.uncovered_blocks or []),
                    "failed": bool((sol.meta or {}).get("chunk_failed")),
                    "elapsed_ms": round(elapsed, 1),
                    "violations": sol.cct_violations,
                }
            )
            _log.info(f"  chunk[{idx}]: {len(chunk_blocks)} blocks → " f"{len(sol.duties)} duties em {elapsed:.0f}ms")

        merged = self._merge(chunk_solutions, chunk_meta)
        merged.elapsed_ms = self._elapsed_ms()
        merged.algorithm = self.name
        merged.meta = {
            **(merged.meta or {}),
            "chunked": True,
            "chunk_count": len(chunks),
            "chunk_threshold": self.chunk_threshold,
            "temporal_window_minutes": self.temporal_window_minutes,
            "chunk_by_depot": self.chunk_by_depot,
            "chunks": chunk_meta,
            "total_chunk_solve_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
        _log.info(f"ChunkedCSP concluído: {len(merged.duties)} duties totais, " f"{merged.cct_violations} violações")
        return merged

    def _partition(self, blocks: List[Block]) -> List[List[Block]]:
        """
        Particiona blocks em chunks disjuntos, primeiro por depot, depois por
        janela temporal. Cada bloco aparece em UM chunk apenas.
        """
        # Etapa 1: agrupar por depot (chave = primeiro depot da primeira trip)
        if self.chunk_by_depot:
            by_depot: Dict[Any, List[Block]] = defaultdict(list)
            for b in blocks:
                key = self._depot_key(b)
                by_depot[key].append(b)
            depot_groups = list(by_depot.values())
        else:
            depot_groups = [list(blocks)]

        # Etapa 2: dentro de cada depot, sub-particionar por janela temporal
        chunks: List[List[Block]] = []
        win = max(60, int(self.temporal_window_minutes))
        for grp in depot_groups:
            if len(grp) <= self.chunk_threshold:
                chunks.append(grp)
                continue
            # Ordena por start_time, agrupa em janelas de `win` minutos
            grp_sorted = sorted(grp, key=lambda b: b.start_time)
            current: List[Block] = []
            window_start = grp_sorted[0].start_time
            for b in grp_sorted:
                if b.start_time - window_start > win or len(current) >= self.chunk_threshold:
                    if current:
                        chunks.append(current)
                    current = [b]
                    window_start = b.start_time
                else:
                    current.append(b)
            if current:
                chunks.append(current)
        return chunks

    @staticmethod
    def _depot_key(block: Block) -> Any:
        if not block.trips:
            return ("none", None)
        first = block.trips[0]
        return ("depot", first.depot_id) if first.depot_id is not None else ("origin", first.origin_id)

    @staticmethod
    def _merge(
        solutions: List[CSPSolution],
        chunk_meta: List[Dict[str, Any]],
    ) -> CSPSolution:
        """Funde duties de múltiplos chunks com renumeração coerente."""
        if not solutions:
            return CSPSolution(meta={"roster_count": 0})

        merged_duties: List[Duty] = []
        merged_uncovered: List[Block] = []
        next_id = 1
        total_violations = 0
        total_cost = 0.0
        warnings: List[str] = []

        for sol in solutions:
            for d in sol.duties:
                d.id = next_id
                next_id += 1
                merged_duties.append(d)
            merged_uncovered.extend(sol.uncovered_blocks or [])
            total_violations += sol.cct_violations
            total_cost += sol.total_cost
            warnings.extend(sol.warnings or [])

        return CSPSolution(
            duties=merged_duties,
            total_cost=total_cost,
            uncovered_blocks=merged_uncovered,
            cct_violations=total_violations,
            warnings=warnings,
            meta={"roster_count": len(merged_duties)},
        )
