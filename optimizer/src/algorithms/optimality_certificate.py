"""
Optimality Certificate — consolida múltiplos lower bounds em um único
certificado de otimalidade para a solução VSP.

Fontes de lower bound (cada uma é matematicamente válida):
    1. Bodin & Golden (1981): LB = max(viagens simultâneas).
       Sempre calculável a partir da timetable. Bound mais frouxo
       quando há restrições operacionais (deadhead, depot, max_shift).
    2. Lagrangian dual (LagrangeanJointSolver): best_lower_bound do
       subgradient method. Bound forte para joint VSP+CSP.
    3. Bundle method (BundleMethodSolver): center_value do método
       de planos cortantes. Bound forte para instâncias grandes.

Estratégia: best-of — usa max(LBs disponíveis), pois cada LB é
uma cota inferior válida e o maior é o mais informativo.

Referências:
    Bodin L., Golden B. (1981) "Classification in vehicle routing
        and scheduling", Networks 11(2):97-108.
    Lemarechal C. (1975) "An extension of Davidon methods to non-
        differentiable problems", Math. Programming Studies.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from ..domain.models import OptimizationResult, Trip

logger = logging.getLogger(__name__)


def _bodin_golden_lb(trips: List[Trip]) -> int:
    """LB = pico de viagens simultâneas no tempo (Bodin & Golden 1981)."""
    if not trips:
        return 0
    events: List[Tuple[int, int]] = []
    for t in trips:
        events.append((int(t.start_time), 1))
        events.append((int(t.end_time), -1))
    events.sort(key=lambda e: (e[0], e[1]))
    concurrent = peak = 0
    for _, delta in events:
        concurrent += delta
        if concurrent > peak:
            peak = concurrent
    return peak


def _collect_lbs_from_meta(meta: Dict[str, Any]) -> Dict[str, float]:
    """Lê LBs que solvers especializados deixaram em vsp.meta."""
    sources: Dict[str, float] = {}
    for key, source_name in (
        ("lagrangean_lower_bound", "lagrangean"),
        ("bundle_lower_bound", "bundle"),
    ):
        value = meta.get(key)
        if value is not None and value > 0:
            sources[source_name] = float(value)
    return sources


def certify_optimality(result: OptimizationResult) -> Dict[str, Any]:
    """
    Computa certificado de otimalidade combinando múltiplos lower bounds.

    Returns dict com:
        lb_value: int | None — melhor LB disponível (max das fontes), or None se LB ausente
        lb_method: str — qual fonte deu o melhor LB
        lb_sources: dict — todos os LBs disponíveis {source: value}
        ub_value: int — veículos usados na solução (UB)
        gap_pct: float | None — (UB - LB) / LB × 100, or None se LB ausente/inválido
        is_optimal_certified: bool — True se gap == 0.0, False se LB ausente
        gap_explained: str — explicação textual

    Compatibilidade: mantém as chaves legadas vsp_lower_bound,
    vsp_actual, vsp_gap_pct para não quebrar consumers existentes.

    IMPORTANTE: quando o lower bound é 0 ou ausente, retorna:
      - vsp_lower_bound: None
      - vsp_gap_pct: None
      - is_optimal_certified: False
      - gap_explained: "No lower bound available — optimality unknown"

    Isto evita confundir "nenhum dado" (LB=0) com "ótimo provado" (gap=0%).
    """
    try:
        all_trips = [t for b in result.vsp.blocks for t in b.trips]
        if result.vsp.unassigned_trips:
            all_trips.extend(result.vsp.unassigned_trips)
        if not all_trips:
            return _empty_certificate()

        ub_value = len(result.vsp.blocks)

        # Fonte 1: Bodin & Golden — sempre disponível
        bodin_lb = _bodin_golden_lb(all_trips)
        lb_sources: Dict[str, float] = {"bodin_golden": float(bodin_lb)}

        # Fontes 2-3: Lagrangian / Bundle — opcionais (se solver rodou)
        meta_lbs = _collect_lbs_from_meta(result.vsp.meta or {})
        lb_sources.update(meta_lbs)

        # Best-of: maior LB válido
        lb_method, lb_value = max(lb_sources.items(), key=lambda kv: kv[1])
        lb_value_int = int(round(lb_value))

        # CHANGED: If lower bound is invalid (0 or negative), return unavailable
        if lb_value_int <= 0:
            return {
                # Chaves legadas
                "vsp_lower_bound": None,
                "vsp_actual": ub_value,
                "vsp_gap_pct": None,
                "vsp_gap_explained": "No lower bound available — optimality unknown",
                # Chaves novas
                "lb_method": "none",
                "lb_sources": {},
                "is_optimal_certified": False,
            }

        gap_pct = ((ub_value - lb_value_int) / lb_value_int * 100.0)
        is_optimal = gap_pct == 0.0

        return {
            # Chaves legadas (compatibilidade com _optimality_metrics original)
            "vsp_lower_bound": lb_value_int,
            "vsp_actual": ub_value,
            "vsp_gap_pct": round(gap_pct, 2),
            "vsp_gap_explained": (
                f"Gap = (veículos usados - LB) / LB × 100. LB={lb_value_int} "
                f"obtido por {lb_method}. Gap=0 indica ótimo certificado; "
                f"gap > 0 pode ser otimização subótima OU restrições "
                f"operacionais (max_shift, depot, deadhead)."
            ),
            # Chaves novas (certificado expandido)
            "lb_method": lb_method,
            "lb_sources": {k: round(v, 2) for k, v in lb_sources.items()},
            "is_optimal_certified": is_optimal,
        }
    except Exception as exc:  # pragma: no cover - defensa contra erro inesperado
        logger.warning("[OPTIMALITY_CERT] cálculo falhou: %s", exc)
        return _empty_certificate()


def _empty_certificate() -> Dict[str, Any]:
    return {
        "vsp_lower_bound": 0,
        "vsp_actual": 0,
        "vsp_gap_pct": 0.0,
        "vsp_gap_explained": "Sem viagens — gap indefinido.",
        "lb_method": "none",
        "lb_sources": {},
        "is_optimal_certified": False,
    }
