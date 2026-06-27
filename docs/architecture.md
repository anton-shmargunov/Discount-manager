# PBA — Architecture

**Pricing Correlation & Bucket Analysis · Phase 1 Streamlit MVP**

Version 1.0.0 · Last updated 2026-06-23

---

## Purpose

This document describes the **technical structure** of the PBA application: layers, modules, data flow, session state, and extension points. For step-by-step usage, see [user-manual.md](user-manual.md).

The application ports an HTML/JS analytics prototype into Python while preserving a strict separation between analytics and UI, so the analytical engine can be reused in FastAPI, workers, notebooks, or tests without Streamlit.

---

## Core architectural rule

> **UI can depend on analytics. Analytics must NEVER depend on UI.**

| Layer | May import from | Must NOT import |
|-------|-----------------|-----------------|
| `pages/`, `ui/` | `core/`, `visualizations/`, `configs/` | — |
| `visualizations/` | `core/`, `configs/` | `streamlit` |
| `core/` | stdlib, numpy, pandas, scipy, sklearn | `streamlit`, `pages/`, `ui/` |

The `core/` package has **zero Streamlit imports**. All business logic, ETL, statistics, clustering, modeling, and discount/prom strategy live there.

---

## Repository layout

```
PBA.v.1.250525/
│
├── app.py                          # Thin entry: page config, theme, welcome screen
│
├── pages/
│   └── 01_Correlation_Analysis.py  # Main analysis page (~2200 lines)
│
├── ui/                             # Reusable Streamlit sections (no analytics)
│   ├── product_bs_scope.py         # Per-mode/category session isolation
│   └── week_discount_ui.py         # Week Discount UI (strategy, table, exports)
│
├── core/                           # Pure analytical engine
│   ├── models.py                   # Dataclasses: BasketTimeSeries, BasketResult, …
│   ├── analytics/
│   │   ├── basket_analysis.py      # run_*_analysis, clustering hooks, sum-up
│   │   ├── week_basket_tables.py   # Week Discount rows, filters, deltas, export
│   │   ├── discount_strategy.py    # Strategy bins, generation, manual overrides
│   │   └── prom_strategy.py        # Prom generation ("Set previous prom")
│   ├── transforms/
│   │   └── data_prep.py            # ETL, product-BS parsing, discount hist I/O
│   ├── statistics/
│   │   ├── correlations.py         # Pearson correlation
│   │   └── metrics.py              # Monthly reserve, stock trends
│   ├── clustering/
│   │   ├── kmeans.py               # K-Means on 3D correlation coords
│   │   └── octants.py              # Sign-based 8-way grouping
│   ├── modeling/
│   │   └── regression.py           # MLR plane, SLR line, PCA fit
│   └── optimization/
│       └── price_optimization.py   # Margin model Price_max(Stock)
│
├── visualizations/                 # Plotly chart builders (no Streamlit)
│   ├── cluster_charts.py
│   ├── detail_charts.py
│   └── sumup_charts.py
│
├── configs/
│   ├── settings.py                 # App constants, paths, cluster colors
│   ├── theme_bootstrap.py          # Light-theme CSS injection
│   └── strategies/
│       └── strategies.v1.csv       # Discount strategy defaults (prom reserved)
│
├── inputs/                         # Sample CSVs and canonical basket list (625)
├── tests/
│   └── test_e2e.py                 # End-to-end smoke tests
├── docs/
│   ├── architecture.md             # This file
│   └── user-manual.md
│
├── requirements.txt
├── .streamlit/config.toml
└── handoff_*.md                    # Developer handoff notes (not user docs)
```

**Planned but not wired in MVP UI:** `services/`, `pipelines/`, `data/` (DuckDB is in `requirements.txt` for Phase 2).

---

## Dependency flow

```
CSV uploads
    ↓
core/transforms/data_prep.py       normalize, parse product-BS, discount hist
    ↓
core/analytics/basket_analysis.py  orchestrate features + correlations
    ↓
core/statistics · clustering · modeling · optimization
    ↓
core/analytics/week_basket_tables · discount_strategy · prom_strategy
    ↓
visualizations/ (Plotly figures)
    ↓
pages/ + ui/ (Streamlit rendering, session state, downloads)
```

---

## Application entry points

### `app.py`

- Sets Streamlit page config (`layout="wide"`, sidebar expanded)
- Applies theme via `configs.theme_bootstrap.apply_page_theme()`
- Shows welcome screen and navigation hint
- Contains **no** analytical logic

### `pages/01_Correlation_Analysis.py`

Main workflow page, numbered sections:

| Section | Responsibility |
|---------|----------------|
| ① Input Data | Input mode, file uploaders, discount history |
| ② Preprocessing | Range filters, K, Product BS Category |
| Build / K-Means / Octants | Trigger `core` analysis |
| ③ Correlation Clusters | Cluster overview table + 3D scatter |
| ④ Detailed Basket Breakdown | Sortable basket table; row click → drill-down |
| ⑤ Basket Detail | Week Progress charts, fits, margin model |
| ⑥ Sum-Up | Weekly aggregates, correlation KPIs, week selector |
| Per-week expanders | Weekly Detail, **Week Discount**, Week Visualization |

Extracted UI modules:

- `render_week_discount_section()` from `ui/week_discount_ui.py`
- Scope helpers from `ui/product_bs_scope.py`

---

## Input modes

Three **TrackingBaskets_v2** formats are supported (legacy 4-CSV mode remains in tests only):

| Mode | Constant | Report file | Metric basis |
|------|----------|-------------|--------------|
| TrackingBaskets_v2 report | `TRACKING_REPORT_MODE` | Single wide report CSV | Standard columns |
| product_BS on date of sale | `PRODUCT_BS_ON_DATE_MODE` | product_BS report | Suffix columns per category |
| product_BS monthly av. | `PRODUCT_BS_MONTHLY_AV_MODE` | product_BS report | Row-level SoldQty / Revenue averages |

**Product BS Category** (product-BS modes only): `Aggregated`, `In`, `Out`, `OutByCondition`, `OutByMinPrice`, `none`.

Parsing lives in `data_prep.tracking_report_to_frame_set()` and `data_prep.tracking_product_bs_report_to_frame_sets()`.

---

## Domain models (`core/models.py`)

| Type | Role |
|------|------|
| `BasketTimeSeries` | Per-basket weekly series: sold, price, m, stock, cost, discount, prom, … |
| `BasketResult` | Summary stats + Pearson correlations + cluster group |
| `WeeklyTotal` | Sum-Up aggregate for one week |
| `WeeklyPoint` | Single basket contribution within a weekly total |
| `Planefit` / `Linefit` | Regression fit results |
| `MarginModelResult` | Analytical margin optimization output |

`AnalysisResult` (in `basket_analysis.py`) bundles `basket_results`, `basket_data`, `weekly_totals`, and `all_weeks`.

---

## Session state and scope isolation

Streamlit session state is namespaced by **input mode + Product BS category** so switching In/Out/Aggregated does not bleed generated discounts, selections, or fits.

### Scope key format

```python
# product-BS modes
"pbs::{input_mode}::{product_bs_category}"

# report mode
"mode::TrackingBaskets_v2 report"
```

Defined in `ui/product_bs_scope.py`:

- `product_bs_scope_key()`
- `scoped_widget_key(scope_key, widget_key)`
- `get_product_bs_scope(session_state, scope_key)`
- `clear_product_bs_scope_derived(scope)` — called on **Build Project**

### Per-scope persisted data

| Key | Content |
|-----|---------|
| `analysis` | `AnalysisResult` after build |
| `selected_basket`, `selected_week` | Drill-down selections |
| `fit_sold`, `fit_cost`, `margin_model`, … | Per-basket and Sum-Up fits |
| `discount_hist_df` | Copy of uploaded discount history at build time |
| Week Discount keys (scoped) | `wd_generated_discount_{week}`, `wd_manual_overrides_{week}`, … |

Global (unscoped): `input_mode`, filter text inputs, sidebar log (`log_messages`).

---

## Discount history pipeline

Optional CSV merged at **Build** into `BasketTimeSeries.discount` / `.prom`.

### Column mapping by category

| Category | Discount column | Prom column |
|----------|-----------------|-------------|
| Aggregated | `discount` | `prom with stock` |
| In | `BasketDiscountInMarket` | `Prom, BasketDiscountInMarket` |
| Out | `BasketDiscountOutOfMarket` | `Prom, BasketDiscountOutOfMarket` |
| OutByCondition | `BasketDiscountOutOfMarketByCondition` | `Prom, …` |
| OutByMinPrice | `BasketDiscountOutOfMarketByMinPrice` | `Prom, …` |
| none | `none` | `Prom, none` |

**Report mode** always uses **Aggregated** columns (no In/Out split).

Functions:

- `parse_discount_hist_lookup()` — ingest at build
- `apply_discount_hist_to_basket_data()` — merge into time series
- `build_discount_hist_export_rows()` + `merge_discount_hist_export()` — export with week **+1** metadata

---

## Week Discount pipeline

End-to-end flow for a selected week:

```
compute_basket_week_discount_rows()     # base metrics from BasketTimeSeries
        ↓
generate_week_discount_values()         # optional: strategy → New Discount
        ↓
generate_week_prom_values()             # optional: "Set previous prom" → New Prom
        ↓
apply_manual_overrides_to_rows()        # optional: Edit / Apply overrides
        ↓
enrich_week_discount_delta_columns()    # dDiscount, dProm
        ↓
apply_week_discount_filters()           # min/max filter table
        ↓
UI: styled dataframe or data_editor
```

Orchestrated by `build_working_week_discount_rows()` in `discount_strategy.py`.

### Delta rules (`week_basket_tables.py`)

- **Current** for deltas = historical `Discount[…]` / `Prom[…]`, resolved via `week_discount_historical_current_column()` — **not** New Discount / New Prom
- **`_safe_delta(new, current)`** — missing values on either side treated as **0**

Example: `Prom[current]=0.02`, `New Prom` empty → `dProm = -0.02`

### Discount strategy (`discount_strategy.py`)

Settings loaded from `configs/strategies/strategies.v1.csv` (sectioned CSV format).

**Modes:**

1. **Based on Strategies** — `Discount[new] = Discount[current] + (dDiscount(strategy) + Balance) × Multiplicator`
2. **Set previous discount**
3. **Zero all Discounts**

**Sub-rules:**

- Sold = 0 → separate sold-zero strategy table + balance
- MtoSt strategy (optional toggle) → `dMtoSt_QW` bins when margin conditions met
- Margin categories → Conservative / Moderate / Strong lookup by current margin
- Priority 1: missing `Discount[current]` → `missing_discount_default` (UI default 0)

### Prom strategy (`prom_strategy.py`)

Currently one mode: **Set previous prom** (`New Prom = Prom[current]`).

Additional prom sections in `strategies.v1.csv` are reserved for future modes.

### Export paths

| Export | Module functions |
|--------|------------------|
| Week Discount CSV | `normalize_week_discount_export_rows`, `expand_week_discount_export_rows` |
| Discount history CSV | `build_discount_hist_export_rows`, `advance_discount_hist_week_metadata`, `merge_discount_hist_export` |

Canonical basket universe: `inputs/full list of baskets.csv` (625 baskets, 5⁴ codes).

---

## Analytics modules reference

### `core/transforms/data_prep.py`

| Function group | Purpose |
|----------------|---------|
| `normalize_csv_df`, `index_by_week`, `resolve_common_weeks` | Legacy wide-CSV ETL |
| `tracking_report_to_frame_set` | TrackingBaskets_v2 report → metric frames |
| `tracking_product_bs_report_to_frame_sets` | product_BS report → per-category frames |
| `compute_basket_features`, `compute_weekly_totals` | Feature + correlation computation |
| `parse_discount_hist_lookup` | Discount history ingest |
| `build_discount_hist_export_rows`, `merge_discount_hist_export` | Discount history export |

### `core/analytics/basket_analysis.py`

| Function | Purpose |
|----------|---------|
| `run_basket_analysis` | Legacy 4-file pipeline |
| `run_tracking_report_analysis` | Report mode entry |
| `run_tracking_product_bs_report_analysis` | product-BS entry |
| `apply_kmeans`, `apply_octants` | Cluster assignment |
| `compute_sumup_series` | Sum-Up table rows |

### `core/analytics/week_basket_tables.py`

Week Discount column metadata, row builders, filters, weighted comparison, summary metrics, export normalization.

### `core/clustering/`

- **K-Means:** 3D correlation coordinates (`corr_SP`, `corr_MP`, `corr_MS`), NaN → 0
- **Octants:** Sign-based assignment into 8 groups

### `core/modeling/regression.py`

- Plane fit: `Sold = z₀ + a·Price + b·Stock`
- Line fit: `Cost = z₀ + a·Price` → leverage price Pl
- PCA orthogonal fit variant

### `core/optimization/price_optimization.py`

Analytical `Price_max(Stock)` from combined sold + cost fits; used in basket and Sum-Up margin model UI.

### `visualizations/`

Plotly figure builders consumed by the main page. No Streamlit imports; figures passed to `st.plotly_chart()`.

---

## Configuration

| File | Contents |
|------|----------|
| `configs/settings.py` | `APP_TITLE`, paths, `DEFAULT_MIN_PRICE`, K-Means defaults, cluster colors |
| `configs/strategies/strategies.v1.csv` | Discount bins, margin categories, MtoSt bins, defaults |
| `.streamlit/config.toml` | Streamlit server/theme settings |

Strategy UI cache version: `DISCOUNT_SETTINGS_UI_VERSION = 5` in `week_discount_ui.py` (invalidates `@st.cache_data` when parsing changes).

---

## Testing

```powershell
python tests/test_e2e.py
```

`tests/test_e2e.py` exercises:

- Legacy 4-CSV pipeline, K-Means, Octants
- Tracking report and product-BS modes
- Discount history parse/apply and export merge
- Week Discount columns, dProm delta rules, manual overrides
- Prom strategy, full-basket export (625), scope isolation
- Strategies v1 loading

**Not covered:** Streamlit widget integration, browser UX, Cloud deployment runtime.

---

## Deployment

| Target | Notes |
|--------|-------|
| Local | `streamlit run app.py --server.port 8501` |
| Streamlit Cloud | https://discount-manager-v1-1.streamlit.app/ |
| GitHub | https://github.com/anton-shmargunov/Discount-manager |
| Python | 3.11+ locally; **3.12** recommended on Cloud |
| Secrets | Empty for MVP (sample data in `inputs/`) |

Push to `main` triggers Cloud redeploy (~1 minute).

---

## Phase 2 migration path

The codebase is structured for reuse without refactor:

```
Next.js Frontend
      ↓
FastAPI API Layer
      ↓
core/ (unchanged)
      ↓
pipelines/ · workers
      ↓
PostgreSQL + TimescaleDB + DuckDB
```

UI extraction continues incrementally (`ui/week_discount_ui.py` is the pattern for Sum-Up and Basket Detail).

---

## Known limitations and risks

| Area | Detail |
|------|--------|
| Streamlit `data_editor` | Do not assign widget key in `session_state` before render; no preview DataFrame feedback in edit mode |
| Session-only state | Generated/manual discount values lost on browser refresh |
| Scope switch | Rebuild after changing input mode or category |
| Discount hist export | `all history` merge requires upload at Build |
| Main page size | `01_Correlation_Analysis.py` still monolithic for sections ⑤–⑥ |
| Prom strategies | Only "Set previous prom" implemented |

---

## Related documents

- [user-manual.md](user-manual.md) — operator guide
- [README.md](../README.md) — quick start
- `handoff_260623.md` — latest developer handoff
- `PBA. Arch. Spec. Phase 1.txt` — original specification
