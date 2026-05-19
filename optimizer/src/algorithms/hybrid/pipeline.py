"""
Pipeline Híbrido — Greedy → Local Search → Melhor Metaheurístico → ILP Polish.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import List, Optional

from ...core.config import get_settings
from ...core.exceptions import InfeasibleProblemError
from ...domain.models import OptimizationResult, Trip, VehicleType
from ..base import BaseAlgorithm
from ..csp.greedy import GreedyCSP
from ..csp.cp_sat_csp import CPSatCSP
from ..csp.set_partitioning import SetPartitioningCSP
from ..evaluator import CostEvaluator
from ..vsp.genetic import GeneticVSP
from ..vsp.greedy import GreedyVSP, build_preferred_pairs
from ..vsp.mcnf import MCNFVSP
from ..vsp.simulated_annealing import SimulatedAnnealingVSP
from ..vsp.tabu_search import TabuSearchVSP
from ..utils import (
    preferred_pair_penalty,
    quick_cost_sorted,
    ConstraintEngine,
)

settings = get_settings()
logger = logging.getLogger(__name__)
evaluator = CostEvaluator()
MIN_REMAINING_BUDGET_FOR_ILP_S = 5.0
# CP-SAT handles significantly more than CBC/PuLP — limits raised accordingly.
# Trip limit raised to 1500 so CP-SAT ILP polish runs at 1000v (194 greedy blocks,
# problem size is determined by blocks not trips — the old 600-trip limit was overly conservative).
# Auditoria 2026-05-17: limites originais (220/180) eram conservadores demais.
# Para 500 trips o SA/Tabu termina em ~30-45s com time_budget de 20s no pipeline,
# então faz sentido permitir até 500 trips com time budget adequado. Acima disso,
# metaheurísticas geram pouco ganho marginal pelo tempo gasto.
DEFAULT_MAX_CSP_ILP_TRIPS = 1500
DEFAULT_MAX_CSP_ILP_BLOCKS = 450
DEFAULT_MAX_VSP_METAHEURISTIC_TRIPS = 220
DEFAULT_MAX_VSP_METAHEURISTIC_BLOCKS = 180


class HybridPipeline(BaseAlgorithm):
    def __init__(self, time_budget_s: Optional[float] = None, cct_params=None, vsp_params=None):
        budget = time_budget_s or settings.hybrid_time_budget_seconds
        super().__init__(name="hybrid_pipeline", time_budget_s=budget)
        self.cct_params = cct_params or {}
        self.vsp_params = dict(vsp_params or {})

        # Alinha parâmetros operacionais compartilhados entre CCT e VSP.
        passthrough_fields = (
            "min_layover_minutes",
            "min_break_minutes",
            "enforce_min_interval",
            "connection_tolerance_minutes",
            "pullout_minutes",
            "pullback_minutes",
            "strict_hard_validation",
            "meal_break_minutes",
            "mandatory_break_after_minutes",
        )
        for field in passthrough_fields:
            if field not in self.vsp_params and self.cct_params.get(field) is not None:
                self.vsp_params[field] = self.cct_params[field]

        if (
            "same_depot_required" not in self.vsp_params
            and self.cct_params.get("enforce_same_depot_start_end") is not None
        ):
            self.vsp_params["same_depot_required"] = bool(self.cct_params.get("enforce_same_depot_start_end"))

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

        best_vsp = None
        self._start_timer()  # único ponto de início — elapsed medido a partir daqui
        # Se houver seed explícita, prioriza replay reprodutível; caso contrário mantém exploração estocástica.
        random_seed = self.vsp_params.get("random_seed")
        random.seed(int(random_seed) if random_seed is not None else int(time.time() * 1000))
        phase_timings_ms: dict[str, float] = {}
        if not trips:
            raise InfeasibleProblemError("No trips for HybridPipeline")

        budget = self.time_budget_s
        n = len(trips)

        # Fast path: AssignmentVSP para grandes datasets ou preferência explícita
        use_assignment = self.vsp_params.get("algorithm_preference") == "assignment_vsp" or n > 5000
        if use_assignment:
            from ..vsp.assignment import AssignmentVSP
            from ..joint_opt_boundary import stitch_chunk_boundaries

            t_phase = time.perf_counter()
            best_vsp = AssignmentVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id)
            phase_timings_ms["vsp_assignment_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
            best_vsp = stitch_chunk_boundaries(best_vsp, self.vsp_params)
            logger.info("[PIPELINE] AssignmentVSP: %d blocos → _finalize", len(best_vsp.blocks))
            return self._finalize(best_vsp, trips, vehicle_types, phase_timings_ms)

        # Pré-calcular preferred_pairs UMA vez — O(n²) evitado em cada _vsp_cost call
        min_layover = int(self.vsp_params.get("min_layover_minutes", 8) or 8)
        if bool(self.vsp_params.get("preserve_preferred_pairs", True)):
            cached_pairs = build_preferred_pairs(
                trips,
                min_layover,
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
        strict_hard = bool(
            self.vsp_params.get("strict_hard_validation", self.cct_params.get("strict_hard_validation", False))
        )
        logger.info(f"[PIPELINE] mcnf baseline: {best_vehicles} veículos, cost={best_cost:.0f}, issues={best_issues}")

        # [Fast Path] Para datasets pequenos, se a baseline for perfeita, encerramos imediatamente.
        if len(trips) <= 10 and best_issues == 0:
            logger.info("[PIPELINE] Solução ideal encontrada para dataset reduzido. Finalizando.")
            return self._finalize(best_vsp, trips, vehicle_types, phase_timings_ms)

        max_metaheuristic_trips = int(
            self.vsp_params.get("max_vsp_metaheuristic_trips", DEFAULT_MAX_VSP_METAHEURISTIC_TRIPS)
            or DEFAULT_MAX_VSP_METAHEURISTIC_TRIPS
        )
        max_metaheuristic_blocks = int(
            self.vsp_params.get("max_vsp_metaheuristic_blocks", DEFAULT_MAX_VSP_METAHEURISTIC_BLOCKS)
            or DEFAULT_MAX_VSP_METAHEURISTIC_BLOCKS
        )
        force_metaheuristics = bool(self.vsp_params.get("force_vsp_metaheuristics", False))
        should_skip_metaheuristics = not force_metaheuristics and (
            n > max_metaheuristic_trips or len(best_vsp.blocks) > max_metaheuristic_blocks
        )
        if should_skip_metaheuristics:
            logger.info(
                "[PIPELINE] Skipping VSP metaheuristics: trips=%d blocks=%d limits=(%d,%d)",
                n,
                len(best_vsp.blocks),
                max_metaheuristic_trips,
                max_metaheuristic_blocks,
            )
            # A grandes escalas (n≥500), MCNF fragmenta excessivamente comparado ao greedy.
            # Abaixo de 500 trips, MCNF e greedy produzem blocos similares; mantemos MCNF
            # pois o greedy pode criar blocos de longa duração em horários pico (manhã+tarde).
            mcnf_block_count = best_vehicles
            if n >= 500:
                t_phase = time.perf_counter()
                greedy_vsp = GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id)
                phase_timings_ms["vsp_greedy_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
                greedy_issues = _vsp_hard_issue_count(greedy_vsp, self.vsp_params)
                greedy_cost = _vsp_cost(greedy_vsp, self.vsp_params, cached_pairs)
                greedy_acceptable = (greedy_issues == 0) if strict_hard else (greedy_issues <= best_issues)
                greedy_better = greedy_acceptable and (
                    greedy_issues < best_issues
                    or (greedy_issues == best_issues and len(greedy_vsp.blocks) < best_vehicles)
                    or (
                        greedy_issues == best_issues
                        and len(greedy_vsp.blocks) == best_vehicles
                        and greedy_cost < best_cost
                    )
                )
                logger.info(
                    "[PIPELINE] scale greedy: %d blocks cost=%.0f issues=%d (mcnf: %d blocks) → %s",
                    len(greedy_vsp.blocks),
                    greedy_cost,
                    greedy_issues,
                    mcnf_block_count,
                    "greedy selected" if greedy_better else "mcnf kept",
                )
                if greedy_better:
                    best_vsp = greedy_vsp
                    best_vehicles = len(greedy_vsp.blocks)
            best_vsp.meta.setdefault("performance", {})
            best_vsp.meta["performance"]["vsp_metaheuristics_skipped"] = {
                "reason": "instance_scale_guard",
                "trip_count": n,
                "block_count": best_vehicles,
                "max_trips": max_metaheuristic_trips,
                "max_blocks": max_metaheuristic_blocks,
                "selected_vsp_algorithm": getattr(best_vsp, "algorithm", "greedy_vsp"),
                "mcnf_blocks": mcnf_block_count,
            }
            return self._finalize(best_vsp, trips, vehicle_types, phase_timings_ms)

        elapsed = time.perf_counter() - self._start_time
        remaining_budget = max(1.0, budget - elapsed)

        def _is_better(sol, cost, issues):
            """Compara por: 1) menos hard issues, 2) menos veículos, 3) menor custo."""
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
        sa_runs = 2 if bool(self.vsp_params.get("preserve_preferred_pairs", True)) and n >= 100 else 1
        sa_budget_total = remaining_budget * 0.35
        sa_budget_each = max(1.0, sa_budget_total / sa_runs)
        sa_seed_base = int(random_seed) if random_seed is not None else int(time.time() * 1000)
        total_sa_elapsed = 0.0
        sa_saved = 0.0

        for sa_run in range(sa_runs):
            sa_params = dict(self.vsp_params)
            sa_params["random_seed"] = sa_seed_base + sa_run
            sa = SimulatedAnnealingVSP(vsp_params=sa_params)
            sa.time_budget_s = sa_budget_each
            t_phase = time.perf_counter()
            sa_sol = sa.solve(trips, vehicle_types, depot_id)
            phase_timings_ms.setdefault("vsp_sa_ms", 0.0)
            phase_timings_ms["vsp_sa_ms"] += round((time.perf_counter() - t_phase) * 1000, 2)
            sa_elapsed_s = (sa_sol.elapsed_ms or 0) / 1000.0
            total_sa_elapsed += sa_elapsed_s
            sa_cost = _vsp_cost(sa_sol, self.vsp_params, cached_pairs)
            sa_issues = _vsp_hard_issue_count(sa_sol, self.vsp_params)
            sa_iters = getattr(sa_sol, "iterations", 0)
            sa_restarts = (sa_sol.meta or {}).get("restarts", 0)
            logger.info(
                f"[PIPELINE] SA[{sa_run + 1}/{sa_runs}]: {len(sa_sol.blocks)} veículos, "
                f"cost={sa_cost:.0f}, issues={sa_issues}, iters={sa_iters}, restarts={sa_restarts}, "
                f"elapsed={sa_sol.elapsed_ms}ms"
            )
            if _is_better(sa_sol, sa_cost, sa_issues):
                best_vsp = sa_sol
                best_cost = sa_cost
                best_issues = sa_issues
                best_vehicles = len(sa_sol.blocks)

        sa_saved = max(0.0, sa_budget_total - total_sa_elapsed)

        # PERF: Early stop se já temos solução perfeita sem out-of-budget
        if best_issues == 0 and self._check_timeout():
            return self._finalize(best_vsp, trips, vehicle_types)

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
        ts_iters = getattr(ts_sol, "iterations", 0)
        logger.info(
            f"[PIPELINE] Tabu: {len(ts_sol.blocks)} veículos, cost={ts_cost:.0f}, issues={ts_issues}, iters={ts_iters}, elapsed={ts_sol.elapsed_ms}ms"  # noqa: E501
        )
        if _is_better(ts_sol, ts_cost, ts_issues):
            best_vsp = ts_sol
            best_cost = ts_cost
            best_issues = ts_issues
            best_vehicles = len(ts_sol.blocks)

        if self._check_timeout():
            return self._finalize(best_vsp, trips, vehicle_types)

        # PERF 2.4: Early stop — se issues==0 e Tabu já não melhorou
        if best_issues == 0 and ts_issues == 0 and abs(ts_cost - best_cost) / max(1.0, best_cost) < 0.01:
            logger.info("[PIPELINE] Early stop: solução estável, pulando Genetic")
            return self._finalize(best_vsp, trips, vehicle_types, phase_timings_ms)

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
        from ...domain.models import VSPSolution

        phase_timings_ms = dict(phase_timings_ms or {})

        if vsp_sol is None:
            vsp_sol = VSPSolution(algorithm=self.name, meta={})

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

        if len(vsp_sol.blocks) > 1500:
            from ..csp.chunked_orchestrator import ChunkedCSPOrchestrator

            t_phase = time.perf_counter()
            csp_chunked = ChunkedCSPOrchestrator(
                vsp_params=self.vsp_params,
                chunk_threshold=1500,
                **kwargs,
            ).solve(vsp_sol.blocks, trips)
            phase_timings_ms["csp_chunked_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
            t_phase = time.perf_counter()
            csp_greedy = GreedyCSP(vsp_params=self.vsp_params, **kwargs).solve(vsp_sol.blocks, trips)
            phase_timings_ms["csp_greedy_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)

            # Capturar baseline para benchmark de qualidade (Antes do Polish/JointSwap)
            from ..evaluator import CostEvaluator

            evaluator = CostEvaluator()
            chunked_key = (
                csp_chunked.cct_violations,
                len(csp_chunked.uncovered_blocks or []),
                csp_chunked.num_crew,
                evaluator.total_cost(
                    OptimizationResult(vsp=vsp_sol, csp=csp_chunked, algorithm="candidate"), vehicle_types
                ),
            )
            greedy_key = (
                csp_greedy.cct_violations,
                len(csp_greedy.uncovered_blocks or []),
                csp_greedy.num_crew,
                evaluator.total_cost(
                    OptimizationResult(vsp=vsp_sol, csp=csp_greedy, algorithm="candidate"), vehicle_types
                ),
            )
            csp_final = csp_chunked if chunked_key <= greedy_key else csp_greedy
            baseline_csp = csp_final
            csp_final.meta.setdefault("selection", {})
            csp_final.meta["selection"].update(
                {
                    "selected_by": "hybrid_pipeline",
                    "selected_csp": getattr(csp_final, "algorithm", ""),
                    "chunked_score": chunked_key,
                    "greedy_score": greedy_key,
                }
            )
            baseline_result = OptimizationResult(vsp=vsp_sol, csp=csp_final, algorithm="baseline")
            baseline_metrics = {
                "vehicles": len(vsp_sol.blocks),
                "crew": csp_final.num_crew,
                "violations": csp_final.cct_violations,
                "total_cost": round(evaluator.total_cost(baseline_result, vehicle_types), 2),
            }

            remaining_budget_s = max(0.0, self.time_budget_s - self._elapsed())
            max_ilp_trips = int(
                self.vsp_params.get("max_csp_ilp_trips", DEFAULT_MAX_CSP_ILP_TRIPS) or DEFAULT_MAX_CSP_ILP_TRIPS
            )
            max_ilp_blocks = int(
                self.vsp_params.get("max_csp_ilp_blocks", DEFAULT_MAX_CSP_ILP_BLOCKS) or DEFAULT_MAX_CSP_ILP_BLOCKS
            )
            should_run_ilp = (
                not self._check_timeout()
                and remaining_budget_s >= MIN_REMAINING_BUDGET_FOR_ILP_S
                and len(trips) <= max_ilp_trips
                and len(vsp_sol.blocks) <= max_ilp_blocks
            )
            if should_run_ilp:
                # O polish exato só pode consumir o orçamento restante.
                ilp_budget = max(1.0, min(remaining_budget_s, self.time_budget_s * 0.25))
                # Fase 3: Tentar CP-SAT primeiro (mais rápido em lógica pura), fallback para CBC
                csp_ilp = None
                ilp_solver_used = "none"
                t_phase = time.perf_counter()
                try:
                    ilp = CPSatCSP(vsp_params=self.vsp_params, **kwargs)
                    ilp.time_budget_s = ilp_budget
                    csp_ilp = ilp.solve(vsp_sol.blocks, trips)
                    # Fase 1: Rescoring com evaluator
                    csp_ilp = self._rescore_csp_solution(csp_ilp)
                    ilp_solver_used = "cpsat"
                    logger.info("[PIPELINE] CP-SAT large-scale polish OK")
                except Exception as e:
                    logger.warning(f"[PIPELINE] CP-SAT falhou em escala grande: {e}. Tentando CBC SetPartitioningCSP...")
                    try:
                        ilp = SetPartitioningCSP(vsp_params=self.vsp_params, **kwargs)
                        ilp.time_budget_s = ilp_budget
                        csp_ilp = ilp.solve(vsp_sol.blocks, trips)
                        # Fase 1: Rescoring com evaluator
                        csp_ilp = self._rescore_csp_solution(csp_ilp)
                        ilp_solver_used = "cbc"
                    except Exception as e2:
                        logger.error(f"[PIPELINE] Falha crítica em ILP solver: {e2}. Mantendo baseline CSP.")
                        csp_ilp = baseline_csp

                if csp_ilp is None:
                    csp_ilp = baseline_csp
                phase_timings_ms[f"csp_{ilp_solver_used}_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
                ilp_better = (
                    csp_ilp.cct_violations,
                    len(csp_ilp.uncovered_blocks or []),
                    csp_ilp.num_crew,
                ) < (
                    baseline_csp.cct_violations,
                    len(baseline_csp.uncovered_blocks or []),
                    baseline_csp.num_crew,
                )
                ilp_tie_and_not_worse_crew = (
                    csp_ilp.cct_violations == baseline_csp.cct_violations
                    and len(csp_ilp.uncovered_blocks or []) <= len(baseline_csp.uncovered_blocks or [])
                    and csp_ilp.num_crew <= baseline_csp.num_crew
                )
                min_work = int(kwargs.get("min_work_minutes", 0))
                if min_work > 0 and csp_ilp.duties and (ilp_better or ilp_tie_and_not_worse_crew):
                    baseline_shorts = sum(1 for d in baseline_csp.duties if d.work_time < min_work)
                    ilp_shorts = sum(1 for d in csp_ilp.duties if d.work_time < min_work)
                    if ilp_shorts > baseline_shorts:
                        logger.info(
                            "[PIPELINE] ILP has more short duties (%d vs %d), keeping selected CSP baseline",
                            ilp_shorts,
                            baseline_shorts,
                        )
                        csp_final = baseline_csp
                    else:
                        csp_final = csp_ilp
                else:
                    csp_final = (
                        csp_ilp if csp_ilp.duties and (ilp_better or ilp_tie_and_not_worse_crew) else baseline_csp
                    )
            else:
                logger.info(
                    "[PIPELINE] Skipping CSP ILP polish: remaining_budget=%.2fs trips=%d blocks=%d",
                    remaining_budget_s,
                    len(trips),
                    len(vsp_sol.blocks),
                )
        else:
            # Escala normal (<= 1500 blocos): greedy CSP + CP-SAT ILP polish
            t_phase = time.perf_counter()
            csp_greedy = GreedyCSP(vsp_params=self.vsp_params, **kwargs).solve(vsp_sol.blocks, trips)
            # Fase 1: Rescoring com evaluator
            csp_greedy = self._rescore_csp_solution(csp_greedy)
            phase_timings_ms["csp_greedy_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
            csp_final = csp_greedy

            # Baseline para benchmark de qualidade
            from ..evaluator import CostEvaluator

            evaluator = CostEvaluator()
            baseline_result = OptimizationResult(vsp=vsp_sol, csp=csp_greedy, algorithm="baseline")
            baseline_metrics = {
                "vehicles": len(vsp_sol.blocks),
                "crew": csp_greedy.num_crew,
                "violations": csp_greedy.cct_violations,
                "total_cost": round(evaluator.total_cost(baseline_result, vehicle_types), 2),
            }

            # CP-SAT ILP polish: melhora run-cutting dentro do orçamento restante.
            # Antes só existia no branch >1500 blocos (onde nunca executava por limites conflitantes).
            remaining_budget_s = max(0.0, self.time_budget_s - self._elapsed())
            max_ilp_trips = int(
                self.vsp_params.get("max_csp_ilp_trips", DEFAULT_MAX_CSP_ILP_TRIPS) or DEFAULT_MAX_CSP_ILP_TRIPS
            )
            max_ilp_blocks = int(
                self.vsp_params.get("max_csp_ilp_blocks", DEFAULT_MAX_CSP_ILP_BLOCKS) or DEFAULT_MAX_CSP_ILP_BLOCKS
            )
            should_run_ilp = (
                not self._check_timeout()
                and remaining_budget_s >= MIN_REMAINING_BUDGET_FOR_ILP_S
                and len(trips) <= max_ilp_trips
                and len(vsp_sol.blocks) <= max_ilp_blocks
            )
            if should_run_ilp:
                ilp_budget = max(1.0, min(remaining_budget_s * 0.5, 90.0))
                ilp = CPSatCSP(vsp_params=self.vsp_params, **kwargs)
                ilp.time_budget_s = ilp_budget
                t_phase = time.perf_counter()
                try:
                    csp_ilp = ilp.solve(vsp_sol.blocks, trips)
                    # Fase 1: Rescoring com evaluator
                    csp_ilp = self._rescore_csp_solution(csp_ilp)
                    phase_timings_ms["csp_cpsat_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
                    ilp_better = csp_ilp.duties and (
                        csp_ilp.cct_violations,
                        len(csp_ilp.uncovered_blocks or []),
                        csp_ilp.num_crew,
                    ) <= (csp_greedy.cct_violations, len(csp_greedy.uncovered_blocks or []), csp_greedy.num_crew)
                    if ilp_better:
                        logger.info(
                            "[PIPELINE] CP-SAT polish: crew %d→%d violations %d→%d uncovered %d→%d",
                            csp_greedy.num_crew,
                            csp_ilp.num_crew,
                            csp_greedy.cct_violations,
                            csp_ilp.cct_violations,
                            len(csp_greedy.uncovered_blocks or []),
                            len(csp_ilp.uncovered_blocks or []),
                        )
                        csp_final = csp_ilp
                    else:
                        logger.info("[PIPELINE] CP-SAT polish not better than greedy CSP — keeping greedy")
                except Exception as e:
                    logger.error("[PIPELINE] CP-SAT polish failed: %s — keeping greedy CSP", e)
                    phase_timings_ms["csp_cpsat_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
            else:
                logger.info(
                    "[PIPELINE] Skipping CP-SAT polish: remaining=%.1fs trips=%d blocks=%d limits=(%d,%d)",
                    remaining_budget_s,
                    len(trips),
                    len(vsp_sol.blocks),
                    max_ilp_trips,
                    max_ilp_blocks,
                )
        from ..joint_opt import joint_duty_vehicle_swap

        t_phase = time.perf_counter()
        try:
            csp_final, vsp_sol = joint_duty_vehicle_swap(
                csp_final,
                vsp_sol,
                trips,
                vehicle_types,
                self.cct_params,
                {**kwargs, "vsp_params": self.vsp_params},
            )
        except (IndexError, KeyError) as exc:
            logger.warning(
                "[PIPELINE] joint_duty_vehicle_swap falhou (%s: %s) — mantendo CSP/VSP do pré-swap",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
        phase_timings_ms["joint_swap_ms"] = round((time.perf_counter() - t_phase) * 1000, 2)
        # ── Benchmark final e decisão de regressão ──────────────────────────
        if "baseline_metrics" in locals() and baseline_metrics:
            from ..evaluator import CostEvaluator

            evaluator = CostEvaluator()
            current_result = OptimizationResult(vsp=vsp_sol, csp=csp_final)
            final_cost = evaluator.total_cost(current_result, vehicle_types)
            baseline_cost = baseline_metrics["total_cost"]

            if final_cost > baseline_cost:
                logger.warning(
                    "[PIPELINE] Pós-otimização piorou o custo total (%.2f > %.2f). Revertendo para baseline.",
                    final_cost,
                    baseline_cost,
                )
                vsp_sol = baseline_result.vsp
                csp_final = baseline_result.csp

        # ── Benchmarking Avançado (Recalculado após reversão se necessário) ──
        total_gaps = []
        for b in vsp_sol.blocks:
            if len(b.trips) > 1:
                total_gaps.extend([b.trips[i + 1].start_time - b.trips[i].end_time for i in range(len(b.trips) - 1)])

        block_sizes = [len(b.trips) for b in vsp_sol.blocks]
        advanced_stats = {
            "gap_stats": {
                "min_gap": min(total_gaps) if total_gaps else 0,
                "avg_gap": round(sum(total_gaps) / len(total_gaps), 1) if total_gaps else 0,
                "total_gaps_count": len(total_gaps),
            },
            "block_distribution": {
                "avg_trips_per_block": round(sum(block_sizes) / len(block_sizes), 2) if block_sizes else 0,
                "max_trips": max(block_sizes) if block_sizes else 0,
                "std_dev_trips": (
                    round(
                        sum((x - (sum(block_sizes) / len(block_sizes))) ** 2 for x in block_sizes) / len(block_sizes), 2
                    )
                    if block_sizes
                    else 0
                ),
            },
        }

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
                "advanced_stats": advanced_stats,
                "explainability": {
                    "vehicles_reduction": (
                        "VSP Merge + Tail Relocation"
                        if len(vsp_sol.blocks) < (baseline_metrics["vehicles"] if "baseline_metrics" in locals() else 0)
                        else "Stable"
                    ),
                    "crew_efficiency": (
                        "Pair Repair + Joint Swap"
                        if csp_final.num_crew < (baseline_metrics["crew"] if "baseline_metrics" in locals() else 0)
                        else "Stable"
                    ),
                    "compliance_fixing": (
                        "LNS + CSP Feedback"
                        if csp_final.cct_violations
                        < (baseline_metrics["violations"] if "baseline_metrics" in locals() else 0)
                        else "Stable"
                    ),
                },
                "benchmark": {
                    "baseline": baseline_metrics if "baseline_metrics" in locals() else None,
                    "final": {
                        "vehicles": len(vsp_sol.blocks),
                        "crew": csp_final.num_crew,
                        "violations": csp_final.cct_violations,
                        "total_cost": round(result.total_cost, 2),
                    },
                },
            }
        )

        if "baseline_metrics" in locals() and baseline_metrics:
            improvement = {
                "vehicles_saved": baseline_metrics["vehicles"] - len(vsp_sol.blocks),
                "crew_saved": baseline_metrics["crew"] - csp_final.num_crew,
                "cost_reduction": round(baseline_metrics["total_cost"] - result.total_cost, 2),
            }
            result.meta["performance"]["benchmark"]["improvement"] = improvement

        return result


def _vsp_cost(sol, vsp_params=None, cached_pairs=None) -> float:
    vsp_params = vsp_params or {}
    unassigned_penalty = Decimal("0.0")
    long_block_penalty = Decimal("0.0")
    infeasible_penalty = Decimal("0.0")
    pair_penalty = Decimal("0.0")

    unassigned_penalty = Decimal(len(getattr(sol, "unassigned_trips", []))) * Decimal("5000.0")

    crew_block_limit = int(vsp_params.get("crew_block_limit_minutes", 0) or 0)
    if crew_block_limit > 0:
        for block in getattr(sol, "blocks", []):
            duration = int(block.end_time - block.start_time)
            if duration > crew_block_limit:
                long_block_penalty += Decimal(duration - crew_block_limit) * Decimal("200.0")

    min_layover = int(vsp_params.get("min_layover_minutes", 8) or 8)
    if bool(vsp_params.get("preserve_preferred_pairs", True)):
        preferred_pairs = (
            cached_pairs
            if cached_pairs is not None
            else build_preferred_pairs(
                [trip for block in getattr(sol, "blocks", []) for trip in getattr(block, "trips", [])],
                min_layover,
                int(vsp_params.get("preferred_pair_window_minutes", 120) or 120),
            )
        )
        pair_break_penalty = Decimal(str(vsp_params.get("pair_break_penalty", 1000.0)))
        paired_trip_bonus = Decimal(str(vsp_params.get("paired_trip_bonus", 40.0)))
        if bool(vsp_params.get("hard_pairing_vehicle_level", False)):
            if "hard_pairing_penalty" in vsp_params:
                hard_pairing_penalty = Decimal(str(vsp_params["hard_pairing_penalty"]))
            else:
                hard_pairing_penalty = max(
                    pair_break_penalty * Decimal("10.0"),
                    Decimal(str(vsp_params.get("fixed_vehicle_activation_cost", 800.0))) * Decimal("25.0"),
                )
        else:
            hard_pairing_penalty = Decimal("0.0")
    else:
        preferred_pairs = {}
        pair_break_penalty = Decimal("0.0")
        paired_trip_bonus = Decimal("0.0")
        hard_pairing_penalty = Decimal("0.0")

    pair_penalty = Decimal(
        str(
            preferred_pair_penalty(
                getattr(sol, "blocks", []),
                preferred_pairs,
                float(pair_break_penalty),
                float(paired_trip_bonus),
                float(hard_pairing_penalty),
            )
        )
    )

    # CONSISTÊNCIA 3.1: Usar ConstraintEngine para penalidade de inviabilidade
    # (mesmo modelo que o post-opt usa, incluindo strict_zero_gap_validation)
    engine = ConstraintEngine(vsp_params)
    for block in getattr(sol, "blocks", []):
        trips = list(getattr(block, "trips", []))
        for index in range(len(trips) - 1):
            if not engine.is_connection_feasible(trips[index], trips[index + 1]):
                gap = int(trips[index + 1].start_time - trips[index].end_time)
                if gap < 0:
                    infeasible_penalty += Decimal("20000.0") + Decimal(abs(gap)) * Decimal("500.0")
                else:
                    infeasible_penalty += Decimal("15000.0")

    quick_cost = Decimal(str(quick_cost_sorted(sol.blocks)))
    total = quick_cost + unassigned_penalty + long_block_penalty + infeasible_penalty + pair_penalty
    return float(total)


def _vsp_hard_issue_count(sol, vsp_params=None) -> int:
    vsp_params = vsp_params or {}
    same_depot_required = bool(vsp_params.get("same_depot_required", False))
    issues = 0
    # CONSISTÊNCIA 3.1: Usar ConstraintEngine para contagem de issues
    engine = ConstraintEngine(vsp_params)

    for block in getattr(sol, "blocks", []):
        trips = list(getattr(block, "trips", []))
        for index in range(len(trips) - 1):
            if not engine.is_connection_feasible(trips[index], trips[index + 1]):
                issues += 1
        if same_depot_required and trips:
            if (
                trips[0].depot_id is not None
                and trips[-1].depot_id is not None
                and trips[0].depot_id != trips[-1].depot_id
            ):
                issues += 1
    if bool(vsp_params.get("hard_pairing_vehicle_level", False)):
        trip_group_blocks: dict[int, set[int]] = {}
        for block in getattr(sol, "blocks", []):
            for trip in getattr(block, "trips", []):
                group_id = getattr(trip, "trip_group_id", None)
                if group_id is None:
                    continue
                trip_group_blocks.setdefault(int(group_id), set()).add(int(block.id))
        issues += sum(1 for block_ids in trip_group_blocks.values() if len(block_ids) > 1)
    return issues
