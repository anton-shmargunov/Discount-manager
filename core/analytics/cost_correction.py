"""
Cost / margin correction for skipped Cost vs Price weeks.

Uses a bulk Cost = z0 + a * Price line. Correction is applied only to the
last N weeks (Skip last points). Skip 0 affects which weeks enter the fit
and the Option B anchor, not which weeks are corrected.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from core.models import BasketTimeSeries, Linefit, WeeklyTotal
from core.modeling.regression import fit_line


def values_skipping_last(
    values: list[float] | tuple[float, ...],
    skip_last: int,
) -> list[float]:
    """Return ``values`` with the last ``skip_last`` points removed."""
    skip = max(0, int(skip_last or 0))
    items = list(values)
    if skip == 0:
        return items
    if skip >= len(items):
        return []
    return items[:-skip]


def paired_values_skipping_zero_x(
    x: list[float] | tuple[float, ...],
    y: list[float] | tuple[float, ...],
    skip_zero_x: bool,
) -> tuple[list[float], list[float]]:
    """Drop paired points whose x value is exactly 0 when ``skip_zero_x`` is true."""
    xs = list(x)
    ys = list(y)
    if not skip_zero_x:
        n = min(len(xs), len(ys))
        return xs[:n], ys[:n]
    kept_x: list[float] = []
    kept_y: list[float] = []
    for xv, yv in zip(xs, ys):
        try:
            x_num = float(xv)
            y_num = float(yv)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(x_num) or not math.isfinite(y_num):
            continue
        if xv == 0:
            continue
        kept_x.append(xv)
        kept_y.append(yv)
    return kept_x, kept_y

COST_CORRECTION_FROM_REGRESSION = "From regression"
COST_CORRECTION_FROM_LAST_POINT = "From the last point"
COST_CORRECTION_MODES = (
    COST_CORRECTION_FROM_REGRESSION,
    COST_CORRECTION_FROM_LAST_POINT,
)


@dataclass
class CostCorrectionResult:
    applied: bool
    skipped_indices: list[int] = field(default_factory=list)
    intercept: float = float("nan")
    cost_corrected: list[float] = field(default_factory=list)
    margin_corrected: list[float] = field(default_factory=list)
    margin_hybrid: list[float] = field(default_factory=list)


def skipped_tail_indices(n_points: int, skip_last: int) -> list[int]:
    """Return indices of the last ``skip_last`` points (correction window)."""
    n = max(0, int(n_points))
    skip = max(0, int(skip_last or 0))
    if n == 0 or skip == 0:
        return []
    start = max(0, n - skip)
    return list(range(start, n))


def last_fitted_index(
    prices: list[float],
    skip_last: int,
    skip_zero_price: bool,
) -> int | None:
    """Last index that would be included in the bulk Cost vs Price fit."""
    n = len(prices)
    skip = max(0, int(skip_last or 0))
    end = n - skip
    if end <= 0:
        return None
    for i in range(end - 1, -1, -1):
        price = prices[i]
        if not math.isfinite(price):
            continue
        if skip_zero_price and price == 0:
            continue
        return i
    return None


def slope_in_correction_range(
    slope: float,
    a_min: float | None,
    a_max: float | None,
) -> bool:
    if not math.isfinite(slope):
        return False
    if a_min is not None and math.isfinite(a_min) and slope < a_min:
        return False
    if a_max is not None and math.isfinite(a_max) and slope > a_max:
        return False
    return True


def _nan_series(n: int) -> list[float]:
    return [float("nan")] * n


def compute_cost_margin_correction(
    prices: list[float],
    costs: list[float],
    sold: list[float],
    margins: list[float],
    fit: Linefit | None,
    skip_last: int,
    skip_zero_price: bool,
    mode: str,
    a_min: float | None,
    a_max: float | None,
) -> CostCorrectionResult:
    """
    Build Cost Corrected / Margin Corrected for the skip-last tail.

    Option A uses regression intercept z0. Option B re-anchors intercept on the
    last fitted week but does not change the Linefit used for Price_max.
    Margin Corrected = Margin + Sold * (Cost - Cost Corrected).
    """
    n = len(prices)
    original_m = list(margins)
    empty = CostCorrectionResult(
        applied=False,
        skipped_indices=skipped_tail_indices(n, skip_last),
        cost_corrected=_nan_series(n),
        margin_corrected=_nan_series(n),
        margin_hybrid=original_m,
    )
    if fit is None or n == 0:
        return empty
    if not slope_in_correction_range(fit.a, a_min, a_max):
        return empty

    skipped = skipped_tail_indices(n, skip_last)
    if not skipped:
        return empty

    intercept = fit.z0
    if mode == COST_CORRECTION_FROM_LAST_POINT:
        anchor = last_fitted_index(prices, skip_last, skip_zero_price)
        if anchor is None:
            return empty
        intercept = costs[anchor] - fit.a * prices[anchor]

    if not math.isfinite(intercept) or not math.isfinite(fit.a):
        return empty

    cost_corrected = _nan_series(n)
    margin_corrected = _nan_series(n)
    margin_hybrid = list(original_m)
    for i in skipped:
        price = prices[i]
        if not math.isfinite(price):
            continue
        unit_corr = intercept + fit.a * price
        cost_corrected[i] = unit_corr
        unit_cost = costs[i] if i < len(costs) else float("nan")
        qty = sold[i] if i < len(sold) else float("nan")
        margin = original_m[i] if i < len(original_m) else float("nan")
        if not math.isfinite(unit_cost) or not math.isfinite(qty) or not math.isfinite(margin):
            continue
        m_corr = margin + qty * (unit_cost - unit_corr)
        margin_corrected[i] = m_corr
        margin_hybrid[i] = m_corr

    return CostCorrectionResult(
        applied=True,
        skipped_indices=skipped,
        intercept=intercept,
        cost_corrected=cost_corrected,
        margin_corrected=margin_corrected,
        margin_hybrid=margin_hybrid,
    )


def fit_bulk_cost_price(
    basket_data: dict[str, BasketTimeSeries],
    skip_last: int,
    skip_zero_price: bool,
) -> dict[str, Linefit]:
    """Fit Cost vs Price for every basket using the bulk skip rules."""
    fitted: dict[str, Linefit] = {}
    for basket_name, ts in basket_data.items():
        prices = values_skipping_last(ts.price, skip_last)
        costs = values_skipping_last(ts.cost, skip_last)
        prices, costs = paired_values_skipping_zero_x(
            prices,
            costs,
            skip_zero_price,
        )
        lf = fit_line(prices, costs)
        if lf is not None:
            fitted[str(basket_name)] = lf
    return fitted


def compute_corrections_for_baskets(
    basket_data: dict[str, BasketTimeSeries],
    fits: dict[str, Linefit] | None,
    skip_last: int,
    skip_zero_price: bool,
    mode: str,
    a_min: float | None,
    a_max: float | None,
) -> dict[str, CostCorrectionResult]:
    """Per-basket Cost / Margin correction from bulk Cost vs Price fits."""
    fits = fits or {}
    out: dict[str, CostCorrectionResult] = {}
    for basket_name, ts in basket_data.items():
        out[str(basket_name)] = compute_cost_margin_correction(
            ts.price,
            ts.cost,
            ts.sold,
            ts.m,
            fits.get(str(basket_name)),
            skip_last,
            skip_zero_price,
            mode,
            a_min,
            a_max,
        )
    return out


def hybrid_margin_map(
    basket_data: dict[str, BasketTimeSeries],
    corrections: dict[str, CostCorrectionResult] | None,
) -> dict[str, list[float]]:
    """Basket → weekly margin series (corrected hybrid, else original)."""
    corrections = corrections or {}
    out: dict[str, list[float]] = {}
    for basket_name, ts in basket_data.items():
        key = str(basket_name)
        corr = corrections.get(key)
        if corr is not None and len(corr.margin_hybrid) == ts.n_weeks:
            out[key] = list(corr.margin_hybrid)
        else:
            out[key] = list(ts.m)
    return out


def _week_index(ts: BasketTimeSeries, week: str) -> int | None:
    week_str = str(week)
    for i, label in enumerate(ts.weeks):
        if str(label) == week_str:
            return i
    return None


def hybrid_margin_at_week(
    ts: BasketTimeSeries,
    week: str,
    correction: CostCorrectionResult | None,
) -> float:
    idx = _week_index(ts, week)
    if idx is None:
        return float("nan")
    if correction is not None and idx < len(correction.margin_hybrid):
        value = correction.margin_hybrid[idx]
        if math.isfinite(value):
            return float(value)
    if idx < len(ts.m):
        return float(ts.m[idx])
    return float("nan")


def enrich_sumup_with_corrected_totals(
    sumup_rows: list[dict],
    weekly_totals: dict[str, WeeklyTotal],
    basket_data: dict[str, BasketTimeSeries],
    corrections: dict[str, CostCorrectionResult] | None,
) -> list[dict]:
    """
    Add Total Margin Corrected and Cost Corrected to Sum-Up rows.

    Total Margin Corrected = sum of per-basket hybrid margins for that week.
    Cost Corrected = (Revenue - Total Margin Corrected) / Sold.
    """
    corrections = corrections or {}
    enriched: list[dict] = []
    for row in sumup_rows:
        week = str(row["week"])
        wt = weekly_totals.get(week)
        total_m_corrected = 0.0
        if wt is not None:
            for pt in wt.points:
                ts = basket_data.get(str(pt.basket))
                if ts is None:
                    total_m_corrected += float(pt.m)
                    continue
                val = hybrid_margin_at_week(
                    ts, week, corrections.get(str(pt.basket)),
                )
                if math.isfinite(val):
                    total_m_corrected += val
                elif math.isfinite(float(pt.m)):
                    total_m_corrected += float(pt.m)
        else:
            total_m_corrected = float(row.get("total_m", float("nan")))
        sold = float(row.get("total_sold", 0.0) or 0.0)
        revenue = float(row.get("total_revenue", 0.0) or 0.0)
        cost_corrected = (
            (revenue - total_m_corrected) / sold if sold > 0 else float("nan")
        )
        new_row = dict(row)
        new_row["total_m_corrected"] = total_m_corrected
        new_row["total_cost_corrected"] = cost_corrected
        enriched.append(new_row)
    return enriched
