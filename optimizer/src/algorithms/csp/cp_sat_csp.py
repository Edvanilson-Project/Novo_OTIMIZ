"""
CSP Set Covering via OR-Tools CP-SAT.

Drop-in alternativa ao SetPartitioningCSP (PuLP/CBC).
Herda geração de colunas e pós-processamento; substitui só o solver ILP.

Por que CP-SAT bate CBC para scheduling:
- Propagação de restrições elimina ramos antes do branch-and-bound
- Heurísticas primais específicas para cobertura de conjuntos
- Paralelismo nativo (n workers por default)
- Sem overhead de marshaling Python→binário (API nativa Python)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ...domain.models import Block, CSPSolution, Duty, Trip
from .set_partitioning import SetPartitioningCSP

_log = logging.getLogger(__name__)

try:
    from ortools.sat.python import cp_model as _cp_model
    _CPSAT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CPSAT_AVAILABLE = False


# CP-SAT requer objetivos inteiros — escala custos floats para centavos
_COST_SCALE = 100


class CPSatCSP(SetPartitioningCSP):
    """Set covering CSP via OR-Tools CP-SAT. Mesma interface de SetPartitioningCSP."""

    def __init__(self, vsp_params: Optional[Dict[str, Any]] = None, **params: Any):
        super().__init__(vsp_params=vsp_params, **params)
        self.name = "cp_sat_csp"

    def solve(self, blocks: List[Block], trips: Optional[List[Trip]] = None) -> CSPSolution:
        if not _CPSAT_AVAILABLE:
            _log.warning("ortools não instalado — fallback para SetPartitioningCSP (PuLP/CBC)")
            self.name = "set_partitioning_csp"
            return super().solve(blocks, trips)

        self._start_timer()
        self.greedy.time_budget_s = max(1.0, float(self.time_budget_s))

        if not blocks:
            return CSPSolution(algorithm=self.name, meta={"roster_count": 0})

        tasks, run_cut_meta = self.greedy.prepare_tasks(blocks)
        if not tasks:
            return self.greedy.solve(blocks, trips)

        columns = self._generate_columns(tasks)
        task_ids = [task.id for task in tasks]
        time_limit = max(1, int(self.time_budget_s))

        # ── CP-SAT model ────────────────────────────────────────────────────
        model = _cp_model.CpModel()
        x = [model.NewBoolVar(f"x_{i}") for i in range(len(columns))]

        # Objetivo: minimizar custo total (custos escalados para inteiros)
        model.Minimize(sum(int(cost * _COST_SCALE) * x[i] for i, (_, cost) in enumerate(columns)))

        # Restrição: cada tarefa coberta por pelo menos 1 jornada
        task_id_set = {tid: set() for tid in task_ids}
        for i, (combo, _) in enumerate(columns):
            for block in combo:
                if block.id in task_id_set:
                    task_id_set[block.id].add(i)

        for task_id, covering_cols in task_id_set.items():
            if covering_cols:
                model.AddAtLeastOne([x[i] for i in covering_cols])
            else:
                _log.warning("Tarefa %s sem coluna cobertura — fallback greedy", task_id)
                return self.greedy.solve(blocks, trips)

        # ── Solver ──────────────────────────────────────────────────────────
        solver = _cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_search_workers = 4  # paralelismo CP-SAT
        solver.parameters.log_search_progress = False

        status = solver.Solve(model)

        if status not in (_cp_model.OPTIMAL, _cp_model.FEASIBLE):
            _log.warning("CP-SAT status: %s — fallback SetPartitioningCSP", solver.StatusName(status))
            self.name = "set_partitioning_csp_fallback"
            return super().solve(blocks, trips)

        # ── Extrair jornadas selecionadas ────────────────────────────────────
        duties: List[Duty] = []
        covered_tasks: set[int] = set()

        for i, var in enumerate(x):
            if not solver.BooleanValue(var):
                continue
            combo, _ = columns[i]
            duty = Duty(id=self._next_duty_id())
            for task in combo:
                if not duty.tasks:
                    self.greedy._apply_block(duty, task, {
                        "new_work": self.greedy._block_drive(task),
                        "new_spread": task.total_duration + self.greedy.pullout + self.greedy.pullback,
                        "new_cont": self.greedy._block_drive(task),
                        "daily_drive": self.greedy._block_drive(task),
                        "extended_days_used": 1 if self.greedy._block_drive(task) > self.greedy.daily_driving_limit else 0,
                    })
                else:
                    ok, _, data = self.greedy._can_extend(duty, task)
                    if not ok:
                        finalized = self.greedy.finalize_selected_duties([duty], original_blocks=blocks)
                        if finalized.duties:
                            duties.append(finalized.duties[0])
                        duty = Duty(id=self._next_duty_id())
                        self.greedy._apply_block(duty, task, {
                            "new_work": self.greedy._block_drive(task),
                            "new_spread": task.total_duration + self.greedy.pullout + self.greedy.pullback,
                            "new_cont": self.greedy._block_drive(task),
                            "daily_drive": self.greedy._block_drive(task),
                            "extended_days_used": 1 if self.greedy._block_drive(task) > self.greedy.daily_driving_limit else 0,
                        })
                    else:
                        self.greedy._apply_block(duty, task, data)
                covered_tasks.add(task.id)
            duties.append(duty)

        # Cobrir tarefas restantes não selecionadas
        for task in tasks:
            if task.id not in covered_tasks:
                duty = Duty(id=self._next_duty_id())
                self.greedy._apply_block(duty, task, {
                    "new_work": self.greedy._block_drive(task),
                    "new_spread": task.total_duration + self.greedy.pullout + self.greedy.pullback,
                    "new_cont": self.greedy._block_drive(task),
                    "daily_drive": self.greedy._block_drive(task),
                    "extended_days_used": 1 if self.greedy._block_drive(task) > self.greedy.daily_driving_limit else 0,
                })
                duties.append(duty)

        duties = self.greedy._merge_small_duties(duties)
        duties, relief_audit = self.greedy._relief_reassignment_postopt(duties, blocks)
        if relief_audit.get("accepted_moves"):
            duties = self.greedy._merge_small_duties(duties)
        duties, soft_audit = self.greedy._soft_issue_reassignment_postopt(duties, blocks)

        sol = self.greedy.finalize_selected_duties(duties, original_blocks=blocks)
        sol.algorithm = self.name
        sol.meta.update({
            "solver": "cp_sat",
            "cp_sat_status": solver.StatusName(status),
            "cp_sat_objective": solver.ObjectiveValue() / _COST_SCALE,
            "cp_sat_wall_time_s": round(solver.WallTime(), 3),
            "workpieces_generated": len(columns),
            "task_count": len(tasks),
            "relief_reassignment_audit": relief_audit,
            "soft_issue_reassignment_audit": soft_audit,
            **run_cut_meta,
        })
        return sol
