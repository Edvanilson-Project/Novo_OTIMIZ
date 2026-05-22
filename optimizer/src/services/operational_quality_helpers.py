"""Funções puras para Operational Quality Scenarios — extraído de optimizer_service.py (Sprint J-1).

Cluster contém helpers SEM dependência de estado (`self.evaluator`/`self.validator`):
- Resolução de modo operacional (strict/balanced/optimized) a partir de params
- Classificação de severidade de duty (critical/borderline/acceptable)
- Clonagem de duty para split (preserva semântica de boundaries)
- Resumo executivo de qualidade operacional
- Mensagens de rejeição/justificativa/trade-offs entre cenários

Métodos NÃO extraídos (ainda têm acoplamento com self.evaluator/self.validator):
- `_apply_operational_quality_mode`, `_refresh_result_summary_meta`,
  `_build_operational_quality_candidate`, `_build_plus_one_duty_candidate`,
  `_select_operational_quality_scenario`, `_ensure_operational_quality_decision`
"""

from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional, Tuple

from ..domain.models import Block, Duty, OptimizationResult


def resolve_operational_quality_mode(
    optimization_params: Optional[Dict[str, Any]] = None,
    vsp_params: Optional[Dict[str, Any]] = None,
    cct_params: Optional[Dict[str, Any]] = None,
    request_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Resolve modo operacional a partir das múltiplas fontes de configuração.

    Procura `operational_quality_mode` em ordem: optimization > vsp > cct > metadata.
    Default: 'balanced' se não encontrado ou inválido.
    """
    for source in (optimization_params, vsp_params, cct_params, request_metadata):
        if not isinstance(source, dict):
            continue
        raw_mode = source.get("operational_quality_mode")
        if raw_mode is None:
            continue
        mode = str(raw_mode).strip().lower()
        if mode in {"strict", "balanced", "optimized"}:
            return mode
    return "balanced"


def classify_duty_severity(duty: Duty) -> Dict[str, Any]:
    """Classifica severidade da duty para priorização em scenarios.

    Severidade:
    - critical: utilização <25% E spread >12h E idle >6h
    - borderline: utilização <25% (mas não crítico)
    - acceptable: caso contrário
    """
    metrics = duty.meta.get("quality_metrics") or {}
    semantic_metrics = metrics.get("operational_semantic") or {}
    utilization = float(semantic_metrics.get("utilization", metrics.get("utilization", 0.0)) or 0.0)
    spread_time = int(semantic_metrics.get("spread_time", duty.spread_time) or duty.spread_time or 0)
    total_idle = int(
        semantic_metrics.get(
            "total_idle_time", metrics.get("total_idle_time", max(0, duty.spread_time - duty.work_time))
        )
        or 0
    )
    severity = "acceptable"
    if utilization < 0.25 and spread_time > 720 and total_idle > 360:
        severity = "critical"
    elif utilization < 0.25:
        severity = "borderline"
    return {
        "severity": severity,
        "utilization": utilization,
        "spread_time": spread_time,
        "total_idle_time": total_idle,
    }


def duty_exception_rank(duty: Duty) -> Tuple[int, float, int, int]:
    """Tupla de ordenação para priorizar duties em scenarios (mais crítico primeiro)."""
    classification = classify_duty_severity(duty)
    severity_rank = {"critical": 0, "borderline": 1, "acceptable": 2}[classification["severity"]]
    return (
        severity_rank,
        float(classification["utilization"]),
        -int(classification["spread_time"]),
        int(duty.id),
    )


def clone_duty_slice(source: Duty, tasks: List[Block], duty_id: int) -> Duty:
    """Clona uma fatia de tasks da duty `source` em nova Duty(`duty_id`).

    CRÍTICO: recomputa boundaries do meta (duty_start_minutes, duty_end_minutes,
    spread_time, work_time) baseado na fatia, e NÃO copia da source. Sem isso,
    operational_time_service lê valores stale do source.meta — bug detalhado em
    sprint_d_relief_ui_2026_05_08 (D24/D7 com window=555 enquanto operam 21min/100min).
    """
    cloned_tasks = [copy.deepcopy(task) for task in tasks]
    cloned = Duty(id=duty_id, meta=copy.deepcopy(source.meta or {}))
    for task in cloned_tasks:
        cloned.add_task(task)

    if cloned.tasks:
        ordered = sorted(
            (t for t in cloned.tasks if t.trips),
            key=lambda item: (item.start_time, item.id),
        )
        if ordered:
            first_task = ordered[0]
            last_task = ordered[-1]
            start_buffer = max(0, int(first_task.meta.get("task_start_buffer_minutes", 0) or 0))
            end_buffer = max(0, int(last_task.meta.get("task_end_buffer_minutes", 0) or 0))
            duty_start = int(first_task.trips[0].start_time) - start_buffer
            duty_end = int(last_task.trips[-1].end_time) + end_buffer
            cloned.meta["start_buffer_minutes"] = start_buffer
            cloned.meta["end_buffer_minutes"] = end_buffer
            cloned.meta["duty_start_minutes"] = duty_start
            cloned.meta["duty_end_minutes"] = duty_end
            cloned.spread_time = max(0, duty_end - duty_start)
            cloned.work_time = sum(
                int(task.meta.get("task_drive_minutes", sum(trip.duration for trip in task.trips)) or 0)
                for task in ordered
            )

    cloned.meta["source_block_ids"] = [int(task.id) for task in cloned.tasks]
    cloned.meta["covered_original_trip_ids"] = [
        int(getattr(trip, "public_id", trip.id)) for task in cloned.tasks for trip in task.trips
    ]
    cloned.meta["covered_trip_group_ids"] = sorted(
        {int(trip.trip_group_id) for task in cloned.tasks for trip in task.trips if trip.trip_group_id is not None}
    )
    cloned.meta["operator_id"] = None
    cloned.meta["operator_name"] = None
    return cloned


def summarize_operational_quality(
    result: OptimizationResult,
    audit: Dict[str, Any],
) -> Dict[str, Any]:
    """Resumo de qualidade do resultado para comparação entre scenarios.

    Inclui contagens de severidade, utilização média, idle médio, hard/soft violations,
    cobertura. Usado pelo selector para escolher melhor cenário operacional.
    """
    duties = list(result.csp.duties or [])
    classifications = [classify_duty_severity(duty) for duty in duties]
    utilizations = [float(item["utilization"]) for item in classifications]
    idle_values = [int(item["total_idle_time"]) for item in classifications]
    hard_issues = list(audit.get("hard_issues") or [])
    soft_issues = list(audit.get("soft_issues") or [])
    mandatory_rest_missing = sum(1 for issue in soft_issues if str(issue).startswith("MANDATORY_REST_MISSING"))
    labels: List[str] = []
    return {
        "total_cost": round(float(result.total_cost or 0.0), 2),
        "vehicles": int(result.vsp.num_vehicles),
        "duties": len(duties),
        "crew": int(result.csp.num_crew),
        "duties_below_25_pct": sum(1 for item in classifications if float(item["utilization"]) < 0.25),
        "duties_below_30_pct": sum(1 for item in classifications if float(item["utilization"]) < 0.30),
        "duties_above_12h": sum(1 for duty in duties if int(duty.spread_time or 0) > 720),
        "avg_utilization_pct": round((sum(utilizations) / max(1, len(utilizations))) * 100.0, 2),
        "avg_idle_minutes": round(sum(idle_values) / max(1, len(idle_values)), 2),
        "overtime_minutes": sum(int(duty.overtime_minutes or 0) for duty in duties),
        "mandatory_rest_missing": mandatory_rest_missing,
        "critical_count": sum(1 for item in classifications if item["severity"] == "critical"),
        "borderline_count": sum(1 for item in classifications if item["severity"] == "borderline"),
        "acceptable_count": sum(1 for item in classifications if item["severity"] == "acceptable"),
        "hard_violation_count": len(hard_issues),
        "soft_violation_count": len(soft_issues),
        "uncovered_blocks": len(result.csp.uncovered_blocks or []),
        "unassigned_trips": len(result.vsp.unassigned_trips or []),
        "labels": labels,
    }


def scenario_rejection_reason(
    mode: str,
    chosen: Dict[str, Any],
    rejected: Dict[str, Any],
    comparison: Optional[Dict[str, Any]] = None,
) -> str:
    """Razão pedagógica para rejeitar um candidato em favor de outro."""
    comparison = comparison or {}
    chosen_summary = chosen["summary"]
    rejected_summary = rejected["summary"]
    blocking_reasons = list(comparison.get("blocking_reasons") or [])
    if (
        "coverage_regressed_unassigned_trips" in blocking_reasons
        or "coverage_regressed_uncovered_blocks" in blocking_reasons
    ):
        return "Piora cobertura do plano."
    if "hard_violations_increased" in blocking_reasons:
        return "Aumenta hard violations."
    if rejected["scenario_id"] != "current_plan" and int(comparison.get("improved_count", 0) or 0) < 2:
        return "Nao melhora ao menos 2 KPIs operacionais frente ao current_plan."
    if mode == "optimized" and rejected_summary["total_cost"] > chosen_summary["total_cost"]:
        return "Custo total maior do que o cenario escolhido."
    if rejected_summary["critical_count"] > chosen_summary["critical_count"]:
        return "Mantem mais excecoes criticas do que o cenario escolhido."
    if rejected_summary["duties_below_25_pct"] > chosen_summary["duties_below_25_pct"]:
        return "Mantem mais duties abaixo de 25%."
    if rejected_summary["duties"] > chosen_summary["duties"]:
        return "Exige mais duties sem compensar em qualidade operacional."
    return "Perde no criterio principal do modo operacional selecionado."


def scenario_justification(
    mode: str,
    chosen: Dict[str, Any],
    strict: Dict[str, Any],
    balanced: Dict[str, Any],
    cheapest: Dict[str, Any],
    current_plan: Dict[str, Any],
    comparison: Optional[Dict[str, Any]],
) -> List[str]:
    """Lista de mensagens explicativas para o cenário escolhido."""
    chosen_summary = chosen["summary"]
    current_summary = current_plan["summary"]
    lines = [
        f"Modo operacional selecionado: {mode}.",
        (
            f"Cenario escolhido: {chosen['title']} ({chosen['scenario_id']}) com custo {chosen_summary['total_cost']:.2f}, "  # noqa: E501
            f"{chosen_summary['duties_below_25_pct']} duties abaixo de 25%, "
            f"{chosen_summary['mandatory_rest_missing']} mandatory_rest_missing e "
            f"{chosen_summary['critical_count']} excecao(oes) critica(s)."
        ),
    ]
    if comparison and chosen["scenario_id"] != current_plan["scenario_id"]:
        lines.append(
            f"Comparado ao current_plan, o cenario escolhido melhorou {int(comparison.get('improved_count', 0))} KPI(s): "  # noqa: E501
            + ", ".join(comparison.get("improvements") or ["sem melhoria listada"])
            + "."
        )
        if comparison.get("cost_increased"):
            lines.append(
                f"O custo aumentou {abs(float(comparison.get('cost_delta', 0.0) or 0.0)):.2f}, mas a melhora operacional foi considerada relevante."  # noqa: E501
            )
    elif chosen["scenario_id"] == current_plan["scenario_id"]:
        lines.append(
            "O current_plan foi mantido porque nenhum candidato melhorou pelo menos 2 KPIs operacionais sem piorar cobertura ou hard violations."  # noqa: E501
        )
    if mode == "strict" and chosen["scenario_id"] != strict["scenario_id"]:
        lines.append(
            "Nao houve cenario com zero duties abaixo de 25%; foi selecionado o fallback mais proximo sem aumentar hard violations."  # noqa: E501
        )
    if mode == "balanced" and chosen["scenario_id"] == balanced["scenario_id"]:
        lines.append(
            "O criterio balanced priorizou reduzir a cauda operacional antes de custo marginal ou do numero de duties."
        )
    if mode == "optimized" and chosen["scenario_id"] == cheapest["scenario_id"]:
        lines.append("O criterio optimized escolheu o menor custo total entre os cenarios viaveis.")
    if chosen["scenario_id"] != current_plan["scenario_id"]:
        lines.append(
            f"Current_plan: duties<25%={current_summary['duties_below_25_pct']}, duties>12h={current_summary['duties_above_12h']}, idle medio={current_summary['avg_idle_minutes']}, mandatory_rest_missing={current_summary['mandatory_rest_missing']}, overtime={current_summary['overtime_minutes']}."  # noqa: E501
        )
        lines.append(
            f"Escolhido: duties<25%={chosen_summary['duties_below_25_pct']}, duties>12h={chosen_summary['duties_above_12h']}, idle medio={chosen_summary['avg_idle_minutes']}, mandatory_rest_missing={chosen_summary['mandatory_rest_missing']}, overtime={chosen_summary['overtime_minutes']}."  # noqa: E501
        )
    return lines


def scenario_tradeoffs(
    chosen: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    comparison: Optional[Dict[str, Any]],
) -> List[str]:
    """Lista de trade-offs (custo vs qualidade) do cenário escolhido vs current_plan."""
    current = next((item for item in candidates if item["scenario_id"] == "current_plan"), chosen)
    chosen_summary = chosen["summary"]
    current_summary = current["summary"]
    trade_offs: List[str] = []
    if chosen["scenario_id"] != current["scenario_id"]:
        duty_delta = chosen_summary["duties"] - current_summary["duties"]
        crew_delta = chosen_summary["crew"] - current_summary["crew"]
        if duty_delta > 0 or crew_delta > 0:
            trade_offs.append(f"Exige {max(duty_delta, 0)} duty(s) extra e {max(crew_delta, 0)} crew adicional(is).")
        cost_delta = round(chosen_summary["total_cost"] - current_summary["total_cost"], 2)
        if not math.isclose(cost_delta, 0.0, abs_tol=0.01):
            direction = "reduz" if cost_delta < 0 else "aumenta"
            trade_offs.append(f"{direction.capitalize()} o custo total em {abs(cost_delta):.2f}.")
        if comparison and comparison.get("regressions"):
            trade_offs.append(
                "Ainda piora os seguintes KPIs frente ao current_plan: "
                + ", ".join(str(item) for item in comparison.get("regressions") or [])
                + "."
            )
    if chosen_summary["critical_count"] < current_summary["critical_count"]:
        trade_offs.append("Reduz o numero de excecoes criticas no plano final.")
    if chosen_summary["duties_below_25_pct"] < current_summary["duties_below_25_pct"]:
        trade_offs.append("Encurta a cauda de duties abaixo de 25% de utilizacao.")
    if chosen_summary["mandatory_rest_missing"] < current_summary["mandatory_rest_missing"]:
        trade_offs.append("Reduz duties com mandatory_rest_missing.")
    if chosen_summary["avg_idle_minutes"] < current_summary["avg_idle_minutes"]:
        trade_offs.append("Reduz idle medio publicado.")
    if not trade_offs:
        trade_offs.append("Mantem o plano atual por nao haver alternativa melhor dentro dos criterios objetivos.")
    return trade_offs
