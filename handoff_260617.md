# PBA v1 — Handoff for Fresh Chat

## Goal

Port the HTML/JS analytics prototype into a **Python Streamlit MVP** for Pricing Correlation & Bucket Analysis, following `PBA. Arch. Spec. Phase 1.txt`:

- **Analytics must never depend on UI**
- `core/` = pure analytics
- `visualizations/` = pure Plotly
- `pages/` = Streamlit orchestration only

The app is now a functional MVP with multiple input modes, basket clustering, drill-down, sum-up analytics, exports, and product-BS category handling.

---

## Project Root

`d:\Anton\UTires\Code\Pricing\Pricing Correlation and Bucket Analysis\streamlit\PBA.v.1.250525\`

Run:

```powershell
streamlit run app.py --server.port 8501
python tests/test_e2e.py
```

---

## Architecture (unchanged)

```
core/              pure Python analytics, no Streamlit
visualizations/    Plotly chart builders, no Streamlit
pages/             Streamlit UI only
configs/           constants, theme bootstrap
tests/             smoke/e2e tests
inputs/            sample CSVs
```

---

## Major Decisions Made

### Input modes (4 total)

1. `Separate metric CSVs`
2. `TrackingBaskets_v2 report`
3. `TrackingBaskets_v2 - product_BS. on date of sale`
4. `TrackingBaskets_v2 - product_BS. monthly av.`

Product-BS modes share one uploader and a **Product BS Category** selector: `Aggregated`, `In`, `Out`, `OutByCondition`, `OutByMinPrice`, `none`.

### Product-BS metric rules

**Stock-like metrics** (`StockQty_W`, `PurchaseQty`, `CountProduct_W`):

- Specific category: from rows where `product BS` maps to that category
- `Aggregated`: sum across all `product BS` rows for week/basket

**On date of sale — Sold/Revenue/Margin:**

- Specific category: suffix columns (`SoldQty_In`, `Revenue_In`, etc.), summed across all `product BS` rows
- `Aggregated`: unsuffixed `SoldQty`, `Revenue`, `Margin`, summed across all rows

**Monthly av. — Sold/Revenue/Margin:**

- Specific category: unsuffixed `SoldQty`, `Revenue`, `Margin` from matching `product BS` row
- `Aggregated`: unsuffixed values summed across all rows

**Avg Price** is always `Revenue / SoldQty`.

Validated against user sample basket `5555` / week `2026-23`.

### TrackingBaskets_v2 report blank cells

Blank numeric cells (`SoldQty`, `AvgSalePrice`, `Margin`, etc.) are now coerced to `0.0`, not dropped.

- Included when **Avg Sale Price Range min = 0**
- Still filtered out by default min `0.001`

### UI / UX

- Sidebar **Log** for upload/build/warning messages
- **Detailed Basket Breakdown**: header tooltips, bulk fit buttons, `Sold/Purchase`, `Total Purchase`, `Avg CountProduct`
- **Sum-Up table**:
  - `Show` (single week for Weekly Detail) vs `Select` (multi-week export)
  - `QW`, `week in QW`
  - Extended columns: stock, count product, purchase, revenue, cost
  - `Colour by QW`, `Select All`, `Export Total`, `Export Week vs Basket`
  - Default: all rows selected
  - `Export Total` exports selected rows only

### Theme loading

Centralized in `configs/theme_bootstrap.py` (`PBA_THEME` single source of truth):

- `.streamlit/config.toml` light theme (mirrors `PBA_THEME`)
- `FORCE_LIGHT_CSS` — expanded widget-level fallback before Streamlit hydrates
- `THEME_BOOTSTRAP_HTML` — seeds `stActiveTheme-${pathname}-v1` for `/` and `/Correlation_Analysis`
- `apply_page_theme()` called from `app.py` and `pages/01_Correlation_Analysis.py`

Bootstrap improvements (2026-06-18):

- Aligned `bodyFont` with config.toml (`sans serif`, not hardcoded Source Sans)
- Proactive multi-path localStorage seeding
- `MutationObserver` + polling for hydration detection
- Loading overlay until `.stApp` + widgets mount (max 8s)
- One auto-reload per path when cache was stale; guard cleared after hydration

**Manual verification checklist** (clear site data first):

1. Cold load `http://localhost:8501/` — light theme, no manual refresh
2. Cold load `http://localhost:8501/Correlation_Analysis` directly
3. Navigate home → Correlation Analysis
4. Hard refresh (Ctrl+F5) on analysis page
5. OS dark mode — app stays light

**Status:** hardened; if flakiness persists on Streamlit 1.49, upgrade to `>=1.52` and switch to `st.html(unsafe_allow_javascript=True)`.

---

## Files Changed (this chat session)

| Area | File | What changed |
|---|---|---|
| Models | `core/models.py` | `count_product`, `purchase`, `week_in_quad` on time series/weekly totals; `average_count_product`, `total_purchase` on `BasketResult` |
| Transforms | `core/transforms/data_prep.py` | Product-BS parsers (on-date + monthly av.), stock/purchase/count product handling, aggregate logic, blank-cell fix for tracking report, week-in-quad propagation |
| Analytics | `core/analytics/basket_analysis.py` | Product-BS wrappers, sum-up fields (`total_stock`, `total_count_product`, `total_purchase`, `total_revenue`, `week_in_quad`) |
| UI | `pages/01_Correlation_Analysis.py` | All input modes, Sum-Up controls/exports, basket table columns, TB Raw export, theme bootstrap, many chart/fit integrations |
| Config | `configs/theme_bootstrap.py` | **New** — `PBA_THEME`, `apply_page_theme()`, expanded CSS + JS bootstrap |
| Config | `configs/settings.py` | Re-exports theme constants from `theme_bootstrap` |
| Entry | `app.py` | Theme bootstrap injection |
| Theme | `.streamlit/config.toml` | Light theme + client/browser settings |
| Charts | `visualizations/sumup_charts.py` | Weekly detail 3D charts, sum-up fits, vertical stack, log axes |
| Charts | `visualizations/detail_charts.py` | Fitted indices, margin surface support |
| Tests | `tests/test_e2e.py` | Product-BS cases, stock/purchase/count product, blank tracking rows, basket `5555` validation |
| Inputs | `inputs/TB Raw selected weeks.csv` | Export format reference |
| Handoff | `handoff_260601` | Partially overwritten; use this file instead |

---

## Current Feature State

**Working:**

- 4 input modes
- K-Means / Octants clustering
- Basket drill-down with fits and margin model
- Sum-Up weekly analytics + exports
- Product-BS category selection
- CountProduct / Purchase / Stock metrics in basket and sum-up tables
- TB Raw selected-week export
- E2E smoke test passes

**Recently fixed:**

- Product-BS `none` row with `SoldQty_In` counted in `In` mode
- Stock/Purchase/CountProduct category vs aggregated logic
- Tracking report blank sales rows with `min_price=0`
- Sum-Up `Select All`, default all selected, export selected only
- First-load theme hydration (centralized bootstrap, expanded CSS, multi-path cache seeding)

---

## Tests Run

```powershell
python -m py_compile core\models.py core\transforms\data_prep.py core\analytics\basket_analysis.py pages\01_Correlation_Analysis.py tests\test_e2e.py
python tests/test_e2e.py
```

**Last result:** `ALL TESTS PASSED`

`tests/test_e2e.py` now covers:

- Legacy 4-CSV basket analysis (198 baskets, 9 weeks)
- K-Means / Octants
- TrackingBaskets_v2 report
- Product-BS on-date and monthly av.
- `none` row with suffix In sales
- Basket `5555` stock/purchase/sold/revenue expectations
- Blank tracking report row with `min_price=0`

**Not covered:**

- Full Streamlit UI interaction tests
- Browser theme bootstrap reliability
- Real-file tests for every external sample path outside `inputs/`

---

## Remaining TODOs / Known Gaps

1. **Phase 2 architecture** — DuckDB, `pipelines/`, `services/`, SaaS migration not started.
2. **Additional pages** — only `01_Correlation_Analysis.py` exists.
3. **Malformed CSV UX** — errors are technical `ValueError`s, not user-friendly messages.
4. **No auth / multi-user** — `st.session_state` only.
5. **Sum-Up `Show` vs `Select All`** — `Select All` resets table widget via generation counter; edge cases with manual edits + toggle may need UX polish.
6. **`handoff_260601`** — stale/overwritten; superseded by this file.
7. **External sample files** — user-provided paths under `d:\Anton\UTires\Pricing\Reports\...` are not in repo; tests use synthetic equivalents.
8. **Theme bootstrap** — localStorage workaround; upgrade to Streamlit 1.52+ if edge cases remain.

---

## Risks

| Risk | Detail |
|---|---|
| Product-BS logic complexity | Different rules for stock vs sold/revenue across 3 modes; easy to regress |
| On-date suffix vs row label | Suffix sales can appear on `product BS=none` rows; stock must still come from matching `product BS` row only |
| Aggregated totals | Must use raw unsuffixed totals for on-date aggregate sold/revenue, not sum of suffix categories |
| Blank/zero price filtering | `min_price=0` vs default `0.001` behavior is intentional but easy to confuse users |
| Styled `st.data_editor` | Sum-Up uses Pandas Styler for QW colors; Streamlit version changes may affect behavior |
| Theme bootstrap JS | Depends on browser localStorage and iframe parent access |
| Large UI file | `pages/01_Correlation_Analysis.py` ~1900 lines; further features should move helpers out |
| No CI | Tests are manual/local only |

---

## Key Reference Paths

- Spec: `PBA. Arch. Spec. Phase 1.txt`
- Main page: `pages/01_Correlation_Analysis.py`
- Parser logic: `core/transforms/data_prep.py` → `tracking_product_bs_report_to_frame_sets`, `tracking_report_to_frame_set`
- Orchestrator: `core/analytics/basket_analysis.py`
- Tests: `tests/test_e2e.py`
- Past chat: `51fe92c7-f25e-4289-9fba-cf4e75be2a86`

---

## Suggested First Message for Fresh Chat

> Continue PBA Streamlit MVP at `PBA.v.1.250525`. Architecture: analytics in `core/`, charts in `visualizations/`, UI in `pages/`. Four input modes including product-BS on-date and monthly av. Product-BS parsing rules for stock vs sold/revenue are implemented and tested. Sum-Up table has Show/Select, QW coloring, Select All, Export Total (selected rows), Export Week vs Basket. Last test: `python tests/test_e2e.py` → ALL TESTS PASSED. Open issue: Streamlit first-load theme/widget hydration may still need refresh.
