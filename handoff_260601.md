We're running out of context in the current chat.
Create a handoff summary for the fresh chat: goal, decisions, files changed, remaining TODOs, tests run, and risks.


260601
Here is the full handoff summary. You can paste this as the opening message of your new chat.

---

## PBA v1 — Handoff Summary

### Goal

Port an existing HTML/JS analytics prototype (`index.html`, ~1 880 lines) to a Python Streamlit MVP, following a strict architecture spec (`PBA. Arch. Spec. Phase 1.txt`): **analytics must never depend on UI**. The app is a Pricing Correlation & Bucket Analysis tool for tyre SKUs.

---

### Architecture Rule (non-negotiable)

```
core/        — pure Python analytics, zero Streamlit imports
visualizations/  — pure Plotly builders, zero Streamlit imports
pages/       — Streamlit UI only; calls core/ and visualizations/
```

---

### Project Root

```
d:\Anton\UTires\Code\Pricing\Pricing Correlation and Bucket Analysis\streamlit\PBA.v.1.250525\
```

Run the app:
```powershell
streamlit run app.py
```

Run the smoke test:
```powershell
python tests/test_e2e.py   # exits 0, prints "ALL TESTS PASSED"
```

Input CSV files live in `inputs/` (two files: price/sold data and stock data).

---

### Files Created / Changed

| File | Lines | Notes |
|---|---|---|
| `app.py` | ~30 | Thin entry point, welcome screen |
| `requirements.txt` | 8 | streamlit, pandas, numpy, plotly, scipy, sklearn, duckdb, pyarrow |
| `.streamlit/config.toml` | ~10 | Forces `base = "light"` theme on first load |
| `.vscode/settings.json` | ~5 | Points Pylance at correct Python interpreter |
| `configs/settings.py` | ~50 | `CLUSTER_COLORS`, `CLUSTER_BORDER_COLORS`, filter defaults |
| `core/models.py` | ~80 | Dataclasses: `BasketTimeSeries`, `BasketResult`, `Planefit`, `Linefit`, `WeeklyTotal`, `MarginModelResult` |
| `core/statistics/correlations.py` | ~100 | Pearson, rolling, weekly aggregate |
| `core/transforms/data_prep.py` | ~200 | CSV → `BasketTimeSeries`; stock trend metrics |
| `core/clustering/kmeans.py` | ~60 | `run_kmeans`, `compute_cluster_summary` |
| `core/clustering/octants.py` | ~60 | `assign_octants`, `compute_octant_summary` |
| `core/modeling/regression.py` | ~150 | MLR, SLR, PCA plane; R², adj-R², RMSE, MAPE |
| `core/optimization/price_optimization.py` | ~120 | Margin model, `Price_max(S)`, surface builder |
| `core/analytics/basket_analysis.py` | ~120 | Orchestrator: `run_basket_analysis`, `apply_kmeans`, `apply_octants`, `compute_sumup_series`, `AnalysisResult` |
| `visualizations/cluster_charts.py` | ~120 | `build_2d_cluster_scatter`, `build_3d_cluster_scatter` |
| `visualizations/detail_charts.py` | 357 | All basket drill-down charts (see below) |
| `visualizations/sumup_charts.py` | 481 | All aggregate / sum-up charts (see below) |
| `pages/01_Correlation_Analysis.py` | 997 | Main Streamlit page (see below) |
| `tests/test_e2e.py` | ~100 | Smoke test using real `inputs/` files |

---

### Key Decisions & Bug Fixes Applied

1. **"Build Project" double-click** — added `st.rerun()` after successful build so K-Means / Octants buttons enable on the first click.
2. **"Group" column colouring** — `CLUSTER_COLORS` palette applied to the "Group" column of the Detailed Basket Breakdown table via a Pandas Styler.
3. **`YYYY-WW` x-axis** — Plotly was parsing week strings as dates; fixed by forcing `type="category"` + explicit `categoryarray` in both `build_basket_scatter_4panel` (detail) and `build_stock_progress` (sum-up).
4. **Stock y-axis rescaling** — `Total Stock vs Week` y-axis is scaled to the data range, not from zero.
5. **Fitting point selection** — "Cost vs Price" and "3D Price×Stock×Sold" expanders both have a "Points to fit" dropdown (All Quadweeks / specific QW / Manual Selection) plus a `_manual_fit_indices` data editor with a "Select All" toggle. Functions `build_cost_vs_price` and `build_3d_price_stock_sold` accept `fitted_indices` parameter.
6. **Margin model 3D surface** — `build_3d_price_stock_m` accepts `margin_surface` parameter; result stored in `st.session_state` so the surface persists after "Run Margin Model".
7. **Evaluation Week label** — dropdown shows `"week (QW)"` format (e.g. `"2026-18 (QW3)"`) instead of `"week (idx)"`.
8. **Dark background on first load** — resolved by `.streamlit/config.toml` with `base = "light"`.
9. **`titlefont` Plotly error** — corrected to `title=dict(text=..., font=dict(color=...))` in `build_combined_progress`.
10. **Stock Progress representations** — three modes via radio button: "Separate plots", "Combined multi-Y-axis plot", "Vertical Stack" (`build_vertical_stack_progress` — 4 stacked subplots with shared categorical x-axis and cross-hair spike lines).

---

### Test Status

```
python tests/test_e2e.py
→ ALL TESTS PASSED  (exit code 0)
```

Covers: basket analysis (198 baskets, 9 weeks), K-Means (k=3), Octants, sum-up series, plane/line fitting for basket `1111`, stock trend metrics.

---

### Remaining TODOs / Known Gaps

Nothing was explicitly left incomplete, but these areas were **not yet done** and may be the natural next step:

1. **Phase 2 migration path** (as described in the spec) — replace Pandas CSV loading with DuckDB queries; introduce `pipelines/` and `services/` layers (empty `__init__.py` stubs exist).
2. **`pages/02_*`** — The spec mentioned additional pages (e.g. a standalone Margin Optimisation page); only `01_Correlation_Analysis.py` exists.
3. **"Vertical Stack" hover** — `hovermode="x"` works but `hovermode="x unified"` was commented out because it produced noisy labels; worth revisiting once Plotly shared-axis hover behaviour is confirmed.
4. **Basket detail: 3D `Price × Sold × M`** — the weekly-detail section renders this plot; verify it behaves correctly when `use_qw_colors` is toggled.
5. **No auth / multi-user isolation** — session state is per-browser tab; fine for local/demo use, needs redesign for SaaS.
6. **No error handling for malformed CSVs** — `normalize_csv_df` in `data_prep.py` will raise if required columns are missing; user-facing error messages would improve UX.

---

### Key Reference Files

- Spec: `PBA. Arch. Spec. Phase 1.txt` (in project root)
- Original prototype: `d:\Anton\UTires\Code\Pricing\Pricing Correlation and Bucket Analysis\local\PCBA v2.260818.2.0523.2\index.html`
- Past chat transcript: [PBA Streamlit MVP build](51fe92c7-f25e-4289-9fba-cf4e75be2a86)