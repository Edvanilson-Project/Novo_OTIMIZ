"""Trip group inference + materialization — extraído de optimizer_service.py (Sprint I-3).

Responsabilidades:
- Sumarizar grupos existentes (`summarize_trip_groups`)
- Inferir pares ida-volta a partir de heurística (línea + janela temporal + terminais)
- Materializar grupos mandatory (atribui trip_group_id sintético quando ausente)
- Injetar constraints de grupo nos params (cct + vsp) baseado em modo strict

Funções puras — operam sobre listas de trips e dicts de params.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..core.exceptions import OptimizerError
from ..domain.models import Trip
from .parameter_normalization import is_strict_trip_group_mode

logger = logging.getLogger(__name__)


def summarize_trip_groups(trips: List[Trip]) -> Dict[str, int]:
    """Conta grupos com 2+ trips e seus tamanhos."""
    grouped: Dict[int, set[int]] = {}
    for trip in trips:
        group_id = getattr(trip, "trip_group_id", None)
        if group_id is None:
            continue
        grouped.setdefault(int(group_id), set()).add(int(trip.id))

    group_sizes = [len(ids) for ids in grouped.values() if len(ids) >= 2]
    return {
        "group_count": len(group_sizes),
        "grouped_trip_count": sum(group_sizes),
        "max_group_size": max(group_sizes) if group_sizes else 0,
    }


def infer_round_trip_pairs(trips: List[Trip], vsp_params: Dict[str, Any]) -> List[List[int]]:
    """Heurística: encontra pares ida+volta na mesma linha, com gap ≤ janela e terminais espelhados.

    Para cada trip, busca a próxima trip da mesma linha onde:
      - destination_id da ida == origin_id da volta
      - origin_id da ida == destination_id da volta
      - gap (start_volta - end_ida) ∈ [0, preferred_pair_window_minutes]
      - direção (se disponível) oposta

    Retorna lista de pares `[id_ida, id_volta]`.
    """
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
            for nxt in ordered[index + 1:]:
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


def materialize_mandatory_trip_groups(
    trips: List[Trip],
    groups: List[List[int]],
    seed: int,
) -> None:
    """Atribui trip_group_id sintético a trips que ainda não têm grupo, dentro de `groups`.

    Mutates trips in-place. `seed` é base para IDs sintéticos (incrementa-decrementa por grupo).
    """
    trip_by_id = {int(trip.id): trip for trip in trips}
    for index, group in enumerate(groups):
        group_ids = [int(item) for item in group]
        existing_group_ids = {
            int(trip_by_id[trip_id].trip_group_id)
            for trip_id in group_ids
            if trip_id in trip_by_id and trip_by_id[trip_id].trip_group_id is not None
        }
        synthetic_group_id = int(seed) - index
        materialized_group_id = next(iter(existing_group_ids)) if len(existing_group_ids) == 1 else synthetic_group_id
        for trip_id in group_ids:
            trip = trip_by_id.get(trip_id)
            if trip is not None and trip.trip_group_id is None:
                trip.trip_group_id = materialized_group_id


def inject_trip_group_constraints(
    trips: List[Trip],
    cct_params: Dict[str, Any],
    vsp_params: Dict[str, Any],
) -> None:
    """Aplica constraints de grupo: materializa mandatory_trip_groups e/ou força hard pairing.

    Mutates trips e params in-place.
    Lógica:
      - Se cct_params já tem `mandatory_trip_groups_same_duty`: materializa diretamente
      - Senão: agrupa por (line_id, trip_group_id); se vazio mas `hard_pairing` ativo, infere pares
      - Se hard_pairing + grupos válidos: define penalty alta no VSP e marca mandatory
    """
    strict_group_mode = is_strict_trip_group_mode(trips, cct_params, vsp_params)
    hard_pairing = (
        strict_group_mode
        or bool(cct_params.get("enforce_trip_groups_hard", False))
        or bool(cct_params.get("operator_pairing_hard", False))
    )
    if cct_params.get("mandatory_trip_groups_same_duty"):
        materialize_mandatory_trip_groups(
            trips,
            cct_params.get("mandatory_trip_groups_same_duty") or [],
            seed=-9_000_000,
        )
        return
    if not hard_pairing and not bool(vsp_params.get("preserve_preferred_pairs", True)):
        return

    grouped: Dict[Any, List[int]] = {}
    for trip in trips:
        if trip.trip_group_id is None:
            continue
        group_key: Any
        if strict_group_mode:
            group_key = int(trip.trip_group_id)
        else:
            group_key = (int(trip.line_id), int(trip.trip_group_id))
        grouped.setdefault(group_key, []).append(int(trip.id))

    explicit_groups: List[List[int]] = [
        sorted(set(ids))
        for ids in grouped.values()
        if len(set(ids)) >= 2
    ]

    if not explicit_groups and hard_pairing:
        inferred = infer_round_trip_pairs(trips, vsp_params)
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
                explicit_groups.append(sorted([a_id, b_id]))
                synthetic_group -= 1

    if hard_pairing and explicit_groups:
        materialize_mandatory_trip_groups(trips, explicit_groups, seed=-1)
        cct_params["mandatory_trip_groups_same_duty"] = explicit_groups
        fixed_cost = float(vsp_params.get("fixed_vehicle_activation_cost", 800.0) or 800.0)
        vsp_params.setdefault("hard_pairing_vehicle_level", True)
        vsp_params.setdefault("hard_pairing_penalty", max(fixed_cost * 25.0, 20000.0))


def build_group_inference_report(
    trips: List[Trip],
    request_metadata: Any,
) -> Dict[str, Any]:
    """Audita coerência entre stats de grupo do backend e do optimizer."""
    metadata = dict(request_metadata or {})
    optimizer_input_stats = summarize_trip_groups(trips)
    mode = str(metadata.get("trip_group_inference_mode") or ("direct_input" if not metadata else "unspecified"))
    has_backend_stats = "backend_trip_group_stats" in metadata
    backend_stats_raw = metadata.get("backend_trip_group_stats") or {}
    backend_stats = {
        "group_count": int(backend_stats_raw.get("group_count", optimizer_input_stats["group_count"]) or 0),
        "grouped_trip_count": int(backend_stats_raw.get("grouped_trip_count", optimizer_input_stats["grouped_trip_count"]) or 0),
        "max_group_size": int(backend_stats_raw.get("max_group_size", optimizer_input_stats["max_group_size"]) or 0),
    }

    if has_backend_stats and backend_stats != optimizer_input_stats:
        raise OptimizerError(
            "Incoming trip_group_id payload diverged between backend and optimizer input.",
            code="TRIP_GROUP_PAYLOAD_DIVERGENCE",
            details={
                "trip_group_inference_mode": mode,
                "backend_trip_group_stats": backend_stats,
                "optimizer_input_stats": optimizer_input_stats,
            },
        )

    return {
        "mode": mode,
        "backend_trip_group_stats": backend_stats,
        "optimizer_input_stats": optimizer_input_stats,
    }


def log_group_inference_report(report: Dict[str, Any]) -> None:
    backend_stats = report.get("backend_trip_group_stats") or {}
    input_stats = report.get("optimizer_input_stats") or {}
    effective_stats = report.get("optimizer_effective_stats") or {}
    logger.info(
        "[GROUPS] mode=%s backend=%d/%d input=%d/%d effective=%d/%d inferred=%s",
        report.get("mode"),
        int(backend_stats.get("group_count", 0) or 0),
        int(backend_stats.get("grouped_trip_count", 0) or 0),
        int(input_stats.get("group_count", 0) or 0),
        int(input_stats.get("grouped_trip_count", 0) or 0),
        int(effective_stats.get("group_count", 0) or 0),
        int(effective_stats.get("grouped_trip_count", 0) or 0),
        bool(report.get("inference_applied", False)),
    )
