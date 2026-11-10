"""Baseline trend predictor.

Deliberately simple: a least-squares line through recent history. It is the
benchmark any fancier model (gradient boosting, neural net) must beat once
enough history has been collected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

MIN_POINTS = 5
STABLE_BAND = 0.02  # +/-2% over the horizon counts as "stable"


@dataclass(frozen=True)
class Forecast:
    direction: str  # rising | falling | stable | insufficient_data
    expected_change_pct: float | None
    confidence: float  # 0..1, R^2 of the fit scaled by how much data there is
    points: int


def forecast(series: list[tuple[datetime, float]], horizon_days: int = 7) -> Forecast:
    n = len(series)
    if n < MIN_POINTS:
        return Forecast("insufficient_data", None, 0.0, n)

    t0 = series[0][0]
    xs = [(ts - t0).total_seconds() / 86400 for ts, _ in series]
    ys = [v for _, v in series]
    if max(xs) - min(xs) < 1e-9:
        return Forecast("insufficient_data", None, 0.0, n)

    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx

    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    current = intercept + slope * xs[-1]
    if current <= 0:
        return Forecast("insufficient_data", None, 0.0, n)
    change = (slope * horizon_days) / current
    direction = "stable" if abs(change) < STABLE_BAND else ("rising" if change > 0 else "falling")
    confidence = max(0.0, min(1.0, r2)) * min(1.0, n / 20)
    return Forecast(direction, round(change * 100, 2), round(confidence, 2), n)
