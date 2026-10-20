"""
Week Discount and discount-history exports rebuilt from session state.

No widgets: used by the Week Discount export row, Project → Save and Release,
so all of them produce the same bytes. Rows of a category are rebuilt from its
saved analysis, generated values, manual overrides and column toggles; the
on-screen table Filters of non-current categories are not applied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd
import streamlit as st

from configs.settings import FULL_BASKET_LIST_PATH
from core.analytics.discount_strategy import build_working_week_discount_rows
from core.analytics.planner import annotate_week_discount_rows, assignment_lookup
from core.analytics.week_basket_tables import (
    WeekDiscountViewSettings,
    build_week_discount_column_meta,
    compute_basket_week_discount_rows,
    expand_week_discount_export_rows,
    normalize_week_discount_export_rows,
    select_visible_week_discount_columns,
    week_discount_filter_columns,
)
from core.transforms.data_prep import (
    DISCOUNT_HIST_EXPORT_COLUMNS,
    advance_discount_hist_week_metadata,
    build_discount_hist_export_rows,
    combine_discount_hist_export_by_category,
    merge_discount_hist_dataframes,
    merge_discount_hist_export,
    parse_full_basket_list,
)
from ui.product_bs_scope import (
    AGGREGATED_DISCOUNT_HIST_CATEGORY,
    PRODUCT_BS_CATEGORY_OPTIONS,
    PRODUCT_BS_INPUT_MODES,
    product_bs_scope_key,
    scoped_widget_key,
)

WEEK_DISCOUNT_MARGIN_ORIGINAL = "Margin"
WEEK_DISCOUNT_MARGIN_CORRECTED = "Margin Corrected"
WEEK_DISCOUNT_MARGIN_SOURCES = (
    WEEK_DISCOUNT_MARGIN_ORIGINAL,
    WEEK_DISCOUNT_MARGIN_CORRECTED,
)

# (settings field, toggle label, widget key prefix, default) — one entry per column toggle.
WEEK_DISCOUNT_VIEW_TOGGLES: tuple[tuple[str, str, str, bool], ...] = (
    ("show_discount", "Discount", "wd_col_discount", True),
    ("show_prom", "Prom", "wd_col_prom", True),
    ("show_stock", "Stock", "wd_col_stock", True),
    ("show_margin", "Margin", "wd_col_margin", True),
    ("show_mtost", "MtoSt", "wd_col_mtost", True),
    ("show_sold", "Sold", "wd_col_sold", True),
    ("show_price", "Price", "wd_col_price", True),
    ("show_reserve", "Monthly Reserve", "wd_col_reserve", False),
    ("show_count_product", "Count Product", "wd_col_count_product", False),
    ("show_w1", "1 W", "wd_col_w1", True),
    ("show_w4", "4 W", "wd_col_w4", True),
    ("show_w5", "5 W", "wd_col_w5", True),
)


@st.cache_data(show_spinner=False)
def _cached_full_basket_list(path: str, mtime_ns: int) -> list[str]:
    del mtime_ns
    df = pd.read_csv(path)
    return parse_full_basket_list(df)


def load_full_basket_list() -> list[str]:
    path = FULL_BASKET_LIST_PATH
    if not path.is_file():
        return []
    return _cached_full_basket_list(str(path), path.stat().st_mtime_ns)


def include_no_stock_key(selected_week: str) -> str:
    return f"wd_export_include_no_stock_{selected_week}"


def export_all_history_key(selected_week: str) -> str:
    return f"wd_export_all_history_{selected_week}"


def view_settings_from_state(ss: Any, scope_key: str, selected_week: str) -> WeekDiscountViewSettings:
    values = {
        field_name: bool(ss.get(scoped_widget_key(scope_key, f"{prefix}_{selected_week}"), default))
        for field_name, _label, prefix, default in WEEK_DISCOUNT_VIEW_TOGGLES
    }
    return WeekDiscountViewSettings(**values)


@dataclass
class _CategoryRows:
    scope_key: str
    scope: dict
    analysis: Any
    working_rows: list[dict]
    columns: list[str]
    meta: dict


def _category_rows(ss: Any, input_mode: str, category: str, selected_week: str) -> Optional[_CategoryRows]:
    scope_key = product_bs_scope_key(input_mode, category)
    scopes = ss.get("_pbs_scopes") or {}
    scope = scopes.get(scope_key) if isinstance(scopes, dict) else None
    analysis = scope.get("analysis") if isinstance(scope, dict) else None
    if analysis is None or selected_week not in (analysis.weekly_totals or {}):
        return None
    margin_source = ss.get(
        scoped_widget_key(scope_key, "wd_margin_source"),
        WEEK_DISCOUNT_MARGIN_CORRECTED,
    )
    margin_by_basket = (
        scope.get("basket_margin_hybrid")
        if margin_source == WEEK_DISCOUNT_MARGIN_CORRECTED
        else None
    )
    base_rows, columns = compute_basket_week_discount_rows(
        analysis.basket_data,
        analysis.weekly_totals,
        analysis.all_weeks,
        selected_week,
        margin_by_basket=margin_by_basket,
    )
    if not base_rows:
        return None
    meta = build_week_discount_column_meta(analysis.weekly_totals, analysis.all_weeks, selected_week)
    filter_map = week_discount_filter_columns(meta)
    gen_discount = ss.get(scoped_widget_key(scope_key, f"wd_generated_discount_{selected_week}"))
    gen_prom = ss.get(scoped_widget_key(scope_key, f"wd_generated_prom_{selected_week}"))
    manual = ss.get(scoped_widget_key(scope_key, f"wd_manual_overrides_{selected_week}"))
    working_rows = build_working_week_discount_rows(
        base_rows,
        filter_map,
        generated_discount=gen_discount if isinstance(gen_discount, dict) and gen_discount else None,
        generated_prom=gen_prom if isinstance(gen_prom, dict) and gen_prom else None,
        manual_overrides=manual if isinstance(manual, dict) and manual else None,
    )
    return _CategoryRows(scope_key, scope, analysis, working_rows, columns, meta)


def _export_rows(
    working_rows: list[dict],
    columns: list[str],
    *,
    include_no_stock: bool,
    full_basket_list: list[str],
) -> list[dict]:
    in_stock = {str(row.get("Basket", "")) for row in working_rows if str(row.get("Basket", ""))}
    rows = working_rows
    expand = bool(include_no_stock and full_basket_list)
    if expand:
        rows = expand_week_discount_export_rows(working_rows, columns, full_basket_list)
    return normalize_week_discount_export_rows(
        rows,
        columns,
        fill_baskets=in_stock if expand else None,
    )


def category_hist_export_rows(
    ss: Any,
    input_mode: str,
    category: str,
    selected_week: str,
    week_meta: dict[str, object],
    *,
    include_no_stock: bool,
    full_basket_list: list[str],
) -> list[dict]:
    """Discount-history rows of the new week for one built category."""
    rows = _category_rows(ss, input_mode, category, selected_week)
    if rows is None:
        return []
    export_rows = _export_rows(
        rows.working_rows,
        rows.columns,
        include_no_stock=include_no_stock,
        full_basket_list=full_basket_list,
    )
    planner = rows.scope.get("planner")
    return build_discount_hist_export_rows(
        export_rows,
        week_meta,
        category,
        assignments=assignment_lookup(planner) if planner else None,
    )


def category_week_discount_csv(
    ss: Any,
    input_mode: str,
    category: str,
    selected_week: str,
    include_no_stock: Optional[bool] = None,
) -> Optional[bytes]:
    """Week Discount CSV of one built category, with that category's visible columns.

    ``include_no_stock`` defaults to that category's own "Include 'no stock'" option.
    """
    rows = _category_rows(ss, input_mode, category, selected_week)
    if rows is None:
        return None
    if include_no_stock is None:
        include_no_stock, _ = _hist_options(ss, rows.scope_key, selected_week)
    annotated = annotate_week_discount_rows(rows.working_rows, rows.scope.get("planner") or {})
    export_rows = _export_rows(
        annotated,
        rows.columns,
        include_no_stock=include_no_stock,
        full_basket_list=load_full_basket_list(),
    )
    visible = select_visible_week_discount_columns(
        rows.columns,
        rows.meta,
        view_settings_from_state(ss, rows.scope_key, selected_week),
    )
    frame = pd.DataFrame(export_rows, columns=rows.columns)
    frame = frame.loc[:, [col for col in visible if col in frame.columns]]
    if frame.empty:
        return None
    return frame.to_csv(index=False).encode()


def _scope(ss: Any, input_mode: str, category: str) -> Optional[dict]:
    scopes = ss.get("_pbs_scopes") or {}
    scope = scopes.get(product_bs_scope_key(input_mode, category)) if isinstance(scopes, dict) else None
    return scope if isinstance(scope, dict) else None


def _built_scopes(ss: Any, input_mode: str) -> list[tuple[str, dict]]:
    if input_mode not in PRODUCT_BS_INPUT_MODES:
        scope = _scope(ss, input_mode, AGGREGATED_DISCOUNT_HIST_CATEGORY)
        if scope is None or scope.get("analysis") is None:
            return []
        return [(AGGREGATED_DISCOUNT_HIST_CATEGORY, scope)]
    built: list[tuple[str, dict]] = []
    for category in PRODUCT_BS_CATEGORY_OPTIONS:
        scope = _scope(ss, input_mode, category)
        if scope is not None and scope.get("analysis") is not None:
            built.append((category, scope))
    return built


def built_categories(ss: Any, input_mode: str, selected_week: str) -> list[str]:
    """Categories whose analysis contains ``selected_week``, in app order.

    The plain TrackingBaskets report mode has one scope, reported as Aggregated.
    """
    return [
        category
        for category, scope in _built_scopes(ss, input_mode)
        if selected_week in (scope["analysis"].weekly_totals or {})
    ]


@dataclass
class HistExport:
    next_week: str
    data: bytes
    categories: list[str] = field(default_factory=list)


def _week_meta(analysis: Any, selected_week: str) -> Optional[dict]:
    try:
        return advance_discount_hist_week_metadata(analysis.weekly_totals, selected_week)
    except ValueError:
        return None


def _hist_options(ss: Any, scope_key: str, selected_week: str) -> tuple[bool, bool]:
    include_no_stock = bool(ss.get(scoped_widget_key(scope_key, include_no_stock_key(selected_week)), True))
    include_all_history = bool(ss.get(scoped_widget_key(scope_key, export_all_history_key(selected_week)), True))
    return include_no_stock, include_all_history


def _hist_frame_export(rows: list[dict], week_meta: dict, categories: list[str]) -> Optional[HistExport]:
    frame = pd.DataFrame(rows, columns=DISCOUNT_HIST_EXPORT_COLUMNS)
    if frame.empty:
        return None
    return HistExport(
        next_week=str(week_meta["year_week"]),
        data=frame.to_csv(index=False).encode(),
        categories=categories,
    )


def discount_hist_category_csv(
    ss: Any,
    input_mode: str,
    category: str,
    selected_week: str,
) -> Optional[HistExport]:
    """"Discount history. Current" of one category: its new week merged with its history."""
    scope = _scope(ss, input_mode, category)
    analysis = scope.get("analysis") if scope else None
    if analysis is None:
        return None
    week_meta = _week_meta(analysis, selected_week)
    if week_meta is None:
        return None
    include_no_stock, include_all_history = _hist_options(
        ss, product_bs_scope_key(input_mode, category), selected_week,
    )
    rows = category_hist_export_rows(
        ss,
        input_mode,
        category,
        selected_week,
        week_meta,
        include_no_stock=include_no_stock,
        full_basket_list=load_full_basket_list(),
    )
    if not rows:
        return None
    source = scope.get("discount_hist_df")
    merged = merge_discount_hist_export(
        source if isinstance(source, pd.DataFrame) and not source.empty else None,
        rows,
        include_all_history=include_all_history,
    )
    return _hist_frame_export(merged, week_meta, [category])


def discount_hist_all_csv(
    ss: Any,
    input_mode: str,
    current_category: str,
    selected_week: str,
) -> Optional[HistExport]:
    """"Discount history. All": new week of every built category merged with their history.

    The plain TrackingBaskets report mode has one scope, so ALL is that scope's history.
    Uses the current scope's "Include no stock" and "all history" options.
    """
    current_scope = _scope(ss, input_mode, current_category)
    analysis = current_scope.get("analysis") if current_scope else None
    if analysis is None:
        return None
    week_meta = _week_meta(analysis, selected_week)
    if week_meta is None:
        return None
    full_basket_list = load_full_basket_list()
    include_no_stock, include_all_history = _hist_options(
        ss, product_bs_scope_key(input_mode, current_category), selected_week,
    )

    category_rows: dict[str, list[dict]] = {}
    sources: list[pd.DataFrame] = []
    for category, scope in _built_scopes(ss, input_mode):
        rows = category_hist_export_rows(
            ss,
            input_mode,
            category,
            selected_week,
            week_meta,
            include_no_stock=include_no_stock,
            full_basket_list=full_basket_list,
        )
        if rows:
            category_rows[category] = rows
        source = scope.get("discount_hist_df")
        if isinstance(source, pd.DataFrame) and not source.empty:
            sources.append(source)
    if not category_rows:
        return None
    combined_source = merge_discount_hist_dataframes(sources) if sources else None
    merged = merge_discount_hist_export(
        combined_source if combined_source is not None and not combined_source.empty else None,
        combine_discount_hist_export_by_category(category_rows),
        include_all_history=include_all_history,
    )
    return _hist_frame_export(merged, week_meta, list(category_rows))
