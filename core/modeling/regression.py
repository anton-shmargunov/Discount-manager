"""
Mathematical fitting models: Multiple Linear Regression, Simple Linear Regression,
PCA-based plane fitting, and goodness-of-fit statistics.

All functions are pure and stateless.
"""

from __future__ import annotations
import math
import numpy as np
from typing import Optional, Sequence

from core.models import Planefit, Linefit
from configs.settings import MIN_POINTS_FOR_MLR, MIN_POINTS_FOR_SLR


# ---------------------------------------------------------------------------
# Multiple Linear Regression  z = b0 + b1*x + b2*y
# ---------------------------------------------------------------------------

def fit_mlr(
    x: Sequence[float],
    y: Sequence[float],
    z: Sequence[float],
) -> Optional[dict[str, float]]:
    """
    Fit a plane z = b0 + b1*x + b2*y using Ordinary Least Squares.

    Returns {"b0": ..., "b1": ..., "b2": ...} or None if not enough data
    or the system is degenerate.
    """
    n = len(x)
    if n < MIN_POINTS_FOR_MLR:
        return None

    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    z_arr = np.asarray(z, dtype=float)

    mean_x, mean_y, mean_z = x_arr.mean(), y_arr.mean(), z_arr.mean()
    dx = x_arr - mean_x
    dy = y_arr - mean_y
    dz = z_arr - mean_z

    Sxx = float((dx * dx).sum())
    Syy = float((dy * dy).sum())
    Sxy = float((dx * dy).sum())
    Sxz = float((dx * dz).sum())
    Syz = float((dy * dz).sum())

    denom = Sxx * Syy - Sxy * Sxy
    if abs(denom) < 1e-10:
        return None

    b1 = (Syy * Sxz - Sxy * Syz) / denom
    b2 = (Sxx * Syz - Sxy * Sxz) / denom
    b0 = mean_z - b1 * mean_x - b2 * mean_y

    return {"b0": b0, "b1": b1, "b2": b2}


# ---------------------------------------------------------------------------
# Simple Linear Regression  y = intercept + slope*x
# ---------------------------------------------------------------------------

def fit_slr(
    x: Sequence[float],
    y: Sequence[float],
) -> Optional[dict[str, float]]:
    """
    Fit a line y = intercept + slope*x using Ordinary Least Squares.

    Returns {"slope": ..., "intercept": ...} or None if degenerate.
    """
    n = len(x)
    if n < MIN_POINTS_FOR_SLR:
        return None

    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)

    sum_x = x_arr.sum()
    sum_y = y_arr.sum()
    sum_xy = (x_arr * y_arr).sum()
    sum_xx = (x_arr * x_arr).sum()

    denom = n * sum_xx - sum_x * sum_x
    if abs(denom) < 1e-10:
        return None

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    return {"slope": slope, "intercept": intercept}


# ---------------------------------------------------------------------------
# PCA-based plane fitting (orthogonal regression)
# ---------------------------------------------------------------------------

def _power_iteration(M: np.ndarray, n_iter: int = 100) -> tuple[np.ndarray, float]:
    """Return dominant eigenvector and eigenvalue of a 3x3 symmetric matrix."""
    v = np.array([1.0, 1.0, 1.0])
    lam = 0.0
    for _ in range(n_iter):
        nv = M @ v
        norm = np.linalg.norm(nv)
        if norm < 1e-10:
            break
        v = nv / norm
        lam = float(v @ (M @ v))
    return v, lam


def fit_pca_plane(
    x: Sequence[float],
    y: Sequence[float],
    z: Sequence[float],
) -> Optional[dict[str, float]]:
    """
    Fit a plane using PCA (orthogonal distance minimisation).
    The normal vector is the third principal component.

    Returns {"b0": ..., "b1": ..., "b2": ...} compatible with fit_mlr output,
    or None if degenerate.
    """
    n = len(x)
    if n < MIN_POINTS_FOR_MLR:
        return None

    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    z_arr = np.asarray(z, dtype=float)

    mean_x, mean_y, mean_z = x_arr.mean(), y_arr.mean(), z_arr.mean()
    dx = x_arr - mean_x
    dy = y_arr - mean_y
    dz = z_arr - mean_z

    # 3x3 covariance matrix
    pts = np.column_stack([dx, dy, dz])
    C = pts.T @ pts

    # First principal component (largest variance)
    v1, lam1 = _power_iteration(C)

    # Deflate and get second principal component
    C2 = C - lam1 * np.outer(v1, v1)
    v2, _ = _power_iteration(C2)

    # Normal vector = v1 × v2
    nx = v1[1] * v2[2] - v1[2] * v2[1]
    ny = v1[2] * v2[0] - v1[0] * v2[2]
    nz = v1[0] * v2[1] - v1[1] * v2[0]

    if abs(nz) < 1e-10:
        return None

    b1 = -nx / nz
    b2 = -ny / nz
    b0 = mean_z - b1 * mean_x - b2 * mean_y

    return {"b0": b0, "b1": b1, "b2": b2}


# ---------------------------------------------------------------------------
# Goodness-of-fit statistics
# ---------------------------------------------------------------------------

def compute_fit_stats_3d(
    x: Sequence[float],
    y: Sequence[float],
    z: Sequence[float],
    fit: dict[str, float],
) -> Optional[Planefit]:
    """
    Compute R², Adjusted R², RMSE, MAPE for a 3D plane fit.

    fit: {"b0": intercept, "b1": coef_x, "b2": coef_y}
    Returns a Planefit dataclass or None if too few data points.
    """
    n = len(x)
    p = 2   # number of predictors
    if n < p + 2:
        return None

    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    z_arr = np.asarray(z, dtype=float)

    z_pred = fit["b0"] + fit["b1"] * x_arr + fit["b2"] * y_arr
    mean_z = z_arr.mean()

    ss_tot = float(((z_arr - mean_z) ** 2).sum())
    ss_res = float(((z_arr - z_pred) ** 2).sum())

    rmse = math.sqrt(ss_res / n)
    r2 = 0.0 if ss_tot == 0.0 else 1.0 - ss_res / ss_tot
    adj_r2 = (1.0 - (1.0 - r2) * (n - 1) / (n - p - 1)) if n > p + 1 else float("nan")

    nonzero = z_arr != 0.0
    mape = (
        float(np.mean(np.abs((z_arr[nonzero] - z_pred[nonzero]) / z_arr[nonzero])) * 100)
        if nonzero.any() else float("nan")
    )

    return Planefit(
        z0=fit["b0"], a=fit["b1"], b=fit["b2"],
        r2=r2, adj_r2=adj_r2, rmse=rmse, mape=mape,
    )


def compute_fit_stats_2d(
    x: Sequence[float],
    y: Sequence[float],
    fit: dict[str, float],
) -> Optional[Linefit]:
    """
    Compute R², RMSE, MAPE and Pl (leverage price) for a 2D line fit.

    fit: {"slope": ..., "intercept": ...}
    Model: y = intercept + slope*x  →  Cost = z0 + a*Price
    Pl = z0 / (1 - a)

    Returns a Linefit dataclass or None if too few data points.
    """
    n = len(x)
    if n < 2:
        return None

    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)

    z0 = fit["intercept"]
    a = fit["slope"]
    y_pred = z0 + a * x_arr
    mean_y = y_arr.mean()

    ss_tot = float(((y_arr - mean_y) ** 2).sum())
    ss_res = float(((y_arr - y_pred) ** 2).sum())

    rmse = math.sqrt(ss_res / n)
    r2 = 0.0 if ss_tot == 0.0 else 1.0 - ss_res / ss_tot

    nonzero = y_arr != 0.0
    mape = (
        float(np.mean(np.abs((y_arr[nonzero] - y_pred[nonzero]) / y_arr[nonzero])) * 100)
        if nonzero.any() else float("nan")
    )

    denom_pl = 1.0 - a
    pl = z0 / denom_pl if abs(denom_pl) > 1e-10 else float("nan")

    return Linefit(z0=z0, a=a, pl=pl, r2=r2, rmse=rmse, mape=mape)


# ---------------------------------------------------------------------------
# Convenience dispatcher
# ---------------------------------------------------------------------------

def fit_plane(
    x: Sequence[float],
    y: Sequence[float],
    z: Sequence[float],
    method: str = "mlr",
) -> Optional[Planefit]:
    """
    Fit a 3D plane and return a Planefit with goodness-of-fit stats.

    method: "mlr" or "pca"
    """
    raw = fit_mlr(x, y, z) if method == "mlr" else fit_pca_plane(x, y, z)
    if raw is None:
        return None
    return compute_fit_stats_3d(x, y, z, raw)


def values_skipping_last(
    values: Sequence[float],
    skip_last: int,
) -> list[float]:
    """Return ``values`` with the last ``skip_last`` points removed."""
    skip = max(0, int(skip_last or 0))
    items = list(values)
    if skip == 0:
        return items
    if skip >= len(items):
        return []
    return items[:-skip]


def paired_values_skipping_zero_x(
    x: Sequence[float],
    y: Sequence[float],
    skip_zero_x: bool,
) -> tuple[list[float], list[float]]:
    """Drop paired points whose x value is exactly 0 when ``skip_zero_x`` is true."""
    xs = list(x)
    ys = list(y)
    if not skip_zero_x:
        n = min(len(xs), len(ys))
        return xs[:n], ys[:n]
    kept_x: list[float] = []
    kept_y: list[float] = []
    for xv, yv in zip(xs, ys):
        if xv == 0:
            continue
        kept_x.append(xv)
        kept_y.append(yv)
    return kept_x, kept_y


def fit_line(
    x: Sequence[float],
    y: Sequence[float],
) -> Optional[Linefit]:
    """Fit a 2D line and return a Linefit with goodness-of-fit stats."""
    raw = fit_slr(x, y)
    if raw is None:
        return None
    return compute_fit_stats_2d(x, y, raw)
