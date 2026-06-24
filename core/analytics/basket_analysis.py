"""
High-level analytical workflow: orchestrates transforms, statistics, and clustering
to produce the full PCBA analysis from raw DataFrames.

This is the single entry point the UI calls — it returns structured results
without touching Streamlit, files, or databases.
"""

from __future__ import annotations
import math
import pandas as pd
from typing import Optional

from core.models import BasketResult, BasketTimeSeries, WeeklyTotal
from core.transforms.data_prep import (
    normalize_csv_df,
    extract_basket_columns,
    index_by_week,
    resolve_common_weeks,
    compute_basket_features,
    compute_weekly_totals,
    tracking_report_to_frame_set,
    tracking_product_bs_report_to_frame_sets,
    parse_discount_hist_lookup,
)
from core.clustering.kmeans import run_kmeans, compute_cluster_summary
from core.clustering.octants import assign_octants, compute_octant_summary
from core.statistics.correlations import compute_pearson
from core.statistics.metrics import monthly_reserve


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------

def run_basket_analysis(
    df_sold: pd.DataFrame,
    df_price: pd.DataFrame,
    df_m: pd.DataFrame,
    df_stock: pd.DataFrame,
    df_count_product: Optional[pd.DataFrame] = None,
    df_purchase: Optional[pd.DataFrame] = None,
    min_sold: float = -math.inf,
    max_sold: float = math.inf,
    min_price: float = 0.001,
    max_price: float = math.inf,
    min_m: float = -math.inf,
    max_m: float = math.inf,
    min_week: Optional[str] = None,
    max_week: Optional[str] = None,
) -> "AnalysisResult":
    """
    Execute the full basket correlation and bucketing analysis.

    Parameters
    ----------
    df_sold, df_price, df_m, df_stock:
        Raw DataFrames as loaded from CSV (one row per week, columns = baskets + metadata).
    min_*/max_*:
        Data-point level filters applied before statistics.
    min_week / max_week:
        Optional ISO week range filter ("YYYY-WW" format).

    Returns
    -------
    AnalysisResult with basket results, time series, and weekly aggregates.
    """
    df_sold = normalize_csv_df(df_sold)
    df_price = normalize_csv_df(df_price)
    df_m = normalize_csv_df(df_m)
    df_stock = normalize_csv_df(df_stock)
    df_count_product = normalize_csv_df(df_count_product) if df_count_product is not None else None
    df_purchase = normalize_csv_df(df_purchase) if df_purchase is not None else None

    sold_dict = index_by_week(df_sold)
    price_dict = index_by_week(df_price)
    m_dict = index_by_week(df_m)
    stock_dict = index_by_week(df_stock)
    count_product_dict = index_by_week(df_count_product) if df_count_product is not None else None
    purchase_dict = index_by_week(df_purchase) if df_purchase is not None else None

    weeks = resolve_common_weeks(
        [sold_dict, price_dict, m_dict, stock_dict],
        min_week=min_week,
        max_week=max_week,
    )
    if not weeks:
        raise ValueError("No overlapping 'year_week' values found across the four files.")

    baskets = extract_basket_columns(df_sold)
    if not baskets:
        raise ValueError("No basket columns found in the SoldIn CSV.")

    basket_results, basket_data = compute_basket_features(
        sold_dict, price_dict, m_dict, stock_dict,
        baskets=baskets,
        weeks=weeks,
        min_sold=min_sold,
        max_sold=max_sold,
        min_price=min_price,
        max_price=max_price,
        min_m=min_m,
        max_m=max_m,
        count_product_dict=count_product_dict,
        purchase_dict=purchase_dict,
    )

    if not basket_results:
        raise ValueError("No baskets passed the data filters. Try relaxing the min/max thresholds.")

    weekly_totals = compute_weekly_totals(
        sold_dict, price_dict, m_dict, stock_dict,
        basket_data=basket_data,
        weeks=weeks,
    )

    return AnalysisResult(
        basket_results=basket_results,
        basket_data=basket_data,
        weekly_totals=weekly_totals,
        all_weeks=weeks,
    )


def run_tracking_report_analysis(
    df_report: pd.DataFrame,
    min_sold: float = -math.inf,
    max_sold: float = math.inf,
    min_price: float = 0.001,
    max_price: float = math.inf,
    min_m: float = -math.inf,
    max_m: float = math.inf,
    min_week: Optional[str] = None,
    max_week: Optional[str] = None,
) -> "AnalysisResult":
    """
    Execute the full analysis from a single long TrackingBaskets_v2 report.
    """
    frames = tracking_report_to_frame_set(df_report)
    return run_basket_analysis(
        frames.sold,
        frames.price,
        frames.margin,
        frames.stock,
        df_count_product=frames.count_product,
        df_purchase=frames.purchase,
        min_sold=min_sold,
        max_sold=max_sold,
        min_price=min_price,
        max_price=max_price,
        min_m=min_m,
        max_m=max_m,
        min_week=min_week,
        max_week=max_week,
    )


def run_tracking_product_bs_report_analysis(
    df_report: pd.DataFrame,
    product_bs_category: str = "Aggregated",
    use_monthly_average_metrics: bool = False,
    min_sold: float = -math.inf,
    max_sold: float = math.inf,
    min_price: float = 0.001,
    max_price: float = math.inf,
    min_m: float = -math.inf,
    max_m: float = math.inf,
    min_week: Optional[str] = None,
    max_week: Optional[str] = None,
) -> tuple["AnalysisResult", list[str]]:
    """
    Execute analysis from a TrackingBaskets_v2 - product_BS report.

    product_bs_category is one of:
    "Aggregated", "In", "Out", "OutByCondition", "OutByMinPrice", "none".
    """
    parsed = tracking_product_bs_report_to_frame_sets(
        df_report,
        use_monthly_average_metrics=use_monthly_average_metrics,
    )
    if product_bs_category == "Aggregated":
        frames = parsed.aggregate
    elif product_bs_category in parsed.categories:
        frames = parsed.categories[product_bs_category]
    else:
        valid = ["Aggregated", *sorted(parsed.categories.keys())]
        raise ValueError(
            "Unknown product_BS category "
            f"'{product_bs_category}'. Expected one of: {', '.join(valid)}."
        )

    analysis = run_basket_analysis(
        frames.sold,
        frames.price,
        frames.margin,
        frames.stock,
        df_count_product=frames.count_product,
        df_purchase=frames.purchase,
        min_sold=min_sold,
        max_sold=max_sold,
        min_price=min_price,
        max_price=max_price,
        min_m=min_m,
        max_m=max_m,
        min_week=min_week,
        max_week=max_week,
    )
    return analysis, parsed.warnings


def apply_kmeans(result: "AnalysisResult", k: int) -> "AnalysisResult":
    """Return a new AnalysisResult with K-Means group assignments applied."""
    import dataclasses
    updated_baskets = run_kmeans(result.basket_results, k)
    return dataclasses.replace(
        result,
        basket_results=updated_baskets,
        cluster_mode="kmeans",
        cluster_k=k,
        cluster_labels=None,
    )


def apply_octants(result: "AnalysisResult") -> "AnalysisResult":
    """Return a new AnalysisResult with Octant group assignments applied."""
    import dataclasses
    from configs.settings import OCTANT_LABELS
    updated_baskets = assign_octants(result.basket_results)
    return dataclasses.replace(
        result,
        basket_results=updated_baskets,
        cluster_mode="octants",
        cluster_k=8,
        cluster_labels=OCTANT_LABELS,
    )


# ---------------------------------------------------------------------------
# Weekly Sum-Up statistics
# ---------------------------------------------------------------------------

def compute_sumup_series(
    weekly_totals: dict[str, WeeklyTotal],
    weeks: list[str],
) -> list[dict]:
    """
    Build a sorted list of weekly summary dicts for the Sum-Up table and charts.

    Each dict contains: week, weighted_price, total_sold, total_m,
    corr_SP, corr_MP, corr_MS.
    """
    rows = []
    for w in weeks:
        if w not in weekly_totals:
            continue
        wt = weekly_totals[w]
        if wt.valid_baskets == 0:
            continue

        sold_vals = [p.sold for p in wt.points]
        price_vals = [p.price for p in wt.points]
        m_vals = [p.m for p in wt.points]

        rows.append({
            "week": w,
            "quadweek": wt.quadweek,
            "week_in_quad": wt.week_in_quad,
            "weighted_price": wt.weighted_price,
            "total_sold": wt.sum_sold,
            "total_stock": wt.sum_stock,
            "total_count_product": wt.sum_count_product,
            "total_purchase": wt.sum_purchase,
            "total_revenue": wt.sum_sold_price,
            "total_m": wt.sum_m,
            "total_cost": wt.weighted_price - (wt.sum_m / wt.sum_sold) if wt.sum_sold > 0 else 0.0,
            "total_monthly_reserve": monthly_reserve(wt.sum_stock, wt.sum_sold),
            "corr_SP": compute_pearson(sold_vals, price_vals),
            "corr_MP": compute_pearson(m_vals, price_vals),
            "corr_MS": compute_pearson(m_vals, sold_vals),
        })

    return rows


def init_discount_prom_on_basket_data(
    basket_data: dict[str, BasketTimeSeries],
    fill: float = float("nan"),
) -> None:
    """Ensure every basket time series has discount/prom aligned to its weeks."""
    for ts in basket_data.values():
        ts.discount = [fill] * ts.n_weeks
        ts.prom = [fill] * ts.n_weeks


def apply_discount_hist_to_basket_data(
    basket_data: dict[str, BasketTimeSeries],
    df_discount_hist: pd.DataFrame,
    product_bs_category: str,
) -> list[str]:
    """Merge discount/prom lookup values into existing basket time series."""
    lookup, warnings = parse_discount_hist_lookup(df_discount_hist, product_bs_category)
    init_discount_prom_on_basket_data(basket_data)
    for ts in basket_data.values():
        for i, week in enumerate(ts.weeks):
            key = (str(ts.basket), str(week))
            if key in lookup:
                discount, prom = lookup[key]
                ts.discount[i] = discount
                ts.prom[i] = prom
    return warnings


# ---------------------------------------------------------------------------
# AnalysisResult container
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AnalysisResult:
    """
    Complete output of run_basket_analysis().
    Immutable snapshot — apply_kmeans / apply_octants return new instances.
    """
    basket_results: list[BasketResult]
    basket_data: dict[str, BasketTimeSeries]
    weekly_totals: dict[str, WeeklyTotal]
    all_weeks: list[str]
    cluster_mode: str = "none"          # "none" | "kmeans" | "octants"
    cluster_k: int = 0
    cluster_labels: Optional[list[str]] = None

    @property
    def basket_count(self) -> int:
        return len(self.basket_results)

    @property
    def week_count(self) -> int:
        return len(self.all_weeks)

    def get_cluster_label(self, group: int) -> str:
        if self.cluster_labels and 1 <= group <= len(self.cluster_labels):
            return self.cluster_labels[group - 1]
        return f"Group {group}" if group > 0 else "Unclustered"

    def get_cluster_summary(self) -> list[dict]:
        if self.cluster_mode == "none" or self.cluster_k == 0:
            return []
        if self.cluster_mode == "octants":
            return compute_octant_summary(self.basket_results)
        return compute_cluster_summary(self.basket_results, self.cluster_k)
