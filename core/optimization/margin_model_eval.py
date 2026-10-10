"""
Margin-model diagnostics and target-point evaluation.

Uses the same analytical model as ``price_optimization``:
    Sold(P, S) = z0_sold + a_sold*P + b_sold*S
    M(P, S)    = (P*(1 - a_cost) - z0_cost) * Sold(P, S)
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

from core.models import Linefit, Planefit
from core.optimization.price_optimization import (
    compute_analytical_margin,
    compute_optimal_price,
)

MARGIN_MODEL_PREDICTORS = 2


def compute_model_sold(price: float, stock: float, fit_sold: Planefit) -> float:
    return fit_sold.z0 + fit_sold.a * price + fit_sold.b * stock


def price_max_or_fallback(
    stock: float,
    fit_sold: Planefit,
    fit_cost: Linefit,
    fallback: float,
) -> float:
    p_max = compute_optimal_price(stock, fit_sold, fit_cost)
    return fallback if math.isnan(p_max) else p_max


def compute_margin_fit_metrics(
    prices: Sequence[float],
    stocks: Sequence[float],
    margins: Sequence[float],
    fit_sold: Planefit,
    fit_cost: Linefit,
    indices: Optional[Sequence[int]] = None,
) -> dict[str, float]:
    """Adj R², RMSE and MAPE of model margin vs actual margin over ``indices``."""
    n_all = min(len(prices), len(stocks), len(margins))
    use = range(n_all) if indices is None else [i for i in indices if 0 <= i < n_all]
    actual: list[float] = []
    predicted: list[float] = []
    for i in use:
        p, s, m = float(prices[i]), float(stocks[i]), float(margins[i])
        if not all(math.isfinite(v) for v in (p, s, m)):
            continue
        m_model = compute_analytical_margin(p, s, fit_sold, fit_cost)
        if not math.isfinite(m_model):
            continue
        actual.append(m)
        predicted.append(m_model)

    n = len(actual)
    nan = float("nan")
    if n == 0:
        return {"n": 0, "r2": nan, "adj_r2": nan, "rmse": nan, "mape": nan}

    mean_m = sum(actual) / n
    ss_tot = sum((m - mean_m) ** 2 for m in actual)
    ss_res = sum((m - mp) ** 2 for m, mp in zip(actual, predicted))
    p = MARGIN_MODEL_PREDICTORS
    r2 = 0.0 if ss_tot == 0.0 else 1.0 - ss_res / ss_tot
    adj_r2 = 1.0 - (1.0 - r2) * (n - 1) / (n - p - 1) if n > p + 1 else nan
    rmse = math.sqrt(ss_res / n)
    pct = [abs((m - mp) / m) for m, mp in zip(actual, predicted) if m != 0.0]
    mape = sum(pct) / len(pct) * 100.0 if pct else nan
    return {"n": n, "r2": r2, "adj_r2": adj_r2, "rmse": rmse, "mape": mape}


def evaluate_margin_target(
    price_actual: float,
    stock_actual: float,
    sold_actual: float,
    fit_sold: Planefit,
    fit_cost: Linefit,
    price_target: Optional[float] = None,
    stock_target: Optional[float] = None,
    tolerance: float = 1e-6,
) -> dict[str, float | bool]:
    """
    Compare the model at the actual point with a target point.

    Target defaults to (Price_max at actual stock, actual stock). ``is_manual``
    is True when the target differs from that default.
    """
    default_price = compute_optimal_price(stock_actual, fit_sold, fit_cost)
    s_target = stock_actual if stock_target is None else float(stock_target)
    if price_target is None:
        p_target = compute_optimal_price(s_target, fit_sold, fit_cost)
    else:
        p_target = float(price_target)

    def _differs(a: float, b: float) -> bool:
        if math.isnan(a) or math.isnan(b):
            return not (math.isnan(a) and math.isnan(b))
        return abs(a - b) > tolerance * max(1.0, abs(b))

    is_manual = bool(_differs(s_target, stock_actual) or _differs(p_target, default_price))

    sold_model = compute_model_sold(price_actual, stock_actual, fit_sold)
    m_model = compute_analytical_margin(price_actual, stock_actual, fit_sold, fit_cost)
    if math.isnan(p_target):
        nan = float("nan")
        sold_target = m_target = price_diff = m_gain = sold_gain = nan
    else:
        sold_target = compute_model_sold(p_target, s_target, fit_sold)
        m_target = compute_analytical_margin(p_target, s_target, fit_sold, fit_cost)
        price_diff = p_target - price_actual
        m_gain = m_target - m_model
        sold_gain = sold_target - sold_model

    return {
        "sold_actual": float(sold_actual),
        "sold_model": sold_model,
        "price_target": p_target,
        "stock_target": s_target,
        "is_manual": is_manual,
        "price_diff": price_diff,
        "m_target": m_target,
        "m_gain": m_gain,
        "sold_target": sold_target,
        "sold_gain": sold_gain,
    }
