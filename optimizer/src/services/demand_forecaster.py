"""
demand_forecaster.py — Previsão de demanda por linha/período usando sklearn.

Usado como input para geração de frequências no timetable:
  - Prediz ridership (passageiros) por (line_id, hour, day_of_week)
  - Modelo: GradientBoostingRegressor (sklearn) com features temporais e de contexto
  - Fallback: média histórica quando dados insuficientes

FLUXO:
  1. DemandForecaster.fit(historical_data) — treina o modelo
  2. DemandForecaster.predict(requests) → List[DemandPrediction]
  3. DemandForecaster.recommend_frequency(line_id, hour, capacity_per_bus)
     → frequência recomendada em ônibus/hora

REFERÊNCIA:
  Petit A. et al. (2019) "Dynamic Transit Frequency Optimization Using Machine
  Learning for Bus Fleet Sizing", Transportation Research Record 2673(7).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_log = logging.getLogger(__name__)

try:
    from sklearn.ensemble import GradientBoostingRegressor  # type: ignore
    from sklearn.preprocessing import StandardScaler  # type: ignore
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False
    _log.warning("[DemandForecaster] sklearn não disponível — usando fallback histórico")


@dataclass
class HistoricalRecord:
    """Registro histórico de demanda."""
    line_id: int
    hour: int              # 0-23
    day_of_week: int       # 0=Mon, 6=Sun
    month: int             # 1-12
    is_holiday: bool
    passengers: float
    weather_score: float = 1.0   # 1.0 = clima normal, <1 = chuva/frio


@dataclass
class DemandPrediction:
    line_id: int
    hour: int
    day_of_week: int
    predicted_passengers: float
    confidence_low: float
    confidence_high: float
    model_used: str


@dataclass
class FrequencyRecommendation:
    line_id: int
    hour: int
    day_of_week: int
    predicted_passengers: float
    recommended_buses_per_hour: int
    headway_minutes: int
    load_factor: float


class DemandForecaster:
    """Previsão de demanda com GradientBoosting sklearn.

    Args:
        n_estimators: árvores no GBR (default 100).
        max_depth: profundidade máxima (default 3).
        learning_rate: taxa de aprendizado (default 0.1).
        min_samples_to_train: mínimo de registros para treinar (abaixo → fallback).
    """

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 3,
        learning_rate: float = 0.1,
        min_samples_to_train: int = 30,
    ):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.min_samples_to_train = min_samples_to_train
        self._model: Optional[Any] = None
        self._scaler: Optional[Any] = None
        self._is_fitted = False
        # fallback: média por (line_id, hour, day_of_week)
        self._historical_means: Dict[Tuple[int, int, int], float] = {}
        self._global_mean: float = 50.0

    # ── Engenharia de features ────────────────────────────────────────────────

    def _make_features(self, records: List[HistoricalRecord]) -> np.ndarray:
        rows = []
        for r in records:
            rows.append([
                r.line_id,
                r.hour,
                r.day_of_week,
                r.month,
                int(r.is_holiday),
                r.weather_score,
                # Features cíclicas para hora e dia
                np.sin(2 * np.pi * r.hour / 24),
                np.cos(2 * np.pi * r.hour / 24),
                np.sin(2 * np.pi * r.day_of_week / 7),
                np.cos(2 * np.pi * r.day_of_week / 7),
                np.sin(2 * np.pi * r.month / 12),
                np.cos(2 * np.pi * r.month / 12),
            ])
        return np.array(rows, dtype=float)

    def _record_from_dict(self, d: Dict[str, Any]) -> HistoricalRecord:
        return HistoricalRecord(
            line_id=int(d["line_id"]),
            hour=int(d["hour"]),
            day_of_week=int(d["day_of_week"]),
            month=int(d.get("month", 1)),
            is_holiday=bool(d.get("is_holiday", False)),
            passengers=float(d["passengers"]),
            weather_score=float(d.get("weather_score", 1.0)),
        )

    # ── Treinamento ───────────────────────────────────────────────────────────

    def fit(self, historical_data: List[Dict[str, Any]]) -> "DemandForecaster":
        """Treina o modelo com dados históricos.

        Args:
            historical_data: lista de dicts com chaves:
                line_id, hour, day_of_week, month, is_holiday, passengers, weather_score.
        """
        records = [self._record_from_dict(d) for d in historical_data]

        # Sempre computa médias históricas (fallback)
        sums: Dict[Tuple[int, int, int], List[float]] = {}
        for r in records:
            key = (r.line_id, r.hour, r.day_of_week)
            sums.setdefault(key, []).append(r.passengers)
        self._historical_means = {k: float(np.mean(v)) for k, v in sums.items()}
        all_pax = [r.passengers for r in records]
        self._global_mean = float(np.mean(all_pax)) if all_pax else 50.0

        if not _SKLEARN_AVAILABLE or len(records) < self.min_samples_to_train:
            _log.info(
                "[DemandForecaster] sklearn indisponível ou dados insuficientes (%d<%d) → fallback histórico",
                len(records), self.min_samples_to_train,
            )
            return self

        X = self._make_features(records)
        y = np.array([r.passengers for r in records], dtype=float)
        self._scaler = StandardScaler()
        X_scaled = self._scaler.fit_transform(X)
        self._model = GradientBoostingRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            subsample=0.8,
            random_state=42,
        )
        self._model.fit(X_scaled, y)
        self._is_fitted = True
        _log.info(
            "[DemandForecaster] modelo treinado: %d amostras, features=12, R²=%.3f",
            len(records),
            self._model.score(X_scaled, y),
        )
        return self

    # ── Predição ──────────────────────────────────────────────────────────────

    def predict(
        self,
        requests: List[Dict[str, Any]],
    ) -> List[DemandPrediction]:
        """Prediz demanda para cada combinação (line_id, hour, day_of_week, ...).

        Args:
            requests: lista de dicts com line_id, hour, day_of_week, month,
                      is_holiday, weather_score.

        Returns:
            Lista de DemandPrediction com intervalo de confiança ±20%.
        """
        records = [self._record_from_dict({**d, "passengers": 0}) for d in requests]
        predictions: List[DemandPrediction] = []

        if self._is_fitted and self._model is not None and self._scaler is not None:
            X = self._make_features(records)
            X_scaled = self._scaler.transform(X)
            y_pred = self._model.predict(X_scaled)
            model_used = "gradient_boosting"
        else:
            y_pred = np.array([
                self._historical_means.get(
                    (r.line_id, r.hour, r.day_of_week), self._global_mean
                )
                for r in records
            ])
            model_used = "historical_mean_fallback"

        for r, pax in zip(records, y_pred):
            pax_clipped = max(0.0, float(pax))
            margin = pax_clipped * 0.20  # ±20% intervalo de confiança
            predictions.append(DemandPrediction(
                line_id=r.line_id,
                hour=r.hour,
                day_of_week=r.day_of_week,
                predicted_passengers=round(pax_clipped, 1),
                confidence_low=round(max(0.0, pax_clipped - margin), 1),
                confidence_high=round(pax_clipped + margin, 1),
                model_used=model_used,
            ))
        return predictions

    def recommend_frequency(
        self,
        line_id: int,
        hour: int,
        day_of_week: int,
        capacity_per_bus: int = 40,
        target_load_factor: float = 0.75,
        month: int = 6,
        is_holiday: bool = False,
        weather_score: float = 1.0,
    ) -> FrequencyRecommendation:
        """Recomenda frequência (ônibus/hora) para atender a demanda prevista.

        Args:
            capacity_per_bus: capacidade nominal do veículo.
            target_load_factor: fator de carga desejado (default 0.75 = 75%).

        Returns:
            FrequencyRecommendation com headway_minutes e buses_per_hour.
        """
        preds = self.predict([{
            "line_id": line_id, "hour": hour, "day_of_week": day_of_week,
            "month": month, "is_holiday": is_holiday, "weather_score": weather_score,
        }])
        pax = preds[0].predicted_passengers
        effective_capacity = max(1, capacity_per_bus * target_load_factor)
        buses_per_hour = max(1, int(np.ceil(pax / effective_capacity)))
        headway = max(5, min(60, 60 // buses_per_hour))
        load_factor = pax / (buses_per_hour * capacity_per_bus) if buses_per_hour > 0 else 0.0

        return FrequencyRecommendation(
            line_id=line_id,
            hour=hour,
            day_of_week=day_of_week,
            predicted_passengers=pax,
            recommended_buses_per_hour=buses_per_hour,
            headway_minutes=headway,
            load_factor=round(load_factor, 3),
        )

    def feature_importances(self) -> Dict[str, float]:
        """Retorna importâncias das features (apenas quando modelo sklearn treinado)."""
        if not self._is_fitted or self._model is None:
            return {}
        names = [
            "line_id", "hour", "day_of_week", "month", "is_holiday", "weather_score",
            "sin_hour", "cos_hour", "sin_dow", "cos_dow", "sin_month", "cos_month",
        ]
        return {n: round(float(imp), 4) for n, imp in zip(names, self._model.feature_importances_)}
