"""Normalização de parâmetros — extraído de optimizer_service.py (Sprint I-2).

Funções puras para:
- Converter dataclass/Pydantic/dict em dict simples (`as_dict`)
- Aplicar regras em linguagem natural via regex parser (`parse_rule`)
- Normalizar pesos de fairness/goals (`normalize_rules`)
- Sincronizar parâmetros entre CCT e VSP (`align_vsp_params_with_cct`)
- Detectar modo strict de trip groups e validar compatibilidade do algoritmo

Estado: módulo sem classe, todas as funções são puras (ou mutam apenas dicts
recebidos como argumento, sem dependência de estado de service).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from ..core.exceptions import OptimizerError
from ..domain.models import AlgorithmType, Trip
from .ai_service import AiService


def as_dict(params: Any) -> Dict[str, Any]:
    """Converte params (dict | Pydantic model | dataclass | None) em dict simples."""
    if params is None:
        return {}
    if isinstance(params, dict):
        return dict(params)
    if hasattr(params, "model_dump"):
        return params.model_dump(exclude_none=True)
    return {key: value for key, value in vars(params).items() if not key.startswith("_") and value is not None}


def parse_rule(rule: str) -> Dict[str, Any]:
    """Extrai parâmetros estruturados de regra em linguagem natural via regex.

    Suporta padrões como "pausa de 30 min", "máximo de 9 horas por semana",
    "reduzir horas extras", "descanso interjornada de 11h", etc.
    Retorna dict de parâmetros conhecidos pelo solver.
    """
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
        parsed.setdefault("enforce_same_depot_start_end", True)

    return parsed


def normalize_rules(params: Any) -> Dict[str, Any]:
    """Normaliza dict de parâmetros: converte fairness_weight, parseia natural-language rules.

    Se houver `natural_language_rules`, tenta parsing por regex; fallback para AI.
    """
    normalized = as_dict(params)
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
    if rules:
        regex_parsed: Dict[str, Any] = {}
        for rule in rules:
            regex_parsed.update(parse_rule(rule))

        if regex_parsed:
            for key, value in regex_parsed.items():
                normalized.setdefault(key, value)
        else:
            ai_parsed = AiService().translate_rules_sync(rules)
            if ai_parsed:
                for key, value in ai_parsed.items():
                    normalized.setdefault(key, value)

    return normalized


def align_vsp_params_with_cct(
    cct_params: Dict[str, Any],
    vsp_params: Dict[str, Any],
) -> None:
    """Sincroniza parâmetros entre CCT (regras trabalhistas) e VSP (vehicle scheduling).

    Mutates `cct_params` and `vsp_params` in-place. Resolve conflitos onde campos
    são compartilhados (min_layover_minutes, etc) e propaga defaults sensatos.
    """
    passthrough_fields = (
        "min_layover_minutes",
        "pullout_minutes",
        "pullback_minutes",
        "connection_tolerance_minutes",
        "strict_hard_validation",
        "strict_zero_gap_validation",
        "strict_operational_mode",
        "strict_hard_constraints",
    )
    for field in passthrough_fields:
        if field not in vsp_params and cct_params.get(field) is not None:
            vsp_params[field] = cct_params[field]

    if cct_params.get("min_connection_time") is not None and cct_params.get("min_layover_minutes") is None:
        cct_params["min_layover_minutes"] = int(cct_params["min_connection_time"])
    if vsp_params.get("min_connection_time") is not None and vsp_params.get("min_layover_minutes") is None:
        vsp_params["min_layover_minutes"] = int(vsp_params["min_connection_time"])
    if cct_params.get("min_connection_time") is not None and vsp_params.get("min_layover_minutes") is None:
        vsp_params["min_layover_minutes"] = int(cct_params["min_connection_time"])

    if "same_depot_required" not in vsp_params and cct_params.get("enforce_same_depot_start_end") is not None:
        vsp_params["same_depot_required"] = bool(cct_params.get("enforce_same_depot_start_end"))

    # min_break_minutes (descanso entre viagens do motorista) deve ser piso de
    # min_layover_minutes (gap entre viagens no mesmo bloco do VSP). Sem isso o
    # VSP greedy usa default 8 min e ignora o intervalo configurado.
    min_break = cct_params.get("min_break_minutes")
    if min_break is not None:
        enforce_min_interval = bool(
            cct_params.get(
                "enforce_min_interval",
                vsp_params.get("enforce_min_interval", True),
            )
        )
        cct_params.setdefault("enforce_min_interval", enforce_min_interval)
        vsp_params.setdefault("enforce_min_interval", enforce_min_interval)
        current_layover = int(vsp_params.get("min_layover_minutes") or 0)
        if enforce_min_interval:
            vsp_params["min_layover_minutes"] = max(current_layover, int(min_break))

    if "pricing_enabled" not in vsp_params and "enable_column_generation" in vsp_params:
        vsp_params["pricing_enabled"] = bool(vsp_params.get("enable_column_generation"))
    if "pricing_enabled" not in vsp_params and "enable_column_generation" in cct_params:
        vsp_params["pricing_enabled"] = bool(cct_params.get("enable_column_generation"))

    # Normalização de aliases para parâmetros CCT/operacionais.
    # Permite que o frontend envie nomes alternativos sem quebrar o solver.
    # max_continuous_driving_minutes / condução_máxima → max_driving_minutes
    for src_params in (cct_params, vsp_params):
        for alias, canonical in (
            ("max_continuous_driving_minutes", "max_driving_minutes"),
            ("conducao_maxima_minutos", "max_driving_minutes"),
            ("max_work_time_minutes", "max_work_minutes"),
            ("max_shift_spread_minutes", "max_shift_minutes"),
            ("break_after_minutes", "mandatory_break_after_minutes"),
            ("pausa_obrigatoria_apos_minutos", "mandatory_break_after_minutes"),
            ("descanso_interjornada_minutos", "inter_shift_rest_minutes"),
            ("descanso_semanal_minutos", "weekly_rest_minutes"),
        ):
            if alias in src_params and canonical not in src_params:
                src_params[canonical] = src_params[alias]


def is_strict_trip_group_mode(
    trips: List[Trip],
    cct_params: Dict[str, Any],
    vsp_params: Dict[str, Any],
) -> bool:
    """Modo strict de trip groups exige preservação de pares (ida+volta) ou similares.

    Ativo quando `strict_hard_constraints=True` E pelo menos uma trip tem `trip_group_id`.
    """
    strict_groups = bool(
        vsp_params.get(
            "strict_hard_constraints",
            cct_params.get("strict_hard_constraints", False),
        )
    )
    if not strict_groups:
        return False
    return any(getattr(trip, "trip_group_id", None) is not None for trip in trips)


def validate_strict_algorithm_support(
    algorithm: AlgorithmType,
    trips: List[Trip],
    cct_params: Dict[str, Any],
    vsp_params: Dict[str, Any],
) -> None:
    """Lança OptimizerError se algoritmo não garante preservação de trip groups em modo strict."""
    if not is_strict_trip_group_mode(trips, cct_params, vsp_params):
        return
    algorithm_value = algorithm.value if hasattr(algorithm, "value") else str(algorithm)

    unsupported = {AlgorithmType.ASSIGNMENT_VSP.value}
    if algorithm_value in unsupported:
        raise OptimizerError(
            (
                f"Algorithm '{algorithm_value}' is not allowed with strict_hard_constraints=true "
                "when trip_group_id is present because it does not guarantee mandatory group preservation."
            ),
            code="ALGORITHM_UNSUPPORTED_STRICT_GROUPS",
            details={
                "algorithm": algorithm_value,
                "strict_hard_constraints": True,
                "grouped_trips": sum(1 for trip in trips if getattr(trip, "trip_group_id", None) is not None),
                "recommendation": "Use an algorithm with group repair/audit, or disable strict_hard_constraints for exploratory runs.",  # noqa: E501
            },
        )
