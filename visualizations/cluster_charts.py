"""
Reusable Plotly chart builders for correlation cluster views.

All functions return Plotly Figure objects — no Streamlit imports.
"""

from __future__ import annotations
import math
import plotly.graph_objects as go
from core.models import BasketResult
from configs.settings import (
    CLUSTER_COLORS,
    CLUSTER_BORDER_COLORS,
    UNCLUSTERED_COLOR,
    UNCLUSTERED_BORDER,
)


def _group_baskets(
    baskets: list[BasketResult],
    k: int,
) -> dict[int, list[BasketResult]]:
    """Partition baskets by group index (0 = unclustered)."""
    groups: dict[int, list[BasketResult]] = {}
    for b in baskets:
        groups.setdefault(b.group, []).append(b)
    return groups


def _get_color(group: int) -> str:
    if group == 0:
        return UNCLUSTERED_COLOR
    return CLUSTER_COLORS[(group - 1) % len(CLUSTER_COLORS)]


def _get_border(group: int) -> str:
    if group == 0:
        return UNCLUSTERED_BORDER
    return CLUSTER_BORDER_COLORS[(group - 1) % len(CLUSTER_BORDER_COLORS)]


def _group_label(group: int, k: int, labels: list[str] | None) -> str:
    if group == 0:
        return "All Baskets" if k == 0 else "Unclustered"
    if labels and 1 <= group <= len(labels):
        return labels[group - 1]
    return f"Group {group}"


# ---------------------------------------------------------------------------
# 2D Cluster Scatter (corr_SP vs corr_MS)
# ---------------------------------------------------------------------------

def build_2d_cluster_scatter(
    baskets: list[BasketResult],
    k: int = 0,
    labels: list[str] | None = None,
) -> go.Figure:
    """
    2D scatter plot of baskets coloured by cluster group.
    X: Corr(Sold, Price)  |  Y: Corr(M, Sold)
    """
    fig = go.Figure()
    groups = _group_baskets(baskets, k)

    for group, members in sorted(groups.items()):
        if not members:
            continue
        xs = [m.corr_SP_safe for m in members]
        ys = [m.corr_MS_safe for m in members]
        texts = [
            f"<b>{m.basket}</b><br>"
            f"Sold/Price: {'N/A' if math.isnan(m.corr_SP) else f'{m.corr_SP:.3f}'}<br>"
            f"M/Sold: {'N/A' if math.isnan(m.corr_MS) else f'{m.corr_MS:.3f}'}<br>"
            f"M/Price: {'N/A' if math.isnan(m.corr_MP) else f'{m.corr_MP:.3f}'}"
            for m in members
        ]
        color = _get_color(group)
        border = _get_border(group)

        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="markers",
            name=_group_label(group, k, labels),
            text=texts,
            hoverinfo="text",
            customdata=[m.basket for m in members],
            marker=dict(size=9, color=color, line=dict(color=border, width=1)),
        ))

    fig.update_layout(
        xaxis_title="Correlation: Sold vs Price",
        yaxis_title="Correlation: M vs Sold",
        legend=dict(orientation="v", x=1.01, y=1),
        margin=dict(l=50, r=150, t=30, b=50),
        height=380,
    )
    return fig


# ---------------------------------------------------------------------------
# 3D Cluster Scatter (corr_SP, corr_MP, corr_MS)
# ---------------------------------------------------------------------------

def build_3d_cluster_scatter(
    baskets: list[BasketResult],
    k: int = 0,
    labels: list[str] | None = None,
) -> go.Figure:
    """
    3D scatter plot of baskets in the correlation space.
    X: Sold/Price  |  Y: M/Price  |  Z: M/Sold
    """
    fig = go.Figure()
    groups = _group_baskets(baskets, k)

    for group, members in sorted(groups.items()):
        if not members:
            continue
        xs = [m.corr_SP_safe for m in members]
        ys = [m.corr_MP_safe for m in members]
        zs = [m.corr_MS_safe for m in members]
        texts = [
            f"<b>{m.basket}</b><br>"
            f"Sold/Price: {'N/A' if math.isnan(m.corr_SP) else f'{m.corr_SP:.3f}'}<br>"
            f"M/Price: {'N/A' if math.isnan(m.corr_MP) else f'{m.corr_MP:.3f}'}<br>"
            f"M/Sold: {'N/A' if math.isnan(m.corr_MS) else f'{m.corr_MS:.3f}'}"
            for m in members
        ]
        color = _get_color(group)
        border = _get_border(group)

        fig.add_trace(go.Scatter3d(
            x=xs, y=ys, z=zs,
            mode="markers",
            name=_group_label(group, k, labels),
            text=texts,
            hoverinfo="text",
            customdata=[m.basket for m in members],
            marker=dict(size=5, color=color, line=dict(color=border, width=1), opacity=1),
        ))

    fig.update_layout(
        scene=dict(
            xaxis_title="Sold vs Price",
            yaxis_title="M vs Price",
            zaxis_title="M vs Sold",
        ),
        margin=dict(l=0, r=0, b=0, t=0),
        legend=dict(x=0, y=1),
        height=500,
    )
    return fig
