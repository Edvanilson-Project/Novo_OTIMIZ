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

from ...core.config import get_settings
from ...domain.models import Block, CSPSolution, Duty, Trip
from .set_partitioning import SetPartitioningCSP

_log = logging.getLogger(__name__)
settings = get_settings()

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

        # Garante cobertura mínima: se alguma tarefa não está coberta, cria coluna unitária para ela
        # Isso evita que o solver falhe com cobertura e caia em fallback greedy desnecessário.
        covered_tasks = set()
        for combo, _ in columns:
            for block in combo:
                covered_tasks.add(block.id)

        for task in tasks:
            if task.id not in covered_tasks:
                columns.append(([task], self._piece_cost([task])))
                _log.debug("Adicionada coluna unitária para tarefa %s não coberta", task.id)

        task_ids = [task.id for task in tasks]
        # BUG-CPSAT-02 fix: max_time_in_seconds aceita float — não truncar para int.
        # int(1.8s) = 1s (perda de 44% do budget para budgets pequenos).
        time_limit = max(1.0, float(self.time_budget_s))

        # ── CP-SAT model ────────────────────────────────────────────────────
        model = _cp_model.CpModel()
        x = [model.NewBoolVar(f"x_{i}") for i in range(len(columns))]

        # Objetivo: minimizar custo total (custos escalados para inteiros)
        # Adicionamos variáveis slack penalizadas com BIG_M para evitar infactibilidade.
        _max_col_cost = max((cost for _, cost in columns), default=100.0)
        BIG_M = max(_max_col_cost * len(task_ids) + 1.0, 1000.0)

        s = {tid: model.NewBoolVar(f"s_{tid}") for tid in task_ids}

        model.Minimize(
            sum(int(cost * _COST_SCALE) * x[i] for i, (_, cost) in enumerate(columns))
            + sum(int(BIG_M * _COST_SCALE) * s[tid] for tid in task_ids)
        )

        # Restrição: cada tarefa coberta por EXATAMENTE 1 jornada (Set Partitioning)
        # Usamos AddExactlyOne que inclui as variáveis da coluna e a variável slack, garantindo que
        # ou exatamente uma coluna cobre a tarefa, ou a variável slack correspondente é ativada.
        task_id_set = {tid: set() for tid in task_ids}
        for i, (combo, _) in enumerate(columns):
            for block in combo:
                if block.id in task_id_set:
                    task_id_set[block.id].add(i)

        for task_id, covering_cols in task_id_set.items():
            model.AddExactlyOne([x[i] for i in covering_cols] + [s[task_id]])

        # ── Solver ──────────────────────────────────────────────────────────
        import os as _os
        solver = _cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        # BUG-CSP-03 fix: usar settings.ilp_threads (configurável) em vez de hardcoded 4.
        # Fallback para cpu_count com cap em 8 (evita sobrecarregar containers).
        _cpus = min(settings.ilp_threads or _os.cpu_count() or 4, 8)
        solver.parameters.num_search_workers = _cpus
        solver.parameters.log_search_progress = False

        status = solver.Solve(model)

        if status not in (_cp_model.OPTIMAL, _cp_model.FEASIBLE):
            _log.warning("CP-SAT status: %s — fallback SetPartitioningCSP", solver.StatusName(status))
            self.name = "set_partitioning_csp_fallback"
            return super().solve(blocks, trips)

        # Verifica se slack foi ativado — se sim, fallback para CBC (melhor qualidade)
        slack_activated = any(solver.BooleanValue(s[tid]) for tid in task_ids)
        if slack_activated:
            _log.warning("CP-SAT usou variáveis slack — fallback SetPartitioningCSP (CBC)")
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
                        finalized = self.greedy.finalize_selected_duties([duty], original_blocks=blocks)
                        if finalized.duties:
                            duties.append(finalized.duties[0])
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

        # Cobrir tarefas restantes não selecionadas
        for task in tasks:
            if task.id not in covered_tasks:
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
                duties.append(duty)

        duties = self.greedy._merge_small_duties(duties)
        duties, relief_audit = self.greedy._relief_reassignment_postopt(duties, blocks)
        if relief_audit.get("accepted_moves"):
            duties = self.greedy._merge_small_duties(duties)
        duties, soft_audit = self.greedy._soft_issue_reassignment_postopt(duties, blocks)

        sol = self.greedy.finalize_selected_duties(duties, original_blocks=blocks)
        sol.algorithm = self.name
        sol.meta.update(
            {
                "solver": "cp_sat",
                "cp_sat_status": solver.StatusName(status),
                "cp_sat_objective": solver.ObjectiveValue() / _COST_SCALE,
                "cp_sat_wall_time_s": round(solver.WallTime(), 3),
                "workpieces_generated": len(columns),
                "task_count": len(tasks),
                "relief_reassignment_audit": relief_audit,
                "soft_issue_reassignment_audit": soft_audit,
                **run_cut_meta,
            }
        )
        return sol
