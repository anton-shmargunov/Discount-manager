"""
Shared domain data models for the analytical engine.

These dataclasses are the contracts between analytical layers.
No Streamlit, no file I/O, no DB — pure data structures.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BasketTimeSeries:
    """
    Raw week-by-week time series for a single basket.
    Produced by the ETL transform and consumed by modeling/statistics layers.
    """
    basket: str
    weeks: list[str]
    quadweeks: list[str]
    sold: list[float]
    price: list[float]
    m: list[float]
    stock: list[float]
    cost: list[float]           # derived: (sold*price - m) / sold  per week
    count_product: list[float] = field(default_factory=list)
    purchase: list[float] = field(default_factory=list)
    week_in_quad: list[int] = field(default_factory=list)
    discount: list[float] = field(default_factory=list)
    prom: list[float] = field(default_factory=list)
    recap: list[float] = field(default_factory=list)

    # Fit results — populated lazily by the modeling layer
    fit_sold: Optional[Planefit] = None   # Sold = f(Price, Stock)
    fit_cost: Optional[Linefit] = None    # Cost = f(Price)

    @property
    def n_weeks(self) -> int:
        return len(self.weeks)


@dataclass
class Planefit:
    """Result of a 3-variable plane fit: z = z0 + a*x + b*y"""
    z0: float
    a: float
    b: float
    # Goodness-of-fit metrics
    r2: float = float("nan")
    adj_r2: float = float("nan")
    rmse: float = float("nan")
    mape: float = float("nan")


@dataclass
class Linefit:
    """Result of a 2-variable line fit: y = z0 + a*x"""
    z0: float           # intercept
    a: float            # slope
    pl: float           # leverage price:  z0 / (1 - a)
    # Goodness-of-fit metrics
    r2: float = float("nan")
    rmse: float = float("nan")
    mape: float = float("nan")


@dataclass
class BasketResult:
    """
    Summary statistics and correlation profile for a single basket.
    Produced by the analytics layer; consumed by clustering, UI, and export.
    """
    basket: str
    total_sold: float
    total_m: float
    total_sold_price: float
    weighted_price: float
    average_stock: float
    average_count_product: float
    total_purchase: float
    corr_SP: float          # Pearson(Sold, Price)
    corr_MP: float          # Pearson(M, Price)
    corr_MS: float          # Pearson(M, Sold)
    av_dstock_w_qw: float   # avg within-quadweek stock slope
    av_dstock_b_qw: float   # avg between-quadweek stock jump

    # Clustering coordinates (NaN-safe: 0 when correlation is NaN)
    coords: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    # Assigned cluster group (0 = unclustered)
    group: int = 0

    @property
    def corr_SP_safe(self) -> float:
        import math
        return 0.0 if math.isnan(self.corr_SP) else self.corr_SP

    @property
    def corr_MP_safe(self) -> float:
        import math
        return 0.0 if math.isnan(self.corr_MP) else self.corr_MP

    @property
    def corr_MS_safe(self) -> float:
        import math
        return 0.0 if math.isnan(self.corr_MS) else self.corr_MS


@dataclass
class WeeklyPoint:
    """A single basket observation within a weekly aggregate."""
    basket: str
    sold: float
    price: float
    m: float
    stock: float
    count_product: float = 0.0
    purchase: float = 0.0
    recap: float = 0.0


@dataclass
class WeeklyTotal:
    """
    Aggregated totals across all valid baskets for a given week.
    Used for the Sum-Up view.
    """
    week: str
    sum_sold: float
    sum_m: float
    sum_sold_price: float
    sum_stock: float
    valid_baskets: int
    sum_count_product: float = 0.0
    sum_purchase: float = 0.0
    sum_recap: float = 0.0
    sum_sold_for_price: float = 0.0
    quadweek: str = "N/A"
    week_in_quad: int = 0
    points: list[WeeklyPoint] = field(default_factory=list)

    @property
    def weighted_price(self) -> float:
        if self.sum_sold_for_price > 0:
            return self.sum_sold_price / self.sum_sold_for_price
        if self.sum_sold_for_price == 0 and self.sum_sold_price > 0 and self.sum_sold > 0:
            return self.sum_sold_price / self.sum_sold
        if self.sum_sold > 0:
            return float("nan")
        return 0.0


@dataclass
class MarginModelResult:
    """Output of the analytical margin optimization model for a specific week."""
    week: str
    price_actual: float
    stock_actual: float
    m_actual: float
    m_model: float
    m_error_abs: float
    m_error_pct: float
    price_max: float
    price_diff: float
    m_surplus: float        # gain from moving to price_max
