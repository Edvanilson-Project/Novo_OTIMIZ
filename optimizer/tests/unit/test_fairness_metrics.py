"""Métricas de equidade (workload balance) entre duties.

Optbus expõe esse tipo de informação para o gestor identificar duties muito
desiguais. Aqui só computamos e expomos — não penalizamos.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.algorithms.evaluator import (
    _compute_fairness_metrics,
    _gini_coefficient,
    _percentile,
)


def test_gini_perfect_equality():
    assert _gini_coefficient([400, 400, 400, 400]) == 0.0


def test_gini_max_inequality():
    # uma única duty tem todo o trabalho
    g = _gini_coefficient([0, 0, 0, 100])
    assert 0.7 < g < 0.85


def test_gini_realistic_low():
    # variação moderada (300-350) → muito justo
    g = _gini_coefficient([300, 310, 320, 330, 340, 350])
    assert g < 0.05


def test_percentile_basic():
    sv = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
    assert _percentile(sv, 5) == 145.0
    assert _percentile(sv, 50) == 550.0
    assert _percentile(sv, 95) == 955.0


def test_fairness_empty():
    metrics = _compute_fairness_metrics([], [])
    assert metrics["num_duties"] == 0
    assert metrics["work_time"]["min"] == 0


class _FakeDuty:
    def __init__(self, work_time):
        self.work_time = work_time


def test_fairness_balanced_solution():
    """6 duties com work_time muito similar → Gini baixo, sem imbalance."""
    duties = [_FakeDuty(w) for w in [400, 410, 405, 415, 420, 408]]
    costs = [{"total": 1000.0 + i * 10} for i in range(6)]
    metrics = _compute_fairness_metrics(duties, costs)

    assert metrics["num_duties"] == 6
    assert metrics["work_time"]["mean"] == 409.67  # (400+410+405+415+420+408)/6 ≈ 409.67
    assert metrics["work_time"]["min"] == 400
    assert metrics["work_time"]["max"] == 420
    assert metrics["work_time"]["gini"] < 0.05  # extremamente justo
    assert metrics["imbalance"]["duties_below_50pct_avg"] == 0
    assert metrics["imbalance"]["duties_above_150pct_avg"] == 0


def test_fairness_imbalanced_solution():
    """6 duties: 1 muito curta (50min), 4 médias (~400), 1 longa (700)."""
    duties = [_FakeDuty(w) for w in [50, 400, 410, 405, 415, 700]]
    costs = [{"total": 1000.0} for _ in range(6)]
    metrics = _compute_fairness_metrics(duties, costs)

    # avg ≈ 396.67. 50 < 198 → below_50pct=1. 700 > 595 → above_150pct=1
    assert metrics["work_time"]["mean"] == 396.67
    assert metrics["work_time"]["min"] == 50
    assert metrics["work_time"]["max"] == 700
    assert metrics["work_time"]["gini"] > 0.10  # claramente desigual
    assert metrics["imbalance"]["duties_below_50pct_avg"] == 1
    assert metrics["imbalance"]["duties_above_150pct_avg"] == 1


def test_fairness_p5_p95_spread():
    """P95/P5 ratio mostra dispersão."""
    duties = [_FakeDuty(w) for w in [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]]
    costs = [{"total": 1000.0} for _ in range(10)]
    metrics = _compute_fairness_metrics(duties, costs)
    assert metrics["work_time"]["p5"] == 145.0
    assert metrics["work_time"]["p95"] == 955.0
