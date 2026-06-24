"""
app.py — Thin Streamlit entry point.

Responsibilities:
- Configure the application.
- Set up navigation.
- Provide a project welcome/home screen.

Must NOT contain: analytical logic, transformations, clustering, or modeling code.
"""

import streamlit as st

from configs.settings import APP_TITLE, APP_VERSION
from configs.theme_bootstrap import apply_page_theme

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_page_theme()

# ─────────────────────────────────────────────────────────────────────────────
# Home / Welcome screen
# ─────────────────────────────────────────────────────────────────────────────

st.title(f"📈 {APP_TITLE}")
st.caption(f"Version {APP_VERSION}  ·  Phase 1 — Analytical Prototype")
st.divider()

st.markdown("""
### Welcome

This application is an **analytical intelligence platform** for pricing correlation
and basket segmentation.

Use the navigation sidebar to access the available analysis pages.

---

#### Current Pages

| Page | Description |
|---|---|
| **Correlation Analysis** | Upload datasets → compute correlations → cluster baskets → drill-down into basket & week detail → run margin optimisation model |

---

#### How to use

1. Navigate to **Correlation Analysis** in the sidebar.
2. Upload four CSV files: **SoldIn**, **AvgSalePrice_In**, **M_In**, **Stock**.
3. Set preprocessing filters and click **Build Project**.
4. Optionally apply **K-Means** or **Octants** clustering.
5. Click any basket row to drill into weekly data and run regression fits.
6. Scroll down to the **Sum-Up** section for aggregate weekly analytics.

---

#### Expected CSV format

Each CSV file must have:
- A `year_week` column (e.g. `2024-01`).
- A `quadweek` column (optional but recommended for trend analysis).
- One column per basket (the basket code is the column name).

---
""")

st.info(
    "📌 Phase 2 will migrate the analytical engine (core/, services/, pipelines/) "
    "into a FastAPI + Next.js SaaS architecture. "
    "The core layer is already UI-independent and ready for direct reuse."
)
