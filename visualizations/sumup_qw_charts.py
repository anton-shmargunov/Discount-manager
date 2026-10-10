"""
Sum-Up Total chart builders with Basket Detail display options:
Line + Symbol, Colour by Quadweek, and QW Average.

Kept as its own module so Streamlit Cloud can load it even when
visualizations/sumup_charts.py is served from an older snapshot.
"""

from __future__ import annotations

from typing import Optional

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from configs.settings import UNCLUSTERED_COLOR
from core.models import Linefit, Planefit
from core.transforms.metric_filters import finite_minmax
from visualizations.detail_charts import (
    add_qw_average_markers_2d,
    add_qw_average_markers_3d,
    marker_colors_for_points,
    qw_color_map,
    qw_index_spans,
    qw_value_averages,
)
from visualizations.sumup_charts import _add_sumup_plane_surface


def sumup_quadweeks(sumup_rows: list[dict]) -> list[str]:
    return [str(r.get("quadweek", "N/A")) for r in sumup_rows]


def _qw_hline_traces(
    week_labels: list[str],
    values: list[float],
    quadweeks: list[str],
    *,
    line_color: Optional[str] = None,
    yaxis: Optional[str] = None,
    label: str = "Average",
) -> list[go.Scatter]:
    """One horizontal segment per quadweek block at the within-QW average."""
    if not values or len(values) != len(quadweeks) or len(week_labels) != len(values):
        return []
    avgs = qw_value_averages(values, quadweeks)
    cmap = qw_color_map(quadweeks)
    traces: list[go.Scatter] = []
    for qw, start, end in qw_index_spans(quadweeks):
        avg = avgs.get(qw)
        if avg is None:
            continue
        kwargs = {"yaxis": yaxis} if yaxis else {}
        traces.append(go.Scatter(
            x=[week_labels[start], week_labels[end]],
            y=[avg, avg],
            mode="lines",
            line=dict(color=line_color or cmap.get(qw, UNCLUSTERED_COLOR), width=2, dash="dash"),
            hovertemplate=f"QW {qw}<br>{label}: %{{y:,.2f}}<extra></extra>",
            showlegend=False,
            **kwargs,
        ))
    return traces


def build_sumup_3panel_qw(
    sumup_rows: list[dict],
    show_line: bool = False,
    use_qw_colors: bool = False,
    show_qw_average: bool = False,
    margin_key: str = "total_m",
    margin_title: str = "Total M",
) -> go.Figure:
    """Total Sold vs W. Price · Margin vs W. Price · Margin vs Total Sold."""
    quadweeks = sumup_quadweeks(sumup_rows)
    wp = [r["weighted_price"] for r in sumup_rows]
    sold = [r["total_sold"] for r in sumup_rows]
    margin = [r.get(margin_key, r["total_m"]) for r in sumup_rows]
    hover = [f"Week: {r['week']} (QW: {r.get('quadweek', 'N/A')})" for r in sumup_rows]
    mode = "lines+markers" if show_line else "markers"

    fig = make_subplots(rows=1, cols=3, subplot_titles=[
        "Total Sold vs W. Price",
        f"{margin_title} vs W. Price",
        f"{margin_title} vs Total Sold",
    ])
    panels = [
        (wp, sold, "rgba(59,130,246,0.75)", "W. Price", "Total Sold"),
        (wp, margin, "rgba(16,185,129,0.75)", "W. Price", margin_title),
        (sold, margin, "rgba(139,92,246,0.75)", "Total Sold", margin_title),
    ]
    for col, (xs, ys, color, x_label, y_label) in enumerate(panels, start=1):
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode=mode,
            text=hover, hoverinfo="text",
            marker=dict(
                color=marker_colors_for_points(quadweeks, use_qw_colors, color),
                size=7,
                line=dict(width=0.5, color="#111827"),
            ),
            line=dict(color=color, width=2),
            showlegend=False,
        ), row=1, col=col)
        if show_qw_average:
            add_qw_average_markers_2d(
                fig, xs, ys, quadweeks, row=1, col=col, x_label=x_label, y_label=y_label,
            )
        fig.update_xaxes(title_text=x_label, row=1, col=col)
        fig.update_yaxes(title_text=y_label, row=1, col=col)

    fig.update_layout(height=320, margin=dict(l=40, r=20, t=50, b=40))
    return fig


def build_sumup_cost_vs_price_qw(
    sumup_rows: list[dict],
    show_line: bool = False,
    use_qw_colors: bool = False,
    show_qw_average: bool = False,
    linefit: Optional[Linefit] = None,
    fitted_indices: Optional[list[int]] = None,
) -> go.Figure:
    """Total Cost vs W. Price with optional fitted line."""
    quadweeks = sumup_quadweeks(sumup_rows)
    wp = [r["weighted_price"] for r in sumup_rows]
    total_cost = [r["total_cost"] for r in sumup_rows]
    base_color = "rgba(6,182,212,0.75)"
    texts = [
        f"Week: {r['week']}<br>QW: {r.get('quadweek', 'N/A')}<br>"
        f"W. Price: {r['weighted_price']:.2f}<br>Total Cost: {r['total_cost']:.2f}"
        for r in sumup_rows
    ]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=wp,
        y=total_cost,
        mode="lines+markers" if show_line else "markers",
        marker=dict(
            size=7,
            color=marker_colors_for_points(
                quadweeks, use_qw_colors, base_color, highlight_indices=fitted_indices,
            ),
            line=dict(width=0.5, color="#111827"),
        ),
        line=dict(color=base_color, width=2),
        text=texts,
        hoverinfo="text",
        showlegend=False,
    ))
    if show_qw_average:
        add_qw_average_markers_2d(
            fig, wp, total_cost, quadweeks, x_label="W. Price", y_label="Total Cost",
        )

    if linefit is not None and wp:
        x_min, x_max = finite_minmax(wp)
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


def _sumup_scatter3d(
    xs: list[float],
    ys: list[float],
    zs: list[float],
    quadweeks: list[str],
    texts: list[str],
    *,
    show_line: bool,
    use_qw_colors: bool,
    base_color: str,
    line_color: str,
    highlight_indices: Optional[list[int]] = None,
) -> go.Scatter3d:
    return go.Scatter3d(
        x=xs, y=ys, z=zs,
        mode="lines+markers" if show_line else "markers",
        marker=dict(
            size=5,
            color=marker_colors_for_points(
                quadweeks, use_qw_colors, base_color, highlight_indices=highlight_indices,
            ),
        ),
        line=dict(color=line_color, width=3),
        text=texts,
        hoverinfo="text",
    )


def build_sumup_3d_qw(
    sumup_rows: list[dict],
    show_line: bool = False,
    use_qw_colors: bool = False,
    show_qw_average: bool = False,
    margin_key: str = "total_m",
    margin_title: str = "Total M",
) -> go.Figure:
    """3D: W. Price × Total Sold × Margin."""
    quadweeks = sumup_quadweeks(sumup_rows)
    wp = [r["weighted_price"] for r in sumup_rows]
    sold = [r["total_sold"] for r in sumup_rows]
    margin = [r.get(margin_key, r["total_m"]) for r in sumup_rows]
    texts = [
        f"Week: {r['week']} (QW: {r.get('quadweek', 'N/A')})<br>W. Price: {r['weighted_price']:.2f}<br>"
        f"Total Sold: {r['total_sold']:.2f}<br>{margin_title}: {m:.2f}"
        for r, m in zip(sumup_rows, margin)
    ]
    fig = go.Figure(_sumup_scatter3d(
        wp, sold, margin, quadweeks, texts,
        show_line=show_line, use_qw_colors=use_qw_colors,
        base_color="rgba(59,130,246,0.8)", line_color="rgb(37,99,235)",
    ))
    if show_qw_average:
        add_qw_average_markers_3d(
            fig, wp, sold, margin, quadweeks,
            x_label="W. Price", y_label="Total Sold", z_label=margin_title,
        )
    fig.update_layout(
        scene=dict(xaxis_title="W. Price", yaxis_title="Total Sold", zaxis_title=margin_title),
        margin=dict(l=0, r=0, b=0, t=0), height=420, showlegend=False,
    )
    return fig


def build_sumup_stock_sold_3d_qw(
    sumup_rows: list[dict],
    show_line: bool = False,
    use_qw_colors: bool = False,
    show_qw_average: bool = False,
    planefit: Optional[Planefit] = None,
    fitted_indices: Optional[list[int]] = None,
) -> go.Figure:
    """3D: W. Price × Total Stock × Total Sold with optional fitted plane."""
    quadweeks = sumup_quadweeks(sumup_rows)
    wp = [r["weighted_price"] for r in sumup_rows]
    stock = [r["total_stock"] for r in sumup_rows]
    sold = [r["total_sold"] for r in sumup_rows]
    texts = [
        f"Week: {r['week']} (QW: {r.get('quadweek', 'N/A')})<br>W. Price: {r['weighted_price']:.2f}<br>"
        f"Total Stock: {r['total_stock']:.2f}<br>Total Sold: {r['total_sold']:.2f}"
        for r in sumup_rows
    ]
    fig = go.Figure(_sumup_scatter3d(
        wp, stock, sold, quadweeks, texts,
        show_line=show_line, use_qw_colors=use_qw_colors,
        base_color="rgba(236,72,153,0.8)", line_color="rgb(219,39,119)",
        highlight_indices=fitted_indices,
    ))
    if show_qw_average:
        add_qw_average_markers_3d(
            fig, wp, stock, sold, quadweeks,
            x_label="W. Price", y_label="Total Stock", z_label="Total Sold",
        )
    if planefit is not None:
        _add_sumup_plane_surface(fig, wp, stock, planefit, "rgba(59,130,246,0.4)")
    fig.update_layout(
        scene=dict(xaxis_title="W. Price", yaxis_title="Total Stock", zaxis_title="Total Sold"),
        margin=dict(l=0, r=0, b=0, t=0), height=420, showlegend=False,
    )
    return fig


def build_sumup_stock_m_3d_qw(
    sumup_rows: list[dict],
    show_line: bool = False,
    use_qw_colors: bool = False,
    show_qw_average: bool = False,
    margin_surface: Optional[tuple[list[float], list[float], list[list[float]]]] = None,
    margin_key: str = "total_m",
    margin_title: str = "Total Margin",
) -> go.Figure:
    """3D: W. Price × Total Stock × Margin with optional analytical surface."""
    quadweeks = sumup_quadweeks(sumup_rows)
    wp = [r["weighted_price"] for r in sumup_rows]
    stock = [r["total_stock"] for r in sumup_rows]
    margin = [r.get(margin_key, r["total_m"]) for r in sumup_rows]
    texts = [
        f"Week: {r['week']} (QW: {r.get('quadweek', 'N/A')})<br>W. Price: {r['weighted_price']:.2f}<br>"
        f"Total Stock: {r['total_stock']:.2f}<br>{margin_title}: {m:.2f}"
        for r, m in zip(sumup_rows, margin)
    ]
    fig = go.Figure(_sumup_scatter3d(
        wp, stock, margin, quadweeks, texts,
        show_line=show_line, use_qw_colors=use_qw_colors,
        base_color="rgba(139,92,246,0.8)", line_color="rgb(109,40,217)",
    ))
    if show_qw_average:
        add_qw_average_markers_3d(
            fig, wp, stock, margin, quadweeks,
            x_label="W. Price", y_label="Total Stock", z_label=margin_title,
        )
    if margin_surface is not None:
        price_grid, stock_grid, m_grid = margin_surface
        fig.add_trace(go.Surface(
            x=price_grid, y=stock_grid, z=m_grid,
            opacity=0.75, colorscale="Viridis", showscale=False,
            hoverinfo="none", name="Analytical M Model",
        ))
    fig.update_layout(
        scene=dict(xaxis_title="W. Price", yaxis_title="Total Stock", zaxis_title=margin_title),
        margin=dict(l=0, r=0, b=0, t=0), height=420, showlegend=False,
    )
    return fig


def build_combined_progress_qw(
    weeks: list[str],
    stock_totals: list[float],
    weighted_prices: list[float],
    total_sold: list[float],
    total_margin: list[float],
    show_line: bool = False,
    total_margin_corrected: list[float] | None = None,
    quadweeks: list[str] | None = None,
    use_qw_colors: bool = False,
    show_qw_average: bool = False,
) -> go.Figure:
    """Combined weekly progress with four y-axes.

    Quadweek colours fill the markers; the marker outline and line keep the
    metric colour so each series stays identifiable.
    """
    week_labels = [str(week) for week in weeks]
    qws = list(quadweeks) if quadweeks and len(quadweeks) == len(week_labels) else None
    mode = "lines+markers" if show_line else "markers"
    metrics = [
        ("Total Stock", stock_totals, "y", "rgb(219,39,119)", "circle"),
        ("W. Price", weighted_prices, "y2", "rgb(5,150,105)", "circle"),
        ("Total Sold", total_sold, "y3", "rgb(37,99,235)", "circle"),
        ("Total Margin", total_margin, "y4", "rgb(109,40,217)", "circle"),
    ]
    if total_margin_corrected is not None and len(total_margin_corrected) == len(week_labels):
        metrics.append(
            ("Total Margin Corrected", total_margin_corrected, "y4", "rgb(220,38,38)", "diamond")
        )

    fig = go.Figure()
    for name, values, axis, color, symbol in metrics:
        fill = (
            marker_colors_for_points(qws, True, color)
            if use_qw_colors and qws is not None
            else color
        )
        fig.add_trace(go.Scatter(
            x=week_labels,
            y=values,
            mode=mode,
            name=name,
            yaxis=axis,
            marker=dict(color=fill, size=8, symbol=symbol, line=dict(width=1.5, color=color)),
            line=dict(color=color, width=2, dash="dash" if symbol == "diamond" else "solid"),
            hovertemplate="Week: %{x}<br>" + f"{name}: " + "%{y:,.2f}<extra></extra>",
        ))
        if show_qw_average and qws is not None:
            for trace in _qw_hline_traces(
                week_labels, list(values), qws, line_color=color, yaxis=axis,
                label=f"{name} average",
            ):
                fig.add_trace(trace)

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
            anchor="free", overlaying="y", side="right", position=1.0,
        ),
        yaxis3=dict(
            title=dict(text="Total Sold", font=dict(color="rgb(37,99,235)")),
            tickfont=dict(color="rgb(37,99,235)"),
            anchor="free", overlaying="y", side="left", position=0.05,
        ),
        yaxis4=dict(
            title=dict(text="Total Margin", font=dict(color="rgb(109,40,217)")),
            tickfont=dict(color="rgb(109,40,217)"),
            anchor="free", overlaying="y", side="right", position=0.95,
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=520,
        margin=dict(l=80, r=90, t=80, b=90),
    )
    return fig


def build_vertical_stack_from_specs_qw(
    weeks: list[str],
    specs: list[dict],
    show_line: bool = False,
    quadweeks: list[str] | None = None,
    use_qw_colors: bool = False,
    show_qw_average: bool = False,
) -> go.Figure:
    """Vertically stacked weekly progress plots driven by metric specs."""
    week_labels = [str(week) for week in weeks]
    qws = list(quadweeks) if quadweeks and len(quadweeks) == len(week_labels) else None
    qw_markers = use_qw_colors and qws is not None
    if show_line:
        trace_mode = "lines+markers"
    else:
        trace_mode = "lines+markers" if qw_markers else "lines"
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
        marker_color = spec.get("marker_color", "rgba(59,130,246,0.75)")
        values = list(spec["values"])
        fig.add_trace(
            go.Scatter(
                x=week_labels,
                y=values,
                name=name,
                mode=trace_mode,
                marker=dict(
                    color=marker_colors_for_points(qws, True, marker_color) if qw_markers else marker_color,
                    size=7,
                    line=dict(width=0.5, color="#111827"),
                ),
                line=dict(color=spec.get("line_color", "rgb(37,99,235)"), width=2),
                hovertemplate="Week: %{x}<br>" + f"{name}: " + "%{y:,.2f}<extra></extra>",
            ),
            row=idx,
            col=1,
        )
        if show_qw_average and qws is not None:
            for trace in _qw_hline_traces(week_labels, values, qws, label=f"{name} average"):
                fig.add_trace(trace, row=idx, col=1)
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
                    hovertemplate="Week: %{x}<br>" + f"{overlay_name}: " + "%{y:,.2f}<extra></extra>",
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
