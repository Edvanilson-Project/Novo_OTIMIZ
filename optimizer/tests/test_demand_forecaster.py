"""Testes para DemandForecaster (ML + fallback histórico)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.services.demand_forecaster import DemandForecaster, _SKLEARN_AVAILABLE


def _make_records(n: int = 100):
    """Gera dados históricos sintéticos para treino."""
    import random
    random.seed(42)
    records = []
    for _ in range(n):
        hour = random.randint(5, 22)
        dow = random.randint(0, 6)
        # Padrão sintético: pico manhã (7-9h) e tarde (17-19h), mais no dia útil
        pax = (
            80 * (1 if 7 <= hour <= 9 else 0.4 if 17 <= hour <= 19 else 0.2)
            * (1.0 if dow < 5 else 0.6)
            + random.gauss(0, 5)
        )
        records.append({
            "line_id": random.choice([1, 2]),
            "hour": hour,
            "day_of_week": dow,
            "month": random.randint(1, 12),
            "is_holiday": random.random() < 0.05,
            "passengers": max(0, pax),
            "weather_score": random.uniform(0.8, 1.0),
        })
    return records


class TestDemandForecasterFallback:
    def test_predict_without_fit_uses_global_mean(self):
        f = DemandForecaster()
        preds = f.predict([{"line_id": 1, "hour": 8, "day_of_week": 1,
                            "month": 6, "is_holiday": False, "weather_score": 1.0}])
        assert len(preds) == 1
        assert preds[0].predicted_passengers >= 0
        assert preds[0].model_used == "historical_mean_fallback"

    def test_fit_with_few_samples_uses_fallback(self):
        f = DemandForecaster(min_samples_to_train=1000)
        f.fit(_make_records(10))
        preds = f.predict([{"line_id": 1, "hour": 8, "day_of_week": 0,
                            "month": 3, "is_holiday": False, "weather_score": 1.0}])
        assert preds[0].model_used == "historical_mean_fallback"

    def test_confidence_interval_non_negative(self):
        f = DemandForecaster()
        preds = f.predict([{"line_id": 1, "hour": 3, "day_of_week": 6,
                            "month": 1, "is_holiday": True, "weather_score": 0.5}])
        assert preds[0].confidence_low >= 0.0
        assert preds[0].confidence_high >= preds[0].predicted_passengers

    def test_recommend_frequency_no_fit(self):
        f = DemandForecaster()
        rec = f.recommend_frequency(line_id=1, hour=8, day_of_week=0)
        assert rec.recommended_buses_per_hour >= 1
        assert 5 <= rec.headway_minutes <= 60
        assert 0.0 <= rec.load_factor


@pytest.mark.skipif(not _SKLEARN_AVAILABLE, reason="sklearn não instalado")
class TestDemandForecasterML:
    def test_fit_and_predict_sklearn(self):
        f = DemandForecaster(n_estimators=20, min_samples_to_train=50)
        f.fit(_make_records(200))
        assert f._is_fitted
        preds = f.predict([{"line_id": 1, "hour": 8, "day_of_week": 0,
                            "month": 6, "is_holiday": False, "weather_score": 1.0}])
        assert preds[0].model_used == "gradient_boosting"
        assert preds[0].predicted_passengers > 0

    def test_peak_hour_higher_than_off_peak(self):
        """Hora de pico (7h) deve ter demanda maior que madrugada (2h)."""
        f = DemandForecaster(n_estimators=50, min_samples_to_train=50)
        f.fit(_make_records(500))
        preds = f.predict([
            {"line_id": 1, "hour": 8, "day_of_week": 1, "month": 6, "is_holiday": False, "weather_score": 1.0},
            {"line_id": 1, "hour": 2, "day_of_week": 1, "month": 6, "is_holiday": False, "weather_score": 1.0},
        ])
        assert preds[0].predicted_passengers > preds[1].predicted_passengers

    def test_feature_importances(self):
        f = DemandForecaster(n_estimators=20, min_samples_to_train=50)
        f.fit(_make_records(200))
        imps = f.feature_importances()
        assert len(imps) == 12
        assert abs(sum(imps.values()) - 1.0) < 0.01  # soma ≈ 1

    def test_recommend_frequency_peak(self):
        f = DemandForecaster(n_estimators=20, min_samples_to_train=50)
        f.fit(_make_records(500))
        peak = f.recommend_frequency(line_id=1, hour=8, day_of_week=0, capacity_per_bus=40)
        off = f.recommend_frequency(line_id=1, hour=2, day_of_week=0, capacity_per_bus=40)
        assert peak.recommended_buses_per_hour >= off.recommended_buses_per_hour

    def test_multiple_lines_predicted_independently(self):
        f = DemandForecaster(n_estimators=20, min_samples_to_train=50)
        f.fit(_make_records(300))
        preds = f.predict([
            {"line_id": 1, "hour": 8, "day_of_week": 0, "month": 6, "is_holiday": False, "weather_score": 1.0},
            {"line_id": 2, "hour": 8, "day_of_week": 0, "month": 6, "is_holiday": False, "weather_score": 1.0},
        ])
        # Ambas devem ter predições válidas
        assert all(p.predicted_passengers >= 0 for p in preds)
