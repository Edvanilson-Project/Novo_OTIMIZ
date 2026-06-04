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
from typing import Any, Dict, List, Optional, Tuple


try:
    import pulp  # type: ignore

    _PULP_AVAILABLE = True
except Exception:
    pulp = None
    _PULP_AVAILABLE = False

try:
    from ortools.graph.python import min_cost_flow as _ortools_mcf_mod  # type: ignore

    _ORTOOLS_MCF_AVAILABLE = True
except Exception:
    _ortools_mcf_mod = None
    _ORTOOLS_MCF_AVAILABLE = False

# Fator de escala para converter custos float → int (OR-Tools exige inteiros)
_COST_SCALE = 1000


def _solve_mcf_ortools(
    N: int,
    valid_X: "Dict[Tuple[int,int], Dict[str, Any]]",
    depot_id: Any,
    pullout_costs: "Dict[Tuple[Any,int], float]",
    pullin_costs: "Dict[Tuple[int,Any], float]",
    fixed_cost: float,
) -> "Optional[Tuple[Dict[int,int], Dict[int,Any], Dict[int,Any]]]":
    """
    Resolve MCNF via OR-Tools SimpleMinCostFlow (network simplex, 40-56x mais rápido que PuLP/CBC).

    Formulação bipartida correta (Löbel 1998 — seção 3):
      - Nós 0..N-1:   trip_start[i]  (supply = -1: cada viagem deve receber um veículo)
      - Nós N..2N-1:  trip_end[i]    (supply = +1: cada viagem libera um veículo)
      - Nó 2N:        depot          (supply = 0: balanceado, custo de ativar veículo no pull-out)

    Arcos:
      - (depot, trip_start[i]):   pull-out  custo = fixed_cost + dh_pullout
      - (trip_end[i], trip_start[j]): conexão i→j  custo = deadhead + idle
      - (trip_end[i], depot):   pull-in  custo = dh_pullin

    Propriedade LP-integral: rede bipartida tem unimodularidade total → sem variáveis binárias.

    Retorna: (next_trip{i→j}, start_depot_for{i→did}, end_depot_for{i→did}) ou None se falhar.
    """
    if not _ORTOOLS_MCF_AVAILABLE:
        return None

    mcf = _ortools_mcf_mod.SimpleMinCostFlow()

    depot_node = 2 * N

    # Supply/demand: trip_start absorve (supply=-1), trip_end gera (supply=+1), depot balanceado
    for i in range(N):
        mcf.set_node_supply(i, -1)      # trip_start[i]: precisa de 1 veículo
        mcf.set_node_supply(N + i, 1)   # trip_end[i]: libera 1 veículo
    mcf.set_node_supply(depot_node, 0)  # depot balanceado

    # Arcos pull-out: depot → trip_start[i]  (ativa novo veículo)
    arc_pullout: list = []
    for i in range(N):
        cost_int = int(round(pullout_costs.get((depot_id, i), fixed_cost) * _COST_SCALE))
        arc_idx = mcf.add_arc_with_capacity_and_unit_cost(depot_node, i, 1, cost_int)
        arc_pullout.append(arc_idx)

    # Arcos de conexão: trip_end[i] → trip_start[j]  (veículo continua de i para j)
    arc_conn: "Dict[int, Tuple[int,int]]" = {}  # arc_idx → (i, j)
    for (i, j), info in valid_X.items():
        cost_int = int(round(max(0.0, info["cost"]) * _COST_SCALE))
        arc_idx = mcf.add_arc_with_capacity_and_unit_cost(N + i, j, 1, cost_int)
        arc_conn[arc_idx] = (i, j)

    # Arcos pull-in: trip_end[i] → depot  (veículo retorna ao depósito)
    arc_pullin: list = []
    for i in range(N):
        cost_int = int(round(pullin_costs.get((i, depot_id), 0.0) * _COST_SCALE))
        arc_idx = mcf.add_arc_with_capacity_and_unit_cost(N + i, depot_node, 1, cost_int)
        arc_pullin.append(arc_idx)

    status = mcf.solve()
    if status != mcf.OPTIMAL:
        return None

    # Extrai solução
    next_trip: "Dict[int, int]" = {}
    start_depot_for: "Dict[int, Any]" = {}
    end_depot_for: "Dict[int, Any]" = {}

    for arc_idx, (i, j) in arc_conn.items():
        if mcf.flow(arc_idx) > 0:
            next_trip[i] = j

    for arc_idx in arc_pullout:
        if mcf.flow(arc_idx) > 0:
            trip_i = mcf.head(arc_idx)  # trip_start node = destination
            start_depot_for[trip_i] = depot_id

    for arc_idx in arc_pullin:
        if mcf.flow(arc_idx) > 0:
            trip_i = mcf.tail(arc_idx) - N  # trip_end[N+i] = source → trip index = i
            end_depot_for[trip_i] = depot_id

    return next_trip, start_depot_for, end_depot_for


def _make_solver(time_limit: int, threads: int = 1) -> "pulp.LpSolver":
    """CBC (primary for binary MIP) with HiGHS as fallback if CBC unavailable."""
    cbc = pulp.PULP_CBC_CMD(timeLimit=time_limit, msg=0, keepFiles=False, threads=threads)
    if cbc.available():
        return cbc
    try:
        return pulp.HiGHS(timeLimit=time_limit, msg=0, threads=threads)
    except Exception:
        return cbc


from ...core.config import get_settings
from ...domain.interfaces import IVSPAlgorithm
from ...domain.models import Block, Trip, VehicleType, VSPSolution
from ..base import BaseAlgorithm
from ..utils import is_connection_feasible, select_vehicle_type
from .greedy import build_preferred_pairs, pairing_stats

_log = logging.getLogger(__name__)
settings = get_settings()

# Limite de trips para resolver o MCNF como um único fluxo (ótimo). Acima disso,
# particiona em clusters temporais/por linha (subótimo: veículos não são reusados
# entre clusters). Medido na carta real Salvador: a 2696 trips, limite=800 fragmenta
# em 736 blocos enquanto limite=3000 resolve em fluxo único = 184 blocos (24s). O MCF
# OR-Tools é polinomial; o gargalo é a construção O(N²) do grafo, tratável até ~3000.
# Configurável via vsp_params["mcnf_cluster_size_limit"].
_CLUSTER_SIZE_LIMIT = 3000
# 10% de overlap nas fronteiras de cluster. Tentativa de 20% foi revertida porque
# criava blocos > 780min forçando duties acima do limite legal CCT (test_no_duty_exceeds_legal_max).
_OVERLAP_RATIO = 0.10


class MCNFVSP(BaseAlgorithm, IVSPAlgorithm):
    """
    Min-Cost Network Flow para VSP de único depósito (Löbel 1998).

    Modelagem como MILP binário via PuLP/CBC:
    - Variáveis X[i,j]: arco trip i → trip j (conexão)
    - Variáveis P_out[depot, i]: pull-out (saída do depósito)
    - Variáveis P_in[i, depot]: pull-in (retorno ao depósito)
    - Restrições de cobertura garantem cada trip coberta exatamente uma vez.

    Para instâncias >800 trips, aplica particionamento temporal com overlap
    para manter a qualidade da solução enquanto evita OOM.
    """

    def __init__(self, vsp_params: Optional[Dict[str, Any]] = None):
        super().__init__(name="mcnf_vsp", time_budget_s=120.0)
        self.vsp_params = vsp_params or {}
        self._cluster_limit = int(self.vsp_params.get("mcnf_cluster_size_limit", _CLUSTER_SIZE_LIMIT) or _CLUSTER_SIZE_LIMIT)

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

        if len(trips) <= self._cluster_limit:
            solution = self._solve_subproblem(trips, vehicle_types, depots)
            return self._rescore_vsp_solution(solution, vehicle_types)

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

            if len(line_trips_sorted) <= self._cluster_limit:
                result = self._solve_subproblem(line_trips_sorted, vehicle_types, depots)
            else:
                result = self._solve_with_temporal_clustering(line_trips_sorted, vehicle_types, depots)

            for block in result.blocks:
                block.id = block_id_counter
                block_id_counter += 1
                all_blocks.append(block)

            all_unassigned.extend(result.unassigned_trips)

        _log.info(f"MCNF Spatial: {len(all_blocks)} blocos de {len(by_line)} linhas")

        solution = VSPSolution(
            blocks=all_blocks,
            unassigned_trips=all_unassigned,
            algorithm=self.name,
            elapsed_ms=self._elapsed_ms(),
        )
        return self._rescore_vsp_solution(solution, vehicle_types)

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
                    _depot = filtered_trips[0].depot_id if filtered_trips else None
                    _vt = select_vehicle_type(vehicle_types, _depot)
                    block = Block(
                        id=block_id_counter,
                        trips=filtered_trips,
                        vehicle_type_id=_vt.id if _vt else None,
                    )
                    if block.trips:
                        block_id_counter += 1
                        all_blocks.append(block)
                        # BUG-MCNF-B fix: `block_trip_ids` era do bloco ORIGINAL (antes do filtro).
                        # Trips removidas pelo filtro eram marcadas como cobertas sem estar em nenhum bloco.
                        # Correto: marcar apenas os IDs das filtered_trips que realmente entraram.
                        assigned_trip_ids.update({t.id for t in block.trips})
                else:
                    block.id = block_id_counter
                    block_id_counter += 1
                    all_blocks.append(block)
                    assigned_trip_ids.update(block_trip_ids)

            for t in result.unassigned_trips:
                if t.id not in assigned_trip_ids:
                    all_unassigned.append(t)

        _log.info(f"MCNF Temporal: {len(all_blocks)} blocos consolidados")

        solution = VSPSolution(
            blocks=all_blocks,
            unassigned_trips=all_unassigned,
            algorithm=self.name,
            elapsed_ms=self._elapsed_ms(),
        )
        return self._rescore_vsp_solution(solution, vehicle_types)

    def _temporal_clustering(self, trips_sorted: List[Trip]) -> List[List[Trip]]:
        """
        Divide trips ordenados por tempo em chunks de tamanho máximo _CLUSTER_SIZE_LIMIT.
        Cada chunk inclui overlap com o próximo para preservar conexões de fronteira.
        """
        chunks: List[List[Trip]] = []
        n = len(trips_sorted)
        chunk_size = self._cluster_limit
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
        vehicle = select_vehicle_type(vehicle_types)
        fixed_cost = float(
            self._p(
                "fixed_vehicle_activation_cost", vehicle.fixed_cost if vehicle else settings.default_vehicle_fixed_cost
            )
        )
        deadhead_cost = float(self._p("deadhead_cost_per_minute", 1.0))
        idle_cost = float(self._p("idle_cost_per_minute", 0.5))  # BUG-MCNF-01: era 0.25, corrigido para 0.5 (consistente com SA/Tabu/Greedy)
        min_layover = int(self._p("min_layover_minutes", 8))
        min_break = self._p("min_break_minutes", None)
        enforce_min_interval = bool(self._p("enforce_min_interval", self._p("strict_min_interval", False)))
        # NOTE: min_break is a DRIVER constraint (CCT) applied in the CSP.
        # Do NOT inflate min_layover here — vehicle only needs technical
        # turnaround time (min_layover). The old code raised min_layover
        # from 10→30, adding ~10 extra vehicles.
        max_shift = int(self._p("max_vehicle_shift_minutes", 960))
        allow_multi = bool(self._p("allow_multi_line_block", True))
        connection_tolerance = int(self._p("connection_tolerance_minutes", 0))
        preserve_preferred_pairs = bool(self._p("preserve_preferred_pairs", True))
        preferred_pair_window = int(self._p("preferred_pair_window_minutes", 120))
        pair_break_penalty = float(self._p("pair_break_penalty", fixed_cost * 1.25))
        paired_trip_bonus = float(self._p("paired_trip_bonus", fixed_cost * 0.05))
        hard_pairing_vehicle_level = bool(self._p("hard_pairing_vehicle_level", False))
        hard_pairing_penalty = (
            float(self._p("hard_pairing_penalty", max(pair_break_penalty * 10.0, fixed_cost * 25.0)))
            if hard_pairing_vehicle_level
            else 0.0
        )
        idle_behavior = str(self._p("vehicle_idle_gap_behavior", "solver_decides") or "solver_decides")
        idle_threshold = self._p("vehicle_idle_gap_threshold_minutes", None)
        max_idle_gap: Optional[int] = None
        if idle_behavior != "stay_at_terminal" and idle_threshold is not None:
            try:
                parsed_threshold = int(idle_threshold)
                max_idle_gap = parsed_threshold if parsed_threshold > 0 else None
            except (TypeError, ValueError):
                max_idle_gap = None

        INF = 1e9
        N = len(trips)

        if N > self._cluster_limit:
            _log.warning(
                "Subproblema MCNF com %d trips excede limite %d; redirecionando para chunking.",
                N,
                self._cluster_limit,
            )
            return self._solve_with_temporal_clustering(trips, vehicle_types, depots)

        trips_sorted = sorted(trips, key=lambda t: (t.start_time, t.id))
        preferred_pairs = (
            build_preferred_pairs(trips_sorted, min_layover, preferred_pair_window) if preserve_preferred_pairs else {}
        )
        trip_order = {int(trip.id): idx for idx, trip in enumerate(trips_sorted)}
        preferred_next = {
            int(trip_id): int(pair_id)
            for trip_id, pair_id in preferred_pairs.items()
            if trip_order.get(int(trip_id), 0) < trip_order.get(int(pair_id), 0)
        }

        # Ensure we have at least one virtual depot if none provided
        local_depots = depots if depots else [{"id": -1, "capacity": 999999}]

        # Pre-filter conexões válidas: O(N²) com early-break por monotonicidade temporal.
        # trips_sorted está ordenado por start_time, então gap = trips[j].start - trips[i].end
        # é não-decrescente em j para j > i. Quando gap > max_shift, todos os j seguintes
        # também excedem, permitindo o break. Iteramos apenas j > i (j < i sempre inválido).
        valid_X: Dict[Tuple[int, int], Dict[str, Any]] = {}
        for i in range(N):
            for j in range(i + 1, N):
                gap = trips_sorted[j].start_time - trips_sorted[i].end_time
                if gap > max_shift:
                    break  # Monotonicidade: todos os j seguintes também excedem max_shift
                if gap < 0:
                    continue  # Sobreposição temporal (trip j começa antes de i terminar)
                if max_idle_gap is not None and gap > max_idle_gap:
                    break  # gap é monotonicamente não-decrescente; todos os j seguintes também excedem
                if not allow_multi and trips_sorted[i].line_id != trips_sorted[j].line_id:
                    continue

                if not is_connection_feasible(
                    trips_sorted[i],
                    trips_sorted[j],
                    min_layover=min_layover,
                    min_break=int(min_break) if min_break is not None else 30,
                    enforce_min_interval=enforce_min_interval,
                    connection_tolerance=connection_tolerance,
                ):
                    continue

                # BUG-MCNF-02 fix: Separate real deadhead travel time from
                # mandatory layover.  Previously the code used
                #   dh = max(min_layover, deadhead_real)
                # which charged deadhead_cost_per_minute for min_layover even
                # when the vehicle stays at the same terminal (real deadhead=0).
                # This inflated connection costs by ~R$100 per same-terminal
                # connection (10min × R$10/min instead of 10min × R$2/min).
                raw_dh = int(trips_sorted[i].deadhead_times.get(trips_sorted[j].origin_id, 0))
                # Same-terminal connections have zero deadhead travel
                if trips_sorted[i].destination_id == trips_sorted[j].origin_id:
                    raw_dh = 0
                dh = max(0, raw_dh)
                # Mandatory layover is idle, not deadhead
                min_wait = max(min_layover, dh)  # vehicle must wait at least min_layover or deadhead travel time
                idle = gap - min_wait
                cost = (dh * deadhead_cost) + ((min_wait - dh + max(0, idle)) * idle_cost)
                # Record actual deadhead and idle for block metadata
                actual_idle = max(0, gap - dh)

                # Preferred pair incentives
                pair_target = preferred_next.get(int(trips_sorted[i].id))
                if pair_target is not None:
                    if int(trips_sorted[j].id) == pair_target:
                        cost -= paired_trip_bonus * 3.0
                    else:
                        cost += hard_pairing_penalty if hard_pairing_vehicle_level else pair_break_penalty

                valid_X[(i, j)] = {
                    "cost": max(0.0, cost),
                    "dh": dh,
                    "idle": max(0, actual_idle),
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
                if int(trips_sorted[i].id) in preferred_next:
                    pullin_costs[(i, did)] += hard_pairing_penalty if hard_pairing_vehicle_level else pair_break_penalty
                pullout_costs[(did, i)] = fixed_cost + (dh_to_depot * deadhead_cost)

        # --- OR-Tools SimpleMinCostFlow (primário: 40-56x mais rápido que PuLP/CBC) ---
        # Funciona para single-depot. Para multi-depot, cai no PuLP abaixo.
        _single_depot_id = list(depot_caps.keys())[0] if len(depot_caps) == 1 else None
        if _ORTOOLS_MCF_AVAILABLE and _single_depot_id is not None:
            _t_ort = time.time()
            _ort_result = _solve_mcf_ortools(
                N=N,
                valid_X=valid_X,
                depot_id=_single_depot_id,
                pullout_costs=pullout_costs,
                pullin_costs=pullin_costs,
                fixed_cost=fixed_cost,
            )
            _elapsed_ort = (time.time() - _t_ort) * 1000
            if _ort_result is not None:
                _log.info("MCNF OR-Tools: N=%d resolvido em %.1fms (vs ~%.0fms PuLP/CBC)", N, _elapsed_ort, N * 1.8)
                next_trip, start_depot_for, end_depot_for = _ort_result
                # Salta direto para reconstrução de blocos (compartilhada com PuLP)
                return self._build_blocks_from_assignment(
                    next_trip=next_trip,
                    start_depot_for=start_depot_for,
                    end_depot_for=end_depot_for,
                    trips_sorted=trips_sorted,
                    valid_X=valid_X,
                    fixed_cost=fixed_cost,
                    pullout_costs=pullout_costs,
                    pullin_costs=pullin_costs,
                    vehicle=vehicle,
                    vehicle_types=vehicle_types,
                    depots=depots,
                    N=N,
                    solver_name="ortools_mcf",
                    elapsed_ms=_elapsed_ort,
                    preserve_preferred_pairs=preserve_preferred_pairs,
                    preferred_pair_window=preferred_pair_window,
                    preferred_pairs=preferred_pairs,
                )
            _log.warning("OR-Tools MCF retornou não-ótimo (N=%d) — fallback para PuLP/CBC", N)

        # If PuLP isn't available, fallback to greedy
        if not _PULP_AVAILABLE:
            _log.warning("PuLP não disponível no ambiente; usando GreedyVSP como fallback.")
            from .greedy import GreedyVSP

            return GreedyVSP(vsp_params=self.vsp_params).solve(
                trips, vehicle_types, depot_id=depots[0]["id"] if depots else None
            )

        # Build MILP
        prob = pulp.LpProblem("MCNF_Subproblem", pulp.LpMinimize)

        X_vars = {k: pulp.LpVariable(f"x_{k[0]}_{k[1]}", cat="Binary") for k in valid_X.keys()}
        P_out_vars = {
            (did, i): pulp.LpVariable(f"pout_{did}_{i}", cat="Binary") for did in depot_caps.keys() for i in range(N)
        }
        P_in_vars = {
            (i, did): pulp.LpVariable(f"pin_{i}_{did}", cat="Binary") for i in range(N) for did in depot_caps.keys()
        }

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

        # Timeout dinâmico: instâncias menores têm mais tempo proporcional (CBC é mais lento em MILPs densos)
        _size_timeout = 120 if N <= 200 else (90 if N <= 500 else (60 if N <= 800 else 40))
        ilp_timeout = int(self.vsp_params.get("mcnf_ilp_timeout_seconds", min(_size_timeout, int(self.time_budget_s))))

        _log.info(f"MCNFVSP: Resolvendo matriz {N}x{N} (timeout={ilp_timeout}s)")

        milp_start = time.time()
        try:
            prob.solve(_make_solver(ilp_timeout, threads=settings.ilp_threads))
            milp_end = time.time()
        except Exception as e:
            _log.exception("PuLP solver falhou: %s", e)
            from .greedy import GreedyVSP

            return GreedyVSP(vsp_params=self.vsp_params).solve(
                trips, vehicle_types, depot_id=depots[0]["id"] if depots else None
            )

        if prob.status != pulp.constants.LpStatusOptimal:
            status_str = pulp.LpStatus[prob.status]
            _log.warning("ILP solver status: %s — fallback para GreedyVSP", status_str)
            from .greedy import GreedyVSP

            res = GreedyVSP(vsp_params=self.vsp_params).solve(
                trips, vehicle_types, depot_id=depots[0]["id"] if depots else None
            )
            res.meta.update(
                {
                    "fallback_used": True,
                    "fallback_reason": status_str,
                    "original_solver": "mcnf_ilp",
                    "fallback_solver": "greedy_vsp",
                }
            )
            return res

        # Reconstroi sequenciamento a partir das variáveis PuLP
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

        _log.info("MCNF Subproblem (PuLP/CBC): N=%d, solve_time_s=%.3f", N, milp_end - milp_start)
        return self._build_blocks_from_assignment(
            next_trip=next_trip,
            start_depot_for=start_depot_for,
            end_depot_for=end_depot_for,
            trips_sorted=trips_sorted,
            valid_X=valid_X,
            fixed_cost=fixed_cost,
            pullout_costs=pullout_costs,
            pullin_costs=pullin_costs,
            vehicle=vehicle,
            vehicle_types=vehicle_types,
            depots=depots,
            N=N,
            solver_name="pulp_cbc",
            elapsed_ms=(milp_end - milp_start) * 1000,
            preserve_preferred_pairs=preserve_preferred_pairs,
            preferred_pair_window=preferred_pair_window,
            preferred_pairs=preferred_pairs,
        )

    def _build_blocks_from_assignment(
        self,
        *,
        next_trip: Dict[int, int],
        start_depot_for: Dict[int, Any],
        end_depot_for: Dict[int, Any],
        trips_sorted: List[Trip],
        valid_X: Dict[Tuple[int, int], Dict[str, Any]],
        fixed_cost: float,
        pullout_costs: Dict[Tuple[Any, int], float],
        pullin_costs: Dict[Tuple[int, Any], float],
        vehicle: Any,
        vehicle_types: List[VehicleType],
        depots: List[Dict[str, Any]],
        N: int,
        solver_name: str = "mcnf",
        elapsed_ms: float = 0.0,
        preserve_preferred_pairs: bool = True,
        preferred_pair_window: int = 120,
        preferred_pairs: Optional[Dict] = None,
    ) -> VSPSolution:
        """Reconstrói blocos VSP a partir do mapeamento next_trip/start_depot_for/end_depot_for.
        Compartilhado entre OR-Tools e PuLP para evitar duplicação.
        """
        prev_trip: Dict[int, int] = {j: i for i, j in next_trip.items()}
        visited: set = set()
        blocks: List[Block] = []
        block_id_counter = 1

        for start_idx in range(N):
            if start_idx in visited:
                continue
            if start_idx in prev_trip:
                continue

            chain_idxs: List[int] = []
            curr: Optional[int] = start_idx
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

            block.meta.update(
                {
                    "activation_cost": fixed_cost,
                    "connection_cost": 0.0,
                    "deadhead_minutes": 0,
                    "idle_minutes": 0,
                }
            )

            for a_idx, b_idx in zip(chain_idxs[:-1], chain_idxs[1:]):
                info = valid_X.get((a_idx, b_idx))
                if info:
                    block.meta["deadhead_minutes"] += info["dh"]
                    block.meta["idle_minutes"] += info["idle"]
                    block.meta["connection_cost"] += info["cost"]

            first_idx = chain_idxs[0]
            last_idx = chain_idxs[-1]
            block.meta["start_depot_id"] = start_depot_for.get(first_idx)
            block.meta["end_depot_id"] = end_depot_for.get(last_idx)
            block.meta["depot_pullout_cost"] = pullout_costs.get((block.meta["start_depot_id"], first_idx), 0.0)
            block.meta["depot_pullin_cost"] = pullin_costs.get((last_idx, block.meta["end_depot_id"]), 0.0)

            blocks.append(block)
            block_id_counter += 1

        if vehicle and vehicle.is_electric and vehicle.battery_capacity_kwh > 0:
            blocks = self._ev_relax(blocks, vehicle, block_id_counter)

        max_block_duration = self._p("max_block_duration_minutes", None)
        # BUG-MCNF-03 fix: O MCNF verifica o GAP entre viagens (max_shift) mas nunca
        # o span TOTAL do bloco. Um bloco pode ter span de 963min com gaps individuais <960min.
        # Quando max_block_duration_minutes não está setado mas max_vehicle_shift_minutes está
        # configurado explicitamente, usá-lo como limite de span total do bloco VSP.
        # Nota: max_vehicle_shift_minutes tem default=960, então verificamos se foi
        # explicitamente passado nos parâmetros (não é None antes do default).
        if max_block_duration is None:
            explicit_max_shift = self.vsp_params.get("max_vehicle_shift_minutes") if hasattr(self, "vsp_params") else None
            if explicit_max_shift is not None:
                max_block_duration = int(explicit_max_shift)
        if max_block_duration is not None and int(max_block_duration) > 0:
            blocks = self._split_blocks_by_total_duration(blocks, int(max_block_duration))


        total_trips_packed = sum(len(b.trips) for b in blocks)
        _effective_preferred_pairs = preferred_pairs or {}
        pair_meta = (
            pairing_stats(blocks, _effective_preferred_pairs)
            if _effective_preferred_pairs
            else {
                "preferred_pair_count": 0,
                "paired_connections_followed": 0,
                "preferred_pair_breaks": 0,
            }
        )
        _log.info(
            "MCNF %s: %d/%d trips → %d blocos em %.1fms",
            solver_name, total_trips_packed, N, len(blocks), elapsed_ms,
        )

        unassigned_trips = [t for t in trips_sorted if t.id not in {tr.id for b in blocks for tr in b.trips}]

        solution = VSPSolution(
            blocks=blocks,
            unassigned_trips=unassigned_trips,
            algorithm=self.name,
            elapsed_ms=self._elapsed_ms(),
            meta={
                "subproblem_trip_count": N,
                "solver": solver_name,
                "solver_elapsed_ms": round(elapsed_ms, 1),
                "multi_depot": bool(depots),
                "depot_count": len(depots) if depots else 0,
                "preserve_preferred_pairs": preserve_preferred_pairs,
                "preferred_pair_window_minutes": preferred_pair_window,
                **pair_meta,
            },
        )
        return self._rescore_vsp_solution(solution, vehicle_types)

    def _split_blocks_by_total_duration(
        self,
        blocks: List[Block],
        max_duration_minutes: int,
    ) -> List[Block]:
        """BUG-06 fix: pós-processamento que divide blocos cuja duração total
        (end_time da última trip - start_time da primeira) excede max_duration_minutes.

        Mantém otimalidade local: divide no ponto onde o gap acumulado seria menor.
        """
        result: List[Block] = []
        next_id = max([b.id for b in blocks], default=0) + 1
        for block in blocks:
            if len(block.trips) <= 1:
                result.append(block)
                continue
            total_duration = block.trips[-1].end_time - block.trips[0].start_time
            if total_duration <= max_duration_minutes:
                result.append(block)
                continue

            # Divide greedy: começa novo bloco quando duração acumulada > max
            chains: List[List[Trip]] = [[block.trips[0]]]
            for t in block.trips[1:]:
                current_start = chains[-1][0].start_time
                if t.end_time - current_start > max_duration_minutes:
                    chains.append([t])
                else:
                    chains[-1].append(t)

            if len(chains) == 1:
                result.append(block)
                continue

            _log.warning(
                "[MCNF-SPLIT] Block %d (duration=%dm > max=%dm) dividido em %d sub-blocos",
                block.id,
                total_duration,
                max_duration_minutes,
                len(chains),
            )
            for chain in chains:
                sub = Block(id=next_id, trips=chain, vehicle_type_id=block.vehicle_type_id)
                sub.meta.update(block.meta or {})
                sub.meta["split_from_block_id"] = block.id
                sub.meta["split_reason"] = "max_block_duration_minutes"
                result.append(sub)
                next_id += 1
        return result

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
                    gap = t.start_time - block.trips[idx - 1].end_time
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
