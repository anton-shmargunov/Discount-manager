# PBA v1 — Handoff (2026-06-23)

## Start here

**This is the current handoff for a fresh chat.**

Read in order if you need full context:

1. **`handoff_260623.md`** (this file) — Week Discount edit/export, discount hist export, report-mode hist, GitHub + Streamlit Cloud
2. **`handoff_260622.md`** — strategies v1, MtoSt P3, UI extract, input modes, W.S./W.C. metrics, product-BS scope
3. **`handoff_260620.md`** — discount history, Week Discount strategy P1/P2, New Discount/Prom, dDiscount/dProm
4. **`handoff_260619.md`** — Monthly Reserve, Sum-Up layout, Week Discount tables/filters
5. **`handoff_260617.md`** — MVP baseline (product-BS, theme, architecture)

---

## Goal

Port the HTML/JS analytics prototype into a **Python Streamlit MVP** for Pricing Correlation & Bucket Analysis (`PBA. Arch. Spec. Phase 1.txt`):

- **Analytics must never depend on UI** — `core/` pure logic, `visualizations/` Plotly, `pages/` + `ui/` orchestration
- Functional MVP: product-BS + TrackingBaskets report inputs, clustering, basket drill-down, Sum-Up, Week Discount tables, optional discount history, discount/prom strategy generation, exports
- **Deployed:** https://discount-manager-v1-1.streamlit.app/
- **GitHub:** https://github.com/anton-shmargunov/Discount-manager (`main`, entry `app.py`)

---

## Project root

`d:\Anton\UTires\Code\Pricing\Pricing Correlation and Bucket Analysis\streamlit\PBA.v.1.250525\`

```powershell
streamlit run app.py --server.port 8501
python tests/test_e2e.py
```

Git: branch **`main`**, remote **`origin`** → `anton-shmargunov/Discount-manager`. Initial commit `f42ab8c` (68 files). Push after changes: `git add . && git commit -m "..." && git push` → Streamlit Cloud auto-redeploys (~1 min).

Streamlit Cloud: **Python 3.12** (not 3.14), **Secrets empty**, main file **`app.py`**.

---

## Architecture (current)

```
core/
  analytics/       basket_analysis, week_basket_tables, discount_strategy, prom_strategy
  transforms/      data_prep (+ discount_hist export/merge, advance week metadata)
ui/
  week_discount_ui.py    Week Discount section (edit, export, strategy UI)
  product_bs_scope.py    Per input-mode / product-BS category session isolation
pages/
  01_Correlation_Analysis.py   Main page (~2200 lines)
configs/strategies/strategies.v1.csv
inputs/              Sample CSVs + full basket list (625)
tests/test_e2e.py
```

---

## Major decisions (this session)

### Week Discount — manual edit

- **Edit / Apply / Cancel** for **New Discount** and **New Prom** only
- Default view: styled read-only `st.dataframe`; edit mode: `st.data_editor`
- Manual overrides stored per scope/week: `wd_manual_overrides_{week}` (scoped via `product_bs_scope`)
- Pipeline: `build_working_week_discount_rows()` → generated discount → generated prom → manual overrides → **`enrich_week_discount_delta_columns()`**
- **Edit mode:** do **not** pre-set `st.session_state[editor_key]` (Streamlit blocks widget key assignment)
- **Edit mode:** no preview-cache feedback into editor (caused revert/scroll jump); **dDiscount/dProm refresh on Apply** only
- Editor key cleared on Edit / Apply / Cancel: `wd_manual_editor_{week}`

### dDiscount / dProm calculation

- **`week_discount_historical_current_column()`** — `Prom[current]` / `Discount[current]` must be historical columns (`Prom[…]`, `Discount[…]`), **not** New Prom / New Discount
- **`_safe_delta(new, current)`** — **both** missing sides treated as **0**:
  - Example: `Prom[current]=0.02`, `New Prom=None` → `dProm = -0.02`
  - Example: `New Prom=0.02`, no current → `dProm = +0.02`

### Prom strategy (separate from discount)

- **`core/analytics/prom_strategy.py`** — mode **"Set previous prom"** only; **Generate Prom** button separate from Generate Discount
- Order: generated discount → generated prom → manual overrides → enrich deltas

### Product BS Category isolation

- **`ui/product_bs_scope.py`** — scope key `pbs::{input_mode}::{category}` or `mode::TrackingBaskets_v2 report`
- Per-scope: analysis, selections, Week Discount generated/manual state, **`discount_hist_df`** (uploaded CSV copy at Build)
- Build clears derived state via `clear_product_bs_scope_derived()`

### TrackingBaskets_v2 report + discount history

- Report mode now has **discount history uploader** (same CSV format as product-BS)
- Always uses **`Aggregated`** category → columns **`discount`**, **`prom with stock`** (no In/Out split)
- Same as product-BS mode with **Product BS Category = Aggregated**

### Week Discount exports

| Control | Behavior |
|--------|----------|
| **Export Week Discount** (renamed from Export CSV) | Visible columns; optional **Include 'no stock'** (625 canonical baskets) |
| **Export Discount history** | Input-format CSV for **selected week + 1** with New Discount/New Prom in category columns |
| **all history** (default **on**) | Merges full uploaded discount hist + new week rows (overrides same basket-week) |
| **all history** off | Only new week rows |

Week +1 rules (`advance_discount_hist_week_metadata`):

- `week from y_w`: +1 (52 → 1, year +1)
- `year_week`: same separator as source (`2026-25` → `2026-26`)
- `week in quad`: 1→2→3→4→1
- `quadweek`: +1 only when new week in quad = 1

Button layout: export row columns `[1, 1, 3]` — **Export Week Discount** width matches **Edit** / **Generate Discount**.

### Git + deployment

- `.gitignore` added (Python cache, venv, secrets, `.cursor/`)
- Repo includes `inputs/` sample data (~5 MB) — works on Streamlit Cloud without extra secrets

### Strategies defaults (from prior session, still valid)

- `DISCOUNT_SETTINGS_UI_VERSION = 5`
- MtoSt toggle default ON, balance 2%, margin mode **Margin categories**
- Discount/Prom column toggles default ON in Week Discount

---

## Key files changed (this session)

| File | Changes |
|------|---------|
| `ui/week_discount_ui.py` | Edit/Apply, exports, prom UI, scoped keys, button layout |
| `ui/product_bs_scope.py` | Scope isolation, `TRACKING_REPORT_MODE`, `AGGREGATED_DISCOUNT_HIST_CATEGORY`, `discount_hist_df` |
| `core/transforms/data_prep.py` | `week_discount_historical_current_column`, discount hist export/merge, week advance |
| `core/analytics/week_basket_tables.py` | `_safe_delta`, enrich, export normalize/expand |
| `core/analytics/discount_strategy.py` | `build_working_week_discount_rows`, `apply_manual_overrides_to_rows` |
| `core/analytics/prom_strategy.py` | Prom generation (Set previous prom) |
| `pages/01_Correlation_Analysis.py` | Scoped state, report-mode discount hist, pass `discount_hist_df` to Week Discount |
| `tests/test_e2e.py` | dProm delta rules, discount hist export merge, tracking report + hist, scope tests |
| `.gitignore` | New |

---

## Session state keys (Week Discount, scoped)

Prefix: `scoped_widget_key(scope_key, ...)` e.g. `pbs::TrackingBaskets_v2 - product_BS. on date of sale::Aggregated::wd_...`

- `wd_generated_discount_{week}`, `wd_generated_prom_{week}`
- `wd_manual_overrides_{week}`, `wd_manual_edit_{week}`, `wd_manual_revision_{week}`
- `wd_manual_editor_{week}` (data_editor widget — do not assign manually)

---

## Tests

Last run: **`python tests/test_e2e.py` → ALL TESTS PASSED**

Covers: legacy 4-CSV pipeline, K-Means/Octants, product-BS modes, discount hist parse/apply, Week Discount columns, manual override + dProm rules, prom strategy, full basket export (625), discount hist export merge, product-BS scope isolation, tracking report + aggregated discount hist.

**Not covered:** Streamlit UI smoke, visual edit-mode behavior, Streamlit Cloud runtime, scoped category switching in browser.

---

## Remaining TODOs

1. **Prom strategies** beyond "Set previous prom" (CSV sections reserved in `strategies.v1.csv`)
2. **Strategy persistence** across browser sessions (currently session-only generated/manual state)
3. **Phase 2 architecture** — DuckDB/pipelines (duckdb in requirements, not wired in MVP UI)
4. **Extract more UI** from main page (Sum-Up, Basket Detail still inline)
5. **Manual edit UX** — optional live dProm preview in editor without breaking Streamlit widget state
6. **Large production data** — consider excluding heavy CSVs from git / using Git LFS or cloud storage
7. **Priority 1 naming vs logic** — UI says missing discount at current week; confirm W−1 intent with user if needed (see `handoff_260620.md`)

---

## Risks / gotchas

| Risk | Detail |
|------|--------|
| **Edit mode + Streamlit** | Never set `session_state[widget_key]` before `st.data_editor`; no preview dataframe fed back into editor |
| **dProm in edit mode** | Stale until Apply — caption explains this |
| **discount hist export without upload** | `all history` on but no file at Build → export is new week only |
| **Report vs product-BS scope** | Switching input mode uses different scope keys — rebuild after switch |
| **Export normalize** | In-stock baskets get New Discount/Prom **0** when unset; no-stock rows stay NaN/empty |
| **Repo size** | `inputs/` xlsx/csv in git; cloud clone includes all |
| **Python on Cloud** | Use 3.12; 3.14 may break scipy/sklearn install |
| **Single commit on GitHub** | All history in one commit; no incremental PR trail yet |

---

## Quick verification checklist (fresh chat)

1. Local: `streamlit run app.py` → product-BS on date of sale → upload report + discount_hist → **Build**
2. Week Discount → Generate Discount / Generate Prom → **Edit** → change New Prom → **Apply** → check **dProm**
3. **Export Week Discount** + **Export Discount history** (`all history` on/off)
4. Switch to **TrackingBaskets_v2 report** → same discount hist columns (`discount`, `prom with stock`)
5. `python tests/test_e2e.py`
6. Cloud: https://discount-manager-v1-1.streamlit.app/ after `git push`

---

## Copy-paste prompt for fresh chat

> Continue PBA Streamlit MVP at `PBA.v.1.250525`. Read **`handoff_260623.md`** first. Deployed: https://discount-manager-v1-1.streamlit.app/ · GitHub: `anton-shmargunov/Discount-manager` (`main`, `app.py`). Recent work: Week Discount manual Edit/Apply, dProm/dDiscount with missing=0, discount hist export (+1 week, all history merge), TrackingBaskets report mode with Aggregated discount hist, product-BS scope isolation. Run: `streamlit run app.py`, `python tests/test_e2e.py` → ALL TESTS PASSED.
