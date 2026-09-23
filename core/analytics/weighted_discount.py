"""
Stock / CountProduct / Sold weighted Discount and Prom.

Kept in its own module so Streamlit Cloud can load it even when
core/analytics/week_basket_tables.py is served from an older snapshot.
"""

from __future__ import annotations

import math
from typing import Optional

from core.models import BasketTimeSeries
from core.statistics.metrics import monthly_reserve

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


def _series_value_at(ts: BasketTimeSeries, attr: str, idx: int) -> float:
    series = getattr(ts, attr, None) or []
    if idx >= len(series):
        return float("nan")
    return float(series[idx]) if _is_finite_number(series[idx]) else float("nan")


def aggregate_selected_basket_weeks(
    basket_data: dict[str, BasketTimeSeries],
    baskets: list[str],
    weeks: list[str],
) -> dict[str, object]:
    """
    Weekly Sum-Up of selected baskets: sums, sold-weighted price, and
    Discount/Prom for Stock, CountProduct, and Sold weights.
    """
    selected = {
        str(name): basket_data[str(name)]
        for name in baskets
        if str(name) in basket_data
    }
    week_labels = [str(week) for week in weeks]
    discount_prom = weighted_discount_prom_series_all(selected, week_labels)

    stock: list[float] = []
    count_product: list[float] = []
    purchase: list[float] = []
    sold: list[float] = []
    revenue: list[float] = []
    margin: list[float] = []
    recap: list[float] = []
    weighted_price: list[float] = []
    cost: list[float] = []
    monthly_res: list[float] = []
    sold_to_stock: list[float] = []
    mtost: list[float] = []
    mtosold: list[float] = []
    quadweeks: list[str] = []

    def _sum_attr(attr: str, week: str) -> float:
        total = 0.0
        found = False
        for ts in selected.values():
            idx = _basket_week_index(ts, week)
            if idx is None:
                continue
            value = _series_value_at(ts, attr, idx)
            if not _is_finite_number(value):
                continue
            total += float(value)
            found = True
        return total if found else float("nan")

    for week in week_labels:
        qw = "N/A"
        for ts in selected.values():
            idx = _basket_week_index(ts, week)
            if idx is None or idx >= len(ts.quadweeks):
                continue
            label = str(ts.quadweeks[idx]).strip()
            if label:
                qw = label
                break
        quadweeks.append(qw)

        sum_stock = _sum_attr("stock", week)
        sum_count = _sum_attr("count_product", week)
        sum_purchase = _sum_attr("purchase", week)
        sum_sold = _sum_attr("sold", week)
        sum_margin = _sum_attr("m", week)
        sum_recap = _sum_attr("recap", week)

        sum_revenue = 0.0
        sold_for_price = 0.0
        found_revenue = False
        for ts in selected.values():
            idx = _basket_week_index(ts, week)
            if idx is None:
                continue
            sold_val = _series_value_at(ts, "sold", idx)
            price_val = _series_value_at(ts, "price", idx)
            if not _is_finite_number(sold_val) or not _is_finite_number(price_val):
                continue
            sum_revenue += float(sold_val) * float(price_val)
            sold_for_price += float(sold_val)
            found_revenue = True
        sum_revenue = sum_revenue if found_revenue else float("nan")
        sold_for_price = sold_for_price if found_revenue else float("nan")

        wp = (
            sum_revenue / sold_for_price
            if _is_finite_number(sum_revenue)
            and _is_finite_number(sold_for_price)
            and sold_for_price > 0
            else float("nan")
        )
        cost_ps = (
            wp - (sum_margin / sum_sold)
            if _is_finite_number(wp)
            and _is_finite_number(sum_margin)
            and _is_finite_number(sum_sold)
            and sum_sold > 0
            else float("nan")
        )
        reserve = (
            monthly_reserve(sum_stock, sum_sold)
            if _is_finite_number(sum_stock) and _is_finite_number(sum_sold)
            else float("nan")
        )
        stock.append(sum_stock)
        count_product.append(sum_count)
        purchase.append(sum_purchase)
        sold.append(sum_sold)
        revenue.append(sum_revenue)
        margin.append(sum_margin)
        recap.append(sum_recap)
        weighted_price.append(wp)
        cost.append(cost_ps)
        monthly_res.append(reserve)
        sold_to_stock.append(
            sum_sold / sum_stock
            if _is_finite_number(sum_sold)
            and _is_finite_number(sum_stock)
            and sum_stock != 0
            else float("nan")
        )
        mtost.append(
            sum_margin / sum_stock
            if _is_finite_number(sum_margin)
            and _is_finite_number(sum_stock)
            and sum_stock != 0
            else float("nan")
        )
        mtosold.append(
            sum_margin / sum_sold
            if _is_finite_number(sum_margin)
            and _is_finite_number(sum_sold)
            and sum_sold != 0
            else float("nan")
        )

    return {
        "weeks": week_labels,
        "quadweeks": quadweeks,
        "stock": stock,
        "count_product": count_product,
        "purchase": purchase,
        "sold": sold,
        "revenue": revenue,
        "margin": margin,
        "recap": recap,
        "weighted_price": weighted_price,
        "cost": cost,
        "monthly_reserve": monthly_res,
        "sold_to_stock": sold_to_stock,
        "mtost": mtost,
        "mtosold": mtosold,
        "discount_by_weight": {
            metric: series[0] for metric, series in discount_prom.items()
        },
        "prom_by_weight": {
            metric: series[1] for metric, series in discount_prom.items()
        },
    }


def combined_basket_time_series(
    agg: dict[str, object],
    basket: str = "Combination",
) -> BasketTimeSeries:
    """Turn a selected-basket weekly aggregate into a BasketTimeSeries for Detail plots."""
    weeks = [str(week) for week in (agg.get("weeks") or [])]
    n = len(weeks)
    quadweeks = [str(label) for label in (agg.get("quadweeks") or [])]
    if len(quadweeks) < n:
        quadweeks.extend(["N/A"] * (n - len(quadweeks)))

    def _col(key: str) -> list[float]:
        raw = list(agg.get(key) or [])
        values: list[float] = []
        for i in range(n):
            if i < len(raw) and _is_finite_number(raw[i]):
                values.append(float(raw[i]))
            else:
                values.append(float("nan"))
        return values

    price = _col("weighted_price")
    sold = _col("sold")
    stock = _col("stock")
    margin = _col("margin")
    cost = _col("cost")
    count_product = _col("count_product")
    purchase = _col("purchase")
    recap = _col("recap")
    return BasketTimeSeries(
        basket=basket,
        weeks=weeks,
        quadweeks=quadweeks[:n],
        sold=sold,
        price=price,
        m=margin,
        stock=stock,
        cost=cost,
        count_product=count_product,
        purchase=purchase,
        recap=recap,
        week_in_quad=[0] * n,
    )
