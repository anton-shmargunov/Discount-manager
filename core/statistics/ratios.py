"""
Ratio helpers kept in their own module so Cloud can load them even when
core/statistics/metrics.py is served from an older snapshot.
"""

from __future__ import annotations

import math
from typing import Sequence


def safe_ratio(numerator: float, denominator: float) -> float:
    """Return numerator / denominator, or NaN when the ratio is undefined."""
    try:
        num = float(numerator)
        den = float(denominator)
    except (TypeError, ValueError):
        return float("nan")
    if not math.isfinite(num) or not math.isfinite(den) or den == 0:
        return float("nan")
    return num / den


def ratio_series(
    numerators: Sequence[float],
    denominators: Sequence[float],
) -> list[float]:
    """Per-week ratio aligned to the shorter of the two series."""
    n = min(len(numerators), len(denominators))
    return [safe_ratio(numerators[i], denominators[i]) for i in range(n)]
