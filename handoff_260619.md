# PBA v1 — Handoff (2026-06-19)

## Start here

**This is the current handoff for a fresh chat.**

Read in order if you need full context:

1. **`handoff_260619.md`** (this file) — latest Sum-Up / Week Detail / Week Discount work
2. **`handoff_260618.md`** — Basket Detail toggles, QW coloring, QW averages
3. **`handoff_260617.md`** — full MVP baseline (input modes, product-BS, theme, architecture)

---

## Goal

Port the HTML/JS analytics prototype into a **Python Streamlit MVP** for Pricing Correlation & Bucket Analysis per `PBA. Arch. Spec. Phase 1.txt`:

- **Analytics must never depend on UI**
- `core/` = pure analytics
- `visualizations/` = pure Plotly
- `pages/` = Streamlit orchestration only

The app is a functional MVP: 4 input modes, clustering, basket drill-down, Sum-Up analytics, per-week basket tables, exports, product-BS handling.

---

## Project Root

`d:\Anton\UTires\Code\Pricing\Pricing Correlation and Bucket Analysis\streamlit\PBA.v.1.250525\`

```powershell
streamlit run app.py --server.port 8501
python tests/test_e2e.py
```

---

## Architecture

```
core/              pure Python analytics, no Streamlit
  analytics/       basket_analysis, week_basket_tables
  statistics/      correlations, metrics (monthly_reserve)
  transforms/      data_prep, product-BS parsers
visualizations/    Plotly chart builders, no Streamlit
pages/             Streamlit UI only (~2360 lines main page)
configs/           theme_bootstrap, settings
tests/             smoke/e2e tests
```

---

## Major decisions (cumulative)

### MVP baseline (see `handoff_260617.md`)

- 4 input modes including product-BS on-date and monthly av.
- Product-BS parsing rules for stock vs sold/revenue differ by mode
- Sum-Up table: Show/Select, QW coloring, exports, extended columns
- Theme bootstrap via `configs/theme_bootstrap.py`

### Basket Detail (see `handoff_260618.md`)

- Three global toggles: **Line + Symbol**, **Colour by Quadweek**, **QW Average**
- Single connected trace per series; QW colors on markers only
- Fit highlight (`fitted_indices`) only when scope = **Manual Selection**
- QW Average: dashed hlines (Week Progress), diamond markers (scatter/3D/cost)

### Monthly Reserve (2026-06-19)

Formula: `Stock / Sold × 7 / 30` (months to sell out at weekly sold rate)

- Basket Detail Week Progress toggle (off by default)
- Sum-Up column **Total Monthly Reserve** after Cost
- Implemented in `core/statistics/metrics.py`; sum-up via `compute_sumup_series()`

### Sum-Up section layout (2026-06-19)

After Sum-Up table + export buttons:

1. **📊 Sum-Up Total** (parent expander, expanded)
   - Stock Progress
   - Total Sold vs W. Price · Total M vs W. Price · Total M vs Total Sold
   - Total Cost vs W. Price
   - 3D aggregate charts + margin optimisation

KPIs + editable Sum-Up table stay **outside** the parent expander.

### Per-week drill-down (when Sum-Up **Show** checked)

Three sibling expanders (require `ss.selected_week`):

| Expander | Purpose |
|---|---|
| **📋 Weekly Detail: {week}** | Per-basket table — Sum-Up columns minus Corr |
| **📉 Week Discount: {week}** | QW-relative basket metrics + filters |
| **📅 Week Visualization: {week}** | Basket scatter + 3D charts (renamed from “Weekly Detail”) |

---

## Week Discount — design

Location: `core/analytics/week_basket_tables.py` + UI in `pages/01_Correlation_Analysis.py`

### Column groups (per basket, selected week)

| Group | Delta (vs W−4) | Level columns (offsets) |
|---|---|---|
| Stock | `dSt_QW` | W, W−1, W−4, W−5 |
| Margin | `dM_QW` | W, W−1, W−4, W−5 |
| MtoSt | `dMtoSt_QW` | W, W−4 only |
| Sold | `dSold_QW` | W, W−1, W−4, W−5 |
| Price | `dPrice_QW` | W, W−1, W−4, W−5 |

- Delta formula: `current / (W−4) − 1`
- MtoSt = `Margin / Stock`
- Headers dynamic: `Stock[19,1]` from week’s `quadweek` + `week_in_quad`
- **Basket** column always shown

### Column toggles (all on by default)

- Metric groups: Stock, Margin, MtoSt, Sold, Price
- Week offsets: **1 W**, **4 W**, **5 W** (hide level columns at those offsets; deltas stay when group is on)

### Filters

Compact **2-row editable table** (min / max):

`dSt_QW | Stock | dM_QW | Margin | dMtoSt | MtoSt | dSold | Sold | dPrice | Price`

- Filters apply to **current-week** level values only (not W−1/W−4/W−5 columns)
- Delta filter inputs are **percent** (e.g. `-10.50` → −10.50%); converted to ratio internally

### Display formats

| Kind | Columns | Format |
|---|---|---|
| Delta | `d…` | Percent, 2 decimals (`10.50%`) |
| Integer | Stock, Sold | 0 decimals |
| Currency | Margin, Price | `$1,234.57` |
| Ratio | MtoSt | 3 decimals |

### Column colours

Grouped backgrounds (light level / dark delta): pink Stock, purple Margin, cyan MtoSt, blue Sold, green Price — via `week_discount_column_background()` + pandas Styler.

---

## Weekly Detail table

`compute_basket_week_detail_rows()` — one row per basket in selected week:

Basket, QW, Week, week in QW, W. Price, Total Stock, Total CountProduct, Total Purchase, Total Sold, Total Revenue, Total Margin, Cost, Total Monthly Reserve

(No Corr columns.)

---

## Files changed (sessions since `handoff_260618`)

| File | Changes |
|---|---|
| `core/statistics/metrics.py` | **New** — `monthly_reserve()`, `monthly_reserve_series()` |
| `core/analytics/basket_analysis.py` | `total_monthly_reserve` in `compute_sumup_series()` |
| `core/analytics/week_basket_tables.py` | **New** — Week Discount + Weekly Detail row builders, column meta, visibility, filters, formatting, colours |
| `pages/01_Correlation_Analysis.py` | Monthly Reserve; Sum-Up layout; Weekly Detail / Week Discount / Week Visualization; Week Discount toggles/filters/formats (~2360 lines) |
| `visualizations/sumup_charts.py` | NaN-safe y-axis in `build_metric_progress()` |
| `tests/test_e2e.py` | monthly_reserve, week_basket_tables, format/filter parse tests |
| `handoff_260618.md` | Prior Basket Detail handoff (still valid) |
| `handoff_260617.md` | Full MVP handoff (still valid) |

**Unchanged since 260618 but relevant:** `visualizations/detail_charts.py`, `visualizations/sumup_charts.py` (QW color/average).

---

## Session state (key additions)

```python
"show_qw_average":  False,   # Basket Detail
"selected_week":    None,    # Sum-Up Show → week drill-down
# Week Discount filter/table keys are per-week: wd_col_*, wd_filter_table_{week}
```

---

## Tests run

```powershell
python -m py_compile core/analytics/week_basket_tables.py core/statistics/metrics.py pages/01_Correlation_Analysis.py
python tests/test_e2e.py
```

**Last result:** `ALL TESTS PASSED`

**E2E now also covers:**

- `monthly_reserve` formula
- `compute_basket_week_detail_rows` row count
- `compute_basket_week_discount_rows` columns + visibility toggles
- `format_week_discount_value` / `parse_week_discount_filter_value`
- `apply_week_discount_filters`

**Not covered:**

- Streamlit UI interactions (toggles, filter table, expanders)
- Week Discount colours/formats in browser
- Edge weeks where W−1/W−4/W−5 missing → duplicate `Stock[?,?]` headers possible
- Theme cold-load checklist (`handoff_260617.md`)
- Full browser automation

---

## Remaining TODOs / known gaps

1. **Phase 2 architecture** — DuckDB, pipelines, services not started
2. **Extract UI modules** — `pages/01_Correlation_Analysis.py` ~2360 lines; move Basket Detail, Sum-Up, Week Discount blocks to helpers
3. **Sum-Up charts** — no QW Average toggle (Basket Detail only)
4. **Week Discount edge weeks** — early/late weeks missing offsets; duplicate `[?,?]` column keys if multiple offsets invalid
5. **Malformed CSV UX** — technical `ValueError`s
6. **No auth / CI** — local tests only
7. **Theme bootstrap** — upgrade Streamlit ≥1.52 if hydration flaky
8. **Weekly Detail table** — no QW row colouring (Sum-Up has it)
9. **Export** — Week Discount / Weekly Detail tables not exported yet

---

## Risks

| Risk | Detail |
|---|---|
| Large UI file | Single page holds most features; regressions likely without extraction |
| Week Discount column keys | Dynamic headers; duplicate `[?,?]` when offsets missing collapses dict keys |
| Filter percent vs ratio | Delta filters entered as %; must keep parse/display in sync |
| Product-BS complexity | See `handoff_260617.md` — easy to regress parsers |
| Styler + Streamlit | Week Discount uses pandas Styler for colours + formats; version-sensitive |
| QW color / fit highlight | Only Manual Selection passes fit indices — see `handoff_260618.md` |
| `sumup_charts` → `detail_charts` import | `add_qw_average_hlines` cross-import; avoid circular deps if refactoring |

---

## Key reference paths

| Topic | Path |
|---|---|
| Main UI | `pages/01_Correlation_Analysis.py` |
| Week tables analytics | `core/analytics/week_basket_tables.py` |
| Monthly Reserve | `core/statistics/metrics.py` |
| Sum-Up series | `core/analytics/basket_analysis.py` → `compute_sumup_series()` |
| QW chart helpers | `visualizations/detail_charts.py` |
| Week progress charts | `visualizations/sumup_charts.py` |
| Data prep / QW | `core/transforms/data_prep.py` |
| E2E tests | `tests/test_e2e.py` |
| Spec | `PBA. Arch. Spec. Phase 1.txt` |

---

## Manual smoke checklist (new features)

1. Build analysis → Sum-Up → check **Total Monthly Reserve** column + export
2. Select basket → Week Progress → toggle **Monthly Reserve**
3. Sum-Up **Show** one week → verify three expanders appear
4. **Weekly Detail** — per-basket rows match aggregate for that week
5. **Week Discount** — toggle Stock/1W/4W; column colours; formats (`%`, `$`, integers)
6. **Filters** — enter min/max on `dSt_QW` (percent) and Stock (integer); row count updates
7. **Week Visualization** — charts still work inside renamed expander
8. **Sum-Up Total** parent expander — Stock Progress before 3-panel scatter

---

## Suggested first message for fresh chat

> Continue PBA Streamlit MVP at `PBA.v.1.250525`. Read `handoff_260619.md` (latest), plus `handoff_260618.md` (Basket Detail QW) and `handoff_260617.md` (MVP baseline). Recent work: Monthly Reserve metric; Sum-Up Total parent expander; per-week **Weekly Detail**, **Week Discount** (QW deltas, column toggles, compact min/max filter table, formatted display), and **Week Visualization** expanders. Week Discount logic in `core/analytics/week_basket_tables.py`. Last test: `python tests/test_e2e.py` → ALL TESTS PASSED.
