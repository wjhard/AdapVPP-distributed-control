from __future__ import annotations

import csv
import math
import random
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Tuple

from .models import ForecastSnapshot, ResourceSnapshot


@dataclass(frozen=True)
class _PendingForecast:
    issue_step: int
    target_step: int
    forecast_mw: Tuple[float, float, float, float]


class ShortTermRenewableForecaster:
    """Persistence forecast with trend extrapolation and correlated uncertainty.

    The model intentionally stays lightweight: persistence forecasting is a
    standard short-horizon renewable baseline, while the AR(1) error state keeps
    forecast errors persistent instead of unrealistically independent.
    """

    node_names = ("PV1", "PV2", "Wind3", "Wind4")
    capacities_mw = (50.0, 40.0, 60.0, 55.0)
    node_kinds = ("pv", "pv", "wind", "wind")

    def __init__(
        self,
        project_root: Path,
        horizon_minutes: float = 15.0,
        horizon_steps: int = 1,
        trend_window: int = 6,
        seed: int = 20260708,
    ) -> None:
        self.project_root = project_root
        self.horizon_minutes = horizon_minutes
        self.horizon_steps = max(1, horizon_steps)
        self.trend_window = max(2, trend_window)
        self.rng = random.Random(seed)
        self.history: Deque[Tuple[float, Tuple[float, float, float, float]]] = deque(maxlen=self.trend_window)
        self.pending: Deque[_PendingForecast] = deque()
        self.error_state = [0.0, 0.0, 0.0, 0.0]
        self.step_index = -1
        self.squared_errors = [0.0, 0.0, 0.0, 0.0]
        self.absolute_percentage_errors = [0.0, 0.0, 0.0, 0.0]
        self.verified_counts = [0, 0, 0, 0]

        history_dir = project_root / "logs" / "forecast_accuracy"
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.history_path = history_dir / f"renewable_forecast_accuracy_{stamp}.csv"
        self._ensure_history_header()

    def update(self, elapsed_s: float, actual: ResourceSnapshot) -> ForecastSnapshot:
        self.step_index += 1
        actual_values = self._renewable_tuple(actual)
        self.history.append((elapsed_s, actual_values))

        verified_forecast = self._verify_due_forecast(actual_values)
        forecast_values = self._forecast_next(actual_values)
        self.pending.append(
            _PendingForecast(
                issue_step=self.step_index,
                target_step=self.step_index + self.horizon_steps,
                forecast_mw=forecast_values,
            )
        )

        rmse, mape, per_node_rmse, per_node_mape, sample_count = self._metrics()
        snapshot = ForecastSnapshot(
            method="persistence_trend_ar1_error",
            horizon_minutes=self.horizon_minutes,
            horizon_steps=self.horizon_steps,
            actual_mw=actual_values,
            forecast_mw=forecast_values,
            verified_forecast_mw=verified_forecast,
            rmse_mw=rmse,
            mape_percent=mape,
            per_node_rmse_mw=tuple(per_node_rmse),
            per_node_mape_percent=tuple(per_node_mape),
            sample_count=sample_count,
            history_path=str(self.history_path),
        )
        self._append_history_rows(elapsed_s, snapshot)
        return snapshot

    def forecast_resource(self, actual: ResourceSnapshot, forecast: ForecastSnapshot) -> ResourceSnapshot:
        return ResourceSnapshot(
            hour_index=actual.hour_index,
            solar_mw=(forecast.forecast_mw[0], forecast.forecast_mw[1]),
            wind_mw=(forecast.forecast_mw[2], forecast.forecast_mw[3]),
            load_mw=actual.load_mw,
        )

    @classmethod
    def forecast_pmax(cls, forecast: ForecastSnapshot) -> List[float]:
        return [
            max(0.0, min(cls.capacities_mw[index], float(forecast.forecast_mw[index])))
            for index in range(4)
        ] + [30.0]

    @classmethod
    def _renewable_tuple(cls, resource: ResourceSnapshot) -> Tuple[float, float, float, float]:
        return (
            float(resource.solar_mw[0]),
            float(resource.solar_mw[1]),
            float(resource.wind_mw[0]),
            float(resource.wind_mw[1]),
        )

    def _forecast_next(self, actual_values: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
        trend = self._linear_trend()
        horizon_multiplier = max(1.0, math.sqrt(self.horizon_minutes / 15.0))
        forecast: List[float] = []
        for index, actual in enumerate(actual_values):
            baseline = actual + trend[index] * self.horizon_steps
            error = self._correlated_error(index, baseline, horizon_multiplier)
            capped = max(0.0, min(self.capacities_mw[index], baseline + error))
            forecast.append(capped)
        return tuple(forecast)  # type: ignore[return-value]

    def _linear_trend(self) -> Tuple[float, float, float, float]:
        if len(self.history) < 2:
            return (0.0, 0.0, 0.0, 0.0)
        first = self.history[0][1]
        last = self.history[-1][1]
        span = max(len(self.history) - 1, 1)
        return tuple((last[index] - first[index]) / span for index in range(4))  # type: ignore[return-value]

    def _correlated_error(self, index: int, baseline: float, horizon_multiplier: float) -> float:
        kind = self.node_kinds[index]
        if kind == "pv":
            fraction = self.rng.uniform(0.08, 0.15)
        else:
            fraction = self.rng.uniform(0.10, 0.20)

        capacity = self.capacities_mw[index]
        active_scale = max(abs(baseline), 0.12 * capacity)
        sigma = active_scale * fraction * horizon_multiplier
        innovation = self.rng.gauss(0.0, sigma)
        self.error_state[index] = 0.82 * self.error_state[index] + 0.57 * innovation
        return self.error_state[index]

    def _verify_due_forecast(self, actual_values: Tuple[float, float, float, float]) -> Tuple[float, float, float, float] | None:
        verified: Tuple[float, float, float, float] | None = None
        while self.pending and self.pending[0].target_step <= self.step_index:
            item = self.pending.popleft()
            verified = item.forecast_mw
            for index, forecast_value in enumerate(item.forecast_mw):
                error = forecast_value - actual_values[index]
                self.squared_errors[index] += error * error
                denominator = max(abs(actual_values[index]), 0.20 * self.capacities_mw[index])
                self.absolute_percentage_errors[index] += abs(error) / denominator * 100.0
                self.verified_counts[index] += 1
        return verified

    def _metrics(self) -> Tuple[float, float, List[float], List[float], int]:
        per_node_rmse: List[float] = []
        per_node_mape: List[float] = []
        for index in range(4):
            count = self.verified_counts[index]
            if count == 0:
                per_node_rmse.append(0.0)
                per_node_mape.append(0.0)
            else:
                per_node_rmse.append(math.sqrt(self.squared_errors[index] / count))
                per_node_mape.append(self.absolute_percentage_errors[index] / count)

        total_count = sum(self.verified_counts)
        if total_count == 0:
            return 0.0, 0.0, per_node_rmse, per_node_mape, 0

        rmse = math.sqrt(sum(self.squared_errors) / total_count)
        mape = sum(self.absolute_percentage_errors) / total_count
        return rmse, mape, per_node_rmse, per_node_mape, total_count

    def _ensure_history_header(self) -> None:
        if self.history_path.exists() and self.history_path.stat().st_size > 0:
            return
        with self.history_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "elapsed_s",
                    "node",
                    "actual_mw",
                    "forecast_mw",
                    "verified_forecast_mw",
                    "rmse_mw",
                    "mape_percent",
                    "method",
                    "horizon_minutes",
                ]
            )

    def _append_history_rows(self, elapsed_s: float, snapshot: ForecastSnapshot) -> None:
        with self.history_path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            for index, node in enumerate(self.node_names):
                verified = (
                    ""
                    if snapshot.verified_forecast_mw is None
                    else f"{snapshot.verified_forecast_mw[index]:.6f}"
                )
                writer.writerow(
                    [
                        f"{elapsed_s:.3f}",
                        node,
                        f"{snapshot.actual_mw[index]:.6f}",
                        f"{snapshot.forecast_mw[index]:.6f}",
                        verified,
                        f"{snapshot.per_node_rmse_mw[index]:.6f}",
                        f"{snapshot.per_node_mape_percent[index]:.6f}",
                        snapshot.method,
                        f"{snapshot.horizon_minutes:.3f}",
                    ]
                )
