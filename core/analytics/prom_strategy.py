"""
Week Discount prom generation — pure analytics, no Streamlit.

Prom calculation is separate from discount strategy; future prom rules may
also affect generated discounts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.analytics.discount_strategy import _row_float
from core.analytics.week_basket_tables import NEW_PROM_COLUMN

PROM_GENERATION_MODES = ("Set previous prom",)


@dataclass
class PromStrategySettings:
    mode: str = "Set previous prom"


def compute_new_prom_value(
    row: dict,
    filter_map: dict[str, str],
    settings: PromStrategySettings,
) -> float:
    """Compute Prom[new] for one Week Discount row."""
    prom_current_col = filter_map.get("prom_current", "")
    prom_current = _row_float(row, prom_current_col)

    if settings.mode == "Set previous prom":
        return prom_current

    return prom_current


def generate_week_prom_values(
    rows: list[dict],
    filter_map: dict[str, str],
    settings: PromStrategySettings,
) -> dict[str, float]:
    """Return {basket: Prom[new]} for all rows."""
    generated: dict[str, float] = {}
    for row in rows:
        basket = str(row.get("Basket", ""))
        if not basket:
            continue
        value = compute_new_prom_value(row, filter_map, settings)
        generated[basket] = (
            round(value, 4) if not math.isnan(value) else float("nan")
        )
    return generated


def apply_generated_proms_to_rows(
    rows: list[dict],
    generated: dict[str, float],
) -> list[dict]:
    """Return shallow copies of rows with New Prom updated."""
    updated: list[dict] = []
    for row in rows:
        copy = dict(row)
        basket = str(copy.get("Basket", ""))
        if basket in generated:
            copy[NEW_PROM_COLUMN] = generated[basket]
        updated.append(copy)
    return updated
