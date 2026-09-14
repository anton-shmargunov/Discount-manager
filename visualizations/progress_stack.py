"""
Switch-driven vertical weekly-progress stack.

Kept as its own module so Streamlit Cloud can load it even when
visualizations/sumup_charts.py is served from an older snapshot.
"""

from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots


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
