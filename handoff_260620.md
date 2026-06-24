# PBA v1 — Handoff (2026-06-20)

## Start here

**This is the current handoff for a fresh chat.**

Read in order if you need full context:

1. **`handoff_260620.md`** (this file) — discount history, Week Discount strategy, New Discount/Prom, dDiscount/dProm
2. **`handoff_260619.md`** — Monthly Reserve, Sum-Up layout, Week Discount tables/filters
3. **`handoff_260618.md`** — Basket Detail QW toggles, QW averages
4. **`handoff_260617.md`** — MVP baseline (input modes, product-BS, theme, architecture)

---

## Goal

Port the HTML/JS analytics prototype into a **Python Streamlit MVP** for Pricing Correlation & Bucket Analysis per `PBA. Arch. Spec. Phase 1.txt`:

- **Analytics must never depend on UI**
- `core/` = pure analytics
- `visualizations/` = pure Plotly
- `pages/` = Streamlit orchestration only

The app is a functional MVP: 4 input modes, clustering, basket drill-down, Sum-Up analytics, per-week basket tables, discount history + strategy generation, exports, product-BS handling.

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
visualizations/    Plotly chart builders
pages/             Streamlit UI only (~2750 lines main page)
configs/           theme_bootstrap, settings
tests/             smoke/e2e tests
inputs/            sample CSVs including discount_hist + Discount settings
```

---

## Major decisions (cumulative + this session)

### MVP baseline (`handoff_260617.md`)

- 4 input modes including product-BS on-date and monthly av.
- Product-BS parsing rules for stock vs sold/revenue differ by mode
- Theme bootstrap via `configs/theme_bootstrap.py`
- **Avg Sale Price Range min default = `0`** (was `0.001`; `configs/settings.py` → `DEFAULT_MIN_PRICE`)

### Basket Detail (`handoff_260618.md`)

- Toggles: Line + Symbol, Colour by Quadweek, QW Average
- Week Progress metrics include **Discount** and **Prom** (off by default) when discount history uploaded

### Sum-Up / Week drill-down (`handoff_260619.md`)

- Monthly Reserve metric; Sum-Up Total parent expander
- Per-week expanders: Weekly Detail, Week Discount, Week Visualization
- Week Discount: metric groups, week-offset toggles, compact min/max filter table, column colours/formats, CSV export

### Discount history input (2026-06-20)

- **Optional** CSV upload after product_BS report uploader (product_BS modes only)
- Example: `inputs/discount_hist_EXAMPLE_SHORT.csv`
- Columns selected by **Product BS Category** (Aggregated / In / Out / …)
- **discount**: signed decimal (negative = price reduction)
- **prom**: `n/a` → 0; valid steps 0, 0.02, 0.04, 0.06…; rejects negatives and odd-cent values (0.01, 0.03)
- Merged into `BasketTimeSeries.discount` / `.prom` per week via `apply_discount_hist_to_basket_data()`

### Week Discount table — discount/prom columns (2026-06-20)

| Column | Meaning |
|---|---|
| **New Discount** | Generated or initial current-week discount |
| **dDiscount** | `New Discount − Discount[current]` |
| **Discount[{qw},{wiq}]** | Levels at W, W−1, W−4, W−5 |
| **New Prom** | Current-week prom |
| **dProm** | `New Prom − Prom[current]` |
| **Prom[{qw},{wiq}]** | Levels at same offsets |

- Removed: `dDisc_QW`, `dProm_QW` (replaced by New + d columns)
- **Highlight colours**: New Discount `#fecdd3`, New Prom `#c7d2fe`, dDiscount `#fda4af`, dProm `#a5b4fc`
- Edge weeks: dynamic headers use `|W-offset` suffix when metadata missing (e.g. `Stock[?,?|W-4]`)

### Discount strategy expander (2026-06-20)

Location: Week Discount section, after **Filters**

**Mode dropdown:**

1. **Based on Strategies** — formula below
2. **Set previous discount** — `New Discount = Discount[current]`
3. **Zero all Discounts** — `New Discount = 0`

**Formula (strategy mode):**

`Discount[new] = Discount[current] + (dDiscount(strategy) + Balance) × Multiplicator`

**Strategy tables** (Conservative / Moderate / Strong): editable `dSt_QW` bins → `dDiscount`, loaded from `inputs/Discount settings.csv`

**Priority 1 — Discount if no Discount [W-1]:**

- Default UI value: `n/a` → **0**
- When discount history has **no row** for basket/week, `Discount[current]` = this default before strategy

**Priority 2 — Sold = 0 strategy:**

- Only baskets with `Sold[current] = 0`
- Strategy dropdown + Balance (default −1%)

**Margin break-down:**

- Single default strategy OR margin categories table
- **Default categories (4 bins):**
  - min → 0: Conservative
  - 0 → 100: Conservative
  - 100 → 1000: Moderate
  - 1000 → max: Moderate

**Zero dSt rules:** optional flags force `dDiscount = 0` when `dSt_QW < 0` or `> 0`

**Generate Discount** button → writes `New Discount` per basket (session state per week); **dDiscount** recomputed automatically

**Sum-up row** (below table, on filtered rows):

- max/min dDiscount, max/min Prom (New Prom)
- W. Discount / W. Prom — stock-weighted averages (`Stock[current]` weights)
- count (Prom) — baskets with New Prom > 0

---

## Files changed (sessions since `handoff_260619`)

| File | Changes |
|---|---|
| `core/models.py` | `discount`, `prom` on `BasketTimeSeries` |
| `core/transforms/data_prep.py` | `parse_discount_hist_lookup()`, prom validation |
| `core/analytics/basket_analysis.py` | `init_discount_prom_on_basket_data()`, `apply_discount_hist_to_basket_data()` |
| `core/analytics/week_basket_tables.py` | New/Prom columns, dDiscount/dProm, enrich + summary, Monthly Reserve group, edge-week headers |
| `core/analytics/discount_strategy.py` | **New** — strategy settings, CSV load, generation, margin categories |
| `core/statistics/metrics.py` | `monthly_reserve()` (from 260619) |
| `pages/01_Correlation_Analysis.py` | Discount hist upload, Basket Detail Discount/Prom charts, Week Discount strategy UI, sum-up metrics (~2750 lines) |
| `configs/settings.py` | `DEFAULT_MIN_PRICE = 0.0` |
| `tests/test_e2e.py` | discount_hist, discount_strategy, dDiscount/dProm, margin categories |
| `inputs/discount_hist_EXAMPLE_SHORT.csv` | Example discount history |
| `inputs/Discount settings.csv` | Strategy defaults reference |
| `handoff_260620.md` | This handoff |

**Unchanged but relevant:** `visualizations/detail_charts.py`, `visualizations/sumup_charts.py`, `configs/theme_bootstrap.py`

---

## Session state (key additions)

```python
"show_qw_average":  False,
"selected_week":    None,
# Week Discount per week:
#   wd_col_*, wd_filter_table_{week}
#   wd_generated_discount_{week}  — {basket: new_discount} after Generate
```

---

## Tests run

```powershell
python -m py_compile core/analytics/discount_strategy.py core/analytics/week_basket_tables.py pages/01_Correlation_Analysis.py
python tests/test_e2e.py
```

**Last result:** `ALL TESTS PASSED`

**E2E covers:**

- Legacy 4-CSV + K-Means/Octants + TrackingBaskets_v2 + product-BS modes
- `monthly_reserve`, `week_basket_tables` (columns, filters, formats)
- `parse_discount_hist_lookup`, `apply_discount_hist_to_basket_data`
- `discount_strategy` (margin categories, bin lookup, zero/set-previous modes)
- `enrich_week_discount_delta_columns` (dDiscount/dProm)
- Edge-week unique column keys

**Not covered:**

- Streamlit UI (strategy expanders, Generate button, sum-up metrics display)
- Visual column highlighting in browser
- End-to-end with real discount_hist + product_BS build in browser
- Theme cold-load checklist
- Prom generation strategy (only Discount is generated today)

---

## Remaining TODOs / known gaps

1. **Phase 2 architecture** — DuckDB, pipelines, services not started
2. **Extract UI modules** — `pages/01_Correlation_Analysis.py` ~2750 lines; move Week Discount / strategy blocks to helpers
3. **Generate Prom** — strategy generates Discount only; New Prom comes from discount hist, no prom strategy yet
4. **Priority 1 naming vs logic** — UI label says `[W-1]` but logic applies when **current week** missing from discount hist (confirm with user if W−1 offset intended)
5. **Discount strategy persistence** — settings reset per session; no save/load of edited strategy tables
6. **Malformed CSV UX** — technical `ValueError`s
7. **Sum-Up charts** — no QW Average toggle (Basket Detail only)
8. **Weekly Detail** — no QW row colouring parity issues if toggled off in Sum-Up
9. **No auth / CI** — local tests only
10. **Theme bootstrap** — upgrade Streamlit ≥1.52 if hydration flaky

---

## Risks

| Risk | Detail |
|---|---|
| Large UI file | Single page holds most features; regressions likely without extraction |
| Discount hist + product_BS category mismatch | Wrong category → wrong discount/prom columns silently empty |
| Strategy vs hist priority | Priority 1 fills missing hist; Priority 2 overrides Sold=0; order must stay documented |
| Filter percent vs ratio | Delta filters entered as %; parse/display must stay in sync |
| Generated discounts in session only | `wd_generated_discount_{week}` lost on full session reset; not written back to basket time series |
| Styler + Streamlit | Week Discount uses pandas Styler; version-sensitive |
| DEFAULT_MIN_PRICE = 0 | Blank/zero price rows now included by default; may change basket counts vs older runs |
| Margin category CSV parse | `Discount settings.csv` layout is positional; file format changes break loader |

---

## Key reference paths

| Topic | Path |
|---|---|
| Main UI | `pages/01_Correlation_Analysis.py` |
| Week Discount tables | `core/analytics/week_basket_tables.py` |
| Discount strategy | `core/analytics/discount_strategy.py` |
| Discount hist parser | `core/transforms/data_prep.py` → `parse_discount_hist_lookup` |
| Strategy defaults CSV | `inputs/Discount settings.csv` |
| Discount hist example | `inputs/discount_hist_EXAMPLE_SHORT.csv` |
| Monthly Reserve | `core/statistics/metrics.py` |
| E2E tests | `tests/test_e2e.py` |
| Spec | `PBA. Arch. Spec. Phase 1.txt` |

---

## Manual smoke checklist (latest features)

1. product_BS mode → upload main report + `discount_hist_EXAMPLE_SHORT.csv` → Build
2. Select basket → Week Progress → toggle **Discount** / **Prom**
3. Sum-Up **Show** week → **Week Discount** → enable Discount/Prom toggles
4. **Discount strategy** → edit Moderate bins → **Generate Discount** → **New Discount** / **dDiscount** update
5. Verify sum-up metrics (max/min dDiscount, W. Discount, count Prom)
6. Export CSV includes New Discount, dDiscount when columns visible
7. Preprocessing **Avg Sale Price min** defaults to `0`
8. Margin categories table shows 4 default bins when using Margin break-down mode

---

## Suggested first message for fresh chat

> Continue PBA Streamlit MVP at `PBA.v.1.250525`. Read `handoff_260620.md` (latest). Recent work: optional discount history upload (discount + prom by product BS); Week Discount with New Discount/Prom, dDiscount/dProm, highlighted columns, sum-up metrics; **Discount strategy** expander with Conservative/Moderate/Strong bins, Generate Discount button, margin categories; Priority 1 = default when discount hist missing; Avg Sale Price min default = 0. Analytics in `core/analytics/discount_strategy.py` + `week_basket_tables.py`. Last test: `python tests/test_e2e.py` → ALL TESTS PASSED.
