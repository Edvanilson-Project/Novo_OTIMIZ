"""
VSP — Regional Decomposition Solver (RDS).

Estratégia para instâncias ≥ 5 000 viagens:

  1. AGRUPA trips por depot_id.
     Se depot_id não estiver preenchido, agrupa por janela temporal de 4h
     (rolling horizon: 5:00-9:00, 9:00-13:00, …), garantindo overlap de
     30 min nas bordas para que blocos não sejam quebrados arbitrariamente.

  2. RESOLVE cada grupo em paralelo com o algoritmo sub configurado
     (padrão: "tabu"; aceita "greedy", "sa", "branch_and_price").

  3. MERGEA soluções: concatena blocks de todos os grupos em uma única
     VSPSolution. O custo total é a soma dos custos parciais.

Complexidade efectiva: O(k · T(n/k)) onde k = n.° grupos e T = custo
do sub-algoritmo. Para n=30 000 com k=30 depots → T(1 000) ≈ 8,5s cada;
em paralelo total ≈ 8,5s (limitado por I/O + GIL → usa processes).

Uso:
    solver = RegionalDecompositionSolver(sub_algorithm="tabu")
    result = solver.solve(trips, vehicle_types)

Via API:
    POST /optimize {"algorithm": "regional", "trips": [...]}
"""

from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from ...domain.interfaces import IVSPAlgorithm
from ...domain.models import Block, Trip, VehicleType, VSPSolution
from ..base import BaseAlgorithm

logger = logging.getLogger(__name__)

# Janela temporal de cada grupo quando não há depot_id (minutos)
_WINDOW_MINUTES = 240  # 4 horas
# Overlap entre janelas para evitar quebrar blocos na fronteira
_OVERLAP_MINUTES = 30


def _solve_group(args: Tuple) -> VSPSolution:
    """Função de topo para ProcessPoolExecutor (deve ser picklável)."""
    import os

    os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "subprocess-worker-key")
    os.environ.setdefault("DATABASE_URL", "sqlite:///./worker.db")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

    trip_dicts, vt_dicts, sub_algorithm, vsp_params, time_budget_s = args

    # Reconstrói objetos do domínio no sub-processo
    from ...domain.models import Trip as T, VehicleType as VT, VSPSolution

    trips = [T(**d) for d in trip_dicts]
    vts = [VT(**d) for d in vt_dicts]

    solver = _make_sub_solver(sub_algorithm, vsp_params, time_budget_s)
    try:
        return solver.solve(trips, vts)
    except Exception as exc:
        logger.error("Erro no sub-solver (%s): %s", sub_algorithm, exc)
        # Fallback: cada viagem vira um bloco unitário
        blocks = [Block(id=i + 1, trips=[t]) for i, t in enumerate(trips)]
        return VSPSolution(blocks=blocks, algorithm="fallback")


def _make_sub_solver(algorithm: str, vsp_params: dict, time_budget_s: float):
    """Instancia o solver filho pelo nome."""
    from .greedy import GreedyVSP
    from .tabu_search import TabuSearchVSP
    from .simulated_annealing import SimulatedAnnealingVSP
    from .branch_and_price import BranchAndPrice

    mapping = {
        "greedy": lambda: GreedyVSP(vsp_params=vsp_params),
        "tabu": lambda: TabuSearchVSP(vsp_params=vsp_params),
        "sa": lambda: SimulatedAnnealingVSP(vsp_params=vsp_params),
        "branch_and_price": lambda: BranchAndPrice(vsp_params=vsp_params),
    }
    factory = mapping.get(algorithm, mapping["tabu"])
    solver = factory()
    solver.time_budget_s = time_budget_s
    return solver


def _group_by_depot(trips: List[Trip]) -> Dict[str, List[Trip]]:
    """Agrupa por depot_id. Trips sem depot vão para grupo 'unassigned'."""
    groups: Dict[str, List[Trip]] = defaultdict(list)
    for t in trips:
        key = str(t.depot_id) if t.depot_id is not None else "unassigned"
        groups[key].append(t)
    return dict(groups)


def _group_by_time_window(trips: List[Trip]) -> Dict[str, List[Trip]]:
    """
    Agrupa por janela temporal de _WINDOW_MINUTES com overlap de _OVERLAP_MINUTES.

    Uma trip aparece em um grupo quando:
        window_start - overlap ≤ trip.start_time < window_start + window_size
    """
    if not trips:
        return {}

    min_t = min(t.start_time for t in trips)
    max_t = max(t.start_time for t in trips)
    groups: Dict[str, List[Trip]] = defaultdict(list)

    window_start = (min_t // _WINDOW_MINUTES) * _WINDOW_MINUTES
    while window_start <= max_t:
        window_end = window_start + _WINDOW_MINUTES
        key = f"w{window_start}"
        lower = window_start - _OVERLAP_MINUTES
        for t in trips:
            if lower <= t.start_time < window_end:
                groups[key].append(t)
        window_start = window_end

    return {k: v for k, v in groups.items() if v}


def _trip_to_dict(t: Trip) -> dict:
    """Converte Trip para dict serialzável (para ProcessPoolExecutor)."""
    return {
        "id": t.id,
        "line_id": t.line_id,
        "start_time": t.start_time,
        "end_time": t.end_time,
        "origin_id": t.origin_id,
        "destination_id": t.destination_id,
        "duration": t.duration,
        "depot_id": t.depot_id,
        "trip_group_id": t.trip_group_id,
        "direction": t.direction,
        "distance_km": t.distance_km,
        "energy_kwh": t.energy_kwh,
    }


def _vt_to_dict(vt: VehicleType) -> dict:
    return {
        "id": vt.id,
        "name": vt.name,
        "passenger_capacity": vt.passenger_capacity,
        "fixed_cost": vt.fixed_cost,
        "cost_per_km": vt.cost_per_km,
        "cost_per_hour": vt.cost_per_hour,
        "is_electric": vt.is_electric,
        "battery_capacity_kwh": vt.battery_capacity_kwh,
        "minimum_soc": vt.minimum_soc,
        "charge_rate_kw": vt.charge_rate_kw,
        "energy_cost_per_kwh": vt.energy_cost_per_kwh,
        "depot_id": vt.depot_id,
    }


class RegionalDecompositionSolver(BaseAlgorithm, IVSPAlgorithm):
    """
    VSP solver para instâncias de grande escala (≥ 5 000 viagens) via
    decomposição regional paralela.

    Parâmetros:
        sub_algorithm: algoritmo filho por grupo ("tabu", "greedy", "sa", "branch_and_price")
        max_workers:   n.° máximo de processos paralelos (None = n.° CPUs)
        use_processes: True → ProcessPoolExecutor (mais isolamento, evita GIL)
                       False → ThreadPoolExecutor (mais rápido em payloads pequenos)
        vsp_params:    repassados ao solver filho
    """

    def __init__(
        self,
        sub_algorithm: str = "tabu",
        max_workers: Optional[int] = None,
        use_processes: bool = True,
        vsp_params: Optional[dict] = None,
        time_budget_s: Optional[float] = None,
    ):
        from ...core.config import get_settings

        settings = get_settings()
        super().__init__(
            name="regional_decomposition",
            time_budget_s=time_budget_s or float(settings.hybrid_time_budget_seconds),
        )
        self.sub_algorithm = sub_algorithm
        self.max_workers = max_workers
        self.use_processes = use_processes
        self.vsp_params = dict(vsp_params or {})

    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int] = None,
    ) -> VSPSolution:
        self._start_timer()
        if not trips:
            return VSPSolution(algorithm=self.name)

        # 1. Agrupa
        has_depot = any(t.depot_id is not None for t in trips)
        if has_depot:
            groups = _group_by_depot(trips)
            logger.info(
                "regional_decomposition: %d trips → %d grupos por depot",
                len(trips),
                len(groups),
            )
        else:
            groups = _group_by_time_window(trips)
            logger.info(
                "regional_decomposition: %d trips → %d janelas temporais",
                len(trips),
                len(groups),
            )

        # Garante ao menos 1 grupo
        if not groups:
            groups = {"all": trips}

        # 2. Resolve em paralelo
        group_list = list(groups.values())
        n_groups = len(group_list)
        sub_budget = max(5.0, self._remaining_budget_s() / max(n_groups, 1))

        trip_dicts_list = [[_trip_to_dict(t) for t in g] for g in group_list]
        vt_dicts = [_vt_to_dict(vt) for vt in vehicle_types]

        args_list = [(tdicts, vt_dicts, self.sub_algorithm, self.vsp_params, sub_budget) for tdicts in trip_dicts_list]

        sub_solutions: List[VSPSolution] = [None] * n_groups  # type: ignore[list-item]

        if self.use_processes and n_groups > 1:
            try:
                with ProcessPoolExecutor(max_workers=self.max_workers) as pool:
                    futures = {pool.submit(_solve_group, args): idx for idx, args in enumerate(args_list)}
                    for fut in as_completed(futures):
                        idx = futures[fut]
                        try:
                            sub_solutions[idx] = fut.result()
                        except Exception as exc:
                            logger.error("Grupo %d falhou: %s", idx, exc)
                            # Fallback unitário
                            sub_solutions[idx] = VSPSolution(
                                blocks=[Block(id=i + 1, trips=[t]) for i, t in enumerate(group_list[idx])],
                                algorithm="fallback",
                            )
            except Exception as exc:
                # ProcessPool não disponível (ex: pytest com coverage) — sequencial
                logger.warning("ProcessPool indisponível, executando sequencialmente: %s", exc)
                for idx, args in enumerate(args_list):
                    sub_solutions[idx] = _solve_group(args)
        else:
            # Sequencial (grupos únicos ou use_processes=False)
            for idx, args in enumerate(args_list):
                sub_solutions[idx] = _solve_group(args)

        # 3. Mergea
        all_blocks: List[Block] = []
        block_id = 1
        total_iters = 0
        unassigned: List[Trip] = []

        for sol in sub_solutions:
            if sol is None:
                continue
            for block in sol.blocks:
                block.id = block_id
                all_blocks.append(block)
                block_id += 1
            unassigned.extend(sol.unassigned_trips)
            total_iters += sol.iterations or 0

        logger.info(
            "regional_decomposition: %d grupos → %d blocos, %d não atribuídas, %.1fs",
            n_groups,
            len(all_blocks),
            len(unassigned),
            self._elapsed(),
        )

        return VSPSolution(
            blocks=all_blocks,
            unassigned_trips=unassigned,
            algorithm=self.name,
            iterations=total_iters,
            elapsed_ms=self._elapsed_ms(),
        )

    def _remaining_budget_s(self) -> float:
        return max(0.0, float(self.time_budget_s) - self._elapsed())
