"""
Weekly Sum-Up of selected baskets for Combination / Group Basket Detail.

Kept in its own module so Streamlit Cloud can load it even when
core/analytics/weighted_discount.py is served from an older snapshot.
"""

from __future__ import annotations

import math
from typing import Optional

from core.analytics.weighted_discount import weighted_discount_prom_series_all
from core.models import BasketTimeSeries
from core.statistics.metrics import monthly_reserve


def _is_finite_number(value: object) -> bool:
    if value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def _basket_week_index(ts: BasketTimeSeries, week: str) -> Optional[int]:
    week_str = str(week)
    for i, w in enumerate(ts.weeks):
        if str(w) == week_str:
            return i
    return None


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
