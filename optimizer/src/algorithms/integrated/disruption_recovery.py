"""
Disruption Recovery — re-otimização incremental após perturbação operacional.

Dado um schedule em execução (blocos de trips) e um conjunto de trips perturbadas
(atrasadas, canceladas, veículo avariado), encontra o menor re-arranjo que restaura
viabilidade com mínima perturbação ao schedule original.

ESTRATÉGIA:
  1. Identifica quais blocos são afetados pela perturbação.
  2. "Abre" apenas esses blocos, mantendo os intactos congelados.
  3. Roda GreedyVSP sobre as trips das regiões afetadas.
  4. Funde o resultado com os blocos congelados.
  5. Retorna um VSPSolution com meta contendo métricas de mudança.

REFERÊNCIA:
  Huisman D., Freling R., Wagelmans A. (2004) "Multiple-depot integrated vehicle
  and crew scheduling", Transportation Science 38(1):90-102.
  Disruption recovery: seção §4.3 "re-optimization with minimal perturbation".
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from ...domain.models import Block, OptimizationResult, Trip, VehicleType, VSPSolution
from ..vsp.greedy import GreedyVSP
from ..utils import select_vehicle_type

_log = logging.getLogger(__name__)

_MAX_DISRUPTION_RATIO = 0.5  # Se >50% dos blocos afetados, re-otimiza tudo


class DisruptionRecoverySolver:
    """Re-otimiza incrementalmente o schedule mínimo necessário após perturbação.

    Args (via vsp_params):
        disruption_max_affected_ratio: razão máxima de blocos reabertos antes de
            usar re-otimização total. Default: 0.5.
        disruption_freeze_unaffected: se True (default), mantém blocos intactos
            fixos e só re-otimiza os afetados.
    """

    def __init__(self, vsp_params: Optional[Dict[str, Any]] = None):
        self.vsp_params = vsp_params or {}

    def _p(self, key: str, default: Any) -> Any:
        return self.vsp_params.get(key, default)

    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        disrupted_trip_ids: Set[int],
        current_blocks: List[List[Trip]],
        depot_id: Optional[int] = None,
    ) -> OptimizationResult:
        """Executa a recuperação.

        Args:
            trips: lista completa de trips (incluindo perturbadas).
            vehicle_types: tipos de veículos disponíveis.
            disrupted_trip_ids: IDs das trips que foram perturbadas.
            current_blocks: schedule atual como lista de listas de trips.
            depot_id: garagem (opcional).

        Returns:
            OptimizationResult com VSP recuperado e meta de métricas de mudança.
        """
        if not trips:
            return OptimizationResult(
                vsp=VSPSolution(algorithm="disruption_recovery"),
                csp=None,
            )

        freeze_unaffected = bool(self._p("disruption_freeze_unaffected", True))
        max_ratio = float(self._p("disruption_max_affected_ratio", _MAX_DISRUPTION_RATIO))

        # Identificar blocos afetados
        affected_block_idxs: Set[int] = set()
        for idx, block_trips in enumerate(current_blocks):
            for trip in block_trips:
                if int(trip.id) in disrupted_trip_ids:
                    affected_block_idxs.add(idx)
                    break

        affected_ratio = len(affected_block_idxs) / max(1, len(current_blocks))
        _log.info(
            "[DisruptionRecovery] %d/%d blocos afetados (%.0f%%)",
            len(affected_block_idxs), len(current_blocks), affected_ratio * 100,
        )

        # Se perturbação > limiar → re-otimiza tudo
        if affected_ratio > max_ratio or not freeze_unaffected or not current_blocks:
            _log.info("[DisruptionRecovery] perturbação ampla → re-otimização total")
            return self._full_reoptimize(trips, vehicle_types, depot_id, disrupted_trip_ids)

        # Trips a re-otimizar: todas trips dos blocos afetados
        reopt_trips: List[Trip] = []
        frozen_blocks: List[Block] = []
        vt = select_vehicle_type(vehicle_types)
        frozen_trip_ids: Set[int] = set()

        for idx, block_trips in enumerate(current_blocks):
            if idx in affected_block_idxs:
                reopt_trips.extend(block_trips)
            else:
                frozen_trip_ids.update(int(t.id) for t in block_trips)
                frozen_blocks.append(
                    Block(
                        id=idx + 1,
                        trips=list(block_trips),
                        vehicle_type_id=vt.id if vt else None,
                        meta={"frozen": True},
                    )
                )

        # Inclui trips perturbadas que não estavam em nenhum bloco (novas trips)
        known_trip_ids = {int(t.id) for block in current_blocks for t in block}
        for trip in trips:
            if int(trip.id) not in known_trip_ids and int(trip.id) in disrupted_trip_ids:
                reopt_trips.append(trip)

        # Remove duplicatas mantendo ordem
        seen: Set[int] = set()
        unique_reopt: List[Trip] = []
        for t in reopt_trips:
            if int(t.id) not in seen:
                seen.add(int(t.id))
                unique_reopt.append(t)

        # Re-otimiza os blocos afetados com Greedy
        if unique_reopt:
            greedy = GreedyVSP(vsp_params=self.vsp_params)
            partial_vsp = greedy.solve(unique_reopt, vehicle_types, depot_id)
            reopt_blocks = partial_vsp.blocks
        else:
            reopt_blocks = []

        # Mescla blocos congelados + re-otimizados, renumerando IDs
        all_blocks: List[Block] = []
        for i, block in enumerate(frozen_blocks + reopt_blocks, start=1):
            block.id = i
            all_blocks.append(block)

        # Métricas de perturbação
        trips_reassigned = len(unique_reopt)
        blocks_changed = len(reopt_blocks)
        blocks_frozen = len(frozen_blocks)

        vsp = VSPSolution(
            blocks=all_blocks,
            unassigned_trips=[],
            algorithm="disruption_recovery",
            meta={
                "disruption_trip_ids": list(disrupted_trip_ids),
                "disruption_affected_blocks": len(affected_block_idxs),
                "disruption_frozen_blocks": blocks_frozen,
                "disruption_reoptimized_blocks": blocks_changed,
                "disruption_trips_reassigned": trips_reassigned,
                "disruption_affected_ratio": round(affected_ratio, 3),
                "disruption_strategy": "incremental",
            },
        )
        return OptimizationResult(vsp=vsp, csp=None)

    def _full_reoptimize(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int],
        disrupted_trip_ids: Set[int],
    ) -> OptimizationResult:
        greedy = GreedyVSP(vsp_params=self.vsp_params)
        vsp = greedy.solve(trips, vehicle_types, depot_id)
        vsp.meta = vsp.meta or {}
        vsp.meta.update({
            "disruption_trip_ids": list(disrupted_trip_ids),
            "disruption_strategy": "full_reoptimize",
            "disruption_affected_ratio": 1.0,
        })
        vsp.algorithm = "disruption_recovery"
        return OptimizationResult(vsp=vsp, csp=None)
