"""
Stock / CountProduct / Sold weighted Discount and Prom.

Kept in its own module so Streamlit Cloud can load it even when
core/analytics/week_basket_tables.py is served from an older snapshot.
"""

from __future__ import annotations

import math
from typing import Optional

from core.models import BasketTimeSeries

DISCOUNT_PROM_WEIGHT_CHOICES: tuple[str, ...] = ("Stock", "CountProduct", "Sold")
DISCOUNT_PROM_WEIGHT_METRICS: tuple[str, ...] = ("stock", "count_product", "sold")
DISCOUNT_PROM_WEIGHT_KEYS: dict[str, str] = {
    "Stock": "stock",
    "CountProduct": "count_product",
    "Sold": "sold",
}
DISCOUNT_PROM_WEIGHT_FILTER_KEYS: dict[str, str] = {
    "stock": "stock_current",
    "count_product": "count_product_current",
    "sold": "sold_current",
}
DISCOUNT_PROM_WEIGHT_SERIES_ATTRS: dict[str, str] = {
    "stock": "stock",
    "count_product": "count_product",
    "sold": "sold",
}
DISCOUNT_PROM_WEIGHT_PREFIX: dict[str, str] = {
    "stock": "W.S.",
    "count_product": "W.C.",
    "sold": "W.Sold",
}
NEW_DISCOUNT_COLUMN = "New Discount"
NEW_PROM_COLUMN = "New Prom"


def discount_prom_weight_key(label: str) -> str:
    return DISCOUNT_PROM_WEIGHT_KEYS.get(str(label), "stock")


def discount_prom_weight_prefix(weight_metric: str) -> str:
    return DISCOUNT_PROM_WEIGHT_PREFIX.get(weight_metric, "W.S.")


def discount_prom_weight_column_labels(weight_metric: str) -> tuple[str, str]:
    prefix = discount_prom_weight_prefix(weight_metric)
    return f"{prefix} Discount", f"{prefix} Prom"


def _is_finite_number(value: object) -> bool:
    if value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def _is_positive_weight(value: object) -> bool:
    return _is_finite_number(value) and float(value) > 0


def _basket_week_index(ts: BasketTimeSeries, week: str) -> Optional[int]:
    week_str = str(week)
    for i, w in enumerate(ts.weeks):
        if str(w) == week_str:
            return i
    return None


def _group_column_at_offset(
    column_meta: dict[str, dict[str, object]],
    group: str,
    offset: int,
) -> str:
    for col, meta in column_meta.items():
        if (
            meta.get("group") == group
            and meta.get("offset") == offset
            and not meta.get("is_delta")
        ):
            return col
    return ""


def compute_week_discount_weighted_comparisons(
    rows: list[dict],
    column_meta: dict[str, dict[str, object]],
    filter_map: dict[str, str],
) -> dict[str, dict[str, dict[str, float | int]]]:
    """Precompute Discount/Prom weighted by Stock, CountProduct, and Sold."""
    periods = {
        "current_minus_1w": (
            _group_column_at_offset(column_meta, "discount", -1),
            _group_column_at_offset(column_meta, "prom", -1),
        ),
        "current": (
            filter_map.get("discount_current", ""),
            filter_map.get("prom_current", ""),
        ),
        "new": (NEW_DISCOUNT_COLUMN, NEW_PROM_COLUMN),
    }
    acc: dict[str, dict[str, dict[str, float | int]]] = {
        metric: {
            period: {"d_num": 0.0, "p_num": 0.0, "den": 0.0, "count_Prom": 0}
            for period in periods
        }
        for metric in DISCOUNT_PROM_WEIGHT_METRICS
    }
    for row in rows:
        for metric in DISCOUNT_PROM_WEIGHT_METRICS:
            weight_col = filter_map.get(
                DISCOUNT_PROM_WEIGHT_FILTER_KEYS[metric],
                "",
            )
            weight_val = row.get(weight_col) if weight_col else None
            if not _is_positive_weight(weight_val):
                continue
            weight = float(weight_val)
            for period, (discount_col, prom_col) in periods.items():
                block = acc[metric][period]
                block["den"] = float(block["den"]) + weight
                discount_val = row.get(discount_col) if discount_col else None
                if _is_finite_number(discount_val):
                    block["d_num"] = float(block["d_num"]) + float(discount_val) * weight
                prom_val = row.get(prom_col) if prom_col else None
                if _is_finite_number(prom_val):
                    block["p_num"] = float(block["p_num"]) + float(prom_val) * weight
                    if float(prom_val) > 0:
                        block["count_Prom"] = int(block["count_Prom"]) + 1

    result: dict[str, dict[str, dict[str, float | int]]] = {}
    for metric in DISCOUNT_PROM_WEIGHT_METRICS:
        result[metric] = {}
        for period in periods:
            block = acc[metric][period]
            den = float(block["den"])
            result[metric][period] = {
                "W_Discount": float(block["d_num"]) / den if den > 0 else float("nan"),
                "W_Prom": float(block["p_num"]) / den if den > 0 else float("nan"),
                "count_Prom": int(block["count_Prom"]),
            }
    return result


def compute_week_discount_weighted_comparison(
    rows: list[dict],
    column_meta: dict[str, dict[str, object]],
    filter_map: dict[str, str],
    weight_metric: str = "stock",
) -> dict[str, dict[str, float | int]]:
    """One weight variant from the precomputed Stock/CountProduct/Sold set."""
    all_comparisons = compute_week_discount_weighted_comparisons(
        rows,
        column_meta,
        filter_map,
    )
    if weight_metric in all_comparisons:
        return all_comparisons[weight_metric]
    return all_comparisons["stock"]


def weighted_discount_prom_series_all(
    basket_data: dict[str, BasketTimeSeries],
    weeks: list[str],
) -> dict[str, tuple[list[float], list[float]]]:
    """Precompute per-week Discount/Prom for Stock, CountProduct, and Sold weights."""
    discounts: dict[str, list[float]] = {
        metric: [] for metric in DISCOUNT_PROM_WEIGHT_METRICS
    }
    proms: dict[str, list[float]] = {
        metric: [] for metric in DISCOUNT_PROM_WEIGHT_METRICS
    }
    for week in weeks:
        discount_num = {metric: 0.0 for metric in DISCOUNT_PROM_WEIGHT_METRICS}
        prom_num = {metric: 0.0 for metric in DISCOUNT_PROM_WEIGHT_METRICS}
        weight_den = {metric: 0.0 for metric in DISCOUNT_PROM_WEIGHT_METRICS}
        for ts in basket_data.values():
            idx = _basket_week_index(ts, str(week))
            if idx is None:
                continue
            discount_val = (
                ts.discount[idx] if idx < len(ts.discount) else float("nan")
            )
            prom_val = ts.prom[idx] if idx < len(ts.prom) else float("nan")
            for metric, attr in DISCOUNT_PROM_WEIGHT_SERIES_ATTRS.items():
                weights = getattr(ts, attr, None) or []
                if idx >= len(weights) or not _is_positive_weight(weights[idx]):
                    continue
                weight = float(weights[idx])
                weight_den[metric] += weight
                if _is_finite_number(discount_val):
                    discount_num[metric] += float(discount_val) * weight
                if _is_finite_number(prom_val):
                    prom_num[metric] += float(prom_val) * weight
        for metric in DISCOUNT_PROM_WEIGHT_METRICS:
            den = weight_den[metric]
            discounts[metric].append(
                discount_num[metric] / den if den > 0 else float("nan")
            )
            proms[metric].append(
                prom_num[metric] / den if den > 0 else float("nan")
            )
    return {
        metric: (discounts[metric], proms[metric])
        for metric in DISCOUNT_PROM_WEIGHT_METRICS
    }


def weighted_discount_prom_series(
    basket_data: dict[str, BasketTimeSeries],
    weeks: list[str],
    weight_metric: str = "stock",
) -> tuple[list[float], list[float]]:
    """One per-week series from the precomputed Stock/CountProduct/Sold set."""
    all_series = weighted_discount_prom_series_all(basket_data, weeks)
    if weight_metric in all_series:
        return all_series[weight_metric]
    return all_series["stock"]
