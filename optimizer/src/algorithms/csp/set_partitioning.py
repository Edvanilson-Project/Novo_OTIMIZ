"""
CSP por Set Partitioning (Exact Cover) / Column Generation simplificada.

Objetivo:
    min Σ_j c_j x_j
s.a.
    Σ_j a_ij x_j == 1   (cada tarefa em EXATAMENTE uma jornada)

Por que ==1 e não >=1: covering permite a mesma tarefa em múltiplas jornadas
selecionadas, gerando duplicação e MANDATORY_GROUP_SPLIT no validator.

Nota: a fase de pricing usa relaxação LP com >=1 apenas para extrair duais π_i
para o SPPRC; o MILP final aplica ==1 (com slack penalizado por BIG_M).
"""

from __future__ import annotations

import logging
from decimal import Decimal
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


def _make_solver(time_limit: int, threads: int = 1) -> "pulp.LpSolver":
    """CBC (primary for binary MIP) with HiGHS as fallback if CBC unavailable."""
    cbc = pulp.PULP_CBC_CMD(timeLimit=time_limit, msg=0, keepFiles=False, threads=threads)
    if cbc.available():
        return cbc
    try:
        return pulp.HiGHS(timeLimit=time_limit, msg=0, threads=threads)
    except Exception:
        return cbc


class SetPartitioningCSP(BaseAlgorithm, ICSPAlgorithm):
    def __init__(self, vsp_params: Optional[Dict[str, Any]] = None, **params: Any):
        # Prioritize ilp_timeout_seconds from params, then vsp_params, then global settings
        timeout = params.get(
            "ilp_timeout_seconds", (vsp_params or {}).get("ilp_timeout_seconds", settings.ilp_timeout_seconds)
        )
        super().__init__(name="set_partitioning_csp", time_budget_s=timeout)
        self.params = params
        self.vsp_params = vsp_params or {}
        self.greedy = GreedyCSP(vsp_params=vsp_params, **params)
        self.max_shift = self.greedy.max_shift
        self.min_piece = int(self.vsp_params.get("min_workpiece_minutes", 0))
        self.max_piece = int(self.vsp_params.get("max_workpiece_minutes", self.max_shift))
        self.min_trips_per_piece = int(self.vsp_params.get("min_trips_per_piece", 1))
        self.max_trips_per_piece = int(self.vsp_params.get("max_trips_per_piece", 4))
        self.goal_weights = dict(self.vsp_params.get("goal_weights") or params.get("goal_weights") or {})
        pricing_default = bool(self.vsp_params.get("enable_column_generation", True))
        self.pricing_enabled = bool(self.vsp_params.get("pricing_enabled", pricing_default))
        self.max_candidate_successors = max(1, int(self.vsp_params.get("max_candidate_successors_per_task", 6)))
        self.max_columns = max(8, int(self.vsp_params.get("max_generated_columns", 6000)))
        self.max_pricing_iterations = max(
            # BUG-SP-01 fix: default era 1 — CG não convergia com 1 iter.
            # Agora default=3 (compromisso: converge na maioria dos casos, sem overhead excessivo).
            # A versão otimizada (set_partitioning_optimized.py) usa SPPRC completo e tem 5 iter.
            0, int(self.vsp_params.get("max_pricing_iterations", 3 if self.pricing_enabled else 0))
        )
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
                        "extended_days_used": (
                            1 if self.greedy._block_drive(task) > self.greedy.daily_driving_limit else 0
                        ),
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

        # Converter tudo para Decimal
        work_dec = Decimal(str(work))
        spread_dec = Decimal(str(spread))  # BUG-SP-02 fix: era descartado (dead code), agora usado
        gaps_sum = Decimal(str(sum(gaps)))
        passive_dec = Decimal(str(passive))

        # Custos base
        cost = Decimal(str(getattr(self.greedy, "cost_duty", 50.0)))  # custo fixo por jornada dinâmico
        cost += (work_dec / Decimal("60.0")) * Decimal(str(_DEFAULT_CREW_COST_PER_HOUR))
        cost += gaps_sum * Decimal("0.1")
        cost += passive_dec * Decimal(str(self.goal_weights.get("passive_transfer", 0.25)))

        # BUG-SP-COST fix: O ILP gerava MAIS duties (70) que o Greedy (63) porque
        # target_work = 85% de max_work penalizava duties longos com underwork+fairness.
        # Resultado: ILP preferia 70 duties curtos a 63 duties longos.
        # Fix: target_work = 95% de max_work para permitir duties mais próximos do limite.
        # Penalidades de underwork e fairness reduzidas significativamente.
        target_work = max(
            self.greedy.min_work,
            min(self.greedy.max_work, int(self.goal_weights.get("target_work_minutes", self.greedy.max_work * 0.95))),
        )
        target_spread = min(
            self.greedy.max_shift, int(self.goal_weights.get("target_spread_minutes", self.greedy.max_shift * 0.95))
        )

        overtime_dev = max(0, work - self.greedy.max_work)
        underwork_dev = max(0, target_work - work)
        spread_dev = max(0, spread - target_spread)
        fairness_dev = abs(work - target_work)

        # Converter desvios para Decimal
        overtime_dev_dec = Decimal(str(overtime_dev))
        underwork_dev_dec = Decimal(str(underwork_dev))
        spread_dev_dec = Decimal(str(spread_dev))
        fairness_dev_dec = Decimal(str(fairness_dev))

        # Adicionar penalidades de desvio
        # BUG-SP-COST fix: reduzir underwork e fairness para não fragmentar duties
        cost += overtime_dev_dec * Decimal(str(self.goal_weights.get("overtime", 1.2)))
        cost += underwork_dev_dec * Decimal(str(self.goal_weights.get("min_work", 0.05)))
        cost += spread_dev_dec * Decimal(str(self.goal_weights.get("spread", 0.05)))
        cost += fairness_dev_dec * Decimal(str(self.goal_weights.get("fairness", 0.01)))

        return float(cost)

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
                        "extended_days_used": (
                            1 if self.greedy._block_drive(block) > self.greedy.daily_driving_limit else 0
                        ),
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

    def _pricing(
        self, tasks: List[Block], columns: List[Tuple[List[Block], float]], duals: Dict[int, float]
    ) -> List[Tuple[List[Block], float]]:
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
                lp += (
                    pulp.lpSum(
                        y[index]
                        for index, (combo, _) in enumerate(columns)
                        if any(task.id == task_id for task in combo)
                    )
                    >= 1,
                    f"cover_{task_id}",
                )
            lp.solve(_make_solver(pricing_time_limit_s, threads=settings.ilp_threads))
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

        # Garantia pós-pricing: o MILP (==1) só é factível se toda task tiver
        # ao menos uma coluna UNITÁRIA (single-task).
        # - _generate_columns trunca em max_columns antes de gerar unit cols para todas
        # - o loop de pricing pode re-truncar para max_columns depois
        # - tasks em colunas multi-task mas sem unit col própria podem tornar
        #   a partição exata impossível (sem escape para o solver)
        # Adicionamos unit cols para tasks sem uma; contadas separadamente
        # para não distorcer workpieces_generated (que reflete o limite configurado).
        unit_cols_added = 0
        single_task_ids = {combo[0].id for combo, _ in columns if len(combo) == 1}
        for task in tasks:
            if task.id not in single_task_ids:
                columns.append(([task], self._piece_cost([task])))
                unit_cols_added += 1
                _log.debug("Coluna unitária adicionada para task %s (sem coluna unitária na pool)", task.id)

        prob = pulp.LpProblem("CSP_SetPartitioning", pulp.LpMinimize)
        x = [pulp.LpVariable(f"x_{index}", cat="Binary") for index in range(len(columns))]
        prob += pulp.lpSum(cost * x[index] for index, (_, cost) in enumerate(columns))
        # Partition (==1): cada task em exatamente uma jornada. Antes era covering
        # (>=1) que permitia duties sobrepostas, gerando MANDATORY_GROUP_SPLIT no
        # validador (mesma trip em múltiplos rosters). Partition é semântica correta.
        for task_id in task_ids:
            prob += (
                pulp.lpSum(
                    x[index] for index, (combo, _) in enumerate(columns) if any(task.id == task_id for task in combo)
                )
                == 1
            )
        prob.solve(_make_solver(total_time_limit_s, threads=settings.ilp_threads))

        if prob.status != pulp.constants.LpStatusOptimal:
            _log.warning("ILP solver status: %s — falling back to greedy CSP", pulp.LpStatus[prob.status])
            fallback = self.greedy.solve(blocks, trips)
            fallback.meta["workpieces_generated"] = len(columns) - unit_cols_added
            fallback.meta["unit_columns_for_coverage"] = unit_cols_added
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
                            "extended_days_used": (
                                1 if self.greedy._block_drive(task) > self.greedy.daily_driving_limit else 0
                            ),
                        },
                    )
                else:
                    ok, _, data = self.greedy._can_extend(duty, task)
                    if not ok:
                        finalized_sol = self.greedy.finalize_selected_duties([duty], original_blocks=blocks)
                        if finalized_sol.duties:
                            duties.append(finalized_sol.duties[0])
                        duty = Duty(id=self._next_duty_id())
                        self.greedy._apply_block(
                            duty,
                            task,
                            {
                                "new_work": self.greedy._block_drive(task),
                                "new_spread": task.total_duration + self.greedy.pullout + self.greedy.pullback,
                                "new_cont": self.greedy._block_drive(task),
                                "daily_drive": self.greedy._block_drive(task),
                                "extended_days_used": (
                                    1 if self.greedy._block_drive(task) > self.greedy.daily_driving_limit else 0
                                ),
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
        duties, soft_issue_reassignment_audit = self.greedy._soft_issue_reassignment_postopt(duties, blocks)

        sol = self.greedy.finalize_selected_duties(duties, original_blocks=blocks)
        sol.algorithm = self.name
        sol.meta.update(
            {
                "workpieces_generated": len(columns) - unit_cols_added,
                "unit_columns_for_coverage": unit_cols_added,
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
                "soft_issue_reassignment_audit": soft_issue_reassignment_audit,
                **run_cut_meta,
            }
        )
        return sol
