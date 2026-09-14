"""
Reusable Plotly chart builders for the Sum-Up (aggregate weekly) view.

All functions return Plotly Figure objects — no Streamlit imports.
"""

from __future__ import annotations
import math
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Optional

from core.models import WeeklyTotal, BasketResult, Planefit, Linefit
from configs.settings import CLUSTER_COLORS, UNCLUSTERED_COLOR
from visualizations.detail_charts import marker_colors_for_points, add_qw_average_hlines


def _is_finite_number(value) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


# ---------------------------------------------------------------------------
# Weekly aggregate 3-panel scatter
# ---------------------------------------------------------------------------

def build_sumup_3panel(
    sumup_rows: list[dict],
    show_line: bool = False,
    margin_key: str = "total_m",
    margin_title: str = "Total M",
) -> go.Figure:
    """
    3-panel scatter for weekly aggregate totals:
    1) Total Sold vs W. Price
    2) Total M vs W. Price
    3) Total M vs Total Sold
    """
    weeks = [r["week"] for r in sumup_rows]
    wp = [r["weighted_price"] for r in sumup_rows]
    ts = [r["total_sold"] for r in sumup_rows]
    tm = [r.get(margin_key, r["total_m"]) for r in sumup_rows]
    hover = [f"Week: {r['week']}" for r in sumup_rows]

    mode = "lines+markers" if show_line else "markers"

    fig = make_subplots(rows=1, cols=3, subplot_titles=[
        "Total Sold vs W. Price",
        f"{margin_title} vs W. Price",
        f"{margin_title} vs Total Sold",
    ])

    for col, (x, y, color) in enumerate([
        (wp, ts, "rgba(59,130,246,0.75)"),
        (wp, tm, "rgba(16,185,129,0.75)"),
        (ts, tm, "rgba(139,92,246,0.75)"),
    ], start=1):
        fig.add_trace(go.Scatter(
            x=x, y=y, mode=mode,
            text=hover, hoverinfo="text",
            marker=dict(color=color, size=7),
            line=dict(color=color),
            showlegend=False,
        ), row=1, col=col)

    fig.update_xaxes(title_text="W. Price", row=1, col=1)
    fig.update_yaxes(title_text="Total Sold", row=1, col=1)
    fig.update_xaxes(title_text="W. Price", row=1, col=2)
    fig.update_yaxes(title_text=margin_title, row=1, col=2)
    fig.update_xaxes(title_text="Total Sold", row=1, col=3)
    fig.update_yaxes(title_text=margin_title, row=1, col=3)

    fig.update_layout(height=320, margin=dict(l=40, r=20, t=50, b=40))
    return fig


# ---------------------------------------------------------------------------
# Weekly 3D aggregate chart
# ---------------------------------------------------------------------------

def build_sumup_3d(
    sumup_rows: list[dict],
    show_line: bool = False,
    margin_key: str = "total_m",
    margin_title: str = "Total M",
) -> go.Figure:
    """3D scatter: W. Price × Total Sold × Total M (one point per week)."""
    mode = "lines+markers" if show_line else "markers"
    wp = [r["weighted_price"] for r in sumup_rows]
    ts = [r["total_sold"] for r in sumup_rows]
    tm = [r.get(margin_key, r["total_m"]) for r in sumup_rows]
    texts = [
        f"Week: {r['week']}<br>W. Price: {r['weighted_price']:.2f}<br>"
        f"Total Sold: {r['total_sold']:.2f}<br>{margin_title}: {r.get(margin_key, r['total_m']):.2f}"
        for r in sumup_rows
    ]

    fig = go.Figure(go.Scatter3d(
        x=wp, y=ts, z=tm,
        mode=mode,
        marker=dict(size=5, color="rgba(59,130,246,0.8)"),
        line=dict(color="rgb(37,99,235)", width=3),
        text=texts, hoverinfo="text",
    ))
    fig.update_layout(
        scene=dict(
            xaxis_title="W. Price",
            yaxis_title="Total Sold",
            zaxis_title=margin_title,
        ),
        margin=dict(l=0, r=0, b=0, t=0), height=420, showlegend=False,
    )
    return fig


def build_sumup_stock_sold_3d(
    sumup_rows: list[dict],
    show_line: bool = False,
    planefit: Optional[Planefit] = None,
    fitted_indices: Optional[list[int]] = None,
) -> go.Figure:
    """3D scatter: W. Price × Total Stock × Total Sold (one point per week)."""
    mode = "lines+markers" if show_line else "markers"
    wp = [r["weighted_price"] for r in sumup_rows]
    stock = [r["total_stock"] for r in sumup_rows]
    sold = [r["total_sold"] for r in sumup_rows]
    if fitted_indices is None:
        marker_colors = ["rgba(236,72,153,0.8)"] * len(sumup_rows)
    else:
        fitted_index_set = set(fitted_indices)
        marker_colors = [
            "rgba(239,68,68,1)" if i in fitted_index_set else "rgba(200,200,200,0.35)"
            for i in range(len(sumup_rows))
        ]
    texts = [
        f"Week: {r['week']}<br>W. Price: {r['weighted_price']:.2f}<br>"
        f"Total Stock: {r['total_stock']:.2f}<br>Total Sold: {r['total_sold']:.2f}"
        for r in sumup_rows
    ]

    fig = go.Figure(go.Scatter3d(
        x=wp, y=stock, z=sold,
        mode=mode,
        marker=dict(size=5, color=marker_colors),
        line=dict(color="rgb(219,39,119)", width=3),
        text=texts, hoverinfo="text",
    ))
    if planefit is not None:
        _add_sumup_plane_surface(fig, wp, stock, planefit, "rgba(59,130,246,0.4)")
    fig.update_layout(
        scene=dict(xaxis_title="W. Price", yaxis_title="Total Stock", zaxis_title="Total Sold"),
        margin=dict(l=0, r=0, b=0, t=0), height=420, showlegend=False,
    )
    return fig


def build_sumup_stock_m_3d(
    sumup_rows: list[dict],
    show_line: bool = False,
    margin_surface: Optional[tuple[list[float], list[float], list[list[float]]]] = None,
    margin_key: str = "total_m",
    margin_title: str = "Total Margin",
) -> go.Figure:
    """3D scatter: W. Price × Total Stock × Total Margin (one point per week)."""
    mode = "lines+markers" if show_line else "markers"
    wp = [r["weighted_price"] for r in sumup_rows]
    stock = [r["total_stock"] for r in sumup_rows]
    margin = [r.get(margin_key, r["total_m"]) for r in sumup_rows]
    texts = [
        f"Week: {r['week']}<br>W. Price: {r['weighted_price']:.2f}<br>"
        f"Total Stock: {r['total_stock']:.2f}<br>{margin_title}: {r.get(margin_key, r['total_m']):.2f}"
        for r in sumup_rows
    ]

    fig = go.Figure(go.Scatter3d(
        x=wp,
        y=stock,
        z=margin,
        mode=mode,
        marker=dict(size=5, color="rgba(139,92,246,0.8)"),
        line=dict(color="rgb(109,40,217)", width=3),
        text=texts,
        hoverinfo="text",
    ))

    if margin_surface is not None:
        price_grid, stock_grid, m_grid = margin_surface
        fig.add_trace(go.Surface(
            x=price_grid,
            y=stock_grid,
            z=m_grid,
            opacity=0.75,
            colorscale="Viridis",
            showscale=False,
            hoverinfo="none",
            name="Analytical M Model",
        ))

    fig.update_layout(
        scene=dict(
            xaxis_title="W. Price",
            yaxis_title="Total Stock",
            zaxis_title=margin_title,
        ),
        margin=dict(l=0, r=0, b=0, t=0),
        height=420,
        showlegend=False,
    )
    return fig


def build_sumup_cost_vs_price(
    sumup_rows: list[dict],
    show_line: bool = False,
    linefit: Optional[Linefit] = None,
    fitted_indices: Optional[list[int]] = None,
) -> go.Figure:
    """Scatter of aggregate Total Cost vs W. Price with optional fitted line."""
    mode = "lines+markers" if show_line else "markers"
    wp = [r["weighted_price"] for r in sumup_rows]
    total_cost = [r["total_cost"] for r in sumup_rows]
    if fitted_indices is None:
        marker_colors = ["rgba(6,182,212,0.75)"] * len(sumup_rows)
    else:
        fitted_index_set = set(fitted_indices)
        marker_colors = [
            "rgba(239,68,68,1)" if i in fitted_index_set else "rgba(200,200,200,0.35)"
            for i in range(len(sumup_rows))
        ]
    texts = [
        f"Week: {r['week']}<br>QW: {r.get('quadweek', 'N/A')}<br>"
        f"W. Price: {r['weighted_price']:.2f}<br>Total Cost: {r['total_cost']:.2f}"
        for r in sumup_rows
    ]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=wp,
        y=total_cost,
        mode=mode,
        marker=dict(size=7, color=marker_colors),
        line=dict(color="rgba(6,182,212,0.75)"),
        text=texts,
        hoverinfo="text",
        showlegend=False,
    ))

    if linefit is not None and wp:
        x_min, x_max = min(wp), max(wp)
        pad = (x_max - x_min) * 0.1 or 1.0
        x0, x1 = x_min - pad, x_max + pad
        fig.add_trace(go.Scatter(
            x=[x0, x1],
            y=[linefit.z0 + linefit.a * x0, linefit.z0 + linefit.a * x1],
            mode="lines",
            name="Fitted Line",
            line=dict(color="rgba(239,68,68,1)", width=2, dash="dash"),
        ))

    fig.update_layout(
        xaxis_title="W. Price",
        yaxis_title="Total Cost",
        title="Total Cost vs W. Price",
        height=420,
        margin=dict(l=50, r=20, t=50, b=50),
        showlegend=False,
    )
    return fig


def _add_sumup_plane_surface(
    fig: go.Figure,
    x: list[float],
    y: list[float],
    fit: Planefit,
    surface_color: str,
) -> None:
    """Add a fitted plane surface to a Sum-Up 3D figure."""
    x_pad = (max(x) - min(x)) * 0.1 or 1.0
    y_pad = (max(y) - min(y)) * 0.1 or 1.0
    x0, x1 = min(x) - x_pad, max(x) + x_pad
    y0, y1 = min(y) - y_pad, max(y) + y_pad
    z_grid = [
        [fit.z0 + fit.a * x0 + fit.b * y0, fit.z0 + fit.a * x1 + fit.b * y0],
        [fit.z0 + fit.a * x0 + fit.b * y1, fit.z0 + fit.a * x1 + fit.b * y1],
    ]
    fig.add_trace(go.Surface(
        x=[x0, x1],
        y=[y0, y1],
        z=z_grid,
        opacity=0.6,
        colorscale=[[0, surface_color], [1, surface_color]],
        showscale=False,
        hoverinfo="none",
        name="Fit Plane",
    ))


# ---------------------------------------------------------------------------
# Stock progress over time
# ---------------------------------------------------------------------------

def build_stock_progress(
    weeks: list[str],
    stock_totals: list[float],
    show_line: bool = False,
) -> go.Figure:
    """Total Stock vs Week line/scatter chart."""
    return build_metric_progress(
        weeks=weeks,
        values=stock_totals,
        title="Total Stock vs Week",
        y_title="Total Stock",
        marker_color="rgba(236,72,153,0.75)",
        line_color="rgb(219,39,119)",
        show_line=show_line,
    )


def build_metric_progress(
    weeks: list[str],
    values: list[float],
    title: str,
    y_title: str,
    marker_color: str,
    line_color: str,
    show_line: bool = False,
    quadweeks: list[str] | None = None,
    use_qw_colors: bool = False,
    show_qw_average: bool = False,
    overlay_values: list[float] | None = None,
    overlay_name: str = "",
    overlay_marker_color: str = "rgba(239,68,68,0.9)",
    overlay_line_color: str = "rgb(220,38,38)",
) -> go.Figure:
    """Generic weekly progress line/scatter chart with categorical YYYY-WW x-axis."""
    mode = "lines+markers" if show_line else "markers"

    week_labels = [str(week) for week in weeks]
    clean_values = [v for v in values if _is_finite_number(v)]
    if overlay_values:
        clean_values.extend(v for v in overlay_values if _is_finite_number(v))
    y_min = min(clean_values) if clean_values else 0.0
    y_max = max(clean_values) if clean_values else 1.0
    y_pad = (y_max - y_min) * 0.1 or max(abs(y_min) * 0.05, 1.0)

    fig = go.Figure()
    marker_colors = (
        marker_colors_for_points(quadweeks, True, marker_color)
        if use_qw_colors and quadweeks and len(quadweeks) == len(values)
        else marker_color
    )
    fig.add_trace(go.Scatter(
        x=week_labels, y=values,
        mode=mode,
        name=y_title,
        marker=dict(
            color=marker_colors,
            size=7,
            line=dict(width=0.5, color="#111827"),
        ),
        line=dict(color=line_color, width=2),
        showlegend=bool(overlay_values),
    ))
    if overlay_values is not None and len(overlay_values) == len(week_labels):
        fig.add_trace(go.Scatter(
            x=week_labels, y=overlay_values,
            mode=mode,
            name=overlay_name or "Corrected",
            marker=dict(
                color=overlay_marker_color,
                size=8,
                symbol="diamond",
                line=dict(width=0.5, color="#111827"),
            ),
            line=dict(color=overlay_line_color, width=2, dash="dash"),
            showlegend=True,
        ))

    if (
        show_qw_average
        and quadweeks
        and len(quadweeks) == len(values)
    ):
        add_qw_average_hlines(fig, week_labels, values, quadweeks)
        if overlay_values is not None and len(overlay_values) == len(values):
            hybrid = []
            n_corrected = 0
            for original, overlay in zip(values, overlay_values):
                if _is_finite_number(overlay):
                    hybrid.append(float(overlay))
                    n_corrected += 1
                else:
                    hybrid.append(original)
            if n_corrected:
                add_qw_average_hlines(
                    fig,
                    week_labels,
                    hybrid,
                    quadweeks,
                    dash="dot",
                    line_color=overlay_line_color,
                    line_width=3,
                    name="Corrected Average QW",
                    hover_label="Corrected Average",
                    legend_once=True,
                )

    fig.update_layout(
        xaxis_title="Week", yaxis_title=y_title,
        title=title,
        xaxis_tickangle=-45,
        xaxis=dict(
            type="category",
            categoryorder="array",
            categoryarray=week_labels,
        ),
        yaxis=dict(range=[y_min - y_pad, y_max + y_pad]),
        height=320, margin=dict(l=50, r=20, t=50, b=80),
    )
    return fig


def build_combined_progress(
    weeks: list[str],
    stock_totals: list[float],
    weighted_prices: list[float],
    total_sold: list[float],
    total_margin: list[float],
    show_line: bool = False,
    total_margin_corrected: list[float] | None = None,
) -> go.Figure:
    """Combined weekly progress chart with four independent y-axes."""
    mode = "lines+markers" if show_line else "markers"
    week_labels = [str(week) for week in weeks]

    metrics = [
        {
            "name": "Total Stock",
            "values": stock_totals,
            "axis": "y",
            "color": "rgb(219,39,119)",
        },
        {
            "name": "W. Price",
            "values": weighted_prices,
            "axis": "y2",
            "color": "rgb(5,150,105)",
        },
        {
            "name": "Total Sold",
            "values": total_sold,
            "axis": "y3",
            "color": "rgb(37,99,235)",
        },
        {
            "name": "Total Margin",
            "values": total_margin,
            "axis": "y4",
            "color": "rgb(109,40,217)",
        },
    ]

    fig = go.Figure()
    for metric in metrics:
        fig.add_trace(go.Scatter(
            x=week_labels,
            y=metric["values"],
            mode=mode,
            name=metric["name"],
            yaxis=metric["axis"],
            marker=dict(color=metric["color"], size=7),
            line=dict(color=metric["color"], width=2),
            hovertemplate=(
                "Week: %{x}<br>"
                f"{metric['name']}: "
                "%{y:,.2f}<extra></extra>"
            ),
        ))

    if (
        total_margin_corrected is not None
        and len(total_margin_corrected) == len(week_labels)
    ):
        fig.add_trace(go.Scatter(
            x=week_labels,
            y=total_margin_corrected,
            mode=mode,
            name="Total Margin Corrected",
            yaxis="y4",
            marker=dict(color="rgb(220,38,38)", size=7, symbol="diamond"),
            line=dict(color="rgb(220,38,38)", width=2, dash="dash"),
            hovertemplate=(
                "Week: %{x}<br>"
                "Total Margin Corrected: %{y:,.2f}<extra></extra>"
            ),
        ))

    fig.update_layout(
        title="Weekly Progress: Stock, Price, Sold, Margin",
        xaxis=dict(
            title="Week",
            type="category",
            categoryorder="array",
            categoryarray=week_labels,
            tickangle=-45,
            domain=[0.08, 0.92],
        ),
        yaxis=dict(
            title=dict(text="Total Stock", font=dict(color="rgb(219,39,119)")),
            tickfont=dict(color="rgb(219,39,119)"),
            side="left",
            position=0.0,
        ),
        yaxis2=dict(
            title=dict(text="W. Price", font=dict(color="rgb(5,150,105)")),
            tickfont=dict(color="rgb(5,150,105)"),
            anchor="free",
            overlaying="y",
            side="right",
            position=1.0,
        ),
        yaxis3=dict(
            title=dict(text="Total Sold", font=dict(color="rgb(37,99,235)")),
            tickfont=dict(color="rgb(37,99,235)"),
            anchor="free",
            overlaying="y",
            side="left",
            position=0.05,
        ),
        yaxis4=dict(
            title=dict(text="Total Margin", font=dict(color="rgb(109,40,217)")),
            tickfont=dict(color="rgb(109,40,217)"),
            anchor="free",
            overlaying="y",
            side="right",
            position=0.95,
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=520,
        margin=dict(l=80, r=90, t=80, b=90),
    )
    return fig


def build_vertical_stack_progress(
    weeks: list[str],
    stock_totals: list[float],
    weighted_prices: list[float],
    total_sold: list[float],
    total_margin: list[float],
    show_line: bool = False,
    total_margin_corrected: list[float] | None = None,
) -> go.Figure:
    """Four vertically stacked weekly progress plots with a shared categorical x-axis."""
    week_labels = [str(week) for week in weeks]
    trace_mode = "lines+markers" if show_line else "lines"

    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.055,
        subplot_titles=(
            "Stock Progress",
            "W. Price vs Week",
            "Total Sold vs Week",
            "Total Margin vs Week",
        ),
    )

    traces = [
        {
            "row": 1,
            "name": "Stock",
            "values": stock_totals,
            "marker_color": "rgba(249,115,22,0.75)",
            "line_color": "rgb(234,88,12)",
            "y_title": "Stock",
        },
        {
            "row": 2,
            "name": "W. Price",
            "values": weighted_prices,
            "marker_color": "rgba(16,185,129,0.75)",
            "line_color": "rgb(5,150,105)",
            "y_title": "W. Price",
        },
        {
            "row": 3,
            "name": "Total Sold",
            "values": total_sold,
            "marker_color": "rgba(59,130,246,0.75)",
            "line_color": "rgb(37,99,235)",
            "y_title": "Sold",
        },
        {
            "row": 4,
            "name": "Total Margin",
            "values": total_margin,
            "marker_color": "rgba(139,92,246,0.75)",
            "line_color": "rgb(109,40,217)",
            "y_title": "Margin",
        },
    ]

    for trace in traces:
        fig.add_trace(
            go.Scatter(
                x=week_labels,
                y=trace["values"],
                name=trace["name"],
                mode=trace_mode,
                marker=dict(color=trace["marker_color"], size=7),
                line=dict(color=trace["line_color"], width=2),
                hovertemplate=(
                    "Week: %{x}<br>"
                    f"{trace['name']}: "
                    "%{y:,.2f}<extra></extra>"
                ),
            ),
            row=trace["row"],
            col=1,
        )
        fig.update_yaxes(title_text=trace["y_title"], row=trace["row"], col=1)

    if (
        total_margin_corrected is not None
        and len(total_margin_corrected) == len(week_labels)
    ):
        fig.add_trace(
            go.Scatter(
                x=week_labels,
                y=total_margin_corrected,
                name="Total Margin Corrected",
                mode=trace_mode,
                marker=dict(color="rgba(220,38,38,0.9)", size=7, symbol="diamond"),
                line=dict(color="rgb(220,38,38)", width=2, dash="dash"),
                hovertemplate=(
                    "Week: %{x}<br>"
                    "Total Margin Corrected: %{y:,.2f}<extra></extra>"
                ),
            ),
            row=4,
            col=1,
        )

    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=week_labels,
        tickangle=-45,

        showspikes=True,            # Enable the vertical cursor lines
        spikemode="across",         # Stretch the lines completely across all subplots
        spikesnap="cursor",         # Force line to snap right onto the nearest data point
        spikethickness=1,           # Line width
        spikecolor="rgb(128,128,128)", # Subtle gray color for the line
        spikedash="dash",
    )
    fig.update_xaxes(title_text="Week", row=4, col=1)
    fig.update_layout(
        height=850,
        #overmode="x unified",
        hovermode="x unified",
        showlegend=bool(total_margin_corrected),
        margin=dict(l=60, r=30, t=70, b=80),
    )
    return fig


def build_vertical_stack_from_specs(
    weeks: list[str],
    specs: list[dict],
    show_line: bool = False,
) -> go.Figure:
    """Vertically stacked weekly progress plots driven by metric specs."""
    week_labels = [str(week) for week in weeks]
    trace_mode = "lines+markers" if show_line else "lines"
    n = max(1, len(specs))
    fig = make_subplots(
        rows=n,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=min(0.08, 0.35 / n),
        subplot_titles=tuple(spec.get("title") or spec.get("name", "") for spec in specs),
    )
    has_overlay = False
    for idx, spec in enumerate(specs, start=1):
        name = spec.get("name") or spec.get("label") or spec.get("y_title", "Value")
        fig.add_trace(
            go.Scatter(
                x=week_labels,
                y=spec["values"],
                name=name,
                mode=trace_mode,
                marker=dict(color=spec.get("marker_color", "rgba(59,130,246,0.75)"), size=7),
                line=dict(color=spec.get("line_color", "rgb(37,99,235)"), width=2),
                hovertemplate=(
                    "Week: %{x}<br>"
                    f"{name}: "
                    "%{y:,.2f}<extra></extra>"
                ),
            ),
            row=idx,
            col=1,
        )
        overlay_values = spec.get("overlay_values")
        overlay_name = spec.get("overlay_name") or "Corrected"
        if overlay_values is not None and len(overlay_values) == len(week_labels):
            has_overlay = True
            fig.add_trace(
                go.Scatter(
                    x=week_labels,
                    y=overlay_values,
                    name=overlay_name,
                    mode=trace_mode,
                    marker=dict(color="rgba(220,38,38,0.9)", size=7, symbol="diamond"),
                    line=dict(color="rgb(220,38,38)", width=2, dash="dash"),
                    hovertemplate=(
                        "Week: %{x}<br>"
                        f"{overlay_name}: "
                        "%{y:,.2f}<extra></extra>"
                    ),
                ),
                row=idx,
                col=1,
            )
        fig.update_yaxes(title_text=spec.get("y_title", ""), row=idx, col=1)

    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=week_labels,
        tickangle=-45,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikethickness=1,
        spikecolor="rgb(128,128,128)",
        spikedash="dash",
    )
    fig.update_xaxes(title_text="Week", row=n, col=1)
    fig.update_layout(
        height=max(360, 160 * n + 80),
        hovermode="x unified",
        showlegend=has_overlay,
        margin=dict(l=60, r=30, t=70, b=80),
    )
    return fig


# ---------------------------------------------------------------------------
# Weekly basket breakdown (when a week row is clicked)
# ---------------------------------------------------------------------------

def build_weekly_basket_3panel(
    weekly_total: WeeklyTotal,
    basket_results: list[BasketResult],
    use_log_price: bool = False,
    use_log_sold: bool = False,
    use_log_margin: bool = False,
    color_by_group: bool = False,
    group_filter: Optional[int] = None,
    show_line: bool = False,
) -> go.Figure:
    """
    3-panel scatter showing basket-level data for a single selected week.
    1) Sold vs Price  2) M vs Price  3) M vs Sold
    """
    # Build group lookup for colouring
    group_map = {b.basket: b.group for b in basket_results}
    pts = [
        p for p in weekly_total.points
        if group_filter is None or group_map.get(p.basket, 0) == group_filter
    ]
    if not pts:
        return go.Figure()

    def _color(basket: str, default: str) -> str:
        if not color_by_group:
            return default
        g = group_map.get(basket, 0)
        return CLUSTER_COLORS[(g - 1) % len(CLUSTER_COLORS)] if g > 0 else UNCLUSTERED_COLOR

    mode = "lines+markers" if show_line else "markers"

    hover = [f"Basket: {p.basket}<br>Price: {p.price:.2f}<br>Sold: {p.sold:.2f}<br>M: {p.m:.2f}" for p in pts]

    fig = make_subplots(rows=1, cols=3, subplot_titles=[
        "1) Sold vs Price", "2) M vs Price", "3) M vs Sold"
    ])

    for col_idx, (x_key, y_key, default_color) in enumerate([
        ("price", "sold", "rgba(59,130,246,0.75)"),
        ("price", "m",    "rgba(16,185,129,0.75)"),
        ("sold",  "m",    "rgba(139,92,246,0.75)"),
    ], start=1):
        xs = [getattr(p, x_key) for p in pts]
        ys = [getattr(p, y_key) for p in pts]
        colors = [_color(p.basket, default_color) for p in pts]

        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode=mode,
            text=hover, hoverinfo="text",
            marker=dict(color=colors, size=7),
            showlegend=False,
        ), row=1, col=col_idx)

    fig.update_xaxes(type="log" if use_log_price else "linear", row=1, col=1)
    fig.update_yaxes(type="log" if use_log_sold else "linear", row=1, col=1)
    fig.update_xaxes(type="log" if use_log_price else "linear", row=1, col=2)
    fig.update_yaxes(type="log" if use_log_margin else "linear", row=1, col=2)
    fig.update_xaxes(type="log" if use_log_sold else "linear", row=1, col=3)
    fig.update_yaxes(type="log" if use_log_margin else "linear", row=1, col=3)
    fig.update_xaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Sold Qty", row=1, col=1)
    fig.update_xaxes(title_text="Price", row=1, col=2)
    fig.update_yaxes(title_text="Margin (M)", row=1, col=2)
    fig.update_xaxes(title_text="Sold Qty", row=1, col=3)
    fig.update_yaxes(title_text="Margin (M)", row=1, col=3)

    fig.update_layout(height=320, margin=dict(l=40, r=20, t=50, b=40))
    return fig


def build_weekly_basket_3d(
    weekly_total: WeeklyTotal,
    basket_results: list[BasketResult],
    use_log_price: bool = False,
    use_log_sold: bool = False,
    use_log_margin: bool = False,
    color_by_group: bool = False,
    group_filter: Optional[int] = None,
) -> go.Figure:
    """3D scatter for a selected week: Price × Sold × M."""
    group_map = {b.basket: b.group for b in basket_results}
    pts = [
        p for p in weekly_total.points
        if group_filter is None or group_map.get(p.basket, 0) == group_filter
    ]
    if not pts:
        return go.Figure()

    def _color(basket: str) -> str:
        if not color_by_group:
            return "rgba(16,185,129,0.8)"
        group = group_map.get(basket, 0)
        return CLUSTER_COLORS[(group - 1) % len(CLUSTER_COLORS)] if group > 0 else UNCLUSTERED_COLOR

    marker_colors = [_color(p.basket) for p in pts]
    hover = [
        f"Basket: {p.basket}<br>Price: {p.price:.2f}<br>Sold: {p.sold:.2f}<br>M: {p.m:.2f}"
        for p in pts
    ]

    fig = go.Figure(go.Scatter3d(
        x=[p.price for p in pts],
        y=[p.sold for p in pts],
        z=[p.m for p in pts],
        mode="markers",
        marker=dict(size=5, color=marker_colors, line=dict(width=1)),
        text=hover,
        hoverinfo="text",
        showlegend=False,
    ))

    fig.update_layout(
        scene=dict(
            xaxis=dict(title="Price", type="log" if use_log_price else "linear"),
            yaxis=dict(title="Sold", type="log" if use_log_sold else "linear"),
            zaxis=dict(title="Margin (M)", type="log" if use_log_margin else "linear"),
        ),
        margin=dict(l=0, r=0, b=0, t=0),
        height=420,
        showlegend=False,
    )
    return fig


def build_weekly_basket_stock_sold_3d(
    weekly_total: WeeklyTotal,
    basket_results: list[BasketResult],
    use_log_price: bool = False,
    use_log_stock: bool = False,
    use_log_sold: bool = False,
    color_by_group: bool = False,
    group_filter: Optional[int] = None,
) -> go.Figure:
    """3D scatter for a selected week: Price × Stock × Sold."""
    group_map = {b.basket: b.group for b in basket_results}
    pts = [
        p for p in weekly_total.points
        if group_filter is None or group_map.get(p.basket, 0) == group_filter
    ]
    if not pts:
        return go.Figure()

    def _color(basket: str) -> str:
        if not color_by_group:
            return "rgba(59,130,246,0.8)"
        group = group_map.get(basket, 0)
        return CLUSTER_COLORS[(group - 1) % len(CLUSTER_COLORS)] if group > 0 else UNCLUSTERED_COLOR

    marker_colors = [_color(p.basket) for p in pts]
    hover = [
        (
            f"Basket: {p.basket}<br>Price: {p.price:.2f}<br>"
            f"Stock: {p.stock:.2f}<br>Sold: {p.sold:.2f}"
        )
        for p in pts
    ]

    fig = go.Figure(go.Scatter3d(
        x=[p.price for p in pts],
        y=[p.stock for p in pts],
        z=[p.sold for p in pts],
        mode="markers",
        marker=dict(size=5, color=marker_colors, line=dict(width=1)),
        text=hover,
        hoverinfo="text",
        showlegend=False,
    ))

    fig.update_layout(
        scene=dict(
            xaxis=dict(title="Price", type="log" if use_log_price else "linear"),
            yaxis=dict(title="Stock", type="log" if use_log_stock else "linear"),
            zaxis=dict(title="Sold", type="log" if use_log_sold else "linear"),
        ),
        margin=dict(l=0, r=0, b=0, t=0),
        height=420,
        showlegend=False,
    )
    return fig


def build_weekly_basket_stock_m_3d(
    weekly_total: WeeklyTotal,
    basket_results: list[BasketResult],
    use_log_price: bool = False,
    use_log_stock: bool = False,
    use_log_margin: bool = False,
    color_by_group: bool = False,
    group_filter: Optional[int] = None,
) -> go.Figure:
    """3D scatter for a selected week: Price × Stock × M."""
    group_map = {b.basket: b.group for b in basket_results}
    pts = [
        p for p in weekly_total.points
        if group_filter is None or group_map.get(p.basket, 0) == group_filter
    ]
    if not pts:
        return go.Figure()

    def _color(basket: str) -> str:
        if not color_by_group:
            return "rgba(139,92,246,0.8)"
        group = group_map.get(basket, 0)
        return CLUSTER_COLORS[(group - 1) % len(CLUSTER_COLORS)] if group > 0 else UNCLUSTERED_COLOR

    marker_colors = [_color(p.basket) for p in pts]
    hover = [
        (
            f"Basket: {p.basket}<br>Price: {p.price:.2f}<br>"
            f"Stock: {p.stock:.2f}<br>M: {p.m:.2f}"
        )
        for p in pts
    ]

    fig = go.Figure(go.Scatter3d(
        x=[p.price for p in pts],
        y=[p.stock for p in pts],
        z=[p.m for p in pts],
        mode="markers",
        marker=dict(size=5, color=marker_colors, line=dict(width=1)),
        text=hover,
        hoverinfo="text",
        showlegend=False,
    ))

    fig.update_layout(
        scene=dict(
            xaxis=dict(title="Price", type="log" if use_log_price else "linear"),
            yaxis=dict(title="Stock", type="log" if use_log_stock else "linear"),
            zaxis=dict(title="Margin (M)", type="log" if use_log_margin else "linear"),
        ),
        margin=dict(l=0, r=0, b=0, t=0),
        height=420,
        showlegend=False,
    )
    return fig
