"""
Week Discount section — Streamlit UI helpers.

Renders column toggles, filters, discount strategy, table, and sum-up metrics.
Analytics live in core/analytics/.
"""

from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from core.analytics.discount_strategy import (
    GENERATION_MODES,
    MARGIN_MODES,
    STRATEGY_NAMES,
    DiscountStrategySettings,
    MarginCategory,
    apply_generated_discounts_to_rows,
    apply_manual_overrides_to_rows,
    build_working_week_discount_rows,
    default_discount_strategy_settings,
    display_rows_to_strategy_bins,
    display_rows_to_mtost_bins,
    generate_week_discount_values,
    load_discount_strategy_settings,
    mtost_bins_to_display_rows,
    strategy_bins_to_display_rows,
)
from core.analytics.prom_strategy import (
    PROM_GENERATION_MODES,
    PromStrategySettings,
    generate_week_prom_values,
)
from core.analytics.week_basket_tables import (
    D_DISCOUNT_COLUMN,
    D_PROM_COLUMN,
    NEW_DISCOUNT_COLUMN,
    NEW_PROM_COLUMN,
    WeekDiscountViewSettings,
    apply_week_discount_filters,
    build_week_discount_column_meta,
    compute_basket_week_discount_rows,
    compute_week_discount_summary,
    expand_week_discount_export_rows,
    normalize_week_discount_export_rows,
    format_week_discount_value,
    parse_week_discount_filter_value,
    select_visible_week_discount_columns,
    week_discount_column_background,
    week_discount_filter_columns,
    week_discount_filter_label_kind,
    week_discount_value_kind,
)
from core.analytics.weighted_discount import (
    DISCOUNT_PROM_WEIGHT_CHOICES,
    compute_week_discount_weighted_comparisons,
    discount_prom_weight_column_labels,
    discount_prom_weight_key,
)
from configs.settings import FULL_BASKET_LIST_PATH, STRATEGIES_V1_PATH
from ui.product_bs_scope import (
    PRODUCT_BS_INPUT_MODES,
    iter_built_product_bs_scopes,
    product_bs_scope_key,
    scoped_widget_key,
)
from core.models import BasketTimeSeries, WeeklyTotal
from core.transforms.data_prep import (
    DISCOUNT_HIST_DISCOUNT_COLUMNS,
    DISCOUNT_HIST_EXPORT_COLUMNS,
    DISCOUNT_HIST_PROM_COLUMNS,
    advance_discount_hist_week_metadata,
    build_discount_hist_export_rows,
    combine_discount_hist_export_by_category,
    merge_discount_hist_dataframes,
    merge_discount_hist_export,
    parse_full_basket_list,
)

DISCOUNT_SETTINGS_CSV = STRATEGIES_V1_PATH
# Bump when strategies file parsing or default layout changes (invalidates Streamlit caches).
DISCOUNT_SETTINGS_UI_VERSION = 5
WEEK_DISCOUNT_MARGIN_ORIGINAL = "Margin"
WEEK_DISCOUNT_MARGIN_CORRECTED = "Margin Corrected"
WEEK_DISCOUNT_MARGIN_SOURCES = (
    WEEK_DISCOUNT_MARGIN_ORIGINAL,
    WEEK_DISCOUNT_MARGIN_CORRECTED,
)


@st.cache_data(show_spinner=False)
def _cached_full_basket_list(path: str, mtime_ns: int) -> list[str]:
    del mtime_ns
    df = pd.read_csv(path)
    return parse_full_basket_list(df)


def _load_full_basket_list() -> list[str]:
    path = FULL_BASKET_LIST_PATH
    if not path.is_file():
        return []
    return _cached_full_basket_list(str(path), path.stat().st_mtime_ns)


def _week_discount_column_style(col: pd.Series) -> list[str]:
    bg = week_discount_column_background(str(col.name))
    if not bg:
        return [""] * len(col)
    return [f"background-color: {bg}; color: #111827;" for _ in col]


def _week_discount_styler(df: pd.DataFrame):
    formatters = {
        col: (lambda column: lambda value: format_week_discount_value(column, value))(col)
        for col in df.columns
        if week_discount_value_kind(col) != "text"
    }
    return df.style.apply(_week_discount_column_style, axis=0).format(
        formatters,
        na_rep="",
    )


def _week_discount_filter_specs() -> list[tuple[str, str]]:
    return [
        ("New Discount", "new_discount"),
        ("Discount", "discount_current"),
        ("New Prom", "new_prom"),
        ("Prom", "prom_current"),
        ("dSt_QW", "dSt_QW"),
        ("Stock", "stock_current"),
        ("dM_QW", "dM_QW"),
        ("Margin", "margin_current"),
        ("dMtoSt", "dMtoSt_QW"),
        ("MtoSt", "mtost_current"),
        ("dSold", "dSold_QW"),
        ("Sold", "sold_current"),
        ("dPrice", "dPrice_QW"),
        ("Price", "price_current"),
        ("dRes", "dRes_QW"),
        ("Monthly Reserve", "reserve_current"),
    ]


def _week_discount_filter_labels() -> list[str]:
    return [label for label, _ in _week_discount_filter_specs()]


def _default_week_discount_filter_df() -> pd.DataFrame:
    empty = {label: None for label in _week_discount_filter_labels()}
    return pd.DataFrame([
        {"Bound": "min", **empty},
        {"Bound": "max", **empty},
    ])


def _week_discount_filter_number_column(label: str, enabled: bool) -> st.column_config.NumberColumn:
    kind = week_discount_filter_label_kind(label)
    if kind == "delta_pct":
        return st.column_config.NumberColumn(
            label,
            format="%.2f",
            disabled=not enabled,
            width="small",
            help="Percent change (e.g. -10.50 for -10.50%).",
        )
    if kind == "integer":
        return st.column_config.NumberColumn(
            label,
            format="%.0f",
            disabled=not enabled,
            width="small",
            step=1,
        )
    if kind == "currency":
        return st.column_config.NumberColumn(
            label,
            format="$%.2f",
            disabled=not enabled,
            width="small",
        )
    if kind == "mtost":
        return st.column_config.NumberColumn(
            label,
            format="%.3f",
            disabled=not enabled,
            width="small",
        )
    if kind == "reserve":
        return st.column_config.NumberColumn(
            label,
            format="%.2f",
            disabled=not enabled,
            width="small",
            help="Months to sell out at weekly sold rate.",
        )
    return st.column_config.NumberColumn(
        label,
        disabled=not enabled,
        width="small",
    )


def _week_discount_filter_column_config(
    filter_key_to_column: dict[str, str],
) -> dict[str, st.column_config.Column]:
    config: dict[str, st.column_config.Column] = {
        "Bound": st.column_config.TextColumn("Bound", disabled=True, width="small"),
    }
    for label, filter_key in _week_discount_filter_specs():
        enabled = bool(filter_key_to_column.get(filter_key, ""))
        config[label] = _week_discount_filter_number_column(label, enabled)
    return config


def _filter_bounds_from_week_discount_df(
    filter_df: pd.DataFrame,
    filter_key_to_column: dict[str, str],
) -> dict[str, tuple[float | None, float | None]]:
    if filter_df.empty or "Bound" not in filter_df.columns:
        return {}

    min_rows = filter_df.loc[filter_df["Bound"].astype(str).str.lower() == "min"]
    max_rows = filter_df.loc[filter_df["Bound"].astype(str).str.lower() == "max"]
    if min_rows.empty or max_rows.empty:
        return {}

    min_row = min_rows.iloc[0]
    max_row = max_rows.iloc[0]
    bounds: dict[str, tuple[float | None, float | None]] = {}

    for label, filter_key in _week_discount_filter_specs():
        col = filter_key_to_column.get(filter_key, "")
        if not col or label not in filter_df.columns:
            continue
        lo = parse_week_discount_filter_value(label, min_row.get(label))
        hi = parse_week_discount_filter_value(label, max_row.get(label))
        if lo is not None or hi is not None:
            bounds[col] = (lo, hi)

    return bounds


@st.cache_data
def _load_discount_strategy_defaults(
    settings_version: int,
    csv_mtime: float,
) -> DiscountStrategySettings:
    if DISCOUNT_SETTINGS_CSV.exists():
        return load_discount_strategy_settings(DISCOUNT_SETTINGS_CSV)
    return default_discount_strategy_settings()


def _cached_discount_strategy_defaults() -> DiscountStrategySettings:
    csv_mtime = (
        DISCOUNT_SETTINGS_CSV.stat().st_mtime
        if DISCOUNT_SETTINGS_CSV.exists()
        else 0.0
    )
    return _load_discount_strategy_defaults(
        DISCOUNT_SETTINGS_UI_VERSION,
        csv_mtime,
    )


def _parse_missing_discount_default(raw: str) -> float:
    text = str(raw).strip()
    if not text or text.lower() in {"n/a", "na", "nan"}:
        return 0.0
    cleaned = text.replace("%", "").replace(",", "")
    try:
        value = float(cleaned)
    except ValueError:
        return 0.0
    if "%" in text or abs(value) > 1.0:
        return value / 100.0
    return value


def _margin_categories_display_df(settings: DiscountStrategySettings) -> pd.DataFrame:
    rows: list[dict] = []
    for category in settings.margin_categories:
        rows.append({
            "lower Margin": (
                "min" if category.lower == float("-inf") else category.lower
            ),
            "Strategy": category.strategy,
            "upper Margin": (
                "max" if category.upper == float("inf") else category.upper
            ),
        })
    return pd.DataFrame(rows)


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return not str(value).strip()


def _margin_categories_from_df(df: pd.DataFrame) -> list[MarginCategory]:
    categories: list[MarginCategory] = []
    for _, row in df.iterrows():
        lower_raw = row.get("lower Margin")
        upper_raw = row.get("upper Margin")
        strategy = row.get("Strategy")
        if lower_raw is None or upper_raw is None or _is_blank(strategy):
            continue
        lower = (
            float("-inf")
            if str(lower_raw).strip().lower() == "min"
            else float(lower_raw)
        )
        upper = (
            float("inf")
            if str(upper_raw).strip().lower() == "max"
            else float(upper_raw)
        )
        categories.append(MarginCategory(lower, upper, str(strategy).strip()))
    return categories


def _render_discount_strategy_settings(selected_week: str, scope_key: str) -> DiscountStrategySettings:
    def wk(widget_key: str) -> str:
        return scoped_widget_key(scope_key, widget_key)

    defaults = _cached_discount_strategy_defaults()
    settings = DiscountStrategySettings(
        conservative=defaults.conservative,
        moderate=defaults.moderate,
        strong=defaults.strong,
        mtost=defaults.mtost,
        margin_categories=list(defaults.margin_categories),
        sold_zero_strategy=defaults.sold_zero_strategy,
        sold_zero_balance=defaults.sold_zero_balance,
        mtost_strategy_enabled=defaults.mtost_strategy_enabled,
        mtost_balance=defaults.mtost_balance,
    )

    with st.expander("Discount strategy", expanded=False):
        settings.mode = st.selectbox(
            "Discount generation mode",
            GENERATION_MODES,
            index=GENERATION_MODES.index("Based on Strategies"),
            key=wk(f"wd_strat_mode_{selected_week}"),
        )

        st.markdown("**Strategies**")
        st.caption(
            "Discount[new] = Discount[current] + (dDiscount(strategy) + Balance) × Multiplicator"
        )

        strat_col1, strat_col2 = st.columns(2)
        settings.balance = strat_col1.number_input(
            "Balance (%)",
            value=0.0,
            step=1.0,
            format="%.2f",
            key=wk(f"wd_strat_balance_{selected_week}"),
            help="Shifts strategy dDiscount before applying the multiplicator.",
        ) / 100.0
        settings.multiplicator = strat_col2.number_input(
            "Multiplicator",
            value=1.0,
            step=0.1,
            format="%.2f",
            key=wk(f"wd_strat_mult_{selected_week}"),
        )

        zero_col1, zero_col2 = st.columns(2)
        settings.zero_d_st_negative = zero_col1.checkbox(
            "dDiscount=0 when dSt_QW < 0",
            value=False,
            key=wk(f"wd_strat_zero_neg_{selected_week}"),
        )
        settings.zero_d_st_positive = zero_col2.checkbox(
            "dDiscount=0 when dSt_QW > 0",
            value=False,
            key=wk(f"wd_strat_zero_pos_{selected_week}"),
        )

        for strategy_name, attr in (
            ("Conservative", "conservative"),
            ("Moderate", "moderate"),
            ("Strong", "strong"),
        ):
            table = getattr(defaults, attr)
            with st.expander(strategy_name, expanded=strategy_name == "Moderate"):
                display_df = pd.DataFrame(strategy_bins_to_display_rows(table))
                edited_df = st.data_editor(
                    display_df,
                    hide_index=True,
                    use_container_width=True,
                    num_rows="dynamic",
                    key=wk(f"wd_strat_table_{strategy_name}_{selected_week}"),
                    column_config={
                        "lower dSt_QW %": st.column_config.TextColumn("lower dSt_QW %"),
                        "dDiscount %": st.column_config.NumberColumn(
                            "dDiscount %",
                            format="%.2f",
                        ),
                        "upper dSt_QW %": st.column_config.TextColumn("upper dSt_QW %"),
                    },
                )
                setattr(
                    settings,
                    attr,
                    display_rows_to_strategy_bins(strategy_name, edited_df.to_dict("records")),
                )

        st.markdown("**Priority 1 — Default when Discount is missing**")
        missing_discount_raw = st.text_input(
            "Default for missing Discount[current] (n/a = 0)",
            value="n/a",
            key=wk(f"wd_strat_missing_discount_{selected_week}"),
            help="Used as Discount[current] when that value is missing (blank/NaN) before applying the strategy.",
        )
        settings.missing_discount_default = _parse_missing_discount_default(missing_discount_raw)

        st.markdown("**Priority 2 — Sold = 0 strategy**")
        sold_col1, sold_col2 = st.columns(2)
        settings.sold_zero_strategy = sold_col1.selectbox(
            "Strategy",
            STRATEGY_NAMES,
            index=STRATEGY_NAMES.index(defaults.sold_zero_strategy),
            key=wk(f"wd_strat_sold_zero_strat_{selected_week}"),
        )
        settings.sold_zero_balance = sold_col2.number_input(
            "Balance (%)",
            value=defaults.sold_zero_balance * 100.0,
            step=0.1,
            format="%.2f",
            key=wk(f"wd_strat_sold_zero_balance_{selected_week}"),
        ) / 100.0

        st.markdown("**Priority 3 — Margin to Stock (MtoSt)**")
        st.caption(
            "Discount[new] = Discount[current] + (dDiscount(dMtoSt_QW) + Balance). "
            "Applies when dSt_QW > 0 and Margin[current] and Margin[W−1] ≥ 0. "
            "Priority above default margin strategy; below Priority 1 and 2."
        )
        settings.mtost_strategy_enabled = st.toggle(
            "MtoSt strategy",
            value=defaults.mtost_strategy_enabled,
            key=wk(f"wd_strat_mtost_enabled_{selected_week}"),
        )
        settings.mtost_balance = st.number_input(
            "Balance (%)",
            value=defaults.mtost_balance * 100.0,
            step=1.0,
            format="%.2f",
            key=wk(f"wd_strat_mtost_balance_{selected_week}"),
            help="Added to MtoSt dDiscount before applying (no multiplicator).",
        ) / 100.0
        mtost_display_df = pd.DataFrame(mtost_bins_to_display_rows(defaults.mtost))
        mtost_edited_df = st.data_editor(
            mtost_display_df,
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key=wk(f"wd_strat_mtost_bins_v{DISCOUNT_SETTINGS_UI_VERSION}_{selected_week}"),
            column_config={
                "lower dMtoSt_QW %": st.column_config.TextColumn("lower dMtoSt_QW %"),
                "dDiscount %": st.column_config.NumberColumn("dDiscount %", format="%.2f"),
                "upper dMtoSt_QW %": st.column_config.TextColumn("upper dMtoSt_QW %"),
            },
            disabled=not settings.mtost_strategy_enabled,
        )
        if settings.mtost_strategy_enabled:
            settings.mtost = display_rows_to_mtost_bins(
                mtost_edited_df.to_dict("records"),
            )

        st.markdown("**Margin break-down**")
        settings.margin_mode = st.radio(
            "Margin strategy mode",
            MARGIN_MODES,
            index=MARGIN_MODES.index(defaults.margin_mode),
            horizontal=True,
            key=wk(f"wd_strat_margin_mode_{selected_week}"),
        )
        settings.default_strategy = st.selectbox(
            "Default strategy",
            STRATEGY_NAMES,
            index=STRATEGY_NAMES.index(defaults.default_strategy),
            key=wk(f"wd_strat_default_strat_{selected_week}"),
        )
        if settings.margin_mode == "Margin categories":
            margin_df = st.data_editor(
                _margin_categories_display_df(defaults),
                hide_index=True,
                use_container_width=True,
                num_rows="dynamic",
                key=(
                    f"wd_strat_margin_cats_v{DISCOUNT_SETTINGS_UI_VERSION}_{selected_week}"
                ),
                column_config={
                    "lower Margin": st.column_config.TextColumn("lower Margin"),
                    "Strategy": st.column_config.SelectboxColumn(
                        "Strategy",
                        options=list(STRATEGY_NAMES),
                    ),
                    "upper Margin": st.column_config.TextColumn("upper Margin"),
                },
            )
            settings.margin_categories = _margin_categories_from_df(margin_df)

    return settings


def _render_prom_strategy_settings(selected_week: str, scope_key: str) -> PromStrategySettings:
    def wk(widget_key: str) -> str:
        return scoped_widget_key(scope_key, widget_key)

    with st.expander("Prom strategy", expanded=False):
        mode = st.selectbox(
            "Prom generation mode",
            PROM_GENERATION_MODES,
            index=0,
            key=wk(f"wd_prom_mode_{selected_week}"),
        )
    return PromStrategySettings(mode=mode)


def _fmt_pct(val: float) -> str:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "N/A"
    return f"{val * 100:.2f}%"


def _can_manual_edit_new_columns(visible_columns: list[str]) -> bool:
    return NEW_DISCOUNT_COLUMN in visible_columns or NEW_PROM_COLUMN in visible_columns


def _week_discount_rows_to_edit_df(
    rows: list[dict],
    all_columns: list[str],
    visible_columns: list[str],
) -> pd.DataFrame:
    """Build a data-editor dataframe; percent columns shown as percent."""
    df = pd.DataFrame(rows, columns=all_columns).loc[:, visible_columns].copy()
    percent_cols = (
        NEW_DISCOUNT_COLUMN,
        NEW_PROM_COLUMN,
        D_DISCOUNT_COLUMN,
        D_PROM_COLUMN,
    )
    for col in percent_cols:
        if col not in df.columns:
            continue
        df[col] = df[col].apply(
            lambda v: (
                None
                if v is None or (isinstance(v, float) and math.isnan(v))
                else round(float(v) * 100.0, 4)
            ),
        )
    return df


def _week_discount_edit_column_config(
    visible_columns: list[str],
) -> dict[str, st.column_config.Column]:
    config: dict[str, st.column_config.Column] = {}
    editable_new = {NEW_DISCOUNT_COLUMN, NEW_PROM_COLUMN}
    for col in visible_columns:
        if col == "Basket":
            config[col] = st.column_config.TextColumn(col, disabled=True)
        elif col in editable_new:
            config[col] = st.column_config.NumberColumn(
                col,
                format="%.2f",
                step=1.0,
                help="Percent (e.g. 5.00 for 5%).",
            )
        else:
            kind = week_discount_value_kind(col)
            if kind == "delta_pct":
                config[col] = st.column_config.NumberColumn(
                    col, format="%.2f", disabled=True,
                )
            elif kind == "integer":
                config[col] = st.column_config.NumberColumn(
                    col, format="%.0f", disabled=True,
                )
            elif kind == "currency":
                config[col] = st.column_config.NumberColumn(
                    col, format="$%.2f", disabled=True,
                )
            elif kind == "mtost":
                config[col] = st.column_config.NumberColumn(
                    col, format="%.3f", disabled=True,
                )
            elif kind == "reserve":
                config[col] = st.column_config.NumberColumn(
                    col, format="%.2f", disabled=True,
                )
            else:
                config[col] = st.column_config.Column(col, disabled=True)
    return config


def _manual_overrides_from_edit_df(
    edited: pd.DataFrame,
    visible_columns: list[str],
) -> dict[str, dict[str, float]]:
    """Parse edited table rows into ratio overrides for New Discount / New Prom."""
    overrides: dict[str, dict[str, float]] = {}
    editable = [
        col for col in (NEW_DISCOUNT_COLUMN, NEW_PROM_COLUMN) if col in visible_columns
    ]
    if not editable:
        return overrides

    for _, row in edited.iterrows():
        basket = str(row.get("Basket", "")).strip()
        if not basket:
            continue
        entry: dict[str, float] = {}
        for col in editable:
            raw = row.get(col)
            if raw is None or (isinstance(raw, float) and math.isnan(raw)):
                entry[col] = float("nan")
            else:
                entry[col] = round(float(raw) / 100.0, 6)
        overrides[basket] = entry
    return overrides


def _category_week_discount_hist_export_rows(
    analysis,
    selected_week: str,
    category: str,
    week_meta: dict[str, object],
    ss,
    scope_key: str,
    *,
    include_no_stock: bool,
    full_basket_list: list[str],
    margin_by_basket: dict[str, list[float]] | None = None,
) -> list[dict]:
    """Build discount-history export rows for one built Product BS category."""
    basket_data = analysis.basket_data
    weekly_totals = analysis.weekly_totals
    all_weeks = analysis.all_weeks
    margin_source = ss.get(
        scoped_widget_key(scope_key, "wd_margin_source"),
        WEEK_DISCOUNT_MARGIN_CORRECTED,
    )
    use_corrected = margin_source == WEEK_DISCOUNT_MARGIN_CORRECTED
    base_rows, week_discount_columns = compute_basket_week_discount_rows(
        basket_data,
        weekly_totals,
        all_weeks,
        selected_week,
        margin_by_basket=margin_by_basket if use_corrected else None,
    )
    if not base_rows:
        return []
    week_discount_meta = build_week_discount_column_meta(
        weekly_totals,
        all_weeks,
        selected_week,
    )
    filter_map = week_discount_filter_columns(week_discount_meta)
    gen_discount = ss.get(scoped_widget_key(scope_key, f"wd_generated_discount_{selected_week}"))
    gen_prom = ss.get(scoped_widget_key(scope_key, f"wd_generated_prom_{selected_week}"))
    manual = ss.get(scoped_widget_key(scope_key, f"wd_manual_overrides_{selected_week}"))
    working_rows = build_working_week_discount_rows(
        base_rows,
        filter_map,
        generated_discount=gen_discount if isinstance(gen_discount, dict) else None,
        generated_prom=gen_prom if isinstance(gen_prom, dict) else None,
        manual_overrides=manual if isinstance(manual, dict) else None,
    )
    export_rows = working_rows
    in_stock_baskets = {
        str(row.get("Basket", ""))
        for row in working_rows
        if str(row.get("Basket", ""))
    }
    if include_no_stock and full_basket_list:
        export_rows = expand_week_discount_export_rows(
            working_rows,
            week_discount_columns,
            full_basket_list,
        )
    export_rows = normalize_week_discount_export_rows(
        export_rows,
        week_discount_columns,
        fill_baskets=(
            in_stock_baskets
            if include_no_stock and full_basket_list
            else None
        ),
    )
    return build_discount_hist_export_rows(
        export_rows,
        week_meta,
        category,
    )


def render_week_discount_section(
    basket_data: dict[str, BasketTimeSeries],
    weekly_totals: dict[str, WeeklyTotal],
    all_weeks: list[str],
    selected_week: str,
    scope_key: str,
    discount_hist_category: str,
    discount_hist_df: pd.DataFrame | None = None,
    input_mode: str | None = None,
    margin_by_basket: dict[str, list[float]] | None = None,
) -> None:
    """Render Week Discount toggles, filters, strategy, table, and sum-up metrics."""
    def wk(widget_key: str) -> str:
        return scoped_widget_key(scope_key, widget_key)

    src_col, _ = st.columns([2, 10])
    margin_source = src_col.selectbox(
        "Margin columns",
        list(WEEK_DISCOUNT_MARGIN_SOURCES),
        index=WEEK_DISCOUNT_MARGIN_SOURCES.index(WEEK_DISCOUNT_MARGIN_CORRECTED),
        key=wk("wd_margin_source"),
        help=(
            "Margin uses original basket margin. Margin Corrected uses the hybrid "
            "series from Cost Correction for Margin[], dM_QW, MtoSt[], dMtoSt_QW, "
            "and discount generation."
        ),
    )
    use_corrected_margin = margin_source == WEEK_DISCOUNT_MARGIN_CORRECTED
    progress = st.progress(0, text="Preparing Week Discount…")
    try:
        progress.progress(20, text="Computing Week Discount rows…")
        week_discount_rows, week_discount_columns = compute_basket_week_discount_rows(
            basket_data,
            weekly_totals,
            all_weeks,
            selected_week,
            margin_by_basket=margin_by_basket if use_corrected_margin else None,
        )
        if not week_discount_rows:
            progress.empty()
            st.info("No basket rows for the selected week.")
            return

        progress.progress(40, text="Building column metadata…")
        week_discount_meta = build_week_discount_column_meta(
            weekly_totals,
            all_weeks,
            selected_week,
        )
        week_discount_filter_map = week_discount_filter_columns(week_discount_meta)
    except Exception:
        progress.empty()
        raise
    ss = st.session_state

    wd_col1, wd_col2, wd_col3, wd_col4, wd_col5, wd_col6, wd_col7, wd_col8, wd_col9, wd_col10, wd_col11, wd_col12 = st.columns(12)
    wd_settings = WeekDiscountViewSettings(
        show_discount=wd_col1.toggle(
            "Discount", True, key=wk(f"wd_col_discount_{selected_week}"),
        ),
        show_prom=wd_col2.toggle(
            "Prom", True, key=wk(f"wd_col_prom_{selected_week}"),
        ),
        show_stock=wd_col3.toggle("Stock", True, key=wk(f"wd_col_stock_{selected_week}")),
        show_margin=wd_col4.toggle("Margin", True, key=wk(f"wd_col_margin_{selected_week}")),
        show_mtost=wd_col5.toggle("MtoSt", True, key=wk(f"wd_col_mtost_{selected_week}")),
        show_sold=wd_col6.toggle("Sold", True, key=wk(f"wd_col_sold_{selected_week}")),
        show_price=wd_col7.toggle("Price", True, key=wk(f"wd_col_price_{selected_week}")),
        show_reserve=wd_col8.toggle(
            "Monthly Reserve",
            False,
            key=wk(f"wd_col_reserve_{selected_week}"),
        ),
        show_count_product=wd_col9.toggle(
            "Count Product",
            False,
            key=wk(f"wd_col_count_product_{selected_week}"),
        ),
        show_w1=wd_col10.toggle("1 W", True, key=wk(f"wd_col_w1_{selected_week}")),
        show_w4=wd_col11.toggle("4 W", True, key=wk(f"wd_col_w4_{selected_week}")),
        show_w5=wd_col12.toggle("5 W", True, key=wk(f"wd_col_w5_{selected_week}")),
    )

    visible_columns = select_visible_week_discount_columns(
        week_discount_columns,
        week_discount_meta,
        wd_settings,
    )
    view_state_key = (
        f"{wd_settings.show_discount}_{wd_settings.show_prom}_"
        f"{wd_settings.show_stock}_{wd_settings.show_margin}_{wd_settings.show_mtost}_"
        f"{wd_settings.show_sold}_{wd_settings.show_price}_{wd_settings.show_reserve}_"
        f"{wd_settings.show_count_product}_"
        f"{wd_settings.show_w1}_{wd_settings.show_w4}_{wd_settings.show_w5}_"
        f"{margin_source}"
    )

    with st.expander("Filters", expanded=False):
        edited_filters_raw = st.data_editor(
            _default_week_discount_filter_df(),
            column_config=_week_discount_filter_column_config(
                week_discount_filter_map,
            ),
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            height=118,
            key=wk(f"wd_filter_table_{selected_week}"),
        )
        edited_filters = (
            edited_filters_raw
            if isinstance(edited_filters_raw, pd.DataFrame)
            else edited_filters_raw.data
        )

    filter_bounds = _filter_bounds_from_week_discount_df(
        edited_filters,
        week_discount_filter_map,
    )

    strategy_settings = _render_discount_strategy_settings(selected_week, scope_key)
    prom_settings = _render_prom_strategy_settings(selected_week, scope_key)
    generated_discount_key = wk(f"wd_generated_discount_{selected_week}")
    generated_prom_key = wk(f"wd_generated_prom_{selected_week}")
    manual_overrides_key = wk(f"wd_manual_overrides_{selected_week}")
    manual_edit_key = wk(f"wd_manual_edit_{selected_week}")
    manual_revision_key = wk(f"wd_manual_revision_{selected_week}")

    progress.progress(65, text="Applying discounts / promotions…")
    manual_overrides = ss.get(manual_overrides_key, {})
    try:
        working_rows = build_working_week_discount_rows(
            week_discount_rows,
            week_discount_filter_map,
            generated_discount=ss.get(generated_discount_key)
            if generated_discount_key in ss and ss[generated_discount_key]
            else None,
            generated_prom=ss.get(generated_prom_key)
            if generated_prom_key in ss and ss[generated_prom_key]
            else None,
            manual_overrides=manual_overrides if manual_overrides else None,
        )
        filtered_rows = apply_week_discount_filters(working_rows, filter_bounds)
    except Exception:
        progress.empty()
        raise
    filter_state_key = "_".join(
        f"{col}:{lo}:{hi}" for col, (lo, hi) in sorted(filter_bounds.items())
    )
    gen_state_key = "1" if generated_discount_key in ss and ss[generated_discount_key] else "0"
    prom_state_key = "1" if generated_prom_key in ss and ss[generated_prom_key] else "0"
    manual_revision = int(ss.get(manual_revision_key, 0))
    manual_state_key = str(manual_revision) if manual_overrides else "0"
    edit_mode = bool(ss.get(manual_edit_key, False))
    can_manual_edit = _can_manual_edit_new_columns(visible_columns)

    _btn_w, _btn_pad = 1, 4
    gen_disc_col, gen_prom_col, _ = st.columns([_btn_w, _btn_w, _btn_pad - _btn_w])
    generate_discount_clicked = gen_disc_col.button(
        "Generate Discount",
        key=wk(f"wd_generate_discount_{selected_week}"),
        help="Apply the selected discount strategy to New Discount.",
        disabled=edit_mode,
        use_container_width=True,
    )
    generate_prom_clicked = gen_prom_col.button(
        "Generate Prom",
        key=wk(f"wd_generate_prom_{selected_week}"),
        help="Apply the selected prom strategy to New Prom.",
        disabled=edit_mode,
        use_container_width=True,
    )
    if generate_discount_clicked:
        progress.progress(80, text="Generating discounts…")
        ss[generated_discount_key] = generate_week_discount_values(
            week_discount_rows,
            week_discount_meta,
            week_discount_filter_map,
            strategy_settings,
        )
        progress.empty()
        st.rerun()
    if generate_prom_clicked:
        progress.progress(80, text="Generating promotions…")
        ss[generated_prom_key] = generate_week_prom_values(
            week_discount_rows,
            week_discount_filter_map,
            prom_settings,
        )
        progress.empty()
        st.rerun()

    if edit_mode:
        apply_col, cancel_col, _ = st.columns([_btn_w, _btn_w, _btn_pad - _btn_w])
        apply_clicked = apply_col.button(
            "Apply",
            key=wk(f"wd_manual_apply_{selected_week}"),
            type="primary",
            use_container_width=True,
        )
        cancel_clicked = cancel_col.button(
            "Cancel",
            key=wk(f"wd_manual_cancel_{selected_week}"),
            use_container_width=True,
        )
    else:
        edit_col, _ = st.columns([_btn_w, _btn_pad])
        edit_clicked = edit_col.button(
            "Edit",
            key=wk(f"wd_manual_edit_btn_{selected_week}"),
            help="Edit New Discount and New Prom for visible baskets.",
            disabled=not can_manual_edit,
            use_container_width=True,
        )
        if edit_clicked:
            progress.empty()
            ss[manual_edit_key] = True
            ss.pop(wk(f"wd_manual_editor_{selected_week}"), None)
            st.rerun()
        apply_clicked = False
        cancel_clicked = False

    if not visible_columns:
        progress.empty()
        st.info("Enable at least one column group to show the table.")
        return

    progress.progress(85, text="Preparing Week Discount table…")
    df_week_discount = pd.DataFrame(filtered_rows, columns=week_discount_columns)
    df_week_discount = df_week_discount.loc[:, visible_columns]

    caption_parts = [f"{len(df_week_discount)} basket(s) shown"]
    if filter_bounds:
        caption_parts.append(f"filtered from {len(week_discount_rows)}")
    if generated_discount_key in ss and ss[generated_discount_key]:
        caption_parts.append(
            f"discount generated for {len(ss[generated_discount_key])} basket(s)"
        )
    if generated_prom_key in ss and ss[generated_prom_key]:
        caption_parts.append(
            f"prom generated for {len(ss[generated_prom_key])} basket(s)"
        )
    if manual_overrides:
        caption_parts.append(f"manual edits for {len(manual_overrides)} basket(s)")
    if edit_mode:
        caption_parts.append(
            "editing New Discount / New Prom (dDiscount / dProm refresh on Apply)",
        )
    st.caption(" · ".join(caption_parts))

    table_state_key = (
        f"{view_state_key}_{filter_state_key}_{gen_state_key}_"
        f"{prom_state_key}_{manual_state_key}"
    )
    progress.progress(95, text="Rendering Week Discount table…")
    if edit_mode:
        editor_key = wk(f"wd_manual_editor_{selected_week}")
        edit_df = _week_discount_rows_to_edit_df(
            filtered_rows,
            week_discount_columns,
            visible_columns,
        )
        edited_raw = st.data_editor(
            edit_df,
            column_config=_week_discount_edit_column_config(visible_columns),
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key=editor_key,
        )
        edited_df = (
            edited_raw if isinstance(edited_raw, pd.DataFrame) else edited_raw.data
        )
        if cancel_clicked:
            progress.empty()
            ss.pop(editor_key, None)
            ss[manual_edit_key] = False
            st.rerun()
        if apply_clicked:
            progress.progress(98, text="Applying manual edits…")
            ss.pop(editor_key, None)
            new_overrides = _manual_overrides_from_edit_df(edited_df, visible_columns)
            merged = dict(ss.get(manual_overrides_key, {}))
            merged.update(new_overrides)
            ss[manual_overrides_key] = merged
            if generated_prom_key in ss and ss[generated_prom_key]:
                gen_prom = dict(ss[generated_prom_key])
                for basket, vals in new_overrides.items():
                    if NEW_PROM_COLUMN in vals:
                        gen_prom[basket] = vals[NEW_PROM_COLUMN]
                ss[generated_prom_key] = gen_prom
            if generated_discount_key in ss and ss[generated_discount_key]:
                gen_disc = dict(ss[generated_discount_key])
                for basket, vals in new_overrides.items():
                    if NEW_DISCOUNT_COLUMN in vals:
                        gen_disc[basket] = vals[NEW_DISCOUNT_COLUMN]
                ss[generated_discount_key] = gen_disc
            ss[manual_revision_key] = manual_revision + 1
            ss[manual_edit_key] = False
            progress.empty()
            st.rerun()
    else:
        st.dataframe(
            _week_discount_styler(df_week_discount),
            use_container_width=True,
            hide_index=True,
            key=wk(f"week_discount_table_{selected_week}_{table_state_key}"),
        )
    progress.empty()

    full_basket_list = _load_full_basket_list()
    include_no_stock = True
    export_all_history = True
    enable_all_bs_export = bool(
        input_mode is not None and input_mode in PRODUCT_BS_INPUT_MODES
    )
    with st.expander("Export", expanded=False):
        if enable_all_bs_export:
            export_col, hist_export_col, hist_all_col, opts_col = st.columns(
                [_btn_w, _btn_w, _btn_w, max(_btn_pad - 2 * _btn_w, 1)],
            )
        else:
            hist_all_col = None
            export_col, hist_export_col, opts_col = st.columns(
                [_btn_w, _btn_w, _btn_pad - _btn_w],
            )
        with opts_col:
            opt_left, opt_right = st.columns(2)
            if full_basket_list:
                include_no_stock = opt_left.checkbox(
                    "Include 'no stock'",
                    value=True,
                    key=wk(f"wd_export_include_no_stock_{selected_week}"),
                    help=(
                        "When checked, export all baskets from the canonical list "
                        f"({len(full_basket_list)}), including those with no current stock in the import."
                    ),
                )
            export_all_history = opt_right.checkbox(
                "all history",
                value=True,
                key=wk(f"wd_export_all_history_{selected_week}"),
                help=(
                    "When checked, discount-history export includes the uploaded history "
                    "plus the new week settings. When unchecked, only the new week is exported."
                ),
            )
        export_rows = filtered_rows
        in_stock_baskets = {
            str(row.get("Basket", ""))
            for row in working_rows
            if str(row.get("Basket", ""))
        }
        if include_no_stock and full_basket_list:
            export_rows = expand_week_discount_export_rows(
                working_rows,
                week_discount_columns,
                full_basket_list,
            )
        export_rows = normalize_week_discount_export_rows(
            export_rows,
            week_discount_columns,
            fill_baskets=(
                in_stock_baskets
                if include_no_stock and full_basket_list
                else None
            ),
        )
        df_export = pd.DataFrame(export_rows, columns=week_discount_columns)
        df_export = df_export.loc[:, visible_columns]
        if include_no_stock and full_basket_list:
            st.caption(f"{len(df_export)} basket(s) in Week Discount export")
        export_col.download_button(
            "Week Discount",
            data=df_export.to_csv(index=False).encode(),
            file_name=f"week_discount_{selected_week}.csv",
            mime="text/csv",
            disabled=df_export.empty or edit_mode,
            use_container_width=True,
            key=wk(
                f"week_discount_export_{selected_week}_{view_state_key}_"
                f"{filter_state_key}_{gen_state_key}_{prom_state_key}_"
                f"{manual_state_key}_{int(include_no_stock)}"
            ),
            help=(
                "Export visible Week Discount columns (raw numeric values). "
                + (
                    "Includes all canonical baskets when 'Include no stock' is checked."
                    if include_no_stock and full_basket_list
                    else "Exports filtered table rows only."
                )
            ),
        )
        try:
            next_week_meta = advance_discount_hist_week_metadata(
                weekly_totals, selected_week
            )
        except ValueError:
            next_week_meta = None
        if next_week_meta is not None:
            new_hist_rows = build_discount_hist_export_rows(
                export_rows,
                next_week_meta,
                discount_hist_category,
            )
            hist_export_rows = merge_discount_hist_export(
                discount_hist_df,
                new_hist_rows,
                include_all_history=export_all_history,
            )
            df_hist_export = pd.DataFrame(
                hist_export_rows, columns=DISCOUNT_HIST_EXPORT_COLUMNS
            )
            hist_export_col.download_button(
                "Discount history. Current",
                data=df_hist_export.to_csv(index=False).encode(),
                file_name=f"discount_hist_{next_week_meta['year_week']}.csv",
                mime="text/csv",
                disabled=df_hist_export.empty or edit_mode,
                use_container_width=True,
                key=wk(
                    f"week_discount_hist_export_{selected_week}_{view_state_key}_"
                    f"{filter_state_key}_{gen_state_key}_{prom_state_key}_"
                    f"{manual_state_key}_{int(include_no_stock)}_{int(export_all_history)}_"
                    f"{discount_hist_category}"
                ),
                help=(
                    "Export New Discount / New Prom in discount-history input format "
                    f"for week {next_week_meta['year_week']} "
                    f"({DISCOUNT_HIST_DISCOUNT_COLUMNS.get(discount_hist_category, 'discount')} / "
                    f"{DISCOUNT_HIST_PROM_COLUMNS.get(discount_hist_category, 'prom with stock')}). "
                    + (
                        "Includes full uploaded history when 'all history' is checked."
                        if export_all_history
                        else "Exports only the new week."
                    )
                ),
            )
            if hist_all_col is not None and input_mode is not None:
                built_scopes = iter_built_product_bs_scopes(ss, input_mode)
                category_rows: dict[str, list[dict]] = {}
                hist_sources: list[pd.DataFrame] = []
                for category, cat_scope in built_scopes:
                    analysis = cat_scope.get("analysis")
                    if analysis is None:
                        continue
                    cat_key = product_bs_scope_key(input_mode, category)
                    cat_hist = _category_week_discount_hist_export_rows(
                        analysis,
                        selected_week,
                        category,
                        next_week_meta,
                        ss,
                        cat_key,
                        include_no_stock=include_no_stock,
                        full_basket_list=full_basket_list,
                        margin_by_basket=cat_scope.get("basket_margin_hybrid"),
                    )
                    if cat_hist:
                        category_rows[category] = cat_hist
                    src_df = cat_scope.get("discount_hist_df")
                    if isinstance(src_df, pd.DataFrame) and not src_df.empty:
                        hist_sources.append(src_df)
                combined_new = combine_discount_hist_export_by_category(category_rows)
                combined_source = (
                    merge_discount_hist_dataframes(hist_sources)
                    if hist_sources
                    else None
                )
                all_hist_rows = merge_discount_hist_export(
                    combined_source
                    if combined_source is not None and not combined_source.empty
                    else None,
                    combined_new,
                    include_all_history=export_all_history,
                )
                df_all_hist = pd.DataFrame(
                    all_hist_rows, columns=DISCOUNT_HIST_EXPORT_COLUMNS
                )
                built_labels = (
                    ", ".join(category_rows.keys()) if category_rows else "none"
                )
                hist_all_col.download_button(
                    "Discount history. All",
                    data=df_all_hist.to_csv(index=False).encode(),
                    file_name=(
                        f"discount_hist_all_bs_{next_week_meta['year_week']}.csv"
                    ),
                    mime="text/csv",
                    disabled=df_all_hist.empty or edit_mode or not category_rows,
                    use_container_width=True,
                    key=wk(
                        f"week_discount_hist_export_all_bs_{selected_week}_"
                        f"{view_state_key}_{filter_state_key}_{gen_state_key}_"
                        f"{prom_state_key}_{manual_state_key}_"
                        f"{int(include_no_stock)}_{int(export_all_history)}_"
                        f"{len(category_rows)}"
                    ),
                    help=(
                        "Combine New Discount / New Prom from every Product BS Category "
                        f"already built in this session ({built_labels}) into one "
                        f"discount-history file for week {next_week_meta['year_week']}. "
                        "Build and generate/edit each category before exporting."
                    ),
                )
        else:
            hist_export_col.button(
                "Discount history. Current",
                disabled=True,
                use_container_width=True,
                help="Week metadata unavailable for discount-history export.",
            )
            if hist_all_col is not None:
                hist_all_col.button(
                    "Discount history. All",
                    disabled=True,
                    use_container_width=True,
                    help="Week metadata unavailable for discount-history export.",
                )

    summary = compute_week_discount_summary(
        filtered_rows,
        week_discount_filter_map,
    )
    all_comparisons = compute_week_discount_weighted_comparisons(
        filtered_rows,
        week_discount_meta,
        week_discount_filter_map,
    )

    sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
    sum_col1.metric("max (dDiscount)", _fmt_pct(summary["max_dDiscount"]))
    sum_col2.metric("min (dDiscount)", _fmt_pct(summary["min_dDiscount"]))
    sum_col3.metric("max (dProm)", _fmt_pct(summary["max_dProm"]))
    sum_col4.metric("min (dProm)", _fmt_pct(summary["min_dProm"]))

    with st.container(border=True):
        weight_col, _ = st.columns([2, 10])
        weight_label = weight_col.selectbox(
            "Weights",
            list(DISCOUNT_PROM_WEIGHT_CHOICES),
            index=0,
            key=wk("wd_weight_metric"),
            help=(
                "Show precomputed Discount and Prom weighted by Stock, "
                "CountProduct, or Sold for Current − 1W, Current, and New."
            ),
        )
        weight_metric = discount_prom_weight_key(weight_label)
        discount_col_label, prom_col_label = discount_prom_weight_column_labels(
            weight_metric
        )
        comparison = all_comparisons.get(weight_metric, all_comparisons["stock"])
        st.caption(
            f"{discount_col_label} and {prom_col_label} use {weight_label} weights "
            "across Current − 1W, Current, and New."
        )
        comparison_rows = [
            {
                "Period": "Current - 1W",
                discount_col_label: _fmt_pct(
                    comparison["current_minus_1w"]["W_Discount"]
                ),
                prom_col_label: _fmt_pct(comparison["current_minus_1w"]["W_Prom"]),
                "count (Prom)": str(comparison["current_minus_1w"]["count_Prom"]),
            },
            {
                "Period": "Current",
                discount_col_label: _fmt_pct(comparison["current"]["W_Discount"]),
                prom_col_label: _fmt_pct(comparison["current"]["W_Prom"]),
                "count (Prom)": str(comparison["current"]["count_Prom"]),
            },
            {
                "Period": "New",
                discount_col_label: _fmt_pct(comparison["new"]["W_Discount"]),
                prom_col_label: _fmt_pct(comparison["new"]["W_Prom"]),
                "count (Prom)": str(comparison["new"]["count_Prom"]),
            },
        ]
        st.dataframe(
            pd.DataFrame(comparison_rows),
            use_container_width=True,
            hide_index=True,
            key=wk(
                f"wd_weighted_compare_{selected_week}_{weight_metric}_{table_state_key}"
            ),
        )
