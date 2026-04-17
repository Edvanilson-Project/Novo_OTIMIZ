"""
POST /api/v1/evaluate-delta — Recálculo what-if após rearranjo de trips no Gantt.
"""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...domain.models import Block, CSPSolution, OptimizationResult, Trip, VehicleType, VSPSolution
from ...algorithms.evaluator import CostEvaluator
from ..schemas import OptimizationParametersDTO
from ...algorithms.utils import sort_block_trips
from ...algorithms.csp.greedy import GreedyCSP


class BaselineRequest(BaseModel):
    """Payload do endpoint /evaluate-baseline: avalia custo do arranjo atual sem mover nada."""
    blocks: List[Dict[str, Any]] = Field(..., description="Estado atual dos blocos (como vieram do resultado)")
    vehicle_types: Optional[List[Dict[str, Any]]] = Field(default=None, description="Tipos de veículos")
    optimization_params: Optional[OptimizationParametersDTO] = None


def _recompute_idle_minutes(blocks: List[Block]) -> None:
    """Recalcula idle_before/after de cada trip a partir dos gaps reais.

    Sem isso, idle_* vem congelado do resultado original da otimização e
    mover trips entre blocos não altera o custo. Convenção: o gap inteiro
    entra em idle_before da trip seguinte; primeira trip tem idle_before=0;
    idle_after=0 em todas (evita double-count em vsp_cost_breakdown).
    """
    for block in blocks:
        trips = block.trips
        for idx, trip in enumerate(trips):
            trip.idle_after_minutes = 0
            if idx == 0:
                trip.idle_before_minutes = 0
                continue
            prev = trips[idx - 1]
            gap = int((trip.start_time or 0) - (prev.end_time or 0))
            trip.idle_before_minutes = max(0, gap)


def _evaluate_arrangement(
    blocks_data: List[Dict[str, Any]],
    vehicle_types: List[VehicleType],
    extra_meta: Optional[Dict[str, Any]] = None,
    algorithm_label: str = "arrangement",
) -> "WhatIfResponse":
    """Avalia o custo de um arranjo de blocos (VSP + GreedyCSP + breakdown).

    Usado tanto pelo what-if (após aplicar o move) quanto pelo baseline
    (sem move). Garante que todo cálculo de custo exibido na UI seja
    comparável — sempre o mesmo pipeline de avaliação.
    """
    block_objects = [_block_from_dict(b) for b in blocks_data]
    sort_block_trips(block_objects)
    _recompute_idle_minutes(block_objects)

    meta: Dict[str, Any] = {
        "num_blocks": len(block_objects),
        "num_trips": sum(len(b.trips) for b in block_objects),
        "vehicle_types_provided": len(vehicle_types),
        "cost_defaults": {
            "idle_cost_per_minute": evaluator.idle_cost_per_minute,
            "crew_cost_per_hour": evaluator.crew_cost_per_hour,
        },
    }
    if extra_meta:
        meta.update(extra_meta)

    mock_vsp = VSPSolution(
        blocks=block_objects,
        unassigned_trips=[],
        algorithm=algorithm_label,
        meta=meta,
    )

    all_trips = [t for b in block_objects for t in b.trips]
    fast_csp: Optional[CSPSolution] = None
    if all_trips and vehicle_types:
        try:
            vsp_params = {
                "min_work_minutes": 0,
                "max_work_minutes": 600,
                "max_shift_minutes": 720,
                "min_layover_minutes": 8,
                "allow_relief_points": True,
                "operator_change_terminals_only": True,
            }
            greedy_csp = GreedyCSP(vsp_params=vsp_params)
            fast_csp = greedy_csp.solve(block_objects, all_trips)
            logger.debug("GreedyCSP: %d duties (%s)", len(fast_csp.duties), algorithm_label)
        except Exception as csp_error:
            logger.warning("GreedyCSP falhou em %s, usando fallback: %s", algorithm_label, csp_error)

    if fast_csp is None:
        fast_csp = CSPSolution(duties=[], algorithm=f"{algorithm_label}_fallback")

    result = OptimizationResult(vsp=mock_vsp, csp=fast_csp)
    cost_breakdown = evaluator.total_cost_breakdown(result, vehicle_types)
    block_responses = [_block_to_response(b, vehicle_types) for b in block_objects]

    return WhatIfResponse(
        status="ok",
        blocks=block_responses,
        cost_breakdown=cost_breakdown,
    )


router = APIRouter()
logger = logging.getLogger(__name__)
evaluator = CostEvaluator()


class WhatIfRequest(BaseModel):
    blocks: List[Dict[str, Any]] = Field(..., description="Estado atual dos blocos")
    trip_id: Optional[int] = Field(default=None, description="ID da viagem sendo movida (único)")
    trip_ids: Optional[List[int]] = Field(default=None, description="IDs das viagens sendo movidas (array)")
    source_block_id: int = Field(..., description="ID do bloco de origem")
    target_block_id: int = Field(..., description="ID do bloco de destino")
    target_index: int = Field(..., description="Posição no bloco destino")
    vehicle_types: Optional[List[Dict[str, Any]]] = Field(default=None, description="Tipos de veículos")
    optimization_params: Optional[OptimizationParametersDTO] = None


class BlockResponse(BaseModel):
    block_id: int
    trips: List[Any]
    num_trips: int
    start_time: int
    end_time: int
    total_cost: float


class WhatIfResponse(BaseModel):
    status: str = "ok"
    blocks: List[BlockResponse]
    cost_breakdown: Dict[str, Any]


def _dict_to_trip(data: Dict[str, Any]) -> Trip:
    return Trip(
        id=int(data.get("id") or 0),
        line_id=int(data.get("line_id") or 0),
        start_time=int(data.get("start_time") or 0),
        end_time=int(data.get("end_time") or 0),
        origin_id=int(data.get("origin_id") or 0),
        destination_id=int(data.get("destination_id") or 0),
        trip_group_id=data.get("trip_group_id"),
        direction=data.get("direction"),
        duration=int(data.get("duration") or 0),
        distance_km=float(data.get("distance_km") or 0.0),
        depot_id=data.get("depot_id"),
        relief_point_id=data.get("relief_point_id"),
        is_relief_point=bool(data.get("is_relief_point", False)),
        deadhead_times={
            int(k): int(v)
            for k, v in (data.get("deadhead_times") or {}).items()
        },
        idle_before_minutes=int(data.get("idle_before_minutes") or 0),
        idle_after_minutes=int(data.get("idle_after_minutes") or 0),
    )


def _dict_to_vehicle_type(data: Dict[str, Any]) -> VehicleType:
    return VehicleType(
        id=data.get("id", 0),
        name=data.get("name", "Unknown"),
        passenger_capacity=data.get("passenger_capacity", 40),
        cost_per_km=data.get("cost_per_km", 0.0),
        cost_per_hour=data.get("cost_per_hour", 0.0),
        fixed_cost=data.get("fixed_cost", 800.0),
        is_electric=data.get("is_electric", False),
        battery_capacity_kwh=data.get("battery_capacity_kwh", 0.0),
        minimum_soc=data.get("minimum_soc", 0.15),
        charge_rate_kw=data.get("charge_rate_kw", 0.0),
        energy_cost_per_kwh=data.get("energy_cost_per_kwh", 0.0),
        depot_id=data.get("depot_id"),
    )


def _block_from_dict(data: Dict[str, Any]) -> Block:
    trips = [_dict_to_trip(t) for t in data.get("trips", [])]
    block = Block(id=data.get("id", 0), trips=trips)
    if data.get("vehicle_type_id"):
        block.vehicle_type_id = data.get("vehicle_type_id")
    return block


def _block_to_response(block: Block, vehicle_types: List[VehicleType]) -> BlockResponse:
    trip_data = []
    for t in block.trips:
        trip_data.append({
            "id": t.id,
            "line_id": t.line_id,
            "start_time": t.start_time,
            "end_time": t.end_time,
            "origin_id": t.origin_id,
            "destination_id": t.destination_id,
            "trip_group_id": t.trip_group_id,
            "direction": t.direction,
            "duration": t.duration or 0,
            "distance_km": t.distance_km or 0.0,
        })
    start_time = int(block.trips[0].start_time or 0) if block.trips else 0
    end_time = int(block.trips[-1].end_time or 0) if block.trips else 0
    try:
        total_cost = evaluator.block_cost(block, vehicle_types)
    except Exception as exc:
        logger.warning("Falha ao calcular custo do bloco %s: %s", block.id, exc)
        total_cost = 0.0
    return BlockResponse(
        block_id=block.id,
        trips=trip_data,
        num_trips=len(trip_data),
        start_time=start_time,
        end_time=end_time,
        total_cost=total_cost,
    )


@router.post(
    "/evaluate-delta",
    response_model=WhatIfResponse,
    tags=["what-if"],
)
async def evaluate_delta(request: WhatIfRequest) -> WhatIfResponse:
    logger.info(
        "evaluate-delta recebido: source=%s target=%s trip_ids=%s blocks=%d",
        request.source_block_id,
        request.target_block_id,
        request.trip_ids,
        len(request.blocks),
    )
    
    # Sincronização de custos dinâmicos
    if request.optimization_params:
        logger.debug(
            "evaluate-delta: Usando pesos customizados: veiculo=%.2f, km=%.2f, jornada=%.2f",
            request.optimization_params.cost_vehicle,
            request.optimization_params.cost_km,
            request.optimization_params.cost_duty,
        )
        evaluator.set_costs(
            cost_vehicle=request.optimization_params.cost_vehicle,
            cost_km=request.optimization_params.cost_km,
            cost_duty=request.optimization_params.cost_duty,
        )

    try:
        blocks = deepcopy(request.blocks)
        vehicle_types = (
            [_dict_to_vehicle_type(v) for v in request.vehicle_types]
            if request.vehicle_types
            else []
        )

        trip_ids = list(request.trip_ids) if request.trip_ids else ([request.trip_id] if request.trip_id else [])
        source_block_id = request.source_block_id
        target_block_id = request.target_block_id
        target_index = request.target_index

        source_block_data = None
        target_block_data = None

        for b in blocks:
            if b.get("id") == source_block_id:
                source_block_data = b
            if b.get("id") == target_block_id:
                target_block_data = b

        # ── Localização das trips: em qual bloco elas estão AGORA? ──────────────
        # Detecta stale state do frontend: se o usuário re-arrastar uma trip que
        # já foi movida, o sourceBlockId enviado pode estar desatualizado.
        # Procuramos as trips em TODOS os blocos para saber se o move já aconteceu.
        initial_ids_set = set(trip_ids)
        trips_actual_location: Dict[int, int] = {}
        for b in blocks:
            b_id = b.get("id")
            for t in b.get("trips", []):
                t_id = t.get("id")
                if t_id in initial_ids_set:
                    trips_actual_location[t_id] = b_id

        trips_in_source = source_block_data is not None and any(
            tid in trips_actual_location and trips_actual_location[tid] == source_block_id
            for tid in initial_ids_set
        )
        trips_in_target = target_block_data is not None and any(
            tid in trips_actual_location and trips_actual_location[tid] == target_block_id
            for tid in initial_ids_set
        )

        if source_block_data is None:
            # Source block ausente do payload. Se as trips estão no target, é
            # provavelmente stale state do frontend (trip já foi movida antes).
            # Avaliamos o estado atual graceful ao invés de quebrar com 404.
            if trips_in_target:
                logger.info(
                    "Source block %s ausente mas trips %s já em target %s → avaliando estado atual (stale-state gracioso).",
                    source_block_id, trip_ids, target_block_id,
                )
                source_block_data = {"id": source_block_id, "trips": [], "vehicle_type_id": None}
            else:
                raise HTTPException(status_code=404, detail=f"Source block {source_block_id} not found")

        source_has_trips = trips_in_source

        if not source_has_trips:
            logger.info(
                "Frontend pré-aplicou o move (trips %s ausentes no source_block=%s). "
                "Avaliando blocks recebidos diretamente.",
                trip_ids, source_block_id,
            )
        else:
            # ─── REGRA "IDA E VOLTA JUNTO" ────────────────────────────────────────
            # Estratégia 1 (prioritária): trip_group_id compartilhado.
            # Estratégia 2 (fallback): ciclo sequencial — mesma linha, Ida outbound
            # seguida de Volta inbound, Destino(Ida)==Origem(Volta), gap < 45 min.
            trip_ids_set = set(trip_ids)

            # — ALGORITMO SIMPLES: Ida+Volta junto ————————————————
            # Passo 1: detecta trip_group_id primeiro
            group_ids_to_expand: set = set()
            for t in source_block_data.get("trips", []):
                if t.get("id") in trip_ids_set and t.get("trip_group_id"):
                    group_ids_to_expand.add(t["trip_group_id"])
            
            if group_ids_to_expand:
                for t in source_block_data.get("trips", []):
                    if t.get("trip_group_id") in group_ids_to_expand and t.get("id") not in trip_ids_set:
                        trip_ids.append(t["id"])
                        trip_ids_set.add(t["id"])
                logger.info("Por trip_group_id: moves %s trips", len(trip_ids_set))
            else:
                # ULTIMO FALLBACK: pega a PRÓXIMA trip no tempo (máximo gap de 120 min)
                src_sorted = sorted(
                    source_block_data.get("trips", []),
                    key=lambda t: int(t.get("start_time") or 0),
                )
                trip_to_time = {int(t.get("id")): int(t.get("start_time") or 0) for t in src_sorted}
                target_start = trip_to_time.get(trip_ids[0], -1)
                
                if target_start >= 0:
                    # Escolhe a trip com menor gap de tempo
                    best_tid = None
                    best_gap = 120
                    for tid, st in trip_to_time.items():
                        if tid == trip_ids[0]:
                            continue
                        gap = st - target_start
                        if 0 < gap < best_gap:
                            best_gap = gap
                            best_tid = tid
                    
                    if best_tid:
                        trip_ids.append(best_tid)
                        trip_ids_set.add(best_tid)
                        logger.info("Vizinho temporal: trip %s (gap=%d min)", best_tid, best_gap)

            if len(trip_ids_set) <= 1:
                # SEGURANÇA: se ainda não achou par, pega qualquer trip vizinha no array
                src_sorted = sorted(source_block_data.get("trips", []), key=lambda t: int(t.get("start_time") or 0))
                trip_idx = {int(t.get("id")): idx for idx, t in enumerate(src_sorted)}
                idx = trip_idx.get(trip_ids[0])
                if idx is not None:
                    if idx + 1 < len(src_sorted):
                        trip_ids.append(src_sorted[idx + 1]["id"])
                    elif idx > 0:
                        trip_ids.append(src_sorted[idx - 1]["id"])
                logger.info("Fallback array: moves %s trips", len(trip_ids_set))

            # ──────────────────────────────────────────────────────────────────

            # Coleta trips a mover (ordem cronológica do source)
            trip_data_list = [
                t for t in source_block_data.get("trips", [])
                if t.get("id") in trip_ids_set
            ]
            if not trip_data_list:
                raise HTTPException(
                    status_code=404,
                    detail=f"Trips {trip_ids} not found in source block {source_block_id}",
                )

            # Remove trips do bloco de origem
            source_block_data["trips"] = [
                t for t in source_block_data.get("trips", [])
                if t.get("id") not in trip_ids_set
            ]

            # Insere trips no bloco de destino (cria se necessário)
            if target_block_data is None:
                target_block_data = {"id": target_block_id, "trips": [], "vehicle_type_id": None}
                blocks.append(target_block_data)

            target_trips = target_block_data.get("trips", [])
            ins = max(0, min(target_index, len(target_trips)))
            for i, trip_data in enumerate(trip_data_list):
                target_trips.insert(ins + i, trip_data)
            target_block_data["trips"] = target_trips

            logger.info(
                "Move aplicado server-side: %d trips de bloco %s → %s (pos=%d)",
                len(trip_data_list), source_block_id, target_block_id, ins,
            )
        # ────────────────────────────────────────────────────────────────────────

        # Descarta blocos que ficaram vazios após o move
        blocks = [b for b in blocks if b.get("trips")]

        return _evaluate_arrangement(
            blocks_data=blocks,
            vehicle_types=vehicle_types,
            extra_meta={
                "what_if_source_block": source_block_id,
                "what_if_target_block": target_block_id,
                "what_if_trip_ids": trip_ids,
                "frontend_preapplied": not source_has_trips,
            },
            algorithm_label="what_if",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Erro interno em evaluate_delta: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Erro ao processar what-if: {exc}") from exc


@router.post(
    "/evaluate-baseline",
    response_model=WhatIfResponse,
    tags=["what-if"],
)
async def evaluate_baseline(request: BaselineRequest) -> WhatIfResponse:
    """Avalia o custo do arranjo atual (sem mover trips).

    Usado pelo frontend no mount do Gantt para estabelecer um `prevCost`
    comparável ao resultado do /evaluate-delta — ambos passam pelo mesmo
    pipeline (_evaluate_arrangement), então a comparação é apples-to-apples.
    """
    logger.info("evaluate-baseline recebido: blocks=%d", len(request.blocks))
    
    # Sincronização de custos dinâmicos
    if request.optimization_params:
        logger.debug(
            "evaluate-baseline: Usando pesos customizados: veiculo=%.2f, km=%.2f, jornada=%.2f",
            request.optimization_params.cost_vehicle,
            request.optimization_params.cost_km,
            request.optimization_params.cost_duty,
        )
        evaluator.set_costs(
            cost_vehicle=request.optimization_params.cost_vehicle,
            cost_km=request.optimization_params.cost_km,
            cost_duty=request.optimization_params.cost_duty,
        )

    try:
        vehicle_types = (
            [_dict_to_vehicle_type(v) for v in request.vehicle_types]
            if request.vehicle_types
            else []
        )
        blocks = [b for b in deepcopy(request.blocks) if b.get("trips")]
        return _evaluate_arrangement(
            blocks_data=blocks,
            vehicle_types=vehicle_types,
            algorithm_label="baseline",
        )
    except Exception as exc:
        logger.error("Erro em evaluate_baseline: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Erro ao processar baseline: {exc}") from exc
