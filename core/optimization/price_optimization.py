"""
Pricing optimization: analytical margin model and Price_max computation.

The model assumes:
    Cost(P) = z0_cost + a_cost * P           [from Cost vs Price line fit]
    Sold(P, S) = z0_sold + a_sold*P + b_sold*S  [from Price/Stock vs Sold plane fit]
    M(P, S) = (P - Cost(P)) * Sold(P, S)

Maximizing M(P) w.r.t. P at fixed S gives:
    Price_max(S) = Pl/2 - (b_sold*S + z0_sold) / (2*a_sold)
    where Pl = z0_cost / (1 - a_cost)

All functions are pure and stateless.
"""

from __future__ import annotations
import math
import numpy as np
from typing import Optional

from core.models import Planefit, Linefit, MarginModelResult


def compute_analytical_margin(
    price: float,
    stock: float,
    fit_sold: Planefit,
    fit_cost: Linefit,
) -> float:
    """
    M(P, S) = (P*(1 - a_cost) - z0_cost) * (a_sold*P + b_sold*S + z0_sold)
    """
    margin_per_unit = price * (1.0 - fit_cost.a) - fit_cost.z0
    quantity = fit_sold.a * price + fit_sold.b * stock + fit_sold.z0
    return margin_per_unit * quantity


def compute_optimal_price(
    stock: float,
    fit_sold: Planefit,
    fit_cost: Linefit,
) -> float:
    """
    Price_max(S) = Pl/2 - (b_sold*S + z0_sold) / (2*a_sold)

    Returns NaN if fit_sold.a == 0 or Pl is NaN.
    """
    if abs(fit_sold.a) < 1e-10 or math.isnan(fit_cost.pl):
        return float("nan")
    return fit_cost.pl / 2.0 - (fit_sold.b * stock + fit_sold.z0) / (2.0 * fit_sold.a)


def evaluate_week_margin_model(
    week: str,
    price_actual: float,
    stock_actual: float,
    m_actual: float,
    fit_sold: Planefit,
    fit_cost: Linefit,
) -> MarginModelResult:
    """
    Evaluate the analytical margin model at a specific week's actual price and stock.
    Computes model error and the optimal price and its margin surplus.
    """
    m_model = compute_analytical_margin(price_actual, stock_actual, fit_sold, fit_cost)
    m_error_abs = abs(m_actual - m_model)
    m_error_pct = (m_error_abs / abs(m_actual) * 100.0) if m_actual != 0.0 else float("nan")

    p_max = compute_optimal_price(stock_actual, fit_sold, fit_cost)
    m_at_p_max = (
        compute_analytical_margin(p_max, stock_actual, fit_sold, fit_cost)
        if not math.isnan(p_max) else float("nan")
    )
    m_surplus = m_at_p_max - m_model if not math.isnan(m_at_p_max) else float("nan")
    price_diff = p_max - price_actual if not math.isnan(p_max) else float("nan")

    return MarginModelResult(
        week=week,
        price_actual=price_actual,
        stock_actual=stock_actual,
        m_actual=m_actual,
        m_model=m_model,
        m_error_abs=m_error_abs,
        m_error_pct=m_error_pct,
        price_max=p_max,
        price_diff=price_diff,
        m_surplus=m_surplus,
    )


def build_margin_surface(
    fit_sold: Planefit,
    fit_cost: Linefit,
    price_range: tuple[float, float],
    stock_range: tuple[float, float],
    n_price: int = 50,
    n_stock: int = 50,
) -> tuple[list[float], list[float], list[list[float]]]:
    """
    Compute a grid of M(P, S) values over the specified price and stock ranges.

    Returns (price_values, stock_values, z_grid) suitable for Plotly surface traces.
    z_grid[j][i] = M(price_values[i], stock_values[j])
    """
    p_min, p_max_range = price_range
    s_min, s_max_range = stock_range

    prices = list(np.linspace(p_min, p_max_range, max(2, n_price)))
    stocks = list(np.linspace(s_min, s_max_range, max(2, n_stock)))

    z_grid: list[list[float]] = []
    for s in stocks:
        row: list[float] = []
        for p in prices:
            row.append(compute_analytical_margin(p, s, fit_sold, fit_cost))
        z_grid.append(row)

    return prices, stocks, z_grid


def compute_price_max_curve(
    fit_sold: Planefit,
    fit_cost: Linefit,
    stock_values: list[float],
) -> list[float]:
    """
    Compute Price_max for each stock value in stock_values.
    Used to render the Price_max vs Stock curve.
    """
    return [compute_optimal_price(s, fit_sold, fit_cost) for s in stock_values]
