"""
OptimizerService — orquestra a seleção e execução de algoritmos.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from .ai_service import AiService

from ..algorithms.csp.greedy import GreedyCSP
from ..algorithms.csp.set_partitioning import SetPartitioningCSP
from ..algorithms.csp.set_partitioning_optimized import SetPartitioningOptimizedCSP
from ..algorithms.evaluator import CostEvaluator
from ..algorithms.hybrid.pipeline import HybridPipeline
from ..algorithms.integrated.joint_solver import JointSolver
from ..algorithms.vsp.genetic import GeneticVSP
from ..algorithms.vsp.greedy import GreedyVSP
from ..algorithms.vsp.mcnf import MCNFVSP
from ..algorithms.vsp.simulated_annealing import SimulatedAnnealingVSP
from ..algorithms.vsp.tabu_search import TabuSearchVSP
from ..core.config import get_settings
from ..core.exceptions import HardConstraintViolationError, InfeasibleProblemError, InvalidAlgorithmError, NoProblemDataError, OptimizerError
from ..domain.models import AlgorithmType, OptimizationResult, Trip, VehicleType
from .hard_constraint_validator import HardConstraintValidator

settings = get_settings()
logger = logging.getLogger(__name__)


class OptimizerService:
    def __init__(self) -> None:
        self.evaluator = CostEvaluator()
        self.validator = HardConstraintValidator()
        self._solver_registry = {
            AlgorithmType.GREEDY: self._run_greedy,
            AlgorithmType.GENETIC: self._run_genetic,
            AlgorithmType.SIMULATED_ANNEALING: self._run_sa,
            AlgorithmType.TABU_SEARCH: self._run_ts,
            AlgorithmType.SET_PARTITIONING: self._run_sp,
            AlgorithmType.MCNF: self._run_mcnf,
            AlgorithmType.JOINT_SOLVER: self._run_joint,
            AlgorithmType.HYBRID_PIPELINE: self._run_hybrid,
        }

    def run(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        algorithm: AlgorithmType = AlgorithmType.HYBRID_PIPELINE,
        depot_id: Optional[int] = None,
        time_budget_s: Optional[float] = None,
        cct_params: Any = None,
        vsp_params: Any = None,
        optimization_params: Any = None,
    ) -> OptimizationResult:
        if not trips:
            raise NoProblemDataError("trips list is empty")

        t0 = time.perf_counter()
        cct_params = self._normalize_rules(cct_params)
        vsp_params = self._normalize_rules(vsp_params)
        normalized_time_budget_s = (
            float(time_budget_s)
            if time_budget_s is not None
            else float(vsp_params.get("time_budget_s", settings.hybrid_time_budget_seconds))
        )
        replay_fingerprint = self._build_replay_fingerprint(
            trips,
            algorithm,
            cct_params,
            vsp_params,
            normalized_time_budget_s,
        )
        had_explicit_mandatory_groups = bool(cct_params.get("mandatory_trip_groups_same_duty"))
        self._inject_trip_group_constraints(trips, cct_params, vsp_params)
        if not had_explicit_mandatory_groups and not bool(cct_params.get("enforce_trip_groups_hard", False)):
            cct_params.pop("mandatory_trip_groups_same_duty", None)
        
        strict_hard_validation = bool(
            vsp_params.get("strict_hard_validation", cct_params.get("strict_hard_validation", True))
        )

        t_input = time.perf_counter()
        input_report = self.validator.audit_input(trips, cct_params, vsp_params)
        input_validation_ms = (time.perf_counter() - t_input) * 1000
        if strict_hard_validation and not input_report["ok"]:
            raise HardConstraintViolationError(
                input_report["issues"],
                details=self.build_failure_payload(
                    HardConstraintViolationError(input_report["issues"]),
                    trips,
                    algorithm,
                    cct_params,
                    vsp_params,
                    stage="input_validation",
                    replay_fingerprint=replay_fingerprint,
                ),
            )

        t_solver = time.perf_counter()
        result = self._dispatch(
            algorithm,
            trips,
            vehicle_types,
            depot_id,
            normalized_time_budget_s,
            cct_params,
            vsp_params,
        )
        solver_ms = (time.perf_counter() - t_solver) * 1000
        result.total_elapsed_ms = (time.perf_counter() - t0) * 1000
        result.algorithm = algorithm
        result.meta.setdefault("input", {})
        result.meta["hard_constraint_report"] = {
            "strict": strict_hard_validation,
            "input": input_report,
        }

        t_output = time.perf_counter()
        output_report = self.validator.audit_result(result, trips, cct_params, vsp_params)
        output_validation_ms = (time.perf_counter() - t_output) * 1000
        result.meta["hard_constraint_report"]["output"] = output_report
        if strict_hard_validation and not output_report["ok"]:
            raise HardConstraintViolationError(
                output_report["issues"],
                details=self.build_failure_payload(
                    HardConstraintViolationError(output_report["issues"]),
                    trips,
                    algorithm,
                    cct_params,
                    vsp_params,
                    stage="output_validation",
                    replay_fingerprint=replay_fingerprint,
                ),
            )

        t_audit = time.perf_counter()
        # Injetar regras dinâmicas e pesos de custo no avaliador
        self.evaluator.set_dynamic_rules(cct_params.get("dynamic_rules") or [])
        
        # Configurar novos pesos de custo
        if optimization_params:
            self.evaluator.set_costs(
                cost_vehicle=optimization_params.get("cost_vehicle", 1000.0),
                cost_km=optimization_params.get("cost_km", 1.0),
                cost_duty=optimization_params.get("cost_duty", 500.0),
            )
        
        cost_breakdown = self.evaluator.total_cost_breakdown(result, vehicle_types)
        result.total_cost = float(cost_breakdown["total"])
        result.meta["cost_breakdown"] = cost_breakdown
        result.meta["operational_kpis"] = self._build_operational_kpis(result, cct_params)
        result.meta["trip_group_audit"] = self._build_trip_group_audit(result, trips)
        result.meta["phase_summary"] = self._build_phase_summary(result, cost_breakdown)
        result.meta["reproducibility"] = self._build_reproducibility_snapshot(
            algorithm,
            trips,
            cct_params,
            vsp_params,
            normalized_time_budget_s,
        )
        result.meta["solver_version"] = settings.app_version
        result.meta["solver_explanation"] = self._build_solver_explanation(result)
        audit_enrichment_ms = (time.perf_counter() - t_audit) * 1000

        performance_meta = dict((result.meta or {}).get("performance") or {})
        phase_timings_ms = dict(performance_meta.get("phase_timings_ms") or {})
        phase_timings_ms.update(
            {
                "input_validation_ms": round(input_validation_ms, 2),
                "solver_ms": round(solver_ms, 2),
                "output_validation_ms": round(output_validation_ms, 2),
                "audit_enrichment_ms": round(audit_enrichment_ms, 2),
            }
        )
        performance_meta.update(
            {
                "phase_timings_ms": phase_timings_ms,
                "total_elapsed_ms": round(result.total_elapsed_ms, 2),
                "trip_count": len(trips),
                "vehicle_type_count": len(vehicle_types),
            }
        )
        result.meta["performance"] = performance_meta

        result.meta["input"].update(
            {
                "n_trips": len(trips),
                "n_vehicle_types": len(vehicle_types),
                "cct_params": cct_params,
                "vsp_params": vsp_params,
                "replay_fingerprint": replay_fingerprint,
            }
        )

        # ── AI Copilot: insight em linguagem natural (nice-to-have) ──────────
        # Esta chamada é o ÚLTIMO passo — toda a matemática já está concluída.
        # Se falhar por qualquer motivo, ai_copilot_insight fica None e o
        # resultado é retornado normalmente. NUNCA quebra o pipeline.
        try:
            cost_bd = result.meta.get("cost_breakdown") or {}
            phase_sum = result.meta.get("phase_summary") or {}
            op_kpis = result.meta.get("operational_kpis") or {}
            ai_metrics = {
                "vehicles": len(result.vsp.blocks or []),
                "crew": result.csp.num_crew,
                "duties": len(result.csp.duties or []),
                "total_cost": float(result.total_cost or 0),
                "vsp_cost": float((cost_bd.get("vsp") or {}).get("total", 0) or 0),
                "csp_cost": float((cost_bd.get("csp") or {}).get("total", 0) or 0),
                "covered_trips": sum(
                    len(block.trips) for block in (result.vsp.blocks or [])
                ),
                "total_trips": len(trips),
                "cct_violations": int(result.csp.cct_violations or 0),
                "work_minutes": int(op_kpis.get("work_minutes", 0) or 0),
                "paid_minutes": int(op_kpis.get("paid_minutes", 0) or 0),
                "dominant_vsp": (
                    (phase_sum.get("vsp") or {}).get("dominant_cost_component") or {}
                ).get("component", "N/A"),
                "dominant_csp": (
                    (phase_sum.get("csp") or {}).get("dominant_cost_component") or {}
                ).get("component", "N/A"),
                "status": (result.meta.get("solver_explanation") or {}).get(
                    "status", "feasible"
                ),
            }
            result.meta["ai_copilot_insight"] = AiService().generate_insight_sync(ai_metrics)
        except Exception as _ai_exc:
            logger.warning("[AI Copilot] Falha ao gerar insight (não crítico): %s", _ai_exc)
            result.meta["ai_copilot_insight"] = None

        return result

    def build_failure_payload(
        self,
        exc: Exception,
        trips: List[Trip],
        algorithm: AlgorithmType | str,
        cct_params: Dict[str, Any] | None,
        vsp_params: Dict[str, Any] | None,
        stage: str = "solver",
        replay_fingerprint: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cct_params = cct_params or {}
        vsp_params = vsp_params or {}
        replay_fingerprint = replay_fingerprint or self._build_replay_fingerprint(
            trips,
            algorithm,
            cct_params,
            vsp_params,
            float(vsp_params.get("time_budget_s", settings.hybrid_time_budget_seconds) or settings.hybrid_time_budget_seconds),
        )
        algorithm_name = str(algorithm.value if hasattr(algorithm, "value") else algorithm)
        issue_strings: List[str] = []
        phase = "integrated"
        kind = "error"
        code = getattr(exc, "code", exc.__class__.__name__)
        summary = str(exc)
        infeasibility_reason = None

        if isinstance(exc, HardConstraintViolationError):
            issue_strings = list(getattr(exc, "issues", []) or [])
            phase = self._dominant_failure_phase(issue_strings)
            kind = "hard_constraint_violation"
            summary = "Falha por restrições operacionais ou regulatórias obrigatórias."
            infeasibility_reason = self._infer_infeasibility_reason(issue_strings)
        elif isinstance(exc, InfeasibleProblemError):
            phase = "integrated"
            kind = "infeasible_problem"
            summary = "O solver concluiu que não encontrou solução viável para o cenário atual."
            infeasibility_reason = {
                "reason": "solver_returned_infeasible",
                "message": str(exc),
            }
        elif isinstance(exc, NoProblemDataError):
            phase = "input"
            kind = "missing_problem_data"
            summary = "Não há dados suficientes de entrada para executar o solver."
        elif isinstance(exc, InvalidAlgorithmError):
            phase = "input"
            kind = "invalid_algorithm"
            summary = "O algoritmo solicitado não é suportado pelo optimizer."
        elif isinstance(exc, OptimizerError):
            phase = "integrated"
            kind = "optimizer_error"

        structured_issues = self._structure_issues(issue_strings, "hard")
        return {
            "code": code,
            "kind": kind,
            "phase": phase,
            "stage": stage,
            "message": str(exc),
            "summary": summary,
            "issues": structured_issues,
            "issue_count": len(structured_issues),
            "infeasibility_explanation": {
                "reason": infeasibility_reason.get("reason") if infeasibility_reason else None,
                "message": infeasibility_reason.get("message") if infeasibility_reason else None,
                "primary_issue_codes": infeasibility_reason.get("primary_issue_codes", []) if infeasibility_reason else [],
                "recommendations": self._build_recommendations(issue_strings, [], {"split_groups": 0}),
            },
            "input_snapshot": {
                "algorithm": algorithm_name,
                "trip_count": len(trips),
                "line_ids": sorted({int(trip.line_id) for trip in trips}) if trips else [],
                "cct_params": cct_params,
                "vsp_params": vsp_params,
                "input_hash": replay_fingerprint.get("input_hash"),
                "params_hash": replay_fingerprint.get("params_hash"),
                "time_budget_s": replay_fingerprint.get("time_budget_s"),
            },
        }

    def _stable_json(self, value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def _build_replay_fingerprint(
        self,
        trips: List[Trip],
        algorithm: AlgorithmType | str,
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        time_budget_s: float,
    ) -> Dict[str, Any]:
        algorithm_name = str(algorithm.value if hasattr(algorithm, "value") else algorithm)
        trips_snapshot = [
            {
                "id": int(trip.id),
                "line_id": int(trip.line_id),
                "trip_group_id": int(trip.trip_group_id) if trip.trip_group_id is not None else None,
                "start_time": int(trip.start_time),
                "end_time": int(trip.end_time),
                "origin_id": int(trip.origin_id),
                "destination_id": int(trip.destination_id),
                "duration": int(trip.duration),
                "distance_km": float(trip.distance_km),
                "direction": trip.direction,
                "is_pull_out": bool(trip.is_pull_out),
                "is_pull_back": bool(trip.is_pull_back),
            }
            for trip in sorted(trips, key=lambda item: (item.id, item.start_time, item.end_time))
        ]
        params_snapshot = {
            "algorithm": algorithm_name,
            "time_budget_s": float(time_budget_s),
            "cct_params": cct_params,
            "vsp_params": vsp_params,
        }
        input_hash = hashlib.sha256(self._stable_json(trips_snapshot).encode("ascii")).hexdigest()[:12]
        params_hash = hashlib.sha256(self._stable_json(params_snapshot).encode("ascii")).hexdigest()[:12]
        return {
            "input_hash": input_hash,
            "params_hash": params_hash,
            "trip_count": len(trips_snapshot),
            "line_ids": sorted({int(trip["line_id"]) for trip in trips_snapshot}),
            "time_budget_s": float(time_budget_s),
        }

    def _dominant_failure_phase(self, issues: List[str]) -> str:
        if not issues:
            return "integrated"
        counts = {"vsp": 0, "csp": 0, "input": 0, "integrated": 0}
        for item in self._structure_issues(issues, "hard"):
            counts[item.get("phase", "integrated")] = counts.get(item.get("phase", "integrated"), 0) + 1
        return max(counts, key=counts.get)

    def _infer_infeasibility_reason(self, issues: List[str]) -> Dict[str, Any]:
        issue_codes = [item["code"] for item in self._structure_issues(issues, "hard")]
        reason = "hard_constraints"
        message = "Restrições obrigatórias impediram a geração de uma solução válida."
        if any(code == "UNCOVERED_TRIP" for code in issue_codes):
            reason = "uncovered_trip"
            message = "Há viagens que não conseguem ser cobertas no VSP com as restrições atuais."
        elif any(code == "DEADHEAD_INFEASIBLE" for code in issue_codes):
            reason = "deadhead_infeasible"
            message = "As conexões físicas entre viagens não têm tempo mínimo viável."
        elif any(code == "SPREAD_EXCEEDED" for code in issue_codes):
            reason = "spread_limit"
            message = "O spread das jornadas ultrapassa o limite máximo configurado."
        elif any(code == "CONTINUOUS_DRIVING_EXCEEDED" for code in issue_codes):
            reason = "continuous_driving_limit"
            message = "A direção contínua exigida pela grade excede o limite regulatório."
        elif any(code == "MANDATORY_GROUP_SPLIT" for code in issue_codes):
            reason = "trip_group_split"
            message = "Os grupos ida/volta obrigatórios não conseguem permanecer juntos no cenário atual."
        return {
            "reason": reason,
            "message": message,
            "primary_issue_codes": issue_codes[:10],
        }

    def _build_phase_summary(self, result: OptimizationResult, cost_breakdown: Dict[str, Any]) -> Dict[str, Any]:
        vsp_breakdown = dict(cost_breakdown.get("vsp") or {})
        csp_breakdown = dict(cost_breakdown.get("csp") or {})
        return {
            "vsp": {
                "vehicles": len(result.vsp.blocks or []),
                "assigned_trips": sum(len(block.trips) for block in (result.vsp.blocks or [])),
                "unassigned_trips": len(result.vsp.unassigned_trips or []),
                "warnings_count": len(result.vsp.warnings or []),
                "cost": float(vsp_breakdown.get("total", 0.0) or 0.0),
                "dominant_cost_component": self._dominant_component(
                    vsp_breakdown,
                    ["activation", "connection", "distance", "time", "idle_cost"],
                ),
            },
            "csp": {
                "duties": len(result.csp.duties or []),
                "crew": result.csp.num_crew,
                "rosters": int((result.csp.meta or {}).get("roster_count", result.csp.num_crew) or result.csp.num_crew),
                "uncovered_blocks": len(result.csp.uncovered_blocks or []),
                "cct_violations": int(result.csp.cct_violations or 0),
                "warnings_count": len(result.csp.warnings or []),
                "cost": float(csp_breakdown.get("total", 0.0) or 0.0),
                "dominant_cost_component": self._dominant_component(
                    csp_breakdown,
                    [
                        "work_cost",
                        "guaranteed_cost",
                        "waiting_cost",
                        "overtime_cost",
                        "long_unpaid_break_penalty",
                        "nocturnal_extra",
                        "holiday_extra",
                        "cct_penalties",
                    ],
                ),
            },
        }

    def _build_trip_group_audit(self, result: OptimizationResult, trips: List[Trip]) -> Dict[str, Any]:
        groups: Dict[int, List[int]] = {}
        for trip in trips:
            if trip.trip_group_id is None:
                continue
            groups.setdefault(int(trip.trip_group_id), []).append(int(trip.id))

        explicit_groups = {
            group_id: sorted(set(member_ids))
            for group_id, member_ids in groups.items()
            if len(set(member_ids)) >= 2
        }
        if not explicit_groups:
            return {
                "groups_total": 0,
                "groups_fully_assigned": 0,
                "same_block_groups": 0,
                "same_duty_groups": 0,
                "same_roster_groups": 0,
                "split_groups": 0,
                "missing_groups": 0,
                "sample_splits": [],
            }

        trip_to_block: Dict[int, int] = {}
        for block in result.vsp.blocks:
            for trip in block.trips:
                trip_to_block[int(trip.id)] = int(block.id)

        trip_to_duty: Dict[int, int] = {}
        trip_to_roster: Dict[int, int | None] = {}
        for duty in result.csp.duties:
            roster_id = duty.meta.get("roster_id")
            for task in duty.tasks:
                for trip in task.trips:
                    trip_to_duty[int(trip.id)] = int(duty.id)
                    trip_to_roster[int(trip.id)] = int(roster_id) if roster_id is not None else None

        groups_fully_assigned = 0
        same_block_groups = 0
        same_duty_groups = 0
        same_roster_groups = 0
        missing_groups = 0
        sample_splits: List[Dict[str, Any]] = []

        for group_id, member_ids in explicit_groups.items():
            block_ids = {trip_to_block.get(trip_id) for trip_id in member_ids}
            duty_ids = {trip_to_duty.get(trip_id) for trip_id in member_ids}
            roster_ids = {trip_to_roster.get(trip_id) for trip_id in member_ids}

            fully_assigned = None not in block_ids and None not in duty_ids
            if fully_assigned:
                groups_fully_assigned += 1
            else:
                missing_groups += 1

            same_block = fully_assigned and len(block_ids) == 1
            same_duty = fully_assigned and len(duty_ids) == 1
            same_roster = fully_assigned and len(roster_ids) == 1 and None not in roster_ids
            if same_block:
                same_block_groups += 1
            if same_duty:
                same_duty_groups += 1
            if same_roster:
                same_roster_groups += 1
            if not same_roster and len(sample_splits) < 10:
                sample_splits.append(
                    {
                        "trip_group_id": group_id,
                        "trip_ids": member_ids,
                        "block_ids": sorted(int(item) for item in block_ids if item is not None),
                        "duty_ids": sorted(int(item) for item in duty_ids if item is not None),
                        "roster_ids": sorted(int(item) for item in roster_ids if item is not None),
                    }
                )

        total_groups = len(explicit_groups)
        return {
            "groups_total": total_groups,
            "groups_fully_assigned": groups_fully_assigned,
            "same_block_groups": same_block_groups,
            "same_duty_groups": same_duty_groups,
            "same_roster_groups": same_roster_groups,
            "split_groups": total_groups - same_roster_groups,
            "missing_groups": missing_groups,
            "same_roster_ratio": round((same_roster_groups / total_groups), 4) if total_groups > 0 else 0.0,
            "sample_splits": sample_splits,
        }

    def _build_reproducibility_snapshot(
        self,
        algorithm: AlgorithmType,
        trips: List[Trip],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        time_budget_s: float,
    ) -> Dict[str, Any]:
        random_seed = vsp_params.get("random_seed")
        algorithm_name = str(algorithm.value if hasattr(algorithm, "value") else algorithm)
        stochastic_algorithms = {
            AlgorithmType.SIMULATED_ANNEALING.value,
            AlgorithmType.TABU_SEARCH.value,
            AlgorithmType.GENETIC.value,
            AlgorithmType.HYBRID_PIPELINE.value,
        }
        stochastic = algorithm_name in stochastic_algorithms
        deterministic_replay_possible = not stochastic
        replay_fingerprint = self._build_replay_fingerprint(
            trips,
            algorithm,
            cct_params,
            vsp_params,
            time_budget_s,
        )
        return {
            "algorithm": algorithm_name,
            "random_seed": random_seed,
            "stochastic_algorithm": stochastic,
            "deterministic_replay_possible": deterministic_replay_possible,
            "input_hash": replay_fingerprint["input_hash"],
            "params_hash": replay_fingerprint["params_hash"],
            "time_budget_s": replay_fingerprint["time_budget_s"],
            "note": (
                "Replicável se os mesmos dados e parâmetros forem reutilizados."
                if deterministic_replay_possible
                else (
                    "Seed explícita reduz a variabilidade, mas o solver usa budget por tempo; execuções equivalentes podem divergir no número de iterações e no resultado final."
                    if random_seed is not None
                    else "Algoritmo estocástico sem seed explícita: execuções equivalentes podem divergir mesmo com o mesmo input."
                )
            ),
        }

    def _dominant_component(self, breakdown: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
        total = float(breakdown.get("total", 0.0) or 0.0)
        best_key = None
        best_value = -1.0
        for key in keys:
            value = float(breakdown.get(key, 0.0) or 0.0)
            if value > best_value:
                best_key = key
                best_value = value
        return {
            "component": best_key,
            "value": round(max(best_value, 0.0), 2),
            "share": round((best_value / total), 4) if total > 0 and best_value > 0 else 0.0,
        }

    def _build_solver_explanation(self, result: OptimizationResult) -> Dict[str, Any]:
        report = ((result.meta or {}).get("hard_constraint_report") or {}).get("output") or {}
        cost_breakdown = (result.meta or {}).get("cost_breakdown") or {}
        phase_summary = (result.meta or {}).get("phase_summary") or {}
        trip_group_audit = (result.meta or {}).get("trip_group_audit") or {}
        hard_issues = list(report.get("hard_issues") or [])
        soft_issues = list(report.get("soft_issues") or [])

        if hard_issues:
            status = "hard_violation"
            headline = "Solução gerada com violações hard; exige correção antes de uso operacional."
        elif soft_issues or int(result.csp.cct_violations or 0) > 0:
            status = "soft_violation"
            headline = "Solução operacional viável, mas com alertas e violações soft que pedem revisão."
        else:
            status = "feasible"
            headline = "Solução viável sem violações hard e sem alertas regulatórios remanescentes."

        total_trips = sum(len(block.trips) for block in (result.vsp.blocks or [])) + len(result.vsp.unassigned_trips or [])
        summary = [
            f"VSP cobriu {sum(len(block.trips) for block in (result.vsp.blocks or []))}/{total_trips} viagens com {len(result.vsp.blocks or [])} veículos.",
            f"CSP produziu {result.csp.num_crew} tripulantes, {len(result.csp.duties or [])} jornadas e {int((result.csp.meta or {}).get('roster_count', result.csp.num_crew) or result.csp.num_crew)} rosters.",
        ]

        dominant_vsp = ((phase_summary.get("vsp") or {}).get("dominant_cost_component") or {}).get("component")
        dominant_csp = ((phase_summary.get("csp") or {}).get("dominant_cost_component") or {}).get("component")
        if cost_breakdown:
            summary.append(
                f"Custo total {float(cost_breakdown.get('total', 0.0) or 0.0):.2f}, com dominância VSP={dominant_vsp or '--'} e CSP={dominant_csp or '--'}."
            )
        if trip_group_audit.get("groups_total", 0) > 0:
            summary.append(
                f"Trip groups preservados no mesmo roster: {trip_group_audit.get('same_roster_groups', 0)}/{trip_group_audit.get('groups_total', 0)}."
            )

        recommendations = self._build_recommendations(hard_issues, soft_issues, trip_group_audit)
        return {
            "status": status,
            "headline": headline,
            "summary": summary,
            "issues": {
                "hard": self._structure_issues(hard_issues, "hard"),
                "soft": self._structure_issues(soft_issues, "soft"),
            },
            "recommendations": recommendations,
            "phase_summary": phase_summary,
            "trip_group_audit": trip_group_audit,
        }

    def _build_recommendations(
        self,
        hard_issues: List[str],
        soft_issues: List[str],
        trip_group_audit: Dict[str, Any],
    ) -> List[str]:
        recommendations: List[str] = []
        issue_pool = hard_issues + soft_issues
        if any(issue.startswith("MANDATORY_GROUP_SPLIT") for issue in issue_pool) or trip_group_audit.get("split_groups", 0) > 0:
            recommendations.append("Revise os grupos ida/volta preservados no CSP e confirme se o pairing deve ser rígido ou apenas preferencial.")
        if any(issue.startswith("CONTINUOUS_DRIVING_EXCEEDED") for issue in issue_pool):
            recommendations.append("Aumente as janelas de pausa ou antecipe o run-cutting para evitar estouro de direção contínua.")
        if any(issue.startswith("SPREAD_EXCEEDED") for issue in issue_pool):
            recommendations.append("Reduza spread por jornada ou permita mais fragmentação de duties no CSP.")
        if any(issue.startswith("UNCOVERED_TRIP") for issue in issue_pool):
            recommendations.append("Valide a viabilidade física do VSP: cobertura, deadhead e teto de frota podem estar incompatíveis com a grade.")
        if not recommendations and issue_pool:
            recommendations.append("Use os códigos estruturados de restrição para inspecionar diretamente a fase VSP ou CSP que produziu o alerta.")
        return recommendations[:4]

    def _structure_issues(self, issues: List[str], severity: str) -> List[Dict[str, Any]]:
        return [self._describe_issue(issue, severity) for issue in issues]

    def _describe_issue(self, issue: str, severity: str) -> Dict[str, Any]:
        code = issue.split()[0] if issue else "UNKNOWN"
        refs = re.findall(r"([TBDR]\d+(?:->\d+)?)", issue)
        phase = "integrated"
        message = "Violação operacional detectada."

        if code.startswith(("UNCOVERED_TRIP", "VEHICLE_OVERLAP", "DEADHEAD_INFEASIBLE", "BLOCK_")):
            phase = "vsp"
        elif code.startswith(("UNCOVERED_BLOCK", "SPREAD_EXCEEDED", "CONTINUOUS_DRIVING_EXCEEDED", "MEAL_BREAK_MISSING", "DUTY_", "INTERSHIFT_", "OPERATOR_")):
            phase = "csp"

        if code.startswith("UNCOVERED_TRIP"):
            message = "Há viagem sem cobertura no VSP."
        elif code.startswith("UNCOVERED_BLOCK"):
            message = "Há bloco de veículo sem cobertura de tripulação no CSP."
        elif code.startswith("VEHICLE_OVERLAP"):
            message = "Duas viagens ficaram sobrepostas no mesmo bloco de veículo."
        elif code.startswith("DEADHEAD_INFEASIBLE"):
            message = "A conexão entre viagens do mesmo bloco não tem tempo suficiente de deadhead/layover."
        elif code.startswith("SPREAD_EXCEEDED"):
            message = "A jornada total ultrapassou o spread permitido."
        elif code.startswith("CONTINUOUS_DRIVING_EXCEEDED"):
            message = "A direção contínua ultrapassou o limite permitido."
        elif code.startswith("MEAL_BREAK_MISSING"):
            message = "A jornada não encaixou intervalo de refeição válido."
        elif code.startswith("MANDATORY_GROUP_SPLIT"):
            message = "Um grupo ida/volta obrigatório foi separado entre rosters ou duties."
        elif code.startswith("OPERATOR_CHANGE_NON_TERMINAL"):
            message = "Houve troca de bloco/veículo fora de terminal ou relief point permitido."
        elif code.startswith("INTERSHIFT_REST_VIOLATION"):
            message = "O descanso entre jornadas de um mesmo roster ficou abaixo do mínimo."

        return {
            "raw": issue,
            "code": code,
            "severity": severity,
            "phase": phase,
            "refs": refs,
            "message": message,
        }

    def _build_operational_kpis(self, result: OptimizationResult, cct_params: Dict[str, Any]) -> Dict[str, Any]:
        duties = list(result.csp.duties or [])
        if not duties:
            return {
                "vehicles": len(result.vsp.blocks or []),
                "crew": 0,
                "work_minutes": 0,
                "paid_minutes": 0,
                "paid_work_delta_minutes": 0,
                "fairness": {
                    "target_work_minutes": int(cct_params.get("fairness_target_work_minutes", 420) or 420),
                    "tolerance_minutes": int(cct_params.get("fairness_tolerance_minutes", 30) or 30),
                    "d_plus_total": 0,
                    "d_minus_total": 0,
                    "within_band_count": 0,
                    "outside_band_count": 0,
                },
            }

        target = int(cct_params.get("fairness_target_work_minutes", 420) or 420)
        tolerance = int(cct_params.get("fairness_tolerance_minutes", 30) or 30)

        total_work = sum(int(duty.work_time or 0) for duty in duties)
        total_paid = sum(int(duty.paid_minutes or duty.work_time or 0) for duty in duties)

        d_plus_total = 0
        d_minus_total = 0
        within_band = 0
        outside_band = 0

        operator_blocks: Dict[int, set[int]] = {}
        for duty in duties:
            work = int(duty.work_time or 0)
            d_plus = max(0, work - target)
            d_minus = max(0, target - work)
            d_plus_total += d_plus
            d_minus_total += d_minus

            if abs(work - target) <= tolerance:
                within_band += 1
            else:
                outside_band += 1

            operator_id = duty.meta.get("operator_id")
            if operator_id is None:
                continue
            source_blocks = {
                int(item)
                for item in duty.meta.get("source_block_ids", [])
                if item is not None
            }
            operator_blocks.setdefault(int(operator_id), set()).update(source_blocks)

        stretch_values = [max(0, len(blocks) - 1) for blocks in operator_blocks.values() if blocks]
        avg_vehicle_changes_per_operator = round(sum(stretch_values) / len(stretch_values), 3) if stretch_values else 0.0

        return {
            "vehicles": len(result.vsp.blocks or []),
            "crew": len(duties),
            "work_minutes": total_work,
            "paid_minutes": total_paid,
            "paid_work_delta_minutes": max(0, total_paid - total_work),
            "fairness": {
                "target_work_minutes": target,
                "tolerance_minutes": tolerance,
                "d_plus_total": d_plus_total,
                "d_minus_total": d_minus_total,
                "within_band_count": within_band,
                "outside_band_count": outside_band,
                "avg_work_minutes": round(total_work / max(1, len(duties)), 2),
            },
            "stretch_kpi": {
                "operators_with_assignment": len(operator_blocks),
                "avg_vehicle_changes_per_operator": avg_vehicle_changes_per_operator,
            },
        }

    def _dispatch(
        self,
        algorithm: AlgorithmType,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int],
        time_budget_s: Optional[float],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
    ) -> OptimizationResult:
        handler = self._solver_registry.get(algorithm)
        if not handler:
            raise InvalidAlgorithmError(str(algorithm))
        return handler(trips, vehicle_types, depot_id, time_budget_s, cct_params, vsp_params)

    def _run_greedy(self, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int], time_budget_s: Optional[float], cct_params: Dict[str, Any], vsp_params: Dict[str, Any]) -> OptimizationResult:
        csp = self._make_csp(cct_params, vsp_params)
        vsp = GreedyVSP(vsp_params=vsp_params).solve(trips, vehicle_types, depot_id)
        return OptimizationResult(vsp=vsp, csp=csp.solve(vsp.blocks, trips))

    def _run_genetic(self, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int], time_budget_s: Optional[float], cct_params: Dict[str, Any], vsp_params: Dict[str, Any]) -> OptimizationResult:
        budget = time_budget_s or vsp_params.get("time_budget_s", settings.hybrid_time_budget_seconds)
        csp = self._make_csp(cct_params, vsp_params)
        ga = GeneticVSP(vsp_params=vsp_params)
        ga.time_budget_s = budget * 0.8
        vsp = ga.solve(trips, vehicle_types, depot_id)
        return OptimizationResult(vsp=vsp, csp=csp.solve(vsp.blocks, trips))

    def _run_sa(self, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int], time_budget_s: Optional[float], cct_params: Dict[str, Any], vsp_params: Dict[str, Any]) -> OptimizationResult:
        budget = time_budget_s or vsp_params.get("time_budget_s", settings.hybrid_time_budget_seconds)
        csp = self._make_csp(cct_params, vsp_params)
        sa = SimulatedAnnealingVSP(vsp_params=vsp_params)
        sa.time_budget_s = budget * 0.8
        vsp = sa.solve(trips, vehicle_types, depot_id)
        return OptimizationResult(vsp=vsp, csp=csp.solve(vsp.blocks, trips))

    def _run_ts(self, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int], time_budget_s: Optional[float], cct_params: Dict[str, Any], vsp_params: Dict[str, Any]) -> OptimizationResult:
        budget = time_budget_s or vsp_params.get("time_budget_s", settings.hybrid_time_budget_seconds)
        csp = self._make_csp(cct_params, vsp_params)
        ts = TabuSearchVSP(vsp_params=vsp_params)
        ts.time_budget_s = budget * 0.8
        vsp = ts.solve(trips, vehicle_types, depot_id)
        return OptimizationResult(vsp=vsp, csp=csp.solve(vsp.blocks, trips))

    def _run_sp(self, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int], time_budget_s: Optional[float], cct_params: Dict[str, Any], vsp_params: Dict[str, Any]) -> OptimizationResult:
        budget = time_budget_s or vsp_params.get("time_budget_s", settings.hybrid_time_budget_seconds)
        vsp = GreedyVSP(vsp_params=vsp_params).solve(trips, vehicle_types, depot_id)
        ilp = self._make_set_covering_csp(cct_params, vsp_params)
        ilp.time_budget_s = budget * 0.9
        return OptimizationResult(vsp=vsp, csp=ilp.solve(vsp.blocks, trips))

    def _run_mcnf(self, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int], time_budget_s: Optional[float], cct_params: Dict[str, Any], vsp_params: Dict[str, Any]) -> OptimizationResult:
        budget = time_budget_s or vsp_params.get("time_budget_s", settings.hybrid_time_budget_seconds)
        csp = self._make_csp(cct_params, vsp_params)
        mcnf = MCNFVSP(vsp_params=vsp_params)
        mcnf.time_budget_s = budget * 0.8
        vsp = mcnf.solve(trips, vehicle_types, depot_id)
        return OptimizationResult(vsp=vsp, csp=csp.solve(vsp.blocks, trips))

    def _run_joint(self, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int], time_budget_s: Optional[float], cct_params: Dict[str, Any], vsp_params: Dict[str, Any]) -> OptimizationResult:
        budget = time_budget_s or vsp_params.get("time_budget_s", settings.hybrid_time_budget_seconds)
        return JointSolver(time_budget_s=budget, cct_params=cct_params, vsp_params=vsp_params).solve(trips, vehicle_types, depot_id)

    def _run_hybrid(self, trips: List[Trip], vehicle_types: List[VehicleType], depot_id: Optional[int], time_budget_s: Optional[float], cct_params: Dict[str, Any], vsp_params: Dict[str, Any]) -> OptimizationResult:
        budget = time_budget_s or vsp_params.get("time_budget_s", settings.hybrid_time_budget_seconds)
        return HybridPipeline(time_budget_s=budget, cct_params=cct_params, vsp_params=vsp_params).solve(trips, vehicle_types, depot_id)

    def _as_dict(self, params: Any) -> Dict[str, Any]:
        if params is None:
            return {}
        if isinstance(params, dict):
            return dict(params)
        if hasattr(params, "model_dump"):
            return params.model_dump(exclude_none=True)
        return {
            key: value
            for key, value in vars(params).items()
            if not key.startswith("_") and value is not None
        }

    def _normalize_rules(self, params: Any) -> Dict[str, Any]:
        normalized = self._as_dict(params)
        fairness_weight = normalized.get("fairness_weight")
        if fairness_weight is not None:
            try:
                fairness = float(fairness_weight)
                if fairness > 1.0:
                    fairness = fairness / 100.0
                fairness = max(0.0, fairness)
                goal_weights = dict(normalized.get("goal_weights") or {})
                goal_weights.setdefault("fairness", fairness)
                normalized["goal_weights"] = goal_weights
            except (TypeError, ValueError):
                pass

        rules = normalized.get("natural_language_rules") or []
        for rule in rules:
            parsed = self._parse_rule(rule)
            for key, value in parsed.items():
                normalized.setdefault(key, value)
        return normalized

    def _inject_trip_group_constraints(
        self,
        trips: List[Trip],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
    ) -> None:
        hard_pairing = bool(cct_params.get("enforce_trip_groups_hard", False)) or bool(
            cct_params.get("operator_pairing_hard", False)
        )
        if cct_params.get("mandatory_trip_groups_same_duty"):
            return
        if not bool(vsp_params.get("preserve_preferred_pairs", True)):
            return

        grouped: Dict[tuple[int, int], List[int]] = {}
        for trip in trips:
            if trip.trip_group_id is None:
                continue
            grouped.setdefault((trip.line_id, trip.trip_group_id), []).append(trip.id)

        explicit_pairs: List[List[int]] = [sorted(ids) for ids in grouped.values() if len(ids) == 2]

        if not explicit_pairs and hard_pairing:
            inferred = self._infer_round_trip_pairs(trips, vsp_params)
            trip_by_id = {trip.id: trip for trip in trips}
            synthetic_group = -1
            for a_id, b_id in inferred:
                a_trip = trip_by_id.get(a_id)
                b_trip = trip_by_id.get(b_id)
                if a_trip is None or b_trip is None:
                    continue
                if a_trip.trip_group_id is None and b_trip.trip_group_id is None:
                    a_trip.trip_group_id = synthetic_group
                    b_trip.trip_group_id = synthetic_group
                    explicit_pairs.append(sorted([a_id, b_id]))
                    synthetic_group -= 1

        if hard_pairing and explicit_pairs:
            cct_params["mandatory_trip_groups_same_duty"] = explicit_pairs
            if bool(cct_params.get("operator_single_vehicle_only", False)):
                fixed_cost = float(vsp_params.get("fixed_vehicle_activation_cost", 800.0) or 800.0)
                vsp_params.setdefault("hard_pairing_vehicle_level", True)
                vsp_params.setdefault("hard_pairing_penalty", max(fixed_cost * 25.0, 20000.0))

    def _infer_round_trip_pairs(self, trips: List[Trip], vsp_params: Dict[str, Any]) -> List[List[int]]:
        pair_window = int(vsp_params.get("preferred_pair_window_minutes", 30) or 30)
        pair_window = max(5, min(pair_window, 90))

        by_line: Dict[int, List[Trip]] = {}
        for trip in trips:
            by_line.setdefault(int(trip.line_id), []).append(trip)

        used: set[int] = set()
        pairs: List[List[int]] = []
        for line_id in sorted(by_line.keys()):
            ordered = sorted(by_line[line_id], key=lambda item: (item.start_time, item.id))
            for index, trip in enumerate(ordered):
                if trip.id in used:
                    continue

                best: Optional[Trip] = None
                best_gap = 10**9
                for nxt in ordered[index + 1 :]:
                    if nxt.id in used:
                        continue
                    gap = int(nxt.start_time - trip.end_time)
                    if gap < 0:
                        continue
                    if gap > pair_window:
                        break
                    # Verificar por terminal: destino da ida == origem da volta
                    if trip.destination_id != nxt.origin_id:
                        continue
                    if trip.origin_id != nxt.destination_id:
                        continue
                    # Verificar por direction se disponível: ida deve ser outbound, volta return
                    if trip.direction and nxt.direction:
                        if trip.direction == nxt.direction:
                            continue  # Mesma direção não forma par ida/volta
                    if gap < best_gap:
                        best = nxt
                        best_gap = gap

                if best is None:
                    continue

                used.add(trip.id)
                used.add(best.id)
                pairs.append(sorted([trip.id, best.id]))

        return pairs

    def _parse_rule(self, rule: str) -> Dict[str, Any]:
        text = rule.lower().strip()
        parsed: Dict[str, Any] = {}

        def _hours_to_minutes(raw: str) -> int:
            return int(round(float(raw.replace(",", ".")) * 60))

        m = re.search(r"pausa de\s+(\d+)\s+min", text)
        if m:
            parsed.setdefault("min_break_minutes", int(m.group(1)))

        m = re.search(r"após\s+cada\s+(\d+[\.,]?\d*)\s+horas", text)
        if m:
            parsed.setdefault("mandatory_break_after_minutes", _hours_to_minutes(m.group(1)))

        m = re.search(r"máximo de\s+(\d+)\s+horas\s+por\s+semana", text)
        if m:
            parsed.setdefault("weekly_driving_limit_minutes", int(m.group(1)) * 60)

        m = re.search(r"(?:nenhum motorista|motorista)\s+deve\s+trabalhar\s+mais\s+de\s+(\d+[\.,]?\d*)\s+horas", text)
        if m:
            parsed.setdefault("max_shift_minutes", _hours_to_minutes(m.group(1)))

        m = re.search(r"spread\s+(?:máximo|maximo|limitado)?\s*(?:de)?\s*(\d+[\.,]?\d*)\s+horas", text)
        if m:
            parsed.setdefault("max_shift_minutes", _hours_to_minutes(m.group(1)))

        m = re.search(r"reduzir\s+horas\s+extras", text)
        if m:
            parsed.setdefault("goal_weights", {})
            parsed["goal_weights"].setdefault("overtime", 1.0)

        m = re.search(r"reduzir\s+o?\s*spread", text)
        if m:
            parsed.setdefault("goal_weights", {})
            parsed["goal_weights"].setdefault("spread", 0.8)

        m = re.search(r"reduzir\s+deslocamentos?\s+passivos", text)
        if m:
            parsed.setdefault("goal_weights", {})
            parsed["goal_weights"].setdefault("passive_transfer", 0.8)

        m = re.search(r"equidade|balancear\s+jornadas|fairness", text)
        if m:
            parsed.setdefault("goal_weights", {})
            parsed["goal_weights"].setdefault("fairness", 0.5)

        m = re.search(r"descanso\s+interjornada\s+de\s+(\d+)\s*h", text)
        if m:
            parsed.setdefault("inter_shift_rest_minutes", int(m.group(1)) * 60)

        m = re.search(r"descanso\s+semanal\s+de\s+(\d+)\s*h", text)
        if m:
            parsed.setdefault("weekly_rest_minutes", int(m.group(1)) * 60)

        m = re.search(r"máximo de\s+(\d+)\s+jornadas\s+acima\s+de\s+(\d+)\s*horas", text)
        if m:
            parsed.setdefault("max_long_duties_per_period", int(m.group(1)))
            parsed.setdefault("extended_daily_driving_limit_minutes", int(m.group(2)) * 60)

        if "mesmo depósito" in text or "mesmo deposito" in text:
            parsed.setdefault("same_depot_required", True)
            parsed.setdefault("enforce_same_depot_start_end", True)

        return parsed

    def _make_csp(self, cct_params: Dict[str, Any], vsp_params: Dict[str, Any]):
        if vsp_params.get("use_set_covering") or vsp_params.get("pricing_enabled"):
            return self._make_set_covering_csp(cct_params, vsp_params)
        return GreedyCSP(vsp_params=vsp_params, **cct_params)

    def _make_set_covering_csp(self, cct_params: Dict[str, Any], vsp_params: Dict[str, Any]):
        # Usa a versão otimizada por padrão (Nível Optibus)
        # Mantém compatibilidade: se explicitamente desabilitado, usa versão original
        if vsp_params.get("use_original_set_partitioning", False):
            logger.debug("Usando SetPartitioningCSP original (compatibilidade)")
            return SetPartitioningCSP(vsp_params=vsp_params, **cct_params)
        else:
            logger.debug("Usando SetPartitioningOptimizedCSP (Nível Optibus)")
            return SetPartitioningOptimizedCSP(vsp_params=vsp_params, **cct_params)
