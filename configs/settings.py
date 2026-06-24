"""
Application-wide constants and default analytical settings.
"""

from pathlib import Path

APP_TITLE = "Pricing Correlation & Bucket Analysis"
APP_VERSION = "1.0.0"

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Discount / prom strategy defaults (v1 sectioned format; prom sections reserved).
STRATEGIES_V1_PATH = PROJECT_ROOT / "configs" / "strategies" / "strategies.v1.csv"
LEGACY_DISCOUNT_SETTINGS_PATH = PROJECT_ROOT / "inputs" / "Discount settings.csv"
DEFAULT_STRATEGIES_PATH = STRATEGIES_V1_PATH

# Canonical basket universe (4 digits 1–5 each → 625 baskets).
FULL_BASKET_LIST_PATH = PROJECT_ROOT / "inputs" / "full list of baskets.csv"
FULL_BASKET_LIST_SIZE = 5**4

# CSV column names that are metadata (not basket identifiers)
CSV_METADATA_COLS: set[str] = {
    "quadweek",
    "year_week",
    "week from y_w (1_52)",
    "week in quad (1_4)",
    "basket",
    "",
}

# Minimum data points required for Pearson correlation
MIN_POINTS_FOR_CORRELATION: int = 3

# Minimum data points required for regression fits
MIN_POINTS_FOR_MLR: int = 3
MIN_POINTS_FOR_SLR: int = 2

# K-Means defaults
KMEANS_DEFAULT_K: int = 2
KMEANS_MAX_K: int = 15
KMEANS_MAX_ITER: int = 100

# Number of octants in octant clustering
OCTANT_COUNT: int = 8

# Default filter values
DEFAULT_MIN_PRICE: float = 0.0

# Color palette for cluster groups (up to 8 groups)
CLUSTER_COLORS: list[str] = [
    "rgba(59, 130, 246, 0.75)",    # blue
    "rgba(249, 115, 22, 0.75)",    # orange
    "rgba(16, 185, 129, 0.75)",    # green
    "rgba(139, 92, 246, 0.75)",    # purple
    "rgba(236, 72, 153, 0.75)",    # pink
    "rgba(234, 179, 8, 0.75)",     # yellow
    "rgba(6, 182, 212, 0.75)",     # cyan
    "rgba(239, 68, 68, 0.75)",     # red
]

CLUSTER_BORDER_COLORS: list[str] = [
    "rgb(37, 99, 235)",
    "rgb(234, 88, 12)",
    "rgb(5, 150, 105)",
    "rgb(109, 40, 217)",
    "rgb(219, 39, 119)",
    "rgb(202, 138, 4)",
    "rgb(8, 145, 178)",
    "rgb(220, 38, 38)",
]

UNCLUSTERED_COLOR: str = "rgba(156, 163, 175, 0.7)"
UNCLUSTERED_BORDER: str = "rgb(107, 114, 128)"

# Re-exported from configs.theme_bootstrap (single source of truth for theme values).
from configs.theme_bootstrap import FORCE_LIGHT_CSS, THEME_BOOTSTRAP_HTML  # noqa: E402

OCTANT_LABELS: list[str] = [
    "Octant 1 (+ + +)",
    "Octant 2 (- + +)",
    "Octant 3 (- - +)",
    "Octant 4 (+ - +)",
    "Octant 5 (+ + -)",
    "Octant 6 (- + -)",
    "Octant 7 (- - -)",
    "Octant 8 (+ - -)",
]
