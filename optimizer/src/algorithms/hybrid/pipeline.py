"""
Pipeline Híbrido — Greedy → Local Search → Melhor Metaheurístico → ILP Polish.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from ...core.config import get_settings
from ...core.exceptions import InfeasibleProblemError
from ...domain.models import OptimizationResult, Trip, VehicleType
from ..base import BaseAlgorithm
from ..csp.greedy import GreedyCSP
from ..csp.set_partitioning import SetPartitioningCSP
from ..evaluator import CostEvaluator
from ..utils import preferred_pair_penalty, quick_cost_sorted
from ..vsp.genetic import GeneticVSP
from ..vsp.greedy import GreedyVSP, build_preferred_pairs
from ..vsp.mcnf import MCNFVSP
from ..vsp.simulated_annealing import SimulatedAnnealingVSP
from ..vsp.tabu_search import TabuSearchVSP

settings = get_settings()
logger = logging.getLogger(__name__)
evaluator = CostEvaluator()


class HybridPipeline(BaseAlgorithm):
    def __init__(self, time_budget_s: Optional[float] = None, cct_params=None, vsp_params=None):
        budget = time_budget_s or settings.hybrid_time_budget_seconds
        super().__init__(name="hybrid_pipeline", time_budget_s=budget)
        self.cct_params = cct_params or {}
        self.vsp_params = dict(vsp_params or {})

        # Propagar connection_tolerance para VSP se definido no CCT mas não no VSP
        if "connection_tolerance_minutes" not in self.vsp_params and self.cct_params.get("connection_tolerance_minutes"):
            self.vsp_params["connection_tolerance_minutes"] = self.cct_params["connection_tolerance_minutes"]

        # NÃO injetar crew_block_limit no VSP.
        # O limite de jornada do TRIPULANTE (CSP) não deve restringir o turno do VEÍCULO (VSP).
        # Veículos podem operar o dia inteiro; o CSP faz run-cutting e troca de operadores.

    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int] = None,
    ) -> OptimizationResult:
        import random
        import time
        # Se houver seed explícita, prioriza replay reprodutível; caso contrário mantém exploração estocástica.
        random_seed = self.vsp_params.get("random_seed")
        random.seed(int(random_seed) if random_seed is not None else int(time.time() * 1000))
        phase_timings_ms: dict[str, float] = {}
        
        # Removido: trips.sort(...) para não quebrar a vizinhança inicial do GreedyVSP.

        self._start_timer()
        if not trips:
            raise InfeasibleProblemError("No trips for HybridPipeline")

        budget = self.time_budget_s
        n = len(trips)

        # Pré-calcular preferred_pairs UMA vez — O(n²) evitado em cada _vsp_cost call
        min_layover = int(self.vsp_params.get("min_layover_minutes", 8) or 8)
        if bool(self.vsp_params.get("preserve_preferred_pairs", True)):
            cached_pairs = build_preferred_pairs(
                trips, min_layover,
                int(self.vsp_params.get("preferred_pair_window_minutes", 120) or 120),
            )
        else:
            cached_pairs = {}

        t_phase = time.perf_counter()
        # MCNF gera a baseline matemática perfeita (Bipartite Matching)
        best_vsp = MCNFVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id)
        phase_timings_ms["vsp_mcnf_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
        best_cost = _vsp_cost(best_vsp, self.vsp_params, cached_pairs)
        best_issues = _vsp_hard_issue_count(best_vsp, self.vsp_params)
        best_vehicles = len(best_vsp.blocks)
        strict_hard = bool(self.vsp_params.get("strict_hard_validation", self.cct_params.get("strict_hard_validation", False)))
        logger.info(f"[PIPELINE] mcnf baseline: {best_vehicles} veículos, cost={best_cost:.0f}, issues={best_issues}")

        elapsed = time.perf_counter() - self._start_time
        remaining_budget = max(1.0, budget - elapsed)

        def _is_better(sol, cost, issues):
            """Compara por: 1) menos hard issues, 2) menos veículos, 3) menor custo."""
            nonlocal best_issues, best_vehicles, best_cost
            n_veh = len(sol.blocks)
            acceptable = (issues == 0) if strict_hard else (issues <= best_issues)
            if not acceptable:
                return False
            if issues < best_issues:
                return True
            if issues == best_issues and n_veh < best_vehicles:
                return True
            if issues == best_issues and n_veh == best_vehicles and cost < best_cost:
                return True
            return False

        remaining_budget = max(1.0, budget - (time.perf_counter() - self._start_time))
        sa = SimulatedAnnealingVSP(vsp_params=self.vsp_params)
        sa_budget = remaining_budget * 0.35
        sa.time_budget_s = sa_budget
        t_phase = time.perf_counter()
        sa_sol = sa.solve(trips, vehicle_types, depot_id)
        phase_timings_ms["vsp_sa_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
        sa_elapsed_s = (sa_sol.elapsed_ms or 0) / 1000.0
        sa_saved = max(0, sa_budget - sa_elapsed_s)
        sa_cost = _vsp_cost(sa_sol, self.vsp_params, cached_pairs)
        sa_issues = _vsp_hard_issue_count(sa_sol, self.vsp_params)
        sa_iters = getattr(sa_sol, 'iterations', 0)
        sa_restarts = (sa_sol.meta or {}).get('restarts', 0)
        logger.info(f"[PIPELINE] SA: {len(sa_sol.blocks)} veículos, cost={sa_cost:.0f}, issues={sa_issues}, iters={sa_iters}, restarts={sa_restarts}, elapsed={sa_sol.elapsed_ms}ms")
        if _is_better(sa_sol, sa_cost, sa_issues):
            best_vsp = sa_sol
            best_cost = sa_cost
            best_issues = sa_issues
            best_vehicles = len(sa_sol.blocks)

        if self._check_timeout():
            return self._finalize(best_vsp, trips, vehicle_types)

        remaining_budget = max(1.0, budget - (time.perf_counter() - self._start_time))
        ts = TabuSearchVSP(vsp_params=self.vsp_params)
        ts_budget = remaining_budget * 0.35 + sa_saved  # Realocar tempo não usado pelo SA
        ts.time_budget_s = ts_budget
        t_phase = time.perf_counter()
        ts_sol = ts.solve(trips, vehicle_types, depot_id)
        phase_timings_ms["vsp_tabu_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
        ts_elapsed_s = (ts_sol.elapsed_ms or 0) / 1000.0
        ts_saved = max(0, ts_budget - ts_elapsed_s)
        ts_cost = _vsp_cost(ts_sol, self.vsp_params, cached_pairs)
        ts_issues = _vsp_hard_issue_count(ts_sol, self.vsp_params)
        ts_iters = getattr(ts_sol, 'iterations', 0)
        logger.info(f"[PIPELINE] Tabu: {len(ts_sol.blocks)} veículos, cost={ts_cost:.0f}, issues={ts_issues}, iters={ts_iters}, elapsed={ts_sol.elapsed_ms}ms")
        if _is_better(ts_sol, ts_cost, ts_issues):
            best_vsp = ts_sol
            best_cost = ts_cost
            best_issues = ts_issues
            best_vehicles = len(ts_sol.blocks)

        if self._check_timeout():
            return self._finalize(best_vsp, trips, vehicle_types)

        remaining_budget = max(1.0, budget - (time.perf_counter() - self._start_time))
        if n > 50:
            ga = GeneticVSP(vsp_params=self.vsp_params)
            ga.time_budget_s = remaining_budget * 0.20 + ts_saved  # Realocar tempo não usado pelo TS
            t_phase = time.perf_counter()
            ga_sol = ga.solve(trips, vehicle_types, depot_id)
            phase_timings_ms["vsp_genetic_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
            ga_cost = _vsp_cost(ga_sol, self.vsp_params, cached_pairs)
            ga_issues = _vsp_hard_issue_count(ga_sol, self.vsp_params)
            logger.info(f"[PIPELINE] Genetic: {len(ga_sol.blocks)} veículos, cost={ga_cost:.0f}, issues={ga_issues}")
            if _is_better(ga_sol, ga_cost, ga_issues):
                best_vsp = ga_sol
                best_cost = ga_cost
                best_issues = ga_issues
                best_vehicles = len(ga_sol.blocks)

        logger.info(f"[PIPELINE] Selecionado: {best_vsp.algorithm} com {best_vehicles} veículos")
        return self._finalize(best_vsp, trips, vehicle_types, phase_timings_ms)

    def _cct(self, key: str, default: int) -> int:
        return self.cct_params.get(key, default)

    def _solver_kwargs(self) -> dict:
        return {k: v for k, v in self.cct_params.items()}

    def _finalize(self, vsp_sol, trips, vehicle_types, phase_timings_ms=None) -> OptimizationResult:
        import time
        phase_timings_ms = dict(phase_timings_ms or {})
        vsp_sol.meta.setdefault(
            "objective",
            {
                "formula": "sum(f_k) + sum(c_ij * x_ij)",
                "fixed_vehicle_activation_cost": float(self.vsp_params.get("fixed_vehicle_activation_cost", 800.0)),
                "deadhead_cost_per_minute": float(self.vsp_params.get("deadhead_cost_per_minute", 1.0)),
                "idle_cost_per_minute": float(self.vsp_params.get("idle_cost_per_minute", 0.25)),
            },
        )
        if "crew_block_limit_minutes" in self.vsp_params:
            vsp_sol.meta.setdefault("crew_block_limit_minutes", int(self.vsp_params["crew_block_limit_minutes"]))
        vsp_sol.meta.setdefault("same_depot_required", bool(self.vsp_params.get("same_depot_required", False)))

        kwargs = self._solver_kwargs()
        if not vsp_sol.blocks:
            return OptimizationResult(
                vsp=vsp_sol,
                csp=GreedyCSP(vsp_params=self.vsp_params, **kwargs).solve([], trips),
                algorithm=self.name,  # type: ignore[arg-type]
                total_elapsed_ms=self._elapsed_ms(),
            )

        t_phase = time.perf_counter()
        csp_greedy = GreedyCSP(vsp_params=self.vsp_params, **kwargs).solve(vsp_sol.blocks, trips)
        phase_timings_ms["csp_greedy_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
        # Dar mais budget ao ILP para gerar colunas melhores
        ilp_budget = max(60.0, self.time_budget_s * 0.25)
        if not self._check_timeout():
            ilp = SetPartitioningCSP(vsp_params=self.vsp_params, **kwargs)
            ilp.time_budget_s = ilp_budget
            t_phase = time.perf_counter()
            csp_ilp = ilp.solve(vsp_sol.blocks, trips)
            phase_timings_ms["csp_set_partitioning_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
            ilp_better = csp_ilp.cct_violations < csp_greedy.cct_violations
            ilp_tie_and_not_worse_crew = (
                csp_ilp.cct_violations == csp_greedy.cct_violations
                and csp_ilp.num_crew <= csp_greedy.num_crew
            )
            # Also check short duty count: prefer solution with fewer shorts
            min_work = int(kwargs.get("min_work_minutes", 0))
            if min_work > 0 and csp_ilp.duties and (ilp_better or ilp_tie_and_not_worse_crew):
                greedy_shorts = sum(1 for d in csp_greedy.duties if d.work_time < min_work)
                ilp_shorts = sum(1 for d in csp_ilp.duties if d.work_time < min_work)
                if ilp_shorts > greedy_shorts:
                    logger.info(
                        "[PIPELINE] ILP has more short duties (%d vs %d), keeping greedy",
                        ilp_shorts, greedy_shorts,
                    )
                    csp_final = csp_greedy
                else:
                    csp_final = csp_ilp
            else:
                csp_final = csp_ilp if csp_ilp.duties and (ilp_better or ilp_tie_and_not_worse_crew) else csp_greedy
        else:
            csp_final = csp_greedy                
        from ..joint_opt import joint_duty_vehicle_swap
        t_phase = time.perf_counter()
        csp_final, vsp_sol = joint_duty_vehicle_swap(
            csp_final,
            vsp_sol,
            trips,
            self.cct_params,
            {**kwargs, "vsp_params": self.vsp_params},
        )
        phase_timings_ms["joint_swap_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
        result = OptimizationResult(
            vsp=vsp_sol,
            csp=csp_final,
            algorithm=self.name,  # type: ignore[arg-type]
            total_elapsed_ms=self._elapsed_ms(),
        )
        result.total_cost = evaluator.total_cost(result, vehicle_types)
        result.meta.setdefault("performance", {})
        result.meta["performance"].update(
            {
                "phase_timings_ms": phase_timings_ms,
                "input_trip_count": len(trips),
                "selected_vsp_algorithm": getattr(vsp_sol, "algorithm", "greedy_vsp"),
                "time_budget_s": self.time_budget_s,
            }
        )
        return result
        


def _vsp_cost(sol, vsp_params=None, cached_pairs=None) -> float:
    vsp_params = vsp_params or {}
    unassigned_penalty = len(getattr(sol, "unassigned_trips", [])) * 5000.0
    crew_block_limit = int(vsp_params.get("crew_block_limit_minutes", 0) or 0)
    long_block_penalty = 0.0
    infeasible_penalty = 0.0
    pair_penalty = 0.0
    if crew_block_limit > 0:
        for block in getattr(sol, "blocks", []):
            duration = int(block.end_time - block.start_time)
            if duration > crew_block_limit:
                long_block_penalty += (duration - crew_block_limit) * 200.0
    min_layover = int(vsp_params.get("min_layover_minutes", 8) or 8)
    if bool(vsp_params.get("preserve_preferred_pairs", True)):
        preferred_pairs = cached_pairs if cached_pairs is not None else build_preferred_pairs(
            [trip for block in getattr(sol, "blocks", []) for trip in getattr(block, "trips", [])],
            min_layover, int(vsp_params.get("preferred_pair_window_minutes", 120) or 120),
        )
        pair_break_penalty = float(vsp_params.get("pair_break_penalty", 1000.0))
        paired_trip_bonus = float(vsp_params.get("paired_trip_bonus", 40.0))
        hard_pairing_penalty = (
            float(
                vsp_params.get(
                    "hard_pairing_penalty",
                    max(pair_break_penalty * 10.0, float(vsp_params.get("fixed_vehicle_activation_cost", 800.0)) * 25.0),
                )
            )
            if bool(vsp_params.get("hard_pairing_vehicle_level", False))
            else 0.0
        )
    else:
        preferred_pairs = {}
        pair_break_penalty = 0.0
        paired_trip_bonus = 0.0
        hard_pairing_penalty = 0.0
    pair_penalty = preferred_pair_penalty(
        getattr(sol, "blocks", []),
        preferred_pairs,
        pair_break_penalty,
        paired_trip_bonus,
        hard_pairing_penalty,
    )
    for block in getattr(sol, "blocks", []):
        trips = list(getattr(block, "trips", []))
        for index in range(len(trips) - 1):
            current = trips[index]
            nxt = trips[index + 1]
            gap = nxt.start_time - current.end_time
            deadhead_need = int(current.deadhead_times.get(nxt.origin_id, 0))
            need = max(min_layover, deadhead_need)
            if gap < 0:
                infeasible_penalty += 20000.0 + abs(gap) * 500.0
            elif gap < need:
                infeasible_penalty += 15000.0 + (need - gap) * 400.0
    return quick_cost_sorted(sol.blocks) + unassigned_penalty + long_block_penalty + infeasible_penalty + pair_penalty


def _vsp_hard_issue_count(sol, vsp_params=None) -> int:
    vsp_params = vsp_params or {}
    min_layover = int(vsp_params.get("min_layover_minutes", 8) or 8)
    same_depot_required = bool(vsp_params.get("same_depot_required", False))
    issues = 0
    for block in getattr(sol, "blocks", []):
        trips = list(getattr(block, "trips", []))
        for index in range(len(trips) - 1):
            current = trips[index]
            nxt = trips[index + 1]
            gap = int(nxt.start_time - current.end_time)
            # Contiguous trip_group pair (ida/volta): no layover needed
            if (
                gap == 0
                and getattr(current, "trip_group_id", None) is not None
                and current.trip_group_id == getattr(nxt, "trip_group_id", None)
            ):
                continue
            deadhead_need = int(current.deadhead_times.get(nxt.origin_id, 0))
            need = max(min_layover, deadhead_need)
            if gap < need:
                issues += 1
        if same_depot_required and trips:
            if trips[0].depot_id is not None and trips[-1].depot_id is not None and trips[0].depot_id != trips[-1].depot_id:
                issues += 1
    return issues
