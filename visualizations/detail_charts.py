"""
Reusable Plotly chart builders for basket drill-down views.

All functions return Plotly Figure objects — no Streamlit imports.
"""

from __future__ import annotations
import math
from collections import defaultdict

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.models import BasketTimeSeries, Planefit, Linefit
from configs.settings import CLUSTER_COLORS, UNCLUSTERED_COLOR


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def normalize_quadweek(value: object) -> str:
    """Normalize quadweek labels so map lookups stay consistent."""
    if value is None:
        return "N/A"
    text = str(value).strip()
    if not text or text.lower() in {"n/a", "nan", "none"}:
        return "N/A"
    try:
        numeric = float(text)
        if numeric == int(numeric):
            return str(int(numeric))
    except ValueError:
        pass
    return text


def qw_color_map(quadweeks: list[str]) -> dict[str, str]:
    """Assign a distinct color to each unique quadweek value."""
    unique_qws = sorted({
        normalize_quadweek(q)
        for q in quadweeks
        if normalize_quadweek(q) != "N/A"
    })
    return {
        qw: CLUSTER_COLORS[i % len(CLUSTER_COLORS)]
        for i, qw in enumerate(unique_qws)
    }


def marker_colors_for_points(
    quadweeks: list[str],
    use_qw_colors: bool,
    default_color: str,
    highlight_indices: list[int] | None = None,
) -> list[str]:
    """Per-point colors with optional manual-selection highlighting."""
    if highlight_indices is not None:
        selected = set(highlight_indices)
        if use_qw_colors:
            qw_colors = marker_colors_for_points(quadweeks, True, default_color)
            return [
                qw_colors[i] if i in selected else "rgba(200,200,200,0.35)"
                for i in range(len(quadweeks))
            ]
        return [
            "rgba(239,68,68,1)" if i in selected else "rgba(200,200,200,0.35)"
            for i in range(len(quadweeks))
        ]

    if not use_qw_colors:
        return [default_color] * len(quadweeks)

    cmap = qw_color_map(quadweeks)
    return [
        cmap.get(normalize_quadweek(q), UNCLUSTERED_COLOR)
        for q in quadweeks
    ]


def _point_colors(
    quadweeks: list[str],
    use_qw_colors: bool,
    default_color: str,
) -> list[str]:
    return marker_colors_for_points(quadweeks, use_qw_colors, default_color)


def qw_index_groups(quadweeks: list[str]) -> dict[str, list[int]]:
    """Map normalized quadweek -> point indices."""
    groups: dict[str, list[int]] = defaultdict(list)
    for idx, qw in enumerate(quadweeks):
        key = normalize_quadweek(qw)
        if key != "N/A":
            groups[key].append(idx)
    return dict(groups)


def qw_index_spans(quadweeks: list[str]) -> list[tuple[str, int, int]]:
    """Contiguous quadweek blocks in chronological order."""
    if not quadweeks:
        return []

    spans: list[tuple[str, int, int]] = []
    start = 0
    current = normalize_quadweek(quadweeks[0])
    for idx in range(1, len(quadweeks)):
        qw = normalize_quadweek(quadweeks[idx])
        if qw != current:
            if current != "N/A":
                spans.append((current, start, idx - 1))
            start = idx
            current = qw
    if current != "N/A":
        spans.append((current, start, len(quadweeks) - 1))
    return spans


def qw_value_averages(values: list[float], quadweeks: list[str]) -> dict[str, float]:
    """Mean metric value for each quadweek (non-finite points skipped)."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for value, qw in zip(values, quadweeks):
        key = normalize_quadweek(qw)
        if key == "N/A":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(number) or math.isinf(number):
            continue
        buckets[key].append(number)
    return {qw: float(np.mean(vs)) for qw, vs in buckets.items() if vs}


def add_qw_average_hlines(
    fig: go.Figure,
    week_labels: list[str],
    values: list[float],
    quadweeks: list[str],
    *,
    dash: str = "dash",
    line_color: str | None = None,
    line_width: int = 2,
    name: str = "",
    hover_label: str = "Average",
    legend_once: bool = False,
) -> None:
    """Horizontal segment per quadweek at the within-QW average."""
    if not values or len(values) != len(quadweeks):
        return

    avgs = qw_value_averages(values, quadweeks)
    cmap = qw_color_map(quadweeks)
    legend_shown = False
    for qw, start, end in qw_index_spans(quadweeks):
        avg = avgs.get(qw)
        if avg is None:
            continue
        color = line_color or cmap.get(qw, UNCLUSTERED_COLOR)
        showlegend = bool(legend_once and name and not legend_shown)
        fig.add_trace(
            go.Scatter(
                x=[week_labels[start], week_labels[end]],
                y=[avg, avg],
                mode="lines",
                name=name if showlegend else None,
                line=dict(color=color, width=line_width, dash=dash),
                hovertemplate=f"QW {qw}<br>{hover_label}: %{{y:.2f}}<extra></extra>",
                showlegend=showlegend,
            )
        )
        if showlegend:
            legend_shown = True


def add_qw_average_markers_2d(
    fig: go.Figure,
    xs: list[float],
    ys: list[float],
    quadweeks: list[str],
    *,
    row: int | None = None,
    col: int | None = None,
    x_label: str = "X",
    y_label: str = "Y",
) -> None:
    """Diamond marker at the within-QW average for each axis pair."""
    if not xs or len(xs) != len(ys) or len(xs) != len(quadweeks):
        return

    cmap = qw_color_map(quadweeks)
    trace_kwargs: dict = {}
    if row is not None and col is not None:
        trace_kwargs = {"row": row, "col": col}

    for qw, indices in sorted(qw_index_groups(quadweeks).items()):
        avg_x = float(np.mean([xs[i] for i in indices]))
        avg_y = float(np.mean([ys[i] for i in indices]))
        color = cmap.get(qw, UNCLUSTERED_COLOR)
        fig.add_trace(
            go.Scatter(
                x=[avg_x],
                y=[avg_y],
                mode="markers",
                marker=dict(
                    symbol="diamond",
                    size=11,
                    color=color,
                    line=dict(width=1.2, color="#111827"),
                ),
                hovertemplate=(
                    f"QW {qw}<br>{x_label}: %{{x:.2f}}<br>"
                    f"{y_label}: %{{y:.2f}}<extra></extra>"
                ),
                showlegend=False,
            ),
            **trace_kwargs,
        )


def add_qw_average_markers_3d(
    fig: go.Figure,
    xs: list[float],
    ys: list[float],
    zs: list[float],
    quadweeks: list[str],
    *,
    x_label: str = "X",
    y_label: str = "Y",
    z_label: str = "Z",
) -> None:
    """Diamond marker at the within-QW average for each 3D axis triplet."""
    if not xs or not (len(xs) == len(ys) == len(zs) == len(quadweeks)):
        return

    cmap = qw_color_map(quadweeks)
    for qw, indices in sorted(qw_index_groups(quadweeks).items()):
        avg_x = float(np.mean([xs[i] for i in indices]))
        avg_y = float(np.mean([ys[i] for i in indices]))
        avg_z = float(np.mean([zs[i] for i in indices]))
        color = cmap.get(qw, UNCLUSTERED_COLOR)
        fig.add_trace(
            go.Scatter3d(
                x=[avg_x],
                y=[avg_y],
                z=[avg_z],
                mode="markers",
                marker=dict(
                    symbol="diamond",
                    size=5,
                    color=color,
                    line=dict(width=1.2, color="#111827"),
                ),
                hovertemplate=(
                    f"QW {qw}<br>{x_label}: %{{x:.2f}}<br>"
                    f"{y_label}: %{{y:.2f}}<br>"
                    f"{z_label}: %{{z:.2f}}<extra></extra>"
                ),
                showlegend=False,
            )
        )


def _add_colored_scatter_trace(
    fig: go.Figure,
    xs: list[float],
    ys: list[float],
    hover: list[str],
    quadweeks: list[str],
    *,
    row: int,
    col: int,
    default_color: str,
    use_qw_colors: bool,
    show_line: bool,
) -> None:
    """Single connected trace: quadweek colours on markers only, one line colour."""
    mode = "lines+markers" if show_line else "markers"
    marker_colors = marker_colors_for_points(quadweeks, use_qw_colors, default_color)

    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode=mode,
            text=hover,
            hoverinfo="text",
            marker=dict(
                color=marker_colors,
                size=7,
                line=dict(width=0.5, color="#111827"),
            ),
            line=dict(color=default_color, width=2),
            showlegend=False,
        ),
        row=row,
        col=col,
    )


# ---------------------------------------------------------------------------
# 4-panel basket scatter row
# ---------------------------------------------------------------------------

def build_basket_scatter_3panel(
    ts: BasketTimeSeries,
    use_qw_colors: bool = False,
    show_line: bool = False,
    show_qw_average: bool = False,
    margin_values: list[float] | None = None,
) -> go.Figure:
    """
    3-panel scatter chart for a basket:
    1) Sold vs Price   2) M vs Price   3) M vs Sold
    """
    m_values = list(margin_values) if margin_values is not None else list(ts.m)
    hover = [
        f"Week: {ts.weeks[i]} (QW: {ts.quadweeks[i]})<br>"
        f"Price: {ts.price[i]:.2f} | Sold: {ts.sold[i]:.2f}<br>"
        f"M: {m_values[i]:.2f} | Stock: {ts.stock[i]:.2f}"
        for i in range(ts.n_weeks)
    ]

    fig = make_subplots(rows=1, cols=3, subplot_titles=[
        "Sold vs Price", "Margin vs Price", "Margin vs Sold",
    ])

    panels = [
        (ts.price, ts.sold, "rgba(59,130,246,0.75)", "Avg Price", "Sold Qty"),
        (ts.price, m_values, "rgba(16,185,129,0.75)", "Avg Price", "Margin"),
        (ts.sold, m_values, "rgba(139,92,246,0.75)", "Sold Qty", "Margin"),
    ]
    for col_idx, (xs, ys, default_color, x_label, y_label) in enumerate(panels, start=1):
        _add_colored_scatter_trace(
            fig,
            xs,
            ys,
            hover,
            ts.quadweeks,
            row=1,
            col=col_idx,
            default_color=default_color,
            use_qw_colors=use_qw_colors,
            show_line=show_line,
        )
        if show_qw_average:
            add_qw_average_markers_2d(
                fig,
                xs,
                ys,
                ts.quadweeks,
                row=1,
                col=col_idx,
                x_label=x_label,
                y_label=y_label,
            )

    fig.update_xaxes(title_text="Avg Price", row=1, col=1)
    fig.update_yaxes(title_text="Sold Qty", row=1, col=1)
    fig.update_xaxes(title_text="Avg Price", row=1, col=2)
    fig.update_yaxes(title_text="Margin", row=1, col=2)
    fig.update_xaxes(title_text="Sold Qty", row=1, col=3)
    fig.update_yaxes(title_text="Margin", row=1, col=3)

    fig.update_layout(
        height=320,
        margin=dict(l=40, r=20, t=50, b=60),
    )
    return fig


def build_basket_scatter_4panel(
    ts: BasketTimeSeries,
    use_qw_colors: bool = False,
    show_line: bool = False,
    show_qw_average: bool = False,
) -> go.Figure:
    """Backward-compatible alias for the 3-panel correlation scatter row."""
    return build_basket_scatter_3panel(
        ts,
        use_qw_colors=use_qw_colors,
        show_line=show_line,
        show_qw_average=show_qw_average,
    )


# ---------------------------------------------------------------------------
# Cost vs Price 2D chart
# ---------------------------------------------------------------------------

def build_cost_vs_price(
    ts: BasketTimeSeries,
    use_qw_colors: bool = False,
    show_line: bool = False,
    linefit: Linefit | None = None,
    fitted_indices: list[int] | None = None,
    show_qw_average: bool = False,
) -> go.Figure:
    """Scatter of Cost vs Price with optional fitted line."""
    hover = [
        f"Week: {ts.weeks[i]} (QW: {ts.quadweeks[i]})<br>"
        f"Price: {ts.price[i]:.2f} | Cost: {ts.cost[i]:.2f}"
        for i in range(ts.n_weeks)
    ]
    colors = marker_colors_for_points(
        ts.quadweeks,
        use_qw_colors,
        "rgba(6,182,212,0.75)",
        highlight_indices=fitted_indices,
    )
    mode = "lines+markers" if show_line else "markers"
    line_color = "rgba(6,182,212,0.75)"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ts.price, y=ts.cost,
        mode=mode, name="Cost vs Price",
        text=hover, hoverinfo="text",
        marker=dict(color=colors, size=7, line=dict(width=0.5, color="#111827")),
        line=dict(color=line_color, width=2),
        showlegend=False,
    ))

    if show_qw_average:
        add_qw_average_markers_2d(
            fig,
            ts.price,
            ts.cost,
            ts.quadweeks,
            x_label="Avg Price",
            y_label="Cost per Unit",
        )

    if linefit is not None:
        x_min, x_max = min(ts.price), max(ts.price)
        pad = (x_max - x_min) * 0.1 or 1.0
        x0, x1 = x_min - pad, x_max + pad
        fig.add_trace(go.Scatter(
            x=[x0, x1],
            y=[linefit.z0 + linefit.a * x0, linefit.z0 + linefit.a * x1],
            mode="lines", name="Fitted Line",
            line=dict(color="rgba(239,68,68,1)", width=2, dash="dash"),
        ))

    fig.update_layout(
        xaxis_title="Avg Price", yaxis_title="Cost per Unit",
        title="Cost vs Price",
        height=420, margin=dict(l=50, r=20, t=50, b=50),
    )
    return fig


# ---------------------------------------------------------------------------
# 3D basket detail charts
# ---------------------------------------------------------------------------

def build_3d_price_sold_m(
    ts: BasketTimeSeries,
    use_qw_colors: bool = False,
    show_line: bool = False,
    show_qw_average: bool = False,
    m_values: list[float] | None = None,
) -> go.Figure:
    """3D scatter: Price × Sold × M (time-labelled)."""
    z_values = list(m_values) if m_values is not None else list(ts.m)
    colors = marker_colors_for_points(
        ts.quadweeks,
        use_qw_colors,
        "rgba(59,130,246,0.8)",
    )
    mode = "lines+markers" if show_line else "markers"
    line_color = "rgb(37,99,235)"

    fig = go.Figure(go.Scatter3d(
        x=ts.price, y=ts.sold, z=z_values,
        mode=mode,
        marker=dict(size=6, color=colors),
        line=dict(color=line_color, width=3),
        text=[
            f"Week: {ts.weeks[i]} (QW: {ts.quadweeks[i]})<br>"
            f"Price: {ts.price[i]:.2f} | Sold: {ts.sold[i]:.2f} | M: {z_values[i]:.2f}"
            for i in range(ts.n_weeks)
        ],
        hoverinfo="text",
    ))
    if show_qw_average:
        add_qw_average_markers_3d(
            fig,
            ts.price,
            ts.sold,
            z_values,
            ts.quadweeks,
            x_label="Price",
            y_label="Sold",
            z_label="M",
        )
    fig.update_layout(
        scene=dict(xaxis_title="Price", yaxis_title="Sold", zaxis_title="M"),
        margin=dict(l=0, r=0, b=0, t=0), height=420, showlegend=False,
    )
    return fig


def build_3d_price_stock_sold(
    ts: BasketTimeSeries,
    use_qw_colors: bool = False,
    show_line: bool = False,
    planefit: Planefit | None = None,
    fitted_indices: list[int] | None = None,
    show_qw_average: bool = False,
) -> go.Figure:
    """3D scatter: Price × Stock × Sold, with optional fitted plane."""
    colors = marker_colors_for_points(
        ts.quadweeks,
        use_qw_colors,
        "rgba(139,92,246,0.8)",
        highlight_indices=fitted_indices,
    )
    mode = "lines+markers" if show_line else "markers"
    line_color = "rgb(109,40,217)"

    fig = go.Figure(go.Scatter3d(
        x=ts.price, y=ts.stock, z=ts.sold,
        mode=mode,
        marker=dict(size=6, color=colors),
        line=dict(color=line_color, width=3),
        text=[
            f"Week: {ts.weeks[i]} (QW: {ts.quadweeks[i]})<br>"
            f"Price: {ts.price[i]:.2f} | Stock: {ts.stock[i]:.2f} | Sold: {ts.sold[i]:.2f}"
            for i in range(ts.n_weeks)
        ],
        hoverinfo="text",
    ))

    if show_qw_average:
        add_qw_average_markers_3d(
            fig,
            ts.price,
            ts.stock,
            ts.sold,
            ts.quadweeks,
            x_label="Price",
            y_label="Stock",
            z_label="Sold",
        )

    if planefit is not None:
        _add_plane_surface(fig, ts.price, ts.stock, planefit, "rgba(59,130,246,0.4)")

    fig.update_layout(
        scene=dict(xaxis_title="Price", yaxis_title="Stock", zaxis_title="Sold"),
        margin=dict(l=0, r=0, b=0, t=0), height=460, showlegend=False,
    )
    return fig


def build_3d_price_stock_m(
    ts: BasketTimeSeries,
    use_qw_colors: bool = False,
    show_line: bool = False,
    planefit: Planefit | None = None,
    margin_surface: tuple[list[float], list[float], list[list[float]]] | None = None,
    show_qw_average: bool = False,
    m_values: list[float] | None = None,
) -> go.Figure:
    """3D scatter: Price × Stock × M, with optional fitted and analytical surfaces."""
    z_values = list(m_values) if m_values is not None else list(ts.m)
    colors = marker_colors_for_points(
        ts.quadweeks,
        use_qw_colors,
        "rgba(236,72,153,0.8)",
    )
    mode = "lines+markers" if show_line else "markers"
    line_color = "rgb(219,39,119)"

    fig = go.Figure(go.Scatter3d(
        x=ts.price, y=ts.stock, z=z_values,
        mode=mode,
        marker=dict(size=6, color=colors),
        line=dict(color=line_color, width=3),
        text=[
            f"Week: {ts.weeks[i]} (QW: {ts.quadweeks[i]})<br>"
            f"Price: {ts.price[i]:.2f} | Stock: {ts.stock[i]:.2f} | M: {z_values[i]:.2f}"
            for i in range(ts.n_weeks)
        ],
        hoverinfo="text",
    ))

    if show_qw_average:
        add_qw_average_markers_3d(
            fig,
            ts.price,
            ts.stock,
            z_values,
            ts.quadweeks,
            x_label="Price",
            y_label="Stock",
            z_label="M",
        )

    if planefit is not None:
        _add_plane_surface(fig, ts.price, ts.stock, planefit, "rgba(236,72,153,0.4)")

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
        scene=dict(xaxis_title="Price", yaxis_title="Stock", zaxis_title="M"),
        margin=dict(l=0, r=0, b=0, t=0), height=460, showlegend=False,
    )
    return fig


def _add_plane_surface(
    fig: go.Figure,
    x: list[float],
    y: list[float],
    fit: Planefit,
    surface_color: str,
) -> None:
    """Add a flat surface patch representing a fitted plane to an existing figure."""
    x_pad = (max(x) - min(x)) * 0.1 or 1.0
    y_pad = (max(y) - min(y)) * 0.1 or 1.0
    x0, x1 = min(x) - x_pad, max(x) + x_pad
    y0, y1 = min(y) - y_pad, max(y) + y_pad

    z_grid = [
        [fit.z0 + fit.a * x0 + fit.b * y0, fit.z0 + fit.a * x1 + fit.b * y0],
        [fit.z0 + fit.a * x0 + fit.b * y1, fit.z0 + fit.a * x1 + fit.b * y1],
    ]

    fig.add_trace(go.Surface(
        x=[x0, x1], y=[y0, y1], z=z_grid,
        opacity=0.6,
        colorscale=[[0, surface_color], [1, surface_color]],
        showscale=False, hoverinfo="none",
        name="Fit Plane",
    ))


# ---------------------------------------------------------------------------
# Price_max vs Stock curve
# ---------------------------------------------------------------------------

def build_price_max_curve(
    stock_values: list[float],
    price_max_values: list[float],
) -> go.Figure:
    """Line chart: optimal price (Price_max) as a function of stock level."""
    fig = go.Figure(go.Scatter(
        x=stock_values,
        y=price_max_values,
        mode="lines",
        line=dict(color="rgba(147,51,234,1)", width=2),
        fill="tozeroy",
        fillcolor="rgba(147,51,234,0.1)",
        name="Price_max",
    ))
    fig.update_layout(
        xaxis_title="Stock Quantity",
        yaxis_title="Optimal Price (Price_max)",
        title="Price_max vs Stock",
        height=280,
        margin=dict(l=50, r=20, t=50, b=50),
        showlegend=False,
    )
    return fig
