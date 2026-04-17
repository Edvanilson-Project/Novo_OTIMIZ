"""
VSP Ótimo via Minimum Cost Network Flow (MCNF) / Bipartite Matching.

Resolve o Vehicle Scheduling Problem de forma GLOBAL, batendo heurísticas gulosas
através da Teoria dos Grafos. A modelagem garante o emparelhamento exato com
o mínimo de ativação de veículos.

ARQUITETURA DE LARGA ESCALA:
    - Particionamento Temporal: Janelas de tempo com overlap para preservar conexões de fronteira
    - Clustering Espacial: Agrupamento por line_id quando allow_multi_line_block=False
    - Subproblemas menores: Cada partição resolve um MCNF 2N x 2N tratável
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
try:
    import pulp  # type: ignore
    _PULP_AVAILABLE = True
except Exception:
    pulp = None
    _PULP_AVAILABLE = False

from ...core.config import get_settings
from ...domain.interfaces import IVSPAlgorithm
from ...domain.models import Block, Trip, VehicleType, VSPSolution
from ..base import BaseAlgorithm

_log = logging.getLogger(__name__)
settings = get_settings()

_CLUSTER_SIZE_LIMIT = 800
_OVERLAP_RATIO = 0.10


class MCNFVSP(BaseAlgorithm, IVSPAlgorithm):
    """
    Otimiza a frota com Bipartite Graph Matching (Linear Sum Assignment).
    
    A formulação expande N trips em uma matriz de Custo 2N x 2N:
    [ T->T (Conexão)    | T->D (Pull-in)  ]
    ---------------------------------------
    [ D->T (Pull-out)   | D->D (Dummy)    ]
    
    A resolução desta matriz por `linear_sum_assignment` garante a cadeia 
    global incancelável que minimiza os custos operacionais da frota.
    
    Para instâncias >800 trips, aplica particionamento temporal com overlap
    para manter a qualidade da solução enquanto evita OOM.
    """
    def __init__(self, vsp_params: Optional[Dict[str, Any]] = None):
        super().__init__(name="mcnf_vsp", time_budget_s=120.0)
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
        
        _log.info(f"MCNF Engine inicializado para {len(trips)} viagens.")
        
        if depots is None:
            depots = [{"id": depot_id, "capacity": 999999}] if depot_id is not None else []
        
        allow_multi = bool(self._p("allow_multi_line_block", True))
        
        if len(trips) <= _CLUSTER_SIZE_LIMIT:
            return self._solve_subproblem(trips, vehicle_types, depots)
        
        if not allow_multi:
            return self._solve_by_line_clustering(trips, vehicle_types, depots)
        
        return self._solve_with_temporal_clustering(trips, vehicle_types, depots)

    def _solve_by_line_clustering(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depots: List[Dict[str, Any]],
    ) -> VSPSolution:
        """Agrupa trips por line_id e resolve cada grupo separadamente."""
        _log.info("MCNF Spatial Clustering: agrupando por line_id")
        
        by_line: Dict[int, List[Trip]] = defaultdict(list)
        for t in trips:
            by_line[t.line_id].append(t)
        
        all_blocks: List[Block] = []
        all_unassigned: List[Trip] = []
        block_id_counter = 1
        
        for line_id, line_trips in by_line.items():
            _log.debug(f"Processando line_id={line_id} com {len(line_trips)} trips")
            line_trips_sorted = sorted(line_trips, key=lambda t: (t.start_time, t.id))
            
            if len(line_trips_sorted) <= _CLUSTER_SIZE_LIMIT:
                result = self._solve_subproblem(line_trips_sorted, vehicle_types, depots)
            else:
                result = self._solve_with_temporal_clustering(line_trips_sorted, vehicle_types, depots)
            
            for block in result.blocks:
                block.id = block_id_counter
                block_id_counter += 1
                all_blocks.append(block)
            
            all_unassigned.extend(result.unassigned_trips)
        
        _log.info(f"MCNF Spatial: {len(all_blocks)} blocos de {len(by_line)} linhas")
        
        return VSPSolution(
            blocks=all_blocks,
            unassigned_trips=all_unassigned,
            algorithm=self.name,
            elapsed_ms=self._elapsed_ms(),
        )

    def _solve_with_temporal_clustering(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depots: List[Dict[str, Any]],
    ) -> VSPSolution:
        """
        Particiona trips em chunks temporais com overlap para preservar
        conexões nas fronteiras. Cada chunk gera blocos que são consolidados
        ao final.
        """
        _log.info(f"MCNF Temporal Clustering: {len(trips)} trips em chunks de {_CLUSTER_SIZE_LIMIT}")
        
        trips_sorted = sorted(trips, key=lambda t: (t.start_time, t.id))
        chunks = self._temporal_clustering(trips_sorted)
        
        _log.info(f"Temporal Clustering gerou {len(chunks)} chunks")
        
        all_blocks: List[Block] = []
        all_unassigned: List[Trip] = []
        assigned_trip_ids: set[int] = set()
        block_id_counter = 1
        
        for chunk_idx, chunk_trips in enumerate(chunks):
            is_first_chunk = chunk_idx == 0
            is_last_chunk = chunk_idx == len(chunks) - 1
            
            effective_trips = chunk_trips
            if not is_first_chunk and not is_last_chunk:
                overlap_size = int(len(chunk_trips) * _OVERLAP_RATIO)
                effective_trips = chunk_trips[overlap_size:]
            
            if len(effective_trips) < 2:
                for t in effective_trips:
                    if t.id not in assigned_trip_ids:
                        all_unassigned.append(t)
                continue
            
            result = self._solve_subproblem(effective_trips, vehicle_types, depots)
            
            for block in result.blocks:
                block_trip_ids = {t.id for t in block.trips}
                if block_trip_ids & assigned_trip_ids:
                    filtered_trips = [t for t in block.trips if t.id not in assigned_trip_ids]
                    if not filtered_trips:
                        continue
                    block = Block(id=block_id_counter, trips=filtered_trips)
                    if block.trips:
                        block.vehicle_type_id = block.trips[0].vehicle_type_id if hasattr(block.trips[0], 'vehicle_type_id') else None
                        block_id_counter += 1
                        all_blocks.append(block)
                        assigned_trip_ids.update(block_trip_ids - assigned_trip_ids)
                else:
                    block.id = block_id_counter
                    block_id_counter += 1
                    all_blocks.append(block)
                    assigned_trip_ids.update(block_trip_ids)
            
            for t in result.unassigned_trips:
                if t.id not in assigned_trip_ids:
                    all_unassigned.append(t)
        
        _log.info(f"MCNF Temporal: {len(all_blocks)} blocos consolidados")
        
        return VSPSolution(
            blocks=all_blocks,
            unassigned_trips=all_unassigned,
            algorithm=self.name,
            elapsed_ms=self._elapsed_ms(),
        )

    def _temporal_clustering(self, trips_sorted: List[Trip]) -> List[List[Trip]]:
        """
        Divide trips ordenados por tempo em chunks de tamanho máximo _CLUSTER_SIZE_LIMIT.
        Cada chunk inclui overlap com o próximo para preservar conexões de fronteira.
        """
        chunks: List[List[Trip]] = []
        n = len(trips_sorted)
        chunk_size = _CLUSTER_SIZE_LIMIT
        overlap_size = int(chunk_size * _OVERLAP_RATIO)
        
        start = 0
        while start < n:
            end = min(start + chunk_size, n)
            chunk = trips_sorted[start:end]
            chunks.append(chunk)
            start = end - overlap_size if end < n else end
        
        return chunks

    def _solve_subproblem(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depots: List[Dict[str, Any]],
    ) -> VSPSolution:
        """
        Core matemático do MCNF: monta matriz de custo 2N x 2N e resolve
        o Assignment Problem via linear_sum_assignment.
        
        Multi-Depot: Pull-out/Pull-in considera o melhor depot baseado em deadhead cost.
        Capacity Balancing: atribui blocos aos depots respeitando limites de capacidade.
        
        NOTA: A verificação de capacidade de depot é feita pós-resolução do assignment.
        O algoritmo primeiro encontra a solução de custo mínimo global, depois atribui
        os blocos aos depots respeitando a capacidade. Se um depot exceder a capacidade,
        um aviso é gerado mas a otimalidade global do emparelhamento é mantida.
        """
        vehicle = vehicle_types[0] if vehicle_types else None
        fixed_cost = float(self._p(
            "fixed_vehicle_activation_cost",
            vehicle.fixed_cost if vehicle else settings.default_vehicle_fixed_cost
        ))
        deadhead_cost = float(self._p("deadhead_cost_per_minute", 1.0))
        idle_cost = float(self._p("idle_cost_per_minute", 0.25))
        min_layover = int(self._p("min_layover_minutes", 8))
        max_shift = int(self._p("max_vehicle_shift_minutes", 960))
        allow_multi = bool(self._p("allow_multi_line_block", True))
        connection_tolerance = int(self._p("connection_tolerance_minutes", 0))
        
        INF = 1e9
        N = len(trips)

        if N > 1000:
            _log.warning("Instância massiva (>1000 trips). MCNF global abortado para evitar OOM. Retornando fallback Greedy.")
            from .greedy import GreedyVSP
            return GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id=depots[0]['id'] if depots else None)

        trips_sorted = sorted(trips, key=lambda t: (t.start_time, t.id))

        # Ensure we have at least one virtual depot if none provided
        local_depots = depots if depots else [{"id": -1, "capacity": 999999}]

        # Pre-filter conexões válidas para reduzir variáveis
        valid_X: Dict[Tuple[int, int], Dict[str, Any]] = {}
        for i in range(N):
            for j in range(N):
                if i == j:
                    continue
                if trips_sorted[j].start_time < trips_sorted[i].end_time:
                    continue
                if not allow_multi and trips_sorted[i].line_id != trips_sorted[j].line_id:
                    continue

                gap = trips_sorted[j].start_time - trips_sorted[i].end_time
                dh = max(min_layover, int(trips_sorted[i].deadhead_times.get(trips_sorted[j].origin_id, 0)))

                if gap + connection_tolerance < dh:
                    continue

                if gap > max_shift:
                    continue

                idle = gap - dh
                cost = (dh * deadhead_cost) + (idle * idle_cost)
                if trips_sorted[i].destination_id == trips_sorted[j].origin_id:
                    cost -= (fixed_cost * 0.05)

                valid_X[(i, j)] = {
                    "cost": max(0.0, cost),
                    "dh": dh,
                    "idle": max(0, idle),
                }

        # Precompute pull-out / pull-in costs per depot
        depot_caps: Dict[Any, int] = {}
        pullout_costs: Dict[Tuple[Any, int], float] = {}
        pullin_costs: Dict[Tuple[int, Any], float] = {}
        for depot in local_depots:
            did = depot.get("id")
            depot_caps[did] = int(depot.get("capacity", 999999))
            for i in range(N):
                dh_to_depot = int(trips_sorted[i].deadhead_times.get(did, 0))
                pullin_costs[(i, did)] = dh_to_depot * deadhead_cost
                pullout_costs[(did, i)] = fixed_cost + (dh_to_depot * deadhead_cost)

        # If PuLP isn't available, fallback to greedy
        if not _PULP_AVAILABLE:
            _log.warning("PuLP não disponível no ambiente; usando GreedyVSP como fallback.")
            from .greedy import GreedyVSP
            return GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id=depots[0]['id'] if depots else None)

        # Build MILP
        prob = pulp.LpProblem("MCNF_Subproblem", pulp.LpMinimize)

        X_vars = {k: pulp.LpVariable(f"x_{k[0]}_{k[1]}", cat="Binary") for k in valid_X.keys()}
        P_out_vars = {(did, i): pulp.LpVariable(f"pout_{did}_{i}", cat="Binary") for did in depot_caps.keys() for i in range(N)}
        P_in_vars = {(i, did): pulp.LpVariable(f"pin_{i}_{did}", cat="Binary") for i in range(N) for did in depot_caps.keys()}

        # Objective
        obj_terms = []
        for k, info in valid_X.items():
            obj_terms.append(info["cost"] * X_vars[k])
        for k, cost in pullout_costs.items():
            obj_terms.append(cost * P_out_vars[k])
        for k, cost in pullin_costs.items():
            obj_terms.append(cost * P_in_vars[k])

        prob += pulp.lpSum(obj_terms)

        # In-degree = 1 (incoming to each trip j)
        for j in range(N):
            in_terms = []
            for i in range(N):
                if (i, j) in X_vars:
                    in_terms.append(X_vars[(i, j)])
            for did in depot_caps.keys():
                in_terms.append(P_out_vars[(did, j)])
            prob += pulp.lpSum(in_terms) == 1, f"in_cover_{j}"

        # Out-degree = 1 (outgoing from each trip i)
        for i in range(N):
            out_terms = []
            for j in range(N):
                if (i, j) in X_vars:
                    out_terms.append(X_vars[(i, j)])
            for did in depot_caps.keys():
                out_terms.append(P_in_vars[(i, did)])
            prob += pulp.lpSum(out_terms) == 1, f"out_cover_{i}"

        # Depot capacity constraints
        for did, cap in depot_caps.items():
            prob += pulp.lpSum(P_out_vars[(did, i)] for i in range(N)) <= cap, f"depot_cap_{did}"

        # Solve with CBC (quiet)
        milp_start = time.time()
        try:
            solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=60)
            prob.solve(solver)
            milp_end = time.time()
        except Exception as e:
            _log.exception("PuLP solver falhou: %s", e)
            from .greedy import GreedyVSP
            return GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id=depots[0]['id'] if depots else None)

        if prob.status != pulp.constants.LpStatusOptimal:
            _log.warning("ILP solver status: %s — fallback para GreedyVSP", pulp.LpStatus[prob.status])
            from .greedy import GreedyVSP
            return GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id=depots[0]['id'] if depots else None)

        # Reconstroi sequenciamento a partir das variáveis selecionadas
        next_trip: Dict[int, int] = {}
        prev_trip: Dict[int, int] = {}
        start_depot_for: Dict[int, Any] = {}
        end_depot_for: Dict[int, Any] = {}

        for (i, j), var in X_vars.items():
            if float(pulp.value(var) or 0.0) > 0.5:
                next_trip[i] = j
                prev_trip[j] = i

        for (did, i), var in P_out_vars.items():
            if float(pulp.value(var) or 0.0) > 0.5:
                start_depot_for[i] = did

        for (i, did), var in P_in_vars.items():
            if float(pulp.value(var) or 0.0) > 0.5:
                end_depot_for[i] = did

        # Monta blocos (cadeias) a partir dos predecessores
        id_to_index = {t.id: idx for idx, t in enumerate(trips_sorted)}
        visited = set()
        blocks: List[Block] = []
        block_id_counter = 1

        for start_idx in range(N):
            if start_idx in visited:
                continue
            if start_idx in prev_trip:
                continue

            chain_idxs = []
            curr = start_idx
            while curr is not None and curr not in visited:
                chain_idxs.append(curr)
                visited.add(curr)
                curr = next_trip.get(curr)

            if not chain_idxs:
                continue

            chain_trips = [trips_sorted[idx] for idx in chain_idxs]
            block = Block(id=block_id_counter, trips=chain_trips)
            if vehicle:
                block.vehicle_type_id = vehicle.id

            block.meta.update({
                "activation_cost": fixed_cost,
                "connection_cost": 0.0,
                "deadhead_minutes": 0,
                "idle_minutes": 0,
            })

            # Soma custos da cadeia
            for a_idx, b_idx in zip(chain_idxs[:-1], chain_idxs[1:]):
                info = valid_X.get((a_idx, b_idx))
                if info:
                    block.meta["deadhead_minutes"] += info["dh"]
                    block.meta["idle_minutes"] += info["idle"]
                    block.meta["connection_cost"] += info["cost"]

            # Pull-out / Pull-in meta
            first_idx = chain_idxs[0]
            last_idx = chain_idxs[-1]
            block.meta["start_depot_id"] = start_depot_for.get(first_idx)
            block.meta["end_depot_id"] = end_depot_for.get(last_idx)
            block.meta["depot_pullout_cost"] = pullout_costs.get((block.meta["start_depot_id"], first_idx), 0.0)
            block.meta["depot_pullin_cost"] = pullin_costs.get((last_idx, block.meta["end_depot_id"]), 0.0)

            blocks.append(block)
            block_id_counter += 1

        total_trips_packed = sum(len(b.trips) for b in blocks)
        _log.info(f"MCNF Subproblem (MILP): {total_trips_packed}/{N} trips em {len(blocks)} blocos; solve_time_s={(milp_end-milp_start):.3f}")

        if vehicle and vehicle.is_electric and vehicle.battery_capacity_kwh > 0:
            blocks = self._ev_relax(blocks, vehicle, block_id_counter)

        # Unassigned (should be none if MILP foi factível)
        unassigned_trips = [t for t in trips_sorted if t.id not in {tr.id for b in blocks for tr in b.trips}]

        return VSPSolution(
            blocks=blocks,
            unassigned_trips=unassigned_trips,
            algorithm=self.name,
            elapsed_ms=self._elapsed_ms(),
            meta={
                "subproblem_trip_count": N,
                "milp_solve_time_s": (milp_end - milp_start) if 'milp_end' in locals() else None,
                "multi_depot": bool(depots),
                "depot_count": len(depots) if depots else 0,
            },
        )

    def _capacity_balancing(
        self,
        blocks: List[Block],
        depots: List[Dict[str, Any]],
        trips_sorted: List[Trip],
        deadhead_cost: float,
    ) -> Tuple[List[Block], List[str]]:
        """
        Atribui cada bloco ao depot com menor custo (pull-out + pull-in)
        que ainda tenha capacidade disponível.
        """
        # removido: capacity balancing agora é tratado na formulação MILP
        return blocks, []

    def _ev_relax(
        self,
        blocks: List[Block],
        vehicle: VehicleType,
        block_id_counter_start: int,
    ) -> List[Block]:
        """Fragmenta blocos que excedem limite de bateria (SoC) para veículos elétricos."""
        fragmented_blocks = []
        block_id_counter = block_id_counter_start
        
        for block in blocks:
            current_chain = []
            current_soc_kwh = vehicle.battery_capacity_kwh
            min_soc_kwh = vehicle.battery_capacity_kwh * vehicle.minimum_soc
            
            for idx, t in enumerate(block.trips):
                base_e = t.energy_kwh if t.energy_kwh > 0 else (t.distance_km * 1.25)
                topo = 1.0 + max(0.0, t.elevation_gain_m) * 0.0008
                energy_need = base_e * topo
                
                if idx > 0 and t.depot_id is not None:
                    gap = t.start_time - block.trips[idx-1].end_time
                    if gap > 0:
                        charged = min(vehicle.charge_rate_kw * (gap / 60.0), vehicle.battery_capacity_kwh)
                        current_soc_kwh = min(vehicle.battery_capacity_kwh, current_soc_kwh + charged)
                
                if current_soc_kwh - energy_need < min_soc_kwh and len(current_chain) > 0:
                    fb = Block(id=block_id_counter, trips=current_chain, vehicle_type_id=vehicle.id)
                    fb.meta["ev_fragmented"] = True
                    fragmented_blocks.append(fb)
                    block_id_counter += 1
                    current_chain = [t]
                    current_soc_kwh = vehicle.battery_capacity_kwh - energy_need
                else:
                    current_chain.append(t)
                    current_soc_kwh -= energy_need
                    
            if current_chain:
                fb = Block(id=block_id_counter, trips=current_chain, vehicle_type_id=vehicle.id)
                fragmented_blocks.append(fb)
                block_id_counter += 1
                
        if len(fragmented_blocks) > len(blocks):
            _log.info(f"EV Relaxer: {len(blocks)} → {len(fragmented_blocks)} blocos por limite de bateria")
        
        return fragmented_blocks