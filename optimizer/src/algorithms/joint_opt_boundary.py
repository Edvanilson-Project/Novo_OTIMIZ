"""
Boundary-focused ALNS para mega-escalas.

Quando o ChunkedCSPOrchestrator divide a instância em sub-problemas, cria
"emendas" (boundaries) artificiais entre chunks. Este módulo aplica
operadores 2-opt e tail-relocation focados APENAS em pares de blocos
que cruzam essas fronteiras, em vez de explorar todo o O(B²) espaço.

Reduz drasticamente o trabalho do ALNS: de O(B²) para O(B_boundary * K),
onde B_boundary << B (tipicamente 5-10% dos blocos tocam fronteiras).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from ..domain.models import Block, Trip, VSPSolution

logger = logging.getLogger(__name__)


def identify_boundary_blocks(
    blocks: List[Block],
    chunk_assignments: Optional[Dict[int, int]] = None,
    temporal_window_minutes: int = 240,
) -> Set[int]:
    """
    Identifica blocos que tocam uma fronteira de chunk.

    Critério:
        - Se chunk_assignments fornecido: bloco é fronteira quando vizinho
          temporal mais próximo está em chunk diferente.
        - Caso contrário: usa janelas temporais de `temporal_window_minutes`
          e marca blocos cujo start_time ou end_time cai dentro de
          ±15min da borda da janela.
    """
    if not blocks:
        return set()

    boundaries: Set[int] = set()
    blocks_sorted = sorted(blocks, key=lambda b: b.start_time)

    if chunk_assignments:
        for i, b in enumerate(blocks_sorted):
            my_chunk = chunk_assignments.get(b.id)
            if my_chunk is None:
                continue
            for nbr in (blocks_sorted[i - 1] if i > 0 else None,
                        blocks_sorted[i + 1] if i < len(blocks_sorted) - 1 else None):
                if nbr is None:
                    continue
                if chunk_assignments.get(nbr.id) != my_chunk:
                    boundaries.add(b.id)
                    break
        return boundaries

    # Fallback: janelas temporais
    win = max(60, int(temporal_window_minutes))
    edge_tol = 15
    if not blocks_sorted:
        return boundaries
    base = blocks_sorted[0].start_time
    for b in blocks_sorted:
        offset_start = (b.start_time - base) % win
        offset_end = (b.end_time - base) % win
        if offset_start <= edge_tol or offset_start >= win - edge_tol:
            boundaries.add(b.id)
        elif offset_end <= edge_tol or offset_end >= win - edge_tol:
            boundaries.add(b.id)
    return boundaries


def boundary_two_opt(
    vsp_sol: VSPSolution,
    vsp_params: Dict[str, Any],
    boundary_block_ids: Optional[Set[int]] = None,
) -> Tuple[VSPSolution, int]:
    """
    Aplica 2-opt mas restrito a pares (b1, b2) onde pelo menos um dos blocos
    está em `boundary_block_ids`. Costura emendas sem refazer trabalho.

    Retorna (nova_solucao, num_swaps_aplicados).
    """
    import copy

    min_layover = int(vsp_params.get("min_layover_minutes", 8))
    max_shift = int(vsp_params.get("max_vehicle_shift_minutes", 960))
    allow_multi = bool(vsp_params.get("allow_multi_line_block", True))

    blocks = [Block(id=b.id, trips=list(b.trips), vehicle_type_id=b.vehicle_type_id,
                    warnings=list(b.warnings), meta=dict(b.meta)) for b in vsp_sol.blocks]
    if boundary_block_ids is None:
        boundary_block_ids = identify_boundary_blocks(blocks)

    if not boundary_block_ids:
        logger.info("[BOUNDARY-2OPT] Nenhum bloco de fronteira — skip")
        return vsp_sol, 0

    blocks.sort(key=lambda b: b.start_time)
    swaps = 0
    boundary_set = set(boundary_block_ids)

    # Único pass focado: tenta mover trip[0] de b2 para fim de b1
    # quando AO MENOS UM dos blocos tocava a fronteira.
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            b1 = blocks[i]
            b2 = blocks[j]
            if b1.id not in boundary_set and b2.id not in boundary_set:
                continue
            if not b1.trips or not b2.trips:
                continue
            last_b1 = b1.trips[-1]
            first_b2 = b2.trips[0]
            gap = first_b2.start_time - last_b1.end_time
            if gap < 0:
                continue
            deadhead = int(last_b1.deadhead_times.get(first_b2.origin_id, 0))
            needed = max(min_layover, deadhead)
            if gap < needed:
                continue
            if not allow_multi and last_b1.line_id != first_b2.line_id:
                continue
            combined = first_b2.end_time - b1.trips[0].start_time
            if max_shift > 0 and combined > max_shift:
                continue
            b1.trips.append(first_b2)
            b2.trips.pop(0)
            swaps += 1

    blocks = [b for b in blocks if b.trips]
    for idx, b in enumerate(blocks):
        b.id = idx + 1

    if swaps == 0:
        return vsp_sol, 0

    new_sol = copy.copy(vsp_sol)
    new_sol.blocks = blocks
    new_sol.meta = {**(vsp_sol.meta or {}), "boundary_swaps": swaps}
    logger.info(
        f"[BOUNDARY-2OPT] {swaps} swaps em {len(boundary_set)} blocos de fronteira "
        f"({len(vsp_sol.blocks)} → {len(blocks)} blocos)"
    )
    return new_sol, swaps


def boundary_tail_relocation(
    vsp_sol: VSPSolution,
    vsp_params: Dict[str, Any],
    boundary_block_ids: Optional[Set[int]] = None,
    max_tail: int = 3,
) -> Tuple[VSPSolution, int]:
    """
    Realoca a "cauda" (últimas N trips) de um bloco de fronteira para
    outro bloco compatível, quando isso elimina um veículo.

    Critério estrito: só executa se o bloco doador ficar VAZIO após relocate
    (ganho real de -1 veículo).
    """
    import copy

    min_layover = int(vsp_params.get("min_layover_minutes", 8))
    max_shift = int(vsp_params.get("max_vehicle_shift_minutes", 960))

    blocks = [Block(id=b.id, trips=list(b.trips), vehicle_type_id=b.vehicle_type_id,
                    warnings=list(b.warnings), meta=dict(b.meta)) for b in vsp_sol.blocks]
    if boundary_block_ids is None:
        boundary_block_ids = identify_boundary_blocks(blocks)
    if not boundary_block_ids:
        return vsp_sol, 0

    relocations = 0
    boundary_set = set(boundary_block_ids)

    changed = True
    while changed:
        changed = False
        blocks.sort(key=lambda b: b.start_time)
        for i, donor in enumerate(blocks):
            if donor.id not in boundary_set or len(donor.trips) > max_tail:
                continue
            tail = donor.trips
            for j, recv in enumerate(blocks):
                if i == j or not recv.trips:
                    continue
                last_recv = recv.trips[-1]
                first_tail = tail[0]
                gap = first_tail.start_time - last_recv.end_time
                if gap < 0:
                    continue
                deadhead = int(last_recv.deadhead_times.get(first_tail.origin_id, 0))
                if gap < max(min_layover, deadhead):
                    continue
                combined = tail[-1].end_time - recv.trips[0].start_time
                if max_shift > 0 and combined > max_shift:
                    continue
                # Aceita: doador esvazia, receptor cresce
                recv.trips.extend(tail)
                donor.trips = []
                relocations += 1
                changed = True
                break
            if changed:
                break
        blocks = [b for b in blocks if b.trips]

    if relocations == 0:
        return vsp_sol, 0

    for idx, b in enumerate(blocks):
        b.id = idx + 1
    new_sol = copy.copy(vsp_sol)
    new_sol.blocks = blocks
    new_sol.meta = {**(vsp_sol.meta or {}), "boundary_tail_relocations": relocations}
    logger.info(
        f"[BOUNDARY-TAIL] {relocations} realocações eliminaram {relocations} veículos"
    )
    return new_sol, relocations


def stitch_chunk_boundaries(
    vsp_sol: VSPSolution,
    vsp_params: Dict[str, Any],
    chunk_assignments: Optional[Dict[int, int]] = None,
    temporal_window_minutes: int = 240,
) -> VSPSolution:
    """
    Pipeline completo de stitching para emendas de chunks:
        1. Identifica blocos de fronteira
        2. Tenta tail relocation (mais agressivo, elimina veículos)
        3. Roda 2-opt nas mesmas fronteiras
    """
    if len(vsp_sol.blocks) < 2:
        return vsp_sol

    boundary_ids = identify_boundary_blocks(
        vsp_sol.blocks,
        chunk_assignments=chunk_assignments,
        temporal_window_minutes=temporal_window_minutes,
    )
    logger.info(
        f"[STITCH] {len(boundary_ids)}/{len(vsp_sol.blocks)} blocos identificados "
        f"como fronteira"
    )
    sol, _ = boundary_tail_relocation(vsp_sol, vsp_params, boundary_ids)
    sol, _ = boundary_two_opt(sol, vsp_params, boundary_ids)
    return sol
