"""
Per-basket week tables for Sum-Up drill-down views.

Pure analytics — no Streamlit imports.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional

from core.models import BasketTimeSeries, WeeklyTotal
from core.statistics.metrics import monthly_reserve


def ratio_change(current: float, previous: float) -> float:
    """Relative change: current / previous - 1."""
    if (
        previous is None
        or current is None
        or math.isnan(previous)
        or math.isnan(current)
        or previous == 0
    ):
        return float("nan")
    return current / previous - 1.0


def week_at_offset(all_weeks: list[str], current_week: str, offset: int) -> Optional[str]:
    """Resolve a week label relative to the chronological week list."""
    try:
        idx = next(i for i, w in enumerate(all_weeks) if str(w) == str(current_week))
    except StopIteration:
        return None
    target = idx + offset
    if target < 0 or target >= len(all_weeks):
        return None
    return str(all_weeks[target])


def metric_header(
    weekly_totals: dict[str, WeeklyTotal],
    week: Optional[str],
    prefix: str,
    week_offset: Optional[int] = None,
) -> str:
    """Build a column header like Stock[19,1] from week metadata."""
    offset_tag = f"|W{week_offset}" if week_offset is not None else ""
    if week is None:
        return f"{prefix}[?,?{offset_tag}]"
    wt = weekly_totals.get(str(week))
    if wt is None:
        return f"{prefix}[?,?{offset_tag}]"
    wiq = wt.week_in_quad if wt.week_in_quad else "?"
    qw = wt.quadweek if wt.quadweek and wt.quadweek != "N/A" else "?"
    if qw == "?" and wiq == "?" and week_offset is not None:
        return f"{prefix}[?,?{offset_tag}]"
    return f"{prefix}[{qw},{wiq}]"


def _basket_week_index(ts: BasketTimeSeries, week: str) -> Optional[int]:
    week_str = str(week)
    for i, w in enumerate(ts.weeks):
        if str(w) == week_str:
            return i
    return None


def _basket_metric_at_week(
    ts: BasketTimeSeries,
    week: Optional[str],
    getter: Callable[[BasketTimeSeries, int], float],
) -> float:
    if week is None:
        return float("nan")
    idx = _basket_week_index(ts, week)
    if idx is None:
        return float("nan")
    return float(getter(ts, idx))


def _basket_cost(ts: BasketTimeSeries, idx: int) -> float:
    if idx < len(ts.cost):
        return float(ts.cost[idx])
    sold = ts.sold[idx]
    if sold <= 0:
        return 0.0
    return float((ts.sold[idx] * ts.price[idx] - ts.m[idx]) / sold)


def _basket_count_product(ts: BasketTimeSeries, idx: int) -> float:
    if idx < len(ts.count_product):
        val = ts.count_product[idx]
        return float(val) if not math.isnan(val) else 0.0
    return 0.0


def _basket_purchase(ts: BasketTimeSeries, idx: int) -> float:
    if idx < len(ts.purchase):
        val = ts.purchase[idx]
        return float(val) if not math.isnan(val) else 0.0
    return 0.0


def _basket_monthly_reserve(ts: BasketTimeSeries, idx: int) -> float:
    return monthly_reserve(float(ts.stock[idx]), float(ts.sold[idx]))


def _basket_discount(ts: BasketTimeSeries, idx: int) -> float:
    if idx < len(ts.discount):
        val = ts.discount[idx]
        return float(val) if not math.isnan(val) else float("nan")
    return float("nan")


def _basket_prom(ts: BasketTimeSeries, idx: int) -> float:
    if idx < len(ts.prom):
        val = ts.prom[idx]
        return float(val) if not math.isnan(val) else float("nan")
    return float("nan")


def compute_basket_week_detail_rows(
    basket_data: dict[str, BasketTimeSeries],
    weekly_totals: dict[str, WeeklyTotal],
    selected_week: str,
) -> list[dict]:
    """
    Per-basket rows for the selected week — same fields as Sum-Up minus correlations.
    """
    wt = weekly_totals.get(str(selected_week))
    if wt is None:
        return []

    rows: list[dict] = []
    for pt in sorted(wt.points, key=lambda p: str(p.basket)):
        ts = basket_data.get(str(pt.basket))
        sold = float(pt.sold)
        price = float(pt.price)
        stock = float(pt.stock)
        margin = float(pt.m)
        revenue = sold * price
        cost = (
            ((sold * price) - margin) / sold
            if sold > 0
            else (
                _basket_metric_at_week(ts, selected_week, _basket_cost)
                if ts is not None
                else 0.0
            )
        )

        rows.append({
            "Basket": str(pt.basket),
            "QW": wt.quadweek,
            "Week": str(selected_week),
            "week in QW": wt.week_in_quad or "",
            "W. Price": round(price, 2),
            "Total Stock": round(stock, 2),
            "Total CountProduct": round(float(pt.count_product), 2),
            "Total Purchase": round(float(pt.purchase), 2),
            "Total Sold": round(sold, 2),
            "Total Revenue": round(revenue, 2),
            "Total Margin": round(margin, 2),
            "Cost": round(cost, 2),
            "Total Monthly Reserve": round(monthly_reserve(stock, sold), 2)
            if not math.isnan(monthly_reserve(stock, sold))
            else float("nan"),
        })

    return rows


DISCOUNT_WEEK_OFFSETS = (0, -1, -4, -5)
DISCOUNT_QW_OFFSET = -4
DISCOUNT_QW_IDX = DISCOUNT_WEEK_OFFSETS.index(DISCOUNT_QW_OFFSET)

# Light / dark background pairs aligned with Basket Detail metric colours.
WEEK_DISCOUNT_GROUP_COLORS: dict[str, tuple[str, str]] = {
    "discount": ("#ffe4e6", "#fda4af"),
    "prom": ("#e0e7ff", "#a5b4fc"),
    "stock": ("#fce7f3", "#f9a8d4"),
    "margin": ("#ede9fe", "#c4b5fd"),
    "mtost": ("#cffafe", "#67e8f9"),
    "sold": ("#dbeafe", "#93c5fd"),
    "price": ("#d1fae5", "#6ee7b7"),
    "reserve": ("#fef3c7", "#fcd34d"),
    "count_product": ("#e0f2fe", "#7dd3fc"),
}

_DELTA_COLUMN_TO_GROUP: dict[str, str] = {
    "dSt_QW": "stock",
    "dM_QW": "margin",
    "dMtoSt_QW": "mtost",
    "dSold_QW": "sold",
    "dPrice_QW": "price",
    "dRes_QW": "reserve",
}

MONTHLY_RESERVE_HEADER_PREFIX = "Monthly Reserve"
COUNT_PRODUCT_HEADER_PREFIX = "Count Product"
DISCOUNT_HEADER_PREFIX = "Discount"
PROM_HEADER_PREFIX = "Prom"
NEW_DISCOUNT_COLUMN = "New Discount"
NEW_PROM_COLUMN = "New Prom"
D_DISCOUNT_COLUMN = "dDiscount"
D_PROM_COLUMN = "dProm"

# Slightly stronger shades for generated / delta discount-prom columns.
WEEK_DISCOUNT_NEW_COLORS: dict[str, str] = {
    NEW_DISCOUNT_COLUMN: "#fecdd3",
    NEW_PROM_COLUMN: "#c7d2fe",
    D_DISCOUNT_COLUMN: "#fda4af",
    D_PROM_COLUMN: "#a5b4fc",
}


@dataclass(frozen=True)
class WeekDiscountViewSettings:
    show_discount: bool = False
    show_prom: bool = False
    show_stock: bool = True
    show_margin: bool = True
    show_mtost: bool = True
    show_sold: bool = True
    show_price: bool = True
    show_reserve: bool = False
    show_count_product: bool = False
    show_w1: bool = True
    show_w4: bool = True
    show_w5: bool = True


def week_discount_column_group(column: str) -> Optional[tuple[str, bool]]:
    """
    Map a Week Discount column to (metric_group, is_delta_column).

    Returns None for Basket and unknown columns.
    """
    if column == "Basket":
        return None
    if column in _DELTA_COLUMN_TO_GROUP:
        return _DELTA_COLUMN_TO_GROUP[column], True
    if column == NEW_DISCOUNT_COLUMN:
        return "discount", False
    if column == D_DISCOUNT_COLUMN:
        return "discount", True
    if column == NEW_PROM_COLUMN:
        return "prom", False
    if column == D_PROM_COLUMN:
        return "prom", True
    if column.startswith(f"{DISCOUNT_HEADER_PREFIX}["):
        return "discount", False
    if column.startswith(f"{PROM_HEADER_PREFIX}["):
        return "prom", False
    if column.startswith("Stock["):
        return "stock", False
    if column.startswith("Margin["):
        return "margin", False
    if column.startswith("MtoSt["):
        return "mtost", False
    if column.startswith("Sold["):
        return "sold", False
    if column.startswith("Price["):
        return "price", False
    if column.startswith(f"{MONTHLY_RESERVE_HEADER_PREFIX}["):
        return "reserve", False
    if column.startswith(f"{COUNT_PRODUCT_HEADER_PREFIX}["):
        return "count_product", False
    return None


def week_discount_column_background(column: str) -> Optional[str]:
    """CSS background colour for a Week Discount column header/cells."""
    if column in WEEK_DISCOUNT_NEW_COLORS:
        return WEEK_DISCOUNT_NEW_COLORS[column]
    grouped = week_discount_column_group(column)
    if grouped is None:
        return None
    group, is_delta = grouped
    light, dark = WEEK_DISCOUNT_GROUP_COLORS[group]
    return dark if is_delta else light


def week_discount_value_kind(column: str) -> str:
    """Return display/filter kind: text, delta_pct, integer, currency, mtost."""
    if column == "Basket":
        return "text"
    grouped = week_discount_column_group(column)
    if grouped is None:
        return "text"
    group, is_delta = grouped
    if is_delta or group in ("discount", "prom"):
        return "delta_pct"
    if group in ("stock", "sold", "count_product"):
        return "integer"
    if group in ("margin", "price"):
        return "currency"
    if group == "mtost":
        return "mtost"
    if group == "reserve":
        return "reserve"
    return "text"


def week_discount_filter_label_kind(label: str) -> str:
    """Map compact filter labels to value kinds."""
    if label.startswith("d"):
        return "delta_pct"
    if label in ("Discount", "Prom", NEW_DISCOUNT_COLUMN, NEW_PROM_COLUMN):
        return "delta_pct"
    if label in (D_DISCOUNT_COLUMN, D_PROM_COLUMN):
        return "delta_pct"
    if label in ("Stock", "Sold", "Count Product"):
        return "integer"
    if label in ("Margin", "Price"):
        return "currency"
    if label == "MtoSt":
        return "mtost"
    if label == "Monthly Reserve":
        return "reserve"
    return "text"


def format_week_discount_value(column: str, value: object) -> str:
    """Format a Week Discount cell for display."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    val = float(value)
    kind = week_discount_value_kind(column)
    if kind == "delta_pct":
        return f"{val * 100:.2f}%"
    if kind == "integer":
        return f"{round(val):.0f}"
    if kind == "currency":
        return f"${val:,.2f}"
    if kind == "mtost":
        return f"{val:.3f}"
    if kind == "reserve":
        return f"{val:.2f}"
    return str(value)


def parse_week_discount_filter_value(label: str, value: object) -> Optional[float]:
    """Parse filter-table input into raw row-comparable values."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        parsed = float(value)
    else:
        raw = str(value).strip().replace("$", "").replace("%", "").replace(",", "")
        if not raw:
            return None
        try:
            parsed = float(raw)
        except ValueError:
            return None

    kind = week_discount_filter_label_kind(label)
    if kind == "delta_pct":
        return parsed / 100.0
    if kind == "integer":
        return float(round(parsed))
    return parsed


def build_week_discount_weeks_by_offset(
    all_weeks: list[str],
    selected_week: str,
) -> dict[int, Optional[str]]:
    return {
        off: week_at_offset(all_weeks, selected_week, off)
        for off in DISCOUNT_WEEK_OFFSETS
    }


def build_week_discount_column_meta(
    weekly_totals: dict[str, WeeklyTotal],
    all_weeks: list[str],
    selected_week: str,
) -> dict[str, dict[str, object]]:
    """Map each Week Discount column to group / week-offset metadata."""
    weeks_by_offset = build_week_discount_weeks_by_offset(all_weeks, selected_week)
    week_qw_ago = weeks_by_offset[DISCOUNT_QW_OFFSET]

    meta: dict[str, dict[str, object]] = {
        "Basket": {"group": None, "offset": None, "is_delta": False},
    }

    meta["New Discount"] = {"group": "discount", "offset": 0, "is_delta": False}
    meta["dDiscount"] = {"group": "discount", "offset": None, "is_delta": True}
    for off in DISCOUNT_WEEK_OFFSETS:
        col = metric_header(
            weekly_totals, weeks_by_offset[off], DISCOUNT_HEADER_PREFIX, week_offset=off,
        )
        meta[col] = {"group": "discount", "offset": off, "is_delta": False}

    meta["New Prom"] = {"group": "prom", "offset": 0, "is_delta": False}
    meta["dProm"] = {"group": "prom", "offset": None, "is_delta": True}
    for off in DISCOUNT_WEEK_OFFSETS:
        col = metric_header(
            weekly_totals, weeks_by_offset[off], PROM_HEADER_PREFIX, week_offset=off,
        )
        meta[col] = {"group": "prom", "offset": off, "is_delta": False}

    stock_delta = "dSt_QW"
    meta[stock_delta] = {"group": "stock", "offset": None, "is_delta": True}
    for off in DISCOUNT_WEEK_OFFSETS:
        col = metric_header(weekly_totals, weeks_by_offset[off], "Stock", week_offset=off)
        meta[col] = {"group": "stock", "offset": off, "is_delta": False}

    margin_delta = "dM_QW"
    meta[margin_delta] = {"group": "margin", "offset": None, "is_delta": True}
    for off in DISCOUNT_WEEK_OFFSETS:
        col = metric_header(weekly_totals, weeks_by_offset[off], "Margin", week_offset=off)
        meta[col] = {"group": "margin", "offset": off, "is_delta": False}

    meta["dMtoSt_QW"] = {"group": "mtost", "offset": None, "is_delta": True}
    mto_st_cur = metric_header(weekly_totals, weeks_by_offset[0], "MtoSt", week_offset=0)
    mto_st_qw = metric_header(
        weekly_totals, week_qw_ago, "MtoSt", week_offset=DISCOUNT_QW_OFFSET,
    )
    meta[mto_st_cur] = {"group": "mtost", "offset": 0, "is_delta": False}
    meta[mto_st_qw] = {"group": "mtost", "offset": DISCOUNT_QW_OFFSET, "is_delta": False}

    sold_delta = "dSold_QW"
    meta[sold_delta] = {"group": "sold", "offset": None, "is_delta": True}
    for off in DISCOUNT_WEEK_OFFSETS:
        col = metric_header(weekly_totals, weeks_by_offset[off], "Sold", week_offset=off)
        meta[col] = {"group": "sold", "offset": off, "is_delta": False}

    price_delta = "dPrice_QW"
    meta[price_delta] = {"group": "price", "offset": None, "is_delta": True}
    for off in DISCOUNT_WEEK_OFFSETS:
        col = metric_header(weekly_totals, weeks_by_offset[off], "Price", week_offset=off)
        meta[col] = {"group": "price", "offset": off, "is_delta": False}

    reserve_delta = "dRes_QW"
    meta[reserve_delta] = {"group": "reserve", "offset": None, "is_delta": True}
    for off in DISCOUNT_WEEK_OFFSETS:
        col = metric_header(
            weekly_totals,
            weeks_by_offset[off],
            MONTHLY_RESERVE_HEADER_PREFIX,
            week_offset=off,
        )
        meta[col] = {"group": "reserve", "offset": off, "is_delta": False}

    for off in DISCOUNT_WEEK_OFFSETS:
        col = metric_header(
            weekly_totals,
            weeks_by_offset[off],
            COUNT_PRODUCT_HEADER_PREFIX,
            week_offset=off,
        )
        meta[col] = {"group": "count_product", "offset": off, "is_delta": False}

    return meta


def select_visible_week_discount_columns(
    columns: list[str],
    column_meta: dict[str, dict[str, object]],
    settings: WeekDiscountViewSettings,
) -> list[str]:
    """Apply metric-group and week-offset visibility toggles."""
    group_flags = {
        "discount": settings.show_discount,
        "prom": settings.show_prom,
        "stock": settings.show_stock,
        "margin": settings.show_margin,
        "mtost": settings.show_mtost,
        "sold": settings.show_sold,
        "price": settings.show_price,
        "reserve": settings.show_reserve,
        "count_product": settings.show_count_product,
    }
    hidden_offsets: set[int] = set()
    if not settings.show_w1:
        hidden_offsets.add(-1)
    if not settings.show_w4:
        hidden_offsets.add(-4)
    if not settings.show_w5:
        hidden_offsets.add(-5)

    visible: list[str] = []
    for col in columns:
        meta = column_meta.get(col)
        if col == "Basket" or meta is None:
            if col == "Basket":
                visible.append(col)
            continue

        group = meta.get("group")
        if group and not group_flags.get(str(group), True):
            continue

        if meta.get("is_delta"):
            visible.append(col)
            continue

        offset = meta.get("offset")
        if offset in hidden_offsets:
            continue

        visible.append(col)

    return visible


def week_discount_historical_current_column(
    column_meta: dict[str, dict[str, object]],
    group: str,
) -> str:
    """
    Return the current-week historical level column for a metric group.

    Uses Prom[…] / Discount[…], not New Prom / New Discount. Those generated
    columns share offset 0 and must not be used as the current baseline for
    dProm / dDiscount.
    """
    generated = {NEW_DISCOUNT_COLUMN, NEW_PROM_COLUMN}
    fallback = ""
    for col, meta in column_meta.items():
        if (
            meta.get("group") == group
            and meta.get("offset") == 0
            and not meta.get("is_delta")
        ):
            if col in generated:
                fallback = col
                continue
            return col
    return fallback


def week_discount_filter_columns(
    column_meta: dict[str, dict[str, object]],
) -> dict[str, str]:
    """
    Resolve compact filter keys to actual column names.

    Keys: dSt_QW, stock_current, dM_QW, margin_current, dMtoSt_QW,
    mtost_current, dSold_QW, sold_current, dPrice_QW, price_current,
    dRes_QW, reserve_current.
    """
    delta_by_group: dict[str, str] = {}

    for col, meta in column_meta.items():
        group = meta.get("group")
        if not group:
            continue
        if meta.get("is_delta"):
            delta_by_group[str(group)] = col

    return {
        "new_discount": "New Discount",
        "d_discount": "dDiscount",
        "discount_current": week_discount_historical_current_column(
            column_meta, "discount",
        ),
        "new_prom": "New Prom",
        "d_prom": "dProm",
        "prom_current": week_discount_historical_current_column(
            column_meta, "prom",
        ),
        "dSt_QW": delta_by_group.get("stock", "dSt_QW"),
        "stock_current": week_discount_historical_current_column(
            column_meta, "stock",
        ),
        "dM_QW": delta_by_group.get("margin", "dM_QW"),
        "margin_current": week_discount_historical_current_column(
            column_meta, "margin",
        ),
        "dMtoSt_QW": delta_by_group.get("mtost", "dMtoSt_QW"),
        "mtost_current": week_discount_historical_current_column(
            column_meta, "mtost",
        ),
        "dSold_QW": delta_by_group.get("sold", "dSold_QW"),
        "sold_current": week_discount_historical_current_column(
            column_meta, "sold",
        ),
        "dPrice_QW": delta_by_group.get("price", "dPrice_QW"),
        "price_current": week_discount_historical_current_column(
            column_meta, "price",
        ),
        "dRes_QW": delta_by_group.get("reserve", "dRes_QW"),
        "reserve_current": week_discount_historical_current_column(
            column_meta, "reserve",
        ),
        "count_product_current": week_discount_historical_current_column(
            column_meta, "count_product",
        ),
    }


def apply_week_discount_filters(
    rows: list[dict],
    bounds: dict[str, tuple[Optional[float], Optional[float]]],
) -> list[dict]:
    """Keep rows whose values fall within optional min/max bounds per column."""
    if not rows or not bounds:
        return rows

    filtered: list[dict] = []
    for row in rows:
        keep = True
        for col, (lo, hi) in bounds.items():
            if not col or col not in row:
                continue
            value = row[col]
            if value is None or (isinstance(value, float) and math.isnan(value)):
                keep = False
                break
            if lo is not None and float(value) < lo:
                keep = False
                break
            if hi is not None and float(value) > hi:
                keep = False
                break
        if keep:
            filtered.append(row)

    return filtered


def build_week_discount_columns(
    weekly_totals: dict[str, WeeklyTotal],
    all_weeks: list[str],
    selected_week: str,
) -> list[str]:
    """Ordered column names for the Week Discount table."""
    return list(
        build_week_discount_column_meta(weekly_totals, all_weeks, selected_week).keys()
    )


def compute_basket_week_discount_rows(
    basket_data: dict[str, BasketTimeSeries],
    weekly_totals: dict[str, WeeklyTotal],
    all_weeks: list[str],
    selected_week: str,
) -> tuple[list[dict], list[str]]:
    """
    Per-basket Week Discount rows with dynamic QW/week column headers.
    """
    wt = weekly_totals.get(str(selected_week))
    if wt is None:
        return [], []

    columns = build_week_discount_columns(weekly_totals, all_weeks, selected_week)
    weeks_by_offset = build_week_discount_weeks_by_offset(all_weeks, selected_week)
    week_qw_ago = weeks_by_offset[DISCOUNT_QW_OFFSET]

    discount_headers = [
        metric_header(
            weekly_totals, weeks_by_offset[off], DISCOUNT_HEADER_PREFIX, week_offset=off,
        )
        for off in DISCOUNT_WEEK_OFFSETS
    ]
    prom_headers = [
        metric_header(
            weekly_totals, weeks_by_offset[off], PROM_HEADER_PREFIX, week_offset=off,
        )
        for off in DISCOUNT_WEEK_OFFSETS
    ]
    stock_headers = [
        metric_header(weekly_totals, weeks_by_offset[off], "Stock", week_offset=off)
        for off in DISCOUNT_WEEK_OFFSETS
    ]
    margin_headers = [
        metric_header(weekly_totals, weeks_by_offset[off], "Margin", week_offset=off)
        for off in DISCOUNT_WEEK_OFFSETS
    ]
    sold_headers = [
        metric_header(weekly_totals, weeks_by_offset[off], "Sold", week_offset=off)
        for off in DISCOUNT_WEEK_OFFSETS
    ]
    price_headers = [
        metric_header(weekly_totals, weeks_by_offset[off], "Price", week_offset=off)
        for off in DISCOUNT_WEEK_OFFSETS
    ]
    reserve_headers = [
        metric_header(
            weekly_totals,
            weeks_by_offset[off],
            MONTHLY_RESERVE_HEADER_PREFIX,
            week_offset=off,
        )
        for off in DISCOUNT_WEEK_OFFSETS
    ]
    count_product_headers = [
        metric_header(
            weekly_totals,
            weeks_by_offset[off],
            COUNT_PRODUCT_HEADER_PREFIX,
            week_offset=off,
        )
        for off in DISCOUNT_WEEK_OFFSETS
    ]
    mto_st_cur_header = metric_header(
        weekly_totals, weeks_by_offset[0], "MtoSt", week_offset=0,
    )
    mto_st_qw_header = metric_header(
        weekly_totals, week_qw_ago, "MtoSt", week_offset=DISCOUNT_QW_OFFSET,
    )

    rows: list[dict] = []
    for pt in sorted(wt.points, key=lambda p: str(p.basket)):
        ts = basket_data.get(str(pt.basket))
        if ts is None:
            continue

        stocks = [
            _basket_metric_at_week(ts, weeks_by_offset[off], lambda t, i: t.stock[i])
            for off in DISCOUNT_WEEK_OFFSETS
        ]
        margins = [
            _basket_metric_at_week(ts, weeks_by_offset[off], lambda t, i: t.m[i])
            for off in DISCOUNT_WEEK_OFFSETS
        ]
        solds = [
            _basket_metric_at_week(ts, weeks_by_offset[off], lambda t, i: t.sold[i])
            for off in DISCOUNT_WEEK_OFFSETS
        ]
        prices = [
            _basket_metric_at_week(ts, weeks_by_offset[off], lambda t, i: t.price[i])
            for off in DISCOUNT_WEEK_OFFSETS
        ]
        discounts = [
            _basket_metric_at_week(ts, weeks_by_offset[off], _basket_discount)
            for off in DISCOUNT_WEEK_OFFSETS
        ]
        proms = [
            _basket_metric_at_week(ts, weeks_by_offset[off], _basket_prom)
            for off in DISCOUNT_WEEK_OFFSETS
        ]
        reserves = [
            _basket_metric_at_week(ts, weeks_by_offset[off], _basket_monthly_reserve)
            for off in DISCOUNT_WEEK_OFFSETS
        ]
        count_products = [
            _basket_metric_at_week(ts, weeks_by_offset[off], _basket_count_product)
            for off in DISCOUNT_WEEK_OFFSETS
        ]

        mto_st_cur = (
            margins[0] / stocks[0]
            if not math.isnan(margins[0]) and not math.isnan(stocks[0]) and stocks[0] != 0
            else float("nan")
        )
        mto_st_qw = _basket_metric_at_week(
            ts,
            week_qw_ago,
            lambda t, i: t.m[i] / t.stock[i] if t.stock[i] != 0 else float("nan"),
        )

        row: dict = {"Basket": str(pt.basket)}

        row["New Discount"] = (
            round(discounts[0], 4) if not math.isnan(discounts[0]) else float("nan")
        )
        for header, value in zip(discount_headers, discounts):
            row[header] = round(value, 4) if not math.isnan(value) else float("nan")

        row["New Prom"] = round(proms[0], 4) if not math.isnan(proms[0]) else float("nan")
        for header, value in zip(prom_headers, proms):
            row[header] = round(value, 4) if not math.isnan(value) else float("nan")

        row[D_DISCOUNT_COLUMN] = float("nan")
        row[D_PROM_COLUMN] = float("nan")

        d_st = ratio_change(stocks[0], stocks[DISCOUNT_QW_IDX])
        row["dSt_QW"] = round(d_st, 4) if not math.isnan(d_st) else float("nan")
        for header, value in zip(stock_headers, stocks):
            row[header] = round(value, 2) if not math.isnan(value) else float("nan")

        d_m = ratio_change(margins[0], margins[DISCOUNT_QW_IDX])
        row["dM_QW"] = round(d_m, 4) if not math.isnan(d_m) else float("nan")
        for header, value in zip(margin_headers, margins):
            row[header] = round(value, 2) if not math.isnan(value) else float("nan")

        d_mto_st = ratio_change(mto_st_cur, mto_st_qw)
        row["dMtoSt_QW"] = round(d_mto_st, 4) if not math.isnan(d_mto_st) else float("nan")
        row[mto_st_cur_header] = round(mto_st_cur, 4) if not math.isnan(mto_st_cur) else float("nan")
        row[mto_st_qw_header] = round(mto_st_qw, 4) if not math.isnan(mto_st_qw) else float("nan")

        d_sold = ratio_change(solds[0], solds[DISCOUNT_QW_IDX])
        row["dSold_QW"] = round(d_sold, 4) if not math.isnan(d_sold) else float("nan")
        for header, value in zip(sold_headers, solds):
            row[header] = round(value, 2) if not math.isnan(value) else float("nan")

        d_price = ratio_change(prices[0], prices[DISCOUNT_QW_IDX])
        row["dPrice_QW"] = round(d_price, 4) if not math.isnan(d_price) else float("nan")
        for header, value in zip(price_headers, prices):
            row[header] = round(value, 2) if not math.isnan(value) else float("nan")

        d_res = ratio_change(reserves[0], reserves[DISCOUNT_QW_IDX])
        row["dRes_QW"] = round(d_res, 4) if not math.isnan(d_res) else float("nan")
        for header, value in zip(reserve_headers, reserves):
            row[header] = round(value, 2) if not math.isnan(value) else float("nan")

        for header, value in zip(count_product_headers, count_products):
            row[header] = round(value, 2) if not math.isnan(value) else float("nan")

        rows.append(row)

    return rows, columns


def build_empty_week_discount_row(basket: str, columns: list[str]) -> dict:
    """Placeholder Week Discount row for a basket with no imported data."""
    row = {col: float("nan") for col in columns}
    row["Basket"] = str(basket)
    return row


def _is_unset_export_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def normalize_week_discount_export_rows(
    rows: list[dict],
    columns: list[str],
    *,
    fill_baskets: set[str] | None = None,
) -> list[dict]:
    """
    Fill unset New Discount / New Prom with 0 for CSV export.

    When *fill_baskets* is provided, only those basket ids are filled; others
  (e.g. no-stock placeholders) keep empty values. When omitted, all rows are filled.
    """
    export_defaults = {
        NEW_DISCOUNT_COLUMN: 0.0,
        NEW_PROM_COLUMN: 0.0,
    }
    normalized: list[dict] = []
    for row in rows:
        copy = dict(row)
        basket = str(copy.get("Basket", ""))
        if fill_baskets is not None and basket not in fill_baskets:
            normalized.append(copy)
            continue
        for col, default in export_defaults.items():
            if col not in columns:
                continue
            if _is_unset_export_value(copy.get(col)):
                copy[col] = default
        normalized.append(copy)
    return normalized


def expand_week_discount_export_rows(
    rows: list[dict],
    columns: list[str],
    full_baskets: list[str],
) -> list[dict]:
    """
    Ensure export includes every basket from the canonical full list.

    Baskets already present in *rows* keep their values; missing baskets get
    empty (NaN) rows. Result is sorted by basket id.
    """
    if not full_baskets:
        return list(rows)

    by_basket: dict[str, dict] = {
        str(row.get("Basket", "")): dict(row)
        for row in rows
        if str(row.get("Basket", ""))
    }
    for basket in full_baskets:
        key = str(basket)
        if key not in by_basket:
            by_basket[key] = build_empty_week_discount_row(key, columns)

    return [by_basket[key] for key in sorted(by_basket.keys(), key=lambda b: (len(b), b))]


def _safe_delta(new_value: float, current_value: float) -> float:
    """Delta from current to new; missing New or current values are treated as 0."""
    new_num = 0.0 if math.isnan(new_value) else new_value
    baseline = 0.0 if math.isnan(current_value) else current_value
    return new_num - baseline


def enrich_week_discount_delta_columns(
    rows: list[dict],
    filter_map: dict[str, str],
) -> list[dict]:
    """Compute dDiscount and dProm from New vs current-week level columns."""
    discount_current_col = filter_map.get("discount_current", "")
    prom_current_col = filter_map.get("prom_current", "")
    enriched: list[dict] = []
    for row in rows:
        copy = dict(row)
        new_discount = copy.get(NEW_DISCOUNT_COLUMN, float("nan"))
        new_prom = copy.get(NEW_PROM_COLUMN, float("nan"))
        discount_current = (
            copy.get(discount_current_col, float("nan")) if discount_current_col else float("nan")
        )
        prom_current = (
            copy.get(prom_current_col, float("nan")) if prom_current_col else float("nan")
        )
        d_disc = _safe_delta(
            float(new_discount) if new_discount is not None else float("nan"),
            float(discount_current) if discount_current is not None else float("nan"),
        )
        d_prom = _safe_delta(
            float(new_prom) if new_prom is not None else float("nan"),
            float(prom_current) if prom_current is not None else float("nan"),
        )
        copy[D_DISCOUNT_COLUMN] = round(d_disc, 4) if not math.isnan(d_disc) else float("nan")
        copy[D_PROM_COLUMN] = round(d_prom, 4) if not math.isnan(d_prom) else float("nan")
        enriched.append(copy)
    return enriched


def week_discount_group_column_at_offset(
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


def _weighted_discount_prom_block(
    rows: list[dict],
    discount_col: str,
    prom_col: str,
    stock_weight_col: str,
    count_product_weight_col: str,
) -> dict[str, float | int]:
    weighted_discount_num = 0.0
    weighted_prom_num = 0.0
    stock_weight_den = 0.0
    count_product_weight_den = 0.0
    prom_positive_count = 0

    for row in rows:
        discount_val = row.get(discount_col) if discount_col else None
        prom_val = row.get(prom_col) if prom_col else None

        stock = row.get(stock_weight_col) if stock_weight_col else float("nan")
        if (
            stock_weight_col
            and stock is not None
            and not (isinstance(stock, float) and math.isnan(stock))
            and float(stock) > 0
        ):
            weight = float(stock)
            stock_weight_den += weight
            if discount_val is not None and not (
                isinstance(discount_val, float) and math.isnan(discount_val)
            ):
                weighted_discount_num += float(discount_val) * weight

        count_product = (
            row.get(count_product_weight_col)
            if count_product_weight_col
            else float("nan")
        )
        if (
            count_product_weight_col
            and count_product is not None
            and not (isinstance(count_product, float) and math.isnan(count_product))
            and float(count_product) > 0
        ):
            cp_weight = float(count_product)
            count_product_weight_den += cp_weight
            if prom_val is not None and not (
                isinstance(prom_val, float) and math.isnan(prom_val)
            ):
                weighted_prom_num += float(prom_val) * cp_weight
                if float(prom_val) > 0:
                    prom_positive_count += 1

    return {
        "W_Discount": (
            weighted_discount_num / stock_weight_den
            if stock_weight_den > 0
            else float("nan")
        ),
        "W_Prom": (
            weighted_prom_num / count_product_weight_den
            if count_product_weight_den > 0
            else float("nan")
        ),
        "count_Prom": prom_positive_count,
    }


def compute_week_discount_weighted_comparison(
    rows: list[dict],
    column_meta: dict[str, dict[str, object]],
    filter_map: dict[str, str],
) -> dict[str, dict[str, float | int]]:
    """W.S. Discount (stock-weighted) and W.C. Prom (count-product-weighted)."""
    stock_col = filter_map.get("stock_current", "")
    count_product_col = filter_map.get("count_product_current", "")
    return {
        "current_minus_1w": _weighted_discount_prom_block(
            rows,
            week_discount_group_column_at_offset(column_meta, "discount", -1),
            week_discount_group_column_at_offset(column_meta, "prom", -1),
            stock_col,
            count_product_col,
        ),
        "current": _weighted_discount_prom_block(
            rows,
            filter_map.get("discount_current", ""),
            filter_map.get("prom_current", ""),
            stock_col,
            count_product_col,
        ),
        "new": _weighted_discount_prom_block(
            rows,
            NEW_DISCOUNT_COLUMN,
            NEW_PROM_COLUMN,
            stock_col,
            count_product_col,
        ),
    }


def compute_week_discount_summary(
    rows: list[dict],
    filter_map: dict[str, str],
) -> dict[str, float | int]:
    """Aggregate min/max dDiscount and dProm for filtered Week Discount rows."""
    d_discount_vals: list[float] = []
    d_prom_vals: list[float] = []

    for row in rows:
        d_disc = row.get(D_DISCOUNT_COLUMN)
        d_prom = row.get(D_PROM_COLUMN)

        if d_disc is not None and not (isinstance(d_disc, float) and math.isnan(d_disc)):
            d_discount_vals.append(float(d_disc))
        if d_prom is not None and not (isinstance(d_prom, float) and math.isnan(d_prom)):
            d_prom_vals.append(float(d_prom))

    return {
        "max_dDiscount": max(d_discount_vals) if d_discount_vals else float("nan"),
        "min_dDiscount": min(d_discount_vals) if d_discount_vals else float("nan"),
        "max_dProm": max(d_prom_vals) if d_prom_vals else float("nan"),
        "min_dProm": min(d_prom_vals) if d_prom_vals else float("nan"),
    }
