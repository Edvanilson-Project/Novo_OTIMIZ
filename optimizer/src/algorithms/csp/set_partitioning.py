"""
CSP por Set Covering / Column Generation simplificada.

Objetivo:
    min Σ_j c_j x_j
s.a.
    Σ_j a_ij x_j >= 1

As colunas são construídas sobre tarefas produzidas pelo run-cutting do CSP.
Assim, cada tarefa legalmente dirigível precisa ser coberta por pelo menos uma
jornada, aproximando melhor a formulação clássica de set covering.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ...core.config import get_settings

_log = logging.getLogger(__name__)
from ...domain.interfaces import ICSPAlgorithm
from ...domain.models import Block, CSPSolution, Duty, Trip
from ..base import BaseAlgorithm
from ..evaluator import _DEFAULT_CREW_COST_PER_HOUR
from .greedy import GreedyCSP

settings = get_settings()

try:
    import pulp  # type: ignore
    _PULP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PULP_AVAILABLE = False


class SetPartitioningCSP(BaseAlgorithm, ICSPAlgorithm):
    def __init__(self, vsp_params: Optional[Dict[str, Any]] = None, **params: Any):
        super().__init__(name="set_partitioning_csp", time_budget_s=settings.ilp_timeout_seconds)
        self.params = params
        self.vsp_params = vsp_params or {}
        self.greedy = GreedyCSP(vsp_params=vsp_params, **params)
        self.max_shift = self.greedy.max_shift
        self.min_piece = int(self.vsp_params.get("min_workpiece_minutes", 0))
        self.max_piece = int(self.vsp_params.get("max_workpiece_minutes", self.max_shift))
        self.min_trips_per_piece = int(self.vsp_params.get("min_trips_per_piece", 1))
        self.max_trips_per_piece = int(self.vsp_params.get("max_trips_per_piece", 4))
        self.goal_weights = dict(self.vsp_params.get("goal_weights") or params.get("goal_weights") or {})
        self.pricing_enabled = bool(self.vsp_params.get("pricing_enabled", True))
        self.max_candidate_successors = max(1, int(self.vsp_params.get("max_candidate_successors_per_task", 6)))
        self.max_columns = max(8, int(self.vsp_params.get("max_generated_columns", 6000)))
        self.max_pricing_iterations = max(0, int(self.vsp_params.get("max_pricing_iterations", 1 if self.pricing_enabled else 0)))
        self.max_pricing_additions = max(1, int(self.vsp_params.get("max_pricing_additions", 512)))

    def _task_neighbors(self, tasks: List[Block]) -> Dict[int, List[Block]]:
        ordered = sorted(tasks, key=lambda block: (block.start_time, block.id))
        neighbors: Dict[int, List[Block]] = {}
        for index, task in enumerate(ordered):
            feasible: List[Tuple[float, Block]] = []
            for nxt in ordered[index + 1 :]:
                if len(feasible) >= self.max_candidate_successors * 3:
                    break
                if nxt.start_time - task.end_time > self.greedy.max_shift:
                    break
                duty = Duty(id=0)
                self.greedy._apply_block(
                    duty,
                    task,
                    {
                        "new_work": self.greedy._block_drive(task),
                        "new_spread": task.total_duration + self.greedy.pullout + self.greedy.pullback,
                        "new_cont": self.greedy._block_drive(task),
                        "daily_drive": self.greedy._block_drive(task),
                        "extended_days_used": 1 if self.greedy._block_drive(task) > self.greedy.daily_driving_limit else 0,
                    },
                )
                ok, _, data = self.greedy._can_extend(duty, nxt)
                if not ok:
                    continue
                score = float(data.get("gap", 0)) + float(data.get("passive_transfer", 0)) * 5.0
                feasible.append((score, nxt))
            feasible.sort(key=lambda item: (item[0], item[1].start_time, item[1].id))
            neighbors[task.id] = [block for _, block in feasible[: self.max_candidate_successors]]
        return neighbors

    def _piece_cost(self, combo: Sequence[Block]) -> float:
        work = sum(self.greedy._block_drive(block) for block in combo)
        spread = self.greedy._duty_spread_minutes(combo)
        gaps = [max(0, combo[index + 1].start_time - combo[index].end_time) for index in range(len(combo) - 1)]
        passive = 0
        for index in range(len(combo) - 1):
            passive += max(0, self.greedy._transfer_needed(combo[index], combo[index + 1]) - self.greedy.min_layover)

        cost = 50.0 + work / 60.0 * _DEFAULT_CREW_COST_PER_HOUR + sum(gaps) * 0.1 + passive * self.goal_weights.get("passive_transfer", 0.25)
        target_work = max(self.greedy.min_work, min(self.greedy.max_work, int(self.goal_weights.get("target_work_minutes", self.greedy.max_work * 0.85))))
        target_spread = min(self.greedy.max_shift, int(self.goal_weights.get("target_spread_minutes", self.greedy.max_shift * 0.9)))
        overtime_dev = max(0, spread - self.greedy.max_work)
        underwork_dev = max(0, target_work - work)
        spread_dev = max(0, spread - target_spread)
        fairness_dev = abs(work - target_work)
        cost += overtime_dev * self.goal_weights.get("overtime", 0.8)
        cost += underwork_dev * self.goal_weights.get("min_work", 0.2)
        cost += spread_dev * self.goal_weights.get("spread", 0.15)
        cost += fairness_dev * self.goal_weights.get("fairness", 0.05)
        return cost

    def _feasible_combo(self, combo: Sequence[Block]) -> bool:
        duty = Duty(id=0)
        for block in combo:
            if not duty.tasks:
                self.greedy._apply_block(
                    duty,
                    block,
                    {
                        "new_work": self.greedy._block_drive(block),
                        "new_spread": block.total_duration + self.greedy.pullout + self.greedy.pullback,
                        "new_cont": self.greedy._block_drive(block),
                        "daily_drive": self.greedy._block_drive(block),
                        "extended_days_used": 1 if self.greedy._block_drive(block) > self.greedy.daily_driving_limit else 0,
                    },
                )
                continue
            ok, _, data = self.greedy._can_extend(duty, block)
            if not ok:
                return False
            self.greedy._apply_block(duty, block, data)
        work = sum(self.greedy._block_drive(block) for block in combo)
        return self.min_piece <= work <= self.max_piece

    def _generate_columns(self, tasks: List[Block]) -> List[Tuple[List[Block], float]]:
        ordered = sorted(tasks, key=lambda block: (block.start_time, block.id))
        neighbors = self._task_neighbors(ordered)
        columns: List[Tuple[List[Block], float]] = []
        seen: set[Tuple[int, ...]] = set()

        def register(combo: List[Block]) -> bool:
            signature = tuple(block.id for block in combo)
            if signature in seen:
                return False
            seen.add(signature)
            columns.append((list(combo), self._piece_cost(combo)))
            return len(columns) >= self.max_columns

        def explore(prefix: List[Block]) -> bool:
            if len(prefix) >= self.min_trips_per_piece:
                if register(prefix):
                    return True
            if len(prefix) >= self.max_trips_per_piece:
                return False
            tail = prefix[-1]
            for nxt in neighbors.get(tail.id, []):
                if nxt.id in {block.id for block in prefix}:
                    continue
                combo = [*prefix, nxt]
                if not self._feasible_combo(combo):
                    continue
                if explore(combo):
                    return True
            return False

        for task in ordered:
            if register([task]):
                break
            if self.max_trips_per_piece > 1 and explore([task]):
                break

        return columns or [([block], self._piece_cost([block])) for block in ordered]

    def _pricing(self, tasks: List[Block], columns: List[Tuple[List[Block], float]], duals: Dict[int, float]) -> List[Tuple[List[Block], float]]:
        existing = {tuple(block.id for block in combo) for combo, _ in columns}
        additions: List[Tuple[List[Block], float]] = []
        candidates = sorted(
            self._generate_columns(tasks),
            key=lambda item: item[1] - sum(duals.get(block.id, 0.0) for block in item[0]),
        )
        for combo, cost in candidates:
            signature = tuple(block.id for block in combo)
            if signature in existing:
                continue
            reduced = cost - sum(duals.get(block.id, 0.0) for block in combo)
            if reduced < -1e-5:
                additions.append((combo, cost))
                if len(additions) >= self.max_pricing_additions:
                    break
        return additions

    def solve(
        self,
        blocks: List[Block],
        trips: Optional[List[Trip]] = None,
    ) -> CSPSolution:
        self._start_timer()
        self.greedy.time_budget_s = max(1.0, float(self.time_budget_s))
        if not blocks:
            return CSPSolution(algorithm=self.name, meta={"roster_count": 0})
        if not _PULP_AVAILABLE:
            return self.greedy.solve(blocks, trips)

        tasks, run_cut_meta = self.greedy.prepare_tasks(blocks)
        if not tasks:
            return self.greedy.solve(blocks, trips)

        columns = self._generate_columns(tasks)
        task_ids = [task.id for task in tasks]

        pricing_rounds = self.max_pricing_iterations if self.pricing_enabled else 0
        total_time_limit_s = max(1, int(max(1.0, float(self.time_budget_s))))
        pricing_time_limit_s = max(1, min(total_time_limit_s, int(max(1.0, float(self.time_budget_s) / 3.0))))
        for _ in range(pricing_rounds):
            lp = pulp.LpProblem("CSP_Pricing", pulp.LpMinimize)
            y = [pulp.LpVariable(f"y_{index}", lowBound=0) for index in range(len(columns))]
            lp += pulp.lpSum(cost * y[index] for index, (_, cost) in enumerate(columns))
            for task_id in task_ids:
                lp += pulp.lpSum(y[index] for index, (combo, _) in enumerate(columns) if any(task.id == task_id for task in combo)) >= 1, f"cover_{task_id}"
            lp.solve(pulp.PULP_CBC_CMD(timeLimit=pricing_time_limit_s, msg=0, mip=False, keepFiles=False))
            duals = {
                task_id: float(lp.constraints[f"cover_{task_id}"].pi or 0.0)
                for task_id in task_ids
                if f"cover_{task_id}" in lp.constraints
            }
            additions = self._pricing(tasks, columns, duals)
            if not additions:
                break
            columns.extend(additions)
            if len(columns) >= self.max_columns:
                columns = columns[: self.max_columns]
                break

        prob = pulp.LpProblem("CSP_SetCovering", pulp.LpMinimize)
        x = [pulp.LpVariable(f"x_{index}", cat="Binary") for index in range(len(columns))]
        prob += pulp.lpSum(cost * x[index] for index, (_, cost) in enumerate(columns))
        for task_id in task_ids:
            prob += pulp.lpSum(x[index] for index, (combo, _) in enumerate(columns) if any(task.id == task_id for task in combo)) >= 1
        prob.solve(pulp.PULP_CBC_CMD(timeLimit=total_time_limit_s, msg=0, keepFiles=False))

        if prob.status != pulp.constants.LpStatusOptimal:
            _log.warning("ILP solver status: %s — falling back to greedy CSP", pulp.LpStatus[prob.status])
            fallback = self.greedy.solve(blocks, trips)
            fallback.meta["workpieces_generated"] = len(columns)
            fallback.meta["column_generation"] = {
                "max_generated_columns": self.max_columns,
                "fallback": True,
            }
            return fallback

        duties: List[Duty] = []
        covered_tasks: set[int] = set()
        for index, variable in enumerate(x):
            if float(pulp.value(variable) or 0.0) < 0.5:
                continue
            combo, _ = columns[index]
            duty = Duty(id=self._next_duty_id())
            for task in combo:
                if not duty.tasks:
                    self.greedy._apply_block(
                        duty,
                        task,
                        {
                            "new_work": self.greedy._block_drive(task),
                            "new_spread": task.total_duration + self.greedy.pullout + self.greedy.pullback,
                            "new_cont": self.greedy._block_drive(task),
                            "daily_drive": self.greedy._block_drive(task),
                            "extended_days_used": 1 if self.greedy._block_drive(task) > self.greedy.daily_driving_limit else 0,
                        },
                    )
                else:
                    ok, _, data = self.greedy._can_extend(duty, task)
                    if not ok:
                        finalized = self.greedy.finalize_selected_duties([duty], original_blocks=blocks).duties[0]
                        duties.append(finalized)
                        duty = Duty(id=self._next_duty_id())
                        self.greedy._apply_block(
                            duty,
                            task,
                            {
                                "new_work": self.greedy._block_drive(task),
                                "new_spread": task.total_duration + self.greedy.pullout + self.greedy.pullback,
                                "new_cont": self.greedy._block_drive(task),
                                "daily_drive": self.greedy._block_drive(task),
                                "extended_days_used": 1 if self.greedy._block_drive(task) > self.greedy.daily_driving_limit else 0,
                            },
                        )
                    else:
                        self.greedy._apply_block(duty, task, data)
                covered_tasks.add(task.id)
            duties.append(duty)

        for task in tasks:
            if task.id in covered_tasks:
                continue
            duty = Duty(id=self._next_duty_id())
            self.greedy._apply_block(
                duty,
                task,
                {
                    "new_work": self.greedy._block_drive(task),
                    "new_spread": task.total_duration + self.greedy.pullout + self.greedy.pullback,
                    "new_cont": self.greedy._block_drive(task),
                    "daily_drive": self.greedy._block_drive(task),
                    "extended_days_used": 1 if self.greedy._block_drive(task) > self.greedy.daily_driving_limit else 0,
                },
            )
            duties.append(duty)

        duties = self.greedy._merge_small_duties(duties)
        duties, relief_reassignment_audit = self.greedy._relief_reassignment_postopt(duties, blocks)
        if relief_reassignment_audit.get("accepted_moves"):
            duties = self.greedy._merge_small_duties(duties)

        sol = self.greedy.finalize_selected_duties(duties, original_blocks=blocks)
        sol.algorithm = self.name
        sol.meta.update(
            {
                "workpieces_generated": len(columns),
                "pricing_enabled": self.pricing_enabled,
                "objective": "min sum(c_j * x_j)",
                "task_count": len(tasks),
                "column_generation": {
                    "max_generated_columns": self.max_columns,
                    "max_candidate_successors_per_task": self.max_candidate_successors,
                    "max_pricing_iterations": self.max_pricing_iterations,
                    "max_pricing_additions": self.max_pricing_additions,
                    "truncated": len(columns) >= self.max_columns,
                },
                "goal_programming": {
                    "deviations": ["overtime", "underwork", "spread", "fairness", "passive_transfer"],
                    "weights": self.goal_weights,
                },
                "duty_merge_diagnostics": self.greedy._extension_diagnostics_snapshot(),
                "relief_reassignment_audit": relief_reassignment_audit,
                **run_cut_meta,
            }
        )
        return sol
