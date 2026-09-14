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
| **Correlation Analysis** | Upload a TrackingBaskets report → correlations → clusters → basket & week detail → Week Discount → Project save |

---

#### How to use

1. Navigate to **Correlation Analysis** in the sidebar.
2. Choose an input format (**TrackingBaskets_v2 report** or **product_BS**) and upload the report CSV.
3. Optionally upload one or more **discount history** CSVs.
4. Set preprocessing filters and click **Build Project**.
5. Optionally apply **K-Means** or **Octants** clustering.
6. Click any basket row to drill into weekly data and run regression fits.
7. In **Sum-Up**, select a week and open **Week Discount** to generate, edit, and export.
8. Use the sidebar **Project** expander to **Save…** or **Restore** a `.disc_proj` snapshot.

---

#### Expected CSV format

**TrackingBaskets_v2** report (or product_BS report): weekly rows with `year_week`, `quadweek`, `basket`, and metric columns. Optional discount history uses `year_week`, `basket`, and category discount/prom columns. Column details are in the user manual (`docs/user-manual.md`).

---
""")

st.info(
    "📌 Phase 2 will migrate the analytical engine (core/, services/, pipelines/) "
    "into a FastAPI + Next.js SaaS architecture. "
    "The core layer is already UI-independent and ready for direct reuse."
)
