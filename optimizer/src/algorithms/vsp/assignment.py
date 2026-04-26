"""
VSP via Sparse N×N Assignment Problem.

Resolve o Vehicle Scheduling Problem como problema de designação bipartido
sobre matriz N×N esparsa, usando
`scipy.sparse.csgraph.min_weight_full_bipartite_matching`.

ESCALA: 30k-40k viagens em segundos com RAM mínima.

FORMULAÇÃO:
    Matriz N×N onde:
      - Linha i = "evento de saída de trip i" (cauda)
      - Coluna j = "evento de entrada de trip j" (cabeça)
      - Cell (i, j), i ≠ j: cost da conexão trip_i → trip_j (se viável)
      - Cell (i, i) (diagonal): fixed_vehicle_cost (= "trip i fica solo,
        consome um veículo só pra ela")

    O matcher seleciona uma permutação σ. Interpretação:
      σ(i) = i  → trip i é cabeça/cauda de um bloco unitário
      σ(i) = j  → existe uma aresta i→j (j é candidato a sucessor de i)

    Pós-processamento: percorre a permutação respeitando o sentido temporal,
    construindo cadeias time-ordered. Arestas que violam ordem temporal são
    descartadas (vira bloco unitário).

GARANTIA DE FEASIBILIDADE:
    Diagonal (i,i) sempre presente → matching perfeito sempre existe.
    Pior caso = N blocos de 1 trip cada, custo N × fixed_cost.

CUSTO DE MEMÓRIA:
    O(N + N·K) onde K = sucessores viáveis por trip (default cap 64).
    Para N=30k, K=64: ~2M entradas × 24 bytes = ~50 MB.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import numpy as np

try:
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import min_weight_full_bipartite_matching
    _SCIPY_OK = True
except Exception:  # pragma: no cover
    csr_matrix = None
    min_weight_full_bipartite_matching = None
    _SCIPY_OK = False

from ...core.config import get_settings
from ...domain.interfaces import IVSPAlgorithm
from ...domain.models import Block, Trip, VehicleType, VSPSolution
from ..base import BaseAlgorithm

_log = logging.getLogger(__name__)
settings = get_settings()


class AssignmentVSP(BaseAlgorithm, IVSPAlgorithm):
    """
    VSP por Sparse N×N Bipartite Assignment — escala para 30k-40k viagens.
    """

    def __init__(self, vsp_params: Optional[Dict[str, Any]] = None):
        super().__init__(name="assignment_vsp", time_budget_s=120.0)
        self.vsp_params = vsp_params or {}

    def _p(self, key: str, default: Any) -> Any:
        return self.vsp_params.get(key, default)

    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int] = None,
        depots: Optional[List[Dict[str, Any]]] = None,
    ) -> VSPSolution:
        self._start_timer()
        if not trips:
            return VSPSolution(algorithm=self.name)

        if not _SCIPY_OK:
            _log.warning("scipy não disponível, fallback GreedyVSP")
            from .greedy import GreedyVSP
            return GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id=depot_id)

        N = len(trips)
        _log.info(f"AssignmentVSP iniciado para {N} viagens (sparse N×N matching)")

        vehicle = vehicle_types[0] if vehicle_types else None
        fixed_cost = float(self._p(
            "fixed_vehicle_activation_cost",
            vehicle.fixed_cost if vehicle else settings.default_vehicle_fixed_cost,
        ))
        deadhead_cost = float(self._p("deadhead_cost_per_minute", 1.0))
        idle_cost = float(self._p("idle_cost_per_minute", 0.25))
        min_layover = int(self._p("min_layover_minutes", 8))
        max_shift = int(self._p("max_vehicle_shift_minutes", 960))
        allow_multi = bool(self._p("allow_multi_line_block", True))
        connection_tolerance = int(self._p("connection_tolerance_minutes", 0))
        max_successors = int(self._p("assignment_max_successors_per_trip", 64))

        trips_sorted = sorted(trips, key=lambda t: (t.start_time, t.id))
        starts = np.fromiter((t.start_time for t in trips_sorted), dtype=np.int64, count=N)
        ends = np.fromiter((t.end_time for t in trips_sorted), dtype=np.int64, count=N)

        # ─────────────────────────────────────────────────────────────────
        # Constrói (rows, cols, costs) esparsos
        # Diagonal sempre: garante perfect matching.
        # Off-diagonal: arestas de conexão viáveis trip_i → trip_j.
        # ─────────────────────────────────────────────────────────────────
        rows: List[int] = []
        cols: List[int] = []
        costs: List[float] = []

        # Diagonal: bloco unitário custa fixed_cost
        for i in range(N):
            rows.append(i)
            cols.append(i)
            costs.append(fixed_cost)

        t0 = time.perf_counter()
        edge_count = 0
        for i in range(N):
            ti = trips_sorted[i]
            ei = ends[i]
            # Busca binária: primeiro j > i com starts[j] >= ei
            lo, hi = i + 1, N
            while lo < hi:
                mid = (lo + hi) // 2
                if starts[mid] < ei:
                    lo = mid + 1
                else:
                    hi = mid
            j_start = lo

            successors_added = 0
            for j in range(j_start, N):
                gap = int(starts[j] - ei)
                if gap > max_shift:
                    break  # monotonicidade: gaps só crescem

                tj = trips_sorted[j]
                if not allow_multi and ti.line_id != tj.line_id:
                    continue

                dh = max(min_layover, int(ti.deadhead_times.get(tj.origin_id, 0)))
                if gap + connection_tolerance < dh:
                    continue

                idle = max(0, gap - dh)
                cost = (dh * deadhead_cost) + (idle * idle_cost)
                if ti.destination_id == tj.origin_id:
                    cost -= fixed_cost * 0.05
                # Garantir custo positivo estritamente menor que diagonal
                # Caso contrário, matcher prefere diagonal (= solo).
                cost = max(0.001, min(cost, fixed_cost - 0.001))

                rows.append(i)
                cols.append(j)
                costs.append(cost)
                edge_count += 1
                successors_added += 1
                if successors_added >= max_successors:
                    break

        build_ms = (time.perf_counter() - t0) * 1000
        _log.info(
            f"Sparse N×N: {edge_count} conexões + {N} diagonais "
            f"em {build_ms:.0f}ms (mem ~{(N + edge_count) * 24 / 1e6:.1f} MB)"
        )

        cost_matrix = csr_matrix(
            (np.asarray(costs, dtype=np.float64),
             (np.asarray(rows, dtype=np.int32),
              np.asarray(cols, dtype=np.int32))),
            shape=(N, N),
        )

        t1 = time.perf_counter()
        try:
            row_ind, col_ind = min_weight_full_bipartite_matching(cost_matrix)
        except Exception as exc:
            _log.exception("Bipartite matching falhou: %s — fallback Greedy", exc)
            from .greedy import GreedyVSP
            return GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id=depot_id)
        match_ms = (time.perf_counter() - t1) * 1000
        _log.info(f"Bipartite matching resolvido em {match_ms:.0f}ms")

        # ─────────────────────────────────────────────────────────────────
        # Reconstrói cadeias respeitando sentido temporal.
        # σ(i) = j: candidata aresta i→j. Aceita só se j > i (ordem
        # temporal preservada) E i ≠ j.
        # ─────────────────────────────────────────────────────────────────
        sigma: Dict[int, int] = {int(r): int(c) for r, c in zip(row_ind, col_ind)}
        next_trip: Dict[int, int] = {}
        prev_trip: Dict[int, int] = {}
        for i, j in sigma.items():
            if i == j:
                continue
            if j <= i:
                continue  # viola ordem temporal — vira solo
            # Confirma feasibilidade temporal (defensive)
            ti, tj = trips_sorted[i], trips_sorted[j]
            gap = int(tj.start_time - ti.end_time)
            dh = max(min_layover, int(ti.deadhead_times.get(tj.origin_id, 0)))
            if gap + connection_tolerance < dh:
                continue
            # Conflito: j já tem outro predecessor? (não deve acontecer com perfect matching)
            if j in prev_trip:
                continue
            next_trip[i] = j
            prev_trip[j] = i

        # Constrói blocos a partir de "starts" (trips sem predecessor)
        visited = set()
        blocks: List[Block] = []
        bid = 1
        for s in range(N):
            if s in visited or s in prev_trip:
                continue
            chain: List[int] = []
            curr: Optional[int] = s
            block_start = trips_sorted[s].start_time
            while curr is not None and curr not in visited:
                # Respeitar max_shift: cortar cadeia se exceder
                if chain and (trips_sorted[curr].end_time - block_start > max_shift):
                    break
                chain.append(curr)
                visited.add(curr)
                curr = next_trip.get(curr)
            if not chain:
                continue
            chain_trips = [trips_sorted[idx] for idx in chain]
            block = Block(id=bid, trips=chain_trips)
            if vehicle:
                block.vehicle_type_id = vehicle.id
            block.meta.update({
                "activation_cost": fixed_cost,
                "connection_cost": 0.0,
                "deadhead_minutes": 0,
                "idle_minutes": 0,
                "start_depot_id": depot_id,
                "end_depot_id": depot_id,
            })
            for a, b in zip(chain[:-1], chain[1:]):
                ta, tb = trips_sorted[a], trips_sorted[b]
                gap = int(tb.start_time - ta.end_time)
                dh = max(min_layover, int(ta.deadhead_times.get(tb.origin_id, 0)))
                idle = max(0, gap - dh)
                block.meta["deadhead_minutes"] += dh
                block.meta["idle_minutes"] += idle
                block.meta["connection_cost"] += (dh * deadhead_cost) + (idle * idle_cost)
            blocks.append(block)
            bid += 1

        # Trips não visitadas = blocos solo de fallback (por ex. cortes max_shift)
        for i in range(N):
            if i in visited:
                continue
            block = Block(id=bid, trips=[trips_sorted[i]])
            if vehicle:
                block.vehicle_type_id = vehicle.id
            block.meta.update({
                "activation_cost": fixed_cost,
                "connection_cost": 0.0,
                "start_depot_id": depot_id,
                "end_depot_id": depot_id,
            })
            blocks.append(block)
            bid += 1

        # ─────────────────────────────────────────────────────────────────
        # Chain-Merge Pass (greedy, O(B log B) por iteração).
        # Para cada cadeia (em ordem temporal de fim), encontra a próxima
        # cadeia compatível mais barata e funde. Itera até convergir.
        # Esta etapa é mantida em greedy puro (não-scipy) porque nenhuma
        # formulação bipartite esparsa modela a fusão sem dummy denso.
        # ─────────────────────────────────────────────────────────────────
        merge_iters = 0
        merge_total = 0
        merge_ms_total = 0.0
        while True:
            tm0 = time.perf_counter()
            blocks_sorted = sorted(blocks, key=lambda b: b.start_time)
            B = len(blocks_sorted)
            if B < 2:
                break

            # Index: para cada cadeia, lista candidatos (j) compatíveis ordenados por custo
            # Greedy maximal matching: percorre arestas em ordem crescente de custo,
            # aceita se ambos endpoints livres.
            edges: List[tuple[float, int, int]] = []
            for a in range(B):
                ba = blocks_sorted[a]
                last_a = ba.trips[-1]
                ea = last_a.end_time
                cap_added = 0
                for b in range(a + 1, B):
                    bb = blocks_sorted[b]
                    first_b = bb.trips[0]
                    gap = first_b.start_time - ea
                    if gap > max_shift:
                        break
                    if gap < 0:
                        continue
                    if not allow_multi and last_a.line_id != first_b.line_id:
                        continue
                    dh = max(min_layover, int(last_a.deadhead_times.get(first_b.origin_id, 0)))
                    if gap + connection_tolerance < dh:
                        continue
                    combined = bb.trips[-1].end_time - ba.trips[0].start_time
                    if combined > max_shift:
                        continue
                    idle = max(0, gap - dh)
                    cost = (dh * deadhead_cost) + (idle * idle_cost)
                    edges.append((cost, a, b))
                    cap_added += 1
                    if cap_added >= 16:  # cap candidatos por cadeia
                        break

            if not edges:
                merge_ms_total += (time.perf_counter() - tm0) * 1000
                break

            edges.sort(key=lambda e: e[0])
            taken_left: set[int] = set()
            taken_right: set[int] = set()
            new_blocks: List[Block] = []
            mapping: Dict[int, int] = {}  # a → b se aceito
            iter_merges = 0
            for cost, a, b in edges:
                if a in taken_left or b in taken_right:
                    continue
                taken_left.add(a)
                taken_right.add(b)
                mapping[a] = b
                iter_merges += 1

            # Reconstrói cadeias seguindo mapping
            visited_b: set[int] = set()
            new_id = 1
            for a in range(B):
                if a in visited_b or a in taken_right:
                    continue
                chain_blocks: List[Block] = [blocks_sorted[a]]
                visited_b.add(a)
                cursor = mapping.get(a)
                while cursor is not None and cursor not in visited_b:
                    chain_blocks.append(blocks_sorted[cursor])
                    visited_b.add(cursor)
                    cursor = mapping.get(cursor)

                merged_trips: List[Trip] = []
                for cb in chain_blocks:
                    merged_trips.extend(cb.trips)
                merged_block = Block(id=new_id, trips=merged_trips)
                if vehicle:
                    merged_block.vehicle_type_id = vehicle.id
                merged_block.meta.update({
                    "activation_cost": fixed_cost,
                    "connection_cost": 0.0,
                    "deadhead_minutes": 0,
                    "idle_minutes": 0,
                    "start_depot_id": depot_id,
                    "end_depot_id": depot_id,
                })
                for ta, tb in zip(merged_trips[:-1], merged_trips[1:]):
                    g = max(0, int(tb.start_time - ta.end_time))
                    dh_ = max(min_layover, int(ta.deadhead_times.get(tb.origin_id, 0)))
                    idle = max(0, g - dh_)
                    merged_block.meta["deadhead_minutes"] += dh_
                    merged_block.meta["idle_minutes"] += idle
                    merged_block.meta["connection_cost"] += (dh_ * deadhead_cost) + (idle * idle_cost)
                new_blocks.append(merged_block)
                new_id += 1

            # Adiciona blocos que ficaram só como "right" (cabeça consumida)
            for a in range(B):
                if a not in visited_b:
                    blk = blocks_sorted[a]
                    if blk not in new_blocks:
                        # Só inclui se não foi fundido como cauda
                        # (taken_right significa que era cabeça sendo prependida; já incluído acima)
                        pass
            merge_ms_total += (time.perf_counter() - tm0) * 1000
            merge_iters += 1
            merge_total += iter_merges

            if iter_merges == 0:
                break
            blocks = new_blocks
            if merge_iters >= 12:
                break

        total_packed = sum(len(b.trips) for b in blocks)
        _log.info(
            f"AssignmentVSP: {total_packed}/{N} trips em {len(blocks)} blocos "
            f"(build={build_ms:.0f}ms, match={match_ms:.0f}ms, "
            f"merge_iters={merge_iters}, merges={merge_total}, merge_ms={merge_ms_total:.0f})"
        )

        return VSPSolution(
            blocks=blocks,
            unassigned_trips=[],
            algorithm=self.name,
            elapsed_ms=self._elapsed_ms(),
            meta={
                "trip_count": N,
                "sparse_entries": len(rows),
                "build_time_ms": round(build_ms, 1),
                "match_time_ms": round(match_ms, 1),
                "merge_iterations": merge_iters,
                "chain_merges_total": merge_total,
                "merge_time_ms_total": round(merge_ms_total, 1),
                "max_successors_per_trip": max_successors,
                "engine": "scipy.sparse.csgraph.min_weight_full_bipartite_matching",
            },
        )
