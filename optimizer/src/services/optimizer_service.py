"""
OptimizerService — orquestra a seleção e execução de algoritmos.
"""

from __future__ import annotations

import copy
import logging
import math
import re
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from .ai_service import AiService
from .algorithm_dispatcher import dispatch_algorithm
from ..algorithms.ev.soc_tracker import EVSoCTracker
from ..algorithms.relief.estimator import ReliefVehicleEstimator
from .parameter_normalization import (
    align_vsp_params_with_cct as _module_align_vsp_params_with_cct,
    as_dict as _module_as_dict,
    is_strict_trip_group_mode as _module_is_strict_trip_group_mode,
    normalize_rules as _module_normalize_rules,
    parse_rule as _module_parse_rule,
    validate_strict_algorithm_support as _module_validate_strict_algorithm_support,
)
from .trip_group_inference import (
    build_group_inference_report as _module_build_group_inference_report,
    infer_round_trip_pairs as _module_infer_round_trip_pairs,
    inject_trip_group_constraints as _module_inject_trip_group_constraints,
    log_group_inference_report as _module_log_group_inference_report,
    materialize_mandatory_trip_groups as _module_materialize_mandatory_trip_groups,
    summarize_trip_groups as _module_summarize_trip_groups,
)
from .operational_quality_helpers import (
    classify_duty_severity as _module_classify_duty_severity,
    clone_duty_slice as _module_clone_duty_slice,
    duty_exception_rank as _module_duty_exception_rank,
    resolve_operational_quality_mode as _module_resolve_operational_quality_mode,
    scenario_justification as _module_scenario_justification,
    scenario_rejection_reason as _module_scenario_rejection_reason,
    scenario_tradeoffs as _module_scenario_tradeoffs,
    summarize_operational_quality as _module_summarize_operational_quality,
)

from ..algorithms.csp.cp_sat_csp import CPSatCSP
from ..algorithms.csp.greedy import GreedyCSP
from ..algorithms.csp.set_partitioning_optimized import SetPartitioningOptimizedCSP
from ..algorithms.evaluator import CostEvaluator

# Imports de solvers VSP/integrated movidos para algorithm_dispatcher.py (Sprint I).
from ..core.config import get_settings
from ..core.exceptions import (
    HardConstraintViolationError,
    InfeasibleProblemError,
    InvalidAlgorithmError,
    NoProblemDataError,
    OptimizerError,
)
from ..domain.models import AlgorithmType, Block, CSPSolution, Duty, OptimizationResult, Trip, VehicleType, VSPSolution
from .hard_constraint_validator import HardConstraintValidator
from .operational_time_service import summarize_operational_time_reports
from . import replay_fingerprint as _replay
from ..algorithms.utils import is_connection_feasible

settings = get_settings()
logger = logging.getLogger(__name__)


def _finalize_duties(csp: Any, *args: Any, **kwargs: Any) -> CSPSolution:
    if hasattr(csp, "finalize_selected_duties"):
        logger.info("[OP-QUALITY] finalize_duties_method=direct")
        return csp.finalize_selected_duties(*args, **kwargs)

    greedy = getattr(csp, "greedy", None)
    if greedy is not None and hasattr(greedy, "finalize_selected_duties"):
        logger.info("[OP-QUALITY] finalize_duties_method=greedy")
        return greedy.finalize_selected_duties(*args, **kwargs)

    logger.warning("[OP-QUALITY] finalize_duties_method=fallback")
    raise OptimizerError(
        "CSP object does not expose finalize_selected_duties directly or via greedy",
        details={"csp_type": type(csp).__name__},
    )


class OptimizerService:
    def __init__(self) -> None:
        self.evaluator = CostEvaluator()
        self.validator = HardConstraintValidator()
        # NOTE: o dispatch dos solvers (_run_greedy, _run_hybrid, etc) foi extraído para
        # algorithm_dispatcher.py (Sprint I — split incremental do monolito 4287→).
        # `_make_csp` e `_make_set_covering_csp` ainda vivem aqui porque dependem de
        # estado (evaluator, validator) e são injetados como factories no dispatcher.

    def run(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        algorithm: AlgorithmType = AlgorithmType.HYBRID_PIPELINE,
        depot_id: Optional[int] = None,
        depot_ids: Optional[List[int]] = None,
        time_budget_s: Optional[float] = None,
        cct_params: Any = None,
        vsp_params: Any = None,
        optimization_params: Any = None,
        request_metadata: Any = None,
    ) -> OptimizationResult:
        if not trips:
            raise NoProblemDataError("trips list is empty")

        if depot_ids:
            trips = [t for t in trips if t.depot_id is None or t.depot_id in depot_ids]
            if not trips:
                raise NoProblemDataError(f"Nenhuma viagem encontrada para os depots {depot_ids}")

        t0 = time.perf_counter()
        cct_params = self._normalize_rules(cct_params)
        vsp_params = self._normalize_rules(vsp_params)

        # Frontend usa force_round_trip / allow_vehicle_swap (intent-level);
        # solver Python espera enforce_trip_groups_hard / operator_single_vehicle_only
        # (constraint-level). Traduzimos aqui para que o que o usuário marca na tela
        # seja efetivamente aplicado.
        intent_params: Dict[str, Any] = {}
        if optimization_params is not None:
            intent_params.update(
                optimization_params if isinstance(optimization_params, dict) else optimization_params.dict()
            )
        resolved_operational_quality_mode = self._resolve_operational_quality_mode(
            optimization_params=optimization_params,
            vsp_params=vsp_params,
            cct_params=cct_params,
            request_metadata=request_metadata,
        )
        intent_params["operational_quality_mode"] = resolved_operational_quality_mode
        submitted_optimization_params = dict(intent_params)

        # Sincronização de Intenções do Frontend com Parâmetros de Solver
        if intent_params.get("force_round_trip"):
            cct_params["enforce_trip_groups_hard"] = True
            cct_params.setdefault("operator_pairing_hard", True)
            vsp_params.setdefault("preserve_preferred_pairs", True)
            # Aumentar bônus de acoplamento se não definido
            intent_params.setdefault("trip_group_keep_bonus", 500.0)

        if intent_params.get("allow_vehicle_swap") is False:
            cct_params["operator_single_vehicle_only"] = True
            vsp_params["allow_vehicle_swap"] = False

        # BUG-04 fix (auditoria 2026-05-17): propagar TODOS os parâmetros para ambos
        # cct_params e vsp_params causa colisão semântica (ex: "max_shift_minutes" tem
        # significado diferente para veículo vs motorista). Agora usamos whitelist.
        #
        # Parâmetros que só fazem sentido em CCT (tripulação/motorista):
        _CCT_ONLY_KEYS = {
            "max_work_minutes",
            "max_driving_minutes",
            "min_break_minutes",
            "meal_break_minutes",
            "mandatory_break_after_minutes",
            "inter_shift_rest_minutes",
            "min_inter_shift_rest_minutes",
            "max_spread_soft",
            "max_spread_hard",
            "cost_duty",
            "min_paid_hours",
            "overtime_multiplier",
            "overtime_limit_minutes",
            "nocturnal_start_hour",
            "nocturnal_end_hour",
            "nocturnal_extra_pct",
            "holiday_extra_pct",
            "idle_time_is_paid",
            "waiting_time_pay_pct",
            "enforce_trip_groups_hard",
            "operator_pairing_hard",
            "operator_single_vehicle_only",
            "operator_change_terminals_only",
            "enforce_single_line_duty",
            "daily_driving_limit_minutes",
            "long_unpaid_break_limit_minutes",
            "long_unpaid_break_penalty_weight",
        }
        # Parâmetros que só fazem sentido em VSP (veículos):
        _VSP_ONLY_KEYS = {
            "max_vehicle_shift_minutes",
            "max_block_duration_minutes",
            "fixed_vehicle_activation_cost",
            "deadhead_cost_per_minute",
            "idle_cost_per_minute",
            "allow_multi_line_block",
            "allow_vehicle_swap",
            "same_depot_required",
            "preserve_preferred_pairs",
            "preferred_pair_window_minutes",
            "pair_break_penalty",
            "paired_trip_bonus",
            "hard_pairing_vehicle_level",
            "hard_pairing_penalty",
            "vehicle_idle_gap_behavior",
            "vehicle_idle_gap_threshold_minutes",
            "mcnf_ilp_timeout_seconds",
            "timetable_slack_minutes",
            "timetable_slack_step_minutes",
            "max_vsp_metaheuristic_trips",
            "max_vsp_metaheuristic_blocks",
            "force_vsp_metaheuristics",
            "algorithm_preference",
        }
        # Compartilhados (cabem em ambos os namespaces):
        _SHARED_KEYS = {
            "min_layover_minutes",
            "enforce_min_interval",
            "strict_min_interval",
            "connection_tolerance_minutes",
            "enforce_same_depot_start_end",
            "force_round_trip",
            "trip_group_keep_bonus",
            "strict_hard_validation",
            "pullout_minutes",
            "pullback_minutes",
            "pullout_counts_in_driver_shift",
            "pullback_counts_in_driver_shift",
            "random_seed",
            "time_budget_s",
            "operational_quality_mode",
            "dynamic_rules",
        }
        for key, value in intent_params.items():
            if key in ("trips", "vehicle_types"):
                continue
            in_cct = key in _CCT_ONLY_KEYS or key in _SHARED_KEYS
            in_vsp = key in _VSP_ONLY_KEYS or key in _SHARED_KEYS
            if not in_cct and not in_vsp:
                # Não conhecido — propaga para ambos (compat) mas registra
                logger.debug("[PARAMS-UNKNOWN] key=%s propagada para CCT+VSP (compat)", key)
                cct_params[key] = value
                vsp_params[key] = value
                continue
            if in_cct:
                cct_params[key] = value
            if in_vsp:
                vsp_params[key] = value

        # Mapeamentos específicos de nomes legados.
        # Preferimos `vehicle_fixed_cost` (custo fixo diário do veículo) quando disponível;
        # `cost_vehicle` é fallback legado e historicamente vinha sobrescrito com valor inflado
        # (ex.: custo mensal/anual em vez de diário), inflacionando o total em ~14×.
        if intent_params.get("vehicle_fixed_cost"):
            vsp_params["fixed_vehicle_activation_cost"] = intent_params["vehicle_fixed_cost"]
        elif intent_params.get("cost_vehicle"):
            vsp_params["fixed_vehicle_activation_cost"] = intent_params["cost_vehicle"]
        if intent_params.get("cost_km"):
            vsp_params["deadhead_cost_per_minute"] = intent_params["cost_km"]
        if intent_params.get("cost_duty"):
            cct_params["cost_duty"] = intent_params["cost_duty"]
        if intent_params.get("max_shift_minutes"):
            vsp_params["max_vehicle_shift_minutes"] = intent_params["max_shift_minutes"]

        self._align_vsp_params_with_cct(cct_params, vsp_params)
        logger.info(
            "[OP-QUALITY] run started mode=%s algorithm=%s trips=%d",
            resolved_operational_quality_mode,
            algorithm.value if hasattr(algorithm, "value") else str(algorithm),
            len(trips),
        )
        logger.warning(
            "[PARAMS-AUDIT] cct enforce_min_interval=%s min_break=%s min_layover=%s tolerance=%s | "
            "vsp enforce_min_interval=%s min_layover=%s tolerance=%s",
            cct_params.get("enforce_min_interval"),
            cct_params.get("min_break_minutes"),
            cct_params.get("min_layover_minutes"),
            cct_params.get("connection_tolerance_minutes"),
            vsp_params.get("enforce_min_interval"),
            vsp_params.get("min_layover_minutes"),
            vsp_params.get("connection_tolerance_minutes"),
        )
        if bool(vsp_params.get("force_round_trip", False)):
            cct_params.setdefault("enforce_trip_groups_hard", True)
            cct_params.setdefault("operator_pairing_hard", True)
        if bool(vsp_params.get("enforce_same_depot_start_end", False)):
            cct_params.setdefault("enforce_same_depot_start_end", True)
        effective_optimization_params = {
            **cct_params,
            **vsp_params,
            **intent_params,
        }
        normalized_time_budget_s = (
            float(time_budget_s)
            if time_budget_s is not None
            else float(vsp_params.get("time_budget_s") or settings.hybrid_time_budget_seconds or 60)
        )
        if vsp_params.get("random_seed") is None:
            deterministic_seed = self._derive_deterministic_seed(
                trips,
                algorithm,
                cct_params,
                vsp_params,
                normalized_time_budget_s,
            )
            vsp_params["random_seed"] = deterministic_seed
            effective_optimization_params["random_seed"] = deterministic_seed
        submitted_cct_params = dict(cct_params)
        submitted_vsp_params = dict(vsp_params)

        # [PIPELINE SAFETY] O orçamento deve ser pelo menos 2 min menor que o soft limit do Celery
        # para garantir o graceful shutdown (SIGTERM -> save result -> return JSON).
        max_safe_budget = settings.celery_task_soft_time_limit - 120
        if normalized_time_budget_s > max_safe_budget:
            logger.warning(
                f"[SAFETY] Orçamento solicitado ({normalized_time_budget_s}s) excede o limite de segurança "
                f"do Celery. Capeando para {max_safe_budget}s."
            )
            normalized_time_budget_s = float(max_safe_budget)
        replay_fingerprint = self._build_replay_fingerprint(
            trips,
            algorithm,
            cct_params,
            vsp_params,
            normalized_time_budget_s,
        )
        had_explicit_mandatory_groups = bool(cct_params.get("mandatory_trip_groups_same_duty"))
        group_inference_report = self._build_group_inference_report(trips, request_metadata)
        self._inject_trip_group_constraints(trips, cct_params, vsp_params)
        group_inference_report["optimizer_effective_stats"] = self._summarize_trip_groups(trips)
        group_inference_report["inference_applied"] = int(
            group_inference_report["optimizer_effective_stats"].get("group_count", 0)
        ) != int(group_inference_report["optimizer_input_stats"].get("group_count", 0)) or int(
            group_inference_report["optimizer_effective_stats"].get("grouped_trip_count", 0)
        ) != int(
            group_inference_report["optimizer_input_stats"].get("grouped_trip_count", 0)
        )
        self._log_group_inference_report(group_inference_report)
        run_snapshot = self._build_run_snapshot(
            trips,
            vehicle_types,
            algorithm,
            submitted_cct_params,
            submitted_vsp_params,
            submitted_optimization_params,
            cct_params,
            vsp_params,
            effective_optimization_params,
            normalized_time_budget_s,
            replay_fingerprint,
            group_inference_report,
            request_metadata,
        )
        if not had_explicit_mandatory_groups and not bool(cct_params.get("enforce_trip_groups_hard", False)):
            cct_params.pop("mandatory_trip_groups_same_duty", None)
        self._ensure_deadhead_coverage(trips, vsp_params)

        strict_hard_validation = bool(
            vsp_params.get("strict_hard_validation", cct_params.get("strict_hard_validation", False))
        )
        group_infeasibility_mode = self._group_infeasibility_mode(
            cct_params,
            vsp_params,
            effective_optimization_params,
            request_metadata,
        )
        self._validate_strict_algorithm_support(algorithm, trips, cct_params, vsp_params)

        t_input = time.perf_counter()
        input_report = self.validator.audit_input(trips, cct_params, vsp_params)
        input_validation_ms = (time.perf_counter() - t_input) * 1000
        if not input_report["ok"]:
            raise HardConstraintViolationError(
                input_report["issues"],
                details=self.build_failure_payload(
                    HardConstraintViolationError(input_report["issues"]),
                    trips,
                    vehicle_types,
                    algorithm,
                    cct_params,
                    vsp_params,
                    effective_optimization_params,
                    request_metadata=request_metadata,
                    stage="input_validation",
                    replay_fingerprint=replay_fingerprint,
                    run_snapshot=run_snapshot,
                ),
            )

        scale_profile = self._build_scale_profile(trips, cct_params, vsp_params)
        t_solver = time.perf_counter()
        try:
            if self._should_use_scale_decomposition(algorithm, trips, cct_params, vsp_params, scale_profile):
                result = self._run_decomposed_hybrid(
                    trips,
                    vehicle_types,
                    depot_id,
                    cct_params,
                    vsp_params,
                    effective_optimization_params,
                    normalized_time_budget_s,
                    scale_profile,
                )
            else:
                result = self._dispatch(
                    algorithm,
                    trips,
                    vehicle_types,
                    depot_id,
                    cct_params,
                    vsp_params,
                    effective_optimization_params,
                    normalized_time_budget_s,
                )
        except OptimizerError as exc:
            details = dict(getattr(exc, "details", {}) or {})
            details.setdefault("group_inference_report", group_inference_report)
            details.setdefault("run_snapshot", run_snapshot)
            if "failed_chunks" in details and "hard_constraint_report" not in details:
                details["hard_constraint_report"] = self._build_scale_failure_hard_constraint_report(
                    details.get("failed_chunks") or []
                )
            exc.details = details
            # Degradação graciosa: se a decomposição em escala falhou por violação dura
            # num chunk (ex: SPREAD_EXCEEDED — deadhead infla o spread do motorista), o
            # solver monolítico resolve a instância inteira (reporta issues em vez de
            # abortar, como greedy/mcnf). MANDATORY_GROUP_SPLIT continua sendo surfaceada
            # (infeasibility real de grupo, ver CLAUDE.md invariante ==1).
            exc_code = getattr(exc, "code", None)
            if (
                exc_code == "SCALE_CHUNK_FAILED"
                and not bool(vsp_params.get("disable_scale_decomposition", False))
                and not bool(vsp_params.get("disable_scale_decomposition_fallback", False))
            ):
                logger.warning(
                    "[OptimizerService] Scale decomposition failed (%s); retrying monolithic.", exc_code
                )
                mono_vsp = dict(vsp_params)
                mono_vsp["disable_scale_decomposition"] = True
                result = self._dispatch(
                    algorithm,
                    trips,
                    vehicle_types,
                    depot_id,
                    cct_params,
                    mono_vsp,
                    effective_optimization_params,
                    normalized_time_budget_s,
                )
                result.meta.setdefault("performance", {})
                result.meta["performance"]["scale_decomposition_fallback"] = {
                    "reason": exc_code,
                    "failed_chunks": (details.get("failed_chunks") or [])[:5],
                    "strategy": "monolithic_retry",
                }
            else:
                raise
        primary_trip_group_audit = self._build_trip_group_audit(result, trips)

        def _group_audit_rank(sol: OptimizationResult, audit: Dict[str, Any]) -> tuple:
            quality = (
                ((sol.csp.meta or {}).get("quality_summary") or {}) if getattr(sol, "csp", None) is not None else {}
            )
            return (
                int(audit.get("split_groups", 0)),
                -float(audit.get("same_roster_ratio", 0.0) or 0.0),
                int(getattr(sol.csp, "cct_violations", 0) or 0),
                int(quality.get("low_utilization_duties", 0) or 0),
                int(quality.get("high_spread_duties", 0) or 0),
                int(quality.get("fragmented_duties", 0) or 0),
                int(quality.get("short_connection_total", 0) or 0),
                -float(quality.get("avg_utilization", 0.0) or 0.0),
                float(sol.total_cost or 0.0),
                len(sol.vsp.blocks or []),
                len(sol.csp.duties or []),
            )

        if primary_trip_group_audit:
            result.meta["trip_group_audit"] = primary_trip_group_audit

        fallback_max_trips = int(vsp_params.get("group_audit_fallback_max_trips", 220) or 220)
        fallback_max_blocks = int(vsp_params.get("group_audit_fallback_max_blocks", 160) or 160)
        strict_group_mode = self._strict_trip_group_mode(trips, cct_params, vsp_params)
        strict_fallback_max_trips = int(vsp_params.get("strict_group_fallback_max_trips", 1000) or 1000)
        strict_fallback_max_blocks = int(vsp_params.get("strict_group_fallback_max_blocks", 1000) or 1000)
        standard_fallback_allowed = (
            len(trips) <= fallback_max_trips and len(result.vsp.blocks or []) <= fallback_max_blocks
        )
        strict_fallback_allowed = (
            strict_group_mode
            and len(trips) <= strict_fallback_max_trips
            and len(result.vsp.blocks or []) <= strict_fallback_max_blocks
        )
        fallback_allowed = standard_fallback_allowed or strict_fallback_allowed

        if (
            str(algorithm.value if hasattr(algorithm, "value") else algorithm) == AlgorithmType.HYBRID_PIPELINE.value
            and int(primary_trip_group_audit.get("split_groups", 0)) > 0
            and not bool(vsp_params.get("disable_group_audit_fallback", False))
            and fallback_allowed
        ):
            fallback_algorithm = AlgorithmType.GREEDY if strict_group_mode else AlgorithmType.SIMULATED_ANNEALING
            fallback_runs = 1 if strict_group_mode else 2
            fallback_time_budget_s = max(45.0, normalized_time_budget_s * 0.25)
            fallback_seed_base_raw = replay_fingerprint.get("input_hash")
            try:
                fallback_seed_base = (
                    int(str(fallback_seed_base_raw), 16) if fallback_seed_base_raw else int(time.time() * 1000)
                )
            except (TypeError, ValueError):
                fallback_seed_base = int(time.time() * 1000)

            best_fallback_result = None
            best_fallback_audit = None
            best_fallback_rank = None
            for attempt in range(fallback_runs):
                fallback_vsp_params = dict(vsp_params)
                fallback_vsp_params["random_seed"] = fallback_seed_base + (attempt * 97)
                fallback_result = self._dispatch(
                    fallback_algorithm,
                    trips,
                    vehicle_types,
                    depot_id,
                    cct_params,
                    fallback_vsp_params,
                    effective_optimization_params,
                    fallback_time_budget_s,
                )
                fallback_trip_group_audit = self._build_trip_group_audit(fallback_result, trips)
                fallback_result.meta["trip_group_audit"] = fallback_trip_group_audit
                fallback_rank = _group_audit_rank(fallback_result, fallback_trip_group_audit)
                if best_fallback_rank is None or fallback_rank < best_fallback_rank:
                    best_fallback_result = fallback_result
                    best_fallback_audit = fallback_trip_group_audit
                    best_fallback_rank = fallback_rank

            if best_fallback_result is not None and best_fallback_audit is not None and best_fallback_rank is not None:
                if best_fallback_rank < _group_audit_rank(result, primary_trip_group_audit):
                    before_split_groups = int(primary_trip_group_audit.get("split_groups", 0))
                    after_split_groups = int(best_fallback_audit.get("split_groups", 0))
                    logger.info(
                        "[OptimizerService] Hybrid fallback (%s) accepted: split_groups %d -> %d",
                        fallback_algorithm.value,
                        before_split_groups,
                        after_split_groups,
                    )
                    result = best_fallback_result
                    primary_trip_group_audit = best_fallback_audit
                    result.meta.setdefault("performance", {})
                    result.meta["performance"]["group_audit_fallback"] = {
                        "reason": "strict_group_repair" if strict_group_mode else "group_audit_repair",
                        "algorithm": fallback_algorithm.value,
                        "attempts": fallback_runs,
                        "before_split_groups": before_split_groups,
                        "after_split_groups": after_split_groups,
                    }
        elif (
            str(algorithm.value if hasattr(algorithm, "value") else algorithm) == AlgorithmType.HYBRID_PIPELINE.value
            and int(primary_trip_group_audit.get("split_groups", 0)) > 0
            and not fallback_allowed
        ):
            result.meta.setdefault("performance", {})
            result.meta["performance"]["group_audit_fallback_skipped"] = {
                "reason": "instance_scale_guard",
                "trip_count": len(trips),
                "block_count": len(result.vsp.blocks or []),
                "max_trips": fallback_max_trips,
                "max_blocks": fallback_max_blocks,
                "strict_group_mode": strict_group_mode,
                "strict_max_trips": strict_fallback_max_trips,
                "strict_max_blocks": strict_fallback_max_blocks,
            }

        if (
            str(algorithm.value if hasattr(algorithm, "value") else algorithm) == AlgorithmType.HYBRID_PIPELINE.value
            and strict_group_mode
            and int(primary_trip_group_audit.get("split_groups", 0)) > 0
            and fallback_allowed
        ):
            try:
                repaired_result = self._repair_split_trip_groups_with_dedicated_blocks(
                    result,
                    trips,
                    cct_params,
                    vsp_params,
                    effective_optimization_params,
                )
            except OptimizerError as exc:
                if getattr(exc, "code", None) != "GROUP_INFEASIBLE":
                    raise
                result = self._apply_group_infeasibility_policy(
                    result,
                    primary_trip_group_audit,
                    exc,
                    group_infeasibility_mode,
                    trips,
                    stage="group_repair",
                )
                repaired_result = None
            if repaired_result is not None:
                repaired_audit = self._build_trip_group_audit(repaired_result, trips)
                repaired_result.meta["trip_group_audit"] = repaired_audit
                if _group_audit_rank(repaired_result, repaired_audit) < _group_audit_rank(
                    result, primary_trip_group_audit
                ):
                    before_split_groups = int(primary_trip_group_audit.get("split_groups", 0))
                    after_split_groups = int(repaired_audit.get("split_groups", 0))
                    logger.info(
                        "[OptimizerService] Dedicated block group repair accepted: split_groups %d -> %d",
                        before_split_groups,
                        after_split_groups,
                    )
                    result = repaired_result
                    primary_trip_group_audit = repaired_audit
                    result.meta.setdefault("performance", {})
                    result.meta["performance"]["group_audit_repair"] = {
                        "reason": "strict_group_dedicated_blocks",
                        "before_split_groups": before_split_groups,
                        "after_split_groups": after_split_groups,
                    }

        self._ensure_vsp_operational_warnings(result, vehicle_types, vsp_params)
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
        non_strict_blocking_output_issues = []
        if not strict_hard_validation:
            non_strict_blocking_output_issues = self._blocking_output_issues_without_strict(
                output_report,
                cct_params,
            )
        if strict_hard_validation and not output_report["ok"]:
            if self._is_controlled_group_relaxation(result, output_report, group_infeasibility_mode):
                result.meta["hard_constraint_report"]["strict_relaxation_override"] = {
                    "mode": group_infeasibility_mode,
                    "reason": "GROUP_INFEASIBLE controlled production relaxation",
                    "hard_issues_preserved": list(output_report.get("hard_issues") or []),
                    "relaxed_constraints": list(
                        (result.meta.get("group_infeasibility_handling") or {}).get("relaxed_constraints") or []
                    ),
                    "affected_groups": list(
                        (result.meta.get("group_infeasibility_handling") or {}).get("affected_groups") or []
                    ),
                }
            else:
                raise HardConstraintViolationError(
                    output_report["issues"],
                    details=self.build_failure_payload(
                        HardConstraintViolationError(output_report["issues"]),
                        trips,
                        vehicle_types,
                        algorithm,
                        cct_params,
                        vsp_params,
                        effective_optimization_params,
                        request_metadata=request_metadata,
                        stage="output_validation",
                        replay_fingerprint=replay_fingerprint,
                        run_snapshot=run_snapshot,
                    ),
                )
        elif non_strict_blocking_output_issues:
            raise HardConstraintViolationError(
                non_strict_blocking_output_issues,
                details=self.build_failure_payload(
                    HardConstraintViolationError(non_strict_blocking_output_issues),
                    trips,
                    vehicle_types,
                    algorithm,
                    cct_params,
                    vsp_params,
                    effective_optimization_params,
                    request_metadata=request_metadata,
                    stage="output_validation",
                    replay_fingerprint=replay_fingerprint,
                    run_snapshot=run_snapshot,
                ),
            )

        t_audit = time.perf_counter()
        # Injetar regras dinâmicas e pesos de custo no avaliador
        self.evaluator.set_dynamic_rules(cct_params.get("dynamic_rules") or [])

        # Configurar pesos de custo e regras de negócio usando o DTO unificado
        if effective_optimization_params:
            self.evaluator.set_costs(effective_optimization_params)
            result.meta["ilp_timeout_seconds"] = int(
                effective_optimization_params.get("ilp_timeout_seconds", 120) or 120
            )

        cost_breakdown = self.evaluator.total_cost_breakdown(result, vehicle_types)
        result.total_cost = float(cost_breakdown["total"])
        result.meta["cost_breakdown"] = cost_breakdown

        # EV fleet SoC report (apenas quando VehicleType é elétrico e há solução VSP)
        ev_vehicle = next((v for v in vehicle_types if getattr(v, "is_electric", False)), None)
        if ev_vehicle and result.vsp and result.vsp.blocks:
            kwh_per_km = float((vsp_params or {}).get("ev_kwh_per_km", 1.8) or 1.8)
            try:
                tracker = EVSoCTracker(ev_vehicle, kwh_per_km=kwh_per_km)
                soc_report = tracker.track(result.vsp)
                result.meta["ev_soc_report"] = soc_report.to_dict()
            except Exception as _e:  # noqa: BLE001
                logger.warning("EVSoCTracker falhou: %s", _e)

        # Relief vehicle estimate (quando há jornadas CSP com rendições entre motoristas)
        if result.csp and result.csp.duties:
            try:
                rv_est = ReliefVehicleEstimator()
                result.meta["relief_vehicle_estimate"] = rv_est.estimate(result.csp).to_dict()
            except Exception as _e:  # noqa: BLE001
                logger.warning("ReliefVehicleEstimator falhou: %s", _e)

        result.meta["roster_count"] = result.csp.meta.get("roster_count", 0)
        result.meta["operational_time_reports"] = summarize_operational_time_reports(result.csp.duties or [])
        result.meta["operational_kpis"] = self._build_operational_kpis(result, cct_params)
        result.meta["trip_group_audit"] = self._build_trip_group_audit(result, trips)
        result.meta["phase_summary"] = self._build_phase_summary(result, cost_breakdown)
        result.meta["parameter_effect_report"] = self._build_parameter_effect_report(
            result,
            trips,
            cct_params,
            vsp_params,
        )
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
                "submitted_cct_params": submitted_cct_params,
                "submitted_vsp_params": submitted_vsp_params,
                "submitted_optimization_params": submitted_optimization_params,
                "cct_params": cct_params,
                "vsp_params": vsp_params,
                "optimization_params": effective_optimization_params,
                "request_metadata": dict(request_metadata or {}),
                "replay_fingerprint": replay_fingerprint,
                "group_inference_report": group_inference_report,
                "run_snapshot": run_snapshot,
            }
        )
        result.meta["run_snapshot"] = run_snapshot
        result = self._apply_operational_quality_mode(
            result=result,
            trips=trips,
            vehicle_types=vehicle_types,
            cct_params=cct_params,
            vsp_params=vsp_params,
            optimization_params=effective_optimization_params,
        )
        result = self._ensure_operational_quality_decision(
            result=result,
            trips=trips,
            vehicle_types=vehicle_types,
            cct_params=cct_params,
            vsp_params=vsp_params,
            optimization_params=effective_optimization_params,
        )

        # ── AI Copilot: insight em linguagem natural (nice-to-have) ──────────
        # Mantido fora do caminho crítico do solver. Se não estiver explicitamente
        # habilitado, não bloqueia a resposta da otimização.
        result.meta["ai_copilot_insight"] = None
        if bool(vsp_params.get("enable_ai_copilot", False)):
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
                    "covered_trips": sum(len(block.trips) for block in (result.vsp.blocks or [])),
                    "total_trips": len(trips),
                    "cct_violations": int(result.csp.cct_violations or 0),
                    "work_minutes": int(op_kpis.get("work_minutes", 0) or 0),
                    "paid_minutes": int(op_kpis.get("paid_minutes", 0) or 0),
                    "dominant_vsp": ((phase_sum.get("vsp") or {}).get("dominant_cost_component") or {}).get(
                        "component", "N/A"
                    ),
                    "dominant_csp": ((phase_sum.get("csp") or {}).get("dominant_cost_component") or {}).get(
                        "component", "N/A"
                    ),
                    "status": (result.meta.get("solver_explanation") or {}).get("status", "feasible"),
                }
                result.meta["ai_copilot_insight"] = AiService().generate_insight_sync(ai_metrics)
            except Exception as _ai_exc:
                logger.warning("[AI Copilot] Falha ao gerar insight (não crítico): %s", _ai_exc)
                result.meta["ai_copilot_insight"] = None

        return result

    def _blocking_output_issues_without_strict(
        self,
        output_report: Dict[str, Any],
        cct_params: Dict[str, Any],
    ) -> List[str]:
        hard_issues = list(output_report.get("hard_issues") or [])
        if not hard_issues:
            return []

        operator_profiles = list(cct_params.get("operator_profiles") or [])
        if not operator_profiles or not bool(cct_params.get("strict_union_rules", True)):
            return []

        blocking_prefixes = (
            "UNASSIGNED_OPERATOR_PROFILE",
            "UNKNOWN_OPERATOR_PROFILE",
            "MANDATORY_SHIFT_PREFERENCE_VIOLATION",
            "MANDATORY_LINE_PREFERENCE_VIOLATION",
        )
        return [issue for issue in hard_issues if issue.startswith(blocking_prefixes)]

    def build_failure_payload(
        self,
        exc: Exception,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        algorithm: AlgorithmType | str,
        cct_params: Dict[str, Any] | None,
        vsp_params: Dict[str, Any] | None,
        optimization_params: Dict[str, Any] | None,
        request_metadata: Any = None,
        stage: str = "solver",
        replay_fingerprint: Optional[Dict[str, Any]] = None,
        run_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cct_params = cct_params or {}
        vsp_params = vsp_params or {}
        optimization_params = optimization_params or {}
        replay_fingerprint = replay_fingerprint or self._build_replay_fingerprint(
            trips,
            algorithm,
            cct_params,
            vsp_params,
            float(
                vsp_params.get("time_budget_s", settings.hybrid_time_budget_seconds)
                or settings.hybrid_time_budget_seconds
            ),
        )
        run_snapshot = run_snapshot or self._build_run_snapshot(
            trips,
            vehicle_types,
            algorithm,
            cct_params,
            vsp_params,
            optimization_params,
            cct_params,
            vsp_params,
            optimization_params,
            float(replay_fingerprint.get("time_budget_s") or settings.hybrid_time_budget_seconds),
            replay_fingerprint,
            self._build_group_inference_report(trips, request_metadata),
            request_metadata,
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
                "primary_issue_codes": (
                    infeasibility_reason.get("primary_issue_codes", []) if infeasibility_reason else []
                ),
                "recommendations": self._build_recommendations(issue_strings, [], {"split_groups": 0}),
            },
            "input_snapshot": {
                "algorithm": algorithm_name,
                "trip_count": len(trips),
                "line_ids": sorted({int(trip.line_id) for trip in trips}) if trips else [],
                "cct_params": cct_params,
                "vsp_params": vsp_params,
                "optimization_params": optimization_params,
                "input_hash": replay_fingerprint.get("input_hash"),
                "params_hash": replay_fingerprint.get("params_hash"),
                "time_budget_s": replay_fingerprint.get("time_budget_s"),
            },
            "run_snapshot": run_snapshot,
        }

    def _group_infeasibility_mode(
        self,
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        optimization_params: Dict[str, Any],
        request_metadata: Any = None,
    ) -> str:
        metadata = dict(request_metadata or {})
        raw = (
            metadata.get("group_infeasibility_mode")
            or optimization_params.get("group_infeasibility_mode")
            or vsp_params.get("group_infeasibility_mode")
            or cct_params.get("group_infeasibility_mode")
            or "strict"
        )
        mode = str(raw).strip().lower()
        if mode not in {"strict", "production", "assisted"}:
            return "strict"
        return mode

    def _group_infeasibility_details(
        self,
        exc: OptimizerError,
        audit: Dict[str, Any],
        trips: List[Trip],
        stage: str,
        mode: str,
    ) -> Dict[str, Any]:
        exc_details = dict(getattr(exc, "details", {}) or {})
        affected_groups: List[Dict[str, Any]] = []
        if exc_details.get("group_id") is not None or exc_details.get("trip_ids"):
            affected_groups.append(
                {
                    "trip_group_id": exc_details.get("group_id"),
                    "trip_ids": list(exc_details.get("trip_ids") or []),
                    "reason_code": exc_details.get("reason_code", "GROUP_INFEASIBLE"),
                    "issues": list(exc_details.get("issues") or []),
                }
            )
        for sample in audit.get("sample_splits") or []:
            group_id = sample.get("trip_group_id")
            if any(item.get("trip_group_id") == group_id for item in affected_groups):
                continue
            affected_groups.append(
                {
                    "trip_group_id": group_id,
                    "trip_ids": list(sample.get("trip_ids") or []),
                    "reason_code": "MANDATORY_GROUP_SPLIT",
                    "block_ids": list(sample.get("block_ids") or []),
                    "duty_ids": list(sample.get("duty_ids") or []),
                    "roster_ids": list(sample.get("roster_ids") or []),
                }
            )
        grouped_trip_ids = {int(trip.id) for trip in trips if getattr(trip, "trip_group_id", None) is not None}
        return {
            "mode": mode,
            "stage": stage,
            "error_code": "GROUP_INFEASIBLE",
            "message": str(exc),
            "relaxed_constraints": [
                {
                    "constraint": "mandatory_trip_group_same_roster",
                    "relaxation": "minimal_group_break",
                    "control": "only affected groups listed in affected_groups",
                }
            ],
            "affected_groups": affected_groups[:20],
            "trip_group_audit": audit,
            "grouped_trip_count": len(grouped_trip_ids),
            "recommendation": exc_details.get(
                "recommendation",
                "Revise os trip_group_id/pairId ou autorize intervenção manual para os grupos listados.",
            ),
        }

    def _apply_group_infeasibility_policy(
        self,
        result: OptimizationResult,
        audit: Dict[str, Any],
        exc: OptimizerError,
        mode: str,
        trips: List[Trip],
        stage: str,
    ) -> OptimizationResult:
        details = self._group_infeasibility_details(exc, audit, trips, stage, mode)
        if mode == "production":
            result.meta["group_infeasibility_handling"] = {
                **details,
                "status": "relaxed",
                "explanation": (
                    "GROUP_INFEASIBLE confirmado. A execução retornou a melhor solução encontrada "
                    "com quebra mínima e auditada dos grupos afetados."
                ),
            }
            result.meta["relaxed_constraints"] = details["relaxed_constraints"]
            result.meta["affected_groups"] = details["affected_groups"]
            warning = "GROUP_INFEASIBLE_RELAXED mode=production"
            if warning not in result.vsp.warnings:
                result.vsp.warnings.append(warning)
            return result

        assisted_details = {
            **dict(getattr(exc, "details", {}) or {}),
            "group_infeasibility_handling": {
                **details,
                "status": "manual_intervention_required" if mode == "assisted" else "failed",
            },
            "affected_groups": details["affected_groups"],
            "relaxed_constraints": [] if mode != "production" else details["relaxed_constraints"],
        }
        raise OptimizerError(
            "GROUP_INFEASIBLE requer intervenção manual." if mode == "assisted" else str(exc),
            code="GROUP_INFEASIBLE",
            details=assisted_details,
        )

    def _is_controlled_group_relaxation(
        self,
        result: OptimizationResult,
        output_report: Dict[str, Any],
        mode: str,
    ) -> bool:
        if mode != "production":
            return False
        if not (result.meta or {}).get("group_infeasibility_handling"):
            return False
        hard_issues = [str(item) for item in output_report.get("hard_issues") or []]
        if not hard_issues:
            return False
        allowed_prefixes = ("MANDATORY_GROUP_SPLIT",)
        return all(any(issue.startswith(prefix) for prefix in allowed_prefixes) for issue in hard_issues)

    def _connection_block_reason(
        self,
        current: Trip,
        nxt: Trip,
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        gap = int(nxt.start_time) - int(current.end_time)
        if gap < 0:
            return "overlap", {"gap": gap}

        min_layover = int(vsp_params.get("min_layover_minutes", cct_params.get("min_layover_minutes", 8)) or 8)
        min_break = int(cct_params.get("min_break_minutes", vsp_params.get("min_break_minutes", 30)) or 30)
        enforce_min_interval = bool(
            vsp_params.get("enforce_min_interval", cct_params.get("enforce_min_interval", False))
        )
        strict_zero_gap_validation = bool(
            vsp_params.get("strict_zero_gap_validation", cct_params.get("strict_zero_gap_validation", False))
        )
        max_vehicle_shift = int(
            vsp_params.get("max_vehicle_shift_minutes", cct_params.get("max_vehicle_shift_minutes", 960)) or 960
        )
        deadhead = int(current.deadhead_times.get(nxt.origin_id, 0))

        if gap == 0 and strict_zero_gap_validation and current.destination_id != nxt.origin_id:
            return "zero_gap", {"gap": gap, "from_terminal": current.destination_id, "to_terminal": nxt.origin_id}
        if enforce_min_interval and 0 < gap < min_break:
            return "min_break", {"gap": gap, "limit": min_break}
        if gap < max(min_layover, deadhead):
            return "min_connection_time", {"gap": gap, "limit": max(min_layover, deadhead), "deadhead": deadhead}
        if max_vehicle_shift > 0 and int(nxt.end_time) - int(current.start_time) > max_vehicle_shift:
            return "max_shift_minutes", {
                "spread": int(nxt.end_time) - int(current.start_time),
                "limit": max_vehicle_shift,
            }
        return None

    def _build_parameter_effect_report(
        self,
        result: OptimizationResult,
        trips: List[Trip],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        min_break = int(cct_params.get("min_break_minutes", vsp_params.get("min_break_minutes", 30)) or 30)
        min_connection = int(vsp_params.get("min_layover_minutes", cct_params.get("min_layover_minutes", 8)) or 8)
        max_shift = int(cct_params.get("max_shift_minutes", 480) or 480)
        max_driving = int(cct_params.get("max_driving_minutes", 270) or 270)
        mandatory_break_after = int(cct_params.get("mandatory_break_after_minutes", max_driving) or max_driving)
        meal_break = int(cct_params.get("meal_break_minutes", min_break) or min_break)
        pullout = int(cct_params.get("pullout_minutes", vsp_params.get("pullout_minutes", 0)) or 0)
        pullback = int(cct_params.get("pullback_minutes", vsp_params.get("pullback_minutes", 0)) or 0)
        enforce_min_interval = bool(
            vsp_params.get("enforce_min_interval", cct_params.get("enforce_min_interval", False))
        )
        strict_zero_gap = bool(
            vsp_params.get("strict_zero_gap_validation", cct_params.get("strict_zero_gap_validation", False))
        )
        allow_vehicle_swap = bool(
            vsp_params.get("allow_vehicle_swap", not cct_params.get("operator_single_vehicle_only", False))
        )
        output_report = ((result.meta or {}).get("hard_constraint_report") or {}).get("output") or {}
        operational_time_reports = ((result.meta or {}).get("operational_time_reports") or {}).get("duties") or []
        issue_counts = Counter(str(issue).split(" ", 1)[0] for issue in output_report.get("issues") or [])

        blocked_by_constraint: Counter[str] = Counter()
        samples: List[Dict[str, Any]] = []
        ordered = sorted(trips, key=lambda item: (item.start_time, item.end_time, item.id))
        max_sample_gap = max(min_connection, min_break, 60)
        for idx, current in enumerate(ordered):
            for nxt in ordered[idx + 1 :]:
                gap = int(nxt.start_time) - int(current.end_time)
                if gap > max_sample_gap:
                    break
                reason = self._connection_block_reason(current, nxt, cct_params, vsp_params)
                if reason is None:
                    continue
                code, context = reason
                if code == "overlap":
                    continue
                blocked_by_constraint[code] += 1
                if len(samples) < 20:
                    samples.append(
                        {
                            "constraint": code,
                            "phase": "vsp_candidate",
                            "from_trip_id": int(current.id),
                            "to_trip_id": int(nxt.id),
                            **context,
                        }
                    )

        for duty in result.csp.duties or []:
            if int(getattr(duty, "spread_time", 0) or 0) > max_shift:
                blocked_by_constraint["max_shift_minutes"] += 1
            meta_drive = int((duty.meta or {}).get("max_continuous_drive_minutes", 0) or 0)
            if getattr(duty, "continuous_driving_violation", False) or meta_drive > max_driving:
                blocked_by_constraint["max_driving_minutes"] += 1
            operational_report = duty.meta.get("operational_time_report") or {}
            if operational_report.get("mandatory_rest_required") and not operational_report.get(
                "has_valid_mandatory_rest"
            ):
                blocked_by_constraint["mandatory_rest"] += 1
            if operational_report.get("invalid_rest_position"):
                blocked_by_constraint["idle_classification"] += 1
            if not allow_vehicle_swap and issue_counts.get("OPERATOR_MULTIPLE_VEHICLES", 0):
                blocked_by_constraint["allow_vehicle_swap"] += issue_counts["OPERATOR_MULTIPLE_VEHICLES"]

        performance = (result.meta or {}).get("performance") or {}
        scale_perf = performance.get("scale_decomposition") or {}
        stitching = (
            scale_perf.get("stitching")
            or ((result.vsp.meta or {}).get("scale_decomposition") or {}).get("stitching")
            or {}
        )
        fallback_meta = {
            "group_audit_fallback": performance.get("group_audit_fallback"),
            "group_audit_fallback_skipped": performance.get("group_audit_fallback_skipped"),
            "scale_fallback_chunk_count": scale_perf.get("fallback_chunk_count"),
        }
        return {
            "schema_version": "parameter_effect_report_v1",
            "active_constraints": {
                "min_break": {"active": enforce_min_interval, "value_minutes": min_break},
                "min_connection_time": {"active": min_connection > 0, "value_minutes": min_connection},
                "max_shift_minutes": {"active": max_shift > 0, "value_minutes": max_shift},
                "max_driving_minutes": {"active": max_driving > 0, "value_minutes": max_driving},
                "mandatory_rest": {
                    "active": mandatory_break_after > 0,
                    "trigger_after_minutes": mandatory_break_after,
                    "minimum_rest_minutes": max(min_break, meal_break),
                },
                "pullout": {"active": pullout > 0, "value_minutes": pullout},
                "pullback": {"active": pullback > 0, "value_minutes": pullback},
                "idle_classification": {
                    "active": True,
                    "short_gap_lt_minutes": min_break,
                    "normal_break_ge_minutes": min_break,
                    "mandatory_rest_ge_minutes": max(min_break, meal_break),
                },
                "zero_gap": {"active": strict_zero_gap, "strict_geography": strict_zero_gap},
                "allow_vehicle_swap": {
                    "active": not allow_vehicle_swap,
                    "value": allow_vehicle_swap,
                    "effective_operator_single_vehicle_only": bool(
                        cct_params.get("operator_single_vehicle_only", False)
                    ),
                },
            },
            "blocked_connections": {
                "total": int(sum(blocked_by_constraint.values())),
                "by_constraint": dict(blocked_by_constraint),
                "samples": samples,
            },
            "impact": {
                "vsp": {
                    "vehicles": len(result.vsp.blocks or []),
                    "unassigned_trips": len(result.vsp.unassigned_trips or []),
                    "warnings": list(result.vsp.warnings or [])[:10],
                },
                "csp": {
                    "duties": len(result.csp.duties or []),
                    "cct_violations": int(result.csp.cct_violations or 0),
                    "issue_counts": dict(issue_counts),
                },
                "operational_time": {
                    "duties_with_reports": len(operational_time_reports),
                    "total_idle_time": sum(int(report.get("idle_time", 0) or 0) for report in operational_time_reports),
                    "total_normal_break_time": sum(
                        int(report.get("normal_break_time", 0) or 0) for report in operational_time_reports
                    ),
                    "total_mandatory_rest_time": sum(
                        int(report.get("mandatory_rest_time", 0) or 0) for report in operational_time_reports
                    ),
                    "total_pullout_time": sum(
                        int(report.get("pullout_time", 0) or 0) for report in operational_time_reports
                    ),
                    "total_pullback_time": sum(
                        int(report.get("pullback_time", 0) or 0) for report in operational_time_reports
                    ),
                },
                "fallback": fallback_meta,
                "stitching": {
                    "attempted": int(stitching.get("attempted", 0) or 0),
                    "accepted": int(stitching.get("accepted", 0) or 0),
                    "rejected": int(stitching.get("rejected", 0) or 0),
                },
            },
        }

    def _stable_json(self, value: Any) -> str:
        return _replay.stable_json(value)

    def _build_replay_fingerprint(
        self,
        trips: List[Trip],
        algorithm: AlgorithmType | str,
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        time_budget_s: float,
    ) -> Dict[str, Any]:
        return _replay.build_replay_fingerprint(trips, algorithm, cct_params, vsp_params, time_budget_s)

    def _derive_deterministic_seed(
        self,
        trips: List[Trip],
        algorithm: AlgorithmType | str,
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        time_budget_s: float,
    ) -> int:
        return _replay.derive_deterministic_seed(trips, algorithm, cct_params, vsp_params, time_budget_s)

    def _build_vehicle_types_hash(self, vehicle_types: List[VehicleType]) -> str:
        return _replay.build_vehicle_types_hash(vehicle_types)

    def _build_run_snapshot(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        algorithm: AlgorithmType | str,
        submitted_cct_params: Dict[str, Any],
        submitted_vsp_params: Dict[str, Any],
        submitted_optimization_params: Dict[str, Any],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        optimization_params: Dict[str, Any],
        time_budget_s: float,
        replay_fingerprint: Dict[str, Any],
        group_inference_report: Dict[str, Any],
        request_metadata: Any = None,
    ) -> Dict[str, Any]:
        return _replay.build_run_snapshot(
            trips,
            vehicle_types,
            algorithm,
            submitted_cct_params,
            submitted_vsp_params,
            submitted_optimization_params,
            cct_params,
            vsp_params,
            optimization_params,
            time_budget_s,
            replay_fingerprint,
            group_inference_report,
            request_metadata,
        )

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
        elif any(code == "MAX_DRIVING_EXCEEDED" for code in issue_codes):
            reason = "continuous_driving_limit"
            message = "A direção contínua exigida pela grade excede o limite regulatório."
        elif any(code == "MANDATORY_REST_MISSING" for code in issue_codes):
            reason = "mandatory_rest_missing"
            message = "A jornada não encontrou descanso obrigatório válido dentro da janela operacional."
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
            group_id: sorted(set(member_ids)) for group_id, member_ids in groups.items() if len(set(member_ids)) >= 2
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

    def _repair_split_trip_groups_with_dedicated_blocks(
        self,
        result: OptimizationResult,
        trips: List[Trip],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        optimization_params: Dict[str, Any],
    ) -> Optional[OptimizationResult]:
        audit = self._build_trip_group_audit(result, trips)
        if int(audit.get("split_groups", 0)) <= 0:
            return None

        trip_by_id = {int(trip.id): trip for trip in trips}
        groups: Dict[int, List[int]] = {}
        for trip in trips:
            if trip.trip_group_id is None:
                continue
            groups.setdefault(int(trip.trip_group_id), []).append(int(trip.id))

        trip_to_roster: Dict[int, Optional[int]] = {}
        for duty in result.csp.duties:
            roster_id = duty.meta.get("roster_id")
            for task in duty.tasks:
                for trip in task.trips:
                    trip_to_roster[int(trip.id)] = int(roster_id) if roster_id is not None else None

        split_member_groups: List[List[int]] = []
        for member_ids in groups.values():
            unique_member_ids = sorted(set(member_ids))
            if len(unique_member_ids) < 2:
                continue
            assigned_rosters = {trip_to_roster.get(trip_id) for trip_id in unique_member_ids}
            if None in assigned_rosters or len(assigned_rosters) > 1:
                split_member_groups.append(unique_member_ids)

        if not split_member_groups:
            return None

        original_block_by_trip: Dict[int, Block] = {}
        for block in result.vsp.blocks:
            for trip in block.trips:
                original_block_by_trip[int(trip.id)] = block

        next_block_id = max((int(block.id) for block in result.vsp.blocks), default=0) + 1
        repaired_blocks: List[Block] = []
        repair_trip_ids: set[int] = set()

        split_groups: List[List[Trip]] = []
        for member_ids in split_member_groups:
            group_trips = [trip_by_id[trip_id] for trip_id in member_ids if trip_id in trip_by_id]
            if len(group_trips) < 2:
                continue
            ordered_group_trips = sorted(group_trips, key=lambda trip: (trip.start_time, trip.id))
            infeasible_issues = self._validate_repair_group_block(ordered_group_trips, cct_params, vsp_params)
            if infeasible_issues:
                group_id = getattr(ordered_group_trips[0], "trip_group_id", None)
                issue_prefixes = sorted({str(issue).split(" ", 1)[0] for issue in infeasible_issues if issue})
                reason_code = issue_prefixes[0] if issue_prefixes else "GROUP_CONNECTION_INFEASIBLE"
                raise OptimizerError(
                    (
                        "Mandatory trip group cannot be repaired into one vehicle block "
                        f"without violating hard VSP constraints: group={group_id}"
                    ),
                    code="GROUP_INFEASIBLE",
                    details={
                        "group_id": int(group_id) if group_id is not None else None,
                        "trip_ids": [int(trip.id) for trip in ordered_group_trips],
                        "reason_code": reason_code,
                        "issues": infeasible_issues,
                        "recommendation": (
                            "Corrija o trip_group_id/pairId de entrada ou relaxe o pareamento hard "
                            "para esta grade; o solver não deve mascarar grupos fisicamente inviáveis."
                        ),
                    },
                )
            split_groups.append(ordered_group_trips)
            repair_trip_ids.update(int(trip.id) for trip in group_trips)

        if not split_groups:
            return None

        for block in result.vsp.blocks:
            current_segment: List[Trip] = []

            def flush_segment() -> None:
                nonlocal next_block_id, current_segment
                if not current_segment:
                    return
                repaired_blocks.append(
                    Block(
                        id=next_block_id,
                        trips=list(current_segment),
                        vehicle_type_id=block.vehicle_type_id,
                        warnings=list(block.warnings),
                        meta={
                            **dict(block.meta or {}),
                            "source_block_id": int(block.id),
                            "group_repair_segment": True,
                        },
                    )
                )
                next_block_id += 1
                current_segment = []

            for trip in block.trips:
                if int(trip.id) in repair_trip_ids:
                    flush_segment()
                else:
                    current_segment.append(trip)
            flush_segment()

        for group_trips in split_groups:
            source_blocks = [
                original_block_by_trip[int(trip.id)] for trip in group_trips if int(trip.id) in original_block_by_trip
            ]
            source_block = source_blocks[0] if source_blocks else None
            repaired_blocks.append(
                Block(
                    id=next_block_id,
                    trips=list(group_trips),
                    vehicle_type_id=source_block.vehicle_type_id if source_block is not None else None,
                    warnings=[],
                    meta={
                        "source_block_ids": sorted({int(block.id) for block in source_blocks}),
                        "group_repair_dedicated_block": True,
                        "covered_trip_group_ids": sorted(
                            {
                                int(trip.trip_group_id)
                                for trip in group_trips
                                if getattr(trip, "trip_group_id", None) is not None
                            }
                        ),
                    },
                )
            )
            next_block_id += 1

        repaired_blocks.sort(key=lambda block: (block.start_time, block.id))
        repaired_vsp = VSPSolution(
            blocks=repaired_blocks,
            total_cost=result.vsp.total_cost,
            unassigned_trips=list(result.vsp.unassigned_trips or []),
            algorithm=f"{result.vsp.algorithm or 'vsp'}+group_repair",
            iterations=result.vsp.iterations,
            elapsed_ms=result.vsp.elapsed_ms,
            warnings=[
                *(result.vsp.warnings or []),
                f"GROUP_REPAIR_DEDICATED_BLOCKS groups={len(split_groups)}",
            ],
            meta={
                **dict(result.vsp.meta or {}),
                "group_repair": {
                    "strategy": "dedicated_blocks",
                    "groups_repaired": len(split_groups),
                    "trips_repaired": sorted(repair_trip_ids),
                },
            },
        )
        csp = self._make_csp(cct_params, vsp_params, optimization_params).solve(repaired_vsp.blocks, trips)
        repaired_result = OptimizationResult(
            vsp=repaired_vsp,
            csp=csp,
            total_cost=result.total_cost,
            total_elapsed_ms=result.total_elapsed_ms,
            algorithm=result.algorithm,
            meta={**dict(result.meta or {})},
        )
        return repaired_result

    def _validate_repair_group_block(
        self,
        group_trips: List[Trip],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
    ) -> List[str]:
        issues: List[str] = []
        if len(group_trips) < 2:
            return issues

        min_layover = int(vsp_params.get("min_layover_minutes", cct_params.get("min_layover_minutes", 8)) or 8)
        min_break = int(cct_params.get("min_break_minutes", vsp_params.get("min_break_minutes", 30)) or 30)
        enforce_min_interval = bool(
            vsp_params.get("enforce_min_interval", cct_params.get("enforce_min_interval", False))
        )
        connection_tolerance = int(
            vsp_params.get(
                "connection_tolerance_minutes",
                cct_params.get("connection_tolerance_minutes", 0),
            )
            or 0
        )
        strict_zero_gap_validation = bool(
            vsp_params.get(
                "strict_zero_gap_validation",
                cct_params.get("strict_zero_gap_validation", False),
            )
        )
        strict_operational_mode = bool(
            vsp_params.get(
                "strict_operational_mode",
                cct_params.get("strict_operational_mode", False),
            )
        )
        strict_hard_constraints = bool(
            vsp_params.get(
                "strict_hard_constraints",
                cct_params.get("strict_hard_constraints", False),
            )
        )

        for current, nxt in zip(group_trips, group_trips[1:]):
            if int(nxt.start_time) < int(current.end_time):
                issues.append(f"GROUP_OVERLAP_INFEASIBLE T{current.id}->{nxt.id}")
                continue
            if not is_connection_feasible(
                current,
                nxt,
                min_layover=min_layover,
                min_break=min_break,
                enforce_min_interval=enforce_min_interval,
                connection_tolerance=connection_tolerance,
                strict_zero_gap_validation=strict_zero_gap_validation,
                strict_operational_mode=strict_operational_mode,
                strict_hard_constraints=strict_hard_constraints,
            ):
                issues.append(f"GROUP_CONNECTION_INFEASIBLE T{current.id}->{nxt.id}")
        return issues

    def _build_scale_profile(
        self,
        trips: List[Trip],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        grouped: Dict[int, List[int]] = {}
        for trip in trips:
            if trip.trip_group_id is not None:
                grouped.setdefault(int(trip.trip_group_id), []).append(int(trip.id))
        group_sizes = [len(set(ids)) for ids in grouped.values() if len(set(ids)) >= 2]
        direct_max = int(vsp_params.get("scale_direct_max_trips", 1000) or 1000)
        decompose_min = int(vsp_params.get("scale_decompose_min_trips", 2000) or 2000)
        if len(trips) <= direct_max:
            mode = "direct_strict"
        elif len(trips) < decompose_min:
            mode = "strict_with_controlled_fallback"
        else:
            mode = "decomposed_required"
        return {
            "trip_count": len(trips),
            "group_count": len(group_sizes),
            "grouped_trip_count": sum(group_sizes),
            "avg_group_size": round(sum(group_sizes) / len(group_sizes), 3) if group_sizes else 0.0,
            "max_group_size": max(group_sizes) if group_sizes else 0,
            "direct_max_trips": direct_max,
            "decompose_min_trips": decompose_min,
            "chunk_target_trips": int(vsp_params.get("scale_chunk_target_trips", 600) or 600),
            "chunk_max_trips": int(vsp_params.get("scale_chunk_max_trips", 800) or 800),
            "mode": mode,
            "strict_trip_group_mode": self._strict_trip_group_mode(trips, cct_params, vsp_params),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Sprint I-3: thin wrappers — implementação em trip_group_inference.py
    # ─────────────────────────────────────────────────────────────────────
    def _summarize_trip_groups(self, trips: List[Trip]) -> Dict[str, int]:
        return _module_summarize_trip_groups(trips)

    def _build_group_inference_report(self, trips: List[Trip], request_metadata: Any) -> Dict[str, Any]:
        return _module_build_group_inference_report(trips, request_metadata)

    def _log_group_inference_report(self, report: Dict[str, Any]) -> None:
        return _module_log_group_inference_report(report)

    def _build_scale_failure_hard_constraint_report(
        self,
        failed_chunks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        issues: List[str] = []
        problem_groups: List[List[int]] = []
        for chunk in failed_chunks:
            chunk_issues = chunk.get("issues") or []
            if isinstance(chunk_issues, list):
                issues.extend(str(item) for item in chunk_issues if item)
            error_message = str(chunk.get("error") or "")
            error_details = chunk.get("error_details") or {}
            detail_issues = error_details.get("issues") or []
            if isinstance(detail_issues, list):
                issues.extend(str(item) for item in detail_issues if item)
            detail_trip_ids = error_details.get("trip_ids") or []
            if error_details.get("error_code") == "GROUP_INFEASIBLE" and detail_trip_ids:
                problem_groups.append([int(trip_id) for trip_id in detail_trip_ids])
                issues.append(f"GROUP_INFEASIBLE {detail_trip_ids}")
            for match in re.findall(r"MANDATORY_GROUP_SPLIT \[([^\]]+)\]", error_message):
                try:
                    group = [int(part.strip()) for part in match.split(",") if part.strip()]
                except ValueError:
                    continue
                if group:
                    problem_groups.append(group)
                    issues.append(f"MANDATORY_GROUP_SPLIT {group}")

        deduped_issues = list(dict.fromkeys(issues))
        deduped_groups: List[List[int]] = []
        seen_groups: set[Tuple[int, ...]] = set()
        for group in problem_groups:
            key = tuple(group)
            if key in seen_groups:
                continue
            seen_groups.add(key)
            deduped_groups.append(group)

        return {
            "ok": False,
            "issues": deduped_issues,
            "failed_chunks": failed_chunks[:20],
            "problem_trip_groups": deduped_groups,
        }

    def _should_use_scale_decomposition(
        self,
        algorithm: AlgorithmType,
        trips: List[Trip],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        scale_profile: Dict[str, Any],
    ) -> bool:
        if bool(vsp_params.get("disable_scale_decomposition", False)):
            return False
        algorithm_value = algorithm.value if hasattr(algorithm, "value") else str(algorithm)
        if algorithm_value != AlgorithmType.HYBRID_PIPELINE.value:
            return False
        if bool(vsp_params.get("force_scale_decomposition", False)):
            return True
        return len(trips) >= int(scale_profile.get("decompose_min_trips", 2000) or 2000)

    def _partition_scale_chunks(
        self,
        trips: List[Trip],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        scale_profile: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        scale_profile = scale_profile or self._build_scale_profile(trips, cct_params, vsp_params)
        target = max(1, int(scale_profile.get("chunk_target_trips", 600) or 600))
        max_size = max(target, int(scale_profile.get("chunk_max_trips", 800) or 800))
        time_window = max(60, int(vsp_params.get("scale_chunk_time_window_minutes", 360) or 360))

        grouped_units: Dict[Tuple[str, int], List[Trip]] = {}
        for trip in trips:
            if trip.trip_group_id is None:
                key = ("trip", int(trip.id))
            else:
                key = ("group", int(trip.trip_group_id))
            grouped_units.setdefault(key, []).append(trip)

        def unit_sort_key(unit: List[Trip]) -> Tuple[int, int, int, Tuple[Any, Any], int]:
            ordered = sorted(unit, key=lambda item: (item.start_time, item.id))
            line_counts = Counter(int(trip.line_id) for trip in ordered)
            line_id = line_counts.most_common(1)[0][0] if line_counts else 0
            first = ordered[0]
            service_day = int(first.start_time) // 1440
            time_bucket = int(first.start_time) // time_window
            if first.origin_latitude is not None and first.origin_longitude is not None:
                region_key: Tuple[Any, Any] = (
                    round(float(first.origin_latitude), 2),
                    round(float(first.origin_longitude), 2),
                )
            else:
                region_key = (int(first.origin_id), int(first.destination_id))
            return (line_id, service_day, time_bucket, region_key, int(first.start_time))

        units = sorted(
            (sorted(unit, key=lambda item: (item.start_time, item.id)) for unit in grouped_units.values()),
            key=unit_sort_key,
        )
        chunks: List[Dict[str, Any]] = []
        current: List[Trip] = []
        current_key: Optional[Tuple[int, int, int, Tuple[Any, Any]]] = None

        def flush() -> None:
            nonlocal current, current_key
            if not current:
                return
            ordered = sorted(current, key=lambda item: (item.start_time, item.id))
            chunks.append(
                {
                    "index": len(chunks),
                    "trips": ordered,
                    "trip_count": len(ordered),
                    "line_ids": sorted({int(trip.line_id) for trip in ordered}),
                    "trip_group_ids": sorted(
                        {int(trip.trip_group_id) for trip in ordered if trip.trip_group_id is not None}
                    ),
                    "start_time": min(int(trip.start_time) for trip in ordered),
                    "end_time": max(int(trip.end_time) for trip in ordered),
                    "partition_key": current_key,
                }
            )
            current = []
            current_key = None

        for unit in units:
            key_full = unit_sort_key(unit)
            key = key_full[:4]
            unit_size = len(unit)
            if unit_size > max_size:
                flush()
                current = list(unit)
                current_key = key
                flush()
                continue
            if current and len(current) + unit_size > max_size:
                flush()
            elif current and key != current_key and len(current) >= target:
                flush()
            current.extend(unit)
            current_key = current_key or key
        flush()
        return chunks

    def _restrict_mandatory_groups_to_chunk(
        self,
        cct_params: Dict[str, Any],
        chunk_trips: List[Trip],
        chunk_index: int,
    ) -> None:
        mandatory_groups = cct_params.get("mandatory_trip_groups_same_duty") or []
        if not mandatory_groups:
            return
        chunk_trip_ids = {int(trip.id) for trip in chunk_trips}
        filtered: List[List[int]] = []
        partial: List[Dict[str, Any]] = []
        for group in mandatory_groups:
            group_ids = {int(item) for item in group}
            inside = group_ids & chunk_trip_ids
            if not inside:
                continue
            if inside != group_ids:
                partial.append(
                    {
                        "group": sorted(group_ids),
                        "inside": sorted(inside),
                        "outside": sorted(group_ids - chunk_trip_ids),
                    }
                )
                continue
            filtered.append(sorted(group_ids))
        if partial:
            raise OptimizerError(
                f"Scale chunk {chunk_index} split mandatory trip groups before solve.",
                code="SCALE_CHUNK_GROUP_SPLIT",
                details={"chunk_index": chunk_index, "partial_groups": partial[:10]},
            )
        cct_params["mandatory_trip_groups_same_duty"] = filtered
        trip_by_id = {int(trip.id): trip for trip in chunk_trips}
        for index, group_ids in enumerate(filtered):
            existing_group_ids = {
                int(trip_by_id[trip_id].trip_group_id)
                for trip_id in group_ids
                if trip_id in trip_by_id and trip_by_id[trip_id].trip_group_id is not None
            }
            synthetic_group_id = -(10_000_000 + chunk_index * 100_000 + index)
            materialized_group_id = (
                next(iter(existing_group_ids)) if len(existing_group_ids) == 1 else synthetic_group_id
            )
            for trip_id in group_ids:
                trip = trip_by_id.get(trip_id)
                if trip is not None and trip.trip_group_id is None:
                    trip.trip_group_id = materialized_group_id

    def _run_decomposed_hybrid(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        optimization_params: Dict[str, Any],
        time_budget_s: float,
        scale_profile: Dict[str, Any],
    ) -> OptimizationResult:
        chunks = self._partition_scale_chunks(trips, cct_params, vsp_params, scale_profile)
        logger.warning(
            "[SCALE] Decomposed hybrid_pipeline: trips=%d groups=%d chunks=%d target=%s max=%s",
            len(trips),
            int(scale_profile.get("group_count", 0) or 0),
            len(chunks),
            scale_profile.get("chunk_target_trips"),
            scale_profile.get("chunk_max_trips"),
        )
        if not chunks:
            raise NoProblemDataError("scale decomposition produced no chunks")

        strict_mode = bool(
            vsp_params.get(
                "strict_hard_constraints",
                cct_params.get("strict_hard_constraints", False),
            )
        )
        chunk_budget = self._scale_chunk_budget(time_budget_s, len(chunks), vsp_params)
        chunk_records: List[Dict[str, Any]] = []
        failed_chunks: List[Dict[str, Any]] = []

        for chunk in chunks:
            chunk_index = int(chunk["index"])
            chunk_trips = list(chunk["trips"])
            logger.info(
                "[SCALE] chunk[%d/%d] trips=%d lines=%s groups=%d window=%s-%s",
                chunk_index + 1,
                len(chunks),
                len(chunk_trips),
                chunk.get("line_ids"),
                len(chunk.get("trip_group_ids") or []),
                chunk.get("start_time"),
                chunk.get("end_time"),
            )
            base_chunk_cct = dict(cct_params)
            base_chunk_vsp = dict(vsp_params)
            base_chunk_vsp["disable_scale_decomposition"] = True
            base_chunk_vsp["scale_chunk_index"] = chunk_index
            self._restrict_mandatory_groups_to_chunk(base_chunk_cct, chunk_trips, chunk_index)
            if strict_mode:
                base_chunk_cct["strict_hard_validation"] = True
                base_chunk_vsp["strict_hard_validation"] = True

            chunk_result: Optional[OptimizationResult] = None
            chunk_status = "completed"
            primary_error: Optional[Exception] = None
            try:
                chunk_result = self.run(
                    trips=chunk_trips,
                    vehicle_types=vehicle_types,
                    algorithm=AlgorithmType.HYBRID_PIPELINE,
                    depot_id=depot_id,
                    time_budget_s=chunk_budget,
                    cct_params=base_chunk_cct,
                    vsp_params=base_chunk_vsp,
                    optimization_params=dict(optimization_params or {}),
                )
            except Exception as exc:
                primary_error = exc
                logger.warning("[SCALE] chunk[%d] primary hybrid failed: %s", chunk_index, exc, exc_info=True)

            def run_fallback(reason: str) -> Optional[OptimizationResult]:
                fallback_cct = dict(base_chunk_cct)
                fallback_vsp = dict(base_chunk_vsp)
                fallback_vsp["scale_chunk_fallback"] = "greedy"

                def append_failed_chunk(
                    exc: Exception,
                    fallback_reason: str,
                    *,
                    error_details: Optional[Dict[str, Any]] = None,
                ) -> None:
                    details = dict(error_details or getattr(exc, "details", {}) or {})
                    failed_chunks.append(
                        {
                            "chunk_index": chunk_index,
                            "trip_count": len(chunk_trips),
                            "line_ids": chunk.get("line_ids"),
                            "error": str(exc),
                            "error_code": getattr(exc, "code", exc.__class__.__name__),
                            "error_details": details,
                            "issues": list(details.get("issues") or []),
                            "primary_error": str(primary_error) if primary_error else None,
                            "fallback_reason": fallback_reason,
                        }
                    )

                def run_group_preserving_repair_fallback() -> Optional[OptimizationResult]:
                    relaxed_cct = dict(fallback_cct)
                    relaxed_vsp = dict(fallback_vsp)
                    relaxed_cct["strict_hard_validation"] = False
                    relaxed_vsp["strict_hard_validation"] = False
                    relaxed_vsp["scale_chunk_fallback"] = "greedy_group_repair"
                    relaxed_result = self._dispatch(
                        AlgorithmType.GREEDY,
                        chunk_trips,
                        vehicle_types,
                        depot_id,
                        relaxed_cct,
                        relaxed_vsp,
                        dict(optimization_params or {}),
                        max(15.0, min(chunk_budget, 60.0)),
                    )
                    relaxed_validation = self._validate_scale_chunk_result(
                        relaxed_result,
                        chunk_trips,
                        fallback_cct,
                        fallback_vsp,
                    )
                    if relaxed_validation["ok"]:
                        logger.info(
                            "[SCALE] chunk[%d] relaxed greedy fallback completed after %s",
                            chunk_index,
                            reason,
                        )
                        return relaxed_result
                    repaired_result = self._repair_split_trip_groups_with_dedicated_blocks(
                        relaxed_result,
                        chunk_trips,
                        fallback_cct,
                        fallback_vsp,
                        optimization_params,
                    )
                    repaired_validation = self._validate_scale_chunk_result(
                        repaired_result,
                        chunk_trips,
                        fallback_cct,
                        fallback_vsp,
                    )
                    if not repaired_validation["ok"]:
                        raise OptimizerError(
                            "Scale chunk fallback remained invalid after local group repair.",
                            code=repaired_validation["error_code"],
                            details={
                                "issues": repaired_validation["issues"],
                                "trip_group_audit": repaired_validation["trip_group_audit"],
                                "hard_constraint_report": repaired_validation["hard_constraint_report"],
                            },
                        )
                    repaired_result.meta.setdefault("performance", {})
                    repaired_result.meta["performance"]["scale_chunk_group_repair"] = {
                        "chunk_index": chunk_index,
                        "reason": reason,
                        "fallback": "greedy_group_repair",
                    }
                    logger.info(
                        "[SCALE] chunk[%d] greedy group-repair fallback completed after %s",
                        chunk_index,
                        reason,
                    )
                    return repaired_result

                try:
                    fallback_result = self.run(
                        trips=chunk_trips,
                        vehicle_types=vehicle_types,
                        algorithm=AlgorithmType.GREEDY,
                        depot_id=depot_id,
                        time_budget_s=max(15.0, min(chunk_budget, 60.0)),
                        cct_params=fallback_cct,
                        vsp_params=fallback_vsp,
                        optimization_params=dict(optimization_params or {}),
                    )
                    logger.info("[SCALE] chunk[%d] fallback greedy completed after %s", chunk_index, reason)
                    return fallback_result
                except Exception as fallback_exc:
                    try:
                        repaired_fallback = run_group_preserving_repair_fallback()
                        if repaired_fallback is not None:
                            return repaired_fallback
                    except OptimizerError as repair_exc:
                        append_failed_chunk(repair_exc, reason, error_details=getattr(repair_exc, "details", {}) or {})
                        logger.error("[SCALE] chunk[%d] fallback repair failed: %s", chunk_index, repair_exc)
                        return None
                    append_failed_chunk(fallback_exc, reason)
                    logger.error("[SCALE] chunk[%d] fallback failed: %s", chunk_index, fallback_exc)
                    return None

            if chunk_result is None:
                chunk_result = run_fallback("primary_exception")
                if chunk_result is None:
                    continue
                chunk_status = "fallback_completed"

            validation = self._validate_scale_chunk_result(chunk_result, chunk_trips, base_chunk_cct, base_chunk_vsp)
            if not validation["ok"]:
                repaired_result = self._try_scale_chunk_group_repair(
                    chunk_result,
                    chunk_trips,
                    base_chunk_cct,
                    base_chunk_vsp,
                    optimization_params,
                    chunk_index,
                    "primary_invalid",
                )
                if repaired_result is not None:
                    repaired_validation = self._validate_scale_chunk_result(
                        repaired_result, chunk_trips, base_chunk_cct, base_chunk_vsp
                    )
                    if repaired_validation["ok"]:
                        chunk_result = repaired_result
                        chunk_status = f"{chunk_status}_repaired"
                        validation = repaired_validation
            if not validation["ok"] and chunk_status != "fallback_completed":
                logger.warning(
                    "[SCALE] chunk[%d] primary result invalid (%s); trying fallback",
                    chunk_index,
                    validation["issues"][:5],
                )
                fallback_result = run_fallback("primary_invalid")
                if fallback_result is None:
                    continue
                chunk_result = fallback_result
                chunk_status = "fallback_completed"
                validation = self._validate_scale_chunk_result(
                    chunk_result, chunk_trips, base_chunk_cct, base_chunk_vsp
                )
                if not validation["ok"]:
                    repaired_result = self._try_scale_chunk_group_repair(
                        chunk_result,
                        chunk_trips,
                        base_chunk_cct,
                        base_chunk_vsp,
                        optimization_params,
                        chunk_index,
                        "fallback_invalid",
                    )
                    if repaired_result is not None:
                        repaired_validation = self._validate_scale_chunk_result(
                            repaired_result, chunk_trips, base_chunk_cct, base_chunk_vsp
                        )
                        if repaired_validation["ok"]:
                            chunk_result = repaired_result
                            chunk_status = "fallback_completed_repaired"
                            validation = repaired_validation
            if not validation["ok"]:
                failed_chunks.append(
                    {
                        "chunk_index": chunk_index,
                        "trip_count": len(chunk_trips),
                        "line_ids": chunk.get("line_ids"),
                        "error_code": validation["error_code"],
                        "issues": validation["issues"],
                    }
                )
                logger.error("[SCALE] chunk[%d] invalid after solve: %s", chunk_index, validation["issues"][:5])
                continue

            chunk_records.append(
                {
                    "chunk": chunk,
                    "result": chunk_result,
                    "status": chunk_status,
                    "trip_group_audit": validation["trip_group_audit"],
                    "hard_constraint_report": validation["hard_constraint_report"],
                }
            )

        if failed_chunks:
            code = (
                "MANDATORY_GROUP_SPLIT"
                if any(item.get("error_code") == "MANDATORY_GROUP_SPLIT" for item in failed_chunks)
                else "SCALE_CHUNK_FAILED"
            )
            raise OptimizerError(
                f"Scale decomposition failed in {len(failed_chunks)} chunk(s).",
                code=code,
                details={
                    "scale_profile": scale_profile,
                    "chunk_count": len(chunks),
                    "failed_chunks": failed_chunks[:20],
                    "strategy": "line_region_temporal_chunking",
                },
            )

        result = self._merge_scale_chunk_results(
            chunk_records,
            trips,
            vehicle_types,
            cct_params,
            vsp_params,
            optimization_params,
            scale_profile,
            time_budget_s,
        )
        coverage_issues = self._validate_scale_coverage(result, trips)
        if coverage_issues:
            raise OptimizerError(
                "Scale decomposition coverage mismatch.",
                code="SCALE_COVERAGE_MISMATCH",
                details={
                    "issues": coverage_issues,
                    "scale_profile": scale_profile,
                    "chunk_count": len(chunks),
                },
            )
        return result

    def _scale_chunk_budget(self, total_budget_s: float, chunk_count: int, vsp_params: Dict[str, Any]) -> float:
        configured = vsp_params.get("scale_chunk_time_budget_s")
        if configured is not None:
            return max(5.0, float(configured))
        floor = float(vsp_params.get("scale_chunk_min_time_budget_s", 30.0) or 30.0)
        ceiling = float(vsp_params.get("scale_chunk_max_time_budget_s", 120.0) or 120.0)
        proportional = max(1.0, float(total_budget_s) / max(1, chunk_count))
        return max(floor, min(ceiling, proportional))

    def _validate_scale_chunk_result(
        self,
        result: OptimizationResult,
        chunk_trips: List[Trip],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        audit = self._build_trip_group_audit(result, chunk_trips)
        hard_report = self.validator.audit_result(result, chunk_trips, cct_params, vsp_params)
        issues = list(hard_report.get("hard_issues") or [])
        if int(audit.get("split_groups", 0) or 0) > 0:
            issues.append("MANDATORY_GROUP_SPLIT")
        return {
            "ok": not issues,
            "issues": issues,
            "error_code": (
                "MANDATORY_GROUP_SPLIT"
                if any(str(item).startswith("MANDATORY_GROUP_SPLIT") for item in issues)
                else "SCALE_CHUNK_HARD_VIOLATION"
            ),
            "trip_group_audit": audit,
            "hard_constraint_report": hard_report,
        }

    def _try_scale_chunk_group_repair(
        self,
        result: OptimizationResult,
        chunk_trips: List[Trip],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        optimization_params: Dict[str, Any],
        chunk_index: int,
        reason: str,
    ) -> Optional[OptimizationResult]:
        audit = self._build_trip_group_audit(result, chunk_trips)
        if int(audit.get("split_groups", 0) or 0) <= 0:
            return None
        try:
            repaired = self._repair_split_trip_groups_with_dedicated_blocks(
                result,
                chunk_trips,
                cct_params,
                vsp_params,
                optimization_params,
            )
        except OptimizerError as exc:
            logger.warning("[SCALE] chunk[%d] group repair rejected after %s: %s", chunk_index, reason, exc)
            return None
        if repaired is None:
            return None
        repaired.meta.setdefault("performance", {})
        repaired.meta["performance"]["scale_chunk_group_repair"] = {
            "chunk_index": chunk_index,
            "reason": reason,
            "before_split_groups": int(audit.get("split_groups", 0) or 0),
        }
        logger.info(
            "[SCALE] chunk[%d] group repair attempted after %s: split_groups=%d",
            chunk_index,
            reason,
            int(audit.get("split_groups", 0) or 0),
        )
        return repaired

    def _merge_scale_chunk_results(
        self,
        chunk_records: List[Dict[str, Any]],
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        optimization_params: Dict[str, Any],
        scale_profile: Dict[str, Any],
        time_budget_s: float,
    ) -> OptimizationResult:
        raw_blocks: List[Block] = []
        raw_duties: List[Duty] = []
        next_block_id = 1
        next_task_id = 1
        next_duty_id = 1
        next_roster_id = 1
        chunk_meta: List[Dict[str, Any]] = []

        for record in chunk_records:
            chunk = record["chunk"]
            chunk_idx = int(chunk["index"])
            chunk_result: OptimizationResult = record["result"]
            old_to_global: Dict[int, int] = {}

            for block in chunk_result.vsp.blocks:
                global_block_id = next_block_id
                next_block_id += 1
                old_to_global[int(block.id)] = global_block_id
                raw_blocks.append(
                    Block(
                        id=global_block_id,
                        trips=list(block.trips),
                        vehicle_type_id=block.vehicle_type_id,
                        warnings=list(block.warnings or []),
                        meta={
                            **dict(block.meta or {}),
                            "scale_chunk_index": chunk_idx,
                            "pre_stitch_block_id": global_block_id,
                            "chunk_source_block_id": int(block.id),
                        },
                    )
                )

            roster_map: Dict[int, int] = {}
            operator_map: Dict[int, int] = {}
            for duty in chunk_result.csp.duties:
                new_duty = Duty(id=next_duty_id)
                next_duty_id += 1
                duty_meta = dict(duty.meta or {})
                if duty_meta.get("roster_id") is not None:
                    old_roster = int(duty_meta.get("roster_id"))
                    roster_map.setdefault(old_roster, next_roster_id + len(roster_map))
                    duty_meta["roster_id"] = roster_map[old_roster]
                if duty_meta.get("operator_id") is not None:
                    old_operator = int(duty_meta.get("operator_id"))
                    operator_map.setdefault(old_operator, next_roster_id + len(operator_map))
                    duty_meta["operator_id"] = operator_map[old_operator]
                duty_meta["scale_chunk_index"] = chunk_idx
                duty_meta["chunk_source_duty_id"] = int(duty.id)

                for task in duty.tasks:
                    source_old = int(task.meta.get("source_block_id", task.id))
                    global_source = old_to_global.get(source_old, old_to_global.get(int(task.id), source_old))
                    new_task = Block(
                        id=next_task_id,
                        trips=list(task.trips),
                        vehicle_type_id=task.vehicle_type_id,
                        warnings=list(task.warnings or []),
                        meta={
                            **dict(task.meta or {}),
                            "source_block_id": global_source,
                            "scale_chunk_index": chunk_idx,
                            "chunk_source_task_id": int(task.id),
                        },
                    )
                    next_task_id += 1
                    new_duty.add_task(new_task)

                new_duty.spread_time = duty.spread_time
                new_duty.work_time = duty.work_time
                new_duty.rest_violations = duty.rest_violations
                new_duty.shift_violations = duty.shift_violations
                new_duty.continuous_driving_violation = duty.continuous_driving_violation
                new_duty.warnings = list(duty.warnings or [])
                new_duty.paid_minutes = duty.paid_minutes
                new_duty.overtime_minutes = duty.overtime_minutes
                new_duty.nocturnal_minutes = duty.nocturnal_minutes
                new_duty.meta = duty_meta
                raw_duties.append(new_duty)

            if roster_map:
                next_roster_id = max(roster_map.values()) + 1
            chunk_meta.append(
                {
                    "chunk_index": chunk_idx,
                    "trip_count": int(chunk["trip_count"]),
                    "line_ids": chunk.get("line_ids"),
                    "trip_group_count": len(chunk.get("trip_group_ids") or []),
                    "status": record.get("status"),
                    "vehicles": len(chunk_result.vsp.blocks or []),
                    "duties": len(chunk_result.csp.duties or []),
                    "split_groups": int((record.get("trip_group_audit") or {}).get("split_groups", 0) or 0),
                    "hard_issues": len((record.get("hard_constraint_report") or {}).get("hard_issues") or []),
                }
            )

        stitched_blocks, block_id_remap, stitching_meta = self._stitch_scale_blocks(raw_blocks, cct_params, vsp_params)
        for duty in raw_duties:
            source_ids: List[int] = []
            for task in duty.tasks:
                old_source = int(task.meta.get("source_block_id", task.id))
                new_source = int(block_id_remap.get(old_source, old_source))
                task.meta["source_block_id"] = new_source
                source_ids.append(new_source)
            duty.meta["source_block_ids"] = list(dict.fromkeys(source_ids))

        fallback_chunks = [item for item in chunk_meta if item.get("status") == "fallback_completed"]
        status = "partially_completed" if fallback_chunks else "completed"
        vsp = VSPSolution(
            blocks=stitched_blocks,
            unassigned_trips=[],
            algorithm="hybrid_pipeline_decomposed",
            warnings=[f"SCALE_DECOMPOSITION chunks={len(chunk_records)} status={status}"],
            meta={
                "scale_decomposition": {
                    "enabled": True,
                    "strategy": "line_region_temporal_chunking",
                    "status": status,
                    "profile": scale_profile,
                    "chunks": chunk_meta,
                    "stitching": stitching_meta,
                }
            },
        )
        csp = CSPSolution(
            duties=raw_duties,
            uncovered_blocks=[],
            cct_violations=sum(int(record["result"].csp.cct_violations or 0) for record in chunk_records),
            algorithm="chunked_hybrid_csp_merge",
            warnings=[f"SCALE_DECOMPOSITION_CSP_MERGE chunks={len(chunk_records)}"],
            meta={
                "roster_count": len(
                    {int(duty.meta.get("roster_id")) for duty in raw_duties if duty.meta.get("roster_id") is not None}
                )
                or len(raw_duties),
                "scale_decomposition": {
                    "status": status,
                    "chunks": chunk_meta,
                    "fallback_chunks": len(fallback_chunks),
                },
            },
        )
        result = OptimizationResult(
            vsp=vsp,
            csp=csp,
            algorithm=AlgorithmType.HYBRID_PIPELINE,
            total_elapsed_ms=0.0,
            meta={
                "performance": {
                    "scale_decomposition": {
                        "enabled": True,
                        "status": status,
                        "chunk_count": len(chunk_records),
                        "fallback_chunk_count": len(fallback_chunks),
                        "chunk_time_budget_s": self._scale_chunk_budget(
                            time_budget_s, max(1, len(chunk_records)), vsp_params
                        ),
                        "chunks": chunk_meta,
                        "stitching": stitching_meta,
                    }
                },
                "scale_execution_status": status,
            },
        )
        result.total_cost = self.evaluator.total_cost(result, vehicle_types)
        return result

    def _stitch_scale_blocks(
        self,
        blocks: List[Block],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
    ) -> Tuple[List[Block], Dict[int, int], Dict[str, Any]]:
        if not blocks:
            return [], {}, {"attempted": 0, "accepted": 0, "rejected": 0}

        # Default elevado de 60→240min após diagnóstico 2026-05-15: 60 era conservador demais
        # para chunks temporais adjacentes. 240min ainda é seguro porque a viabilidade do bloco
        # combinado é validada por max_vehicle_shift (960min hard) + is_connection_feasible.
        # Medido em seed=42 a 2000v: 366→360 blocos, custo -0.5%, tempo +1%.
        max_gap = int(vsp_params.get("scale_stitch_max_gap_minutes", 240) or 240)
        max_vehicle_shift = int(
            vsp_params.get("max_vehicle_shift_minutes", cct_params.get("max_vehicle_shift_minutes", 960)) or 960
        )
        min_layover = int(vsp_params.get("min_layover_minutes", cct_params.get("min_layover_minutes", 8)) or 8)
        min_break = int(cct_params.get("min_break_minutes", vsp_params.get("min_break_minutes", 30)) or 30)
        enforce_min_interval = bool(
            vsp_params.get("enforce_min_interval", cct_params.get("enforce_min_interval", False))
        )
        connection_tolerance = int(
            vsp_params.get("connection_tolerance_minutes", cct_params.get("connection_tolerance_minutes", 0)) or 0
        )
        strict_zero_gap_validation = bool(
            vsp_params.get("strict_zero_gap_validation", cct_params.get("strict_zero_gap_validation", False))
        )
        strict_operational_mode = bool(
            vsp_params.get("strict_operational_mode", cct_params.get("strict_operational_mode", False))
        )
        strict_hard_constraints = bool(
            vsp_params.get("strict_hard_constraints", cct_params.get("strict_hard_constraints", False))
        )
        soft_span_limit = int(
            vsp_params.get("scale_stitch_soft_span_minutes", min(max_vehicle_shift, 12 * 60))
            or min(max_vehicle_shift, 12 * 60)
        )
        soft_gap_weight = float(vsp_params.get("scale_stitch_soft_gap_weight", 1.0) or 1.0)
        soft_span_weight = float(vsp_params.get("scale_stitch_soft_span_weight", 0.25) or 0.25)

        ordered = sorted(blocks, key=lambda block: (block.start_time, block.end_time, block.id))
        used: set[int] = set()
        stitched: List[Block] = []
        old_to_new: Dict[int, int] = {}
        attempted = 0
        accepted = 0
        rejected = 0

        for block in ordered:
            if int(block.id) in used:
                continue
            used.add(int(block.id))
            source_ids = [int(block.id)]
            trips_merged = list(block.trips)
            warnings = list(block.warnings or [])
            vehicle_type_id = block.vehicle_type_id

            while trips_merged:
                last_trip = trips_merged[-1]
                candidates = [
                    candidate
                    for candidate in ordered
                    if int(candidate.id) not in used
                    and candidate.trips
                    and int(candidate.start_time) >= int(last_trip.end_time)
                    and int(candidate.start_time) - int(last_trip.end_time) <= max_gap
                ]
                if not candidates:
                    break
                attempted += len(candidates)
                feasible_candidates: List[Tuple[float, Block]] = []
                for candidate in candidates:
                    if (
                        max_vehicle_shift > 0
                        and int(candidate.end_time) - int(trips_merged[0].start_time) > max_vehicle_shift
                    ):
                        rejected += 1
                        continue
                    if not is_connection_feasible(
                        last_trip,
                        candidate.trips[0],
                        min_layover=min_layover,
                        min_break=min_break,
                        enforce_min_interval=enforce_min_interval,
                        connection_tolerance=connection_tolerance,
                        strict_zero_gap_validation=strict_zero_gap_validation,
                        strict_operational_mode=strict_operational_mode,
                        strict_hard_constraints=strict_hard_constraints,
                    ):
                        rejected += 1
                        continue
                    merged_span = int(candidate.end_time) - int(trips_merged[0].start_time)
                    gap = int(candidate.start_time) - int(last_trip.end_time)
                    soft_penalty = max(0, merged_span - soft_span_limit) * soft_span_weight
                    score = gap * soft_gap_weight + soft_penalty
                    feasible_candidates.append((float(score), candidate))
                selected: Optional[Block] = None
                if feasible_candidates:
                    feasible_candidates.sort(
                        key=lambda item: (
                            item[0],
                            int(item[1].start_time) - int(last_trip.end_time),
                            int(item[1].end_time) - int(trips_merged[0].start_time),
                            int(item[1].id),
                        )
                    )
                    selected = feasible_candidates[0][1]
                if selected is None:
                    break
                used.add(int(selected.id))
                source_ids.append(int(selected.id))
                trips_merged.extend(selected.trips)
                warnings.extend(selected.warnings or [])
                accepted += 1

            new_id = len(stitched) + 1
            for old_id in source_ids:
                old_to_new[old_id] = new_id
            stitched.append(
                Block(
                    id=new_id,
                    trips=sorted(trips_merged, key=lambda trip: (trip.start_time, trip.id)),
                    vehicle_type_id=vehicle_type_id,
                    warnings=list(dict.fromkeys(warnings)),
                    meta={
                        "scale_stitched": len(source_ids) > 1,
                        "source_block_ids": source_ids,
                        "pre_stitch_block_id": source_ids[0],
                    },
                )
            )

        return (
            stitched,
            old_to_new,
            {
                "attempted": attempted,
                "accepted": accepted,
                "rejected": rejected,
                "input_blocks": len(blocks),
                "output_blocks": len(stitched),
                "max_gap_minutes": max_gap,
            },
        )

    def _validate_scale_coverage(self, result: OptimizationResult, trips: List[Trip]) -> List[str]:
        input_ids = {int(trip.id) for trip in trips}
        covered_ids = [int(trip.id) for block in result.vsp.blocks for trip in block.trips]
        covered_counter = Counter(covered_ids)
        missing = sorted(input_ids - set(covered_ids))
        duplicated = sorted(trip_id for trip_id, count in covered_counter.items() if count > 1)
        extra = sorted(set(covered_ids) - input_ids)
        issues: List[str] = []
        if missing:
            issues.append(f"SCALE_MISSING_TRIPS count={len(missing)} sample={missing[:10]}")
        if duplicated:
            issues.append(f"SCALE_DUPLICATED_TRIPS count={len(duplicated)} sample={duplicated[:10]}")
        if extra:
            issues.append(f"SCALE_EXTRA_TRIPS count={len(extra)} sample={extra[:10]}")
        return issues

    def _build_reproducibility_snapshot(
        self,
        algorithm: AlgorithmType,
        trips: List[Trip],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        time_budget_s: float,
    ) -> Dict[str, Any]:
        return _replay.build_reproducibility_snapshot(algorithm, trips, cct_params, vsp_params, time_budget_s)

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

        total_trips = sum(len(block.trips) for block in (result.vsp.blocks or [])) + len(
            result.vsp.unassigned_trips or []
        )
        summary = [
            f"VSP cobriu {sum(len(block.trips) for block in (result.vsp.blocks or []))}/{total_trips} viagens com {len(result.vsp.blocks or [])} veículos.",  # noqa: E501
            f"CSP produziu {result.csp.num_crew} tripulantes, {len(result.csp.duties or [])} jornadas e {int((result.csp.meta or {}).get('roster_count', result.csp.num_crew) or result.csp.num_crew)} rosters.",  # noqa: E501
        ]

        dominant_vsp = ((phase_summary.get("vsp") or {}).get("dominant_cost_component") or {}).get("component")
        dominant_csp = ((phase_summary.get("csp") or {}).get("dominant_cost_component") or {}).get("component")
        if cost_breakdown:
            summary.append(
                f"Custo total {float(cost_breakdown.get('total', 0.0) or 0.0):.2f}, com dominância VSP={dominant_vsp or '--'} e CSP={dominant_csp or '--'}."  # noqa: E501
            )
        if trip_group_audit.get("groups_total", 0) > 0:
            summary.append(
                f"Trip groups preservados no mesmo roster: {trip_group_audit.get('same_roster_groups', 0)}/{trip_group_audit.get('groups_total', 0)}."  # noqa: E501
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
        if (
            any(issue.startswith("MANDATORY_GROUP_SPLIT") for issue in issue_pool)
            or trip_group_audit.get("split_groups", 0) > 0
        ):
            recommendations.append(
                "Revise os grupos ida/volta preservados no CSP e confirme se o pairing deve ser rígido ou apenas preferencial."  # noqa: E501
            )
        if any(issue.startswith("MAX_DRIVING_EXCEEDED") for issue in issue_pool):
            recommendations.append(
                "Aumente as janelas de pausa ou antecipe o run-cutting para evitar estouro de direção contínua."
            )
        if any(issue.startswith("MANDATORY_REST_MISSING") for issue in issue_pool):
            recommendations.append(
                "Revise a regra configurável de descanso obrigatório da CCT e garanta uma pausa válida no meio da jornada."  # noqa: E501
            )
        if any(issue.startswith("INVALID_REST_POSITION") for issue in issue_pool):
            recommendations.append(
                "Não conte soltura ou recolhimento como descanso legal; a pausa precisa ocorrer dentro da jornada."
            )
        if any(issue.startswith("SPREAD_EXCEEDED") for issue in issue_pool):
            recommendations.append("Reduza spread por jornada ou permita mais fragmentação de duties no CSP.")
        if any(issue.startswith("UNCOVERED_TRIP") for issue in issue_pool):
            recommendations.append(
                "Valide a viabilidade física do VSP: cobertura, deadhead e teto de frota podem estar incompatíveis com a grade."  # noqa: E501
            )
        if not recommendations and issue_pool:
            recommendations.append(
                "Use os códigos estruturados de restrição para inspecionar diretamente a fase VSP ou CSP que produziu o alerta."  # noqa: E501
            )
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
        elif code.startswith(
            (
                "UNCOVERED_BLOCK",
                "SPREAD_EXCEEDED",
                "MAX_DRIVING_EXCEEDED",
                "MANDATORY_REST_MISSING",
                "INVALID_REST_POSITION",
                "DUTY_",
                "INTERSHIFT_",
                "OPERATOR_",
            )
        ):
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
        elif code.startswith("MAX_DRIVING_EXCEEDED"):
            message = "A direção contínua ultrapassou o limite configurado para a jornada."
        elif code.startswith("MANDATORY_REST_MISSING"):
            message = "A jornada não encaixou descanso obrigatório válido no meio da operação."
        elif code.startswith("INVALID_REST_POSITION"):
            message = "Uma pausa longa apareceu apenas no início/fim da jornada e não vale como descanso obrigatório."
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

    def _apply_operational_quality_mode(
        self,
        result: OptimizationResult,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        optimization_params: Optional[Dict[str, Any]],
    ) -> OptimizationResult:
        mode = self._resolve_operational_quality_mode(
            optimization_params=optimization_params,
            vsp_params=vsp_params,
            cct_params=cct_params,
        )
        result.meta = dict(result.meta or {})

        baseline_candidate = self._build_operational_quality_candidate(
            scenario_id="current_plan",
            title="Plano atual",
            result=result,
            trips=trips,
            vehicle_types=vehicle_types,
            cct_params=cct_params,
            vsp_params=vsp_params,
        )
        candidates = [baseline_candidate]

        plus_one_candidate = self._build_plus_one_duty_candidate(
            base_result=result,
            trips=trips,
            vehicle_types=vehicle_types,
            cct_params=cct_params,
            vsp_params=vsp_params,
            optimization_params=optimization_params,
        )
        if plus_one_candidate is not None:
            candidates.append(plus_one_candidate)

        decision = self._select_operational_quality_scenario(mode, candidates)
        chosen_id = str(decision.get("chosen_scenario") or baseline_candidate["scenario_id"])
        chosen_candidate = next(
            (candidate for candidate in candidates if candidate["scenario_id"] == chosen_id),
            baseline_candidate,
        )

        if chosen_candidate["scenario_id"] != baseline_candidate["scenario_id"]:
            result.csp = chosen_candidate["result"].csp
            result.total_cost = float(chosen_candidate["result"].total_cost)
            self._refresh_result_summary_meta(result, vehicle_types, trips, cct_params, vsp_params)

        result.meta["chosen_scenario"] = chosen_candidate["scenario_id"]
        result.meta["rejected_scenarios"] = list(decision.get("rejected_scenarios") or [])
        result.meta["justification"] = list(decision.get("justification") or [])
        result.meta["trade_offs"] = list(decision.get("trade_offs") or [])
        result.meta["operational_quality_decision"] = decision
        logger.info(
            "[OP-QUALITY] mode=%s chosen_scenario=%s candidates=%d",
            mode,
            result.meta["chosen_scenario"],
            len(candidates),
        )
        return result

    # Sprint J-1: thin wrapper — implementação em operational_quality_helpers.py
    def _resolve_operational_quality_mode(
        self,
        optimization_params: Optional[Dict[str, Any]] = None,
        vsp_params: Optional[Dict[str, Any]] = None,
        cct_params: Optional[Dict[str, Any]] = None,
        request_metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        return _module_resolve_operational_quality_mode(optimization_params, vsp_params, cct_params, request_metadata)

    def _ensure_operational_quality_decision(
        self,
        result: OptimizationResult,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        optimization_params: Optional[Dict[str, Any]],
    ) -> OptimizationResult:
        meta = dict(result.meta or {})
        chosen_scenario = meta.get("chosen_scenario")
        decision = meta.get("operational_quality_decision")
        decision_chosen = decision.get("chosen_scenario") if isinstance(decision, dict) else None
        if chosen_scenario and decision_chosen:
            return result

        logger.warning(
            "[OP-QUALITY] missing decision after primary apply; rebuilding decision mode=%s",
            self._resolve_operational_quality_mode(
                optimization_params=optimization_params,
                vsp_params=vsp_params,
                cct_params=cct_params,
            ),
        )
        return self._apply_operational_quality_mode(
            result=result,
            trips=trips,
            vehicle_types=vehicle_types,
            cct_params=cct_params,
            vsp_params=vsp_params,
            optimization_params=optimization_params,
        )

    def _refresh_result_summary_meta(
        self,
        result: OptimizationResult,
        vehicle_types: List[VehicleType],
        trips: List[Trip],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
    ) -> None:
        cost_breakdown = self.evaluator.total_cost_breakdown(result, vehicle_types)
        result.total_cost = float(cost_breakdown["total"])
        result.meta["cost_breakdown"] = cost_breakdown
        result.meta["roster_count"] = result.csp.meta.get("roster_count", 0)
        result.meta["operational_kpis"] = self._build_operational_kpis(result, cct_params)
        result.meta["trip_group_audit"] = self._build_trip_group_audit(result, trips)
        result.meta["phase_summary"] = self._build_phase_summary(result, cost_breakdown)
        result.meta["parameter_effect_report"] = self._build_parameter_effect_report(
            result,
            trips,
            cct_params,
            vsp_params,
        )
        result.meta["solver_explanation"] = self._build_solver_explanation(result)

    def _build_operational_quality_candidate(
        self,
        scenario_id: str,
        title: str,
        result: OptimizationResult,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        candidate_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        preview = copy.deepcopy(result)
        self._refresh_result_summary_meta(preview, vehicle_types, trips, cct_params, vsp_params)
        audit = self.validator.audit_result(preview, trips, cct_params, vsp_params)
        summary = self._summarize_operational_quality(preview, audit)
        return {
            "scenario_id": scenario_id,
            "title": title,
            "candidate_note": candidate_note,
            "result": preview,
            "summary": summary,
        }

    def _build_plus_one_duty_candidate(
        self,
        base_result: OptimizationResult,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        optimization_params: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if len(base_result.csp.duties or []) < 1:
            return None

        duties = list(base_result.csp.duties or [])
        ranked = sorted(
            duties,
            key=lambda duty: self._duty_exception_rank(duty),
        )
        if not ranked:
            return None

        csp = self._make_csp(cct_params, vsp_params, optimization_params)
        candidate_pool: List[Dict[str, Any]] = []
        next_duty_id = max((int(duty.id) for duty in duties), default=0) + 1

        for source in ranked[:3]:
            if len(source.tasks) <= 1:
                continue
            source_summary = self._classify_duty_severity(source)
            if source_summary["severity"] == "acceptable":
                continue
            for split_idx in range(1, len(source.tasks)):
                left = self._clone_duty_slice(source, source.tasks[:split_idx], int(source.id))
                right = self._clone_duty_slice(source, source.tasks[split_idx:], next_duty_id)
                candidate_duties = [copy.deepcopy(duty) for duty in duties if int(duty.id) != int(source.id)]
                candidate_duties.extend([left, right])
                try:
                    finalized = _finalize_duties(
                        csp,
                        candidate_duties,
                        original_blocks=copy.deepcopy(base_result.vsp.blocks),
                    )
                except Exception as exc:
                    logger.warning("[OP-QUALITY] plus_one_candidate_failed=%s", exc)
                    return None
                if finalized.uncovered_blocks:
                    continue

                candidate_result = OptimizationResult(
                    vsp=copy.deepcopy(base_result.vsp),
                    csp=finalized,
                    total_cost=base_result.total_cost,
                    algorithm=base_result.algorithm,
                    total_elapsed_ms=base_result.total_elapsed_ms,
                    meta=copy.deepcopy(base_result.meta or {}),
                )
                candidate = self._build_operational_quality_candidate(
                    scenario_id="plus_one_duty",
                    title="Plano +1 duty",
                    result=candidate_result,
                    trips=trips,
                    vehicle_types=vehicle_types,
                    cct_params=cct_params,
                    vsp_params=vsp_params,
                    candidate_note=f"Split da duty {source.id} em dois blocos compactos no corte {split_idx}.",
                )
                summary = candidate["summary"]
                if summary["uncovered_blocks"] > 0 or summary["unassigned_trips"] > 0:
                    continue
                candidate_pool.append(candidate)

        if not candidate_pool:
            return None

        candidate_pool.sort(
            key=lambda item: (
                item["summary"]["critical_count"],
                item["summary"]["duties_below_25_pct"],
                item["summary"]["duties_above_12h"],
                item["summary"]["avg_idle_minutes"],
                item["summary"]["total_cost"],
            )
        )
        return candidate_pool[0]

    # ─────────────────────────────────────────────────────────────────────
    # Sprint J-1: thin wrappers — implementação em operational_quality_helpers.py
    # ─────────────────────────────────────────────────────────────────────
    def _clone_duty_slice(self, source: Duty, tasks: List[Block], duty_id: int) -> Duty:
        return _module_clone_duty_slice(source, tasks, duty_id)

    def _duty_exception_rank(self, duty: Duty) -> Tuple[int, float, int, int]:
        return _module_duty_exception_rank(duty)

    def _classify_duty_severity(self, duty: Duty) -> Dict[str, Any]:
        return _module_classify_duty_severity(duty)

    def _summarize_operational_quality(self, result: OptimizationResult, audit: Dict[str, Any]) -> Dict[str, Any]:
        return _module_summarize_operational_quality(result, audit)

    def compare_scenarios(
        self,
        current_plan: Dict[str, Any],
        candidate: Dict[str, Any],
    ) -> Dict[str, Any]:
        current = current_plan["summary"]
        proposed = candidate["summary"]
        blocking_reasons: List[str] = []
        if int(proposed.get("unassigned_trips", 0)) > int(current.get("unassigned_trips", 0)):
            blocking_reasons.append("coverage_regressed_unassigned_trips")
        if int(proposed.get("uncovered_blocks", 0)) > int(current.get("uncovered_blocks", 0)):
            blocking_reasons.append("coverage_regressed_uncovered_blocks")
        if int(proposed.get("hard_violation_count", 0)) > int(current.get("hard_violation_count", 0)):
            blocking_reasons.append("hard_violations_increased")

        criteria = [
            ("duties_below_25_pct", "duties_lt_25"),
            ("duties_above_12h", "duties_gt_12h"),
            ("avg_idle_minutes", "avg_idle_minutes"),
            ("mandatory_rest_missing", "mandatory_rest_missing"),
            ("overtime_minutes", "overtime_minutes"),
        ]
        improvements: List[str] = []
        regressions: List[str] = []
        unchanged: List[str] = []
        deltas: Dict[str, Dict[str, float]] = {}
        for key, label in criteria:
            before = float(current.get(key, 0) or 0)
            after = float(proposed.get(key, 0) or 0)
            delta = round(after - before, 2)
            deltas[label] = {"before": before, "after": after, "delta": delta}
            if after < before:
                improvements.append(label)
            elif after > before:
                regressions.append(label)
            else:
                unchanged.append(label)

        cost_before = float(current.get("total_cost", 0.0) or 0.0)
        cost_after = float(proposed.get("total_cost", 0.0) or 0.0)
        cost_delta = round(cost_after - cost_before, 2)
        improved_count = len(improvements)
        materially_better = not blocking_reasons and improved_count >= 2

        logger.info(
            "\n[OP-DECISION]\n"
            "- current_plan metrics: total_cost=%.2f, duties_lt_25=%d, duties_gt_12h=%d, idle=%.2f, rest_missing=%d, overtime=%d\n"  # noqa: E501
            "- candidate metrics: total_cost=%.2f, duties_lt_25=%d, duties_gt_12h=%d, idle=%.2f, rest_missing=%d, overtime=%d\n"  # noqa: E501
            "- motivos da escolha: blocking=%s, improvements=%s, materially_better=%s",
            cost_before,
            current.get("duties_below_25_pct", 0),
            current.get("duties_above_12h", 0),
            current.get("avg_idle_minutes", 0),
            current.get("mandatory_rest_missing", 0),
            current.get("overtime_minutes", 0),
            cost_after,
            proposed.get("duties_below_25_pct", 0),
            proposed.get("duties_above_12h", 0),
            proposed.get("avg_idle_minutes", 0),
            proposed.get("mandatory_rest_missing", 0),
            proposed.get("overtime_minutes", 0),
            blocking_reasons,
            improvements,
            materially_better,
        )

        return {
            "current_scenario": current_plan["scenario_id"],
            "candidate_scenario": candidate["scenario_id"],
            "coverage_ok": not any(reason.startswith("coverage_regressed") for reason in blocking_reasons),
            "hard_violation_ok": "hard_violations_increased" not in blocking_reasons,
            "blocking_reasons": blocking_reasons,
            "improvements": improvements,
            "regressions": regressions,
            "unchanged": unchanged,
            "improved_count": improved_count,
            "cost_delta": cost_delta,
            "cost_increased": cost_delta > 0.01,
            "materially_better": materially_better,
            "metrics": deltas,
        }

    def _select_operational_quality_scenario(
        self,
        mode: str,
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        baseline_candidate = next(
            (candidate for candidate in candidates if candidate["scenario_id"] == "current_plan"),
            candidates[0],
        )
        cheapest = min(
            candidates,
            key=lambda item: (
                item["summary"]["hard_violation_count"],
                item["summary"]["total_cost"],
                item["summary"]["duties"],
                item["summary"]["crew"],
            ),
        )
        balanced = min(
            candidates,
            key=lambda item: (
                item["summary"]["hard_violation_count"],
                item["summary"]["critical_count"],
                item["summary"]["duties_below_25_pct"],
                item["summary"]["total_cost"],
                item["summary"]["duties"],
            ),
        )
        strict_candidates = [
            item
            for item in candidates
            if item["summary"]["hard_violation_count"] == 0
            and item["summary"]["critical_count"] == 0
            and item["summary"]["duties_below_25_pct"] == 0
        ]
        if strict_candidates:
            strict = min(strict_candidates, key=lambda item: (item["summary"]["total_cost"], item["summary"]["duties"]))
        else:
            strict = min(
                candidates,
                key=lambda item: (
                    item["summary"]["hard_violation_count"],
                    item["summary"]["critical_count"],
                    item["summary"]["duties_below_25_pct"],
                    item["summary"]["total_cost"],
                    item["summary"]["duties"],
                ),
            )

        label_map: Dict[str, List[str]] = {}
        for scenario, label in (
            (cheapest["scenario_id"], "Plano mais barato"),
            (balanced["scenario_id"], "Plano mais equilibrado"),
        ):
            label_map.setdefault(str(scenario), []).append(label)
        if strict["summary"]["critical_count"] == 0 and strict["summary"]["hard_violation_count"] == 0:
            label_map.setdefault(str(strict["scenario_id"]), []).append("Plano sem excecoes criticas")

        for candidate in candidates:
            candidate["summary"]["labels"] = label_map.get(candidate["scenario_id"], [])

        operational_comparisons: List[Dict[str, Any]] = []
        operational_winners: List[Tuple[int, int, float, float, Dict[str, Any], Dict[str, Any]]] = []
        for candidate in candidates:
            if candidate["scenario_id"] == baseline_candidate["scenario_id"]:
                continue
            comparison = self.compare_scenarios(baseline_candidate, candidate)
            operational_comparisons.append(comparison)
            if comparison["materially_better"]:
                operational_winners.append(
                    (
                        -int(comparison["improved_count"]),
                        int(candidate["summary"].get("hard_violation_count", 0)),
                        float(candidate["summary"].get("avg_idle_minutes", 0)),
                        float(candidate["summary"].get("total_cost", 0)),
                        candidate,
                        comparison,
                    )
                )

        default_mode_choice = {
            "strict": strict,
            "balanced": balanced,
            "optimized": cheapest,
        }.get(mode, balanced)
        chosen = default_mode_choice
        chosen_comparison: Optional[Dict[str, Any]] = None

        if operational_winners:
            operational_winners.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4]["scenario_id"]))
            chosen = operational_winners[0][4]
            chosen_comparison = operational_winners[0][5]
            chosen["summary"]["labels"] = list(
                dict.fromkeys([*chosen["summary"].get("labels", []), "Melhor operacionalmente"])
            )
        elif default_mode_choice["scenario_id"] != baseline_candidate["scenario_id"]:
            chosen_comparison = self.compare_scenarios(baseline_candidate, default_mode_choice)

        rejected: List[Dict[str, Any]] = []
        for candidate in candidates:
            if candidate["scenario_id"] == chosen["scenario_id"]:
                continue
            comparison = self.compare_scenarios(baseline_candidate, candidate)
            rejected.append(
                {
                    "scenario_id": candidate["scenario_id"],
                    "title": candidate["title"],
                    "reason": self._scenario_rejection_reason(mode, chosen, candidate, comparison),
                    "comparison_vs_current_plan": comparison,
                    "summary": candidate["summary"],
                }
            )

        chosen_summary = chosen["summary"]
        justification = self._scenario_justification(
            mode,
            chosen,
            strict,
            balanced,
            cheapest,
            baseline_candidate,
            chosen_comparison,
        )
        trade_offs = self._scenario_tradeoffs(chosen, candidates, chosen_comparison)
        logger.info(
            "[OP-DECISION] mode=%s chosen=%s default_choice=%s operational_override=%s comparison=%s",
            mode,
            chosen["scenario_id"],
            default_mode_choice["scenario_id"],
            bool(operational_winners),
            chosen_comparison,
        )
        return {
            "mode": mode,
            "chosen_scenario": chosen["scenario_id"],
            "chosen_title": chosen["title"],
            "justification": justification,
            "trade_offs": trade_offs,
            "rejected_scenarios": rejected,
            "comparison_to_current_plan": chosen_comparison,
            "criteria": {
                "strict": "Prioriza eliminar duties criticas e duties abaixo de 25%; pode aceitar +1 duty/crew.",
                "balanced": "Publica candidato quando nao piora cobertura, nao aumenta hard violations e melhora ao menos 2 KPIs operacionais.",  # noqa: E501
                "optimized": "Prioriza menor custo total entre cenarios operacionais viaveis.",
            },
            "available_scenarios": [
                {
                    "scenario_id": candidate["scenario_id"],
                    "title": candidate["title"],
                    "labels": candidate["summary"]["labels"],
                    "summary": candidate["summary"],
                    "candidate_note": candidate.get("candidate_note"),
                }
                for candidate in candidates
            ],
            "selected_summary": chosen_summary,
        }

    # Sprint J-1: thin wrappers — implementação em operational_quality_helpers.py
    def _scenario_rejection_reason(
        self, mode: str, chosen: Dict[str, Any], rejected: Dict[str, Any], comparison: Optional[Dict[str, Any]] = None
    ) -> str:
        return _module_scenario_rejection_reason(mode, chosen, rejected, comparison)

    def _scenario_justification(
        self,
        mode: str,
        chosen: Dict[str, Any],
        strict: Dict[str, Any],
        balanced: Dict[str, Any],
        cheapest: Dict[str, Any],
        current_plan: Dict[str, Any],
        comparison: Optional[Dict[str, Any]],
    ) -> List[str]:
        return _module_scenario_justification(mode, chosen, strict, balanced, cheapest, current_plan, comparison)

    def _scenario_tradeoffs(
        self, chosen: Dict[str, Any], candidates: List[Dict[str, Any]], comparison: Optional[Dict[str, Any]]
    ) -> List[str]:
        return _module_scenario_tradeoffs(chosen, candidates, comparison)

    def _build_operational_kpis(self, result: OptimizationResult, cct_params: Dict[str, Any]) -> Dict[str, Any]:
        duties = list(result.csp.duties or [])
        blocks_list = list(result.vsp.blocks or [])
        num_blocks = len(blocks_list)

        # ── Métricas VSP ────────────────────────────────────────────────────────
        total_trips = sum(len(b.trips) for b in blocks_list)
        trips_per_vehicle = round(total_trips / max(1, num_blocks), 2)
        total_driving_min = sum(t.duration for b in blocks_list for t in b.trips)
        total_block_span_min = sum((b.trips[-1].end_time - b.trips[0].start_time) for b in blocks_list if b.trips)
        avg_block_duration_h = round(total_block_span_min / max(1, num_blocks) / 60.0, 2)
        fleet_utilization_pct = round(100.0 * total_driving_min / max(1, total_block_span_min), 1)
        # Deadhead: lacunas entre viagens consecutivas do mesmo bloco
        total_deadhead_min = sum(
            b.trips[k + 1].start_time - b.trips[k].end_time
            for b in blocks_list
            if len(b.trips) > 1
            for k in range(len(b.trips) - 1)
            if b.trips[k + 1].start_time - b.trips[k].end_time > 0
        )
        total_distance_km = sum(t.distance_km for b in blocks_list for t in b.trips)

        # ── Métricas CSP ────────────────────────────────────────────────────────
        if not duties:
            empty_fairness = {
                "target_work_minutes": int(cct_params.get("fairness_target_work_minutes", 420) or 420),
                "tolerance_minutes": int(cct_params.get("fairness_tolerance_minutes", 30) or 30),
                "d_plus_total": 0,
                "d_minus_total": 0,
                "within_band_count": 0,
                "outside_band_count": 0,
                "avg_work_minutes": 0.0,
            }
            return {
                "vehicles": num_blocks,
                "crew": 0,
                "work_minutes": 0,
                "paid_minutes": 0,
                "paid_work_delta_minutes": 0,
                "trips_per_vehicle": trips_per_vehicle,
                "avg_block_duration_h": avg_block_duration_h,
                "fleet_utilization_pct": fleet_utilization_pct,
                "total_deadhead_min": total_deadhead_min,
                "total_distance_km": round(total_distance_km, 2),
                "duties_with_overtime": 0,
                "overtime_rate_pct": 0.0,
                "avg_overtime_min_per_duty": 0.0,
                "fairness": empty_fairness,
                "stretch_kpi": {"operators_with_assignment": 0, "avg_vehicle_changes_per_operator": 0.0},
                "executive_summary": {},
            }

        target = int(cct_params.get("fairness_target_work_minutes", 420) or 420)
        tolerance = int(cct_params.get("fairness_tolerance_minutes", 30) or 30)

        total_work = sum(int(d.work_time or 0) for d in duties)
        total_paid = sum(int(d.paid_minutes or d.work_time or 0) for d in duties)
        total_spread = sum(int(d.spread_time or d.work_time or 0) for d in duties)
        total_overtime = sum(int(d.overtime_minutes or 0) for d in duties)

        d_plus_total = 0
        d_minus_total = 0
        within_band = 0
        outside_band = 0
        duties_with_overtime = 0

        operator_blocks: Dict[int, set] = {}
        for duty in duties:
            work = int(duty.work_time or 0)
            d_plus_total += max(0, work - target)
            d_minus_total += max(0, target - work)
            if abs(work - target) <= tolerance:
                within_band += 1
            else:
                outside_band += 1
            if (duty.overtime_minutes or 0) > 0:
                duties_with_overtime += 1
            operator_id = duty.meta.get("operator_id")
            if operator_id is not None:
                source_blocks = {int(item) for item in duty.meta.get("source_block_ids", []) if item is not None}
                operator_blocks.setdefault(int(operator_id), set()).update(source_blocks)

        stretch_values = [max(0, len(bks) - 1) for bks in operator_blocks.values() if bks]
        avg_vehicle_changes = round(sum(stretch_values) / len(stretch_values), 3) if stretch_values else 0.0

        overtime_rate_pct = round(100.0 * duties_with_overtime / max(1, len(duties)), 1)
        avg_overtime_min = round(total_overtime / max(1, len(duties)), 2)

        # Deadhead como % do spread total das jornadas (mede "tempo improdutivo do veículo")
        deadhead_pct = round(100.0 * total_deadhead_min / max(1, total_spread), 1)

        # ── Resumo financeiro executivo ─────────────────────────────────────────
        # cost_breakdown já calculado antes desta chamada; acessado via result.meta
        cost_bd = (result.meta or {}).get("cost_breakdown") or {}
        total_cost = float(cost_bd.get("total", 0.0) or 0.0)
        vsp_cost = float((cost_bd.get("vsp") or {}).get("total", 0.0) or 0.0)
        csp_cost = float((cost_bd.get("csp") or {}).get("total", 0.0) or 0.0)

        cost_per_trip = round(total_cost / max(1, total_trips), 2)
        cost_per_productive_hour = round(total_cost / max(0.01, total_driving_min / 60.0), 2)
        cost_per_km = round(total_cost / total_distance_km, 2) if total_distance_km > 0 else None

        executive_summary = {
            # ── Custos ──
            "total_cost_brl": round(total_cost, 2),
            "fleet_cost_brl": round(vsp_cost, 2),
            "crew_cost_brl": round(csp_cost, 2),
            "fleet_cost_share_pct": round(100.0 * vsp_cost / max(1.0, total_cost), 1),
            "crew_cost_share_pct": round(100.0 * csp_cost / max(1.0, total_cost), 1),
            # ── Eficiência de custo ──
            "cost_per_trip_brl": cost_per_trip,
            "cost_per_km_brl": cost_per_km,
            "cost_per_productive_hour_brl": cost_per_productive_hour,
            # ── Eficiência operacional ──
            "fleet_utilization_pct": fleet_utilization_pct,
            "trips_per_vehicle": trips_per_vehicle,
            "overtime_rate_pct": overtime_rate_pct,
            "deadhead_pct_of_spread": deadhead_pct,
            # ── Volume ──
            "total_trips": total_trips,
            "total_distance_km": round(total_distance_km, 2),
            "total_driving_hours": round(total_driving_min / 60.0, 2),
            "total_deadhead_min": total_deadhead_min,
        }

        return {
            # ── Contagens base (compatibilidade com versão anterior) ────────────
            "vehicles": num_blocks,
            "crew": len(duties),
            "work_minutes": total_work,
            "paid_minutes": total_paid,
            "paid_work_delta_minutes": max(0, total_paid - total_work),
            # ── KPIs de frota ───────────────────────────────────────────────────
            "trips_per_vehicle": trips_per_vehicle,
            "avg_block_duration_h": avg_block_duration_h,
            "fleet_utilization_pct": fleet_utilization_pct,
            "total_deadhead_min": total_deadhead_min,
            "total_distance_km": round(total_distance_km, 2),
            # ── KPIs de tripulação ──────────────────────────────────────────────
            "duties_with_overtime": duties_with_overtime,
            "overtime_rate_pct": overtime_rate_pct,
            "avg_overtime_min_per_duty": avg_overtime_min,
            # ── Equidade de jornada ─────────────────────────────────────────────
            "fairness": {
                "target_work_minutes": target,
                "tolerance_minutes": tolerance,
                "d_plus_total": d_plus_total,
                "d_minus_total": d_minus_total,
                "within_band_count": within_band,
                "outside_band_count": outside_band,
                "avg_work_minutes": round(total_work / max(1, len(duties)), 2),
            },
            # ── Mobilidade de veículos por operador ─────────────────────────────
            "stretch_kpi": {
                "operators_with_assignment": len(operator_blocks),
                "avg_vehicle_changes_per_operator": avg_vehicle_changes,
            },
            # ── Resumo executivo para Dashboard ────────────────────────────────
            "executive_summary": executive_summary,
        }

    def _dispatch(
        self,
        algorithm: AlgorithmType,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int],
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        optimization_params: Optional[Dict[str, Any]],
        effective_time_budget_s: float,
    ) -> OptimizationResult:
        # Delegamos para o módulo extraído (algorithm_dispatcher.py). Injetamos os
        # factories de CSP que dependem do estado deste service (evaluator, validator).
        return dispatch_algorithm(
            algorithm,
            trips=trips,
            vehicle_types=vehicle_types,
            depot_id=depot_id,
            cct_params=cct_params,
            vsp_params=vsp_params,
            optimization_params=optimization_params,
            effective_time_budget_s=effective_time_budget_s,
            csp_factory=self._make_csp,
            set_covering_factory=self._make_set_covering_csp,
        )

    # NOTE: Os métodos _run_greedy/_run_genetic/_run_sa/_run_ts/_run_sp/_run_mcnf/
    # _run_joint/_run_hybrid/_run_vcsp_pulp/_run_assignment_vsp foram movidos para
    # services/algorithm_dispatcher.py (Sprint I — split incremental do monolito).
    # Caso necessite chamar diretamente sem passar pelo dispatcher, importe de lá.

    # ─────────────────────────────────────────────────────────────────────
    # Sprint I-2: lógica movida para services/parameter_normalization.py.
    # Mantemos thin wrappers para compatibilidade interna (testes monkey-patcham
    # alguns métodos via `self._method`).
    # ─────────────────────────────────────────────────────────────────────
    def _as_dict(self, params: Any) -> Dict[str, Any]:
        return _module_as_dict(params)

    def _normalize_rules(self, params: Any) -> Dict[str, Any]:
        return _module_normalize_rules(params)

    # ─────────────────────────────────────────────────────────────────────
    # Sprint I-3: thin wrappers — implementação em trip_group_inference.py
    # ─────────────────────────────────────────────────────────────────────
    def _inject_trip_group_constraints(
        self, trips: List[Trip], cct_params: Dict[str, Any], vsp_params: Dict[str, Any]
    ) -> None:
        return _module_inject_trip_group_constraints(trips, cct_params, vsp_params)

    def _materialize_mandatory_trip_groups(self, trips: List[Trip], groups: List[List[int]], seed: int) -> None:
        return _module_materialize_mandatory_trip_groups(trips, groups, seed)

    def _infer_round_trip_pairs(self, trips: List[Trip], vsp_params: Dict[str, Any]) -> List[List[int]]:
        return _module_infer_round_trip_pairs(trips, vsp_params)

    # ─────────────────────────────────────────────────────────────────────
    # Sprint I-2: thin wrappers — implementação em parameter_normalization.py
    # ─────────────────────────────────────────────────────────────────────
    def _align_vsp_params_with_cct(self, cct_params: Dict[str, Any], vsp_params: Dict[str, Any]) -> None:
        return _module_align_vsp_params_with_cct(cct_params, vsp_params)

    def _strict_trip_group_mode(
        self, trips: List[Trip], cct_params: Dict[str, Any], vsp_params: Dict[str, Any]
    ) -> bool:
        return _module_is_strict_trip_group_mode(trips, cct_params, vsp_params)

    def _validate_strict_algorithm_support(
        self, algorithm: AlgorithmType, trips: List[Trip], cct_params: Dict[str, Any], vsp_params: Dict[str, Any]
    ) -> None:
        return _module_validate_strict_algorithm_support(algorithm, trips, cct_params, vsp_params)

    def _ensure_deadhead_coverage(
        self,
        trips: List[Trip],
        vsp_params: Dict[str, Any],
    ) -> None:
        if not trips:
            return

        terminal_coords: Dict[int, tuple[float, float]] = {}
        for trip in trips:
            if trip.origin_latitude is not None and trip.origin_longitude is not None:
                terminal_coords.setdefault(
                    int(trip.origin_id), (float(trip.origin_latitude), float(trip.origin_longitude))
                )
            if trip.destination_latitude is not None and trip.destination_longitude is not None:
                terminal_coords.setdefault(
                    int(trip.destination_id), (float(trip.destination_latitude), float(trip.destination_longitude))
                )

        origin_ids = sorted({int(trip.origin_id) for trip in trips})
        fallback_speed_kmh = float(vsp_params.get("fallback_deadhead_speed_kmh", 18.0) or 18.0)
        fallback_floor = int(vsp_params.get("fallback_deadhead_floor_minutes", 8) or 8)
        impossible_deadhead = int(vsp_params.get("unknown_deadhead_minutes", 999999) or 999999)

        for trip in trips:
            trip.deadhead_times = dict(trip.deadhead_times or {})
            dest_coords = terminal_coords.get(int(trip.destination_id))
            for origin_id in origin_ids:
                if origin_id in trip.deadhead_times:
                    continue
                if int(trip.destination_id) == int(origin_id):
                    trip.deadhead_times[origin_id] = 0
                    continue
                origin_coords = terminal_coords.get(int(origin_id))
                if dest_coords is None or origin_coords is None:
                    trip.deadhead_times[origin_id] = impossible_deadhead
                    continue
                trip.deadhead_times[origin_id] = self._estimate_deadhead_minutes(
                    dest_coords,
                    origin_coords,
                    fallback_speed_kmh,
                    fallback_floor,
                )

    def _estimate_deadhead_minutes(
        self,
        from_coords: tuple[float, float],
        to_coords: tuple[float, float],
        speed_kmh: float,
        floor_minutes: int,
    ) -> int:
        distance_km = self._haversine_km(from_coords, to_coords)
        if distance_km <= 0:
            return 0
        minutes = math.ceil((distance_km / max(speed_kmh, 1.0)) * 60.0)
        return max(floor_minutes, minutes)

    def _haversine_km(
        self,
        from_coords: tuple[float, float],
        to_coords: tuple[float, float],
    ) -> float:
        lat1, lon1 = from_coords
        lat2, lon2 = to_coords
        radius_km = 6371.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        return 2.0 * radius_km * math.atan2(math.sqrt(a), math.sqrt(max(1.0 - a, 0.0)))

    def _ensure_vsp_operational_warnings(
        self,
        result: OptimizationResult,
        vehicle_types: List[VehicleType],
        vsp_params: Dict[str, Any],
    ) -> None:
        warnings = list(getattr(result.vsp, "warnings", []) or [])
        meta = dict(getattr(result.vsp, "meta", {}) or {})
        max_chargers = int(
            vsp_params.get("max_simultaneous_chargers", meta.get("max_simultaneous_chargers", 999999)) or 999999
        )
        electric_vehicle = next(
            (
                vehicle
                for vehicle in vehicle_types
                if vehicle.is_electric and vehicle.battery_capacity_kwh > 0 and vehicle.charge_rate_kw > 0
            ),
            None,
        )

        charger_peak = 0
        if electric_vehicle is not None and max_chargers < 999999:
            charger_peak = self._estimate_charger_peak(result.vsp.blocks or [], electric_vehicle)
            meta["charger_peak_concurrency"] = charger_peak
            meta["max_simultaneous_chargers"] = max_chargers
            if charger_peak > max_chargers:
                meta["charger_capacity_exceeded"] = True
                warning = f"CHARGER_CAPACITY_EXCEEDED peak={charger_peak}>{max_chargers}"
                if warning not in warnings:
                    warnings.append(warning)
            else:
                meta["charger_capacity_exceeded"] = False
        elif "charger_capacity_exceeded" not in meta:
            meta["charger_capacity_exceeded"] = False

        result.vsp.warnings = warnings
        result.vsp.meta = meta

    def _estimate_charger_peak(
        self,
        blocks: List[Any],
        vehicle: VehicleType,
    ) -> int:
        timeline: List[tuple[int, int]] = []
        for block in blocks:
            trips = list(getattr(block, "trips", []) or [])
            if not trips:
                continue

            home_depot = block.meta.get("start_depot_id") if getattr(block, "meta", None) else None
            if home_depot is None:
                home_depot = trips[0].depot_id

            current_soc = float(vehicle.battery_capacity_kwh)
            for index, trip in enumerate(trips):
                current_soc = max(0.0, current_soc - self._estimate_trip_energy_need(trip, vehicle))
                if index + 1 >= len(trips):
                    continue

                nxt = trips[index + 1]
                gap = int(nxt.start_time - trip.end_time)
                can_charge = (
                    gap > 0
                    and home_depot is not None
                    and nxt.depot_id is not None
                    and nxt.depot_id == home_depot
                    and current_soc < float(vehicle.battery_capacity_kwh)
                )
                if not can_charge:
                    continue

                charge_window_start = int(nxt.start_time - gap)
                timeline.append((charge_window_start, 1))
                timeline.append((int(nxt.start_time), -1))
                charged = min(
                    float(vehicle.charge_rate_kw) * (gap / 60.0),
                    float(vehicle.battery_capacity_kwh) - current_soc,
                )
                current_soc = min(float(vehicle.battery_capacity_kwh), current_soc + max(0.0, charged))

        concurrent = 0
        peak = 0
        for _, delta in sorted(timeline):
            concurrent += delta
            peak = max(peak, concurrent)
        return peak

    def _estimate_trip_energy_need(self, trip: Trip, vehicle: VehicleType) -> float:
        if getattr(trip, "energy_kwh", 0.0) > 0:
            base = float(trip.energy_kwh)
        else:
            base = float(getattr(trip, "distance_km", 0.0) or 0.0) * 1.25
        topo_factor = 1.0 + max(0.0, float(getattr(trip, "elevation_gain_m", 0.0) or 0.0)) * 0.0008
        return base * topo_factor

    def _parse_rule(self, rule: str) -> Dict[str, Any]:
        # Sprint I-2: lógica em parameter_normalization.parse_rule
        return _module_parse_rule(rule)

    def _make_csp(
        self,
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        optimization_params: Optional[Dict[str, Any]] = None,
    ):
        # Merge optimization_params into cct_params for CSP solvers
        full_params = {**cct_params}
        if optimization_params:
            full_params.update(optimization_params)

        if vsp_params.get("use_set_covering") or vsp_params.get("pricing_enabled"):
            return self._make_set_covering_csp(full_params, vsp_params)
        return GreedyCSP(vsp_params=vsp_params, **full_params)

    def _make_set_covering_csp(
        self,
        cct_params: Dict[str, Any],
        vsp_params: Dict[str, Any],
        prefer_solver: Optional[str] = None,
    ):
        """Constrói CSP de set covering. BUG-02 fix (auditoria 2026-05-17):
        permite escolher explicitamente entre CP-SAT (OR-Tools) e PuLP/CBC.

        prefer_solver:
            - "cp_sat"   → força OR-Tools CP-SAT (raise se não disponível)
            - "pulp_cbc" → força PuLP+CBC (não usa OR-Tools mesmo se disponível)
            - None       → comportamento padrão: CP-SAT se disponível, senão CBC
        """
        if prefer_solver == "pulp_cbc":
            return SetPartitioningOptimizedCSP(vsp_params=vsp_params, **cct_params)

        if prefer_solver == "cp_sat":
            try:
                from ortools.sat.python import cp_model as _  # noqa: F401
            except ImportError as exc:
                raise InvalidAlgorithmError(
                    "AlgorithmType.CP_SAT requested but ortools is not installed. "
                    "Install with: pip install ortools>=9.10.0 — or choose SET_PARTITIONING."
                ) from exc
            return CPSatCSP(vsp_params=vsp_params, **cct_params)

        # Default: CP-SAT preferido, fallback silencioso para CBC se ortools indisponível
        try:
            from ortools.sat.python import cp_model as _  # noqa: F401

            return CPSatCSP(vsp_params=vsp_params, **cct_params)
        except ImportError:
            return SetPartitioningOptimizedCSP(vsp_params=vsp_params, **cct_params)
