"""
Joint Timetable + Vehicle Scheduling Optimization (MILP).

Diferente do TimetableSlack atual (pós-processamento heurístico), aqui as
trip start_times são VARIÁVEIS DE DECISÃO dentro do MILP, otimizadas
conjuntamente com a alocação de veículos.

Referências:
  [1] Schmid V., Ehmke J. (2015) "Integrated timetabling and vehicle scheduling
      with periodicity constraints", Transportation Research B 75:32-49.
  [2] Hindawi (2019) "Vehicle scheduling on variable timetable":
      https://www.hindawi.com/journals/jat/2019/2781590/
  [3] Wang et al. (2024) "Integrated timetable + vehicle scheduling for
      electric buses with variable transfer time thresholds", TRR 03611981251350647.

FORMULAÇÃO:
    Variáveis:
      x_ij ∈ {0,1}: trip i seguido por trip j no mesmo veículo
      s_i ∈ [s_i^orig - W, s_i^orig + W]: start time ajustável (W = slack)
      v_k ∈ {0,1}: vehicle k activated
      δ_i ∈ [0, 2W]: |s_i - s_i^orig| (perturbação)

    Restrições:
      Σ_j x_ji + Σ_k inflow_k(i) = 1     ∀i (cobertura)
      Σ_j x_ij + Σ_k outflow_k(i) = 1    ∀i (cobertura)
      s_j - (s_i + duration_i) ≥ deadhead_ij - M(1 - x_ij)    ∀i,j (precedência)
      δ_i ≥ s_i - s_i^orig                ∀i
      δ_i ≥ s_i^orig - s_i                ∀i

    Objetivo:
      min  Σ_k FIXED * v_k + Σ_ij deadhead_cost * x_ij + Σ_i timetable_penalty * δ_i

ESCALABILIDADE:
    MILP completo: ~N² variables binárias + N continuous. Tractable até ~150 trips.
    Acima: usa TimetableSlackOptimizer pós-processamento (existente).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from ...core.config import get_settings
from ...domain.interfaces import IVSPAlgorithm
from ...domain.models import Block, Trip, VehicleType, VSPSolution
from ..base import BaseAlgorithm
from ..utils import is_connection_feasible, select_vehicle_type

_log = logging.getLogger(__name__)
settings = get_settings()

try:
    import pulp  # type: ignore

    _PULP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PULP_AVAILABLE = False


_DEFAULT_SLACK_MINUTES = 10
_DEFAULT_TIMETABLE_PENALTY = 2.0  # custo por minuto de ajuste
_DEFAULT_MILP_TIMEOUT = 60
_MAX_TRIPS_MILP = 150


class JointTimetableVSP(BaseAlgorithm, IVSPAlgorithm):
    """Joint optimization of timetable shifts + vehicle assignment via MILP.

    Args (via vsp_params):
        timetable_slack_minutes: ±W janela permitida para ajuste (default 10)
        timetable_penalty_per_minute: custo de cada minuto de ajuste (default 2.0)
        joint_timetable_milp_timeout: timeout do solver (default 60s)
    """

    def __init__(self, vsp_params: Optional[Dict[str, Any]] = None):
        super().__init__(name="joint_timetable_vsp", time_budget_s=120.0)
        self.vsp_params = vsp_params or {}

    def _p(self, key: str, default: Any) -> Any:
        return self.vsp_params.get(key, default)

    def solve(
        self,
        trips: List[Trip],
        vehicle_types: List[VehicleType],
        depot_id: Optional[int] = None,
    ) -> VSPSolution:
        self._start_timer()
        if not trips:
            return VSPSolution(algorithm=self.name)

        n = len(trips)
        if n > _MAX_TRIPS_MILP:
            _log.warning(
                "[JOINT-TT] %d trips excede %d → fallback para GreedyVSP",
                n,
                _MAX_TRIPS_MILP,
            )
            from .greedy import GreedyVSP

            sol = GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id)
            sol.meta = sol.meta or {}
            sol.meta["joint_timetable_skipped"] = "instance_too_large"
            return sol

        if not _PULP_AVAILABLE:
            _log.warning("[JOINT-TT] PuLP indisponível → fallback para GreedyVSP")
            from .greedy import GreedyVSP

            return GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id)

        slack = int(self._p("timetable_slack_minutes", _DEFAULT_SLACK_MINUTES))
        penalty = float(self._p("timetable_penalty_per_minute", _DEFAULT_TIMETABLE_PENALTY))
        milp_timeout = int(self._p("joint_timetable_milp_timeout", _DEFAULT_MILP_TIMEOUT))
        min_layover = int(self._p("min_layover_minutes", 8))
        fixed_cost = float(
            self._p(
                "fixed_vehicle_activation_cost",
                vehicle_types[0].fixed_cost if vehicle_types else 900.0,
            )
        )
        deadhead_cost = float(self._p("deadhead_cost_per_minute", 1.0))

        trips_sorted = sorted(trips, key=lambda t: (t.start_time, t.id))
        trip_idx = {int(t.id): i for i, t in enumerate(trips_sorted)}
        BIG_M = 10 * (max(t.end_time for t in trips_sorted) + slack)

        # ── MILP ───────────────────────────────────────────────────────────
        prob = pulp.LpProblem("JointTimetableVSP", pulp.LpMinimize)

        # x_ij = 1 se trip j segue i no mesmo veículo
        x: Dict[Tuple[int, int], Any] = {}
        # candidatos: pares (i,j) onde gap permite conexão dentro do slack
        candidates: List[Tuple[int, int]] = []
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                gap_min = (trips_sorted[j].start_time - slack) - (
                    trips_sorted[i].end_time + slack
                )
                if gap_min > BIG_M:
                    continue
                # Verifica se é potencialmente factível
                # BUG-JT-01 fix: parênteses corrigidos na aritmética de filtro
                if (
                    (trips_sorted[j].start_time + slack)
                    - (trips_sorted[i].end_time - slack)
                    < min_layover
                ):
                    continue
                candidates.append((i, j))
                x[(i, j)] = pulp.LpVariable(f"x_{i}_{j}", cat="Binary")

        # s_i = start time (continuous, dentro de slack)
        s = {
            i: pulp.LpVariable(
                f"s_{i}",
                lowBound=trips_sorted[i].start_time - slack,
                upBound=trips_sorted[i].start_time + slack,
            )
            for i in range(n)
        }

        # δ_i = perturbação absoluta
        delta = {
            i: pulp.LpVariable(f"delta_{i}", lowBound=0, upBound=slack)
            for i in range(n)
        }

        # Activation de "novo veículo começa" (in-flow virtual de depot)
        pull_out = {
            i: pulp.LpVariable(f"pout_{i}", cat="Binary") for i in range(n)
        }
        pull_in = {
            i: pulp.LpVariable(f"pin_{i}", cat="Binary") for i in range(n)
        }

        # Objetivo: fixed_cost * pull-outs + deadhead + penalidades
        obj_terms = []
        for i in range(n):
            obj_terms.append(fixed_cost * pull_out[i])
            obj_terms.append(penalty * delta[i])
        for (i, j), var in x.items():
            dh = max(
                min_layover,
                int(trips_sorted[i].deadhead_times.get(trips_sorted[j].origin_id, 0)),
            )
            obj_terms.append(deadhead_cost * dh * var)
        prob += pulp.lpSum(obj_terms)

        # Cobertura: in-degree = 1
        for j in range(n):
            in_terms = [x[(i, j)] for i in range(n) if (i, j) in x]
            in_terms.append(pull_out[j])
            prob += pulp.lpSum(in_terms) == 1, f"in_{j}"

        # Cobertura: out-degree = 1
        for i in range(n):
            out_terms = [x[(i, j)] for j in range(n) if (i, j) in x]
            out_terms.append(pull_in[i])
            prob += pulp.lpSum(out_terms) == 1, f"out_{i}"

        # Precedência temporal: se x_ij=1, então s_j ≥ s_i + dur_i + deadhead_ij
        for (i, j), var in x.items():
            dh = max(
                min_layover,
                int(trips_sorted[i].deadhead_times.get(trips_sorted[j].origin_id, 0)),
            )
            duration_i = trips_sorted[i].end_time - trips_sorted[i].start_time
            prob += (
                s[j] - s[i] - duration_i - dh + BIG_M * (1 - var) >= 0,
                f"prec_{i}_{j}",
            )

        # δ_i ≥ |s_i - s_i^orig|
        for i in range(n):
            prob += delta[i] >= s[i] - trips_sorted[i].start_time, f"delta_pos_{i}"
            prob += delta[i] >= trips_sorted[i].start_time - s[i], f"delta_neg_{i}"

        # Solve
        solver = pulp.PULP_CBC_CMD(timeLimit=milp_timeout, msg=0, threads=settings.ilp_threads)
        milp_t0 = time.time()
        try:
            prob.solve(solver)
        except Exception as exc:
            _log.exception("[JOINT-TT] solver crashed: %s", exc)
            from .greedy import GreedyVSP

            sol = GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id)
            sol.meta = sol.meta or {}
            sol.meta["joint_timetable_failed"] = str(exc)
            return sol
        milp_elapsed = time.time() - milp_t0

        status = pulp.LpStatus[prob.status]
        if prob.status != pulp.constants.LpStatusOptimal:
            _log.warning("[JOINT-TT] MILP status=%s → fallback", status)
            from .greedy import GreedyVSP

            sol = GreedyVSP(vsp_params=self.vsp_params).solve(trips, vehicle_types, depot_id)
            sol.meta = sol.meta or {}
            sol.meta["fallback_used"] = True
            sol.meta["fallback_reason"] = status
            sol.meta["original_solver"] = self.name
            sol.meta["fallback_solver"] = "greedy_vsp"
            return sol

        # ── Reconstroi solução ────────────────────────────────────────────
        # 1. Aplica timetable shifts às trips (cópia)
        adjusted_trips: Dict[int, Trip] = {}
        total_adjustment = 0.0
        n_adjusted = 0
        for i in range(n):
            s_val = int(round(pulp.value(s[i])))
            orig = trips_sorted[i].start_time
            adjustment = s_val - orig
            if adjustment != 0:
                n_adjusted += 1
                total_adjustment += abs(adjustment)
            # Cópia com novo start/end
            new_trip = Trip(
                id=trips_sorted[i].id,
                line_id=trips_sorted[i].line_id,
                start_time=s_val,
                end_time=s_val + (trips_sorted[i].end_time - trips_sorted[i].start_time),
                origin_id=trips_sorted[i].origin_id,
                destination_id=trips_sorted[i].destination_id,
                duration=trips_sorted[i].end_time - trips_sorted[i].start_time,
                distance_km=trips_sorted[i].distance_km,
                depot_id=trips_sorted[i].depot_id,
                deadhead_times=dict(trips_sorted[i].deadhead_times),
                trip_group_id=trips_sorted[i].trip_group_id,
                direction=trips_sorted[i].direction,
                energy_kwh=trips_sorted[i].energy_kwh,
            )
            adjusted_trips[i] = new_trip

        # 2. Reconstrói cadeias via x_ij
        next_trip: Dict[int, int] = {}
        prev_trip: Dict[int, int] = {}
        for (i, j), var in x.items():
            if pulp.value(var) is not None and pulp.value(var) > 0.5:
                next_trip[i] = j
                prev_trip[j] = i

        vt = select_vehicle_type(vehicle_types)
        blocks: List[Block] = []
        visited = set()
        block_id = 1

        for start_idx in range(n):
            if start_idx in visited or start_idx in prev_trip:
                continue
            chain_idxs = []
            curr = start_idx
            while curr is not None and curr not in visited:
                chain_idxs.append(curr)
                visited.add(curr)
                curr = next_trip.get(curr)
            chain_trips = [adjusted_trips[idx] for idx in chain_idxs]
            block = Block(
                id=block_id,
                trips=chain_trips,
                vehicle_type_id=vt.id if vt else None,
            )
            block.meta["joint_timetable_chain"] = True
            blocks.append(block)
            block_id += 1

        elapsed_ms = self._elapsed_ms()
        return VSPSolution(
            blocks=blocks,
            unassigned_trips=[],
            algorithm=self.name,
            elapsed_ms=elapsed_ms,
            meta={
                "joint_timetable_milp_status": status,
                "joint_timetable_milp_solve_s": round(milp_elapsed, 3),
                "joint_timetable_objective": round(float(pulp.value(prob.objective) or 0.0), 2),
                "joint_timetable_trips_adjusted": n_adjusted,
                "joint_timetable_total_adjustment_minutes": int(total_adjustment),
                "joint_timetable_avg_adjustment_minutes": round(
                    total_adjustment / max(1, n_adjusted), 2
                ),
                "joint_timetable_slack_window": slack,
            },
        )
