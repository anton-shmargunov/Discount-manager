"""
Preprocessing filter levels.

General: drop a whole week if any ranged metric is out of bounds.
Targeted: keep the week and mask only the out-of-range metric with NaN.
"""

from __future__ import annotations

import math
from typing import Sequence

FILTER_LEVEL_GENERAL = "General"
FILTER_LEVEL_TARGETED = "Targeted"
FILTER_LEVEL_CHOICES: tuple[str, ...] = (
    FILTER_LEVEL_GENERAL,
    FILTER_LEVEL_TARGETED,
)


def normalize_filter_level(level: object) -> str:
    text = str(level or FILTER_LEVEL_GENERAL).strip()
    if text == FILTER_LEVEL_TARGETED:
        return FILTER_LEVEL_TARGETED
    return FILTER_LEVEL_GENERAL


def is_targeted_filter(level: object) -> bool:
    return normalize_filter_level(level) == FILTER_LEVEL_TARGETED


def is_finite_number(value: object) -> bool:
    if value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def apply_metric_range(value: object, min_value: float, max_value: float) -> float:
    """Return the value when it is finite and in range, otherwise NaN."""
    if not is_finite_number(value):
        return float("nan")
    number = float(value)
    if min_value <= number <= max_value:
        return number
    return float("nan")


def finite_aligned(*series: Sequence[object]) -> list[tuple[float, ...]]:
    """Keep index-aligned tuples where every value is finite."""
    if not series:
        return []
    n = min(len(item) for item in series)
    rows: list[tuple[float, ...]] = []
    for i in range(n):
        values: list[float] = []
        ok = True
        for item in series:
            if not is_finite_number(item[i]):
                ok = False
                break
            values.append(float(item[i]))
        if ok:
            rows.append(tuple(values))
    return rows


def finite_minmax(values: Sequence[object]) -> tuple[float, float]:
    finite = [float(v) for v in values if is_finite_number(v)]
    if not finite:
        return 0.0, 1.0
    return min(finite), max(finite)


METRIC_BOUND_KEYS: tuple[str, ...] = (
    "min_sold",
    "max_sold",
    "min_price",
    "max_price",
    "min_m",
    "max_m",
)


def unbounded_metric_bounds() -> dict[str, float]:
    return {
        "min_sold": -math.inf,
        "max_sold": math.inf,
        "min_price": -math.inf,
        "max_price": math.inf,
        "min_m": -math.inf,
        "max_m": math.inf,
    }


def merge_metric_bounds(bounds: dict[str, object] | None) -> dict[str, float]:
    merged = unbounded_metric_bounds()
    if not bounds:
        return merged
    for key in METRIC_BOUND_KEYS:
        if key not in bounds:
            continue
        try:
            merged[key] = float(bounds[key])
        except (TypeError, ValueError):
            continue
    return merged


def resolve_level_bound_sets(
    *,
    min_sold: float,
    max_sold: float,
    min_price: float,
    max_price: float,
    min_m: float,
    max_m: float,
    filter_level: object = FILTER_LEVEL_GENERAL,
    general_filters: dict[str, object] | None = None,
    targeted_filters: dict[str, object] | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """Return (general bounds, targeted bounds). Legacy min_* map to one level."""
    if general_filters is not None or targeted_filters is not None:
        return (
            merge_metric_bounds(general_filters),
            merge_metric_bounds(targeted_filters),
        )
    legacy = merge_metric_bounds({
        "min_sold": min_sold,
        "max_sold": max_sold,
        "min_price": min_price,
        "max_price": max_price,
        "min_m": min_m,
        "max_m": max_m,
    })
    if is_targeted_filter(filter_level):
        return unbounded_metric_bounds(), legacy
    return legacy, unbounded_metric_bounds()


def _week_limit(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def combine_week_limits(*ranges: tuple[object, object]) -> tuple[str | None, str | None]:
    """Intersect YYYY-WW windows; blank means no limit."""
    mins = [_week_limit(lo) for lo, _ in ranges]
    maxs = [_week_limit(hi) for _, hi in ranges]
    kept_mins = [week for week in mins if week]
    kept_maxs = [week for week in maxs if week]
    return (
        max(kept_mins) if kept_mins else None,
        min(kept_maxs) if kept_maxs else None,
    )
