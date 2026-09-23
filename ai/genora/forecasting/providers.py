"""Forecasting providers.

* ``BaselineForecastProvider`` — additive Holt-Winters (level + trend + weekly seasonality), parameters
  chosen by grid search on in-sample one-step error, with residual-based prediction intervals. Pure numpy.
* ``SeasonalNaiveForecastProvider`` — repeats the last observed week; used as a benchmark.
* ``TimesFMForecastProvider`` — Google's TimesFM foundation model. Only usable when the optional
  ``timesfm`` package (and its model checkpoint) is installed; otherwise it reports itself unavailable
  and is never silently substituted.
* TabFM / other foundation models plug in by implementing :class:`ForecastingProvider`.
"""

from __future__ import annotations

import importlib.util
import itertools
from typing import Any

import numpy as np

from genora.errors import ProviderUnavailableError
from genora.forecasting.base import Forecast, ForecastingProvider, ForecastPoint, TimeSeries, backtest

Z80 = 1.2816


def _clip(values: np.ndarray, non_negative: bool) -> np.ndarray:
    return np.maximum(values, 0.0) if non_negative else values


class SeasonalNaiveForecastProvider(ForecastingProvider):
    name = "seasonal_naive"
    description = "Repeats the last observed seasonal cycle (weekly). Benchmark model."

    def __init__(self, season: int = 7) -> None:
        self.season = season

    @property
    def available(self) -> bool:
        return True

    def forecast(self, series: TimeSeries, horizon: int) -> Forecast:
        y = series.array
        if len(y) == 0:
            raise ValueError("empty series")
        m = min(self.season, len(y))
        last = y[-m:]
        pred = np.array([last[i % m] for i in range(horizon)])
        resid = y[m:] - y[:-m] if len(y) > m else np.zeros(1)
        sd = float(np.std(resid)) if len(resid) > 1 else 0.0
        steps = np.sqrt(np.floor(np.arange(horizon) / m) + 1)
        nonneg = bool((y >= 0).all())
        pts = [ForecastPoint(d, float(v), float(_clip(np.array([v - Z80 * sd * s]), nonneg)[0]), float(v + Z80 * sd * s))
               for d, v, s in zip(series.future_dates(horizon), pred, steps, strict=True)]
        return Forecast(self.name, f"seasonal-naive(m={m})", horizon, series.frequency, pts, 0.8)


class BaselineForecastProvider(ForecastingProvider):
    name = "baseline"
    description = "Additive Holt-Winters exponential smoothing with weekly seasonality and 80% prediction intervals."

    ALPHAS = (0.1, 0.2, 0.3, 0.5)
    BETAS = (0.01, 0.05, 0.1)
    GAMMAS = (0.05, 0.1, 0.3)

    def __init__(self, season: int = 7) -> None:
        self.season = season

    @property
    def available(self) -> bool:
        return True

    @staticmethod
    def _fit(y: np.ndarray, m: int, a: float, b: float, g: float) -> tuple[float, float, np.ndarray, np.ndarray]:
        level = float(np.mean(y[:m]))
        trend = float((np.mean(y[m:2 * m]) - np.mean(y[:m])) / m) if len(y) >= 2 * m else 0.0
        season = y[:m] - level
        fitted = np.zeros(len(y))
        season = season.astype(float).copy()
        for t in range(len(y)):
            s = season[t % m]
            fitted[t] = level + trend + s
            prev_level = level
            level = a * (y[t] - s) + (1 - a) * (level + trend)
            trend = b * (level - prev_level) + (1 - b) * trend
            season[t % m] = g * (y[t] - level) + (1 - g) * s
        return level, trend, season, fitted

    def forecast(self, series: TimeSeries, horizon: int) -> Forecast:
        y = series.array
        n = len(y)
        if n < 3:
            raise ValueError("at least 3 observations are required")
        nonneg = bool((y >= 0).all())
        m = self.season if n >= 2 * self.season else 1
        best: tuple[float, tuple[float, float, float]] | None = None
        for a, b, g in itertools.product(self.ALPHAS, self.BETAS, self.GAMMAS if m > 1 else (0.0,)):
            *_, fitted = self._fit(y, m, a, b, g)
            sse = float(np.sum((y[m:] - fitted[m:]) ** 2))
            if best is None or sse < best[0]:
                best = (sse, (a, b, g))
        assert best is not None
        a, b, g = best[1]
        level, trend, season, fitted = self._fit(y, m, a, b, g)
        # damp the trend so long horizons do not explode on short histories
        phi = 0.9
        damp = np.cumsum(phi ** np.arange(1, horizon + 1))
        idx = (np.arange(n, n + horizon)) % m
        pred = level + damp * trend + season[idx]
        pred = _clip(pred, nonneg)
        resid = y[m:] - fitted[m:]
        sd = float(np.std(resid)) if len(resid) > 1 else float(np.std(y))
        widen = np.sqrt(1 + np.arange(horizon) * a * a)
        lower = _clip(pred - Z80 * sd * widen, nonneg)
        upper = pred + Z80 * sd * widen
        pts = [ForecastPoint(d, float(v), float(lo), float(hi))
               for d, v, lo, hi in zip(series.future_dates(horizon), pred, lower, upper, strict=True)]
        return Forecast(self.name, f"holt-winters-additive(m={m},damped)", horizon, series.frequency, pts, 0.8,
                        params={"alpha": a, "beta": b, "gamma": g, "phi": phi, "season": m, "residual_sd": round(sd, 3)})


class TimesFMForecastProvider(ForecastingProvider):
    name = "timesfm"
    description = "Google TimesFM time-series foundation model (requires the optional `timesfm` package)."
    CHECKPOINT = "google/timesfm-1.0-200m-pytorch"

    def __init__(self) -> None:
        self._model: Any = None

    @property
    def available(self) -> bool:
        return importlib.util.find_spec("timesfm") is not None

    @property
    def unavailable_reason(self) -> str | None:
        return None if self.available else "The `timesfm` package is not installed (pip install 'genora[timesfm]')"

    def _load(self, horizon: int) -> Any:  # pragma: no cover - requires optional dependency + model download
        import timesfm  # type: ignore[import-not-found]

        if self._model is None:
            self._model = timesfm.TimesFm(
                hparams=timesfm.TimesFmHparams(backend="cpu", per_core_batch_size=1, horizon_len=max(horizon, 128)),
                checkpoint=timesfm.TimesFmCheckpoint(huggingface_repo_id=self.CHECKPOINT),
            )
        return self._model

    def forecast(self, series: TimeSeries, horizon: int) -> Forecast:
        if not self.available:
            raise ProviderUnavailableError(self.unavailable_reason or "TimesFM unavailable")
        model = self._load(horizon)  # pragma: no cover
        point, quantiles = model.forecast([series.array], freq=[0])  # pragma: no cover
        values = np.asarray(point[0][:horizon], dtype=float)  # pragma: no cover
        q = np.asarray(quantiles[0][:horizon])  # pragma: no cover - columns: mean, q10..q90
        pts = [ForecastPoint(d, float(v), float(q[i, 1]), float(q[i, -1]))  # pragma: no cover
               for i, (d, v) in enumerate(zip(series.future_dates(horizon), values, strict=True))]
        return Forecast(self.name, self.CHECKPOINT, horizon, series.frequency, pts, 0.8)  # pragma: no cover


class ForecastingRegistry:
    def __init__(self, providers: list[ForecastingProvider] | None = None) -> None:
        items = providers or [BaselineForecastProvider(), SeasonalNaiveForecastProvider(), TimesFMForecastProvider()]
        self._providers = {p.name: p for p in items}

    def get(self, name: str) -> ForecastingProvider:
        if name not in self._providers:
            raise ProviderUnavailableError(f"unknown forecasting provider '{name}'")
        provider = self._providers[name]
        if not provider.available:
            raise ProviderUnavailableError(provider.unavailable_reason or f"provider '{name}' is unavailable")
        return provider

    def describe(self) -> list[dict[str, Any]]:
        return [p.describe() for p in self._providers.values()]

    def run(self, name: str, series: TimeSeries, horizon: int) -> Forecast:
        provider = self.get(name)
        result = provider.forecast(series, horizon)
        holdout = min(14, max(len(series.values) // 6, 0))
        result.metrics = {"backtest": backtest(provider, series, holdout)}
        if name != "seasonal_naive":
            bench = backtest(SeasonalNaiveForecastProvider(), series, holdout)
            result.metrics["benchmark_seasonal_naive"] = bench
            if result.metrics["backtest"]["mae"] is not None and bench["mae"]:
                result.metrics["skill_vs_naive"] = round(1 - result.metrics["backtest"]["mae"] / bench["mae"], 3)
        return result
