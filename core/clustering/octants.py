"""
Octant clustering: assign each basket to one of 8 octants
based on the sign combination of (corr_SP, corr_MP, corr_MS).

Octant mapping (mirrors the JS prototype):
    1: (+, +, +)    5: (+, +, -)
    2: (-, +, +)    6: (-, +, -)
    3: (-, -, +)    7: (-, -, -)
    4: (+, -, +)    8: (+, -, -)
"""

from __future__ import annotations
import dataclasses
from core.models import BasketResult
from configs.settings import OCTANT_LABELS


def assign_octants(baskets: list[BasketResult]) -> list[BasketResult]:
    """
    Return a new list of BasketResult objects with `.group` set to octant (1–8).
    NaN correlations are treated as 0 (non-negative threshold).
    """
    updated: list[BasketResult] = []
    for b in baskets:
        x = b.corr_SP_safe   # 0 if NaN
        y = b.corr_MP_safe
        z = b.corr_MS_safe

        if   x >= 0 and y >= 0 and z >= 0:  group = 1
        elif x <  0 and y >= 0 and z >= 0:  group = 2
        elif x <  0 and y <  0 and z >= 0:  group = 3
        elif x >= 0 and y <  0 and z >= 0:  group = 4
        elif x >= 0 and y >= 0 and z <  0:  group = 5
        elif x <  0 and y >= 0 and z <  0:  group = 6
        elif x <  0 and y <  0 and z <  0:  group = 7
        else:                                group = 8

        updated.append(dataclasses.replace(b, group=group))

    return updated


def get_octant_label(group: int) -> str:
    """Return human-readable octant label for group 1–8."""
    if 1 <= group <= 8:
        return OCTANT_LABELS[group - 1]
    return f"Group {group}"


def compute_octant_summary(baskets: list[BasketResult]) -> list[dict]:
    """
    Aggregate octant-level summary statistics.

    Returns a list of dicts (one per octant 1..8) with:
        group, label, count, avg_corr_SP, avg_corr_MP, avg_corr_MS,
        total_sold, total_m, weighted_price
    """
    import math
    import numpy as np

    groups: dict[int, list[BasketResult]] = {i: [] for i in range(1, 9)}
    for b in baskets:
        if b.group in groups:
            groups[b.group].append(b)

    summaries = []
    for g, members in groups.items():
        label = OCTANT_LABELS[g - 1]
        if not members:
            summaries.append({"group": g, "label": label, "count": 0})
            continue

        def _avg(key: str) -> float:
            vals = [getattr(m, key) for m in members if not math.isnan(getattr(m, key))]
            return float(np.mean(vals)) if vals else float("nan")

        total_sold = sum(m.total_sold for m in members)
        total_m = sum(m.total_m for m in members)
        total_sp = sum(m.total_sold_price for m in members)
        wp = total_sp / total_sold if total_sold > 0 else 0.0

        summaries.append({
            "group": g,
            "label": label,
            "count": len(members),
            "avg_corr_SP": _avg("corr_SP"),
            "avg_corr_MP": _avg("corr_MP"),
            "avg_corr_MS": _avg("corr_MS"),
            "total_sold": total_sold,
            "total_m": total_m,
            "weighted_price": wp,
        })

    return summaries
