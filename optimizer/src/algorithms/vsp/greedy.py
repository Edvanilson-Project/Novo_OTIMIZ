"""
VSP Guloso com objetivo de custo mínimo aproximado.

Função objetivo aproximada:
    Z = Σ_k f_k + Σ_(i,j) c_ij x_ij

Cada bloco representa a ativação de um veículo, e cada conexão carrega custo
 de deadhead, ociosidade e energia quando houver frota elétrica.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ...core.config import get_settings

_log = logging.getLogger(__name__)
from ...domain.interfaces import IVSPAlgorithm
from ...domain.models import Block, Trip, VehicleType, VSPSolution
from ..base import BaseAlgorithm

settings = get_settings()


def _sort_trips(trips: List[Trip]) -> List[Trip]:
    """Sort trips by start_time, keeping contiguous trip_group pairs together.

    For trip_groups with gap=0 (volta starts when ida ends), the volta is placed
    immediately after its ida so the greedy loop assigns them to the same block.
    """
    base = sorted(trips, key=lambda t: (t.start_time, t.end_time, t.id))

    # Build trip_group map: group_id -> list of trips
    group_map: Dict[int, List[Trip]] = {}
    for t in base:
        if t.trip_group_id is not None:
            group_map.setdefault(t.trip_group_id, []).append(t)

    # Identify contiguous pairs (ida.end_time == volta.start_time)
    volta_ids: set = set()
    ida_to_volta: Dict[int, Trip] = {}
    for gid, members in group_map.items():
        if len(members) == 2:
            a, b = sorted(members, key=lambda t: t.start_time)
            if a.end_time == b.start_time:
                volta_ids.add(b.id)
                ida_to_volta[a.id] = b

    # Rebuild list: skip volta trips, insert them right after their ida
    result: List[Trip] = []
    for t in base:
        if t.id in volta_ids:
            continue  # will be inserted after its ida
        result.append(t)
        if t.id in ida_to_volta:
            result.append(ida_to_volta[t.id])

    return result


def build_preferred_pairs(trips: List[Trip], min_layover: int, max_pair_window: int) -> Dict[int, int]:
    """Gera emparelhamentos ida-volta preferenciais por menor folga."""
    ordered = _sort_trips(trips)
    paired: set[int] = set()
    pair_map: Dict[int, int] = {}

    grouped: Dict[tuple[int, int], List[Trip]] = {}
    for trip in ordered:
        if trip.trip_group_id is None:
            continue
        grouped.setdefault((trip.line_id, trip.trip_group_id), []).append(trip)

    for (_, _), members in grouped.items():
        members = sorted(members, key=lambda item: (item.start_time, item.id))
        if len(members) != 2:
            continue
        first, second = members
        if first.id in paired or second.id in paired:
            continue
        if first.destination_id != second.origin_id or first.origin_id != second.destination_id:
            continue
        gap = second.start_time - first.end_time
        min_pair_gap = 0 if gap == 0 and first.trip_group_id == second.trip_group_id else min_layover
        if second.start_time - first.end_time < min_pair_gap:
            continue
        pair_map[first.id] = second.id
        pair_map[second.id] = first.id
        paired.add(first.id)
        paired.add(second.id)

    for index, trip in enumerate(ordered):
        if trip.id in paired:
            continue
        best: Optional[Trip] = None
        best_slack: Optional[int] = None
        for nxt in ordered[index + 1 :]:
            if nxt.id in paired:
                continue
            gap = nxt.start_time - trip.end_time
            if gap > max_pair_window:
                break
            min_pair_gap = min_layover
            if gap < min_pair_gap:
                continue
            if trip.line_id != nxt.line_id:
                continue
            if trip.destination_id != nxt.origin_id:
                continue
            if trip.origin_id != nxt.destination_id:
                continue
            slack = gap - min_layover
            if best is None or slack < (best_slack if best_slack is not None else slack):
                best = nxt
                best_slack = slack
        if best is None:
            continue
        pair_map[trip.id] = best.id
        pair_map[best.id] = trip.id
        paired.add(trip.id)
        paired.add(best.id)
    return pair_map


def pairing_stats(blocks: List[Block], preferred_pairs: Dict[int, int]) -> Dict[str, int]:
    unique_pairs = {
        tuple(sorted((trip_id, pair_id)))
        for trip_id, pair_id in preferred_pairs.items()
        if trip_id < pair_id
    }
    consecutive_pairs = {
        tuple(sorted((block.trips[index].id, block.trips[index + 1].id)))
        for block in blocks
        for index in range(len(block.trips) - 1)
        if preferred_pairs.get(block.trips[index].id) == block.trips[index + 1].id
    }
    matched = len(unique_pairs & consecutive_pairs)
    return {
        "preferred_pair_count": len(unique_pairs),
        "paired_connections_followed": matched,
        "preferred_pair_breaks": max(0, len(unique_pairs) - matched),
    }


class GreedyVSP(BaseAlgorithm, IVSPAlgorithm):
    def __init__(self, vsp_params: Optional[Dict[str, Any]] = None):
        super().__init__(name="greedy_vsp", time_budget_s=30.0)
        self.vsp_params = vsp_params or {}

    def _p(self, key: str, default: Any) -> Any:
        return self.vsp_params.get(key, default)

    def _deadhead(self, a: Trip, b: Trip, min_layover: int) -> int:
        """Retorna o tempo mínimo necessário entre trip a e trip b.
        Usa deadhead_times codificado no payload (inclui layover mínimo por terminal).
        """
        dh = int(a.deadhead_times.get(b.origin_id, 0))
        return max(min_layover, dh)

    def _energy_need(self, trip: Trip, vehicle: Optional[VehicleType]) -> float:
        if trip.energy_kwh > 0:
            base = trip.energy_kwh
        else:
            base_rate = 1.25 if vehicle and vehicle.is_electric else 0.0
            base = trip.distance_km * base_rate
        topo_factor = 1.0 + max(0.0, trip.elevation_gain_m) * 0.0008
        return base * topo_factor

    def _maybe_recharge(
        self,
        block: Block,
        gap: int,
        vehicle: Optional[VehicleType],
        trip: Trip,
    ) -> Tuple[float, float]:
        if not vehicle or not vehicle.is_electric or vehicle.battery_capacity_kwh <= 0 or vehicle.charge_rate_kw <= 0:
            current = float(block.meta.get("soc_kwh", vehicle.battery_capacity_kwh if vehicle else 0.0))
            return 0.0, current

        can_charge = (
            gap > 0
            and trip.depot_id is not None
            and block.meta.get("start_depot_id") is not None
            and trip.depot_id == block.meta.get("start_depot_id")
        )
        if not can_charge:
            return 0.0, float(block.meta.get("soc_kwh", vehicle.battery_capacity_kwh))

        charged = min(vehicle.charge_rate_kw * (gap / 60.0), vehicle.battery_capacity_kwh)
        soc_after = min(
            vehicle.battery_capacity_kwh,
            float(block.meta.get("soc_kwh", vehicle.battery_capacity_kwh)) + charged,
        )
        return charged, soc_after

    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int] = None,
    ) -> VSPSolution:
        _log.debug("VSP PARAMS: %s", self.vsp_params)

        self._start_timer()
        if not trips:
            return VSPSolution(algorithm=self.name)

        sorted_trips = _sort_trips(trips)
        trip_by_id = {trip.id: trip for trip in sorted_trips}
        active_blocks: List[Block] = []
        closed_blocks: List[Block] = []
        unassigned_trips: List[Trip] = []
        trip_to_block: Dict[int, Block] = {}
        charger_events: List[Tuple[int, int]] = []
        warnings: List[str] = []

        vehicle = vehicle_types[0] if vehicle_types else None
        fixed_cost = float(
            self._p(
                "fixed_vehicle_activation_cost",
                vehicle.fixed_cost if vehicle else settings.default_vehicle_fixed_cost,
            )
        )
        deadhead_cost = float(self._p("deadhead_cost_per_minute", 1.0))
        idle_cost = float(self._p("idle_cost_per_minute", 0.25))
        min_layover = int(self._p("min_layover_minutes", 8))
        max_vehicle_shift = int(self._p("max_vehicle_shift_minutes", 960))
        crew_block_limit = int(self._p("crew_block_limit_minutes", 0) or 0)
        if crew_block_limit > 0:
            max_vehicle_shift = min(max_vehicle_shift, crew_block_limit)
        same_depot_required = bool(self._p("same_depot_required", False))
        allow_multi_line_block = bool(self._p("allow_multi_line_block", True))
        allow_vehicle_split_shifts = bool(self._p("allow_vehicle_split_shifts", True))
        split_shift_min_gap = int(self._p("split_shift_min_gap_minutes", 120))
        split_shift_max_gap = int(self._p("split_shift_max_gap_minutes", 540))
        split_shift_min_gap = max(min_layover, split_shift_min_gap)
        split_shift_max_gap = max(split_shift_min_gap, split_shift_max_gap)
        max_chargers = int(self._p("max_simultaneous_chargers", 999999))
        preserve_preferred_pairs = bool(self._p("preserve_preferred_pairs", True))
        preferred_pair_window = int(self._p("preferred_pair_window_minutes", 120))
        pair_break_penalty = float(self._p("pair_break_penalty", fixed_cost * 1.25))
        paired_trip_bonus = float(self._p("paired_trip_bonus", fixed_cost * 0.05))
        reuse_ratio = float(self._p("max_connection_cost_for_reuse_ratio", 1.2))
        max_vehicles = int(self._p("max_vehicles", self._p("maxVehicles", 0)) or 0)
        connection_tolerance = int(self._p("connection_tolerance_minutes", 0))
        pullout_m = int(self._p("pullout_minutes", 10))
        pullback_m = int(self._p("pullback_minutes", 10))
        garage_return_cost = (pullout_m + pullback_m) * deadhead_cost
        garage_policy = self._p("vsp_garage_return_policy", "smart")
        if connection_tolerance > 0:
            _log.info("GreedyVSP: Using connection_tolerance_minutes=%d", connection_tolerance)

        enable_single_trip_compaction = bool(self._p("enable_single_trip_compaction", True))
        single_trip_compaction_max_gap = int(self._p("single_trip_compaction_max_gap_minutes", 420))
        single_trip_compaction_max_gap = max(min_layover, single_trip_compaction_max_gap)
        preferred_pairs = build_preferred_pairs(sorted_trips, min_layover, preferred_pair_window) if preserve_preferred_pairs else {}

        # Build trip_group forcing map: trip_group_id → [trip_ids]
        # When a trip has a trip_group_id, its pair must go to the same block (vehicle).
        trip_group_map: Dict[int, List[int]] = {}
        for trip in sorted_trips:
            gid = getattr(trip, "trip_group_id", None)
            if gid is not None:
                trip_group_map.setdefault(gid, []).append(trip.id)

        def _forced_trip_group_candidate(trip: Trip) -> Optional[Tuple[float, Block, Dict[str, Any]]]:
            """If another trip in the same trip_group is already assigned,
            try to place this trip in the same block (vehicle).
            For contiguous ida/volta (gap=0), relaxes deadhead requirements."""
            gid = getattr(trip, "trip_group_id", None)
            if gid is None:
                return None
            group_trips = trip_group_map.get(gid, [])
            # Find the block containing the other trip(s) from this group
            target_blk: Optional[Block] = None
            for tid in group_trips:
                if tid == trip.id:
                    continue
                blk = trip_to_block.get(tid)
                if blk is not None:
                    target_blk = blk
                    break
            if target_blk is None:
                return None

            # Check feasibility against LAST trip in block
            last = target_blk.trips[-1]
            gap = trip.start_time - last.end_time

            # For same trip_group with gap=0 (contiguous ida/volta), skip deadhead
            pair_trip = trip_by_id.get(group_trips[0] if group_trips[0] != trip.id else group_trips[-1])
            is_contiguous_group = (
                pair_trip is not None
                and pair_trip.end_time == trip.start_time
            )

            if gap < 0:
                # The block has trips AFTER the pair trip from the group.
                # For contiguous ida/volta, we need to INSERT after the pair trip.
                if is_contiguous_group:
                    # Check: can we insert this trip right after its pair trip?
                    pair_idx = None
                    for idx, t in enumerate(target_blk.trips):
                        if t.id == pair_trip.id:
                            pair_idx = idx
                            break
                    if pair_idx is not None:
                        # Check gap between pair_trip and THIS trip
                        pair_gap = trip.start_time - pair_trip.end_time
                        if pair_gap >= 0:
                            # Also check gap between THIS trip and the next trip in block
                            if pair_idx + 1 < len(target_blk.trips):
                                next_in_block = target_blk.trips[pair_idx + 1]
                                gap_after = next_in_block.start_time - trip.end_time
                                needed_after = self._deadhead(trip, next_in_block, min_layover)
                                if gap_after + connection_tolerance >= needed_after:
                                    # Feasible insertion! Insert after pair_trip
                                    data = {
                                        "gap": pair_gap,
                                        "needed_deadhead": 0,
                                        "charged_kwh": 0.0,
                                        "soc_after_trip": 0.0,
                                        "energy_need_kwh": self._energy_need(trip, vehicle),
                                        "marginal_cost": -paired_trip_bonus * 3.0,
                                        "pairing_delta": -paired_trip_bonus * 3.0,
                                        "pairing_state": "trip_group_inserted",
                                        "is_split_shift_window": False,
                                        "insert_after_idx": pair_idx,
                                    }
                                    return (-paired_trip_bonus * 3.0, target_blk, data)
                            else:
                                # pair_trip is the last trip, so this becomes new last
                                data = {
                                    "gap": pair_gap,
                                    "needed_deadhead": 0,
                                    "charged_kwh": 0.0,
                                    "soc_after_trip": 0.0,
                                    "energy_need_kwh": self._energy_need(trip, vehicle),
                                    "marginal_cost": -paired_trip_bonus * 3.0,
                                    "pairing_delta": -paired_trip_bonus * 3.0,
                                    "pairing_state": "trip_group_forced",
                                    "is_split_shift_window": False,
                                }
                                return (-paired_trip_bonus * 3.0, target_blk, data)
                return None

            needed = 0 if is_contiguous_group and gap == 0 else self._deadhead(last, trip, min_layover)
            if gap + connection_tolerance < needed:
                return None
            if trip.end_time - target_blk.start_time > max_vehicle_shift:
                return None
            if not allow_multi_line_block and last.line_id != trip.line_id:
                return None

            start_depot = target_blk.meta.get("start_depot_id")
            if same_depot_required and trip.depot_id is not None and start_depot is not None and trip.depot_id != start_depot:
                return None

            charged, soc_after_charge = self._maybe_recharge(target_blk, gap, vehicle, trip)
            energy_need = self._energy_need(trip, vehicle)
            soc_after_trip = soc_after_charge
            if vehicle and vehicle.is_electric and vehicle.battery_capacity_kwh > 0:
                min_soc_kwh = vehicle.minimum_soc * vehicle.battery_capacity_kwh
                soc_after_trip = soc_after_charge - energy_need
                if soc_after_trip < min_soc_kwh:
                    return None

            slack = max(0, gap - needed)
            energy_rate = 0.0
            if vehicle and vehicle.is_electric:
                energy_rate = vehicle.energy_cost_per_kwh or float(self._p("offpeak_energy_cost_per_kwh", 0.0))

            pairing_delta = -paired_trip_bonus * 3.0  # strong bonus for group forcing
            marginal_cost = needed * deadhead_cost + slack * idle_cost + energy_need * energy_rate + pairing_delta
            data = {
                "gap": gap,
                "needed_deadhead": needed,
                "charged_kwh": charged,
                "soc_after_trip": soc_after_trip,
                "energy_need_kwh": energy_need,
                "marginal_cost": marginal_cost,
                "pairing_delta": pairing_delta,
                "pairing_state": "trip_group_forced",
                "is_split_shift_window": bool(
                    allow_vehicle_split_shifts
                    and split_shift_min_gap <= gap <= split_shift_max_gap
                ),
                "garage_return_cost": garage_return_cost,
            }
            if data["is_split_shift_window"]:
                if garage_policy == "always":
                    data["marginal_cost"] = garage_return_cost + pairing_delta
                elif garage_policy == "never":
                    pass # stays as calculated (idle)
                else: # smart
                    data["marginal_cost"] = min(data["marginal_cost"], garage_return_cost + pairing_delta)

            return (data["marginal_cost"], target_blk, data)

        def _best_candidate(trip: Trip) -> Optional[Tuple[float, Block, Dict[str, Any]]]:
            best: Optional[Tuple[float, Block, tuple]] = None
            for blk in active_blocks:
                last = blk.trips[-1]
                reserved_pair = preferred_pairs.get(last.id)
                if reserved_pair is not None and reserved_pair != trip.id:
                    reserved_trip = trip_by_id.get(reserved_pair)
                    if reserved_trip is not None and trip.start_time <= reserved_trip.start_time:
                        continue
                if not allow_multi_line_block and last.line_id != trip.line_id:
                    continue
                gap = trip.start_time - last.end_time
                needed = self._deadhead(last, trip, min_layover)
                if gap < 0 or gap + connection_tolerance < needed:
                    continue
                if trip.end_time - blk.start_time > max_vehicle_shift:
                    continue

                start_depot = blk.meta.get("start_depot_id")
                if same_depot_required and trip.depot_id is not None and start_depot is not None and trip.depot_id != start_depot:
                    continue

                charged, soc_after_charge = self._maybe_recharge(blk, gap, vehicle, trip)
                energy_need = self._energy_need(trip, vehicle)
                soc_after_trip = soc_after_charge
                if vehicle and vehicle.is_electric and vehicle.battery_capacity_kwh > 0:
                    min_soc_kwh = vehicle.minimum_soc * vehicle.battery_capacity_kwh
                    soc_after_trip = soc_after_charge - energy_need
                    if soc_after_trip < min_soc_kwh:
                        continue

                slack = max(0, gap - needed)
                energy_rate = 0.0
                if vehicle and vehicle.is_electric:
                    energy_rate = vehicle.energy_cost_per_kwh or float(self._p("offpeak_energy_cost_per_kwh", 0.0))

                pairing_delta = 0.0
                pairing_state = "neutral"
                expected_pair = preferred_pairs.get(last.id)
                trip_gid = getattr(trip, "trip_group_id", None)
                block_has_group = False
                if trip_gid is not None:
                    block_has_group = any(getattr(t, "trip_group_id", None) == trip_gid for t in blk.trips)
                
                if block_has_group:
                    pairing_delta -= paired_trip_bonus * 3.0
                    pairing_state = "trip_group_match"
                elif expected_pair == trip.id:
                    pairing_delta -= paired_trip_bonus
                    pairing_state = "preferred_pair"
                elif expected_pair is not None and expected_pair != trip.id:
                    pairing_delta += pair_break_penalty
                    pairing_state = "pair_break"
                else:
                    if last.line_id == trip.line_id:
                        if last.destination_id == trip.origin_id and last.origin_id == trip.destination_id:
                            pairing_delta -= paired_trip_bonus * 2.0
                            pairing_state = "inferred_ida_volta"
                        else:
                            pairing_delta -= paired_trip_bonus * 0.5
                            pairing_state = "same_line"

                marginal_cost = needed * deadhead_cost + slack * idle_cost + energy_need * energy_rate + pairing_delta
                ranking_key = marginal_cost
                if best is None or ranking_key < best[0]:
                    best = (ranking_key, blk, (gap, needed, charged, soc_after_trip, energy_need, marginal_cost, pairing_delta, pairing_state))
                    
            if best is None:
                return None
            
            b_ranking, b_blk, raw_data = best
            gap, needed, charged, soc_after_trip, energy_need, marginal_cost, pairing_delta, pairing_state = raw_data
            
            data = {
                "gap": gap,
                "needed_deadhead": needed,
                "charged_kwh": charged,
                "soc_after_trip": soc_after_trip,
                "energy_need_kwh": energy_need,
                "marginal_cost": marginal_cost,
                "ranking_key": b_ranking,
                "pairing_delta": pairing_delta,
                "pairing_state": pairing_state,
                "is_split_shift_window": bool(allow_vehicle_split_shifts and split_shift_min_gap <= gap <= split_shift_max_gap),
                "garage_return_cost": garage_return_cost,
            }
            if data["is_split_shift_window"]:
                if garage_policy == "always":
                    data["marginal_cost"] = garage_return_cost + pairing_delta
                elif garage_policy == "never":
                    pass # stays as calculated (idle)
                else: # smart
                    data["marginal_cost"] = min(data["marginal_cost"], garage_return_cost + pairing_delta)
                
                data["ranking_key"] = data["marginal_cost"]

            return (data["marginal_cost"], b_blk, data)

        def _forced_preferred_pair_candidate(trip: Trip) -> Optional[Tuple[float, Block, Dict[str, Any]]]:
            pair_trip_id = preferred_pairs.get(trip.id)
            if pair_trip_id is None:
                return None
            pair_trip = trip_by_id.get(pair_trip_id)
            if pair_trip is None:
                return None
            if pair_trip.end_time > trip.start_time:
                return None
            blk = trip_to_block.get(pair_trip_id)
            if blk is None or not blk.trips or blk.trips[-1].id != pair_trip_id:
                return None

            last = blk.trips[-1]
            if not allow_multi_line_block and last.line_id != trip.line_id:
                return None
            gap = trip.start_time - last.end_time
            needed = self._deadhead(last, trip, min_layover)
            if gap < 0 or gap + connection_tolerance < needed:
                return None
            if trip.end_time - blk.start_time > max_vehicle_shift:
                return None

            start_depot = blk.meta.get("start_depot_id")
            if same_depot_required and trip.depot_id is not None and start_depot is not None and trip.depot_id != start_depot:
                return None

            charged, soc_after_charge = self._maybe_recharge(blk, gap, vehicle, trip)
            energy_need = self._energy_need(trip, vehicle)
            soc_after_trip = soc_after_charge
            if vehicle and vehicle.is_electric and vehicle.battery_capacity_kwh > 0:
                min_soc_kwh = vehicle.minimum_soc * vehicle.battery_capacity_kwh
                soc_after_trip = soc_after_charge - energy_need
                if soc_after_trip < min_soc_kwh:
                    return None

            slack = max(0, gap - needed)
            energy_rate = 0.0
            if vehicle and vehicle.is_electric:
                energy_rate = vehicle.energy_cost_per_kwh or float(self._p("offpeak_energy_cost_per_kwh", 0.0))

            pairing_delta = -paired_trip_bonus
            marginal_cost = needed * deadhead_cost + slack * idle_cost + energy_need * energy_rate + pairing_delta
            data = {
                "gap": gap,
                "needed_deadhead": needed,
                "charged_kwh": charged,
                "soc_after_trip": soc_after_trip,
                "energy_need_kwh": energy_need,
                "marginal_cost": marginal_cost,
                "pairing_delta": pairing_delta,
                "pairing_state": "preferred_pair",
                "is_split_shift_window": bool(
                    allow_vehicle_split_shifts
                    and split_shift_min_gap <= gap <= split_shift_max_gap
                ),
                "garage_return_cost": garage_return_cost,
            }
            if data["is_split_shift_window"]:
                if garage_policy == "always":
                    data["marginal_cost"] = garage_return_cost + pairing_delta
                elif garage_policy == "never":
                    pass # stays as calculated (idle)
                else: # smart
                    data["marginal_cost"] = min(data["marginal_cost"], garage_return_cost + pairing_delta)

            return (data["marginal_cost"], blk, data)

        for trip in sorted_trips:
            candidate = _forced_trip_group_candidate(trip) or _forced_preferred_pair_candidate(trip) or _best_candidate(trip)
            candidate_follows_pair = bool(candidate and candidate[2].get("pairing_state") in ("preferred_pair", "trip_group_forced"))
            candidate_is_split_shift = bool(candidate and candidate[2].get("is_split_shift_window"))
            # Usar marginal_cost (não ranking_key) para decisão de abrir novo veículo
            candidate_cost = float(candidate[2].get("marginal_cost", 0)) if candidate else 0
            should_open_new_vehicle = candidate is None or (
                candidate_cost >= fixed_cost * reuse_ratio
                and not candidate_follows_pair
                and not candidate_is_split_shift
            )
            if should_open_new_vehicle:
                current_fleet = len(active_blocks) + len(closed_blocks)
                if max_vehicles > 0 and current_fleet >= max_vehicles:
                    if candidate is None:
                        unassigned_trips.append(trip)
                        warnings.append(f"FLEET_LIMIT_EXCEEDED max_vehicles={max_vehicles} T{trip.id}")
                        continue
                else:
                    blk = Block(id=self._next_block_id(), trips=[trip])
                    if vehicle:
                        blk.vehicle_type_id = vehicle.id
                    blk.meta.update(
                        {
                            "start_depot_id": trip.depot_id if trip.depot_id is not None else depot_id,
                            "end_depot_id": trip.depot_id if trip.depot_id is not None else depot_id,
                            "activation_cost": fixed_cost,
                            "connection_cost": 0.0,
                            "deadhead_minutes": 0,
                            "idle_minutes": 0,
                            "energy_kwh": self._energy_need(trip, vehicle),
                            "pairing_score": 0.0,
                            "paired_connections_followed": 0,
                            "pair_break_connections": 0,
                        }
                    )
                    if vehicle and vehicle.is_electric and vehicle.battery_capacity_kwh > 0:
                        blk.meta["soc_kwh"] = vehicle.battery_capacity_kwh - self._energy_need(trip, vehicle)
                        if blk.meta["soc_kwh"] < vehicle.minimum_soc * vehicle.battery_capacity_kwh:
                            unassigned_trips.append(trip)
                            warnings.append(f"EV_SOC_INSUFFICIENT T{trip.id}")
                            continue
                    active_blocks.append(blk)
                    trip_to_block[trip.id] = blk
                    continue

            if candidate is None:
                unassigned_trips.append(trip)
                warnings.append(f"UNASSIGNED_TRIP T{trip.id}")
                continue

            if should_open_new_vehicle and max_vehicles > 0:
                warnings.append(f"FLEET_REUSE_FORCED max_vehicles={max_vehicles} T{trip.id}")

            _, blk, data = candidate
            insert_idx = data.get("insert_after_idx")
            if insert_idx is not None:
                blk.trips.insert(insert_idx + 1, trip)
            else:
                blk.trips.append(trip)
            blk.meta["connection_cost"] = float(blk.meta.get("connection_cost", 0.0)) + float(data["marginal_cost"])
            blk.meta["deadhead_minutes"] = int(blk.meta.get("deadhead_minutes", 0)) + int(data["needed_deadhead"])
            blk.meta["idle_minutes"] = int(blk.meta.get("idle_minutes", 0)) + max(0, int(data["gap"] - data["needed_deadhead"]))
            blk.meta["energy_kwh"] = float(blk.meta.get("energy_kwh", 0.0)) + float(data["energy_need_kwh"])
            blk.meta["pairing_score"] = float(blk.meta.get("pairing_score", 0.0)) - float(data.get("pairing_delta", 0.0))
            if data.get("pairing_state") == "preferred_pair":
                blk.meta["paired_connections_followed"] = int(blk.meta.get("paired_connections_followed", 0)) + 1
            elif data.get("pairing_state") == "pair_break":
                blk.meta["pair_break_connections"] = int(blk.meta.get("pair_break_connections", 0)) + 1
            if vehicle and vehicle.is_electric:
                blk.meta["soc_kwh"] = float(data["soc_after_trip"])
                if data["charged_kwh"] > 0:
                    charger_events.append((trip.start_time - int(data["gap"]), trip.start_time))
                    blk.meta["charged_kwh"] = float(blk.meta.get("charged_kwh", 0.0)) + float(data["charged_kwh"])
            blk.meta["end_depot_id"] = trip.depot_id if trip.depot_id is not None else blk.meta.get("start_depot_id")

            still_active: List[Block] = []
            for active in active_blocks:
                if trip.start_time - active.trips[-1].end_time > max_vehicle_shift:
                    closed_blocks.append(active)
                else:
                    still_active.append(active)
            active_blocks = still_active
            if blk not in active_blocks and blk not in closed_blocks:
                active_blocks.append(blk)
            trip_to_block[trip.id] = blk

        all_blocks = [*closed_blocks, *active_blocks]

        if enable_single_trip_compaction and not (vehicle and vehicle.is_electric):
            moved_count = 0

            def _append_candidate(target: Block, trip: Trip) -> Optional[Tuple[float, Dict[str, Any]]]:
                if not target.trips:
                    return None
                last = target.trips[-1]
                if not allow_multi_line_block and last.line_id != trip.line_id:
                    return None
                gap = int(trip.start_time - last.end_time)
                needed = int(self._deadhead(last, trip, min_layover))
                if gap < needed or gap > single_trip_compaction_max_gap:
                    return None
                if trip.end_time - target.start_time > max_vehicle_shift:
                    return None
                start_depot = target.meta.get("start_depot_id")
                end_depot = target.meta.get("end_depot_id")
                if same_depot_required and start_depot is not None and trip.depot_id is not None and trip.depot_id != start_depot:
                    return None
                if same_depot_required and end_depot is not None and trip.depot_id is not None and start_depot is not None and trip.depot_id != start_depot:
                    return None
                marginal = needed * deadhead_cost + max(0, gap - needed) * idle_cost
                return marginal, {"mode": "append", "gap": gap, "needed": needed}

            def _prepend_candidate(target: Block, trip: Trip) -> Optional[Tuple[float, Dict[str, Any]]]:
                if not target.trips:
                    return None
                first = target.trips[0]
                if not allow_multi_line_block and first.line_id != trip.line_id:
                    return None
                gap = int(first.start_time - trip.end_time)
                needed = int(self._deadhead(trip, first, min_layover))
                if gap < needed or gap > single_trip_compaction_max_gap:
                    return None
                if target.end_time - trip.start_time > max_vehicle_shift:
                    return None
                start_depot = target.meta.get("start_depot_id")
                end_depot = target.meta.get("end_depot_id")
                if same_depot_required and end_depot is not None and trip.depot_id is not None and trip.depot_id != end_depot:
                    return None
                if same_depot_required and start_depot is not None and end_depot is not None and trip.depot_id is not None and trip.depot_id != end_depot:
                    return None
                marginal = needed * deadhead_cost + max(0, gap - needed) * idle_cost
                return marginal, {"mode": "prepend", "gap": gap, "needed": needed}

            for source in sorted([b for b in all_blocks if len(b.trips) == 1], key=lambda b: (b.start_time, b.id)):
                if source not in all_blocks or len(source.trips) != 1:
                    continue
                trip = source.trips[0]
                best: Optional[Tuple[float, Block, Dict[str, Any]]] = None
                for target in all_blocks:
                    if target.id == source.id:
                        continue
                    append = _append_candidate(target, trip)
                    if append is not None:
                        score, data = append
                        if best is None or score < best[0]:
                            best = (score, target, data)
                    prepend = _prepend_candidate(target, trip)
                    if prepend is not None:
                        score, data = prepend
                        if best is None or score < best[0]:
                            best = (score, target, data)

                if best is None:
                    continue

                _, target, data = best
                if data["mode"] == "append":
                    target.trips.append(trip)
                else:
                    target.trips.insert(0, trip)

                target.meta["connection_cost"] = float(target.meta.get("connection_cost", 0.0)) + float(
                    data["needed"] * deadhead_cost + max(0, data["gap"] - data["needed"]) * idle_cost
                )
                target.meta["deadhead_minutes"] = int(target.meta.get("deadhead_minutes", 0)) + int(data["needed"])
                target.meta["idle_minutes"] = int(target.meta.get("idle_minutes", 0)) + max(0, int(data["gap"] - data["needed"]))
                target.meta["energy_kwh"] = float(target.meta.get("energy_kwh", 0.0)) + float(self._energy_need(trip, vehicle))
                if vehicle and vehicle.is_electric and vehicle.battery_capacity_kwh > 0:
                    target.meta["soc_kwh"] = float(target.meta.get("soc_kwh", vehicle.battery_capacity_kwh)) - float(self._energy_need(trip, vehicle))
                target.meta["start_depot_id"] = target.trips[0].depot_id if target.trips[0].depot_id is not None else target.meta.get("start_depot_id")
                target.meta["end_depot_id"] = target.trips[-1].depot_id if target.trips[-1].depot_id is not None else target.meta.get("end_depot_id")

                all_blocks.remove(source)
                moved_count += 1

            if moved_count > 0:
                warnings.append(f"SINGLE_TRIP_BLOCKS_COMPACTED count={moved_count}")
        pair_meta = pairing_stats(all_blocks, preferred_pairs) if preferred_pairs else {
            "preferred_pair_count": 0,
            "paired_connections_followed": 0,
            "preferred_pair_breaks": 0,
        }

        if same_depot_required:
            for blk in all_blocks:
                if (
                    blk.meta.get("start_depot_id") is not None
                    and blk.meta.get("end_depot_id") is not None
                    and blk.meta["start_depot_id"] != blk.meta["end_depot_id"]
                ):
                    blk.warnings.append("START_END_DEPOT_MISMATCH")
                    warnings.append(f"BLOCK_DEPOT_MISMATCH B{blk.id}")

        if charger_events and max_chargers < 999999:
            timeline: List[Tuple[int, int]] = []
            for start, end in charger_events:
                timeline.append((start, 1))
                timeline.append((end, -1))
            concurrent = 0
            peak = 0
            for _, delta in sorted(timeline):
                concurrent += delta
                peak = max(peak, concurrent)
            if peak > max_chargers:
                warnings.append(f"CHARGER_CAPACITY_EXCEEDED peak={peak}>{max_chargers}")
        if pair_meta["preferred_pair_breaks"] > 0:
            warnings.append(
                f"PREFERRED_PAIR_BREAKS matched={pair_meta['paired_connections_followed']}/{pair_meta['preferred_pair_count']}"
            )

        return VSPSolution(
            blocks=all_blocks,
            unassigned_trips=unassigned_trips,
            algorithm=self.name,
            elapsed_ms=self._elapsed_ms(),
            warnings=warnings,
            meta={
                "objective": {
                    "formula": "sum(f_k) + sum(c_ij * x_ij)",
                    "fixed_vehicle_activation_cost": fixed_cost,
                    "deadhead_cost_per_minute": deadhead_cost,
                    "idle_cost_per_minute": idle_cost,
                },
                "crew_block_limit_minutes": crew_block_limit,
                "same_depot_required": same_depot_required,
                "max_simultaneous_chargers": max_chargers,
                "preserve_preferred_pairs": preserve_preferred_pairs,
                "preferred_pair_window_minutes": preferred_pair_window,
                "enable_single_trip_compaction": enable_single_trip_compaction,
                "single_trip_compaction_max_gap_minutes": single_trip_compaction_max_gap,
                **pair_meta,
            },
        )
