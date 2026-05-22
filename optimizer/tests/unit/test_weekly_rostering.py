"""Testes unitários para WeeklyRosteringSolver."""
from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Stubs mínimos para não depender de toda a cadeia de imports
# ---------------------------------------------------------------------------

@dataclass
class _Duty:
    id: int
    start_time: int   # minutos desde meia-noite
    end_time: int
    duration: int

    @classmethod
    def make(cls, id: int, start: int, end: int) -> "_Duty":
        dur = end - start if end >= start else (1440 - start) + end
        return cls(id=id, start_time=start, end_time=end, duration=dur)


@dataclass
class _Operator:
    id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ops(n: int) -> List[_Operator]:
    return [_Operator(id=f"op{i}") for i in range(n)]


def _duty(id: int, start: int, end: int) -> _Duty:
    return _Duty.make(id, start, end)


def _import_solver():
    from src.services.rostering.weekly_solver import WeeklyRosteringSolver  # type: ignore
    return WeeklyRosteringSolver


# ---------------------------------------------------------------------------
# Casos básicos
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_duties_returns_infeasible(self):
        Solver = _import_solver()
        sol = Solver().solve({}, _ops(2))
        assert sol.feasible is False
        assert sol.meta["reason"] == "empty_input"

    def test_empty_operators_returns_infeasible(self):
        Solver = _import_solver()
        duties = {0: [_duty(1, 480, 960)]}
        sol = Solver().solve(duties, [])
        assert sol.feasible is False


class TestSingleDaySingleDuty:
    """1 jornada, 1 operador, 1 dia → deve ser atribuída."""

    def test_assigns_single_duty(self):
        Solver = _import_solver()
        # Day 1 empty so max_days_worked = 2-1 = 1 (operator can work day 0)
        duties = {0: [_duty(1, 360, 840)], 1: []}   # 6h–14h
        sol = Solver().solve(duties, _ops(1))
        assert sol.feasible is True
        assert len(sol.schedules) == 1
        sched = sol.schedules[0]
        assert len(sched.assignments) == 1
        assert sched.assignments[0].duty_id == 1
        assert sched.total_minutes == 480

    def test_total_minutes_correct(self):
        Solver = _import_solver()
        # Day 1 empty so max_days_worked = 2-1 = 1 (operator can work day 0)
        duties = {0: [_duty(1, 0, 300)], 1: []}   # 5h de duração
        sol = Solver().solve(duties, _ops(2))
        assert sol.total_minutes_assigned == 300


class TestCoverageConstraint:
    """Toda jornada deve ser coberta por exatamente 1 operador."""

    def test_all_duties_covered_multiple_days(self):
        Solver = _import_solver()
        duties = {
            0: [_duty(1, 360, 720), _duty(2, 720, 1080)],
            1: [_duty(3, 480, 840)],
        }
        ops = _ops(3)
        sol = Solver().solve(duties, ops)
        # Com 3 ops para 3 jornadas deve ser viável
        assert sol.feasible is True
        covered = sum(len(s.assignments) for s in sol.schedules)
        assert covered == 3
        assert len(sol.unassigned_by_day) == 0

    def test_one_duty_per_operator_per_day(self):
        """Um operador não pode fazer 2 jornadas no mesmo dia."""
        Solver = _import_solver()
        duties = {
            0: [_duty(1, 360, 720), _duty(2, 720, 1080)],
        }
        ops = _ops(2)
        sol = Solver().solve(duties, ops)
        for sched in sol.schedules:
            days_seen = [wa.day_index for wa in sched.assignments]
            assert len(days_seen) == len(set(days_seen)), "Operador fez 2 jornadas no mesmo dia"


class TestWeeklyHoursLimit:
    """Limite de 44h/semana (2640 min) deve ser respeitado."""

    def test_does_not_exceed_weekly_limit(self):
        Solver = _import_solver()
        # 5 dias com jornada de 540 min (9h) = 2700 min → acima do limite para 1 op
        duties = {d: [_duty(d * 10 + 1, 360, 900)] for d in range(5)}
        ops = _ops(2)
        sol = Solver(weekly_hour_limit_minutes=2640).solve(duties, ops)
        for sched in sol.schedules:
            assert sched.total_minutes <= 2640, (
                f"Operador {sched.operator_id} excedeu limite semanal: {sched.total_minutes}"
            )

    def test_custom_weekly_limit_respected(self):
        Solver = _import_solver()
        # Jornada de 480 min × 4 dias = 1920 min — acima do limite customizado de 1440
        duties = {d: [_duty(d * 10 + 1, 480, 960)] for d in range(4)}
        ops = _ops(4)
        sol = Solver(weekly_hour_limit_minutes=1440).solve(duties, ops)
        for sched in sol.schedules:
            assert sched.total_minutes <= 1440


class TestMinDaysOff:
    """Cada operador deve ter ao menos 1 dia de folga (CLT Art. 67)."""

    def test_at_least_one_day_off_per_week(self):
        Solver = _import_solver()
        # 7 dias de jornada exigiria trabalhar todos os dias
        duties = {d: [_duty(d * 10 + 1, 480, 960)] for d in range(7)}
        ops = _ops(8)
        sol = Solver(min_days_off=1).solve(duties, ops)
        for sched in sol.schedules:
            if sched.days_worked > 0:
                assert len(sched.days_off) >= 1, (
                    f"Operador {sched.operator_id} sem folga: days_off={sched.days_off}"
                )

    def test_days_off_list_consistent(self):
        Solver = _import_solver()
        duties = {0: [_duty(1, 480, 960)], 1: [_duty(2, 480, 960)]}
        ops = _ops(2)
        sol = Solver().solve(duties, ops)
        for sched in sol.schedules:
            worked = {wa.day_index for wa in sched.assignments}
            for d in sched.days_off:
                assert d not in worked, "Dia marcado como folga mas tem jornada atribuída"


class TestInterShiftRest:
    """Descanso mínimo de 11h (660 min) entre jornadas em dias consecutivos."""

    def test_no_violation_when_gap_sufficient(self):
        Solver = _import_solver()
        # Dia 0: termina às 23:00 (1380), Dia 1: começa às 07:00 (420)
        # gap = (1440 - 1380) + 420 = 480 min → MENOS de 660 → par inválido
        # Com 2 ops deve reatribuir para ops diferentes
        duties = {
            0: [_duty(1, 900, 1380)],   # 15h–23h
            1: [_duty(2, 420, 900)],    # 7h–15h
        }
        ops = _ops(2)
        sol = Solver(min_inter_shift_rest_minutes=660).solve(duties, ops)
        # Verificar que nenhum operador tem o par inviável
        for sched in sol.schedules:
            by_day = {wa.day_index: wa for wa in sched.assignments}
            if 0 in by_day and 1 in by_day:
                gap = (1440 - by_day[0].duty_end) + by_day[1].duty_start
                assert gap >= 660, (
                    f"Violação de descanso para {sched.operator_id}: gap={gap} min"
                )

    def test_sufficient_gap_allows_same_operator(self):
        Solver = _import_solver()
        # Dia 0: 06h–14h (360–840), Dia 1: 06h–14h (360–840)
        # gap = (1440 - 840) + 360 = 960 min → OK
        # Day 2 empty so max_days_worked = 3-1 = 2 (1 op can cover both duty days)
        duties = {
            0: [_duty(1, 360, 840)],
            1: [_duty(2, 360, 840)],
            2: [],
        }
        ops = _ops(1)
        sol = Solver(min_inter_shift_rest_minutes=660).solve(duties, ops)
        # Com 1 op e gap suficiente, deve ser viável
        assert sol.feasible is True


class TestFairness:
    """Coeficiente de Gini mede equidade (0 = perfeito)."""

    def test_gini_zero_when_all_equal(self):
        Solver = _import_solver()
        # 2 ops, 2 jornadas idênticas em dias diferentes
        duties = {
            0: [_duty(1, 360, 840)],   # 480 min
            1: [_duty(2, 360, 840)],   # 480 min
        }
        ops = _ops(2)
        sol = Solver().solve(duties, ops)
        # Distribuição perfeita → Gini próximo de 0
        assert sol.fairness_gini <= 0.05

    def test_gini_between_zero_and_one(self):
        Solver = _import_solver()
        duties = {d: [_duty(d * 10 + 1, 360, 360 + 60 * (d + 4))] for d in range(4)}
        ops = _ops(4)
        sol = Solver().solve(duties, ops)
        assert 0.0 <= sol.fairness_gini <= 1.0


class TestMeta:
    """Campo meta deve conter informações de diagnóstico."""

    def test_meta_contains_basic_fields(self):
        Solver = _import_solver()
        duties = {0: [_duty(1, 480, 960)]}
        sol = Solver().solve(duties, _ops(1))
        assert "operators" in sol.meta
        assert "days" in sol.meta
        assert "duties_total" in sol.meta

    def test_elapsed_ms_positive(self):
        Solver = _import_solver()
        duties = {0: [_duty(1, 480, 960)]}
        sol = Solver().solve(duties, _ops(1))
        assert sol.elapsed_ms > 0


class TestCctParamsOverride:
    """cct_params deve sobrescrever defaults do solver."""

    def test_override_weekly_limit(self):
        Solver = _import_solver()
        # Jornada de 600 min — acima do limite customizado de 480 min
        duties = {0: [_duty(1, 0, 600)]}
        ops = _ops(1)
        sol = Solver(weekly_hour_limit_minutes=2640).solve(
            duties, ops, cct_params={"weekly_hour_limit_minutes": 480}
        )
        # Com apenas 1 op e limite de 480, jornada de 600 não cabe → unassigned
        # (O solver pode ser infeasible ou deixar a jornada sem atribuição)
        if sol.feasible:
            for sched in sol.schedules:
                assert sched.total_minutes <= 480
        else:
            assert len(sol.unassigned_by_day.get(0, [])) > 0 or not sol.feasible


class TestAlgorithmField:
    """Campo algorithm identifica o método usado."""

    def test_algorithm_field_present(self):
        Solver = _import_solver()
        duties = {0: [_duty(1, 480, 960)]}
        sol = Solver().solve(duties, _ops(1))
        assert sol.algorithm in ("weekly_cp_sat", "weekly_greedy", "weekly_cp_sat_fallback_greedy")
