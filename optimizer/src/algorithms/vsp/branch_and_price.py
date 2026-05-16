"""
VSP via Branch-and-Price (column generation).

STATUS: F4+EV+CCT — Ryan-Foster branching + EV-aware pricing + CCT driving constraint.
        F4: Ryan-Foster (1 camada) sobre LP fracionário.
        EV (Sprint 2): label 6D com SoC como recurso. Dominância 4D.
        CCT (Sprint 2+3): driving_continuous como recurso duro no pricing.
        Ver docs/column_generation_plan.md para plano completo.

Formulação:

    min  Σ_p c_p x_p
    s.a. Σ_p a_{ip} x_p = 1     ∀ trip i
              x_p ∈ {0,1}

Master (LP relaxado):  x_p ∈ [0,1] — expõe duais π_i.
Pricing (SPPRC):       Label 6D = (rc, shift, cost, path_ids, soc_kwh, drv_minutes).
                       Dominância 4D: rc↓, shift↓, soc↑, drv↓.
                       EV: SoC propagado (recharge no gap, consumo na trip). Hard filter.
                       CCT: drv_continuous resetado após break ≥ min_break. Hard filter.
MIP final:             CBC com todas colunas acumuladas → solução inteira.
Ryan-Foster (F4):      Se LP fracionário, resolve MIP em TOGETHER/APART sobre par mais
                       fracionário. Aceita ramo se melhora (blocos, custo).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from ...core.config import get_settings
from ...domain.interfaces import IVSPAlgorithm
from ...domain.models import Block, Trip, VehicleType, VSPSolution
from ..base import BaseAlgorithm
from ..utils import is_connection_feasible, select_vehicle_type
from .greedy import GreedyVSP

_log = logging.getLogger(__name__)
settings = get_settings()

try:
    import pulp  # type: ignore
    _PULP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PULP_AVAILABLE = False

_DEFAULT_FIXED_COST = 800.0
_DEFAULT_DEADHEAD_COST = 1.0
_DEFAULT_IDLE_COST = 0.25
_DEFAULT_MIN_LAYOVER = 8
_DEFAULT_MAX_VEHICLE_SHIFT = 960
_DEFAULT_MAX_PRICING_ITERS = 5
_DEFAULT_MAX_PRICING_COLUMNS = 2000
_DEFAULT_EV_KWH_PER_KM = 1.8     # kWh/km típico ônibus elétrico
_DEFAULT_MAX_DRIVING_MINUTES = 0  # 0 = desabilitado (sem restrição CCT no pricing)
_DEFAULT_MIN_BREAK_MINUTES = 30   # pausa mínima para resetar condução contínua (CLT)

# Índices dos elementos do label SPPRC (6-tupla)
_I_RC, _I_SHIFT, _I_COST, _I_PATH, _I_SOC, _I_DRV = 0, 1, 2, 3, 4, 5


def _make_solver(time_limit: int, threads: int = 1) -> "pulp.LpSolver":
    cbc = pulp.PULP_CBC_CMD(timeLimit=time_limit, msg=0, keepFiles=False, threads=threads)
    if cbc.available():
        return cbc
    try:
        return pulp.HiGHS(timeLimit=time_limit, msg=0, threads=threads)
    except Exception:
        return cbc


class MasterProblemLP:
    """LP relaxado do set covering sobre colunas de blocos de veículo.

    Mantém pool de colunas, resolve relaxação LP (x_p ∈ [0,1]),
    expõe duais π_i das restrições de cobertura para o pricing subproblem.
    """

    def __init__(self) -> None:
        self._columns: List[Tuple[List[int], float]] = []
        self._lp_objective: Optional[float] = None
        self._lp_status: Optional[int] = None
        self._x_values: List[float] = []
        self._duals: Dict[int, float] = {}

    def add_column(self, trip_ids: List[int], cost: float) -> int:
        idx = len(self._columns)
        self._columns.append((list(trip_ids), float(cost)))
        return idx

    @property
    def num_columns(self) -> int:
        return len(self._columns)

    def solve_lp(self, time_limit: int = 60) -> float:
        """Resolve relaxação LP. Retorna objetivo. Popula x_values e duais."""
        if not _PULP_AVAILABLE:
            raise RuntimeError("PuLP indisponível — MasterProblemLP requer pulp")
        if not self._columns:
            self._lp_objective = 0.0
            return 0.0

        all_trips = sorted({tid for ids, _ in self._columns for tid in ids})
        prob = pulp.LpProblem("BP_Master_LP", pulp.LpMinimize)
        x = [
            pulp.LpVariable(f"x_{i}", lowBound=0.0, upBound=1.0)
            for i in range(len(self._columns))
        ]
        prob += pulp.lpSum(cost * x[i] for i, (_, cost) in enumerate(self._columns))
        for trip_id in all_trips:
            prob += (
                pulp.lpSum(
                    x[i] for i, (ids, _) in enumerate(self._columns) if trip_id in ids
                )
                >= 1,
                f"cover_{trip_id}",
            )
        prob.solve(_make_solver(time_limit, threads=settings.ilp_threads))
        self._lp_status = prob.status
        self._x_values = [float(pulp.value(v) or 0.0) for v in x]
        self._duals = {
            tid: float(prob.constraints[f"cover_{tid}"].pi or 0.0)
            for tid in all_trips
            if f"cover_{tid}" in prob.constraints
        }
        self._lp_objective = float(pulp.value(prob.objective) or 0.0)
        return self._lp_objective

    def solve_mip(self, time_limit: int = 120) -> float:
        """Resolve MIP inteiro (x_p ∈ {0,1}) sobre pool atual de colunas."""
        if not _PULP_AVAILABLE:
            raise RuntimeError("PuLP indisponível")
        if not self._columns:
            self._lp_objective = 0.0
            return 0.0

        all_trips = sorted({tid for ids, _ in self._columns for tid in ids})
        prob = pulp.LpProblem("BP_Master_MIP", pulp.LpMinimize)
        x = [
            pulp.LpVariable(f"x_{i}", cat="Binary")
            for i in range(len(self._columns))
        ]
        prob += pulp.lpSum(cost * x[i] for i, (_, cost) in enumerate(self._columns))
        for trip_id in all_trips:
            prob += (
                pulp.lpSum(
                    x[i] for i, (ids, _) in enumerate(self._columns) if trip_id in ids
                )
                >= 1,
                f"cover_{trip_id}",
            )
        prob.solve(_make_solver(time_limit, threads=settings.ilp_threads))
        self._lp_status = prob.status
        self._x_values = [float(pulp.value(v) or 0.0) for v in x]
        self._lp_objective = float(pulp.value(prob.objective) or 0.0)
        return self._lp_objective

    def duals(self) -> Dict[int, float]:
        return dict(self._duals)

    def selected_columns(self, threshold: float = 0.5) -> List[int]:
        return [i for i, v in enumerate(self._x_values) if v >= threshold]

    def column_trips(self, index: int) -> List[int]:
        return list(self._columns[index][0])

    # ------------------------------------------------------------------ F4

    def is_lp_integral(self, tol: float = 1e-4) -> bool:
        """True se todos os x_p da última solução LP estão em {0,1} (dentro de tol)."""
        return all(v < tol or v > 1.0 - tol for v in self._x_values)

    def ryan_foster_pair(self) -> Optional[Tuple[int, int]]:
        """Seleciona par (i,j) Ryan-Foster a partir da solução LP fracionária.

        Escolhe a coluna mais fracionária (x_p mais próximo de 0.5) que contém
        ≥ 2 trips. Retorna os dois primeiros trip_ids dessa coluna.
        Retorna None se LP for integral ou todas as colunas fracionárias forem singletoons.
        """
        candidates = [
            (abs(v - 0.5), i, self._columns[i][0])
            for i, v in enumerate(self._x_values)
            if 1e-4 < v < 1.0 - 1e-4 and len(self._columns[i][0]) >= 2
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])  # menor distância a 0.5 primeiro
        _, _, trip_ids = candidates[0]
        return (trip_ids[0], trip_ids[1])

    def solve_mip_with_constraints(
        self,
        together: Optional[Tuple[int, int]] = None,
        apart: Optional[Tuple[int, int]] = None,
        time_limit: int = 60,
    ) -> Tuple[float, List[int]]:
        """Resolve MIP sobre colunas que satisfazem os constraints Ryan-Foster.

        together=(i,j): coluna deve conter ambos ou nenhum dos trips i,j.
        apart=(i,j):    coluna não pode conter ambos i e j.

        Retorna (objective, selected_global_indices). Se inviável, retorna (inf, []).
        """
        if not _PULP_AVAILABLE:
            raise RuntimeError("PuLP indisponível")

        # Filtrar colunas que violam os constraints
        valid: List[int] = []
        for i, (trip_ids, _) in enumerate(self._columns):
            tset = set(trip_ids)
            if together:
                a, b = together
                if (a in tset) != (b in tset):
                    continue
            if apart:
                a, b = apart
                if a in tset and b in tset:
                    continue
            valid.append(i)

        if not valid:
            return (float("inf"), [])

        sub_cols = [self._columns[i] for i in valid]
        all_trips = sorted({tid for ids, _ in sub_cols for tid in ids})

        prob = pulp.LpProblem("BP_RF_MIP", pulp.LpMinimize)
        x = [pulp.LpVariable(f"x_{j}", cat="Binary") for j in range(len(sub_cols))]
        prob += pulp.lpSum(cost * x[j] for j, (_, cost) in enumerate(sub_cols))
        for trip_id in all_trips:
            prob += (
                pulp.lpSum(x[j] for j, (ids, _) in enumerate(sub_cols) if trip_id in ids) >= 1,
                f"cover_{trip_id}",
            )

        prob.solve(_make_solver(time_limit))
        obj = float(pulp.value(prob.objective) or float("inf"))
        sel_local = [j for j, v in enumerate(x) if (pulp.value(v) or 0.0) >= 0.5]
        sel_global = [valid[j] for j in sel_local]
        return (obj, sel_global)


class PricingSubproblem:
    """Pricing via SPPRC com dominância 4D (EV+CCT aware).

    Algoritmo: DP em ordem topológica (start_time).
    Label 6D = (rc, shift, cost, path_ids, soc_kwh, drv_minutes).

    Dominância: label A domina B no mesmo nó se:
        rc_A ≤ rc_B  E  shift_A ≤ shift_B  E  soc_A ≥ soc_B  E  drv_A ≤ drv_B

    EV: soc propagado — recarrega no gap a charge_rate_kw, consome kwh_per_km*dist.
        Labels com soc < minimum_soc_kwh são descartados (hard filter).
    CCT: drv acumulado desde o último break. Reseta quando gap ≥ min_break_minutes.
        Labels com drv > max_driving_minutes são descartados (hard filter).

    Para não-EV: soc = float('inf') → dimensão soc sempre satisfeita.
    Para CCT desabilitado: drv = 0 → dimensão drv sempre satisfeita.
    """

    _MAX_SUCCESSORS_PER_NODE = 30

    def __init__(
        self,
        trips: List[Trip],
        fixed_cost: float = _DEFAULT_FIXED_COST,
        deadhead_cost: float = _DEFAULT_DEADHEAD_COST,
        idle_cost: float = _DEFAULT_IDLE_COST,
        min_layover: int = _DEFAULT_MIN_LAYOVER,
        max_vehicle_shift: int = _DEFAULT_MAX_VEHICLE_SHIFT,
        max_labels_per_node: int = 0,
        # Sprint 2: EV params
        is_ev: bool = False,
        battery_kwh: float = 0.0,
        minimum_soc_kwh: float = 0.0,
        charge_rate_kw: float = 0.0,
        energy_cost_per_kwh: float = 0.0,
        kwh_per_km: float = _DEFAULT_EV_KWH_PER_KM,
        # Sprint 2+3: CCT driving constraint
        max_driving_minutes: int = _DEFAULT_MAX_DRIVING_MINUTES,
        min_break_minutes: int = _DEFAULT_MIN_BREAK_MINUTES,
    ) -> None:
        self._trips = sorted(trips, key=lambda t: t.start_time)
        self._by_id: Dict[int, Trip] = {t.id: t for t in self._trips}
        self.fixed_cost = float(fixed_cost)
        self.deadhead_cost = float(deadhead_cost)
        self.idle_cost = float(idle_cost)
        self.min_layover = int(min_layover)
        self.max_vehicle_shift = int(max_vehicle_shift)
        n = len(self._trips)
        if max_labels_per_node <= 0:
            self.max_labels_per_node = max(5, min(50, 5000 // max(1, n)))
        else:
            self.max_labels_per_node = int(max_labels_per_node)
        self.is_ev = bool(is_ev)
        self.battery_kwh = float(battery_kwh)
        self.minimum_soc_kwh = float(minimum_soc_kwh)
        self.charge_rate_kw = float(charge_rate_kw)
        self.energy_cost_per_kwh = float(energy_cost_per_kwh)
        self.kwh_per_km = float(kwh_per_km)
        self.max_driving_minutes = int(max_driving_minutes)
        self.min_break_minutes = int(min_break_minutes)
        self._successors: Dict[int, List[Trip]] = self._build_successors()

    def _build_successors(self) -> Dict[int, List[Trip]]:
        succ: Dict[int, List[Trip]] = {}
        cap = self._MAX_SUCCESSORS_PER_NODE
        for i, trip in enumerate(self._trips):
            candidates = []
            for j in range(i + 1, len(self._trips)):
                nxt = self._trips[j]
                if nxt.start_time - trip.end_time > self.max_vehicle_shift:
                    break
                if is_connection_feasible(trip, nxt, min_layover=self.min_layover):
                    candidates.append(nxt)
                    if len(candidates) >= cap:
                        break
            succ[trip.id] = candidates
        return succ

    def _arc_cost(self, curr: Trip, nxt: Trip) -> float:
        deadhead = curr.deadhead_times.get(nxt.origin_id, 0)
        gap = nxt.start_time - curr.end_time
        idle = max(0, gap - deadhead)
        return deadhead * self.deadhead_cost + idle * self.idle_cost

    @staticmethod
    def _dominates(a: tuple, b: tuple) -> bool:
        """True se label a domina b (rc↓, shift↓, soc↑, drv↓)."""
        return (a[_I_RC] <= b[_I_RC] and a[_I_SHIFT] <= b[_I_SHIFT]
                and a[_I_SOC] >= b[_I_SOC] and a[_I_DRV] <= b[_I_DRV])

    def _prune(self, labels: list) -> list:
        """Remove labels dominados. label = (rc, shift, cost, path_ids, soc, drv)."""
        if len(labels) <= 1:
            return labels
        kept: list = []
        for lbl in sorted(labels, key=lambda x: (x[_I_RC], x[_I_SHIFT])):
            if not any(self._dominates(k, lbl) and k is not lbl for k in kept):
                kept.append(lbl)
        return kept[:self.max_labels_per_node]

    def find_columns(
        self,
        duals: Dict[int, float],
        max_columns: int = _DEFAULT_MAX_PRICING_COLUMNS,
    ) -> List[Tuple[List[int], float]]:
        """Devolve até max_columns (trip_ids, custo) com reduced cost < -1e-5.

        Label 6D: (rc, shift, cost, path_ids, soc_kwh, drv_minutes).
        EV: soc propagado (recharge no gap, consumo na trip). Hard filter.
        CCT: drv resetado após break ≥ min_break_minutes. Hard filter.
        Memória: labels liberados após propagação — pico O(fan-out × max_labels).
        """
        labels_at: Dict[int, list] = {}
        results: List[Tuple[float, List[int], float]] = []

        for trip in self._trips:
            my_labels = labels_at.pop(trip.id, [])

            # Label inicial para este nó (início de um novo bloco)
            trip_kwh_init = trip.distance_km * self.kwh_per_km if self.is_ev else 0.0
            soc0 = (self.battery_kwh - trip_kwh_init) if self.is_ev else float('inf')
            drv0 = trip.duration if self.max_driving_minutes > 0 else 0
            if (not self.is_ev or soc0 >= self.minimum_soc_kwh) and \
               (self.max_driving_minutes == 0 or drv0 <= self.max_driving_minutes):
                energy_cost_init = trip_kwh_init * self.energy_cost_per_kwh
                rc0 = self.fixed_cost + energy_cost_init - duals.get(trip.id, 0.0)
                shift0 = trip.end_time - trip.start_time
                my_labels.append((rc0, shift0, self.fixed_cost + energy_cost_init,
                                   (trip.id,), soc0, drv0))
            my_labels = self._prune(my_labels)

            # Coletar colunas com rc < 0 que terminam neste nó
            for lbl in my_labels:
                if lbl[_I_RC] < -1e-5:
                    results.append((lbl[_I_RC], list(lbl[_I_PATH]), lbl[_I_COST]))
                    if len(results) >= max_columns * 4:
                        results.sort(key=lambda r: r[0])
                        results = results[:max_columns]

            # Propagar para sucessores
            for nxt in self._successors.get(trip.id, []):
                arc = self._arc_cost(trip, nxt)
                nxt_dual = duals.get(nxt.id, 0.0)
                gap_minutes = nxt.start_time - trip.end_time
                nxt_kwh = nxt.distance_km * self.kwh_per_km if self.is_ev else 0.0
                nxt_energy_cost = nxt_kwh * self.energy_cost_per_kwh
                gap_is_break = (self.max_driving_minutes > 0
                                and gap_minutes >= self.min_break_minutes)
                max_recharge = (gap_minutes / 60.0 * self.charge_rate_kw
                                if self.is_ev else 0.0)

                new_labels: list = []
                for lbl in my_labels:
                    rc, _shift, cost, path_ids, soc, drv = lbl
                    if nxt.id in path_ids:
                        continue
                    new_shift = nxt.end_time - self._by_id[path_ids[0]].start_time
                    if new_shift > self.max_vehicle_shift:
                        continue
                    if self.is_ev:
                        recharged = min(max_recharge, self.battery_kwh - soc)
                        new_soc = soc + max(0.0, recharged) - nxt_kwh
                        if new_soc < self.minimum_soc_kwh:
                            continue
                    else:
                        new_soc = float('inf')
                    if self.max_driving_minutes > 0:
                        new_drv = nxt.duration if gap_is_break else drv + nxt.duration
                        if new_drv > self.max_driving_minutes:
                            continue
                    else:
                        new_drv = 0
                    new_rc = rc + arc + nxt_energy_cost - nxt_dual
                    new_cost = cost + arc + nxt_energy_cost
                    new_labels.append((new_rc, new_shift, new_cost,
                                       path_ids + (nxt.id,), new_soc, new_drv))

                if new_labels:
                    existing = labels_at.get(nxt.id, [])
                    labels_at[nxt.id] = self._prune(
                        (existing + new_labels) if existing else new_labels
                    )

        results.sort(key=lambda r: r[0])
        seen: Set[Tuple[int, ...]] = set()
        deduped = []
        for rc, trip_ids, cost in results:
            key = tuple(trip_ids)
            if key not in seen:
                seen.add(key)
                deduped.append((trip_ids, cost))
            if len(deduped) >= max_columns:
                break
        return deduped


class BranchAndPrice(BaseAlgorithm, IVSPAlgorithm):
    """B&P com warm-start greedy + pricing enumerativo (F2) + MIP final.

    Parâmetros lidos de vsp_params (mesmas chaves do GreedyVSP):
      - fixed_vehicle_activation_cost
      - deadhead_cost_per_minute
      - idle_cost_per_minute
      - min_layover_minutes
      - max_vehicle_shift_minutes
      - bp_max_pricing_iterations   (default: 5)
      - bp_max_pricing_columns      (default: 2000)
      - bp_max_labels_per_node      (default: 50)
    """

    def __init__(self, vsp_params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(name="branch_and_price")
        self.vsp_params: Dict[str, Any] = dict(vsp_params or {})

    def _p(self, key: str, default: Any) -> Any:
        v = self.vsp_params.get(key, default)
        return default if v is None else v

    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int] = None,
    ) -> VSPSolution:
        self._start_timer()
        if not trips:
            return VSPSolution(algorithm=self.name)
        if not _PULP_AVAILABLE:
            _log.warning("PuLP indisponível — caindo no GreedyVSP")
            sol = GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id)
            sol.meta["branch_and_price"] = {"fallback": "pulp_unavailable"}
            return sol

        vehicle = select_vehicle_type(vehicle_types, depot_id)
        fixed_cost = float(self._p(
            "fixed_vehicle_activation_cost",
            vehicle.fixed_cost if vehicle else _DEFAULT_FIXED_COST,
        ))
        deadhead_cost = float(self._p("deadhead_cost_per_minute", _DEFAULT_DEADHEAD_COST))
        idle_cost = float(self._p("idle_cost_per_minute", _DEFAULT_IDLE_COST))
        min_layover = int(self._p("min_layover_minutes", _DEFAULT_MIN_LAYOVER))
        max_vehicle_shift = int(self._p("max_vehicle_shift_minutes", _DEFAULT_MAX_VEHICLE_SHIFT))
        max_pricing_iters = int(self._p("bp_max_pricing_iterations", _DEFAULT_MAX_PRICING_ITERS))
        max_pricing_cols = int(self._p("bp_max_pricing_columns", _DEFAULT_MAX_PRICING_COLUMNS))
        max_labels_per_node = int(self._p("bp_max_labels_per_node", 50))

        # EV params from vehicle type
        is_ev = bool(getattr(vehicle, "is_electric", False)) if vehicle else False
        battery_kwh = float(getattr(vehicle, "battery_capacity_kwh", 0.0)) if vehicle else 0.0
        min_soc_frac = float(getattr(vehicle, "minimum_soc", 0.15)) if vehicle else 0.15
        minimum_soc_kwh = battery_kwh * min_soc_frac
        charge_rate_kw = float(getattr(vehicle, "charge_rate_kw", 0.0)) if vehicle else 0.0
        energy_cost_per_kwh = float(getattr(vehicle, "energy_cost_per_kwh", 0.0)) if vehicle else 0.0
        kwh_per_km = float(self._p("ev_kwh_per_km", _DEFAULT_EV_KWH_PER_KM))

        # CCT driving constraint (0 = disabled)
        max_driving_minutes = int(self._p("bp_max_driving_minutes", _DEFAULT_MAX_DRIVING_MINUTES))
        min_break_minutes = int(self._p("bp_min_break_minutes", _DEFAULT_MIN_BREAK_MINUTES))

        # Warm-start: greedy produz partição válida como colunas iniciais
        warm_start = GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id)
        if not warm_start.blocks:
            warm_start.meta["branch_and_price"] = {"fallback": "empty_warm_start"}
            return warm_start

        master = MasterProblemLP()
        trip_by_id = {t.id: t for t in trips}
        for block in warm_start.blocks:
            master.add_column([t.id for t in block.trips], fixed_cost)

        pricing = PricingSubproblem(
            trips=trips,
            fixed_cost=fixed_cost,
            deadhead_cost=deadhead_cost,
            idle_cost=idle_cost,
            min_layover=min_layover,
            max_vehicle_shift=max_vehicle_shift,
            max_labels_per_node=max_labels_per_node,
            is_ev=is_ev,
            battery_kwh=battery_kwh,
            minimum_soc_kwh=minimum_soc_kwh,
            charge_rate_kw=charge_rate_kw,
            energy_cost_per_kwh=energy_cost_per_kwh,
            kwh_per_km=kwh_per_km,
            max_driving_minutes=max_driving_minutes,
            min_break_minutes=min_break_minutes,
        )

        # Tempo reservado: 1/3 para LP rounds, 2/3 para MIP final
        total_budget = max(10, int(self.time_budget_s))
        lp_budget = max(5, total_budget // 3)
        mip_budget = total_budget - lp_budget
        lp_per_round = max(2, lp_budget // max(1, max_pricing_iters))

        pricing_rounds = 0
        new_cols_added = 0

        for _ in range(max_pricing_iters):
            if self._check_timeout():
                break
            master.solve_lp(time_limit=lp_per_round)
            duals = master.duals()
            new_cols = pricing.find_columns(duals, max_columns=max_pricing_cols)
            if not new_cols:
                break
            for trip_ids, cost in new_cols:
                master.add_column(trip_ids, cost)
            new_cols_added += len(new_cols)
            pricing_rounds += 1

        # MIP final sobre pool completo de colunas
        mip_obj = master.solve_mip(time_limit=mip_budget)
        selected = master.selected_columns()

        # F4: Ryan-Foster branching se LP fracionário após todos os rounds
        rf_used = False
        rf_pair: Optional[Tuple[int, int]] = None
        if not master.is_lp_integral() and not self._check_timeout():
            pair = master.ryan_foster_pair()
            if pair is not None:
                rf_pair = pair
                rf_budget = max(10, mip_budget // 2)
                all_trip_ids = {t.id for t in trips}
                rf_candidates: List[Tuple[int, float, List[int]]] = []

                for constraint_type in ("together", "apart"):
                    kw = dict(
                        together=pair if constraint_type == "together" else None,
                        apart=pair if constraint_type == "apart" else None,
                        time_limit=rf_budget,
                    )
                    obj_rf, sel_rf = master.solve_mip_with_constraints(**kw)
                    if not sel_rf:
                        continue
                    covered_rf = {tid for idx in sel_rf for tid in master.column_trips(idx)}
                    if all_trip_ids <= covered_rf:
                        rf_candidates.append((len(sel_rf), obj_rf, sel_rf))

                if rf_candidates:
                    # Menor blocos primeiro; desempate: menor custo
                    rf_candidates.sort(key=lambda r: (r[0], r[1]))
                    best_n, best_obj, best_sel = rf_candidates[0]
                    if (best_n, best_obj) < (len(selected), mip_obj):
                        selected = best_sel
                        mip_obj = best_obj
                        rf_used = True

        # Reconstrução: blocos a partir dos trip_ids selecionados
        rebuilt_blocks: List[Block] = []
        covered: set[int] = set()
        for idx in selected:
            col_trip_ids = master.column_trips(idx)
            col_trips = [trip_by_id[tid] for tid in col_trip_ids if tid in trip_by_id]
            if not col_trips:
                continue
            block = Block(id=len(rebuilt_blocks) + 1, trips=sorted(col_trips, key=lambda t: t.start_time))
            block.vehicle_type_id = vehicle.id if vehicle else None
            rebuilt_blocks.append(block)
            covered.update(col_trip_ids)

        unassigned = [t for t in trips if t.id not in covered]

        sol = VSPSolution(
            blocks=rebuilt_blocks,
            total_cost=mip_obj,
            unassigned_trips=unassigned,
            algorithm=self.name,
            warnings=list(warm_start.warnings),
        )
        sol.meta = {
            "branch_and_price": {
                "phase": "F4",
                "warm_start_algorithm": warm_start.algorithm,
                "warm_start_blocks": len(warm_start.blocks),
                "columns_seeded": len(warm_start.blocks),
                "columns_after_pricing": master.num_columns,
                "new_cols_from_pricing": new_cols_added,
                "pricing_rounds": pricing_rounds,
                "columns_selected": len(selected),
                "mip_objective": mip_obj,
                "mip_status": master._lp_status,
                "branching": rf_used,
                "rf_pair": list(rf_pair) if rf_pair else None,
                "ev_aware": is_ev,
                "cct_driving_constrained": max_driving_minutes > 0,
            }
        }
        return sol
