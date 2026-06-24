# PBA v1 — Handoff (2026-06-22)

## Start here

**This is the current handoff for a fresh chat.**

Read in order if you need full context:

1. **`handoff_260622.md`** (this file) — strategies v1, MtoSt P3, Week Discount UI extract, input modes, W.S./W.C. metrics
2. **`handoff_260620.md`** — discount history, Week Discount strategy P1/P2, New Discount/Prom, dDiscount/dProm
3. **`handoff_260619.md`** — Monthly Reserve, Sum-Up layout, Week Discount tables/filters
4. **`handoff_260618.md`** — Basket Detail QW toggles, QW averages
5. **`handoff_260617.md`** — MVP baseline (product-BS, theme, architecture)

---

## Goal

Port the HTML/JS analytics prototype into a **Python Streamlit MVP** for Pricing Correlation & Bucket Analysis per `PBA. Arch. Spec. Phase 1.txt`:

- **Analytics must never depend on UI**
- `core/` = pure analytics
- `visualizations/` = pure Plotly
- `pages/` + `ui/` = Streamlit orchestration only

Functional MVP: product-BS input (3 modes), clustering, basket drill-down, Sum-Up analytics, per-week basket tables, optional discount history, **discount strategy generation** (P1–P3 + margin break-down), exports.

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
core/
  analytics/       basket_analysis, week_basket_tables, discount_strategy
  statistics/      correlations, metrics (monthly_reserve)
  transforms/      data_prep (product-BS + discount_hist parsers)
ui/                Streamlit UI helpers (Week Discount section)
visualizations/    Plotly chart builders
pages/             Streamlit main page (~2170 lines)
configs/
  settings.py      STRATEGIES_V1_PATH, DEFAULT_STRATEGIES_PATH
  strategies/      strategies.v1.csv (sectioned discount + prom placeholder)
tests/             smoke/e2e tests
inputs/            sample CSVs; legacy Discount settings.csv still loadable
```

---

## Major decisions (this session + cumulative)

### MVP baseline (see `handoff_260617.md`)

- Product-BS parsing, theme bootstrap, Sum-Up exports, QW coloring
- `DEFAULT_MIN_PRICE = 0`

### Discount history + Week Discount (see `handoff_260620.md`)

- Optional `discount_hist` upload (product-BS modes)
- Week Discount: New Discount/Prom, dDiscount/dProm, filters, strategy expander, Generate Discount
- **Priority 1:** when `Discount[current]` is **missing (NaN)** → use default (`n/a` = 0)
- **Priority 2:** `Sold[current] = 0` → sold-zero strategy (+ multiplicator)

### UI extraction (2026-06-22)

- **`ui/week_discount_ui.py`** (~665 lines): Week Discount toggles, filters, strategy UI, table, sum-up metrics
- **`pages/01_Correlation_Analysis.py`** reduced ~2750 → **~2170 lines**; calls `render_week_discount_section()`

### Input Data (2026-06-22)

- **Removed** UI mode `Separate metric CSVs` (core `run_basket_analysis` remains for e2e)
- **3 modes**, vertical radio:
  1. TrackingBaskets_v2 report
  2. **TrackingBaskets_v2 - product_BS. on date of sale** *(default)*
  3. TrackingBaskets_v2 - product_BS. monthly av.
- Discount history uploader on product-BS modes only

### Strategies config v1 (2026-06-22)

- **Canonical file:** `configs/strategies/strategies.v1.csv` (sectioned single file)
- **`prom.*` sections reserved** for future Prom strategy
- Loader: `load_strategies_v1()` + `StrategiesFormatError` (clear row/section errors)
- `load_discount_strategy_settings()` auto-detects v1 vs legacy `inputs/Discount settings.csv`
- **`configs/settings.py`:** `STRATEGIES_V1_PATH`, `DEFAULT_STRATEGIES_PATH`
- UI loads v1 via `@st.cache_data` (version + CSV mtime); widget keys versioned (`DISCOUNT_SETTINGS_UI_VERSION = 4`)

### Margin categories fix (2026-06-22)

- Legacy workbook parser: margin data starts **row 6** (row 5 is header); fixes shifted strategies in UI

### Discount strategy — Priority 3 MtoSt (2026-06-22)

**Toggle:** MtoSt strategy on/off  
**Balance default:** +1% (`mtost_balance`)  
**Formula (no multiplicator):**  
`Discount[new] = Discount[current] + (dDiscount(dMtoSt_QW) + Balance)`

**Default dMtoSt_QW bins:**

| dMtoSt_QW | dDiscount |
|---|---|
| 0% → 20% | −2% |
| 20% → 50% | 0% |
| 50% → max | +2% |

**Priority order (Generate Discount):**

1. P1 — missing `Discount[current]`
2. P2 — `Sold = 0`
3. **P3 — MtoSt** (if enabled): `dSt_QW > 0`, `Margin[current] ≥ 0`, `Margin[W−1] ≥ 0`
4. Default — margin break-down (Conservative/Moderate/Strong + multiplicator)

### Week Discount table & sum-up (2026-06-22)

- **Discount / Prom toggles:** default **ON**
- **Count Product** columns (offsets 0, W−1, W−4, W−5); toggle **off** by default; after Monthly Reserve
- Sum-up row: **max/min (dDiscount)**, **max/min (dProm)** (from dProm column, not New Prom)
- **Comparison block** (filtered rows, bordered table):

| Period | Discount col | Prom col | Weights |
|---|---|---|---|
| Current − 1W | Discount/Prom at W−1 | same | Stock / Count Product at **current** |
| Current | Discount/Prom current | same | same |
| New | New Discount / New Prom | same | same |

- Labels: **W.S. Discount** (stock-weighted), **W.C. Prom** (count-product-weighted), **count (Prom)**

### Not implemented (discussed)

- **Editable Week Discount column headers** — not native in `st.dataframe`/`st.data_editor`; would need alias map in session state if desired later

---

## Files changed (sessions since `handoff_260620`)

| File | Changes |
|---|---|
| `ui/week_discount_ui.py` | **New** — Week Discount + discount strategy UI |
| `ui/__init__.py` | **New** |
| `pages/01_Correlation_Analysis.py` | Input modes (3, vertical, default product-BS); removed legacy 4-CSV UI path; delegates Week Discount |
| `core/analytics/discount_strategy.py` | v1 loader, MtoSt P3, margin parse fix, `_limit_label_for_display` |
| `core/analytics/week_basket_tables.py` | Count Product group; W.S./W.C. weighted comparison; dProm sum-up |
| `configs/strategies/strategies.v1.csv` | **New** — sectioned discount + mtost + prom placeholder |
| `configs/settings.py` | `STRATEGIES_V1_PATH`, `PROJECT_ROOT` |
| `tests/test_e2e.py` | v1, MtoSt P3, margin categories, weighted compare, Count Product |
| `handoff_260622.md` | This handoff |

**Unchanged but relevant:** `core/transforms/data_prep.py`, `visualizations/*`, `inputs/Discount settings.csv` (legacy fallback)

---

## Session state (key additions)

```python
# Week Discount per week:
#   wd_col_*, wd_filter_table_{week}
#   wd_generated_discount_{week}  — {basket: new_discount} after Generate
#   wd_strat_*_{week}             — strategy UI widgets
```

---

## Tests run

```powershell
python -m py_compile core/analytics/discount_strategy.py core/analytics/week_basket_tables.py ui/week_discount_ui.py pages/01_Correlation_Analysis.py
python tests/test_e2e.py
```

**Last result:** `ALL TESTS PASSED`

**E2E covers:**

- Legacy 4-CSV pipeline + K-Means/Octants + TrackingBaskets_v2 + product-BS modes
- `week_basket_tables` (columns, filters, Count Product, weighted comparison)
- `parse_discount_hist_lookup`, `apply_discount_hist_to_basket_data`
- `load_strategies_v1`, legacy workbook, margin categories (4 bins)
- MtoSt P3 (`mtost_strategy_applies`, `lookup_mtost_d_discount`)
- P1 missing discount, zero/set-previous modes, dDiscount/dProm enrich

**Not covered:**

- Streamlit UI (toggles, strategy expanders, comparison table display)
- Browser smoke with real product_BS + discount_hist + Generate Discount
- Prom generation strategy
- strategies v1 file upload (loads bundled default only)

---

## Remaining TODOs / known gaps

1. **Phase 2 architecture** — DuckDB, pipelines, services not started
2. **Extract more UI** — Sum-Up Total, Basket Detail blocks still in main page (~2170 lines)
3. **Generate Prom** — discount strategy only; prom from discount hist only
4. **Prom settings** — implement `[prom.*]` sections in `strategies.v1.csv` + loader
5. **Discount strategy persistence** — edited bins/categories reset per session; no save/load
6. **Malformed CSV UX in UI** — v1 raises `StrategiesFormatError`; not surfaced in Streamlit yet
7. **Sum-Up charts** — no QW Average toggle (Basket Detail only)
8. **Column header aliases** — if user wants custom Week Discount header labels
9. **No auth / CI** — local tests only
10. **Legacy `inputs/Discount settings.csv`** — deprecate when v1 is sole source

---

## Risks

| Risk | Detail |
|---|---|
| Large main page | ~2170 lines; regressions without further extraction |
| Strategy cache + widget keys | Bump `DISCOUNT_SETTINGS_UI_VERSION` when defaults/layout change |
| P3 vs default strategy | MtoSt skips when margins negative or `dSt_QW ≤ 0`; order must stay documented |
| W.S. / W.C. weights | Both use **current-week** Stock / Count Product for all three comparison periods |
| v1 + legacy dual loader | File format detection by `[meta]` / `.v1.` in name; wrong file → silent fallback to code defaults |
| Generated discounts in session only | `wd_generated_discount_{week}` not written back to time series |
| Count Product toggle off | W.C. Prom still computed from hidden columns (weights may be 0 → N/A) |

---

## Key reference paths

| Topic | Path |
|---|---|
| Main UI | `pages/01_Correlation_Analysis.py` |
| Week Discount UI | `ui/week_discount_ui.py` |
| Week Discount analytics | `core/analytics/week_basket_tables.py` |
| Discount strategy | `core/analytics/discount_strategy.py` |
| Strategies v1 defaults | `configs/strategies/strategies.v1.csv` |
| Strategy paths | `configs/settings.py` |
| Legacy strategy CSV | `inputs/Discount settings.csv` |
| Discount hist example | `inputs/discount_hist_EXAMPLE_SHORT.csv` |
| E2E tests | `tests/test_e2e.py` |
| Spec | `PBA. Arch. Spec. Phase 1.txt` |

---

## Manual smoke checklist (latest features)

1. Input: default **product_BS on date of sale** → upload report + optional discount_hist → Build
2. Sum-Up **Show** week → **Week Discount** → Discount/Prom columns visible by default
3. Toggle **Count Product** → columns appear after Monthly Reserve
4. **Discount strategy** → enable **MtoSt** → edit bins → **Generate Discount**
5. Verify sum-up: max/min **dProm**; comparison table **W.S. Discount** / **W.C. Prom** for Current−1W / Current / New
6. Margin categories: min→0 Conservative, 100→1000 Moderate (from v1 file)
7. Priority 1: basket with missing discount hist → default applied before strategy

---

## Suggested first message for fresh chat

> Continue PBA Streamlit MVP at `PBA.v.1.250525`. Read `handoff_260622.md` (latest). Recent work: Week Discount UI in `ui/week_discount_ui.py`; strategies v1 at `configs/strategies/strategies.v1.csv`; discount strategy P1/P2/P3 (MtoSt on dMtoSt_QW); input default product-BS on-date (3 modes); W.S. Discount / W.C. Prom comparison block; Count Product columns. Last test: `python tests/test_e2e.py` → ALL TESTS PASSED.
