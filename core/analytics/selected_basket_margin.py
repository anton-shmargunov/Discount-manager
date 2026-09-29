"""
Margin Corrected for several selected baskets (Multiselect / Group Basket Detail).

Kept in its own module so Streamlit Cloud can load it even when older
modules are served from a stale snapshot.
"""

from __future__ import annotations

import math

from core.analytics.cost_correction import CostCorrectionResult
from core.models import BasketTimeSeries


def _finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _week_index(ts: BasketTimeSeries, week: str) -> int | None:
    for i, label in enumerate(ts.weeks):
        if str(label) == week:
            return i
    return None


def selected_baskets_margin_corrected(
    basket_data: dict[str, BasketTimeSeries],
    baskets: list[str],
    weeks: list[str],
    corrections: dict[str, CostCorrectionResult] | None,
    weighted_price: list[float] | None = None,
) -> dict[str, object]:
    """
    Weekly sums of per-basket hybrid margin for the selected baskets.

    margin_hybrid: original margin on kept weeks, Margin Corrected on skipped weeks.
    margin_corrected: margin_hybrid only on weeks where at least one selected
    basket was corrected, NaN elsewhere.
    cost_corrected: W.Price - margin_hybrid / Sold on corrected weeks, NaN elsewhere.
    """
    corrections = corrections or {}
    selected = [
        (str(name), basket_data[str(name)])
        for name in baskets
        if str(name) in basket_data
    ]
    week_labels = [str(week) for week in weeks]
    prices = list(weighted_price or [])

    margin_hybrid: list[float] = []
    margin_corrected: list[float] = []
    cost_corrected: list[float] = []
    applied = False

    for w_idx, week in enumerate(week_labels):
        total_m = 0.0
        total_sold = 0.0
        found_m = False
        found_sold = False
        corrected = False
        for name, ts in selected:
            idx = _week_index(ts, week)
            if idx is None:
                continue
            corr = corrections.get(name)
            margin = ts.m[idx] if idx < len(ts.m) else float("nan")
            if (
                corr is not None
                and corr.applied
                and idx < len(corr.margin_corrected)
                and _finite(corr.margin_corrected[idx])
            ):
                margin = corr.margin_corrected[idx]
                corrected = True
            if _finite(margin):
                total_m += float(margin)
                found_m = True
            sold = ts.sold[idx] if idx < len(ts.sold) else float("nan")
            if _finite(sold):
                total_sold += float(sold)
                found_sold = True

        hybrid = total_m if found_m else float("nan")
        margin_hybrid.append(hybrid)
        if not corrected:
            margin_corrected.append(float("nan"))
            cost_corrected.append(float("nan"))
            continue

        applied = True
        margin_corrected.append(hybrid)
        wp = prices[w_idx] if w_idx < len(prices) else float("nan")
        if _finite(wp) and _finite(hybrid) and found_sold and total_sold > 0:
            cost_corrected.append(float(wp) - hybrid / total_sold)
        else:
            cost_corrected.append(float("nan"))

    return {
        "applied": applied,
        "margin_hybrid": margin_hybrid,
        "margin_corrected": margin_corrected,
        "cost_corrected": cost_corrected,
    }
