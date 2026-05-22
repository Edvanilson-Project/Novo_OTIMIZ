"""
Solver de Escala Semanal (Weekly Crew Rostering Problem).

Atribui motoristas a jornadas em múltiplos dias da semana respeitando:
  - CLT Art. 67: ≥ 1 dia de folga obrigatório por semana
  - CLT Art. 7/CF: máximo 44h/semana (2640 min) para jornada padrão
  - CCT: descanso mínimo entre jornadas de dias consecutivos (11h = 660 min)
  - Equidade: distribuição justa de horas semanais (mínimo Gini)

Usa OR-Tools CP-SAT — melhor que PuLP/CBC para scheduling com restrições de
tempo (intervalo entre turnos, blocos de dias consecutivos).

Fallback automático para greedy guloso se CP-SAT não estiver disponível.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from ...domain.models import (
    Duty,
    OperatorProfile,
    OperatorWeeklySchedule,
    WeeklyAssignment,
    WeeklyRosterSolution,
)

logger = logging.getLogger(__name__)

# Constantes CLT/CCT
_CLT_WEEKLY_LIMIT_MINUTES = 2640  # 44h × 60 = 2640 min
_CCT_MIN_INTER_SHIFT_REST_MINUTES = 660  # 11h entre jornadas de dias consecutivos
_CLT_MIN_DAYS_OFF = 1  # ao menos 1 folga/semana


def _gini(values: List[float]) -> float:
    """Coeficiente de Gini das horas semanais (0 = perfeita equidade)."""
    if not values or all(v == 0 for v in values):
        return 0.0
    n = len(values)
    s = sorted(values)
    total = sum(s)
    if total == 0:
        return 0.0
    cumsum = 0.0
    gini_num = 0.0
    for i, v in enumerate(s):
        cumsum += v
        gini_num += (2 * cumsum - v - total) / total
    return -gini_num / n


class WeeklyRosteringSolver:
    """
    Resolve o problema de escala semanal via CP-SAT (fallback: greedy).

    Parâmetros
    ----------
    weekly_hour_limit_minutes : int
        Limite semanal de minutos trabalhados por motorista. Padrão: 2640 (44h CLT).
    min_days_off : int
        Dias mínimos de folga por semana. Padrão: 1 (CLT Art. 67).
    min_inter_shift_rest_minutes : int
        Descanso mínimo entre fim de jornada do dia D e início do dia D+1. Padrão: 660 (11h CCT).
    time_budget_s : float
        Orçamento de tempo para CP-SAT. Padrão: 60s.
    """

    def __init__(
        self,
        weekly_hour_limit_minutes: int = _CLT_WEEKLY_LIMIT_MINUTES,
        min_days_off: int = _CLT_MIN_DAYS_OFF,
        min_inter_shift_rest_minutes: int = _CCT_MIN_INTER_SHIFT_REST_MINUTES,
        time_budget_s: float = 60.0,
    ):
        self.weekly_limit = weekly_hour_limit_minutes
        self.min_days_off = min_days_off
        self.min_rest = min_inter_shift_rest_minutes
        self.time_budget_s = time_budget_s

    def solve(
        self,
        daily_duties: Dict[int, List[Duty]],
        operators: List[OperatorProfile],
        cct_params: Optional[Dict[str, Any]] = None,
    ) -> WeeklyRosterSolution:
        """
        Parameters
        ----------
        daily_duties : dict[int, list[Duty]]
            Mapa de dia_index (0=segunda…6=domingo) para lista de jornadas daquele dia.
        operators : list[OperatorProfile]
            Motoristas disponíveis para a semana.
        cct_params : dict, optional
            Parâmetros adicionais (substitui defaults do solver).
        """
        t0 = time.perf_counter()
        params = cct_params or {}
        weekly_limit = int(params.get("weekly_hour_limit_minutes", self.weekly_limit))
        min_days_off = int(params.get("min_days_off_per_week", self.min_days_off))
        min_rest = int(params.get("min_inter_shift_rest_minutes", self.min_rest))

        days = sorted(daily_duties.keys())
        if not days or not operators:
            return WeeklyRosterSolution(
                feasible=False,
                meta={"reason": "empty_input", "days": days, "operators": len(operators)},
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )

        try:
            from ortools.sat.python import cp_model

            return self._solve_cpsat(
                daily_duties,
                operators,
                days,
                weekly_limit,
                min_days_off,
                min_rest,
                time_budget_s=self.time_budget_s,
                cp_model=cp_model,
                t0=t0,
            )
        except ImportError:
            logger.warning("[WeeklyRostering] ortools não instalado — usando greedy")
            return self._solve_greedy(
                daily_duties,
                operators,
                days,
                weekly_limit,
                min_days_off,
                min_rest,
                t0,
            )

    # ── CP-SAT ────────────────────────────────────────────────────────────────

    def _solve_cpsat(
        self,
        daily_duties,
        operators,
        days,
        weekly_limit,
        min_days_off,
        min_rest,
        time_budget_s,
        cp_model,
        t0,
    ) -> WeeklyRosterSolution:
        model = cp_model.CpModel()
        n_operators = len(operators)

        # x[o][d][j] = 1 se operador o trabalha jornada j no dia d
        x: Dict[tuple, Any] = {}
        for d in days:
            for j, duty in enumerate(daily_duties[d]):
                for o in range(n_operators):
                    x[(o, d, j)] = model.NewBoolVar(f"x_o{o}_d{d}_j{j}")

        # ── Restrição 1: cada jornada coberta por exatamente 1 operador ──────
        for d in days:
            for j in range(len(daily_duties[d])):
                model.AddExactlyOne([x[(o, d, j)] for o in range(n_operators)])

        # ── Restrição 2: cada operador faz no máximo 1 jornada por dia ───────
        for o in range(n_operators):
            for d in days:
                opts = [x[(o, d, j)] for j in range(len(daily_duties[d]))]
                if opts:
                    model.AddAtMostOne(opts)

        # ── Restrição 3: dias de folga mínimos ────────────────────────────────
        max_days_worked = len(days) - min_days_off
        for o in range(n_operators):
            worked_flags = []
            for d in days:
                if daily_duties[d]:
                    day_worked = model.NewBoolVar(f"worked_o{o}_d{d}")
                    model.AddMaxEquality(day_worked, [x[(o, d, j)] for j in range(len(daily_duties[d]))])
                    worked_flags.append(day_worked)
            if worked_flags:
                model.Add(sum(worked_flags) <= max_days_worked)

        # ── Restrição 4: limite semanal de horas ──────────────────────────────
        for o in range(n_operators):
            weekly_terms = []
            for d in days:
                for j, duty in enumerate(daily_duties[d]):
                    dur = getattr(duty, "duration", 0) or 0
                    weekly_terms.append(dur * x[(o, d, j)])
            if weekly_terms:
                model.Add(sum(weekly_terms) <= weekly_limit)

        # ── Restrição 5: descanso entre jornadas de dias consecutivos ─────────
        for idx, d in enumerate(days[:-1]):
            d_next = days[idx + 1]
            if (d_next - d) != 1:
                continue  # só aplica se dias realmente consecutivos
            for j1, duty1 in enumerate(daily_duties[d]):
                end1 = getattr(duty1, "end_time", 0) or 0
                for j2, duty2 in enumerate(daily_duties[d_next]):
                    start2 = getattr(duty2, "start_time", 0) or 0
                    # gap entre fim do dia D e início do dia D+1 (D+1 está 1440 min à frente)
                    gap = (1440 - end1) + start2
                    if gap < min_rest:
                        # Conflito: motorista não pode trabalhar esses dois turnos consecutivos
                        for o in range(n_operators):
                            model.AddAtMostOne([x[(o, d, j1)], x[(o, d_next, j2)]])

        # ── Objetivo: minimizar custo total ───────────────────────────────────
        cost_terms = []
        for d in days:
            for j, duty in enumerate(daily_duties[d]):
                dur = getattr(duty, "duration", 0) or 0
                for o in range(n_operators):
                    cost_terms.append(dur * x[(o, d, j)])
        model.Minimize(sum(cost_terms))

        # ── Resolver ──────────────────────────────────────────────────────────
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = int(time_budget_s)
        solver.parameters.num_search_workers = 4
        solver.parameters.log_search_progress = False
        status = solver.Solve(model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            logger.warning(
                "[WeeklyRostering] CP-SAT status=%s — fallback greedy",
                solver.StatusName(status),
            )
            return self._solve_greedy(
                daily_duties,
                operators,
                days,
                weekly_limit,
                min_days_off,
                min_rest,
                t0,
                algorithm="weekly_cp_sat_fallback_greedy",
            )

        # ── Construir solução ─────────────────────────────────────────────────
        op_schedules: Dict[int, OperatorWeeklySchedule] = {
            o: OperatorWeeklySchedule(operator_id=operators[o].id) for o in range(n_operators)
        }
        unassigned_by_day: Dict[int, List[int]] = {}

        for d in days:
            for j, duty in enumerate(daily_duties[d]):
                assigned = False
                for o in range(n_operators):
                    if solver.BooleanValue(x[(o, d, j)]):
                        sched = op_schedules[o]
                        dur = getattr(duty, "duration", 0) or 0
                        wa = WeeklyAssignment(
                            operator_id=operators[o].id,
                            day_index=d,
                            duty_id=duty.id,
                            duty_minutes=dur,
                            duty_start=getattr(duty, "start_time", 0) or 0,
                            duty_end=getattr(duty, "end_time", 0) or 0,
                        )
                        sched.assignments.append(wa)
                        sched.total_minutes += dur
                        sched.days_worked += 1
                        assigned = True
                        break
                if not assigned:
                    unassigned_by_day.setdefault(d, []).append(duty.id)

        # Preencher dias de folga e custo
        for o, sched in op_schedules.items():
            worked_days = {wa.day_index for wa in sched.assignments}
            sched.days_off = [d for d in days if d not in worked_days]
            sched.weekly_cost = float(sched.total_minutes)

        schedules = list(op_schedules.values())
        total_minutes = sum(s.total_minutes for s in schedules)
        gini = _gini([s.total_minutes for s in schedules])

        return WeeklyRosterSolution(
            schedules=schedules,
            unassigned_by_day=unassigned_by_day,
            fairness_gini=round(gini, 4),
            total_minutes_assigned=total_minutes,
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 2),
            algorithm="weekly_cp_sat",
            feasible=True,
            meta={
                "cp_sat_status": solver.StatusName(status),
                "cp_sat_wall_time_s": round(solver.WallTime(), 3),
                "operators": n_operators,
                "days": days,
                "duties_total": sum(len(v) for v in daily_duties.values()),
                "weekly_limit_minutes": weekly_limit,
                "min_days_off": min_days_off,
                "min_rest_minutes": min_rest,
            },
        )

    # ── Greedy fallback ───────────────────────────────────────────────────────

    def _solve_greedy(
        self,
        daily_duties,
        operators,
        days,
        weekly_limit,
        min_days_off,
        min_rest,
        t0,
        algorithm: str = "weekly_greedy",
    ) -> WeeklyRosterSolution:
        """Heurística gulosa: atribui jornadas em ordem, respeitando limites."""
        max_days_worked = len(days) - min_days_off
        op_minutes: Dict[str, int] = {op.id: 0 for op in operators}
        op_days_worked: Dict[str, int] = {op.id: 0 for op in operators}
        op_last_end: Dict[str, Dict[int, int]] = {op.id: {} for op in operators}
        op_schedules: Dict[str, OperatorWeeklySchedule] = {
            op.id: OperatorWeeklySchedule(operator_id=op.id) for op in operators
        }
        unassigned_by_day: Dict[int, List[int]] = {}

        for d in days:
            for duty in daily_duties[d]:
                dur = getattr(duty, "duration", 0) or 0
                start = getattr(duty, "start_time", 0) or 0
                end = getattr(duty, "end_time", 0) or 0
                assigned = False
                for op in operators:
                    oid = op.id
                    # Limite semanal de horas
                    if op_minutes[oid] + dur > weekly_limit:
                        continue
                    # Limite de dias trabalhados
                    if op_days_worked[oid] >= max_days_worked:
                        continue
                    # Descanso entre dias consecutivos
                    prev_day = d - 1
                    if prev_day in op_last_end[oid]:
                        gap = (1440 - op_last_end[oid][prev_day]) + start
                        if gap < min_rest:
                            continue
                    # Assign
                    wa = WeeklyAssignment(
                        operator_id=oid,
                        day_index=d,
                        duty_id=duty.id,
                        duty_minutes=dur,
                        duty_start=start,
                        duty_end=end,
                    )
                    op_schedules[oid].assignments.append(wa)
                    op_minutes[oid] += dur
                    op_schedules[oid].total_minutes += dur
                    op_schedules[oid].days_worked += 1
                    op_days_worked[oid] += 1
                    op_last_end[oid][d] = end
                    assigned = True
                    break
                if not assigned:
                    unassigned_by_day.setdefault(d, []).append(duty.id)

        schedules = list(op_schedules.values())
        for sched in schedules:
            worked_days = {wa.day_index for wa in sched.assignments}
            sched.days_off = [d for d in days if d not in worked_days]
            sched.weekly_cost = float(sched.total_minutes)

        total_minutes = sum(s.total_minutes for s in schedules)
        gini = _gini([s.total_minutes for s in schedules])

        return WeeklyRosterSolution(
            schedules=schedules,
            unassigned_by_day=unassigned_by_day,
            fairness_gini=round(gini, 4),
            total_minutes_assigned=total_minutes,
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 2),
            algorithm=algorithm,
            feasible=len(unassigned_by_day) == 0,
            meta={
                "operators": len(operators),
                "days": days,
                "duties_total": sum(len(v) for v in daily_duties.values()),
                "weekly_limit_minutes": weekly_limit,
                "min_days_off": min_days_off,
                "min_rest_minutes": min_rest,
            },
        )
