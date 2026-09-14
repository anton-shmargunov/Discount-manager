"""
Correlation & Group Analysis — main Streamlit page.

UI responsibilities only:
- File uploads and filter widgets.
- Triggering analytical workflows via core/ functions.
- Rendering results using visualizations/ chart builders.

No analytical logic lives here.
"""

from __future__ import annotations
import math
import io
from pathlib import Path
import pandas as pd
import streamlit as st

from core.analytics.basket_analysis import (
    run_tracking_report_analysis,
    run_tracking_product_bs_report_analysis,
    apply_kmeans,
    apply_octants,
    compute_sumup_series,
    apply_discount_hist_to_basket_data,
    init_discount_prom_on_basket_data,
    AnalysisResult,
)
from core.analytics.cost_correction import (
    COST_CORRECTION_FROM_LAST_POINT,
    COST_CORRECTION_MODES,
    compute_corrections_for_baskets,
    compute_cost_margin_correction,
    enrich_sumup_with_corrected_totals,
    fit_bulk_cost_price,
    hybrid_margin_map,
)
from core.analytics.week_basket_tables import compute_basket_week_detail_rows
from ui.week_discount_ui import render_week_discount_section
from ui.project_save_ui import apply_pending_project_restore, render_sidebar_project_panel
from ui.product_bs_scope import (
    AGGREGATED_DISCOUNT_HIST_CATEGORY,
    PRODUCT_BS_CATEGORY_OPTIONS,
    PRODUCT_BS_INPUT_MODES,
    PRODUCT_BS_MONTHLY_AV_MODE,
    PRODUCT_BS_ON_DATE_MODE,
    TRACKING_REPORT_MODE,
    clear_product_bs_scope_derived,
    get_product_bs_scope,
    product_bs_scope_key,
    scoped_widget_key,
)
from core.transforms.data_prep import merge_discount_hist_dataframes
from core.models import BasketTimeSeries, Planefit, Linefit
from core.modeling.regression import (
    fit_plane,
    fit_line,
)
from core.optimization.price_optimization import (
    evaluate_week_margin_model,
    build_margin_surface,
    compute_price_max_curve,
)
from core.statistics.correlations import compute_pearson
from core.statistics.metrics import monthly_reserve_series
from core.statistics.ratios import ratio_series
from visualizations.cluster_charts import build_2d_cluster_scatter, build_3d_cluster_scatter
from visualizations.detail_charts import (
    build_basket_scatter_3panel,
    build_cost_vs_price,
    build_3d_price_sold_m,
    build_3d_price_stock_sold,
    build_3d_price_stock_m,
    build_price_max_curve,
)
from visualizations.progress_stack import build_vertical_stack_from_specs
from visualizations.sumup_charts import (
    build_combined_progress,
    build_sumup_cost_vs_price,
    build_sumup_3panel,
    build_sumup_3d,
    build_sumup_stock_m_3d,
    build_sumup_stock_sold_3d,
    build_metric_progress,
    build_weekly_basket_3panel,
    build_weekly_basket_3d,
    build_weekly_basket_stock_sold_3d,
    build_weekly_basket_stock_m_3d,
)
from configs.settings import (
    KMEANS_DEFAULT_K,
    KMEANS_MAX_K,
    DEFAULT_MIN_PRICE,
    CLUSTER_BORDER_COLORS,
    CLUSTER_COLORS,
    UNCLUSTERED_COLOR,
)
from configs.theme_bootstrap import apply_page_theme

# ─────────────────────────────────────────────────────────────────────────────
# Helper display utilities  (defined first — called throughout the page)
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(val: float | None) -> str:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "N/A"
    return f"{val:.2f}"


def _fmt3(val: float) -> str:
    if math.isnan(val):
        return "N/A"
    return f"{val:.3f}"


def _fmt2(val: float) -> str:
    if math.isnan(val):
        return "N/A"
    return f"{val:.2f}"


def _basket_series_values(ts: BasketTimeSeries, values: list[float]) -> list[float]:
    n = ts.n_weeks
    if not values:
        return [0.0] * n
    if len(values) < n:
        return list(values) + [0.0] * (n - len(values))
    return list(values[:n])


def _basket_optional_metric_values(ts: BasketTimeSeries, values: list[float]) -> list[float]:
    """Align optional per-week metrics; missing weeks stay NaN."""
    n = ts.n_weeks
    aligned = [float("nan")] * n
    for i, value in enumerate(values[:n]):
        aligned[i] = float(value)
    return aligned


def _basket_week_progress_specs(ts: BasketTimeSeries) -> list[dict]:
    revenue = [s * p for s, p in zip(ts.sold, ts.price)]
    return [
        {
            "key": "stock",
            "label": "Stock",
            "default": True,
            "title": "Stock vs Week",
            "y_title": "Stock Qty",
            "values": _basket_series_values(ts, ts.stock),
            "marker_color": "rgba(236,72,153,0.75)",
            "line_color": "rgb(219,39,119)",
        },
        {
            "key": "count_product",
            "label": "CountProduct",
            "default": False,
            "title": "CountProduct vs Week",
            "y_title": "CountProduct",
            "values": _basket_series_values(ts, ts.count_product),
            "marker_color": "rgba(249,115,22,0.75)",
            "line_color": "rgb(234,88,12)",
        },
        {
            "key": "price",
            "label": "Price",
            "default": True,
            "title": "Avg Price vs Week",
            "y_title": "Avg Price",
            "values": ts.price,
            "marker_color": "rgba(16,185,129,0.75)",
            "line_color": "rgb(5,150,105)",
        },
        {
            "key": "discount",
            "label": "Discount",
            "default": False,
            "title": "Discount vs Week",
            "y_title": "Discount",
            "values": _basket_optional_metric_values(ts, ts.discount),
            "marker_color": "rgba(244,63,94,0.75)",
            "line_color": "rgb(225,29,72)",
        },
        {
            "key": "prom",
            "label": "Prom",
            "default": False,
            "title": "Prom vs Week",
            "y_title": "Prom",
            "values": _basket_optional_metric_values(ts, ts.prom),
            "marker_color": "rgba(99,102,241,0.75)",
            "line_color": "rgb(79,70,229)",
        },
        {
            "key": "purchase",
            "label": "Purchase",
            "default": False,
            "title": "Purchase vs Week",
            "y_title": "Purchase Qty",
            "values": _basket_series_values(ts, ts.purchase),
            "marker_color": "rgba(6,182,212,0.75)",
            "line_color": "rgb(8,145,178)",
        },
        {
            "key": "sold",
            "label": "Sold",
            "default": True,
            "title": "Sold vs Week",
            "y_title": "Sold Qty",
            "values": ts.sold,
            "marker_color": "rgba(59,130,246,0.75)",
            "line_color": "rgb(37,99,235)",
        },
        {
            "key": "revenue",
            "label": "Revenue",
            "default": False,
            "title": "Revenue vs Week",
            "y_title": "Revenue",
            "values": revenue,
            "marker_color": "rgba(20,184,166,0.75)",
            "line_color": "rgb(13,148,136)",
        },
        {
            "key": "margin",
            "label": "Margin",
            "default": True,
            "title": "Margin vs Week",
            "y_title": "Margin",
            "values": ts.m,
            "marker_color": "rgba(139,92,246,0.75)",
            "line_color": "rgb(109,40,217)",
        },
        {
            "key": "recap",
            "label": "Recap",
            "default": False,
            "title": "Recap vs Week",
            "y_title": "Recap",
            "values": _basket_optional_metric_values(ts, getattr(ts, "recap", []) or []),
            "marker_color": "rgba(245,158,11,0.75)",
            "line_color": "rgb(217,119,6)",
        },
        {
            "key": "cost_per_sold",
            "label": "Cost/Sold",
            "default": False,
            "title": "Cost per Sold vs Week",
            "y_title": "Cost per Sold",
            "values": ts.cost,
            "marker_color": "rgba(107,114,128,0.75)",
            "line_color": "rgb(75,85,99)",
        },
        {
            "key": "monthly_reserve",
            "label": "Monthly Reserve",
            "default": False,
            "title": "Monthly Reserve vs Week",
            "y_title": "Months",
            "values": monthly_reserve_series(
                _basket_series_values(ts, ts.stock),
                ts.sold,
            ),
            "marker_color": "rgba(234,179,8,0.75)",
            "line_color": "rgb(202,138,4)",
        },
        {
            "key": "sold_to_stock",
            "label": "SoldToStock",
            "default": False,
            "title": "SoldToStock vs Week",
            "y_title": "Sold / Stock",
            "values": ratio_series(ts.sold, ts.stock),
            "marker_color": "rgba(14,165,233,0.75)",
            "line_color": "rgb(2,132,199)",
        },
        {
            "key": "mtost",
            "label": "MtoSt",
            "default": False,
            "title": "MtoSt vs Week",
            "y_title": "Margin / Stock",
            "values": ratio_series(ts.m, ts.stock),
            "marker_color": "rgba(6,182,212,0.75)",
            "line_color": "rgb(8,145,178)",
        },
        {
            "key": "mtosold",
            "label": "MtoSold",
            "default": False,
            "title": "MtoSold vs Week",
            "y_title": "Margin / Sold",
            "values": ratio_series(ts.m, ts.sold),
            "marker_color": "rgba(132,204,22,0.75)",
            "line_color": "rgb(101,163,13)",
        },
    ]


def _render_progress_toggles(
    specs: list[dict],
    key_fn,
) -> list[dict]:
    """Render metric switches in rows of 4 and return the enabled specs."""
    enabled: list[dict] = []
    for row_start in range(0, len(specs), 4):
        cols = st.columns(4)
        for offset, spec in enumerate(specs[row_start:row_start + 4]):
            with cols[offset]:
                if st.toggle(
                    spec["label"],
                    value=spec["default"],
                    key=key_fn(spec["key"]),
                ):
                    enabled.append(spec)
    return enabled


def _sumup_week_progress_specs(
    valid_weeks: list[str],
    sumup_rows: list[dict],
    *,
    total_margin_corrected: list[float] | None = None,
    total_cost_corrected: list[float] | None = None,
) -> list[dict]:
    by_week = {str(row["week"]): row for row in sumup_rows}

    def _series(key: str) -> list[float]:
        values: list[float] = []
        for week in valid_weeks:
            row = by_week.get(str(week))
            if row is None:
                values.append(float("nan"))
                continue
            value = row.get(key, float("nan"))
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                values.append(float("nan"))
        return values

    total_stock = _series("total_stock")
    total_sold = _series("total_sold")
    total_margin = _series("total_m")
    total_cost = _series("total_cost")
    return [
        {
            "key": "stock",
            "label": "Total Stock",
            "default": True,
            "title": "Total Stock vs Week",
            "y_title": "Total Stock",
            "values": total_stock,
            "marker_color": "rgba(236,72,153,0.75)",
            "line_color": "rgb(219,39,119)",
        },
        {
            "key": "count_product",
            "label": "Total CountProduct",
            "default": False,
            "title": "Total CountProduct vs Week",
            "y_title": "Total CountProduct",
            "values": _series("total_count_product"),
            "marker_color": "rgba(249,115,22,0.75)",
            "line_color": "rgb(234,88,12)",
        },
        {
            "key": "price",
            "label": "W. Price",
            "default": True,
            "title": "W. Price vs Week",
            "y_title": "W. Price",
            "values": _series("weighted_price"),
            "marker_color": "rgba(16,185,129,0.75)",
            "line_color": "rgb(5,150,105)",
        },
        {
            "key": "purchase",
            "label": "Total Purchase",
            "default": False,
            "title": "Total Purchase vs Week",
            "y_title": "Total Purchase",
            "values": _series("total_purchase"),
            "marker_color": "rgba(6,182,212,0.75)",
            "line_color": "rgb(8,145,178)",
        },
        {
            "key": "sold",
            "label": "Total Sold",
            "default": True,
            "title": "Total Sold vs Week",
            "y_title": "Total Sold",
            "values": total_sold,
            "marker_color": "rgba(59,130,246,0.75)",
            "line_color": "rgb(37,99,235)",
        },
        {
            "key": "revenue",
            "label": "Total Revenue",
            "default": False,
            "title": "Total Revenue vs Week",
            "y_title": "Total Revenue",
            "values": _series("total_revenue"),
            "marker_color": "rgba(20,184,166,0.75)",
            "line_color": "rgb(13,148,136)",
        },
        {
            "key": "margin",
            "label": "Total Margin",
            "default": True,
            "title": "Total Margin vs Week",
            "y_title": "Total Margin",
            "values": total_margin,
            "overlay_values": total_margin_corrected,
            "overlay_name": "Total Margin Corrected",
            "marker_color": "rgba(139,92,246,0.75)",
            "line_color": "rgb(109,40,217)",
        },
        {
            "key": "recap",
            "label": "Total Recap",
            "default": False,
            "title": "Total Recap vs Week",
            "y_title": "Total Recap",
            "values": _series("total_recap"),
            "marker_color": "rgba(245,158,11,0.75)",
            "line_color": "rgb(217,119,6)",
        },
        {
            "key": "cost",
            "label": "Total Cost",
            "default": False,
            "title": "Total Cost vs Week",
            "y_title": "Total Cost",
            "values": total_cost,
            "overlay_values": total_cost_corrected,
            "overlay_name": "Cost Corrected",
            "marker_color": "rgba(107,114,128,0.75)",
            "line_color": "rgb(75,85,99)",
        },
        {
            "key": "monthly_reserve",
            "label": "Total Monthly Reserve",
            "default": False,
            "title": "Total Monthly Reserve vs Week",
            "y_title": "Months",
            "values": _series("total_monthly_reserve"),
            "marker_color": "rgba(234,179,8,0.75)",
            "line_color": "rgb(202,138,4)",
        },
        {
            "key": "sold_to_stock",
            "label": "SoldToStock",
            "default": False,
            "title": "SoldToStock vs Week",
            "y_title": "Sold / Stock",
            "values": ratio_series(total_sold, total_stock),
            "marker_color": "rgba(14,165,233,0.75)",
            "line_color": "rgb(2,132,199)",
        },
        {
            "key": "mtost",
            "label": "MtoSt",
            "default": False,
            "title": "MtoSt vs Week",
            "y_title": "Margin / Stock",
            "values": ratio_series(total_margin, total_stock),
            "overlay_values": (
                ratio_series(total_margin_corrected, total_stock)
                if total_margin_corrected is not None
                else None
            ),
            "overlay_name": "MtoSt Corrected",
            "marker_color": "rgba(6,182,212,0.75)",
            "line_color": "rgb(8,145,178)",
        },
        {
            "key": "mtosold",
            "label": "MtoSold",
            "default": False,
            "title": "MtoSold vs Week",
            "y_title": "Margin / Sold",
            "values": ratio_series(total_margin, total_sold),
            "overlay_values": (
                ratio_series(total_margin_corrected, total_sold)
                if total_margin_corrected is not None
                else None
            ),
            "overlay_name": "MtoSold Corrected",
            "marker_color": "rgba(132,204,22,0.75)",
            "line_color": "rgb(101,163,13)",
        },
    ]


def _set_log(lines: list[str]) -> None:
    st.session_state.log_messages = lines


def _append_log(message: str) -> None:
    st.session_state.log_messages.append(message)


def _analysis_log_lines(analysis: AnalysisResult) -> list[str]:
    if analysis.all_weeks:
        week_range = f"{analysis.all_weeks[0]} to {analysis.all_weeks[-1]}"
    else:
        week_range = "N/A"
    return [
        f"Baskets built: {analysis.basket_count}",
        f"Weeks built: {analysis.week_count}",
        f"Week range: {week_range}",
    ]


def _render_planefit_stats(fit: Planefit, label: str = "") -> None:
    if label:
        st.markdown(f"**Model:** {label}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Parameters**")
        # st.write(f"z₀ (intercept): `{fit.z0:.8f}`")
        # st.write(f"a (x-coeff):    `{fit.a:.8f}`")
        # st.write(f"b (y-coeff):    `{fit.b:.8f}`")

        st.metric(f"z₀ (intercept)", f"{fit.z0:.4f}")
        st.metric(f"a (x-coeff)", f"{fit.a:.4f}")
        st.metric(f"b (y-coeff)", f"{fit.b:.5f}")

    with c2:
        st.markdown("**Error Metrics**")
        st.metric("Adj R²", "N/A" if math.isnan(fit.adj_r2) else f"{fit.adj_r2:.4f}")
        st.metric("RMSE",   f"{fit.rmse:.4f}")
        st.metric("MAPE",   "N/A" if math.isnan(fit.mape) else f"{fit.mape:.2f}%")


def _render_linefit_stats(fit: Linefit) -> None:
    st.markdown("**Model:** Cost = z₀ + a·Price")
    #st.markdown("**Model:** `Cost = z₀ + a·Price`")
    #st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Parameters**")
        st.metric(f"z₀ (intercept)", f"{fit.z0:.4f}")
        st.metric(f"a (slope)", f"{fit.a:.5f}")
        st.metric(f"Pl", "N/A" if math.isnan(fit.pl) else f"{fit.pl:.4f}")

        # st.markdown("**Parameters**")
        # st.write(f"z₀ (intercept): `{fit.z0:.8f}`")
        # st.write(f"a (slope):      `{fit.a:.8f}`")
        # st.write(f"Pl:             `{'N/A' if math.isnan(fit.pl) else f'{fit.pl:.8f}'}`")

    with c2:
        st.markdown("**Error Metrics**")
        st.metric("R²",   "N/A" if math.isnan(fit.r2) else f"{fit.r2:.4f}")
        st.metric("RMSE", f"{fit.rmse:.4f}")
        st.metric("MAPE", "N/A" if math.isnan(fit.mape) else f"{fit.mape:.2f}%")


def _render_margin_model(
    basket_name: str,
    ts: BasketTimeSeries,
    fit_sold: Planefit,
    fit_cost: Linefit,
    scope: dict,
    sk,
    m_values: list[float] | None = None,
) -> None:

    def wk(widget_key: str) -> str:
        return sk(widget_key)

    m_series = list(m_values) if m_values is not None else list(ts.m)

    set_clmn, result_clmn = st.columns([1, 2])
    with set_clmn.container(border=True):
        run_margin_model_clicked = st.button("▶ Run Margin Model", key=wk(f"run_model_{basket_name}"))
        """Render the analytical margin optimisation UI block."""
        week_options = {
            f"{week}  (QW:{ts.quadweeks[i]})": i
            for i, week in enumerate(ts.weeks)
        }
        selected_label = st.selectbox(
            "Evaluation Week", list(week_options.keys()),
            index=len(week_options) - 1,
            key=wk(f"model_week_{basket_name}"),
        )
        week_idx = week_options[selected_label]

        mc1, mc2 = st.columns(2)
        p_range = max(ts.price) - min(ts.price) or 1.0
        s_range = max(ts.stock) - min(ts.stock) or 1.0
        p_min_val = mc1.number_input("Min Price", value=float(min(ts.price)) - p_range * 0.1,
                                    key=wk(f"mp_min_{basket_name}"))
        p_max_val = mc1.number_input("Max Price", value=float(max(ts.price)) + p_range * 0.1,
                                    key=wk(f"mp_max_{basket_name}"))
        s_min_val = mc2.number_input("Min Stock", value=float(min(ts.stock)) - s_range * 0.1,
                                    key=wk(f"ms_min_{basket_name}"))
        s_max_val = mc2.number_input("Max Stock", value=float(max(ts.stock)) + s_range * 0.1,
                                    key=wk(f"ms_max_{basket_name}"))
        n_p = st.slider("Price grid points", 10, 100, 50, key=wk(f"np_{basket_name}"))
        n_s = st.slider("Stock grid points", 10, 100, 50, key=wk(f"ns_{basket_name}"))

        if run_margin_model_clicked:
            res = evaluate_week_margin_model(
                week=ts.weeks[week_idx],
                price_actual=ts.price[week_idx],
                stock_actual=ts.stock[week_idx],
                m_actual=m_series[week_idx],
                fit_sold=fit_sold,
                fit_cost=fit_cost,
            )
            prices_grid, stocks_grid, m_grid = build_margin_surface(
                fit_sold, fit_cost,
                price_range=(p_min_val, p_max_val),
                stock_range=(s_min_val, s_max_val),
                n_price=n_p, n_stock=n_s,
            )
            p_max_vals = compute_price_max_curve(fit_sold, fit_cost, stocks_grid)
            scope["margin_model"][basket_name] = {
                "result": res,
                "surface": (prices_grid, stocks_grid, m_grid),
                "stock_grid": stocks_grid,
                "price_max_values": p_max_vals,
            }
            st.rerun()
    with result_clmn:
        saved_model = scope["margin_model"].get(basket_name)
        if saved_model:
            with st.container(border=True):
                res = saved_model["result"]
                rc1, rc2, rc3 = st.columns(3)
                with rc1:
                    st.markdown("**Actual Results**")
                    st.metric(f"Price (actual)", _fmt( res.price_actual ) )
                    st.metric(f"Stock (actual)", _fmt( res.stock_actual ) )
                    st.metric(f"Margin (actual)", _fmt( res.m_actual ) )
                    
                    # st.write(f"Price (actual): `{res.price_actual:.2f}`")
                    # st.write(f"Stock (actual): `{res.stock_actual:.2f}`")
                    # st.write(f"Margin (actual): `{res.m_actual:.2f}`")
                    # st.write(f"Margin (model):   `{res.m_model:.2f}`")
                    # st.write(f"|dM| error:     `{res.m_error_abs:.2f}`")
                    # st.write(f"Error %:        `{_fmt(res.m_error_pct)}%`")

                    # rc1_1, rc1_2 = st.columns(2)
                    # with rc1_1:
                    #     st.markdown("**Actual Results**")
                    #     st.metric(f"Price (actual)", _fmt( res.price_actual ) )
                    #     st.metric(f"Stock (actual)", _fmt( res.stock_actual ) )
                    #     st.metric(f"Margin (actual)", _fmt( res.m_actual ) )

                    # with rc1_2:
                    #     st.markdown("**Model at Price (actual)**")
                    #     st.metric(f"Margin (model)", _fmt(res.m_model))
                    #     st.metric(f"|dM| error", _fmt(res.m_error_abs))
                    #     st.metric(f"Error %", _fmt(res.m_error_pct))

                with rc2:
                    st.markdown("**Model at Price (actual)**")
                    st.metric(f"Margin (model)", _fmt(res.m_model))
                    st.metric(f"|dM| error", _fmt(res.m_error_abs))
                    st.metric(f"Error %", _fmt(res.m_error_pct))
                with rc3:
                    st.markdown("**Optimisation**")
                    #st.metric("Price_max",       _fmt(res.price_max), delta=f"{res.price_diff:+.2f}" )
                    st.metric("Price_max",       _fmt(res.price_max) )
                    st.metric("Price_diff",      _fmt(res.price_diff),)
                    st.metric("M surplus (gain)", _fmt(res.m_surplus))

    if saved_model:
        fig_pmax = build_price_max_curve(
            saved_model["stock_grid"],
            saved_model["price_max_values"],
        )
        st.plotly_chart(fig_pmax, use_container_width=True,
                        key=wk(f"pmax_curve_{basket_name}"))


def _render_sumup_margin_model(
    sumup_rows: list[dict],
    fit_sold: Planefit,
    fit_cost: Linefit,
    scope: dict,
    sk,
    margin_key: str = "total_m",
) -> None:

    def wk(widget_key: str) -> str:
        return sk(widget_key)
    """Render analytical margin optimisation for aggregate Sum-Up weekly data."""
    set_clmn, result_clmn = st.columns([1, 2])
    with set_clmn.container(border=True):
        run_margin_model_clicked = st.button("▶ Run Margin Model", key=wk("run_sumup_margin_model"))
        week_options = {
            f"{row['week']}  (QW:{row.get('quadweek', 'N/A')})": i
            for i, row in enumerate(sumup_rows)
        }
        selected_label = st.selectbox(
            "Evaluation Week",
            list(week_options.keys()),
            index=len(week_options) - 1,
            key=wk("sumup_model_week"),
        )
        week_idx = week_options[selected_label]

        prices = [r["weighted_price"] for r in sumup_rows]
        stocks = [r["total_stock"] for r in sumup_rows]
        p_range = max(prices) - min(prices) or 1.0
        s_range = max(stocks) - min(stocks) or 1.0
        mc1, mc2 = st.columns(2)
        p_min_val = mc1.number_input(
            "Min W. Price",
            value=float(min(prices)) - p_range * 0.1,
            key=wk("sumup_mp_min"),
        )
        p_max_val = mc1.number_input(
            "Max W. Price",
            value=float(max(prices)) + p_range * 0.1,
            key=wk("sumup_mp_max"),
        )
        s_min_val = mc2.number_input(
            "Min Total Stock",
            value=float(min(stocks)) - s_range * 0.1,
            key=wk("sumup_ms_min"),
        )
        s_max_val = mc2.number_input(
            "Max Total Stock",
            value=float(max(stocks)) + s_range * 0.1,
            key=wk("sumup_ms_max"),
        )
        n_p = st.slider("Price grid points", 10, 100, 50, key=wk("sumup_np"))
        n_s = st.slider("Stock grid points", 10, 100, 50, key=wk("sumup_ns"))

        if run_margin_model_clicked:
            row = sumup_rows[week_idx]
            res = evaluate_week_margin_model(
                week=row["week"],
                price_actual=row["weighted_price"],
                stock_actual=row["total_stock"],
                m_actual=row.get(margin_key, row["total_m"]),
                fit_sold=fit_sold,
                fit_cost=fit_cost,
            )
            prices_grid, stocks_grid, m_grid = build_margin_surface(
                fit_sold,
                fit_cost,
                price_range=(p_min_val, p_max_val),
                stock_range=(s_min_val, s_max_val),
                n_price=n_p,
                n_stock=n_s,
            )
            p_max_vals = compute_price_max_curve(fit_sold, fit_cost, stocks_grid)
            scope["sumup_margin_model"] = {
                "result": res,
                "surface": (prices_grid, stocks_grid, m_grid),
                "stock_grid": stocks_grid,
                "price_max_values": p_max_vals,
            }
            st.rerun()

    with result_clmn:
        saved_model = scope["sumup_margin_model"]
        if saved_model:
            with st.container(border=True):
                res = saved_model["result"]
                rc1, rc2, rc3 = st.columns(3)
                with rc1:
                    st.markdown("**Actual Results**")
                    st.metric("W. Price (actual)", _fmt(res.price_actual))
                    st.metric("Total Stock (actual)", _fmt(res.stock_actual))
                    st.metric("Total Margin (actual)", _fmt(res.m_actual))
                with rc2:
                    st.markdown("**Model at Price (actual)**")
                    st.metric("Total Margin (model)", _fmt(res.m_model))
                    st.metric("|dM| error", _fmt(res.m_error_abs))
                    st.metric("Error %", _fmt(res.m_error_pct))
                with rc3:
                    st.markdown("**Optimisation**")
                    st.metric("Price_max", _fmt(res.price_max), delta=f"{res.price_diff:+.2f}")
                    st.metric("Margin surplus", _fmt(res.m_surplus))

        if saved_model:
            fig_pmax = build_price_max_curve(
                saved_model["stock_grid"],
                saved_model["price_max_values"],
            )
            st.plotly_chart(fig_pmax, use_container_width=True, key=wk("sumup_pmax_curve"))


def _parse_float(raw: str, default: float) -> float:
    s = raw.strip()
    if s == "":
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _parse_optional_float(raw: str) -> float | None:
    s = str(raw or "").strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _apply_optional_discount_hist(
    basket_data: dict[str, BasketTimeSeries],
    file_discount_hist,
    discount_category: str,
    log_lines: list[str],
) -> pd.DataFrame | None:
    """Load optional discount history CSV(s) and merge discount/prom into basket data.

    Accepts a single uploaded file, a list of files, or None. Multiple files are
    aggregated by ``(year_week, basket)`` before applying the active category.
    """
    if file_discount_hist is None:
        init_discount_prom_on_basket_data(basket_data)
        return None

    uploads = (
        list(file_discount_hist)
        if isinstance(file_discount_hist, (list, tuple))
        else [file_discount_hist]
    )
    if not uploads:
        init_discount_prom_on_basket_data(basket_data)
        return None

    frames: list[pd.DataFrame] = []
    for upload in uploads:
        frames.append(pd.read_csv(io.BytesIO(upload.read())))

    if len(frames) == 1:
        df_discount_hist = frames[0]
        log_lines.append(f"Discount history rows uploaded: {len(df_discount_hist)}")
    else:
        df_discount_hist = merge_discount_hist_dataframes(frames)
        log_lines.append(
            f"Discount history files uploaded: {len(frames)} "
            f"(aggregated to {len(df_discount_hist)} basket-week rows)"
        )

    log_lines.append(f"Discount history category: {discount_category}")
    log_lines.extend(
        apply_discount_hist_to_basket_data(
            basket_data,
            df_discount_hist,
            discount_category,
        )
    )
    return df_discount_hist.copy()


def _quadweek_fit_options(ts: BasketTimeSeries) -> list[str]:
    quadweeks = sorted({str(qw) for qw in ts.quadweeks if str(qw) and str(qw) != "N/A"})
    return ["All Quadweeks", *[f"Quadweek: {qw}" for qw in quadweeks], "Manual Selection"]


def _manual_fit_indices(
    ts: BasketTimeSeries,
    key: str,
    value_label: str,
    values: list[float],
) -> list[int]:
    select_all = st.toggle("Select All", value=True, key=f"{key}_select_all")
    table = pd.DataFrame({
        "Select": [select_all] * ts.n_weeks,
        "Week": [str(w) for w in ts.weeks],
        "QW": [str(qw) for qw in ts.quadweeks],
        value_label: values,
    })
    edited = st.data_editor(
        table,
        hide_index=True,
        use_container_width=True,
        height=360,
        key=key,
        disabled=["Week", "QW", value_label],
        column_config={
            "Select": st.column_config.CheckboxColumn("Select", default=True),
            value_label: st.column_config.NumberColumn(value_label, format="%.2f"),
        },
    )
    return [i for i, selected in enumerate(edited["Select"].tolist()) if selected]


def _resolve_fit_indices(
    ts: BasketTimeSeries,
    fit_scope: str,
    manual_indices: list[int] | None = None,
) -> list[int]:
    if fit_scope == "All Quadweeks":
        return list(range(ts.n_weeks))

    if fit_scope == "Manual Selection":
        return manual_indices or []

    selected_qw = fit_scope.replace("Quadweek: ", "", 1)
    return [i for i, qw in enumerate(ts.quadweeks) if str(qw) == selected_qw]


def _sumup_fit_options(sumup_rows: list[dict]) -> list[str]:
    quadweeks = sorted({
        str(r.get("quadweek", "N/A"))
        for r in sumup_rows
        if str(r.get("quadweek", "N/A")) and str(r.get("quadweek", "N/A")) != "N/A"
    })
    return ["All Quadweeks", *[f"Quadweek: {qw}" for qw in quadweeks], "Manual Selection"]


def _manual_sumup_fit_indices(
    sumup_rows: list[dict],
    key: str,
) -> list[int]:
    select_all = st.toggle("Select All", value=True, key=f"{key}_select_all")
    table = pd.DataFrame({
        "Select": [select_all] * len(sumup_rows),
        "Week": [str(r["week"]) for r in sumup_rows],
        "QW": [str(r.get("quadweek", "N/A")) for r in sumup_rows],
        "W. Price": [r["weighted_price"] for r in sumup_rows],
        "Total Stock": [r["total_stock"] for r in sumup_rows],
        "Total Sold": [r["total_sold"] for r in sumup_rows],
    })
    edited = st.data_editor(
        table,
        hide_index=True,
        use_container_width=True,
        height=360,
        key=key,
        disabled=["Week", "QW", "W. Price", "Total Stock", "Total Sold"],
        column_config={
            "Select": st.column_config.CheckboxColumn("Select", default=True),
            "W. Price": st.column_config.NumberColumn("W. Price", format="%.2f"),
            "Total Stock": st.column_config.NumberColumn("Total Stock", format="%.2f"),
            "Total Sold": st.column_config.NumberColumn("Total Sold", format="%.2f"),
        },
    )
    return [i for i, selected in enumerate(edited["Select"].tolist()) if selected]


def _manual_sumup_cost_fit_indices(
    sumup_rows: list[dict],
    key: str,
) -> list[int]:
    select_all = st.toggle("Select All", value=True, key=f"{key}_select_all")
    table = pd.DataFrame({
        "Select": [select_all] * len(sumup_rows),
        "Week": [str(r["week"]) for r in sumup_rows],
        "QW": [str(r.get("quadweek", "N/A")) for r in sumup_rows],
        "W. Price": [r["weighted_price"] for r in sumup_rows],
        "Total Cost": [r["total_cost"] for r in sumup_rows],
    })
    edited = st.data_editor(
        table,
        hide_index=True,
        use_container_width=True,
        height=360,
        key=key,
        disabled=["Week", "QW", "W. Price", "Total Cost"],
        column_config={
            "Select": st.column_config.CheckboxColumn("Select", default=True),
            "W. Price": st.column_config.NumberColumn("W. Price", format="%.2f"),
            "Total Cost": st.column_config.NumberColumn("Total Cost", format="%.2f"),
        },
    )
    return [i for i, selected in enumerate(edited["Select"].tolist()) if selected]


def _resolve_sumup_fit_indices(
    sumup_rows: list[dict],
    fit_scope: str,
    manual_indices: list[int] | None = None,
) -> list[int]:
    if fit_scope == "All Quadweeks":
        return list(range(len(sumup_rows)))

    if fit_scope == "Manual Selection":
        return manual_indices or []

    selected_qw = fit_scope.replace("Quadweek: ", "", 1)
    return [
        i for i, row in enumerate(sumup_rows)
        if str(row.get("quadweek", "N/A")) == selected_qw
    ]


def _build_tb_raw_selected_weeks(
    basket_data: dict[str, BasketTimeSeries],
    selected_weeks: list[str],
) -> pd.DataFrame:
    """Build TB Raw export for selected weeks, latest selected week first."""
    export_weeks = list(reversed(selected_weeks))
    rows: list[dict] = []

    for basket_name, ts in basket_data.items():
        week_index = {str(week): idx for idx, week in enumerate(ts.weeks)}
        row: dict[str, object] = {"basket": basket_name}

        for metric_name, values in (
            ("Stock", ts.stock),
            ("Sold", ts.sold),
            ("Margin", ts.m),
            ("AvgSalePrice", ts.price),
        ):
            for week in export_weeks:
                idx = week_index.get(str(week))
                row[f"{metric_name}[{week}]"] = values[idx] if idx is not None else float("nan")

        rows.append(row)

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Page config & session-state bootstrap
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Correlation & Group Analysis",
    page_icon="📊",
    layout="wide",
)
apply_page_theme()


def _init_state() -> None:
    defaults: dict = {
        "log_messages": ["Ready."],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()
ss = st.session_state
apply_pending_project_restore()

with st.sidebar:
    render_sidebar_project_panel()

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────

st.title("📊 Correlation & Group Analysis")
st.caption(
    "Upload datasets to calculate correlations between Sold, Avg Price, and Margin. "
    "Baskets are clustered into groups. **Click any table row to drill into weekly data.**"
)
st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# ① File uploads
# ─────────────────────────────────────────────────────────────────────────────

st.subheader("① Input Data")
INPUT_MODE_OPTIONS = [
    TRACKING_REPORT_MODE,
    PRODUCT_BS_ON_DATE_MODE,
    PRODUCT_BS_MONTHLY_AV_MODE,
]
input_mode = st.radio(
    "Input format",
    INPUT_MODE_OPTIONS,
    index=INPUT_MODE_OPTIONS.index(PRODUCT_BS_ON_DATE_MODE),
    horizontal=False,
    key="input_mode",
)

file_tracking = None
file_discount_hist = None
if input_mode == TRACKING_REPORT_MODE:
    file_tracking = st.file_uploader(
        "📄 TrackingBaskets_v2 report",
        type="csv",
        key="fu_tracking_report",
        help="Single report with quadweek, year_week, basket, StockQty_W, SoldQty, Margin, and AvgSalePrice columns.",
    )
else:
    file_tracking = st.file_uploader(
        "📄 TrackingBaskets_v2 - product_BS report",
        type="csv",
        key="fu_tracking_product_bs_report",
        help="Single report with product BS category rows. On-date mode uses suffix metric columns; monthly-av mode uses row-level SoldQty and Revenue.",
    )

discount_hist_help = (
    "Optional weekly discount and promotion by basket. "
    "Upload one combined CSV and/or multiple per-category CSVs — they are "
    "aggregated by basket-week before Build. "
    + (
        "Uses aggregate columns: discount, prom with stock (no In/Out split)."
        if input_mode == TRACKING_REPORT_MODE
        else "Columns depend on Product BS category (or all categories if combined)."
    )
)
file_discount_hist = st.file_uploader(
    "📄 Discount history (discount + prom)",
    type="csv",
    key="fu_discount_hist",
    accept_multiple_files=True,
    help=discount_hist_help,
)

# ─────────────────────────────────────────────────────────────────────────────
# ② Preprocessing Filters & Settings
# ─────────────────────────────────────────────────────────────────────────────

st.subheader("② Preprocessing Filters & Settings")
st.caption("Exclude weekly data points outside these ranges. Leave blank for no limit.")

f1, f2, f3, f4, f5 = st.columns(5)

with f1:
    st.markdown("**Sold Quantity Range**")
    #sc1, sc2 = st.columns(2)
    # min_sold_raw  = sc1.text_input("Min", value="",                  key="fi_min_sold",  placeholder="Min")
    # max_sold_raw  = sc2.text_input("Max", value="",                  key="fi_max_sold",  placeholder="Max")
    min_sold_raw  = st.text_input(label="Min", label_visibility="collapsed", value="",                  key="fi_min_sold",  placeholder="Min")
    max_sold_raw  = st.text_input(label="Max", label_visibility="collapsed", value="",                  key="fi_max_sold",  placeholder="Max")

with f2:
    st.markdown("**Avg Sale Price Range**")
    # pc1, pc2 = st.columns(2)
    # min_price_raw = pc1.text_input("Min", value=str(DEFAULT_MIN_PRICE), key="fi_min_price", placeholder="Min")
    # max_price_raw = pc2.text_input("Max", value="",                  key="fi_max_price", placeholder="Max")
    min_price_raw = st.text_input(label="Min", label_visibility="collapsed", value=str(DEFAULT_MIN_PRICE), key="fi_min_price", placeholder="Min")
    max_price_raw = st.text_input(label="Max", label_visibility="collapsed", value="",                  key="fi_max_price", placeholder="Max")

with f3:
    st.markdown("**Margin (M) Range**")
    # mc1, mc2 = st.columns(2)
    # min_m_raw     = mc1.text_input("Min", value="",                  key="fi_min_m",     placeholder="Min")
    # max_m_raw     = mc2.text_input("Max", value="",                  key="fi_max_m",     placeholder="Max")
    min_m_raw     = st.text_input(label="Min", label_visibility="collapsed", value="",                  key="fi_min_m",     placeholder="Min")
    max_m_raw     = st.text_input(label="Max", label_visibility="collapsed", value="",                  key="fi_max_m",     placeholder="Max")

with f4:
    st.markdown("**Week (YYYY-WW) Range**")
    # wc1, wc2 = st.columns(2)
    # min_week      = wc1.text_input("Min", value="",                  key="fi_min_week",  placeholder="Min")
    # max_week      = wc2.text_input("Max", value="",                  key="fi_max_week",  placeholder="Max")
    min_week      = st.text_input(label="Min", label_visibility="collapsed", value="",                  key="fi_min_week",  placeholder="Min")
    max_week      = st.text_input(label="Max", label_visibility="collapsed", value="",                  key="fi_max_week",  placeholder="Max")

with f5:
    st.markdown("**:blue[Number of Clusters (K)]**")
    num_clusters  = st.number_input(
        "K", min_value=1, max_value=KMEANS_MAX_K, value=KMEANS_DEFAULT_K,
        label_visibility="collapsed", key="fi_k",
    )

product_bs_category = "Aggregated"
if input_mode in PRODUCT_BS_INPUT_MODES:
    st.markdown("**Product BS Category**")
    product_bs_category = st.selectbox(
        "Product BS Category",
        PRODUCT_BS_CATEGORY_OPTIONS,
        index=0,
        label_visibility="collapsed",
        key="fi_product_bs_category",
    )


pbs_scope_key = product_bs_scope_key(input_mode, product_bs_category)
pbs_scope = get_product_bs_scope(ss, pbs_scope_key)


# ─────────────────────────────────────────────────────────────────────────────
# Action Buttons
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
btn1, btn2, btn3, _ = st.columns([1, 1, 1, 3])

build_clicked   = btn1.button("🔨 Build Project",  type="primary",  use_container_width=True)
kmeans_clicked  = btn2.button("🔵 K-Means",        disabled=(pbs_scope["analysis"] is None), use_container_width=True)
octants_clicked = btn3.button("🟣 Octants",        disabled=(pbs_scope["analysis"] is None), use_container_width=True)

if pbs_scope["build_message"]:
    st.success(pbs_scope["build_message"])
    pbs_scope["build_message"] = None

# ─────────────────────────────────────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────────────────────────────────────

if build_clicked:
    if input_mode in {TRACKING_REPORT_MODE, *PRODUCT_BS_INPUT_MODES} and file_tracking is None:
        warning = f"Please upload a {input_mode} before building."
        _set_log([f"Input format: {input_mode}", f"Warning: {warning}"])
        st.error(warning)
    else:
        with st.spinner("Parsing and computing correlations…"):
            try:
                log_lines = [f"Input format: {input_mode}"]
                if input_mode == TRACKING_REPORT_MODE:
                    df_report = pd.read_csv(io.BytesIO(file_tracking.read()))
                    log_lines.append(f"TrackingBaskets rows uploaded: {len(df_report)}")
                    analysis = run_tracking_report_analysis(
                        df_report,
                        min_sold  = _parse_float(min_sold_raw,  -math.inf),
                        max_sold  = _parse_float(max_sold_raw,   math.inf),
                        min_price = _parse_float(min_price_raw, DEFAULT_MIN_PRICE),
                        max_price = _parse_float(max_price_raw,  math.inf),
                        min_m     = _parse_float(min_m_raw,     -math.inf),
                        max_m     = _parse_float(max_m_raw,      math.inf),
                        min_week  = min_week.strip() or None,
                        max_week  = max_week.strip() or None,
                    )
                    pbs_scope["discount_hist_df"] = _apply_optional_discount_hist(
                        analysis.basket_data,
                        file_discount_hist,
                        AGGREGATED_DISCOUNT_HIST_CATEGORY,
                        log_lines,
                    )
                else:
                    df_report = pd.read_csv(io.BytesIO(file_tracking.read()))
                    log_lines.append(f"TrackingBaskets product_BS rows uploaded: {len(df_report)}")
                    log_lines.append(f"Product BS category: {product_bs_category}")
                    log_lines.append(
                        "product_BS metric basis: "
                        + ("monthly average" if input_mode == PRODUCT_BS_MONTHLY_AV_MODE else "on date of sale")
                    )
                    analysis, parser_warnings = run_tracking_product_bs_report_analysis(
                        df_report,
                        product_bs_category=product_bs_category,
                        use_monthly_average_metrics=input_mode == PRODUCT_BS_MONTHLY_AV_MODE,
                        min_sold  = _parse_float(min_sold_raw,  -math.inf),
                        max_sold  = _parse_float(max_sold_raw,   math.inf),
                        min_price = _parse_float(min_price_raw, DEFAULT_MIN_PRICE),
                        max_price = _parse_float(max_price_raw,  math.inf),
                        min_m     = _parse_float(min_m_raw,     -math.inf),
                        max_m     = _parse_float(max_m_raw,      math.inf),
                        min_week  = min_week.strip() or None,
                        max_week  = max_week.strip() or None,
                    )
                    log_lines.extend(parser_warnings)
                    pbs_scope["discount_hist_df"] = _apply_optional_discount_hist(
                        analysis.basket_data,
                        file_discount_hist,
                        product_bs_category,
                        log_lines,
                    )
                pbs_scope["analysis"] = analysis
                clear_product_bs_scope_derived(pbs_scope)
                log_lines.extend(_analysis_log_lines(analysis))
                _set_log(log_lines)
                pbs_scope["build_message"] = (
                    f"✅ Built — **{analysis.basket_count}** baskets · "
                    f"**{analysis.week_count}** weeks."
                )
                st.rerun()
            except Exception as exc:
                error = f"Error: {exc}"
                _set_log([f"Input format: {input_mode}", error])
                st.error(error)

# ─────────────────────────────────────────────────────────────────────────────
# Clustering
# ─────────────────────────────────────────────────────────────────────────────

if kmeans_clicked and pbs_scope["analysis"] is not None:
    with st.spinner("Running K-Means…"):
        pbs_scope["analysis"] = apply_kmeans(pbs_scope["analysis"], k=int(num_clusters))
    _append_log(f"K-Means complete: {int(num_clusters)} groups assigned.")
    st.success(f"K-Means complete — {int(num_clusters)} groups assigned.")

if octants_clicked and pbs_scope["analysis"] is not None:
    with st.spinner("Assigning octants…"):
        pbs_scope["analysis"] = apply_octants(pbs_scope["analysis"])
    _append_log("Octants complete: groups assigned.")
    st.success("Octant assignment complete.")

with st.sidebar:
    st.subheader("Log")
    st.text("\n".join(ss.log_messages))

# ─────────────────────────────────────────────────────────────────────────────
# Guard — nothing below runs until analysis exists
# ─────────────────────────────────────────────────────────────────────────────

if pbs_scope["analysis"] is None:
    st.stop()

scope = pbs_scope
result: AnalysisResult = scope["analysis"]

def sk(widget_key: str) -> str:
    return scoped_widget_key(pbs_scope_key, widget_key)


# ─────────────────────────────────────────────────────────────────────────────
# ③ General settings
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
st.subheader("③ General settings")

with st.expander("Cost Correction", expanded=True):
    fit_cp_col, _, _, _ = st.columns([1, 1, 1, 3])
    with fit_cp_col:
        skip_last_points = int(
            st.number_input(
                "Skip last points",
                min_value=0,
                value=4,
                step=1,
                key=sk("bulk_fit_cost_skip_last"),
                help=(
                    "Exclude this many last weeks from Cost vs Price fitting. "
                    "Same idea as unchecking the latest points in the Cost vs Price expander."
                ),
            )
        )
        skip_zero_price = st.checkbox(
            "Skip 0",
            value=True,
            key=sk("bulk_fit_cost_skip_zero"),
            help="Exclude weeks where Price = 0 from Cost vs Price fitting.",
        )
        cost_correction_mode = st.selectbox(
            "Cost correction",
            list(COST_CORRECTION_MODES),
            index=COST_CORRECTION_MODES.index(COST_CORRECTION_FROM_LAST_POINT),
            key=sk("bulk_fit_cost_correction_mode"),
            help=(
                "From regression: Cost Corrected = z0 + a·Price. "
                "From the last point: keep slope a and re-anchor the intercept "
                "on the last week used in the fit."
            ),
        )
        a_min_raw = st.text_input(
            "a_min",
            value="0",
            key=sk("bulk_fit_cost_a_min"),
            help="Do not correct this basket if fitted slope a is below a_min. Default 0.",
        )
        a_max_raw = st.text_input(
            "a_max",
            value="",
            key=sk("bulk_fit_cost_a_max"),
            help="Do not correct this basket if fitted slope a is above a_max. Empty = no max.",
        )
        correct_margin = st.toggle(
            "Correct Margin",
            value=True,
            key=sk("bulk_fit_cost_correct_margin"),
            help=(
                "When on, Fit Cost x Price is calculated automatically and "
                "Sum-Up / Basket Detail use Margin Corrected."
            ),
        )
    cost_a_min = _parse_float(str(a_min_raw), 0.0)
    cost_a_max = _parse_optional_float(str(a_max_raw))

if correct_margin:
    scope["bulk_fit_cost_price"] = fit_bulk_cost_price(
        result.basket_data,
        skip_last_points,
        bool(skip_zero_price),
    )

basket_corrections = compute_corrections_for_baskets(
    result.basket_data,
    scope.get("bulk_fit_cost_price") or {},
    skip_last_points,
    bool(skip_zero_price),
    str(cost_correction_mode),
    cost_a_min,
    cost_a_max,
)
scope["basket_margin_hybrid"] = hybrid_margin_map(
    result.basket_data,
    basket_corrections,
)

# ─────────────────────────────────────────────────────────────────────────────
# ④ Cluster Overview
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
st.subheader("④ Correlation Clusters")

chart_col, insight_col = st.columns([3, 2])

with chart_col:
    fig2d = build_2d_cluster_scatter(
        result.basket_results,
        k=result.cluster_k,
        labels=result.cluster_labels,
    )
    st.plotly_chart(fig2d, use_container_width=True, key=sk("chart_2d"))

with insight_col:
    with st.expander("**Group Insights**", expanded=False):
        #st.markdown("**Group Insights**")
        summaries = result.get_cluster_summary()
        if not summaries:
            st.info("No clusters yet. Run **K-Means** or **Octants** to see group insights.")
        else:
            for s in summaries:
                if s.get("count", 0) == 0:
                    continue
                label = s.get("label") or result.get_cluster_label(s["group"])
                with st.container(border=True):
                    st.markdown(f"**{label}** — {s['count']} baskets")
                    c1, c2 = st.columns(2)
                    c1.metric("Sold",    _fmt(s.get("total_sold")))
                    c2.metric("Margin",       _fmt(s.get("total_m")))
                    c1.metric("Price", _fmt(s.get("weighted_price")))
                    c2.markdown(
                        f"Avg Corr SP / MP / MS:  "
                        f"`{_fmt(s.get('avg_corr_SP'))}` / "
                        f"`{_fmt(s.get('avg_corr_MP'))}` / "
                        f"`{_fmt(s.get('avg_corr_MS'))}`"
                    )

with st.expander("🔵 3D Correlation Space", expanded=False):
    fig3d_cl = build_3d_cluster_scatter(
        result.basket_results,
        k=result.cluster_k,
        labels=result.cluster_labels,
    )
    st.plotly_chart(fig3d_cl, use_container_width=True, key=sk("chart_3d_cluster"))

# ─────────────────────────────────────────────────────────────────────────────
# ⑤ Basket Table
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
st.subheader("⑤ Detailed Basket Breakdown")

price_sold_fits = scope.get("bulk_fit_price_sold") or {}
price_stock_sold_fits = scope.get("bulk_fit_price_stock_sold") or {}
cost_price_fits = scope.get("bulk_fit_cost_price") or {}
show_price_sold_fit = bool(price_sold_fits)
show_price_stock_sold_fit = bool(price_stock_sold_fits)
show_cost_price_fit = bool(cost_price_fits)

basket_rows = []
group_color_map = {"—": 0}
for b in result.basket_results:
    group_label = result.get_cluster_label(b.group) if b.group > 0 else "—"
    group_color_map[group_label] = b.group
    row = {
        "Basket":      b.basket,
        "Group":       group_label,
        "W. Price":    round(b.weighted_price, 2),
        "Total Sold":  round(b.total_sold, 2),
        "Total Margin":     round(b.total_m, 2),
        "Avg Stock":   round(b.average_stock, 2),
        "Avg CountProduct": round(b.average_count_product, 2),
        "Total Purchase": round(b.total_purchase, 2),
        "Sold/Purchase": round(b.total_sold / b.total_purchase, 4) if b.total_purchase > 0 else float("nan"),
        "Corr(S/P)":   b.corr_SP,
        "Corr(M/P)":   b.corr_MP,
        "Corr(M/S)":   b.corr_MS,
        "dStock/w":    b.av_dstock_w_qw,
        "dStock_b":    b.av_dstock_b_qw,
    }
    if show_price_sold_fit:
        price_sold_fit = price_sold_fits.get(b.basket)
        row["Sold~Price z0"] = price_sold_fit.z0 if price_sold_fit else float("nan")
        row["Sold~Price a"] = price_sold_fit.a if price_sold_fit else float("nan")
        row["Sold~Price R2"] = price_sold_fit.r2 if price_sold_fit else float("nan")
    if show_price_stock_sold_fit:
        price_stock_sold_fit = price_stock_sold_fits.get(b.basket)
        row["Sold~Price+Stock z0"] = (
            price_stock_sold_fit.z0 if price_stock_sold_fit else float("nan")
        )
        row["Sold~Price+Stock a"] = (
            price_stock_sold_fit.a if price_stock_sold_fit else float("nan")
        )
        row["Sold~Price+Stock b"] = (
            price_stock_sold_fit.b if price_stock_sold_fit else float("nan")
        )
        row["Sold~Price+Stock Adj R2"] = (
            price_stock_sold_fit.adj_r2 if price_stock_sold_fit else float("nan")
        )
    if show_cost_price_fit:
        cost_price_fit = cost_price_fits.get(b.basket)
        row["Cost~Price z0"] = cost_price_fit.z0 if cost_price_fit else float("nan")
        row["Cost~Price a"] = cost_price_fit.a if cost_price_fit else float("nan")
        row["Cost~Price Pl"] = cost_price_fit.pl if cost_price_fit else float("nan")
        row["Cost~Price R2"] = cost_price_fit.r2 if cost_price_fit else float("nan")
        row["Cost~Price RMSE"] = cost_price_fit.rmse if cost_price_fit else float("nan")
    basket_rows.append(row)

df_table = pd.DataFrame(basket_rows)

fit_ps_col, fit_pss_col, fit_cp_col, exp_col, _ = st.columns([1, 1, 1, 1, 2])
if fit_ps_col.button("Fit Price x Sold", use_container_width=True):
    fitted: dict[str, Linefit] = {}
    for basket_name, ts in result.basket_data.items():
        lf = fit_line(ts.price, ts.sold)
        if lf is not None:
            fitted[basket_name] = lf
    scope["bulk_fit_price_sold"] = fitted
    st.rerun()

if fit_pss_col.button("Fit Price x Stock x Sold", use_container_width=True):
    fitted_planes: dict[str, Planefit] = {}
    for basket_name, ts in result.basket_data.items():
        pf = fit_plane(ts.price, ts.stock, ts.sold, method="mlr")
        if pf is not None:
            fitted_planes[basket_name] = pf
    scope["bulk_fit_price_stock_sold"] = fitted_planes
    st.rerun()

if fit_cp_col.button("Fit Cost x Price", use_container_width=True):
    scope["bulk_fit_cost_price"] = fit_bulk_cost_price(
        result.basket_data,
        skip_last_points,
        bool(skip_zero_price),
    )
    st.rerun()

csv_bytes  = df_table.to_csv(index=False).encode()
exp_col.download_button(
    "⬇ Export CSV", data=csv_bytes,
    file_name="pcba_results.csv", mime="text/csv",
)



# 1. Define the coloring rule
def color_pos_neg(val):
    if pd.isna(val): 
        return ''
    elif val > 0:
        return 'color: #2ecc71; font-weight: bold;' # Soft green
    elif val < 0:
        return 'color: #e74c3c; font-weight: bold;' # Soft red
    return ''

# Style Group cells with the same palette used by the 2D/3D cluster plots.
def color_group(val):
    group = group_color_map.get(val, 0)
    if group <= 0:
        return ''

    color = CLUSTER_COLORS[(group - 1) % len(CLUSTER_COLORS)]
    border = CLUSTER_BORDER_COLORS[(group - 1) % len(CLUSTER_BORDER_COLORS)]
    return (
        f'background-color: {color}; '
        'color: #111827; '
        'font-weight: 700; '
        f'border-left: 4px solid {border};'
    )

# 2. Specify which columns to apply this color rule to
target_columns = ["Corr(S/P)", "Corr(M/P)", "Corr(M/S)", "dStock/w", "dStock_b"]
fit_columns: list[str] = []
if show_price_sold_fit:
    fit_columns.extend(["Sold~Price z0", "Sold~Price a", "Sold~Price R2"])
if show_price_stock_sold_fit:
    fit_columns.extend([
        "Sold~Price+Stock z0",
        "Sold~Price+Stock a",
        "Sold~Price+Stock b",
        "Sold~Price+Stock Adj R2",
    ])
if show_cost_price_fit:
    fit_columns.extend([
        "Cost~Price z0",
        "Cost~Price a",
        "Cost~Price Pl",
        "Cost~Price R2",
        "Cost~Price RMSE",
    ])

basket_table_column_config = {
    "Basket": st.column_config.TextColumn(
        "Basket",
        help="Basket identifier from the uploaded dataset.",
    ),
    "Group": st.column_config.TextColumn(
        "Group",
        help="Cluster or octant group assigned to the basket. A dash means no group is assigned.",
    ),
    "W. Price": st.column_config.NumberColumn(
        "W. Price",
        help="Weighted average selling price across valid weeks for this basket.",
        format="%.2f",
    ),
    "Total Sold": st.column_config.NumberColumn(
        "Total Sold",
        help="Total sold quantity across all valid weeks for this basket.",
        format="%.2f",
    ),
    "Total Margin": st.column_config.NumberColumn(
        "Total Margin",
        help="Total margin across all valid weeks for this basket.",
        format="%.2f",
    ),
    "Avg Stock": st.column_config.NumberColumn(
        "Avg Stock",
        help="Average stock level across all valid weeks for this basket.",
        format="%.2f",
    ),
    "Avg CountProduct": st.column_config.NumberColumn(
        "Avg CountProduct",
        help="Average CountProduct_W across all valid weeks for this basket.",
        format="%.2f",
    ),
    "Total Purchase": st.column_config.NumberColumn(
        "Total Purchase",
        help="Total PurchaseQty across all valid weeks for this basket.",
        format="%.2f",
    ),
    "Sold/Purchase": st.column_config.NumberColumn(
        "Sold/Purchase",
        help="Ratio of Total Sold to Total Purchase for this basket.",
        format="%.4f",
    ),
    "Corr(S/P)": st.column_config.NumberColumn(
        "Corr(S/P)",
        help="Pearson correlation between Sold quantity and Avg Price for this basket.",
        format="%.3f",
    ),
    "Corr(M/P)": st.column_config.NumberColumn(
        "Corr(M/P)",
        help="Pearson correlation between Margin and Avg Price for this basket.",
        format="%.3f",
    ),
    "Corr(M/S)": st.column_config.NumberColumn(
        "Corr(M/S)",
        help="Pearson correlation between Margin and Sold quantity for this basket.",
        format="%.3f",
    ),
    "dStock/w": st.column_config.NumberColumn(
        "dStock/w",
        help="Average week-to-week stock change within quadweeks.",
        format="%.2f",
    ),
    "dStock_b": st.column_config.NumberColumn(
        "dStock_b",
        help="Average stock change at quadweek boundaries.",
        format="%.2f",
    ),
    "Sold~Price z0": st.column_config.NumberColumn(
        "Sold~Price z0",
        help="Intercept of the bulk line fit: Sold = z0 + a * Price.",
        format="%.4f",
    ),
    "Sold~Price a": st.column_config.NumberColumn(
        "Sold~Price a",
        help="Price coefficient of the bulk line fit: Sold = z0 + a * Price.",
        format="%.4f",
    ),
    "Sold~Price R2": st.column_config.NumberColumn(
        "Sold~Price R2",
        help="R2 goodness-of-fit for the bulk Sold vs Price line model.",
        format="%.4f",
    ),
    "Sold~Price+Stock z0": st.column_config.NumberColumn(
        "Sold~Price+Stock z0",
        help="Intercept of the bulk plane fit: Sold = z0 + a * Price + b * Stock.",
        format="%.4f",
    ),
    "Sold~Price+Stock a": st.column_config.NumberColumn(
        "Sold~Price+Stock a",
        help="Price coefficient of the bulk plane fit: Sold = z0 + a * Price + b * Stock.",
        format="%.4f",
    ),
    "Sold~Price+Stock b": st.column_config.NumberColumn(
        "Sold~Price+Stock b",
        help="Stock coefficient of the bulk plane fit: Sold = z0 + a * Price + b * Stock.",
        format="%.4f",
    ),
    "Sold~Price+Stock Adj R2": st.column_config.NumberColumn(
        "Sold~Price+Stock Adj R2",
        help="Adjusted R2 goodness-of-fit for the bulk Price and Stock plane model.",
        format="%.4f",
    ),
    "Cost~Price z0": st.column_config.NumberColumn(
        "Cost~Price z0",
        help="Intercept of the bulk line fit: Cost = z0 + a * Price.",
        format="%.4f",
    ),
    "Cost~Price a": st.column_config.NumberColumn(
        "Cost~Price a",
        help="Price coefficient of the bulk line fit: Cost = z0 + a * Price.",
        format="%.4f",
    ),
    "Cost~Price Pl": st.column_config.NumberColumn(
        "Cost~Price Pl",
        help="Leverage price Pl = z0 / (1 - a) from the bulk Cost vs Price fit.",
        format="%.4f",
    ),
    "Cost~Price R2": st.column_config.NumberColumn(
        "Cost~Price R2",
        help="R2 goodness-of-fit for the bulk Cost vs Price line model.",
        format="%.4f",
    ),
    "Cost~Price RMSE": st.column_config.NumberColumn(
        "Cost~Price RMSE",
        help="RMSE of the bulk Cost vs Price line model.",
        format="%.4f",
    ),
}

# 3. Chain the styling and string formatting together
styled_df = (
    df_table.style
    .map(color_group, subset=["Group"])
    .map(color_pos_neg, subset=target_columns)
    # This handles your _fmt2 and _fmt3 formatting requirements cleanly:
    .format({
        "Corr(S/P)": "{:.3f}", # Equivalent to your _fmt3 3-decimal formatting
        "Corr(M/P)": "{:.3f}",
        "Corr(M/S)": "{:.3f}",
        "dStock/w":  "{:.2f}", # Equivalent to your _fmt2 2-decimal formatting
        "dStock_b":  "{:.2f}",
        **{col: "{:.4f}" for col in fit_columns},
    })
)




tbl_event = st.dataframe(
    styled_df,  # <--- Pass the styled dataframe here!
    # df_table,
    use_container_width=True,
    height=420,
    on_select="rerun",
    selection_mode="single-row",
    key=sk(
        f"basket_table_{int(show_price_sold_fit)}_"
        f"{int(show_price_stock_sold_fit)}_{int(show_cost_price_fit)}"
    ),
    column_config=basket_table_column_config,
)

sel_rows = tbl_event.selection.rows if tbl_event and tbl_event.selection else []
if sel_rows:
    chosen_basket = df_table.iloc[sel_rows[0]]["Basket"]
    if chosen_basket != scope["selected_basket"]:
        scope["selected_basket"] = chosen_basket

# ─────────────────────────────────────────────────────────────────────────────
# ⑥ Basket Drill-Down
# ─────────────────────────────────────────────────────────────────────────────

if scope["selected_basket"] and scope["selected_basket"] in result.basket_data:
    ts          = result.basket_data[scope["selected_basket"]]
    basket_name = scope["selected_basket"]

    st.divider()
    st.subheader(f"⑥ Basket Detail: **{basket_name}**")

    ctrl1, ctrl2, ctrl3, _ = st.columns([1, 1, 1, 3])
    show_line = ctrl1.toggle(
        "Line + Symbol",
        value=scope["show_line"],
        key=sk(f"tog_line_{basket_name}"),
    )
    show_qw = ctrl2.toggle(
        "Colour by Quadweek",
        value=scope["show_qw_colors"],
        key=sk(f"tog_qw_{basket_name}"),
    )
    show_qw_avg = ctrl3.toggle(
        "QW Average",
        value=scope["show_qw_average"],
        key=sk(f"tog_qw_avg_{basket_name}"),
    )
    scope["show_line"]       = show_line
    scope["show_qw_colors"]  = show_qw
    scope["show_qw_average"] = show_qw_avg

    bulk_cost_fit = (scope.get("bulk_fit_cost_price") or {}).get(basket_name)
    cost_correction = basket_corrections.get(basket_name) or compute_cost_margin_correction(
        ts.price,
        ts.cost,
        ts.sold,
        ts.m,
        bulk_cost_fit,
        skip_last_points,
        bool(skip_zero_price),
        str(cost_correction_mode),
        cost_a_min,
        cost_a_max,
    )
    use_margin_corrected = bool(correct_margin) and cost_correction.applied
    plot_margin = (
        cost_correction.margin_hybrid if use_margin_corrected else None
    )
    skipped_note = ""
    if use_margin_corrected:
        skipped_note = (
            "Note: skipped Cost vs Price weeks use Margin Corrected "
            "(original margin on kept weeks)."
        )

    chart_state_key = (
        f"{show_qw}_{show_line}_{show_qw_avg}_"
        f"{int(cost_correction.applied)}_{int(use_margin_corrected)}_"
        f"{cost_correction_mode}_{int(skip_last_points)}"
    )

    week_labels = [str(week) for week in ts.weeks]
    progress_specs = _basket_week_progress_specs(ts)
    stock_values = _basket_series_values(ts, ts.stock)

    with st.expander("📈 Week Progress", expanded=True):
        enabled_progress = _render_progress_toggles(
            progress_specs,
            lambda key: sk(f"wp_{key}_{basket_name}"),
        )

        if enabled_progress:
            prog_cols = st.columns(2)
            for idx, spec in enumerate(enabled_progress):
                overlay_values = None
                overlay_name = ""
                if cost_correction.applied and spec["key"] == "cost_per_sold":
                    overlay_values = cost_correction.cost_corrected
                    overlay_name = "Cost Corrected"
                elif use_margin_corrected and spec["key"] == "margin":
                    overlay_values = cost_correction.margin_corrected
                    overlay_name = "Margin Corrected"
                elif use_margin_corrected and spec["key"] == "mtost":
                    overlay_values = ratio_series(
                        cost_correction.margin_hybrid,
                        stock_values,
                    )
                    overlay_name = "MtoSt Corrected"
                elif use_margin_corrected and spec["key"] == "mtosold":
                    overlay_values = ratio_series(
                        cost_correction.margin_hybrid,
                        ts.sold,
                    )
                    overlay_name = "MtoSold Corrected"
                with prog_cols[idx % 2]:
                    st.plotly_chart(
                        build_metric_progress(
                            week_labels,
                            spec["values"],
                            title=spec["title"],
                            y_title=spec["y_title"],
                            marker_color=spec["marker_color"],
                            line_color=spec["line_color"],
                            show_line=show_line,
                            quadweeks=ts.quadweeks,
                            use_qw_colors=show_qw,
                            show_qw_average=show_qw_avg,
                            overlay_values=overlay_values,
                            overlay_name=overlay_name,
                        ),
                        use_container_width=True,
                        key=sk(f"wp_chart_{spec['key']}_{basket_name}_{chart_state_key}"),
                    )
        else:
            st.caption("Enable at least one metric above to show week progress charts.")

    with st.expander("📊 Sold vs Price · Margin vs Price · Margin vs Sold"):
        if skipped_note:
            st.caption(skipped_note)
        st.plotly_chart(
            build_basket_scatter_3panel(
                ts,
                use_qw_colors=show_qw,
                show_line=show_line,
                show_qw_average=show_qw_avg,
                margin_values=plot_margin,
            ),
            use_container_width=True,
            key=sk(f"scatter_3panel_{basket_name}_{chart_state_key}"),
        )

    # ── Cost vs Price ──────────────────────────────────────────────────────

    with st.expander("📉 Cost vs Price (Basket Detail)"):
        fit_cost_res = scope["fit_cost"].get(basket_name)
        scope_col, button_fit_cost_col, _ = st.columns([1, 1, 4])
        fit_scope_cost = scope_col.selectbox(
            "Points to fit",
            _quadweek_fit_options(ts),
            key=sk(f"scope_cost_{basket_name}"),
            label_visibility="collapsed",
        )
        fit_cost_line_clicked = button_fit_cost_col.button("Fit Line", key=sk(f"btn_cost_{basket_name}"))

        plot_clmn, selection_clmn = st.columns([3, 1])

        manual_indices_cost: list[int] | None = None
        #if fit_scope_cost == "Manual Selection":
        with selection_clmn:
            st.markdown("**Data Points**")
            manual_indices_cost = _manual_fit_indices(
                ts,
                key=sk(f"manual_cost_{basket_name}"),
                value_label="Cost",
                values=ts.cost,
            )

        fit_indices_cost = _resolve_fit_indices(ts, fit_scope_cost, manual_indices_cost)
        highlight_cost = (
            fit_indices_cost if fit_scope_cost == "Manual Selection" else None
        )
        plot_clmn.plotly_chart(
                                build_cost_vs_price(
                                    ts,
                                    use_qw_colors=show_qw,
                                    show_line=show_line,
                                    linefit=fit_cost_res,
                                    fitted_indices=highlight_cost,
                                    show_qw_average=show_qw_avg,
                                ),
                                use_container_width=True,
                                key=sk(f"cost_{basket_name}_{chart_state_key}"),
        )

        if fit_cost_line_clicked:
            if len(fit_indices_cost) < 2:
                st.warning("Select at least 2 data points to fit a line.")
                lf = None
            else:
                lf = fit_line(
                    [ts.price[i] for i in fit_indices_cost],
                    [ts.cost[i] for i in fit_indices_cost],
                )
            if lf is None:
                st.warning("Not enough data points to fit a line.")
            else:
                scope["fit_cost"][basket_name] = lf
                st.rerun()
        if fit_cost_res:
            cost_res_col, _ = st.columns([3,1])
            with cost_res_col.container(border=True):
                _render_linefit_stats(fit_cost_res)

    # ── 3D Price × Sold × M ───────────────────────────────────────────────

    with st.expander("🌐 3D Overview: Price × Sold × M (Basket Detail)"):
        if skipped_note:
            st.caption(skipped_note)
        st.plotly_chart(
            build_3d_price_sold_m(
                ts,
                use_qw_colors=show_qw,
                show_line=show_line,
                show_qw_average=show_qw_avg,
                m_values=plot_margin,
            ),
            use_container_width=True,
            key=sk(f"3d_psm_{basket_name}_{chart_state_key}"),
        )

    # ── 3D Price × Stock × Sold ────────────────────────────────────────────

    with st.expander("🌐 3D Overview: Price × Stock × Sold  (Basket Detail)"):
        fit_sold_res = scope["fit_sold"].get(basket_name)
        method_col, scope_col, button_fit_sold_plane_col, _ = st.columns([1, 1, 1, 3])
        method_s = method_col.selectbox(
            "Fit method",
            ["mlr", "pca"],
            format_func=str.upper,
            key=sk(f"meth_s_{basket_name}"),
            label_visibility="collapsed",
        )
        fit_scope_s = scope_col.selectbox(
            "Points to fit",
            _quadweek_fit_options(ts),
            key=sk(f"scope_s_{basket_name}"),
            label_visibility="collapsed",
        )
        fit_sold_plane_clicked = button_fit_sold_plane_col.button("Fit Plane", key=sk(f"btn_plane_sold_{basket_name}"))

        plot_clmn, selection_clmn = st.columns([3, 1])

        manual_indices_s: list[int] | None = None
        #if fit_scope_s == "Manual Selection":
        with selection_clmn:
            st.markdown("**Data Points**")
            manual_indices_s = _manual_fit_indices(
                ts,
                key=sk(f"manual_sold_{basket_name}"),
                value_label="Sold",
                values=ts.sold,
            )

        fit_indices_s = _resolve_fit_indices(ts, fit_scope_s, manual_indices_s)
        highlight_s = fit_indices_s if fit_scope_s == "Manual Selection" else None
        plot_clmn.plotly_chart(
                                    build_3d_price_stock_sold(
                                        ts,
                                        use_qw_colors=show_qw,
                                        show_line=show_line,
                                        planefit=fit_sold_res,
                                        fitted_indices=highlight_s,
                                        show_qw_average=show_qw_avg,
                                    ),
                                    use_container_width=True,
                                    key=sk(f"3d_pss_{basket_name}_{chart_state_key}"),
                                )
        if fit_sold_plane_clicked:
            if len(fit_indices_s) < 3:
                st.warning("Select at least 3 data points to fit a plane.")
                pf = None
            else:
                pf = fit_plane(
                    [ts.price[i] for i in fit_indices_s],
                    [ts.stock[i] for i in fit_indices_s],
                    [ts.sold[i] for i in fit_indices_s],
                    method=method_s,
                )
            if pf is None:
                st.warning("Not enough data points to fit a plane.")
            else:
                scope["fit_sold"][basket_name] = pf
                st.rerun()
        if fit_sold_res:
            sold_res_col, _ = st.columns([3,1])
            with sold_res_col.container(border=True):
                _render_planefit_stats(fit_sold_res, label="Sold = z₀ + a·Price + b·Stock")

    # ── 3D Price × Stock × M  +  Margin Optimisation ─────────────────────

    with st.expander("🌐 3D Overview: Price × Stock × M  +  Margin Optimisation (Basket Detail)"):
        fit_m_res = scope["fit_sold_m"].get(basket_name)
        saved_margin_model = scope["margin_model"].get(basket_name)
        margin_surface = saved_margin_model["surface"] if saved_margin_model else None
        method_col, scope_col, button_fit_sold_plane_col, _ = st.columns([1, 1, 1, 3])
        if skipped_note:
            st.caption(skipped_note)
        st.plotly_chart(
            build_3d_price_stock_m(
                ts,
                use_qw_colors=show_qw,
                show_line=show_line,
                planefit=fit_m_res,
                margin_surface=margin_surface,
                show_qw_average=show_qw_avg,
                m_values=plot_margin,
            ),
            use_container_width=True,
            key=sk(f"3d_pstm_{basket_name}_{chart_state_key}"),
        )
        # method_m = st.selectbox("Fit method", ["mlr", "pca"],
        #                          format_func=str.upper,
        #                          key=sk(f"meth_m_{basket_name}"))
        # if st.button("Fit Plane  (M = z₀ + a·Price + b·Stock)",
        #              key=sk(f"btn_fitm_{basket_name}")):
        #     pf_m = fit_plane(ts.price, ts.stock, ts.m, method=method_m)
        #     if pf_m is None:
        #         st.warning("Not enough data points to fit a plane.")
        #     else:
        #         scope["fit_sold_m"][basket_name] = pf_m
        #         st.rerun()
        # if fit_m_res:
        #     _render_planefit_stats(fit_m_res, label="M = z₀ + a·Price + b·Stock")

        #st.divider()
       # st.markdown("**📐 Analytical Margin Optimisation Model**")
        with st.expander("**📐 Analytical Margin Optimisation Model**"):
            fit_sold_ok = scope["fit_sold"].get(basket_name)
            fit_cost_ok = bulk_cost_fit or scope["fit_cost"].get(basket_name)
            if fit_sold_ok and fit_cost_ok:
                _render_margin_model(
                    basket_name,
                    ts,
                    fit_sold_ok,
                    fit_cost_ok,
                    scope,
                    sk,
                    m_values=plot_margin,
                )
            else:
                st.info(
                    "To run the model, first fit both:\n"
                    "- **Cost vs Price** (Cost = z₀ + a·Price)\n"
                    "- **Price × Stock × Sold** plane (Sold = z₀ + a·Price + b·Stock)"
                )

# ─────────────────────────────────────────────────────────────────────────────
# ⑦ Sum-Up
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
st.subheader("⑦ Sum-Up  (All Filtered Baskets)")
st.caption("Aggregated values and correlations across all valid baskets, broken down by week.")

sumup_rows = compute_sumup_series(result.weekly_totals, result.all_weeks)
sumup_rows = enrich_sumup_with_corrected_totals(
    sumup_rows,
    result.weekly_totals,
    result.basket_data,
    basket_corrections,
)
if not sumup_rows:
    st.info("No weekly data to display.")
    st.stop()

wp_arr = [r["weighted_price"] for r in sumup_rows]
ts_arr = [r["total_sold"]     for r in sumup_rows]
tm_arr = [r["total_m"]        for r in sumup_rows]
sumup_use_corrected = bool(correct_margin)
sumup_margin_key = "total_m_corrected" if sumup_use_corrected else "total_m"
sumup_margin_title = "Total M Corrected" if sumup_use_corrected else "Total M"
sumup_margin_label = "Total Margin Corrected" if sumup_use_corrected else "Total Margin"

kpi1, kpi2, kpi3 = st.columns(3)
# kpi1.container(border=True).metric("Overall Corr  Sold vs W. Price", _fmt3(compute_pearson(ts_arr, wp_arr)))
# kpi2.container(border=True).metric("Overall Corr  M vs W. Price",    _fmt3(compute_pearson(tm_arr, wp_arr)))
# kpi3.container(border=True).metric("Overall Corr  M vs Total Sold",  _fmt3(compute_pearson(tm_arr, ts_arr)))

kpi1.container(border=True).metric("Overall Corr  Sold vs W. Price", _fmt3(compute_pearson(ts_arr, wp_arr)))
kpi2.container(border=True).metric("Overall Corr  Margin vs W. Price",    _fmt3(compute_pearson(tm_arr, wp_arr)))
kpi3.container(border=True).metric("Overall Corr  Margin vs Total Sold",  _fmt3(compute_pearson(tm_arr, ts_arr)))


df_sumup = pd.DataFrame([{
    "Show":        str(r["week"]) == str(scope["selected_week"]),
    "Select":      True,
    "QW":          r.get("quadweek", "N/A"),
    "Week":        r["week"],
    "week in QW":  r.get("week_in_quad", 0) or "",
    "W. Price":    round(r["weighted_price"], 2),
    "Total Stock": round(r["total_stock"], 2),
    "Total CountProduct": round(r["total_count_product"], 2),
    "Total Purchase": round(r["total_purchase"], 2),
    "Total Sold":  round(r["total_sold"], 2),
    "Total Revenue": round(r["total_revenue"], 2),
    "Total Margin": round(r["total_m"], 2),
    "Total Margin Corrected": round(r["total_m_corrected"], 2),
    "Cost":  round(r["total_cost"], 2),
    "Cost Corrected": round(r["total_cost_corrected"], 2)
        if not math.isnan(r["total_cost_corrected"]) else float("nan"),
    "Total Monthly Reserve": round(r["total_monthly_reserve"], 2)
        if not math.isnan(r["total_monthly_reserve"]) else float("nan"),
    "Corr S/P":    _fmt3(r["corr_SP"]),
    "Corr M/P":    _fmt3(r["corr_MP"]),
    "Corr M/S":    _fmt3(r["corr_MS"]),
} for r in sumup_rows])

export_total_col, export_week_basket_col, _ = st.columns([1, 1.2, 6])
export_total_placeholder = export_total_col.empty()
tb_raw_placeholder = export_week_basket_col.empty()

select_all_col, sumup_color_col, _ = st.columns([1, 1.2, 6])


def _reset_sumup_selection_table() -> None:
    scope["sumup_select_generation"] += 1


select_all_sumup = select_all_col.toggle(
    "Select All",
    value=True,
    key=sk("tog_sumup_select_all"),
    on_change=_reset_sumup_selection_table,
)
colour_sumup_by_qw = sumup_color_col.toggle(
    "Colour by QW",
    value=False,
    key=sk("tog_sumup_qw_colors"),
)
df_sumup["Select"] = select_all_sumup

sumup_qw_values = sorted({
    str(qw)
    for qw in df_sumup["QW"].tolist()
    if str(qw) and str(qw) != "N/A"
})
sumup_qw_color_map = {
    qw: CLUSTER_COLORS[i % len(CLUSTER_COLORS)]
    for i, qw in enumerate(sumup_qw_values)
}


def _sumup_qw_row_style(row: pd.Series) -> list[str]:
    if not colour_sumup_by_qw:
        return [""] * len(row)
    color = sumup_qw_color_map.get(str(row.get("QW", "")))
    if not color:
        return [""] * len(row)
    return [
        f"background-color: {color}; color: #111827;"
        for _ in row
    ]


sumup_table_data = (
    df_sumup.style.apply(_sumup_qw_row_style, axis=1)
    if colour_sumup_by_qw
    else df_sumup
)

edited_sumup_raw = st.data_editor(
    sumup_table_data,
    use_container_width=True,
    height=300,
    key=sk(f"sumup_selection_table_{scope['sumup_select_generation']}"),
    hide_index=True,
    disabled=[
        "QW",
        "Week",
        "week in QW",
        "W. Price",
        "Total Stock",
        "Total CountProduct",
        "Total Purchase",
        "Total Sold",
        "Total Revenue",
        "Total Margin",
        "Total Margin Corrected",
        "Cost",
        "Cost Corrected",
        "Total Monthly Reserve",
        "Corr S/P",
        "Corr M/P",
        "Corr M/S",
    ],
    column_config={
        "Show": st.column_config.CheckboxColumn(
            "Show",
            help="Show this single week in the Week Detail / Week Discount / Week Visualization sections below. Only one week can be shown at a time.",
            default=False,
        ),
        "Select": st.column_config.CheckboxColumn(
            "Select",
            help="Select one or more weeks for TB Raw export and other bulk manipulations.",
            default=False,
        ),
        "QW": st.column_config.TextColumn(
            "QW",
            help="Quadweek for this Sum-Up row.",
        ),
        "Week": st.column_config.TextColumn(
            "Week",
            help="Year-week included in the Sum-Up aggregation.",
        ),
        "week in QW": st.column_config.NumberColumn(
            "week in QW",
            help="Week position inside the quadweek, from 1 to 4.",
            format="%d",
        ),
        "W. Price": st.column_config.NumberColumn(
            "W. Price",
            help="Weighted average selling price across all filtered baskets for this week.",
            format="%.2f",
        ),
        "Total Stock": st.column_config.NumberColumn(
            "Total Stock",
            help="Total StockQty_W across all filtered baskets for this week.",
            format="%.2f",
        ),
        "Total CountProduct": st.column_config.NumberColumn(
            "Total CountProduct",
            help="Total CountProduct_W across all filtered baskets for this week.",
            format="%.2f",
        ),
        "Total Purchase": st.column_config.NumberColumn(
            "Total Purchase",
            help="Total PurchaseQty across all filtered baskets for this week.",
            format="%.2f",
        ),
        "Total Sold": st.column_config.NumberColumn(
            "Total Sold",
            help="Total sold quantity across all filtered baskets for this week.",
            format="%.2f",
        ),
        "Total Revenue": st.column_config.NumberColumn(
            "Total Revenue",
            help="Total revenue across all filtered baskets for this week.",
            format="%.2f",
        ),
        "Total Margin": st.column_config.NumberColumn(
            "Total Margin",
            help="Total margin across all filtered baskets for this week.",
            format="%.2f",
        ),
        "Total Margin Corrected": st.column_config.NumberColumn(
            "Total Margin Corrected",
            help="Sum of per-basket Margin Corrected (hybrid: original on kept weeks, corrected on skipped weeks).",
            format="%.2f",
        ),
        "Cost": st.column_config.NumberColumn(
            "Cost",
            help="Estimated total cost: W. Price - Total Margin / Total Sold.",
            format="%.2f",
        ),
        "Cost Corrected": st.column_config.NumberColumn(
            "Cost Corrected",
            help="(Revenue - Total Margin Corrected) / Sold.",
            format="%.2f",
        ),
        "Total Monthly Reserve": st.column_config.NumberColumn(
            "Total Monthly Reserve",
            help="Estimated months to sell out total stock at the weekly sold rate (Stock / Sold × 7 / 30).",
            format="%.2f",
        ),
        "Corr S/P": st.column_config.TextColumn(
            "Corr S/P",
            help="Weekly Pearson correlation between basket Sold quantities and basket prices.",
        ),
        "Corr M/P": st.column_config.TextColumn(
            "Corr M/P",
            help="Weekly Pearson correlation between basket margins and basket prices.",
        ),
        "Corr M/S": st.column_config.TextColumn(
            "Corr M/S",
            help="Weekly Pearson correlation between basket margins and basket Sold quantities.",
        ),
    },
)
edited_sumup = (
    edited_sumup_raw
    if isinstance(edited_sumup_raw, pd.DataFrame)
    else edited_sumup_raw.data
)
show_sumup_weeks = [
    str(row["Week"])
    for _, row in edited_sumup.iterrows()
    if bool(row["Show"])
]
if len(show_sumup_weeks) > 1:
    previous_show_week = str(scope["selected_week"]) if scope["selected_week"] else None
    newly_checked = [week for week in show_sumup_weeks if week != previous_show_week]
    scope["selected_week"] = newly_checked[-1] if newly_checked else show_sumup_weeks[-1]
    st.rerun()
elif len(show_sumup_weeks) == 1:
    scope["selected_week"] = show_sumup_weeks[0]
else:
    scope["selected_week"] = None

selected_sumup_weeks = [
    str(row["Week"])
    for _, row in edited_sumup.iterrows()
    if bool(row["Select"])
]

export_total_placeholder.download_button(
    "Export Total",
    data=edited_sumup.to_csv(index=False).encode(),
    file_name="sumup_total.csv",
    mime="text/csv",
    help="Export the Sum-Up table in the same column format currently shown.",
)

tb_raw_df = _build_tb_raw_selected_weeks(result.basket_data, selected_sumup_weeks)
tb_raw_placeholder.download_button(
    "Export Week vs Basket",
    data=tb_raw_df.to_csv(index=False).encode(),
    file_name="TB Raw selected weeks.csv",
    mime="text/csv",
    disabled=not selected_sumup_weeks,
    help="Export selected weeks in basket-level raw format. Select at least one week in the table.",
)

with st.expander("📊 Sum-Up Total", expanded=True):
    with st.expander("📦 Stock Progress", expanded=True):
        valid_weeks  = [w for w in result.all_weeks if w in result.weekly_totals]
        progress_view = st.radio(
            "Progress representation",
            ["Separate plots", "Combined multi-Y-axis plot", "Vertical Stack"],
            horizontal=True,
            key=sk("progress_view_mode"),
        )
        show_stk     = st.toggle("Line + Symbol", True, key=sk("tog_stk"))
        total_margin_by_week = {r["week"]: r["total_m_corrected"] for r in sumup_rows}
        total_cost_by_week = {r["week"]: r.get("total_cost_corrected") for r in sumup_rows}
        total_margin_corrected = (
            [total_margin_by_week.get(w, float("nan")) for w in valid_weeks]
            if sumup_use_corrected
            else None
        )
        total_cost_corrected = (
            [total_cost_by_week.get(w, float("nan")) for w in valid_weeks]
            if sumup_use_corrected
            else None
        )
        stock_totals = [result.weekly_totals[w].sum_stock for w in valid_weeks]
        weighted_prices = [result.weekly_totals[w].weighted_price for w in valid_weeks]
        total_sold = [result.weekly_totals[w].sum_sold for w in valid_weeks]
        total_margin = [result.weekly_totals[w].sum_m for w in valid_weeks]
        sumup_progress_specs = _sumup_week_progress_specs(
            valid_weeks,
            sumup_rows,
            total_margin_corrected=total_margin_corrected,
            total_cost_corrected=total_cost_corrected,
        )
        enabled_sumup_progress = _render_progress_toggles(
            sumup_progress_specs,
            lambda key: sk(f"su_wp_{key}"),
        )
    
        if not enabled_sumup_progress:
            st.caption("Enable at least one metric above to show stock progress charts.")
        elif progress_view == "Separate plots":
            prog_cols = st.columns(2)
            for idx, spec in enumerate(enabled_sumup_progress):
                with prog_cols[idx % 2]:
                    st.plotly_chart(
                        build_metric_progress(
                            valid_weeks,
                            spec["values"],
                            title=spec["title"],
                            y_title=spec["y_title"],
                            marker_color=spec["marker_color"],
                            line_color=spec["line_color"],
                            show_line=show_stk,
                            overlay_values=spec.get("overlay_values"),
                            overlay_name=spec.get("overlay_name") or "",
                        ),
                        use_container_width=True,
                        key=sk(f"su_wp_chart_{spec['key']}"),
                    )
        elif progress_view == "Combined multi-Y-axis plot":
            st.plotly_chart(
                build_combined_progress(
                    valid_weeks,
                    stock_totals,
                    weighted_prices,
                    total_sold,
                    total_margin,
                    show_line=show_stk,
                    total_margin_corrected=total_margin_corrected,
                ),
                use_container_width=True,
                key=sk("chart_combined_progress"),
            )
            extra_enabled = [
                spec["label"]
                for spec in enabled_sumup_progress
                if spec["key"] not in {"stock", "price", "sold", "margin"}
            ]
            if extra_enabled:
                st.caption(
                    "Combined view shows Total Stock, W. Price, Total Sold, and Total Margin. "
                    "Use Separate plots or Vertical Stack for: "
                    + ", ".join(extra_enabled)
                    + "."
                )
        else:
            st.plotly_chart(
                build_vertical_stack_from_specs(
                    valid_weeks,
                    enabled_sumup_progress,
                    show_line=show_stk,
                ),
                use_container_width=True,
                key=sk("chart_stacked_progress"),
            )
    
    with st.expander(
        f"📊 Total Sold vs W. Price · {sumup_margin_title} vs W. Price · {sumup_margin_title} vs Total Sold",
        expanded=False,
    ):
        show_su_line = st.toggle("Line + Symbol", value=False, key=sk("tog_su_line"))
        st.plotly_chart(
            build_sumup_3panel(
                sumup_rows,
                show_line=show_su_line,
                margin_key=sumup_margin_key,
                margin_title=sumup_margin_title,
            ),
            use_container_width=True, key=sk("chart_su_3panel"),
        )
    
    with st.expander("📈 Total Cost vs W. Price"):
        fit_sumup_cost_res = scope["fit_sumup_cost"]
        scope_col, button_col, _ = st.columns([1, 1, 4])
        fit_scope_sumup_cost = scope_col.selectbox(
            "Points to fit",
            _sumup_fit_options(sumup_rows),
            key=sk("scope_sumup_cost"),
            label_visibility="collapsed",
        )
        fit_sumup_cost_clicked = button_col.button("Fit Line", key=sk("btn_line_sumup_cost"))
    
        plot_clmn, selection_clmn = st.columns([3, 1])
        with selection_clmn:
            st.markdown("**Datapoints**")
            manual_indices_sumup_cost = _manual_sumup_cost_fit_indices(
                sumup_rows,
                key=sk("manual_sumup_cost"),
            )
    
        fit_indices_sumup_cost = _resolve_sumup_fit_indices(
            sumup_rows,
            fit_scope_sumup_cost,
            manual_indices_sumup_cost,
        )
        plot_clmn.plotly_chart(
            build_sumup_cost_vs_price(
                sumup_rows,
                show_line=show_su_line,
                linefit=fit_sumup_cost_res,
                fitted_indices=fit_indices_sumup_cost,
            ),
            use_container_width=True,
            key=sk("chart_sumup_cost_vs_price"),
        )
    
        if fit_sumup_cost_clicked:
            if len(fit_indices_sumup_cost) < 2:
                st.warning("Select at least 2 data points to fit a line.")
                lf = None
            else:
                lf = fit_line(
                    [sumup_rows[i]["weighted_price"] for i in fit_indices_sumup_cost],
                    [sumup_rows[i]["total_cost"] for i in fit_indices_sumup_cost],
                )
            if lf is None:
                st.warning("Not enough data points to fit a line.")
            else:
                scope["fit_sumup_cost"] = lf
                st.rerun()
    
        if fit_sumup_cost_res:
            cost_res_col, _ = st.columns([3, 1])
            with cost_res_col.container(border=True):
                _render_linefit_stats(fit_sumup_cost_res)
    
    with st.expander(f"🌐 3D: W. Price × Total Sold × {sumup_margin_title}"):
        st.plotly_chart(
            build_sumup_3d(
                sumup_rows,
                show_line=show_su_line,
                margin_key=sumup_margin_key,
                margin_title=sumup_margin_title,
            ),
            use_container_width=True, key=sk("chart_su_3d"),
        )
    
    with st.expander("🌐 3D: W. Price × Total Stock × Total Sold"):
        fit_sumup_res = scope["fit_sumup_stock_sold"]
        method_col, scope_col, button_fit_sumup_plane_col, _ = st.columns([1, 1, 1, 3])
        method_sumup = method_col.selectbox(
            "Fit method",
            ["mlr", "pca"],
            format_func=str.upper,
            key=sk("meth_sumup_stock_sold"),
            label_visibility="collapsed",
        )
        fit_scope_sumup = scope_col.selectbox(
            "Points to fit",
            _sumup_fit_options(sumup_rows),
            key=sk("scope_sumup_stock_sold"),
            label_visibility="collapsed",
        )
        fit_sumup_plane_clicked = button_fit_sumup_plane_col.button(
            "Fit Plane",
            key=sk("btn_plane_sumup_stock_sold"),
        )
    
        plot_clmn, selection_clmn = st.columns([3, 1])
        with selection_clmn:
            st.markdown("**Datapoints**")
            manual_indices_sumup = _manual_sumup_fit_indices(
                sumup_rows,
                key=sk("manual_sumup_stock_sold"),
            )
    
        fit_indices_sumup = _resolve_sumup_fit_indices(
            sumup_rows,
            fit_scope_sumup,
            manual_indices_sumup,
        )
        plot_clmn.plotly_chart(
            build_sumup_stock_sold_3d(
                sumup_rows,
                show_line=show_su_line,
                planefit=fit_sumup_res,
                fitted_indices=fit_indices_sumup,
            ),
            use_container_width=True,
            key=sk("chart_su_stock_sold_3d"),
        )
    
        if fit_sumup_plane_clicked:
            if len(fit_indices_sumup) < 3:
                st.warning("Select at least 3 data points to fit a plane.")
                pf = None
            else:
                pf = fit_plane(
                    [sumup_rows[i]["weighted_price"] for i in fit_indices_sumup],
                    [sumup_rows[i]["total_stock"] for i in fit_indices_sumup],
                    [sumup_rows[i]["total_sold"] for i in fit_indices_sumup],
                    method=method_sumup,
                )
            if pf is None:
                st.warning("Not enough data points to fit a plane.")
            else:
                scope["fit_sumup_stock_sold"] = pf
                st.rerun()
    
        if fit_sumup_res:
            sumup_fit_res_col, _ = st.columns([3, 1])
            with sumup_fit_res_col.container(border=True):
                _render_planefit_stats(
                    fit_sumup_res,
                    label="Total Sold = z₀ + a·W. Price + b·Total Stock",
                )
    
    with st.expander(f"🌐 3D Overview: W. Price × Total Stock × {sumup_margin_label} + Margin Optimisation"):
        saved_sumup_margin_model = scope["sumup_margin_model"]
        sumup_margin_surface = saved_sumup_margin_model["surface"] if saved_sumup_margin_model else None
        st.plotly_chart(
            build_sumup_stock_m_3d(
                sumup_rows,
                show_line=show_su_line,
                margin_surface=sumup_margin_surface,
                margin_key=sumup_margin_key,
                margin_title=sumup_margin_label,
            ),
            use_container_width=True,
            key=sk("chart_su_stock_m_3d"),
        )
    
        with st.expander("**📐 Analytical Margin Optimisation Model**"):
            fit_sold_ok = scope["fit_sumup_stock_sold"]
            fit_cost_ok = scope["fit_sumup_cost"]
            if fit_sold_ok and fit_cost_ok:
                _render_sumup_margin_model(
                    sumup_rows, fit_sold_ok, fit_cost_ok, scope, sk,
                    margin_key=sumup_margin_key,
                )
            else:
                st.info(
                    "Fit `Total Sold = f(W. Price, Total Stock)` and "
                    "`Total Cost = f(W. Price)` first."
                )
    
# Weekly basket detail
if scope["selected_week"] and scope["selected_week"] in result.weekly_totals:
    wt = result.weekly_totals[scope["selected_week"]]
    selected_week = str(scope["selected_week"])

    week_detail_rows = compute_basket_week_detail_rows(
        result.basket_data,
        result.weekly_totals,
        selected_week,
        margin_by_basket=scope.get("basket_margin_hybrid"),
    )

    with st.expander(f"📋 Weekly Detail: {selected_week}", expanded=False):
        if week_detail_rows:
            df_week_detail = pd.DataFrame(week_detail_rows)
            week_detail_export_col, _ = st.columns([1, 5])
            week_detail_export_col.download_button(
                "Export CSV",
                data=df_week_detail.to_csv(index=False).encode(),
                file_name=f"weekly_detail_{selected_week}.csv",
                mime="text/csv",
                key=sk(f"week_detail_export_{selected_week}"),
                help="Export all basket rows for this week (raw numeric values).",
            )
            week_detail_display = (
                df_week_detail.style.apply(_sumup_qw_row_style, axis=1)
                if colour_sumup_by_qw
                else df_week_detail
            )
            st.dataframe(
                week_detail_display,
                use_container_width=True,
                hide_index=True,
                key=sk(f"week_detail_table_{selected_week}"),
            )
        else:
            st.info("No basket rows for the selected week.")

    with st.expander(f"📉 Week Discount: {selected_week}", expanded=True):
        discount_hist_category = (
            product_bs_category
            if input_mode in PRODUCT_BS_INPUT_MODES
            else AGGREGATED_DISCOUNT_HIST_CATEGORY
        )
        render_week_discount_section(
            result.basket_data,
            result.weekly_totals,
            result.all_weeks,
            selected_week,
            pbs_scope_key,
            discount_hist_category,
            pbs_scope.get("discount_hist_df"),
            input_mode=input_mode,
            margin_by_basket=scope.get("basket_margin_hybrid"),
        )

    with st.expander(f"📅 Week Visualization: {selected_week}", expanded=False):
        wk1, wk2, wk3, wk4, wk5, wk6, wk7 = st.columns(7)
        available_groups = sorted({b.group for b in result.basket_results if b.group > 0})
        selected_group = wk1.selectbox(
            "Group",
            options=[None] + available_groups,
            format_func=lambda g: "All Groups" if g is None else result.get_cluster_label(g),
            key=sk("sel_wk_group"),
            label_visibility="collapsed",
        )
        log_price    = wk2.toggle("Log Price",    False, key=sk("tog_wk_log_price"))
        log_sold_qty = wk3.toggle("Log Sold Qty", False, key=sk("tog_wk_log_sold"))
        log_stock    = wk4.toggle("Log Stock",    False, key=sk("tog_wk_log_stock"))
        log_margin   = wk5.toggle("Log Margin",   False, key=sk("tog_wk_log_margin"))
        color_grp    = wk6.toggle("Colour by Group", False, key=sk("tog_wk_color"))
        show_wk_line = wk7.toggle("Line + Symbol",   False, key=sk("tog_wk_line"))
    
        st.plotly_chart(
            build_weekly_basket_3panel(
                wt,
                basket_results=result.basket_results,
                use_log_price=log_price,
                use_log_sold=log_sold_qty,
                use_log_margin=log_margin,
                color_by_group=color_grp,
                group_filter=selected_group,
                show_line=show_wk_line,
            ),
            use_container_width=True, key=sk(f"chart_wk_{scope['selected_week']}"),
        )
    
        with st.expander("🌐 3D Overview: Price × Sold × M"):
            st.plotly_chart(
                build_weekly_basket_3d(
                    wt,
                    basket_results=result.basket_results,
                    use_log_price=log_price,
                    use_log_sold=log_sold_qty,
                    use_log_margin=log_margin,
                    color_by_group=color_grp,
                    group_filter=selected_group,
                ),
                use_container_width=True,
                key=sk(f"chart_wk_3d_{scope['selected_week']}"),
            )
    
        with st.expander("🌐 3D Overview: Price × Stock × Sold"):
            st.plotly_chart(
                build_weekly_basket_stock_sold_3d(
                    wt,
                    basket_results=result.basket_results,
                    use_log_price=log_price,
                    use_log_stock=log_stock,
                    use_log_sold=log_sold_qty,
                    color_by_group=color_grp,
                    group_filter=selected_group,
                ),
                use_container_width=True,
                key=sk(f"chart_wk_stock_sold_3d_{scope['selected_week']}"),
            )
    
        with st.expander("🌐 3D Overview: Price × Stock × M"):
            st.plotly_chart(
                build_weekly_basket_stock_m_3d(
                    wt,
                    basket_results=result.basket_results,
                    use_log_price=log_price,
                    use_log_stock=log_stock,
                    use_log_margin=log_margin,
                    color_by_group=color_grp,
                    group_filter=selected_group,
                ),
                use_container_width=True,
                key=sk(f"chart_wk_stock_m_3d_{scope['selected_week']}"),
            )
