"""
Per Product BS category session isolation for Streamlit UI state.

Each scope (input mode + product BS category) keeps its own analysis, drill-down
selections, fits, and derived Week Discount values.
"""

from __future__ import annotations

import copy
from typing import Any

TRACKING_REPORT_MODE = "TrackingBaskets_v2 report"
PRODUCT_BS_ON_DATE_MODE = "TrackingBaskets_v2 - product_BS. on date of sale"
PRODUCT_BS_MONTHLY_AV_MODE = "TrackingBaskets_v2 - product_BS. monthly av."
PRODUCT_BS_INPUT_MODES = frozenset({
    PRODUCT_BS_ON_DATE_MODE,
    PRODUCT_BS_MONTHLY_AV_MODE,
})
# Discount history columns for non–product-BS report input (no In/Out split).
AGGREGATED_DISCOUNT_HIST_CATEGORY = "Aggregated"

PRODUCT_BS_CATEGORY_OPTIONS: list[str] = [
    "Aggregated",
    "In",
    "Out",
    "OutByCondition",
    "OutByMinPrice",
    "none",
]


def product_bs_scope_key(input_mode: str, product_bs_category: str) -> str:
    """Stable key for namespacing session state and widgets."""
    if input_mode in PRODUCT_BS_INPUT_MODES:
        return f"pbs::{input_mode}::{product_bs_category}"
    return f"mode::{input_mode}"


def scoped_widget_key(scope_key: str, widget_key: str) -> str:
    return f"{scope_key}::{widget_key}"


def default_product_bs_scope_state() -> dict[str, Any]:
    return {
        "analysis": None,
        "selected_basket": None,
        "selected_baskets": [],
        "selected_week": None,
        "show_line": False,
        "show_qw_colors": False,
        "show_qw_average": False,
        "fit_sold": {},
        "fit_sold_m": {},
        "fit_cost": {},
        "bulk_fit_price_sold": {},
        "bulk_fit_price_stock_sold": {},
        "bulk_fit_cost_price": {},
        "fit_sumup_cost": None,
        "fit_sumup_stock_sold": None,
        "sumup_margin_model": None,
        "margin_model": {},
        "sumup_select_generation": 0,
        "build_message": None,
        "discount_hist_df": None,
    }


def get_product_bs_scope(session_state: Any, scope_key: str) -> dict[str, Any]:
    if "_pbs_scopes" not in session_state:
        session_state._pbs_scopes = {}
    scopes: dict[str, dict[str, Any]] = session_state._pbs_scopes
    if scope_key not in scopes:
        scopes[scope_key] = copy.deepcopy(default_product_bs_scope_state())
    return scopes[scope_key]


def clear_product_bs_scope_derived(scope: dict[str, Any]) -> None:
    """Reset selections and derived UI state after a rebuild."""
    scope["selected_basket"] = None
    scope["selected_baskets"] = []
    scope["selected_week"] = None
    scope["show_line"] = False
    scope["show_qw_colors"] = False
    scope["show_qw_average"] = False
    scope["fit_sold"] = {}
    scope["fit_sold_m"] = {}
    scope["fit_cost"] = {}
    scope["bulk_fit_price_sold"] = {}
    scope["bulk_fit_price_stock_sold"] = {}
    scope["bulk_fit_cost_price"] = {}
    scope["fit_sumup_cost"] = None
    scope["fit_sumup_stock_sold"] = None
    scope["sumup_margin_model"] = None
    scope["margin_model"] = {}
    scope["sumup_select_generation"] = 0


def iter_built_product_bs_scopes(
    session_state: Any,
    input_mode: str,
) -> list[tuple[str, dict[str, Any]]]:
    """
    Return ``(category, scope)`` pairs for this input mode that have a built analysis.

    Order follows PRODUCT_BS_CATEGORY_OPTIONS.
    """
    if input_mode not in PRODUCT_BS_INPUT_MODES:
        return []
    scopes = getattr(session_state, "_pbs_scopes", None) or {}
    built: list[tuple[str, dict[str, Any]]] = []
    for category in PRODUCT_BS_CATEGORY_OPTIONS:
        key = product_bs_scope_key(input_mode, category)
        scope = scopes.get(key)
        if scope is None or scope.get("analysis") is None:
            continue
        built.append((category, scope))
    return built
