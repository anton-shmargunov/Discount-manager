"""
Pure dataframe transformation and feature-engineering pipeline.

Responsibilities:
- Normalize and index raw CSVs by year_week.
- Filter data points according to user-supplied thresholds.
- Compute per-basket time series and summary features.
- Compute weekly aggregate totals.

CRITICAL: no file I/O, no DB, no Streamlit, no orchestration here.
All functions are deterministic and stateless.
"""

from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd
from typing import Optional

from core.models import (
    BasketTimeSeries,
    BasketResult,
    WeeklyPoint,
    WeeklyTotal,
)
from core.statistics.correlations import compute_basket_correlations, safe_correlation_coord
from configs.settings import CSV_METADATA_COLS


@dataclass
class MetricFrameSet:
    """Canonical wide metric frames: one row per week, basket IDs as columns."""
    sold: pd.DataFrame
    price: pd.DataFrame
    margin: pd.DataFrame
    stock: pd.DataFrame
    count_product: Optional[pd.DataFrame] = None
    purchase: Optional[pd.DataFrame] = None
    recap: Optional[pd.DataFrame] = None


@dataclass
class ProductBSTransformResult:
    """Parsed TrackingBaskets_v2 product-BS report outputs."""
    aggregate: MetricFrameSet
    categories: dict[str, MetricFrameSet]
    warnings: list[str]


# ---------------------------------------------------------------------------
# Dataframe normalization helpers
# ---------------------------------------------------------------------------

def normalize_csv_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Strip whitespace from column names and string values.
    Ensures consistent lowercase matching for metadata column detection.
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    if "year_week" in df.columns:
        df["year_week"] = df["year_week"].astype(str).str.strip()
    return df


def extract_basket_columns(df: pd.DataFrame) -> list[str]:
    """
    Return basket column names by excluding metadata columns.
    Comparison is case-insensitive.
    """
    lower_meta = {c.lower() for c in CSV_METADATA_COLS}
    return [
        c for c in df.columns
        if c.strip() != "" and c.strip().lower() not in lower_meta
    ]


def index_by_week(df: pd.DataFrame, week_col: str = "year_week") -> dict[str, pd.Series]:
    """Build a {year_week -> row Series} dict for fast lookups."""
    result: dict[str, pd.Series] = {}
    for _, row in df.iterrows():
        key = str(row.get(week_col, "")).strip()
        if key:
            result[key] = row
    return result


def resolve_common_weeks(
    dicts: list[dict[str, pd.Series]],
    min_week: Optional[str] = None,
    max_week: Optional[str] = None,
) -> list[str]:
    """
    Return sorted list of year_week keys present in ALL provided dicts,
    optionally clipped by [min_week, max_week].
    """
    if not dicts:
        return []
    common = set(dicts[0].keys())
    for d in dicts[1:]:
        common &= set(d.keys())
    weeks = sorted(common)
    if min_week:
        weeks = [w for w in weeks if w >= min_week]
    if max_week:
        weeks = [w for w in weeks if w <= max_week]
    return weeks


def _infer_week_in_quadweek(week_quad_pairs: pd.DataFrame) -> dict[str, int]:
    """
    Infer 1..4 week position inside each quadweek from chronological report rows.

    The report may start mid-quadweek. If the first observed quadweek has only
    three weeks, those weeks are assigned 2, 3, 4 rather than 1, 2, 3.
    """
    unique_weeks = (
        week_quad_pairs[["year_week", "quadweek"]]
        .drop_duplicates()
        .sort_values(["year_week"])
        .reset_index(drop=True)
    )
    if unique_weeks.empty:
        return {}

    first_qw = str(unique_weeks.loc[0, "quadweek"])
    first_qw_count = int((unique_weeks["quadweek"].astype(str) == first_qw).sum())
    first_qw_start = max(1, 5 - min(first_qw_count, 4))

    positions: dict[str, int] = {}
    current_qw: Optional[str] = None
    position = 0
    for _, row in unique_weeks.iterrows():
        week = str(row["year_week"]).strip()
        qw = str(row["quadweek"]).strip()
        if qw != current_qw:
            current_qw = qw
            position = first_qw_start if not positions else 1
        else:
            position += 1
        positions[week] = min(position, 4)

    return positions


def _metric_wide_frame(
    report: pd.DataFrame,
    metric_col: str,
    week_meta: pd.DataFrame,
    aggfunc: str = "sum",
) -> pd.DataFrame:
    """Pivot one TrackingBaskets_v2 metric to the canonical wide input shape."""
    metric = report[["year_week", "basket", metric_col]].copy()
    metric[metric_col] = pd.to_numeric(metric[metric_col], errors="coerce").fillna(0.0)

    wide = (
        metric.pivot_table(
            index="year_week",
            columns="basket",
            values=metric_col,
            aggfunc=aggfunc,
        )
        .reset_index()
    )
    wide.columns = [str(c).strip() for c in wide.columns]
    return week_meta.merge(wide, on="year_week", how="left")


def _normalize_basket_id(value: object) -> str:
    """Keep numeric basket IDs stable when CSV inference reads them as floats."""
    if pd.isna(value):
        return ""
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return str(int(value))
    text = str(value).strip()
    if text.endswith(".0"):
        maybe_number = text[:-2]
        if maybe_number.isdigit():
            return maybe_number
    return text


def tracking_report_to_frame_set(
    df_report: pd.DataFrame,
) -> MetricFrameSet:
    """
    Convert a long TrackingBaskets_v2 report into canonical wide metric frames.
    """
    report = normalize_csv_df(df_report)
    required = {
        "quadweek",
        "year_week",
        "basket",
        "StockQty_W",
        "SoldQty",
        "Margin",
        "AvgSalePrice",
        "CountProduct_W",
        "PurchaseQty",
    }
    missing = sorted(required - set(report.columns))
    if missing:
        raise ValueError(
            "TrackingBaskets_v2 report is missing required column(s): "
            + ", ".join(missing)
        )

    report = report.copy()
    for col in ["quadweek", "year_week"]:
        report[col] = report[col].astype(str).str.strip()
    report["basket"] = report["basket"].map(_normalize_basket_id)

    # Drop Total/footer/filter rows and rows without a real basket-week observation.
    report = report[
        report["quadweek"].ne("")
        & report["year_week"].ne("")
        & report["basket"].ne("")
        & report["quadweek"].str.lower().ne("total")
        & report["year_week"].str.match(r"^\d{4}-\d{1,2}$", na=False)
    ].copy()
    if report.empty:
        raise ValueError("TrackingBaskets_v2 report has no valid basket-week rows.")

    week_positions = _infer_week_in_quadweek(report[["year_week", "quadweek"]])
    week_meta = (
        report[["year_week", "quadweek"]]
        .drop_duplicates()
        .sort_values("year_week")
        .reset_index(drop=True)
    )
    week_meta["week in quad (1_4)"] = week_meta["year_week"].map(week_positions)

    df_sold = _metric_wide_frame(report, "SoldQty", week_meta, aggfunc="sum")
    df_price = _metric_wide_frame(report, "AvgSalePrice", week_meta, aggfunc="mean")
    df_m = _metric_wide_frame(report, "Margin", week_meta, aggfunc="sum")
    df_stock = _metric_wide_frame(report, "StockQty_W", week_meta, aggfunc="sum")
    df_count_product = _metric_wide_frame(report, "CountProduct_W", week_meta, aggfunc="sum")
    df_purchase = _metric_wide_frame(report, "PurchaseQty", week_meta, aggfunc="sum")
    df_recap = (
        _metric_wide_frame(report, "Recap", week_meta, aggfunc="sum")
        if "Recap" in report.columns
        else None
    )
    return MetricFrameSet(
        sold=df_sold,
        price=df_price,
        margin=df_m,
        stock=df_stock,
        count_product=df_count_product,
        purchase=df_purchase,
        recap=df_recap,
    )


def tracking_report_to_metric_frames(
    df_report: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Convert a long TrackingBaskets_v2 report into the four canonical wide frames.

    Returns frames in the same order as run_basket_analysis expects:
    (sold, price, margin, stock).
    """
    frames = tracking_report_to_frame_set(df_report)
    return frames.sold, frames.price, frames.margin, frames.stock


PRODUCT_BS_CATEGORIES: dict[str, str] = {
    "BasketDiscountInMarket": "In",
    "BasketDiscountOutOfMarket": "Out",
    "BasketDiscountOutOfMarketByCondition": "OutByCondition",
    "BasketDiscountOutOfMarketByMinPrice": "OutByMinPrice",
    "none": "none",
}


PRODUCT_BS_METRIC_COLUMNS: dict[str, dict[str, str]] = {
    "In": {
        "sold": "SoldQty_In",
        "margin": "Margin_In",
        "revenue": "Revenue_In",
        "recap": "Recap_In",
    },
    "Out": {
        "sold": "SoldQty_Out",
        "margin": "Margin_Out",
        "revenue": "Revenue_Out",
        "recap": "Recap_Out",
    },
    "OutByCondition": {
        "sold": "SoldQty_OutByCondition",
        "margin": "Margin_OutByCondition",
        "revenue": "Revenue_OutByCondition",
        "recap": "Recap_OutByCondition",
    },
    "OutByMinPrice": {
        "sold": "SoldQty_OutByMinPrice",
        "margin": "Margin_OutByMinPrice",
        "revenue": "Revenue_OutByMinPrice",
        "recap": "Recap_OutByMinPrice",
    },
    "none": {
        "sold": "SoldQty_none",
        "margin": "Margin_none",
        "revenue": "Revenue_none",
        "recap": "Recap_none",
    },
}


def _clean_tracking_product_bs_report(df_report: pd.DataFrame) -> pd.DataFrame:
    """Normalize and keep only real product-BS basket-week rows."""
    report = normalize_csv_df(df_report)
    required = {
        "quadweek",
        "year_week",
        "basket",
        "product BS",
        "StockQty_W",
        "CountProduct_W",
        "PurchaseQty",
        "SoldQty",
        "Revenue",
        "Margin",
    }
    for category_cols in PRODUCT_BS_METRIC_COLUMNS.values():
        required.update(
            col for key, col in category_cols.items() if key in {"sold", "margin", "revenue"}
        )

    missing = sorted(required - set(report.columns))
    if missing:
        raise ValueError(
            "TrackingBaskets_v2 - product_BS report is missing required column(s): "
            + ", ".join(missing)
        )

    report = report.copy()
    for col in ["quadweek", "year_week", "product BS"]:
        report[col] = report[col].astype(str).str.strip()
    report["basket"] = report["basket"].map(_normalize_basket_id)
    report["product_bs_category"] = report["product BS"].map(PRODUCT_BS_CATEGORIES)

    report = report[
        report["quadweek"].ne("")
        & report["year_week"].ne("")
        & report["basket"].ne("")
        & report["quadweek"].str.lower().ne("total")
        & report["year_week"].str.match(r"^\d{4}-\d{1,2}$", na=False)
        & report["product_bs_category"].notna()
    ].copy()
    if report.empty:
        raise ValueError("TrackingBaskets_v2 - product_BS report has no valid basket-week rows.")

    numeric_cols = {
        "StockQty_W",
        "CountProduct_W",
        "PurchaseQty",
        "SoldQty",
        "Revenue",
        "Margin",
        *[cols["sold"] for cols in PRODUCT_BS_METRIC_COLUMNS.values()],
        *[cols["revenue"] for cols in PRODUCT_BS_METRIC_COLUMNS.values()],
        *[cols["margin"] for cols in PRODUCT_BS_METRIC_COLUMNS.values()],
    }
    for col in numeric_cols:
        report[col] = pd.to_numeric(report[col], errors="coerce").fillna(0.0)

    return report


def _week_meta_from_report(report: pd.DataFrame) -> pd.DataFrame:
    """Build canonical week metadata including inferred week-in-quadweek."""
    week_positions = _infer_week_in_quadweek(report[["year_week", "quadweek"]])
    week_meta = (
        report[["year_week", "quadweek"]]
        .drop_duplicates()
        .sort_values("year_week")
        .reset_index(drop=True)
    )
    week_meta["week in quad (1_4)"] = week_meta["year_week"].map(week_positions)
    return week_meta


def _wide_from_values(
    values: pd.DataFrame,
    value_col: str,
    week_meta: pd.DataFrame,
) -> pd.DataFrame:
    """Pivot year_week/basket/value rows to the canonical wide frame shape."""
    if values.empty:
        return week_meta.copy()
    wide = (
        values.pivot_table(
            index="year_week",
            columns="basket",
            values=value_col,
            aggfunc="sum",
        )
        .reset_index()
    )
    wide.columns = [str(c).strip() for c in wide.columns]
    return week_meta.merge(wide, on="year_week", how="left")


def _group_metric_values(
    report: pd.DataFrame,
    value_col: str,
    output_col: str,
) -> pd.DataFrame:
    """Sum a metric by basket-week."""
    return (
        report.groupby(["year_week", "basket"], as_index=False)[value_col]
        .sum()
        .rename(columns={value_col: output_col})
    )


def _optional_group_metric_values(
    report: pd.DataFrame,
    value_col: str,
    output_col: str,
) -> Optional[pd.DataFrame]:
    """Sum a metric by basket-week when the source column exists."""
    if not value_col or value_col not in report.columns:
        return None
    return _group_metric_values(report, value_col, output_col)


def _frame_set_from_grouped_values(
    sold: pd.DataFrame,
    revenue: pd.DataFrame,
    margin: pd.DataFrame,
    stock: pd.DataFrame,
    week_meta: pd.DataFrame,
    count_product: Optional[pd.DataFrame] = None,
    purchase: Optional[pd.DataFrame] = None,
    recap: Optional[pd.DataFrame] = None,
) -> MetricFrameSet:
    """Create canonical sold/price/margin/stock frames from grouped values."""
    price = sold.merge(revenue, on=["year_week", "basket"], how="outer").fillna(0.0)
    price["price"] = np.where(
        price["sold"].abs() > 1e-10,
        price["revenue"] / price["sold"],
        0.0,
    )

    return MetricFrameSet(
        sold=_wide_from_values(sold, "sold", week_meta),
        price=_wide_from_values(price[["year_week", "basket", "price"]], "price", week_meta),
        margin=_wide_from_values(margin, "margin", week_meta),
        stock=_wide_from_values(stock, "stock", week_meta),
        count_product=(
            _wide_from_values(count_product, "count_product", week_meta)
            if count_product is not None else None
        ),
        purchase=(
            _wide_from_values(purchase, "purchase", week_meta)
            if purchase is not None else None
        ),
        recap=(
            _wide_from_values(recap, "recap", week_meta)
            if recap is not None else None
        ),
    )


def _mismatch_warnings(
    raw: pd.DataFrame,
    derived: pd.DataFrame,
    metric_label: str,
    tolerance: float = 0.1,
) -> list[str]:
    """Compare raw aggregate metric to sum of category metrics by basket-week."""
    cmp = raw.merge(
        derived,
        on=["year_week", "basket"],
        how="outer",
        suffixes=("_raw", "_derived"),
    ).fillna(0.0)
    raw_col = f"{metric_label}_raw"
    derived_col = f"{metric_label}_derived"
    bad = cmp[(cmp[raw_col] - cmp[derived_col]).abs() > tolerance]
    if bad.empty:
        return []

    examples = [
        f"{row.year_week}/{row.basket}: raw={getattr(row, raw_col):.2f}, categories={getattr(row, derived_col):.2f}"
        for row in bad.head(3).itertuples(index=False)
    ]
    return [
        (
            f"Warning: {metric_label} aggregate mismatch for {len(bad)} basket-week row(s); "
            f"using sum of category columns. Examples: " + "; ".join(examples)
        )
    ]


def tracking_product_bs_report_to_frame_sets(
    df_report: pd.DataFrame,
    use_monthly_average_metrics: bool = False,
) -> ProductBSTransformResult:
    """
    Convert a TrackingBaskets_v2 - product_BS report into category and aggregate frames.

    Default mode ("on date of sale"):
    Category Sold/Margin/Revenue are summed from their suffix columns across all
    product-BS rows for each basket-week. Aggregate Sold/Margin/Revenue use the
    unsuffixed report totals.

    Monthly-average mode:
    Category Sold/Margin/Revenue are summed from the unsuffixed SoldQty, Margin,
    and Revenue columns on rows matching that product-BS category.

    In both modes, category Stock/CountProduct/Purchase come from rows matching
    that product-BS category. Avg Price is always Revenue / Sold.
    """
    report = _clean_tracking_product_bs_report(df_report)
    week_meta = _week_meta_from_report(report)
    categories: dict[str, MetricFrameSet] = {}
    warnings: list[str] = []

    category_sold_values: list[pd.DataFrame] = []
    category_margin_values: list[pd.DataFrame] = []
    category_revenue_values: list[pd.DataFrame] = []
    category_count_product_values: list[pd.DataFrame] = []
    category_purchase_values: list[pd.DataFrame] = []
    suffix_sold_values: list[pd.DataFrame] = []
    suffix_margin_values: list[pd.DataFrame] = []
    suffix_revenue_values: list[pd.DataFrame] = []

    for category, cols in PRODUCT_BS_METRIC_COLUMNS.items():
        category_report = report[report["product_bs_category"] == category]
        if use_monthly_average_metrics:
            sold = _group_metric_values(category_report, "SoldQty", "sold")
            revenue = _group_metric_values(category_report, "Revenue", "revenue")
            margin = _group_metric_values(category_report, "Margin", "margin")
        else:
            sold = _group_metric_values(report, cols["sold"], "sold")
            revenue = _group_metric_values(report, cols["revenue"], "revenue")
            margin = _group_metric_values(report, cols["margin"], "margin")
            suffix_sold_values.append(sold)
            suffix_margin_values.append(margin)
            suffix_revenue_values.append(revenue)
        stock = _group_metric_values(
            category_report,
            "StockQty_W",
            "stock",
        )
        count_product = _group_metric_values(
            category_report,
            "CountProduct_W",
            "count_product",
        )
        purchase = _group_metric_values(
            category_report,
            "PurchaseQty",
            "purchase",
        )
        if use_monthly_average_metrics:
            recap = _optional_group_metric_values(category_report, "Recap", "recap")
        else:
            recap = _optional_group_metric_values(report, cols.get("recap", ""), "recap")

        categories[category] = _frame_set_from_grouped_values(
            sold=sold,
            revenue=revenue,
            margin=margin,
            stock=stock,
            week_meta=week_meta,
            count_product=count_product,
            purchase=purchase,
            recap=recap,
        )
        category_sold_values.append(sold)
        category_margin_values.append(margin)
        category_revenue_values.append(revenue)
        category_count_product_values.append(count_product)
        category_purchase_values.append(purchase)

    def _sum_category_metric(frames: list[pd.DataFrame], value_col: str) -> pd.DataFrame:
        combined = pd.concat(frames, ignore_index=True)
        return combined.groupby(["year_week", "basket"], as_index=False)[value_col].sum()

    aggregate_sold = _group_metric_values(report, "SoldQty", "sold")
    aggregate_margin = _group_metric_values(report, "Margin", "margin")
    aggregate_revenue = _group_metric_values(report, "Revenue", "revenue")
    aggregate_stock = _group_metric_values(report, "StockQty_W", "stock")
    aggregate_count_product = _group_metric_values(report, "CountProduct_W", "count_product")
    aggregate_purchase = _group_metric_values(report, "PurchaseQty", "purchase")
    aggregate_recap = _optional_group_metric_values(report, "Recap", "recap")

    if not use_monthly_average_metrics:
        suffix_sold = _sum_category_metric(suffix_sold_values, "sold")
        suffix_margin = _sum_category_metric(suffix_margin_values, "margin")
        suffix_revenue = _sum_category_metric(suffix_revenue_values, "revenue")
        warnings.extend(_mismatch_warnings(aggregate_sold, suffix_sold, "sold"))
        warnings.extend(_mismatch_warnings(aggregate_margin, suffix_margin, "margin"))
        warnings.extend(_mismatch_warnings(aggregate_revenue, suffix_revenue, "revenue"))

    aggregate = _frame_set_from_grouped_values(
        sold=aggregate_sold,
        revenue=aggregate_revenue,
        margin=aggregate_margin,
        stock=aggregate_stock,
        week_meta=week_meta,
        count_product=aggregate_count_product,
        purchase=aggregate_purchase,
        recap=aggregate_recap,
    )

    return ProductBSTransformResult(
        aggregate=aggregate,
        categories=categories,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Per-basket stock trend metrics
# ---------------------------------------------------------------------------

def _slr_slope(x: list[float], y: list[float]) -> Optional[float]:
    """Simple Linear Regression slope (for stock trend within quadweeks)."""
    n = len(x)
    if n < 2:
        return None
    x_arr = np.array(x, dtype=float)
    y_arr = np.array(y, dtype=float)
    sum_x = x_arr.sum()
    sum_y = y_arr.sum()
    sum_xy = (x_arr * y_arr).sum()
    sum_xx = (x_arr * x_arr).sum()
    denom = n * sum_xx - sum_x * sum_x
    if abs(denom) < 1e-10:
        return None
    return float((n * sum_xy - sum_x * sum_y) / denom)


def compute_stock_trend_metrics(
    stock: list[float],
    quadweeks: list[str],
) -> tuple[float, float]:
    """
    Compute two stock-trend metrics:
    - av_dstock_w_qw: average linear slope of stock *within* each quadweek
      (requires exactly 4 data points per quadweek to be computed).
    - av_dstock_b_qw: average stock jump *between* adjacent quadweeks
      (first difference at each quadweek boundary).

    Returns (av_dstock_w_qw, av_dstock_b_qw) — NaN when not enough data.
    """
    # --- Within-quadweek slope ---
    qw_groups: dict[str, list[int]] = {}
    for i, qw in enumerate(quadweeks):
        if qw and qw != "N/A":
            qw_groups.setdefault(qw, []).append(i)

    slopes_within: list[float] = []
    for indices in qw_groups.values():
        if len(indices) == 4:
            y_vals = [stock[idx] for idx in indices]
            slope = _slr_slope([0.0, 1.0, 2.0, 3.0], y_vals)
            if slope is not None:
                slopes_within.append(slope)

    av_w = float(np.mean(slopes_within)) if slopes_within else float("nan")

    # --- Between-quadweek jump ---
    diffs_between: list[float] = []
    for i in range(1, len(quadweeks)):
        prev_qw = quadweeks[i - 1]
        curr_qw = quadweeks[i]
        if (
            prev_qw and curr_qw
            and prev_qw != "N/A" and curr_qw != "N/A"
            and prev_qw != curr_qw
        ):
            diffs_between.append(stock[i] - stock[i - 1])

    av_b = float(np.mean(diffs_between)) if diffs_between else float("nan")

    return av_w, av_b


# ---------------------------------------------------------------------------
# Main basket transformation
# ---------------------------------------------------------------------------

def compute_basket_features(
    sold_dict: dict[str, pd.Series],
    price_dict: dict[str, pd.Series],
    m_dict: dict[str, pd.Series],
    stock_dict: dict[str, pd.Series],
    baskets: list[str],
    weeks: list[str],
    min_sold: float = -math.inf,
    max_sold: float = math.inf,
    min_price: float = -math.inf,
    max_price: float = math.inf,
    min_m: float = -math.inf,
    max_m: float = math.inf,
    count_product_dict: Optional[dict[str, pd.Series]] = None,
    purchase_dict: Optional[dict[str, pd.Series]] = None,
    recap_dict: Optional[dict[str, pd.Series]] = None,
) -> tuple[list[BasketResult], dict[str, BasketTimeSeries]]:
    """
    Core ETL: build per-basket summary results and time series.

    Parameters
    ----------
    sold_dict, price_dict, m_dict, stock_dict:
        {year_week -> row Series} dicts produced by index_by_week().
    baskets:
        List of basket column names.
    weeks:
        Sorted list of common year_week keys.
    min_*/max_*:
        Preprocessing filter bounds; data points outside are excluded.

    Returns
    -------
    (list[BasketResult], dict[basket_name -> BasketTimeSeries])
    """
    results: list[BasketResult] = []
    basket_data: dict[str, BasketTimeSeries] = {}

    for basket in baskets:
        arr_sold: list[float] = []
        arr_price: list[float] = []
        arr_m: list[float] = []
        arr_stock: list[float] = []
        arr_count_product: list[float] = []
        arr_purchase: list[float] = []
        arr_recap: list[float] = []
        arr_cost: list[float] = []
        arr_weeks: list[str] = []
        arr_qw: list[str] = []
        arr_week_in_quad: list[int] = []

        sum_sold = 0.0
        sum_m = 0.0
        sum_sold_price = 0.0
        sum_stock = 0.0
        sum_count_product = 0.0
        sum_purchase = 0.0

        for w in weeks:
            try:
                s = float(sold_dict[w][basket])
                p = float(price_dict[w][basket])
                mv = float(m_dict[w][basket])
                stk = float(stock_dict[w][basket])
            except (KeyError, ValueError, TypeError):
                continue

            cp = float("nan")
            pur = float("nan")
            rec = float("nan")
            try:
                if count_product_dict is not None:
                    cp = float(count_product_dict[w][basket])
                if purchase_dict is not None:
                    pur = float(purchase_dict[w][basket])
                if recap_dict is not None:
                    rec = float(recap_dict[w][basket])
            except (KeyError, ValueError, TypeError):
                pass

            if any(math.isnan(v) for v in (s, p, mv, stk)):
                continue

            if not (min_sold <= s <= max_sold):
                continue
            if not (min_price <= p <= max_price):
                continue
            if not (min_m <= mv <= max_m):
                continue

            cost = ((s * p) - mv) / s if s > 0 else 0.0

            arr_sold.append(s)
            arr_price.append(p)
            arr_m.append(mv)
            arr_stock.append(stk)
            arr_count_product.append(cp)
            arr_purchase.append(pur)
            arr_recap.append(rec)
            arr_cost.append(cost)
            arr_weeks.append(w)
            arr_qw.append(str(sold_dict[w].get("quadweek", "N/A")).strip() or "N/A")
            try:
                week_in_quad = int(float(sold_dict[w].get("week in quad (1_4)", 0)))
            except (ValueError, TypeError):
                week_in_quad = 0
            arr_week_in_quad.append(week_in_quad)

            sum_sold += s
            sum_m += mv
            sum_sold_price += s * p
            sum_stock += stk
            if not math.isnan(cp):
                sum_count_product += cp
            if not math.isnan(pur):
                sum_purchase += pur

        if not arr_sold:
            continue

        corrs = compute_basket_correlations(arr_sold, arr_price, arr_m)
        av_w, av_b = compute_stock_trend_metrics(arr_stock, arr_qw)
        n = len(arr_sold)
        avg_count_product = (
            sum_count_product / sum(not math.isnan(v) for v in arr_count_product)
            if any(not math.isnan(v) for v in arr_count_product)
            else float("nan")
        )
        result = BasketResult(
            basket=str(basket),
            total_sold=sum_sold,
            total_m=sum_m,
            total_sold_price=sum_sold_price,
            weighted_price=sum_sold_price / sum_sold if sum_sold > 0 else 0.0,
            average_stock=sum_stock / n,
            average_count_product=avg_count_product,
            total_purchase=sum_purchase if any(not math.isnan(v) for v in arr_purchase) else float("nan"),
            corr_SP=corrs["corr_SP"],
            corr_MP=corrs["corr_MP"],
            corr_MS=corrs["corr_MS"],
            av_dstock_w_qw=av_w,
            av_dstock_b_qw=av_b,
            coords=[
                safe_correlation_coord(corrs["corr_SP"]),
                safe_correlation_coord(corrs["corr_MP"]),
                safe_correlation_coord(corrs["corr_MS"]),
            ],
            group=0,
        )
        results.append(result)

        basket_data[str(basket)] = BasketTimeSeries(
            basket=str(basket),
            weeks=arr_weeks,
            quadweeks=arr_qw,
            sold=arr_sold,
            price=arr_price,
            m=arr_m,
            stock=arr_stock,
            cost=arr_cost,
            count_product=arr_count_product,
            purchase=arr_purchase,
            recap=arr_recap,
            week_in_quad=arr_week_in_quad,
        )

    return results, basket_data


# ---------------------------------------------------------------------------
# Weekly aggregate computation
# ---------------------------------------------------------------------------

def compute_weekly_totals(
    sold_dict: dict[str, pd.Series],
    price_dict: dict[str, pd.Series],
    m_dict: dict[str, pd.Series],
    stock_dict: dict[str, pd.Series],
    basket_data: dict[str, BasketTimeSeries],
    weeks: list[str],
) -> dict[str, WeeklyTotal]:
    """
    Aggregate per-week totals across all valid baskets.

    Only includes weeks and baskets that passed the per-basket filter
    (i.e., baskets present in basket_data).
    """
    totals: dict[str, WeeklyTotal] = {
        w: WeeklyTotal(
            week=w,
            sum_sold=0.0,
            sum_m=0.0,
            sum_sold_price=0.0,
            sum_stock=0.0,
            valid_baskets=0,
        )
        for w in weeks
    }

    for basket, ts in basket_data.items():
        for i, w in enumerate(ts.weeks):
            if w not in totals:
                continue
            totals[w].sum_sold += ts.sold[i]
            totals[w].sum_m += ts.m[i]
            totals[w].sum_sold_price += ts.sold[i] * ts.price[i]
            totals[w].sum_stock += ts.stock[i]
            if i < len(ts.count_product) and not math.isnan(ts.count_product[i]):
                totals[w].sum_count_product += ts.count_product[i]
            if i < len(ts.purchase) and not math.isnan(ts.purchase[i]):
                totals[w].sum_purchase += ts.purchase[i]
            recap_values = getattr(ts, "recap", None) or []
            if i < len(recap_values) and not math.isnan(recap_values[i]):
                totals[w].sum_recap += recap_values[i]
            totals[w].valid_baskets += 1
            if totals[w].quadweek == "N/A":
                totals[w].quadweek = str(ts.quadweeks[i])
            if totals[w].week_in_quad == 0 and i < len(ts.week_in_quad):
                totals[w].week_in_quad = ts.week_in_quad[i]
            totals[w].points.append(
                WeeklyPoint(
                    basket=basket,
                    sold=ts.sold[i],
                    price=ts.price[i],
                    m=ts.m[i],
                    stock=ts.stock[i],
                    count_product=(
                        ts.count_product[i]
                        if i < len(ts.count_product) and not math.isnan(ts.count_product[i])
                        else 0.0
                    ),
                    purchase=(
                        ts.purchase[i]
                        if i < len(ts.purchase) and not math.isnan(ts.purchase[i])
                        else 0.0
                    ),
                    recap=(
                        recap_values[i]
                        if i < len(recap_values) and not math.isnan(recap_values[i])
                        else 0.0
                    ),
                )
            )

    return {w: t for w, t in totals.items() if t.valid_baskets > 0}


# ---------------------------------------------------------------------------
# Discount history report (discount + prom by basket / week / product BS)
# ---------------------------------------------------------------------------

DISCOUNT_HIST_DISCOUNT_COLUMNS: dict[str, str] = {
    "Aggregated": "discount",
    "In": "BasketDiscountInMarket",
    "Out": "BasketDiscountOutOfMarket",
    "OutByCondition": "BasketDiscountOutOfMarketByCondition",
    "OutByMinPrice": "BasketDiscountOutOfMarketByMinPrice",
    "none": "none",
}

DISCOUNT_HIST_PROM_COLUMNS: dict[str, str] = {
    "Aggregated": "prom with stock",
    "In": "Prom, BasketDiscountInMarket",
    "Out": "Prom, BasketDiscountOutOfMarket",
    "OutByCondition": "Prom, BasketDiscountOutOfMarketByCondition",
    "OutByMinPrice": "Prom, BasketDiscountOutOfMarketByMinPrice",
    "none": "Prom, none",
}

DISCOUNT_HIST_EXPORT_COLUMNS: list[str] = [
    "quadweek",
    "year_week",
    "week from y_w (1_52)",
    "week in quad (1_4)",
    "",
    "basket",
    "discount",
    "BasketDiscountInMarket",
    "BasketDiscountOutOfMarket",
    "BasketDiscountOutOfMarketByCondition",
    "BasketDiscountOutOfMarketByMinPrice",
    "none",
    "prom with stock",
    "Prom, BasketDiscountInMarket",
    "Prom, BasketDiscountOutOfMarket",
    "Prom, BasketDiscountOutOfMarketByCondition",
    "Prom, BasketDiscountOutOfMarketByMinPrice",
    "Prom, none",
]

# Discount / prom value columns only (exclude week + basket metadata).
DISCOUNT_HIST_VALUE_COLUMNS: list[str] = [
    col for col in DISCOUNT_HIST_EXPORT_COLUMNS
    if col not in {
        "quadweek",
        "year_week",
        "week from y_w (1_52)",
        "week in quad (1_4)",
        "",
        "basket",
    }
]

# Preferred category order when combining Product BS exports.
DISCOUNT_HIST_CATEGORY_ORDER: list[str] = [
    "Aggregated",
    "In",
    "Out",
    "OutByCondition",
    "OutByMinPrice",
    "none",
]


def _parse_year_week_parts(year_week: str) -> tuple[int, int, str]:
    """Return (year, week_number, separator) from strings like 2026-25 or 2026_25."""
    text = str(year_week).strip()
    for sep in ("-", "_"):
        if sep in text:
            year_raw, week_raw = text.split(sep, 1)
            return int(year_raw), int(week_raw), sep
    raise ValueError(f"Cannot parse year_week value: {year_week!r}")


def advance_discount_hist_week_metadata(
    weekly_totals: dict[str, WeeklyTotal],
    selected_week: str,
) -> dict[str, object]:
    """
    Advance week metadata by one step for discount-history export.

    Rules:
    - week from y_w: +1 (wrap 52 -> 1, increment year)
    - year_week: same separator as source, updated year/week
    - week in quad: 1..4 cycle (4 -> 1)
    - quadweek: +1 only when new week in quad is 1
    """
    wt = weekly_totals.get(str(selected_week))
    if wt is None:
        raise ValueError(f"Unknown week {selected_week!r}.")

    year, week_num, sep = _parse_year_week_parts(str(selected_week))
    new_week_num = week_num + 1
    new_year = year
    if new_week_num > 52:
        new_year += 1
        new_week_num = 1

    week_in_quad = int(wt.week_in_quad) if wt.week_in_quad else 1
    new_week_in_quad = 1 if week_in_quad >= 4 else week_in_quad + 1

    try:
        qw_int = int(str(wt.quadweek).strip())
    except (TypeError, ValueError):
        qw_int = None

    if new_week_in_quad == 1 and qw_int is not None:
        new_quadweek: object = qw_int + 1
    elif qw_int is not None:
        new_quadweek = qw_int
    else:
        new_quadweek = wt.quadweek

    return {
        "quadweek": new_quadweek,
        "year_week": f"{new_year}{sep}{new_week_num}",
        "week from y_w (1_52)": new_week_num,
        "week in quad (1_4)": new_week_in_quad,
    }


def _format_discount_hist_export_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)


def build_discount_hist_export_rows(
    week_discount_rows: list[dict],
    week_meta: dict[str, object],
    discount_category: str,
    *,
    new_discount_column: str = "New Discount",
    new_prom_column: str = "New Prom",
) -> list[dict]:
    """
    Build discount-history CSV rows from Week Discount New Discount / New Prom.

    Only the active category discount/prom columns are populated; other columns
    stay empty. Week columns use *week_meta* (typically selected week + 1).
    """
    if discount_category not in DISCOUNT_HIST_DISCOUNT_COLUMNS:
        valid = ", ".join(sorted(DISCOUNT_HIST_DISCOUNT_COLUMNS))
        raise ValueError(
            f"Unknown discount history category {discount_category!r}. Expected: {valid}."
        )

    discount_col = DISCOUNT_HIST_DISCOUNT_COLUMNS[discount_category]
    prom_col = DISCOUNT_HIST_PROM_COLUMNS[discount_category]
    hist_rows: list[dict] = []

    for row in week_discount_rows:
        basket = str(row.get("Basket", "")).strip()
        if not basket:
            continue

        hist_row: dict[str, object] = {col: "" for col in DISCOUNT_HIST_EXPORT_COLUMNS}
        hist_row["quadweek"] = week_meta["quadweek"]
        hist_row["year_week"] = week_meta["year_week"]
        hist_row["week from y_w (1_52)"] = week_meta["week from y_w (1_52)"]
        hist_row["week in quad (1_4)"] = week_meta["week in quad (1_4)"]
        hist_row[""] = ""
        hist_row["basket"] = basket

        discount_val = row.get(new_discount_column)
        prom_val = row.get(new_prom_column)
        if not (
            discount_val is None
            or (isinstance(discount_val, float) and math.isnan(discount_val))
        ):
            hist_row[discount_col] = _format_discount_hist_export_value(discount_val)
        if not (
            prom_val is None
            or (isinstance(prom_val, float) and math.isnan(prom_val))
        ):
            hist_row[prom_col] = _format_discount_hist_export_value(prom_val)

        hist_rows.append(hist_row)

    return hist_rows


def _source_row_to_discount_hist_export(row: pd.Series) -> dict[str, object] | None:
    """Convert one normalized discount-history source row to export format."""
    basket = _normalize_basket_id(row.get("basket"))
    week = str(row.get("year_week", "")).strip()
    if not basket or not week:
        return None

    lower_to_actual = {str(c).strip().lower(): c for c in row.index}
    hist_row: dict[str, object] = {col: "" for col in DISCOUNT_HIST_EXPORT_COLUMNS}
    for export_col in DISCOUNT_HIST_EXPORT_COLUMNS:
        if export_col == "":
            blank_col = next(
                (
                    row.index[i]
                    for i, c in enumerate(row.index)
                    if str(c).strip() == "" or str(c).startswith("Unnamed")
                ),
                None,
            )
            if blank_col is not None:
                val = row.get(blank_col)
                hist_row[""] = "" if val is None or (isinstance(val, float) and math.isnan(val)) else val
            continue
        source_col = lower_to_actual.get(export_col.strip().lower())
        if source_col is None:
            continue
        val = row.get(source_col)
        if val is None or (isinstance(val, float) and math.isnan(val)):
            hist_row[export_col] = ""
        else:
            hist_row[export_col] = val

    hist_row["basket"] = basket
    hist_row["year_week"] = week
    return hist_row


def merge_discount_hist_export(
    source_df: pd.DataFrame | None,
    new_rows: list[dict],
    *,
    include_all_history: bool,
) -> list[dict]:
    """
    Combine uploaded discount history with exported New Discount / New Prom rows.

    When *include_all_history* is False, returns *new_rows* only.
    When True, keeps all source rows except basket-week keys overridden by *new_rows*.
    """
    if not include_all_history or not new_rows:
        return new_rows
    if source_df is None or source_df.empty:
        return new_rows

    new_by_key = {
        (str(row.get("year_week", "")).strip(), str(row.get("basket", "")).strip()): row
        for row in new_rows
        if str(row.get("basket", "")).strip()
    }

    merged: list[dict] = []
    report = normalize_csv_df(source_df)
    for _, row in report.iterrows():
        hist_row = _source_row_to_discount_hist_export(row)
        if hist_row is None:
            continue
        key = (str(hist_row["year_week"]), str(hist_row["basket"]))
        if key in new_by_key:
            continue
        merged.append(hist_row)

    merged.extend(new_by_key.values())
    merged.sort(
        key=lambda r: (
            str(r.get("year_week", "")),
            len(str(r.get("basket", ""))),
            str(r.get("basket", "")),
        ),
    )
    return merged


def _is_blank_discount_hist_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    text = str(value).strip()
    return not text or text.lower() in {"n/a", "na", "nan"}


def _prefer_discount_hist_value(current: object, incoming: object) -> object:
    """Keep non-blank values; later files overwrite earlier non-blank values."""
    if _is_blank_discount_hist_value(incoming):
        return "" if _is_blank_discount_hist_value(current) else current
    return incoming


def merge_discount_hist_dataframes(
    dataframes: list[pd.DataFrame],
) -> pd.DataFrame:
    """
    Aggregate one or more discount-history CSVs into a single wide table.

    Rows are keyed by ``(year_week, basket)``. Non-empty discount/prom cells from
    later files overwrite earlier ones for the same key/column. Metadata for a
    key is taken from the first non-empty source, updated when a later file
    supplies the same key.
    """
    if not dataframes:
        return pd.DataFrame(columns=DISCOUNT_HIST_EXPORT_COLUMNS)

    merged_by_key: dict[tuple[str, str], dict[str, object]] = {}
    for df in dataframes:
        if df is None or df.empty:
            continue
        report = normalize_csv_df(df)
        for _, row in report.iterrows():
            hist_row = _source_row_to_discount_hist_export(row)
            if hist_row is None:
                continue
            key = (str(hist_row["year_week"]), str(hist_row["basket"]))
            if key not in merged_by_key:
                merged_by_key[key] = hist_row
                continue
            existing = merged_by_key[key]
            for col in DISCOUNT_HIST_EXPORT_COLUMNS:
                if col in {"year_week", "basket"}:
                    continue
                if col in DISCOUNT_HIST_VALUE_COLUMNS:
                    existing[col] = _prefer_discount_hist_value(
                        existing.get(col),
                        hist_row.get(col),
                    )
                elif _is_blank_discount_hist_value(existing.get(col)) and not (
                    _is_blank_discount_hist_value(hist_row.get(col))
                ):
                    existing[col] = hist_row[col]

    if not merged_by_key:
        return pd.DataFrame(columns=DISCOUNT_HIST_EXPORT_COLUMNS)

    rows = list(merged_by_key.values())
    rows.sort(
        key=lambda r: (
            str(r.get("year_week", "")),
            len(str(r.get("basket", ""))),
            str(r.get("basket", "")),
        ),
    )
    return pd.DataFrame(rows, columns=DISCOUNT_HIST_EXPORT_COLUMNS)


def combine_discount_hist_export_by_category(
    category_rows: dict[str, list[dict]],
) -> list[dict]:
    """
    Combine per–Product-BS-category export row lists into one row per basket.

    Each category list should already use the shared next-week metadata.
    Category-specific discount/prom columns are merged; blank cells do not
    overwrite non-blank values from another category.
    """
    if not category_rows:
        return []

    ordered_categories = [
        cat for cat in DISCOUNT_HIST_CATEGORY_ORDER if cat in category_rows
    ]
    ordered_categories.extend(
        sorted(cat for cat in category_rows if cat not in DISCOUNT_HIST_CATEGORY_ORDER)
    )

    combined_by_basket: dict[str, dict[str, object]] = {}
    for category in ordered_categories:
        if category not in DISCOUNT_HIST_DISCOUNT_COLUMNS:
            raise ValueError(
                f"Unknown discount history category {category!r}. "
                f"Expected: {', '.join(sorted(DISCOUNT_HIST_DISCOUNT_COLUMNS))}."
            )
        discount_col = DISCOUNT_HIST_DISCOUNT_COLUMNS[category]
        prom_col = DISCOUNT_HIST_PROM_COLUMNS[category]
        for row in category_rows.get(category) or []:
            basket = str(row.get("basket", "")).strip()
            if not basket:
                continue
            if basket not in combined_by_basket:
                base = {col: "" for col in DISCOUNT_HIST_EXPORT_COLUMNS}
                for meta_col in (
                    "quadweek",
                    "year_week",
                    "week from y_w (1_52)",
                    "week in quad (1_4)",
                    "",
                    "basket",
                ):
                    base[meta_col] = row.get(meta_col, "")
                base["basket"] = basket
                combined_by_basket[basket] = base
            target = combined_by_basket[basket]
            for col in (discount_col, prom_col):
                target[col] = _prefer_discount_hist_value(
                    target.get(col),
                    row.get(col),
                )
            for meta_col in (
                "quadweek",
                "year_week",
                "week from y_w (1_52)",
                "week in quad (1_4)",
            ):
                if _is_blank_discount_hist_value(target.get(meta_col)) and not (
                    _is_blank_discount_hist_value(row.get(meta_col))
                ):
                    target[meta_col] = row[meta_col]

    rows = list(combined_by_basket.values())
    rows.sort(key=lambda r: (len(str(r.get("basket", ""))), str(r.get("basket", ""))))
    return rows


def _parse_discount_hist_discount_value(raw: object) -> float:
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return float("nan")
    text = str(raw).strip()
    if not text or text.lower() in {"n/a", "na", "nan"}:
        return float("nan")
    try:
        return float(text.replace("%", "").replace(",", ""))
    except ValueError:
        return float("nan")


def _parse_discount_hist_prom_value(raw: object) -> float:
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return float("nan")
    text = str(raw).strip()
    if not text or text.lower() in {"n/a", "na", "nan"}:
        return 0.0
    try:
        value = float(text.replace("%", "").replace(",", ""))
    except ValueError:
        return float("nan")
    if value < 0:
        return float("nan")
  # Valid prom steps: 0, 0.02, 0.04, 0.06, … (not 0.01 / 0.03)
    cents = round(value * 100)
    if cents % 2 != 0:
        return float("nan")
    return value


def parse_discount_hist_lookup(
    df_report: pd.DataFrame,
    product_bs_category: str,
) -> tuple[dict[tuple[str, str], tuple[float, float]], list[str]]:
    """
  Parse a discount history CSV into {(basket, year_week): (discount, prom)}.

  Column selection follows the active product BS category.
  """
    if product_bs_category not in DISCOUNT_HIST_DISCOUNT_COLUMNS:
        valid = ", ".join(sorted(DISCOUNT_HIST_DISCOUNT_COLUMNS))
        raise ValueError(
            f"Unknown product_BS category '{product_bs_category}'. Expected one of: {valid}."
        )

    report = normalize_csv_df(df_report)
    required = {"year_week", "basket"}
    missing = sorted(required - set(report.columns))
    if missing:
        raise ValueError(
            "Discount history report is missing required column(s): " + ", ".join(missing)
        )

    discount_col = DISCOUNT_HIST_DISCOUNT_COLUMNS[product_bs_category]
    prom_col = DISCOUNT_HIST_PROM_COLUMNS[product_bs_category]
    if discount_col not in report.columns:
        raise ValueError(
            f"Discount history report is missing discount column '{discount_col}'."
        )
    if prom_col not in report.columns:
        raise ValueError(
            f"Discount history report is missing prom column '{prom_col}'."
        )

    lookup: dict[tuple[str, str], tuple[float, float]] = {}
    warnings: list[str] = []
    for _, row in report.iterrows():
        basket = _normalize_basket_id(row.get("basket"))
        week = str(row.get("year_week", "")).strip()
        if not basket or not week:
            continue
        discount = _parse_discount_hist_discount_value(row.get(discount_col))
        prom = _parse_discount_hist_prom_value(row.get(prom_col))
        lookup[(basket, week)] = (discount, prom)

    if not lookup:
        warnings.append("Discount history report produced no basket-week rows.")

    return lookup, warnings


# ---------------------------------------------------------------------------
# Full basket list (canonical 625-basket universe)
# ---------------------------------------------------------------------------

def parse_full_basket_list(df: pd.DataFrame) -> list[str]:
    """
    Parse a single-column CSV of basket IDs into a sorted unique list.

    Accepts a header named ``basket`` (case-insensitive) or a single unnamed column.
    """
    report = normalize_csv_df(df)
    if report.empty:
        return []

    if len(report.columns) == 1:
        col = report.columns[0]
    else:
        lower_map = {str(c).strip().lower(): c for c in report.columns}
        if "basket" not in lower_map:
            raise ValueError(
                "Full basket list CSV must have a 'basket' column or a single column."
            )
        col = lower_map["basket"]

    baskets: list[str] = []
    seen: set[str] = set()
    for value in report[col]:
        basket = _normalize_basket_id(value)
        if not basket or basket in seen:
            continue
        seen.add(basket)
        baskets.append(basket)

    return sorted(baskets, key=lambda b: (len(b), b))
