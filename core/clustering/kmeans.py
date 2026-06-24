"""
K-Means clustering on the 3D correlation space (corr_SP, corr_MP, corr_MS).

Pure implementation — no scikit-learn dependency for the core logic,
keeping it identical to the validated JS logic from the prototype.
Scikit-learn can be used for advanced variants in future phases.
"""

from __future__ import annotations
import random
import numpy as np
from core.models import BasketResult
from configs.settings import KMEANS_MAX_ITER


def run_kmeans(
    baskets: list[BasketResult],
    k: int,
    max_iter: int = KMEANS_MAX_ITER,
    seed: int = 42,
) -> list[BasketResult]:
    """
    Assign K-Means cluster labels (1-indexed groups) to each BasketResult.

    Clustering operates in the 3D correlation space: coords = [corr_SP, corr_MP, corr_MS]
    (with NaN replaced by 0 in BasketResult.coords).

    Returns a new list of BasketResult objects with `.group` set.
    """
    if k <= 0 or not baskets:
        return baskets

    k = min(k, len(baskets))
    n = len(baskets)
    coords = np.array([b.coords for b in baskets], dtype=float)

    # Evenly-spaced initialisation (mirrors the JS prototype)
    rng = np.random.default_rng(seed)
    indices = np.linspace(0, n - 1, k, dtype=int)
    centroids = coords[indices].copy()

    assignments = np.zeros(n, dtype=int)

    for _ in range(max_iter):
        # Assignment step
        dists = np.linalg.norm(coords[:, None, :] - centroids[None, :, :], axis=2)
        new_assignments = np.argmin(dists, axis=1)

        if np.array_equal(new_assignments, assignments):
            break
        assignments = new_assignments

        # Update step
        for c in range(k):
            members = coords[assignments == c]
            if len(members) > 0:
                centroids[c] = members.mean(axis=0)

    updated: list[BasketResult] = []
    for i, b in enumerate(baskets):
        import dataclasses
        updated.append(dataclasses.replace(b, group=int(assignments[i]) + 1))

    return updated


def compute_cluster_summary(
    baskets: list[BasketResult],
    k: int,
) -> list[dict]:
    """
    Aggregate cluster-level summary statistics.

    Returns a list of dicts (one per group 1..k) with:
        group, label, count, avg_corr_SP, avg_corr_MP, avg_corr_MS,
        total_sold, total_m, weighted_price
    """
    import math

    groups: dict[int, list[BasketResult]] = {i: [] for i in range(1, k + 1)}
    for b in baskets:
        if b.group in groups:
            groups[b.group].append(b)

    summaries = []
    for g, members in groups.items():
        if not members:
            summaries.append({"group": g, "count": 0})
            continue

        def _avg_corr(key: str) -> float:
            vals = [getattr(m, key) for m in members if not math.isnan(getattr(m, key))]
            return float(np.mean(vals)) if vals else float("nan")

        total_sold = sum(m.total_sold for m in members)
        total_m = sum(m.total_m for m in members)
        total_sp = sum(m.total_sold_price for m in members)
        wp = total_sp / total_sold if total_sold > 0 else 0.0

        summaries.append({
            "group": g,
            "count": len(members),
            "avg_corr_SP": _avg_corr("corr_SP"),
            "avg_corr_MP": _avg_corr("corr_MP"),
            "avg_corr_MS": _avg_corr("corr_MS"),
            "total_sold": total_sold,
            "total_m": total_m,
            "weighted_price": wp,
        })

    return summaries
