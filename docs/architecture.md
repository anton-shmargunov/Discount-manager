# PBA — Architecture

**Pricing Correlation & Bucket Analysis · Phase 1 Streamlit MVP**

Version 1.0.2.t1 · Last updated 2026-10-10

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
│   └── 01_Correlation_Analysis.py  # Main analysis page (~3600 lines)
│
├── ui/                             # Reusable Streamlit sections (no analytics)
│   ├── product_bs_scope.py         # Per-mode/category session isolation
│   ├── week_discount_ui.py         # Week Discount UI (strategy, table, exports)
│   ├── planner_ui.py               # Sidebar Planner (Campaign / Job) + conflict dialog
│   ├── auth_gate.py                # Login / password gate (require_login)
│   └── project_save_ui.py          # Sidebar Project save / restore (.disc_proj)
│
├── core/                           # Pure analytical engine
│   ├── models.py                   # Dataclasses: BasketTimeSeries, BasketResult, …
│   ├── persistence/
│   │   └── project_io.py           # .disc_proj pack / unpack / apply (no Streamlit)
│   ├── security/
│   │   └── passwords.py            # PBKDF2 hash / verify, login throttle
│   ├── analytics/
│   │   ├── basket_analysis.py      # run_*_analysis, clustering hooks, sum-up
│   │   ├── week_basket_tables.py   # Week Discount rows, filters, deltas, export
│   │   ├── discount_strategy.py    # Strategy bins, generation, manual overrides
│   │   ├── prom_strategy.py        # Prom generation ("Set previous prom")
│   │   ├── planner.py              # Campaign / Job model, assignment, generate-all
│   │   ├── cost_correction.py      # Cost Corrected / Margin Corrected series
│   │   ├── selected_basket_margin.py  # Margin Corrected for multi-basket detail
│   │   ├── selected_basket_weeks.py   # Weekly Sum-Up of a basket selection
│   │   └── weighted_discount.py    # Stock / CountProduct / Sold weighted Discount, Prom
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
│       ├── price_optimization.py   # Margin model Price_max(Stock)
│       └── margin_model_eval.py    # Margin-model error metrics + target point
│
├── visualizations/                 # Plotly chart builders (no Streamlit)
│   ├── cluster_charts.py
│   ├── detail_charts.py
│   ├── progress_stack.py           # Vertical-stack progress figures
│   ├── sumup_charts.py
│   └── sumup_qw_charts.py          # Sum-up charts with quadweek colour / QW average
│
├── configs/
│   ├── settings.py                 # App constants, paths, cluster colors
│   ├── theme_bootstrap.py          # Light-theme CSS injection
│   └── strategies/
│       └── strategies.v1.csv       # Discount strategy defaults (prom reserved)
│
├── inputs/                         # Sample CSVs and canonical basket list (625)
├── scripts/
│   └── hash_password.py            # Prints a secrets.toml entry for one user
├── tests/
│   └── test_e2e.py                 # End-to-end smoke tests
├── docs/
│   ├── architecture.md             # This file
│   └── user-manual.md
│
├── CHANGELOG.md                    # Main updates by version
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
| ④ Detailed Basket Breakdown | Sortable basket table; row click → drill-down; Group / Multiselect; **Set a Job** |
| ⑤ Basket Detail | Week Progress charts, fits, margin model |
| ⑥ Sum-Up | Weekly aggregates, correlation KPIs, week selector, margin model |
| Per-week expanders | Weekly Detail, **Week Discount**, Week Visualization |

Extracted UI modules:

- `render_week_discount_section()` from `ui/week_discount_ui.py`
- Scope helpers from `ui/product_bs_scope.py` (`PRODUCT_BS_CATEGORY_OPTIONS`, `iter_built_product_bs_scopes`)
- `render_sidebar_project_panel()` / `apply_pending_project_restore()` from `ui/project_save_ui.py`
- `render_sidebar_planner_panel()` from `ui/planner_ui.py`

**Basket Detail selection priority** (first match wins): Group → Select All → table rows → Planner focus. Planner focus is the selected Jobs or, when no Job is selected, every basket of the selected Campaign. A single-basket Basket Detail therefore needs the Planner Campaign set to **Select…**.

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
| `fit_sold_indices[basket]`, `fit_sumup_stock_sold_indices` | Weeks used by the last **Fit Plane** (margin-model metrics reuse them) |
| `margin_model[basket]`, `sumup_margin_model` | Saved model: `result`, `target` (point evaluation), `metrics` (Adj R², RMSE, MAPE) |
| `planner` | Campaign / Job planner (see [Campaign / Job Planner](#campaign--job-planner)) |
| `discount_hist_df` | Copy of uploaded discount history at build time |
| Week Discount keys (scoped) | `wd_generated_discount_{week}`, `wd_manual_overrides_{week}`, … |

`clear_product_bs_scope_derived()` resets selections, fits, fit-week indices and margin models on **Build Project**. The Planner is kept.

Global (unscoped): `input_mode`, filter text inputs, sidebar log (`log_messages`).

A full session snapshot (all scopes + picklable UI keys + log) can be saved as `.disc_proj` — see [Project persistence](#project-persistence).

---

## Discount history pipeline

Optional CSV(s) merged at **Build** into `BasketTimeSeries.discount` / `.prom`. Multiple files are accepted.

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
- `merge_discount_hist_dataframes()` — combine one or more uploaded CSVs by `(year_week, basket)` (later non-blank values win)
- `build_discount_hist_export_rows()` + `merge_discount_hist_export()` — export with week **+1** metadata
- `combine_discount_hist_export_by_category()` — merge per-category New Discount/Prom into one wide hist file (`DISCOUNT_HIST_CATEGORY_ORDER`)

The discount-history uploader accepts **multiple files**. At Build they are aggregated with `merge_discount_hist_dataframes()` before parse/apply. A single combined file also works.

---

## Campaign / Job Planner

Model and rules live in `core/analytics/planner.py` (no Streamlit). The sidebar panel and the conflict dialog live in `ui/planner_ui.py`.

- **Storage:** `scope["planner"]`, a plain dict, so it is saved in `.disc_proj`. Older planners are migrated through `settings_version` (currently 2).
- **Hierarchy:** Campaign → Jobs. IDs are 10 digits (`new_planner_id`).
- **Exclusive membership:** a basket belongs to at most one Job; a Job belongs to one Campaign.
- **Strategies:** each Job stores its own serialized Discount and Prom settings. Baskets with no Job use the planner's default settings, seeded from `configs/strategies/strategies.v1.csv`.

| Action | Where | Function |
|--------|-------|----------|
| Create / rename / delete Campaign or Job | Sidebar **Planner** | `add_*`, `rename_*`, `delete_*` |
| **Update** the selected Job to the current table selection | Sidebar **Planner** | `find_assignment_conflicts`, `apply_job_assignment` |
| **Set a Job** from the current Group | ④ Combination expander | same, with a new Job |
| **Apply** on-screen strategy settings | Week Discount | `store_default_settings` (Campaign switch off) / `apply_settings_to_jobs` (on) |

Assigning a basket that already belongs to another Job opens a per-basket **conflict dialog** (`st.dialog` + `data_editor`: Approve all / Keep all / Confirm / Cancel). Only approved baskets move.

`assignment_lookup()` feeds the **Campaign** and **Job** columns of the Detailed Basket Breakdown and Week Discount tables, and the discount-history export.

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

### Generation buttons and the Planner

| Button | Baskets | Settings | Existing generated values |
|--------|---------|----------|---------------------------|
| **Generate Discount / Prom**, Campaign switch off | Unassigned baskets | On-screen | Merged |
| **Generate Discount / Prom**, Campaign switch on | Baskets of the Planner-selected Jobs | On-screen | Merged |
| **Generate Discount all / Prom all** | Every Job, plus unassigned baskets | Each Job's stored settings; stored default for unassigned | Replaced |

Target selection: `target_baskets_for_generate()`. Generate-all: `generate_discount_all_jobs()` / `generate_prom_all_jobs()`.

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

UI lives in the Week Discount **Export** expander. Buttons are disabled while Edit mode is active.

| Export button | Module functions | Scope |
|---------------|------------------|--------|
| **Week Discount** | `normalize_week_discount_export_rows`, `expand_week_discount_export_rows` | Visible columns for the current category |
| **Discount history. Current** | `build_discount_hist_export_rows`, `advance_discount_hist_week_metadata`, `merge_discount_hist_export` | Current Product BS category (report mode: Aggregated) |
| **Discount history. All** | `iter_built_product_bs_scopes` + `combine_discount_hist_export_by_category` | product_BS modes only; every **built** category in this session |

Discount-history exports end with four Planner columns: `campaign_id`, `campaign_name`, `job_id`, `job_name`.

**Discount history. All** is omitted in report mode. It only includes categories that have been **Built** (and generated/edited) this session — switching category and building each one is required.

Checkboxes: **Include 'no stock'** (canonical 625-basket list) and **all history** (merge uploaded hist + new week; last duplicate `(basket, year_week)` wins).

A progress bar (`st.progress`) runs while Week Discount rows are computed, generated, applied, and rendered; it is cleared before the Export expander.

Canonical basket universe: `inputs/full list of baskets.csv` (625 baskets, 5⁴ codes).

---

## Access control

The Correlation Analysis page calls `require_login()` (`ui/auth_gate.py`) right after `set_page_config` / theme, before any session init, restore or sidebar. Until a user signs in, the script ends with `st.stop()`. The check is in the page itself because Streamlit pages can be opened directly by URL. The home page (`app.py`) stays public; it shows no data.

**Users** are stored in the app secrets (`.streamlit/secrets.toml` locally, which is gitignored; **Settings → Secrets** on Streamlit Cloud):

```toml
[app_users.anton]
password_hash = "pbkdf2_sha256$600000$<salt_hex>$<hash_hex>"
name = "Anton"   # optional
```

Create an entry with `python scripts/hash_password.py`; it reads the password without echoing it. Only hashes are stored, never plain passwords. The `[auth]` section name is reserved for Streamlit's `st.login()`, which is why users live under `[app_users]`.

| Safeguard | Implementation |
|-----------|----------------|
| Password storage | PBKDF2-HMAC-SHA256, 600 000 iterations, 16-byte random salt (stdlib `hashlib`) |
| Comparison | `hmac.compare_digest`; unknown logins verify against a dummy hash, so timing does not reveal which logins exist |
| Brute force | `LoginThrottle`: 5 failures in 15 min lock that login for 5 min (per server process), plus a 1 s delay on each failure |
| Fail closed | No `[app_users]` configured → page locked with an "Access is not configured" message |
| Revocation | A user removed from secrets is signed out on their next interaction |
| Session scope | Login lives in `session_state` only (no cookie). Refresh or a new tab means signing in again. **Log out** clears the whole session |
| Project files | `_auth_*` keys are never written to `.disc_proj` and never set by a restore |

**Alternatives considered:**
- **`st.login()` (OIDC)** with Google / Microsoft / Auth0: stronger (MFA, central user management), but needs an identity-provider client and isn't login/password.
- **Streamlit Community Cloud private app**: viewer allowlist by email, enforced by the platform. Only one private app per workspace, and the repo must be private.
- **`streamlit-authenticator`**: bcrypt plus a 30-day JWT cookie. It's third-party and pulls in several dependencies; a cookie only adds convenience.

**Security note:** `.disc_proj` files are pickles. Loading a crafted file can run code on the server, so only Restore files you created. Restore is only reachable after sign-in.

---

## Project persistence

Sidebar expander **Project** (above **Log**). Format: magic `PBA1DISC` + gzip pickle. Extension `.disc_proj`. Implementation: `core/persistence/project_io.py` (pure Python) + `ui/project_save_ui.py`.

| Action | Behaviour |
|--------|-----------|
| **Save…** | Dialog for filename → download snapshot |
| **Restore** | File uploader (`type=["disc_proj"]`) then **Restore** |

Payload: `format`, `version`, `saved_at`, `ui` (picklable session keys), `scopes` (`_pbs_scopes` including `analysis`, `discount_hist_df` and `planner`), `log_messages`.

Restore does **not** need the report or discount-history CSVs: the built `AnalysisResult` (with discount/prom already merged), `discount_hist_df`, the Planner and the UI settings are all in the file. Only **Build** reads the uploaders.

**Not saved / not restored:**

- Original CSV uploads (`fu_*` keys, `UploadedFile` objects)
- Streamlit **button**, **download_button** and **form_submit_button** keys (session assignment is forbidden)
- Streamlit widget-state objects (`data_editor` / `dataframe` selection states), detected by type
- Project-panel widget keys (`_project_*`)

### Widget key naming rule

Streamlit raises `StreamlitValueAssignmentNotAllowedError` if a restored session value has the key of a button-type widget or a file uploader. `project_io` skips these keys by name:

| Widget | Key rule | Example |
|--------|----------|---------|
| `st.button`, `st.download_button`, `st.form_submit_button` | Ends with **`_btn`** (`BUTTON_KEY_SUFFIX`) | `wk(f"wd_generate_discount_{week}_btn")` |
| `st.file_uploader` | Starts with **`fu_`** (or `_project_`), unscoped | `"fu_discount_hist"` |

Scoped keys (`scope::name`) keep the suffix, so `wk()` / `sk()` are fine for buttons. Unkeyed buttons are safe: Streamlit stores them under internal IDs that are never saved. `tests/test_e2e.py` (`_button_key_naming_violations`) parses `pages/` and `ui/` and fails on any keyed button or uploader that breaks the rule.

### Cross-version loading

Cloud and local run different Streamlit and NumPy versions. `_ProjectUnpickler` therefore:

- returns `UnavailableWidgetState` (a dict stand-in that is never restored) for **any** `streamlit.*` class;
- maps `numpy.core` ↔ `numpy._core`.

On save, pyarrow string columns of `discount_hist_df` are converted to `object`. Read errors include the underlying exception text.

Restore applies **before** widgets render (`apply_pending_project_restore()`). Widget-key cleanup must **not** delete `_pbs_scopes`. Browser **Save As / fixed download folder** is not available in Streamlit Cloud; a desktop wrapper would be needed for a true disk path.

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
| `merge_discount_hist_dataframes` | Multi-file hist upload merge |
| `build_discount_hist_export_rows`, `merge_discount_hist_export` | Discount history export |
| `combine_discount_hist_export_by_category` | All-category hist export combine |

### `core/persistence/project_io.py`

`.disc_proj` snapshot: `build_project_payload`, `pack_project_bytes`, `unpack_project_bytes`, `apply_project_payload`. Must not import Streamlit.

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

### `core/optimization/margin_model_eval.py`

Diagnostics for the same analytical model, `M(P, S) = (P·(1 − a_cost) − z0_cost) · Sold(P, S)`:

| Function | Purpose |
|----------|---------|
| `compute_margin_fit_metrics` | Adj R² (p = 2), RMSE, MAPE of model M vs actual M over given week indices (the Sold plane fit weeks) |
| `evaluate_margin_target` | Model at the actual point vs a target point (default: Price_max at actual stock). Returns Sold (model), Price_diff, M gain, Sold gain and a plain-`bool` `is_manual` |
| `compute_model_sold`, `price_max_or_fallback` | Helpers for the manual Price / Stock inputs |

Basket Detail passes the plotted margin, which is the hybrid series when **Margin Corrected** is on.

### `visualizations/`

Plotly figure builders consumed by the main page. No Streamlit imports; figures passed to `st.plotly_chart()`.

`sumup_qw_charts.py` holds the Sum-up variants driven by the **Line + Symbol**, **Colour by Quadweek** and **QW Average** toggles (`build_sumup_3panel_qw`, `build_sumup_3d_qw`, `build_combined_progress_qw`, `build_vertical_stack_from_specs_qw`, …). The "Separate plots" view uses `build_metric_progress(quadweeks=…, use_qw_colors=…, show_qw_average=…)`.

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
- Multi-file discount hist merge, all-category export combine
- `.disc_proj` round-trip; `_btn` / `fu_*` keys skipped on restore; missing or live Streamlit classes; pyarrow → object
- Button / uploader key naming rule across `pages/` and `ui/`
- Planner: membership, conflicts, generate-all; discount-history Planner columns
- Margin-model metrics and manual target point
- Password hashing / verification, login throttle, `_auth_*` keys excluded from `.disc_proj`

pytest is not installed; the file runs as a script. Compile check: `python -m py_compile <file>`.

**Not covered:** Streamlit widget integration, browser UX, Cloud deployment runtime, Project Restore of very large sessions in the browser. Real-data UI checks were run ad hoc with `streamlit.testing.v1.AppTest` (set `PYTHONIOENCODING=utf-8` on Windows).

---

## Deployment

| Target | Notes |
|--------|-------|
| Local | `streamlit run app.py --server.port 8501` |
| Streamlit Cloud | https://discount-manager-v1-1.streamlit.app/ |
| GitHub | https://github.com/anton-shmargunov/Discount-manager |
| Python | 3.9+ locally (tested on 3.9.13); **3.12** on Cloud |
| Streamlit | `>=1.49` (needs `width="stretch"` on buttons, `dataframe`, `data_editor`) |
| Secrets | `[app_users]` login entries (see [Access control](#access-control)). Add them on Cloud **before** pushing, or the page is locked |

Each Cloud app redeploys (~1 minute) when its branch is pushed: the main app from `main`, the test app from `v1-1-test_1`.

Layout widths use `width="stretch"`; `use_container_width` is deprecated and must not be reintroduced. `st.plotly_chart` gets no width argument: it stretches by default in both 1.49 and newer releases.

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
| Session-only state | Generated/manual discount values lost on browser refresh unless saved as `.disc_proj` |
| Project restore + widgets | Button keys must end with `_btn`, uploader keys start with `fu_` (see [Widget key naming rule](#widget-key-naming-rule)); uploads are not re-attached. Cleanup must preserve `_pbs_scopes`. |
| Cloud stale modules | Streamlit Cloud can serve old copies of existing modules. Put new public names in **new modules** and do not add kwargs to builders that pages already call. |
| Margin model on weak fits | If the Sold slope vs Price is positive, the stationary point is a margin **minimum** and M surplus is negative. Real-data fits are weak (Adj R² often < 0.4). |
| Planner focus | A selected Campaign with no Job puts the whole Campaign in focus and overrides single-basket Basket Detail |
| Scope switch | Rebuild after changing input mode or category |
| Discount hist export | `all history` merge requires upload at Build; **Discount history. All** only includes **built** categories |
| Download folder | Browser-controlled; app cannot set Save As path |
| Main page size | `01_Correlation_Analysis.py` still monolithic for sections ⑤–⑥ |
| Prom strategies | Only "Set previous prom" implemented |

---

## Related documents

- [user-manual.md](user-manual.md) — operator guide
- [README.md](../README.md) — quick start
- [CHANGELOG.md](../CHANGELOG.md) — main updates by version
- `handoff_261008.md` — latest developer handoff (Planner, Cloud restore, margin-model table, Sum-up toggles)
- `handoff_260912.md` — Project save, all-BS export
- `handoff_260623.md` — Week Discount edit/export, Cloud deploy
- `PBA. Arch. Spec. Phase 1.txt` — original specification
