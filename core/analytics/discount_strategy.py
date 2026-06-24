"""
Week Discount strategy generation — pure analytics, no Streamlit.

Formula (strategy mode):
    Discount[new] = Discount[current] + (dDiscount(strategy) + Balance) * Multiplicator
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from core.analytics.week_basket_tables import NEW_DISCOUNT_COLUMN, NEW_PROM_COLUMN

STRATEGY_NAMES = ("Conservative", "Moderate", "Strong")

GENERATION_MODES = (
    "Based on Strategies",
    "Set previous discount",
    "Zero all Discounts",
)

MARGIN_MODES = (
    "apply single strategy to all Margins",
    "Margin categories",
)


@dataclass
class StrategyBin:
    lower: float
    upper: float
    d_discount: float


@dataclass
class StrategyTable:
    name: str
    bins: list[StrategyBin] = field(default_factory=list)


@dataclass
class MarginCategory:
    lower: float
    upper: float
    strategy: str


@dataclass
class DiscountStrategySettings:
    mode: str = "Based on Strategies"
    balance: float = 0.0
    multiplicator: float = 1.0
    zero_d_st_negative: bool = False
    zero_d_st_positive: bool = False
    missing_discount_default: float = 0.0  # used when Discount[current] is missing (NaN)
    sold_zero_strategy: str = "Conservative"
    sold_zero_balance: float = -0.01
    mtost_strategy_enabled: bool = True
    mtost_balance: float = 0.02
    mtost: StrategyTable = field(default_factory=lambda: StrategyTable("MtoSt"))
    margin_mode: str = "Margin categories"
    default_strategy: str = "Moderate"
    conservative: StrategyTable = field(default_factory=lambda: StrategyTable("Conservative"))
    moderate: StrategyTable = field(default_factory=lambda: StrategyTable("Moderate"))
    strong: StrategyTable = field(default_factory=lambda: StrategyTable("Strong"))
    margin_categories: list[MarginCategory] = field(default_factory=list)


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return not str(value).strip()


def parse_percent_value(raw: object) -> Optional[float]:
    """Parse '2%', '-50%', '0', '-1%' into ratio floats."""
    if _is_blank(raw):
        return None
    text = str(raw).strip().replace(",", "")
    if text.lower() in {"n/a", "na", "nan"}:
        return None
    try:
        if text.endswith("%"):
            return float(text[:-1]) / 100.0
        return float(text)
    except ValueError:
        return None


def parse_limit_value(raw: object) -> Optional[float]:
    if _is_blank(raw):
        return None
    text = str(raw).strip().lower()
    if text == "min":
        return float("-inf")
    if text == "max":
        return float("inf")
    return parse_percent_value(raw)


def _parse_strategy_bins_from_columns(df: pd.DataFrame, limit_col: int, ddisc_col: int) -> list[StrategyBin]:
    limits: list[float] = []
    ddiscounts: list[float] = []
    for row_idx in range(3, len(df)):
        limit_raw = df.iloc[row_idx, limit_col] if limit_col < df.shape[1] else None
        ddisc_raw = df.iloc[row_idx, ddisc_col] if ddisc_col < df.shape[1] else None
        if not _is_blank(limit_raw):
            parsed = parse_limit_value(limit_raw)
            if parsed is not None:
                limits.append(parsed)
        if not _is_blank(ddisc_raw):
            parsed = parse_percent_value(ddisc_raw)
            if parsed is not None:
                ddiscounts.append(parsed)

    if not limits or not ddiscounts:
        return []

    pair_count = min(len(limits) - 1, len(ddiscounts))
    bins: list[StrategyBin] = []
    for i in range(pair_count):
        bins.append(StrategyBin(limits[i], limits[i + 1], ddiscounts[i]))
    return bins


def _parse_margin_categories(df: pd.DataFrame) -> list[MarginCategory]:
    limit_col, strategy_col = 25, 26
    if df.shape[1] <= strategy_col:
        return default_margin_categories()

    limits: list[float] = []
    strategies: list[str] = []
    # Row 5 is the "Margin limits / Strategy" header; data starts at row 6.
    # Limits and strategies alternate on separate rows in the CSV workbook layout.
    for row_idx in range(6, len(df)):
        limit_raw = df.iloc[row_idx, limit_col]
        strategy_raw = df.iloc[row_idx, strategy_col]
        if not _is_blank(limit_raw):
            parsed = parse_limit_value(limit_raw)
            if parsed is not None:
                limits.append(parsed)
        if not _is_blank(strategy_raw):
            strategy = str(strategy_raw).strip()
            if strategy.lower() != "strategy":
                strategies.append(strategy)

    if len(limits) < 2:
        return default_margin_categories()

    categories: list[MarginCategory] = []
    for i in range(len(limits) - 1):
        strategy = strategies[i] if i < len(strategies) else "Moderate"
        categories.append(MarginCategory(limits[i], limits[i + 1], strategy))
    return categories


def default_conservative_bins() -> list[StrategyBin]:
    limits = [-math.inf, -0.50, -0.30, -0.10, -0.05, 0.0, 0.05, 0.10, 0.30, 0.50, math.inf]
    ddiscounts = [0.02, 0.02, 0.01, 0.0, 0.0, 0.0, 0.0, -0.01, -0.02, -0.02]
    return [StrategyBin(limits[i], limits[i + 1], ddiscounts[i]) for i in range(len(ddiscounts))]


def default_moderate_bins() -> list[StrategyBin]:
    limits = [-math.inf, -0.50, -0.30, -0.10, -0.05, 0.0, 0.05, 0.10, 0.30, 0.50, math.inf]
    ddiscounts = [0.05, 0.04, 0.03, 0.02, 0.0, 0.0, -0.02, -0.03, -0.04, -0.05]
    return [StrategyBin(limits[i], limits[i + 1], ddiscounts[i]) for i in range(len(ddiscounts))]


def default_strong_bins() -> list[StrategyBin]:
    limits = [-math.inf, -0.50, -0.30, -0.10, -0.05, 0.0, 0.05, 0.10, 0.30, 0.50, math.inf]
    ddiscounts = [0.07, 0.05, 0.04, 0.03, 0.0, 0.0, -0.02, -0.03, -0.04, -0.07]
    return [StrategyBin(limits[i], limits[i + 1], ddiscounts[i]) for i in range(len(ddiscounts))]


def default_margin_categories() -> list[MarginCategory]:
    return [
        MarginCategory(float("-inf"), 0.0, "Conservative"),
        MarginCategory(0.0, 100.0, "Conservative"),
        MarginCategory(100.0, 1000.0, "Moderate"),
        MarginCategory(1000.0, float("inf"), "Moderate"),
    ]


def default_mtost_bins() -> list[StrategyBin]:
    limits = [0.0, 0.20, 0.50, math.inf]
    ddiscounts = [-0.02, 0.0, 0.02]
    return [StrategyBin(limits[i], limits[i + 1], ddiscounts[i]) for i in range(len(ddiscounts))]


def default_discount_strategy_settings() -> DiscountStrategySettings:
    return DiscountStrategySettings(
        conservative=StrategyTable("Conservative", default_conservative_bins()),
        moderate=StrategyTable("Moderate", default_moderate_bins()),
        strong=StrategyTable("Strong", default_strong_bins()),
        mtost=StrategyTable("MtoSt", default_mtost_bins()),
        margin_categories=default_margin_categories(),
    )


class StrategiesFormatError(ValueError):
    """Raised when a strategies v1 file is malformed."""


def _is_strategies_v1_path(path: Path) -> bool:
    if ".v1." in path.name.lower():
        return True
    try:
        head = path.read_text(encoding="utf-8")[:800]
    except OSError:
        return False
    return "[meta]" in head or "PBA Strategies v1" in head


def _read_v1_sections(path: Path) -> dict[str, list[list[str]]]:
    sections: dict[str, list[list[str]]] = {}
    current: Optional[str] = None
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            if not current:
                raise StrategiesFormatError(f"line {line_no}: empty section name")
            sections[current] = []
            continue
        if current is None:
            raise StrategiesFormatError(
                f"line {line_no}: data row before any [section] header",
            )
        sections[current].append([part.strip() for part in line.split(",")])
    return sections


def _validate_strategy_name(name: str, context: str) -> None:
    if name not in STRATEGY_NAMES:
        allowed = ", ".join(STRATEGY_NAMES)
        raise StrategiesFormatError(
            f"{context}: strategy must be one of {allowed}, got {name!r}",
        )


def _parse_v1_key_value_section(section: str, rows: list[list[str]]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_no, row in enumerate(rows, start=1):
        if not row or all(_is_blank(cell) for cell in row):
            continue
        if len(row) < 2 or _is_blank(row[0]):
            raise StrategiesFormatError(
                f"[{section}] row {line_no}: expected key,value",
            )
        key = str(row[0]).strip()
        value = ",".join(row[1:]).strip()
        if not value:
            raise StrategiesFormatError(
                f"[{section}] row {line_no}: missing value for {key!r}",
            )
        values[key] = value
    return values


def _parse_v1_strategy_bins(section: str, rows: list[list[str]]) -> list[StrategyBin]:
    if len(rows) < 2:
        raise StrategiesFormatError(
            f"[{section}]: expected header row and at least one data row",
        )

    limits: list[float] = []
    ddiscounts: list[float] = []
    for line_no, row in enumerate(rows[1:], start=2):
        if not row or all(_is_blank(cell) for cell in row):
            continue
        lower_raw = row[0] if len(row) > 0 else None
        ddisc_raw = row[1] if len(row) > 1 else None
        if not _is_blank(lower_raw):
            parsed = parse_limit_value(lower_raw)
            if parsed is None:
                raise StrategiesFormatError(
                    f"[{section}] row {line_no}: invalid lower_dSt_QW {lower_raw!r}",
                )
            limits.append(parsed)
        if not _is_blank(ddisc_raw):
            parsed = parse_percent_value(ddisc_raw)
            if parsed is None:
                raise StrategiesFormatError(
                    f"[{section}] row {line_no}: invalid dDiscount {ddisc_raw!r}",
                )
            ddiscounts.append(parsed)

    if len(limits) < 2:
        raise StrategiesFormatError(
            f"[{section}]: need at least two limits (min … max)",
        )
    expected_bins = len(limits) - 1
    if len(ddiscounts) != expected_bins:
        raise StrategiesFormatError(
            f"[{section}]: expected {expected_bins} dDiscount value(s), got {len(ddiscounts)}",
        )

    return [
        StrategyBin(limits[i], limits[i + 1], ddiscounts[i])
        for i in range(expected_bins)
    ]


def _parse_v1_margin_categories(section: str, rows: list[list[str]]) -> list[MarginCategory]:
    if len(rows) < 2:
        raise StrategiesFormatError(
            f"[{section}]: expected header row and at least one category row",
        )

    categories: list[MarginCategory] = []
    for line_no, row in enumerate(rows[1:], start=2):
        if not row or all(_is_blank(cell) for cell in row):
            continue
        if len(row) < 3:
            raise StrategiesFormatError(
                f"[{section}] row {line_no}: expected lower_margin,upper_margin,strategy",
            )
        lower_raw, upper_raw, strategy_raw = row[0], row[1], row[2]
        if _is_blank(strategy_raw):
            raise StrategiesFormatError(
                f"[{section}] row {line_no}: missing strategy",
            )
        strategy = str(strategy_raw).strip()
        _validate_strategy_name(strategy, f"[{section}] row {line_no}")

        lower = parse_limit_value(lower_raw)
        upper = parse_limit_value(upper_raw)
        if lower is None or upper is None:
            raise StrategiesFormatError(
                f"[{section}] row {line_no}: invalid margin limits "
                f"{lower_raw!r}, {upper_raw!r}",
            )
        categories.append(MarginCategory(lower, upper, strategy))

    if not categories:
        raise StrategiesFormatError(f"[{section}]: no margin categories defined")
    return categories


def load_strategies_v1(path: str | Path) -> DiscountStrategySettings:
    """Load discount strategy settings from a PBA Strategies v1 sectioned file."""
    sections = _read_v1_sections(Path(path))
    settings = default_discount_strategy_settings()

    defaults_rows = sections.get("discount.defaults", [])
    if defaults_rows:
        defaults = _parse_v1_key_value_section("discount.defaults", defaults_rows)
        if "sold_zero_strategy" in defaults:
            _validate_strategy_name(defaults["sold_zero_strategy"], "discount.defaults")
            settings.sold_zero_strategy = defaults["sold_zero_strategy"]
        if "sold_zero_balance" in defaults:
            balance = parse_percent_value(defaults["sold_zero_balance"])
            if balance is None:
                raise StrategiesFormatError(
                    "discount.defaults: invalid sold_zero_balance "
                    f"{defaults['sold_zero_balance']!r}",
                )
            settings.sold_zero_balance = balance
        if "default_margin_strategy" in defaults:
            _validate_strategy_name(
                defaults["default_margin_strategy"],
                "discount.defaults",
            )
            settings.default_strategy = defaults["default_margin_strategy"]
        if "margin_mode" in defaults:
            settings.margin_mode = defaults["margin_mode"]

    for section_key, attr, table_name in (
        ("discount.conservative_bins", "conservative", "Conservative"),
        ("discount.moderate_bins", "moderate", "Moderate"),
        ("discount.strong_bins", "strong", "Strong"),
    ):
        section_rows = sections.get(section_key)
        if section_rows:
            table = StrategyTable(
                table_name,
                _parse_v1_strategy_bins(section_key, section_rows),
            )
            setattr(settings, attr, table)

    margin_rows = sections.get("discount.margin_categories")
    if margin_rows:
        settings.margin_categories = _parse_v1_margin_categories(
            "discount.margin_categories",
            margin_rows,
        )

    mtost_defaults_rows = sections.get("discount.mtost_strategy", [])
    if mtost_defaults_rows:
        mtost_defaults = _parse_v1_key_value_section(
            "discount.mtost_strategy",
            mtost_defaults_rows,
        )
        if "enabled" in mtost_defaults:
            settings.mtost_strategy_enabled = mtost_defaults["enabled"].strip().lower() in {
                "1", "true", "yes", "on",
            }
        if "balance" in mtost_defaults:
            balance = parse_percent_value(mtost_defaults["balance"])
            if balance is None:
                raise StrategiesFormatError(
                    "discount.mtost_strategy: invalid balance "
                    f"{mtost_defaults['balance']!r}",
                )
            settings.mtost_balance = balance

    mtost_bins_rows = sections.get("discount.mtost_bins")
    if mtost_bins_rows:
        settings.mtost = StrategyTable(
            "MtoSt",
            _parse_v1_strategy_bins("discount.mtost_bins", mtost_bins_rows),
        )

    # prom.* sections reserved for future prom strategy loading.

    return settings


def _load_legacy_discount_workbook(path: Path) -> DiscountStrategySettings:
    """Load strategy tables from the legacy Excel-export workbook CSV."""
    df = pd.read_csv(path, header=None)
    settings = default_discount_strategy_settings()

    conservative_bins = _parse_strategy_bins_from_columns(df, 3, 4)
    moderate_bins = _parse_strategy_bins_from_columns(df, 5, 6)
    strong_bins = _parse_strategy_bins_from_columns(df, 7, 8)

    if conservative_bins:
        settings.conservative.bins = conservative_bins
    if moderate_bins:
        settings.moderate.bins = moderate_bins
    if strong_bins:
        settings.strong.bins = strong_bins

    margin_categories = _parse_margin_categories(df)
    if margin_categories:
        settings.margin_categories = margin_categories

    if df.shape[1] > 24:
        sold_zero_balance = parse_percent_value(df.iloc[4, 24])
        if sold_zero_balance is not None:
            settings.sold_zero_balance = sold_zero_balance
        sold_zero_strategy = df.iloc[3, 23] if df.shape[1] > 23 else None
        if not _is_blank(sold_zero_strategy):
            settings.sold_zero_strategy = str(sold_zero_strategy).strip()

    return settings


def load_discount_strategy_settings(csv_path: str | Path) -> DiscountStrategySettings:
    """Load discount strategy settings from v1 or legacy workbook CSV."""
    path = Path(csv_path)
    if not path.exists():
        return default_discount_strategy_settings()
    if _is_strategies_v1_path(path):
        return load_strategies_v1(path)
    return _load_legacy_discount_workbook(path)


def strategy_table_by_name(settings: DiscountStrategySettings, name: str) -> StrategyTable:
    lookup = {
        "Conservative": settings.conservative,
        "Moderate": settings.moderate,
        "Strong": settings.strong,
    }
    return lookup.get(name, settings.moderate)


def lookup_strategy_d_discount(d_st_qw: float, table: StrategyTable) -> float:
    if math.isnan(d_st_qw):
        return float("nan")
    for bin_row in table.bins:
        lower = bin_row.lower
        upper = bin_row.upper
        if upper == math.inf:
            if d_st_qw >= lower:
                return bin_row.d_discount
        elif d_st_qw >= lower and d_st_qw < upper:
            return bin_row.d_discount
    return float("nan")


def lookup_mtost_d_discount(d_mto_st_qw: float, table: StrategyTable) -> float:
    """Lookup dDiscount from dMtoSt_QW category bins."""
    return lookup_strategy_d_discount(d_mto_st_qw, table)


def mtost_strategy_applies(
    d_st_qw: float,
    margin_current: float,
    margin_w1: float,
    settings: DiscountStrategySettings,
) -> bool:
    """Priority 3 — MtoSt strategy eligibility (above default margin strategy)."""
    if not settings.mtost_strategy_enabled:
        return False
    if math.isnan(d_st_qw) or d_st_qw <= 0:
        return False
    if math.isnan(margin_current) or margin_current < 0:
        return False
    if math.isnan(margin_w1) or margin_w1 < 0:
        return False
    return True


def lookup_margin_strategy(margin_current: float, settings: DiscountStrategySettings) -> str:
    if settings.margin_mode != "Margin categories":
        return settings.default_strategy
    if math.isnan(margin_current):
        return settings.default_strategy
    for category in settings.margin_categories:
        lower = category.lower
        upper = category.upper
        if upper == math.inf:
            if margin_current >= lower:
                return category.strategy
        elif margin_current >= lower and margin_current < upper:
            return category.strategy
    return settings.default_strategy


def apply_zero_d_st_rules(d_st_qw: float, d_discount: float, settings: DiscountStrategySettings) -> float:
    if math.isnan(d_st_qw) or math.isnan(d_discount):
        return d_discount
    if settings.zero_d_st_negative and d_st_qw < 0:
        return 0.0
    if settings.zero_d_st_positive and d_st_qw > 0:
        return 0.0
    return d_discount


def _limit_label_for_display(limit: float) -> str:
    """Format bin limit for TextColumn data editors (always string)."""
    if limit == float("-inf"):
        return "min"
    if limit == float("inf"):
        return "max"
    return str(limit * 100.0)


def mtost_bins_to_display_rows(table: StrategyTable) -> list[dict]:
    """Rows for UI tables: dDiscount between consecutive dMtoSt_QW limits."""
    rows: list[dict] = []
    for bin_row in table.bins:
        rows.append({
            "lower dMtoSt_QW %": _limit_label_for_display(bin_row.lower),
            "dDiscount %": bin_row.d_discount * 100.0,
            "upper dMtoSt_QW %": _limit_label_for_display(bin_row.upper),
        })
    return rows


def display_rows_to_mtost_bins(rows: list[dict]) -> StrategyTable:
    bins: list[StrategyBin] = []
    for row in rows:
        lower_raw = row.get("lower dMtoSt_QW %")
        upper_raw = row.get("upper dMtoSt_QW %")
        ddisc_raw = row.get("dDiscount %")
        if lower_raw is None or upper_raw is None or ddisc_raw is None:
            continue
        lower = float("-inf") if str(lower_raw).strip().lower() == "min" else float(lower_raw) / 100.0
        upper = float("inf") if str(upper_raw).strip().lower() == "max" else float(upper_raw) / 100.0
        d_discount = float(ddisc_raw) / 100.0
        bins.append(StrategyBin(lower, upper, d_discount))
    return StrategyTable("MtoSt", bins)


def strategy_bins_to_display_rows(table: StrategyTable) -> list[dict]:
    """Rows for UI tables: dDiscount shown between consecutive dSt_QW limits."""
    rows: list[dict] = []
    for bin_row in table.bins:
        rows.append({
            "lower dSt_QW %": _limit_label_for_display(bin_row.lower),
            "dDiscount %": bin_row.d_discount * 100.0,
            "upper dSt_QW %": _limit_label_for_display(bin_row.upper),
        })
    return rows


def display_rows_to_strategy_bins(name: str, rows: list[dict]) -> StrategyTable:
    bins: list[StrategyBin] = []
    for row in rows:
        lower_raw = row.get("lower dSt_QW %")
        upper_raw = row.get("upper dSt_QW %")
        ddisc_raw = row.get("dDiscount %")
        if lower_raw is None or upper_raw is None or ddisc_raw is None:
            continue
        lower = float("-inf") if str(lower_raw).strip().lower() == "min" else float(lower_raw) / 100.0
        upper = float("inf") if str(upper_raw).strip().lower() == "max" else float(upper_raw) / 100.0
        d_discount = float(ddisc_raw) / 100.0
        bins.append(StrategyBin(lower, upper, d_discount))
    return StrategyTable(name, bins)


def week_discount_group_column_at_offset(
    column_meta: dict[str, dict[str, object]],
    group: str,
    offset: int,
) -> str:
    for col, meta in column_meta.items():
        if meta.get("group") == group and meta.get("offset") == offset and not meta.get("is_delta"):
            return col
    return ""


def _row_float(row: dict, column: str) -> float:
    if not column or column not in row:
        return float("nan")
    value = row[column]
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return float("nan")
    return float(value)


def compute_new_discount_value(
    row: dict,
    column_meta: dict[str, dict[str, object]],
    filter_map: dict[str, str],
    settings: DiscountStrategySettings,
) -> float:
    """Compute Discount[new] for one Week Discount row."""
    discount_current_col = filter_map.get("discount_current") or filter_map.get("new_discount", "")
    discount_current_raw = _row_float(row, discount_current_col)
    has_discount_current = not math.isnan(discount_current_raw)
    # Priority 1: substitute default when Discount[current] is missing.
    discount_current = (
        discount_current_raw
        if has_discount_current
        else settings.missing_discount_default
    )

    d_st_qw = _row_float(row, filter_map.get("dSt_QW", "dSt_QW"))
    sold_current = _row_float(row, filter_map.get("sold_current", ""))
    margin_current = _row_float(row, filter_map.get("margin_current", ""))

    if not math.isnan(sold_current) and sold_current == 0.0:
        if settings.mode == "Zero all Discounts":
            return 0.0
        if settings.mode == "Set previous discount":
            return discount_current
        table = strategy_table_by_name(settings, settings.sold_zero_strategy)
        d_discount = lookup_strategy_d_discount(d_st_qw, table)
        d_discount = apply_zero_d_st_rules(d_st_qw, d_discount, settings)
        if math.isnan(d_discount):
            return discount_current
        return discount_current + (d_discount + settings.sold_zero_balance) * settings.multiplicator

    if settings.mode == "Set previous discount":
        return discount_current
    if settings.mode == "Zero all Discounts":
        return 0.0

    margin_w1_col = week_discount_group_column_at_offset(column_meta, "margin", -1)
    margin_w1 = _row_float(row, margin_w1_col)
    d_mto_st_qw = _row_float(row, filter_map.get("dMtoSt_QW", "dMtoSt_QW"))

    if mtost_strategy_applies(d_st_qw, margin_current, margin_w1, settings):
        d_discount = lookup_mtost_d_discount(d_mto_st_qw, settings.mtost)
        if not math.isnan(d_discount):
            return discount_current + (d_discount + settings.mtost_balance)

    strategy_name = lookup_margin_strategy(margin_current, settings)
    table = strategy_table_by_name(settings, strategy_name)
    d_discount = lookup_strategy_d_discount(d_st_qw, table)
    d_discount = apply_zero_d_st_rules(d_st_qw, d_discount, settings)
    if math.isnan(d_discount):
        return discount_current

    return discount_current + (d_discount + settings.balance) * settings.multiplicator


def generate_week_discount_values(
    rows: list[dict],
    column_meta: dict[str, dict[str, object]],
    filter_map: dict[str, str],
    settings: DiscountStrategySettings,
) -> dict[str, float]:
    """Return {basket: Discount[new]} for all rows."""
    generated: dict[str, float] = {}
    for row in rows:
        basket = str(row.get("Basket", ""))
        if not basket:
            continue
        generated[basket] = round(
            compute_new_discount_value(row, column_meta, filter_map, settings),
            4,
        )
    return generated


def apply_generated_discounts_to_rows(
    rows: list[dict],
    generated: dict[str, float],
) -> list[dict]:
    """Return shallow copies of rows with New Discount updated."""
    updated: list[dict] = []
    for row in rows:
        copy = dict(row)
        basket = str(copy.get("Basket", ""))
        if basket in generated:
            copy[NEW_DISCOUNT_COLUMN] = generated[basket]
        updated.append(copy)
    return updated


def apply_manual_overrides_to_rows(
    rows: list[dict],
    overrides: dict[str, dict[str, float]],
) -> list[dict]:
    """Return shallow copies with manual New Discount / New Prom overrides applied."""
    if not overrides:
        return [dict(row) for row in rows]

    editable = {NEW_DISCOUNT_COLUMN, NEW_PROM_COLUMN}
    updated: list[dict] = []
    for row in rows:
        copy = dict(row)
        basket = str(copy.get("Basket", ""))
        basket_overrides = overrides.get(basket)
        if basket_overrides:
            for col, value in basket_overrides.items():
                if col in editable:
                    copy[col] = value
        updated.append(copy)
    return updated


def build_working_week_discount_rows(
    base_rows: list[dict],
    filter_map: dict[str, str],
    generated_discount: dict[str, float] | None = None,
    generated_prom: dict[str, float] | None = None,
    manual_overrides: dict[str, dict[str, float]] | None = None,
) -> list[dict]:
    """Apply generated/manual New values, then recompute dDiscount and dProm."""
    from core.analytics.prom_strategy import apply_generated_proms_to_rows
    from core.analytics.week_basket_tables import enrich_week_discount_delta_columns

    rows = base_rows
    if generated_discount:
        rows = apply_generated_discounts_to_rows(rows, generated_discount)
    if generated_prom:
        rows = apply_generated_proms_to_rows(rows, generated_prom)
    if manual_overrides:
        rows = apply_manual_overrides_to_rows(rows, manual_overrides)
    return enrich_week_discount_delta_columns(rows, filter_map)
