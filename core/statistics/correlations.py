"""
Reusable statistical correlation utilities.

All functions are pure, stateless, and UI-independent.
"""

from __future__ import annotations
import math
import numpy as np
from typing import Sequence

from configs.settings import MIN_POINTS_FOR_CORRELATION


def compute_pearson(x: Sequence[float], y: Sequence[float]) -> float:
    """
    Pearson correlation coefficient between two equal-length sequences.

    Returns NaN when:
    - fewer than MIN_POINTS_FOR_CORRELATION data points,
    - either series has zero variance.
    """
    n = len(x)
    if n < MIN_POINTS_FOR_CORRELATION:
        return float("nan")

    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)

    if x_arr.std() == 0.0 or y_arr.std() == 0.0:
        return float("nan")

    return float(np.corrcoef(x_arr, y_arr)[0, 1])


def compute_basket_correlations(
    sold: Sequence[float],
    price: Sequence[float],
    m: Sequence[float],
) -> dict[str, float]:
    """
    Compute the three core pairwise correlations for a basket's time series.

    Returns:
        {
            "corr_SP": Pearson(Sold, Price),
            "corr_MP": Pearson(M, Price),
            "corr_MS": Pearson(M, Sold),
        }
    """
    return {
        "corr_SP": compute_pearson(sold, price),
        "corr_MP": compute_pearson(m, price),
        "corr_MS": compute_pearson(m, sold),
    }


def safe_correlation_coord(value: float) -> float:
    """Return 0.0 for NaN correlations (used in clustering coordinate space)."""
    return 0.0 if math.isnan(value) else value


def compute_rolling_correlations(
    sold: Sequence[float],
    price: Sequence[float],
    m: Sequence[float],
    window: int = 8,
) -> dict[str, list[float]]:
    """
    Compute rolling Pearson correlations over a sliding window.

    Returns three lists of rolling correlation values (NaN where window is too small).
    Useful for time-evolution analysis.
    """
    n = len(sold)
    corr_SP, corr_MP, corr_MS = [], [], []

    for i in range(n):
        start = max(0, i - window + 1)
        s = list(sold[start : i + 1])
        p = list(price[start : i + 1])
        mv = list(m[start : i + 1])
        corr_SP.append(compute_pearson(s, p))
        corr_MP.append(compute_pearson(mv, p))
        corr_MS.append(compute_pearson(mv, s))

    return {"corr_SP": corr_SP, "corr_MP": corr_MP, "corr_MS": corr_MS}


def aggregate_weekly_correlations(
    weekly_sold: Sequence[float],
    weekly_price: Sequence[float],
    weekly_m: Sequence[float],
) -> dict[str, float]:
    """
    Compute correlations on aggregated weekly totals across all baskets.
    Used in the Sum-Up section.
    """
    return compute_basket_correlations(weekly_sold, weekly_price, weekly_m)
