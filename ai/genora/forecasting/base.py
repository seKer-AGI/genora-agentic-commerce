"""Forecasting provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np


@dataclass
class TimeSeries:
    dates: list[date]
    values: list[float]
    frequency: str = "D"

    def __post_init__(self) -> None:
        if len(self.dates) != len(self.values):
            raise ValueError("dates and values must have the same length")

    @property
    def array(self) -> np.ndarray:
        return np.asarray(self.values, dtype=float)

    def future_dates(self, horizon: int) -> list[date]:
        last = self.dates[-1]
        return [last + timedelta(days=i) for i in range(1, horizon + 1)]


@dataclass
class ForecastPoint:
    date: date
    value: float
    lower: float | None = None
    upper: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"date": self.date.isoformat(), "value": round(self.value, 2),
                "lower": None if self.lower is None else round(self.lower, 2),
                "upper": None if self.upper is None else round(self.upper, 2)}


@dataclass
class Forecast:
    provider: str
    model_name: str
    horizon: int
    frequency: str
    points: list[ForecastPoint]
    interval: float | None  # e.g. 0.8 for an 80% prediction interval, None if not supported
    metrics: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)


class ForecastingProvider(ABC):
    name: str
    description: str

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @property
    def unavailable_reason(self) -> str | None:
        return None

    @abstractmethod
    def forecast(self, series: TimeSeries, horizon: int) -> Forecast: ...

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "available": self.available,
                "unavailable_reason": self.unavailable_reason}


def backtest(provider: ForecastingProvider, series: TimeSeries, holdout: int) -> dict[str, float | None]:
    """Hold out the last `holdout` points, forecast them and report accuracy."""
    if holdout < 1 or len(series.values) < holdout + 14:
        return {"mae": None, "mape": None, "smape": None, "holdout": 0}
    train = TimeSeries(series.dates[:-holdout], series.values[:-holdout], series.frequency)
    actual = np.asarray(series.values[-holdout:], dtype=float)
    pred = np.asarray([p.value for p in provider.forecast(train, holdout).points], dtype=float)
    mae = float(np.mean(np.abs(actual - pred)))
    nz = actual != 0
    mape = float(np.mean(np.abs((actual[nz] - pred[nz]) / actual[nz])) * 100) if nz.any() else None
    denom = np.abs(actual) + np.abs(pred)
    smape = float(np.mean(np.where(denom == 0, 0, 2 * np.abs(actual - pred) / np.where(denom == 0, 1, denom))) * 100)
    return {"mae": round(mae, 3), "mape": None if mape is None else round(mape, 2), "smape": round(smape, 2),
            "holdout": holdout}
