"""Dispatch de algoritmos VSP+CSP — extraído de optimizer_service.py para reduzir
o monolito de 4287 linhas (Sprint I).

Cada `_run_X` aqui é wrapper fino sobre o solver específico (GreedyVSP, MCNFVSP, etc).
A escolha do CSP (greedy_csp ou set_partitioning) é injetada via callable `csp_factory`,
mantendo OptimizerService responsável pela construção dos CSPs (que dependem de seu
estado interno como evaluator/validator).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from ..algorithms.hybrid.pipeline import HybridPipeline
from ..algorithms.integrated.joint_solver import JointSolver
from ..algorithms.integrated.vcsp_solver import VCSPJointSolver
from ..algorithms.vsp.assignment import AssignmentVSP
from ..algorithms.vsp.branch_and_price import BranchAndPrice
from ..algorithms.vsp.genetic import GeneticVSP
from ..algorithms.vsp.greedy import GreedyVSP
from ..algorithms.vsp.mcnf import MCNFVSP
from ..algorithms.vsp.simulated_annealing import SimulatedAnnealingVSP
from ..algorithms.vsp.tabu_search import TabuSearchVSP
from ..core.config import get_settings
from ..core.exceptions import InvalidAlgorithmError
from ..domain.interfaces import ICSPAlgorithm
from ..domain.models import AlgorithmType, OptimizationResult, Trip, VehicleType

logger = logging.getLogger(__name__)
settings = get_settings()

# Tipo: factory que constrói um CSP de jornadas (GreedyCSP) com os parâmetros dados.
CSPFactory = Callable[[Dict[str, Any], Dict[str, Any], Optional[Dict[str, Any]]], ICSPAlgorithm]
# Tipo: factory que constrói um CSP de set-covering ILP (SetPartitioningCSP).
SetCoveringFactory = Callable[[Dict[str, Any], Dict[str, Any]], ICSPAlgorithm]


def _run_greedy(
    *, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int],
    time_budget_s: Optional[float], cct_params: Dict[str, Any], vsp_params: Dict[str, Any],
    optimization_params: Optional[Dict[str, Any]], csp_factory: CSPFactory,
) -> OptimizationResult:
    csp = csp_factory(cct_params, vsp_params, optimization_params)
    vsp = GreedyVSP(vsp_params=vsp_params).solve(trips, vehicle_types, depot_id)
    return OptimizationResult(vsp=vsp, csp=csp.solve(vsp.blocks, trips))


def _run_genetic(
    *, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int],
    time_budget_s: float, cct_params: Dict[str, Any], vsp_params: Dict[str, Any],
    optimization_params: Optional[Dict[str, Any]], csp_factory: CSPFactory,
) -> OptimizationResult:
    csp = csp_factory(cct_params, vsp_params, optimization_params)
    ga = GeneticVSP(vsp_params=vsp_params)
    ga.time_budget_s = time_budget_s
    vsp = ga.solve(trips, vehicle_types, depot_id)
    return OptimizationResult(vsp=vsp, csp=csp.solve(vsp.blocks, trips))


def _run_sa(
    *, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int],
    time_budget_s: float, cct_params: Dict[str, Any], vsp_params: Dict[str, Any],
    optimization_params: Optional[Dict[str, Any]], csp_factory: CSPFactory,
) -> OptimizationResult:
    csp = csp_factory(cct_params, vsp_params, optimization_params)
    sa = SimulatedAnnealingVSP(vsp_params=vsp_params)
    sa.time_budget_s = time_budget_s
    vsp = sa.solve(trips, vehicle_types, depot_id)
    return OptimizationResult(vsp=vsp, csp=csp.solve(vsp.blocks, trips))


def _run_ts(
    *, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int],
    time_budget_s: float, cct_params: Dict[str, Any], vsp_params: Dict[str, Any],
    optimization_params: Optional[Dict[str, Any]], csp_factory: CSPFactory,
) -> OptimizationResult:
    csp = csp_factory(cct_params, vsp_params, optimization_params)
    ts = TabuSearchVSP(vsp_params=vsp_params)
    ts.time_budget_s = time_budget_s
    vsp = ts.solve(trips, vehicle_types, depot_id)
    return OptimizationResult(vsp=vsp, csp=csp.solve(vsp.blocks, trips))


def _run_sp(
    *, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int],
    time_budget_s: float, cct_params: Dict[str, Any], vsp_params: Dict[str, Any],
    optimization_params: Optional[Dict[str, Any]],
    csp_factory: CSPFactory, set_covering_factory: SetCoveringFactory,
) -> OptimizationResult:
    vsp = GreedyVSP(vsp_params=vsp_params).solve(trips, vehicle_types, depot_id)
    ilp = set_covering_factory(cct_params, vsp_params)
    ilp.time_budget_s = time_budget_s
    return OptimizationResult(vsp=vsp, csp=ilp.solve(vsp.blocks, trips))


def _run_mcnf(
    *, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int],
    time_budget_s: float, cct_params: Dict[str, Any], vsp_params: Dict[str, Any],
    optimization_params: Optional[Dict[str, Any]], csp_factory: CSPFactory,
) -> OptimizationResult:
    csp = csp_factory(cct_params, vsp_params, optimization_params)
    mcnf = MCNFVSP(vsp_params=vsp_params)
    mcnf.time_budget_s = time_budget_s
    vsp = mcnf.solve(trips, vehicle_types, depot_id)
    return OptimizationResult(vsp=vsp, csp=csp.solve(vsp.blocks, trips))


def _run_joint(
    *, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int],
    time_budget_s: Optional[float], cct_params: Dict[str, Any], vsp_params: Dict[str, Any],
    optimization_params: Optional[Dict[str, Any]],
) -> OptimizationResult:
    budget = time_budget_s or vsp_params.get("time_budget_s", settings.hybrid_time_budget_seconds)
    return JointSolver(time_budget_s=budget, cct_params=cct_params, vsp_params=vsp_params).solve(
        trips, vehicle_types, depot_id
    )


def _run_hybrid(
    *, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int],
    time_budget_s: Optional[float], cct_params: Dict[str, Any], vsp_params: Dict[str, Any],
    optimization_params: Optional[Dict[str, Any]],
) -> OptimizationResult:
    budget = time_budget_s or vsp_params.get("time_budget_s", settings.hybrid_time_budget_seconds)
    full_cct_params = {**cct_params, **(optimization_params or {})}
    full_vsp_params = {**vsp_params}
    if optimization_params and optimization_params.get("ilp_timeout_seconds") is not None:
        full_vsp_params.setdefault("ilp_timeout_seconds", optimization_params["ilp_timeout_seconds"])
    return HybridPipeline(time_budget_s=budget, cct_params=full_cct_params, vsp_params=full_vsp_params).solve(
        trips, vehicle_types, depot_id
    )


def _run_vcsp_pulp(
    *, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int],
    time_budget_s: float, cct_params: Dict[str, Any], vsp_params: Dict[str, Any],
    optimization_params: Optional[Dict[str, Any]],
) -> OptimizationResult:
    return VCSPJointSolver(
        time_budget_s=time_budget_s,
        cct_params={**cct_params, **(optimization_params or {})},
        vsp_params=vsp_params,
    ).solve(trips, vehicle_types, depot_id)


def _run_assignment_vsp(
    *, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int],
    time_budget_s: float, cct_params: Dict[str, Any], vsp_params: Dict[str, Any],
    optimization_params: Optional[Dict[str, Any]], csp_factory: CSPFactory,
) -> OptimizationResult:
    csp = csp_factory(cct_params, vsp_params, optimization_params)
    vsp = AssignmentVSP(vsp_params=vsp_params)
    vsp.time_budget_s = time_budget_s
    vsp_sol = vsp.solve(trips, vehicle_types, depot_id)
    return OptimizationResult(vsp=vsp_sol, csp=csp.solve(vsp_sol.blocks, trips))


def _run_branch_and_price(
    *, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int],
    time_budget_s: float, cct_params: Dict[str, Any], vsp_params: Dict[str, Any],
    optimization_params: Optional[Dict[str, Any]], csp_factory: CSPFactory,
) -> OptimizationResult:
    csp = csp_factory(cct_params, vsp_params, optimization_params)
    bp = BranchAndPrice(vsp_params=vsp_params)
    bp.time_budget_s = time_budget_s
    vsp_sol = bp.solve(trips, vehicle_types, depot_id)
    return OptimizationResult(vsp=vsp_sol, csp=csp.solve(vsp_sol.blocks, trips))


def dispatch_algorithm(
    algorithm: AlgorithmType,
    *,
    trips: List[Trip],
    vehicle_types: List[VehicleType],
    depot_id: Optional[int],
    cct_params: Dict[str, Any],
    vsp_params: Dict[str, Any],
    optimization_params: Optional[Dict[str, Any]],
    effective_time_budget_s: float,
    csp_factory: CSPFactory,
    set_covering_factory: SetCoveringFactory,
) -> OptimizationResult:
    """Despacha para o solver apropriado baseado em `algorithm`.

    `csp_factory` e `set_covering_factory` são injetados pelo OptimizerService
    porque eles dependem de seu estado (evaluator, validator).

    COMPORTAMENTO MULTI-DEPOT:
      - `same_depot_required=True` é suportado em todos os algoritmos como filtro
        hard: trips de depots diferentes nunca são agrupadas no mesmo bloco.
      - Otimização de custo entre garagens (pull-out/pull-in multi-depot) é
        exclusiva do MCNF. Para redes com múltiplas garagens e requisito de
        minimizar deadhead entre elas, use AlgorithmType.MCNF.
      - Algoritmos greedy, SA, tabu, genetic tratam depot_id como filtro único;
        trips com depot_id diferente do bloco são descartadas (when same_depot_required=True).
    """
    # Unifica parâmetros dinâmicos de otimização na base do VSP e CCT
    if optimization_params:
        vsp_params.update(optimization_params)
        cct_params.update(optimization_params)

    # Guardrail multi-depot: se há trips de depots distintos e same_depot_required=True
    # com algoritmo não-MCNF, alertar que custo cross-depot não é otimizado.
    if vsp_params.get("same_depot_required") and algorithm not in (
        AlgorithmType.MCNF,
        AlgorithmType.HYBRID_PIPELINE,
        AlgorithmType.JOINT_SOLVER,
    ):
        unique_depots = {t.depot_id for t in trips if t.depot_id is not None}
        if len(unique_depots) > 1:
            logger.warning(
                "[AlgorithmDispatcher] MULTI_DEPOT_LIMITED: %d depots distintos detectados "
                "com algorithm=%s. same_depot_required aplicado como filtro hard. "
                "Para otimização de custo entre garagens use algorithm=mcnf.",
                len(unique_depots),
                algorithm.value if hasattr(algorithm, "value") else algorithm,
            )

    logger.info(
        "[AlgorithmDispatcher] algorithm=%s trips=%d budget=%ss",
        algorithm.value if hasattr(algorithm, "value") else algorithm,
        len(trips),
        effective_time_budget_s,
    )

    common_kwargs = dict(
        trips=trips, vehicle_types=vehicle_types, depot_id=depot_id,
        time_budget_s=effective_time_budget_s,
        cct_params=cct_params, vsp_params=vsp_params,
        optimization_params=optimization_params,
    )

    if algorithm == AlgorithmType.GREEDY:
        return _run_greedy(**common_kwargs, csp_factory=csp_factory)
    if algorithm == AlgorithmType.GENETIC:
        return _run_genetic(**common_kwargs, csp_factory=csp_factory)
    if algorithm == AlgorithmType.SIMULATED_ANNEALING:
        return _run_sa(**common_kwargs, csp_factory=csp_factory)
    if algorithm == AlgorithmType.TABU_SEARCH:
        return _run_ts(**common_kwargs, csp_factory=csp_factory)
    if algorithm in (AlgorithmType.SET_PARTITIONING, AlgorithmType.CP_SAT):
        return _run_sp(**common_kwargs, csp_factory=csp_factory, set_covering_factory=set_covering_factory)
    if algorithm == AlgorithmType.MCNF:
        return _run_mcnf(**common_kwargs, csp_factory=csp_factory)
    if algorithm == AlgorithmType.JOINT_SOLVER:
        return _run_joint(**common_kwargs)
    if algorithm == AlgorithmType.HYBRID_PIPELINE:
        return _run_hybrid(**common_kwargs)
    if algorithm == AlgorithmType.VCSP_PULP:
        return _run_vcsp_pulp(**common_kwargs)
    if algorithm == AlgorithmType.ASSIGNMENT_VSP:
        return _run_assignment_vsp(**common_kwargs, csp_factory=csp_factory)
    if algorithm == AlgorithmType.BRANCH_AND_PRICE:
        return _run_branch_and_price(**common_kwargs, csp_factory=csp_factory)

    raise InvalidAlgorithmError(str(algorithm))
