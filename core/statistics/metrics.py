"""
Reusable derived metric utilities.

Pure functions — no Streamlit, no I/O.
"""

from __future__ import annotations

import math
from typing import Sequence


def monthly_reserve(stock: float, sold: float) -> float:
    """
    Estimated months to sell out stock at the current weekly sold rate.

    Formula: Stock / Sold * 7 / 30
    """
    if sold <= 0 or math.isnan(sold) or math.isnan(stock):
        return float("nan")
    return stock / sold * 7.0 / 30.0


def monthly_reserve_series(
    stock: Sequence[float],
    sold: Sequence[float],
) -> list[float]:
    """Per-week monthly reserve aligned to the shorter of the two series."""
    n = min(len(stock), len(sold))
    return [monthly_reserve(float(stock[i]), float(sold[i])) for i in range(n)]
