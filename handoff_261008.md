# PBA v1 — Handoff (2026-10-08)

## Start here

**This is the current handoff for a fresh chat.**

Read in order if you need more context:

1. **`handoff_261008.md`** (this file): Campaign/Job Planner, Cloud project-restore fixes, margin-model table upgrades, Sum-up display toggles.
2. **`handoff_260912.md`**: docs, all-BS discount hist export/upload, Project save/restore.
3. Older: `handoff_260623.md` → `260622` → `260620` → `260619` → `260617`.

**Docs:** `docs/architecture.md`, `docs/user-manual.md` (updated 2026-10-08 for everything below).

---

## Goal

Streamlit port of **Pricing Correlation & Bucket Analysis (PBA)**. Layers are kept strictly separate:
- `core/`: analytics.
- `visualizations/`: Plotly figure builders.
- `pages/` + `ui/`: the only Streamlit code.

- **Local:** `streamlit run app.py --server.port 8501`
- **Tests:** `python tests/test_e2e.py` (pytest is not installed). Compile check: `python -m py_compile <file>`.
- **GitHub:** https://github.com/anton-shmargunov/Discount-manager
- **Branches:** work is on **`v1-1-test_1`**, which tracks `origin/v1-1-test_1`. A Streamlit Cloud test app deploys from this branch.
  - **The user asked to leave `main` alone.** It is at `8ae451c`. Deploy = push `v1-1-test_1`.
- **Local env:** Python 3.9.13, Streamlit 1.49.1, pandas 2.3, numpy 2.0.2.
- **Cloud env:** Python 3.12 with a newer Streamlit.
- **Version:** `configs/settings.py` → `APP_VERSION = "1.0.1.t1"`. The user set this; the app page shows "Version …".

Project root: `d:\Anton\UTires\Code\Pricing\Pricing Correlation and Bucket Analysis\streamlit\PBA.v.1.250525\`

---

## Git state at handoff

Last pushed commit on `v1-1-test_1`: **`276b079` Fix Cloud project restore across Streamlit versions.**

**Uncommitted (not deployed):** the margin-model upgrades and Sum-up toggles (sections C and D), plus TODOs 3–5 (docs, `_btn` key convention, `width="stretch"` migration):

```
 M core/persistence/project_io.py
 M docs/architecture.md
 M docs/user-manual.md
 M pages/01_Correlation_Analysis.py
 M requirements.txt
 M tests/test_e2e.py
 M ui/planner_ui.py
 M ui/product_bs_scope.py
 M ui/project_save_ui.py
 M ui/week_discount_ui.py
?? core/optimization/margin_model_eval.py
?? handoff_261008.md
?? visualizations/sumup_qw_charts.py
```

Only commit or deploy when the user asks. When deploying, push `v1-1-test_1` and do not touch `main`. Pushes or commits may need the user's approval through the approval prompt.

---

## Work completed in this session

### A. Campaign / Job Planner (committed: `0d948fb`, `6496c05`, `fdfd4fd`)

Rules confirmed with the user:
- **Exclusive membership:** a basket belongs to at most one Job, and a Job to one Campaign.
- **IDs:** 10 digits.
- **Storage:** the Planner lives in the scope as `scope["planner"]`, so it is saved in `.disc_proj`.

Week Discount generation:

| Button | What it does |
|---|---|
| **Generate Discount / Generate Prom** | Campaign switch **off**: unassigned baskets, with the on-screen settings. Switch **on**: baskets of the Planner-selected Jobs, with the on-screen settings. The result is merged into the existing generated values. |
| **Generate Discount all / Generate Prom all** | Every Job with its stored settings, plus the stored default (seeded from `configs/strategies/strategies.v1.csv`) for unassigned baskets. The result replaces the existing generated values. |

Editing and assignment:
- The **Planner** (sidebar expander) is the only place where strategy assignment is edited.
- **Apply** (`wd_strategy_save_*`) saves the on-screen settings to the default pool or to the selected Jobs.
- **Group** selection still drives the Basket Detail plots.
- **"Set a Job"** creates a new Job from the current Group in the selected Campaign.
- Assigning a basket that is already in another Job opens a per-basket **conflict approval dialog**: `st.dialog` + `data_editor` with Approve all / Keep all / Confirm / Cancel.

Columns:
- **Campaign** and **Job** columns are shown in the Detailed Basket Breakdown table and in the Week Discount table.
  - In Week Discount they sit **after the Prom columns**. The user does not want the Discount/Prom column formats changed.
- `discount_hist` export has 4 extra columns at the end: `campaign_id`, `campaign_name`, `job_id`, `job_name`.

Files:
- `core/analytics/planner.py`: model, assignment, conflicts, `generate_*_all_jobs`. Legacy planners are migrated via `settings_version` = 2.
- `ui/planner_ui.py`: sidebar panel and conflict dialog.
- Changes in `ui/week_discount_ui.py`, `core/analytics/week_basket_tables.py`, `core/transforms/data_prep.py`, `core/analytics/discount_strategy.py`, `core/analytics/prom_strategy.py`, `pages/01_Correlation_Analysis.py`.

**Selection priority** in Detailed Basket Breakdown: Group → Select All → table rows → **Planner focus**.
- Planner focus is the selected Jobs. If no Job is selected, it is all baskets of the selected Campaign.
- To get a single-basket Basket Detail, the Campaign must be set to "Select…" (`—`).

Earlier in this session: Select All in Multiselect mode; Margin Corrected for multi-basket Basket Detail (`core/analytics/selected_basket_margin.py`); Cloud fix `st.iframe(height=1)` + CSS in `configs/theme_bootstrap.py`.

### B. Project restore (`.disc_proj`) fixes (committed: `491c7d1`, `276b079`, deployed)

All changes are in `core/persistence/project_io.py`.

Root cause: Cloud saves contained Streamlit widget-state objects (`DataEditorState`, `DataframeState`) whose class names differ between Streamlit versions, so the files could not be read.

Fixes:
- **Load:** `_ProjectUnpickler` returns `UnavailableWidgetState` (a dict subclass) for **any** `streamlit.*` class, and maps `numpy.core` ↔ `numpy._core`.
- **Save:** Streamlit widget-state values are skipped.
- **Restore:** Streamlit widget-state values are not written back to the session.
- **Save:** `discount_hist_df` pyarrow string columns are converted to `object`.
- **Button keys:** the new button keys (planner add/delete/update, set_job, `wd_strategy_save`) are added to `_WRITE_DISALLOWED_KEY_FRAGMENTS`. Without this, restore raised `StreamlitValueAssignmentNotAllowedError`.
- **Errors:** the error message now includes the underlying exception.
- Also: the margin-categories editor key in `ui/week_discount_ui.py` is now wrapped in `wk()`, so it is scoped per Product BS.

The user confirmed the restore works on Cloud.

**Q&A:** Restore does **not** need the report or discount-history CSVs. `.disc_proj` stores:
- the built `AnalysisResult` (weekly sold/price/stock/margin/cost, with discount/prom already merged);
- `discount_hist_df`;
- the Planner and UI settings.

Only **Build** reads the uploaders.

### C. Analytical Margin Optimisation Model table (UNCOMMITTED)

Applies to **Basket Detail** and **Sum-up Total**, in the "3D Overview: Price × Stock × M + Margin Optimisation" expander.

1. **Column layout:** Actual Results | **Model Error Metrics** | Model at Price | Optimisation. The result column ratio is now `[1, 3]`.
2. **Model Error Metrics** (Adj R², RMSE, MAPE):
   - They compare the analytical margin `M = (P(1−a_c) − z0_c)·Sold(P,S)` with the actual margin. Predictors p = 2.
   - They are computed over **the same weeks as the Sold plane fit**, which the user chose.
   - The fit weeks are stored at "Fit Plane": `scope["fit_sold_indices"][basket]` and `scope["fit_sumup_stock_sold_indices"]`.
   - If nothing is stored (fit made earlier), the current widget selection is used.
   - Basket Detail uses the plotted margin, which is the hybrid when Margin Corrected is on.
3. **Price_diff** in Basket Detail is now a delta under Price_max (Sum-up style). The separate metric was removed.
4. **Sold metrics:** Sold / Total Sold (actual), Sold (model), Sold gain = Sold(target) − Sold(actual point).
5. **Price (manual) / Stock (manual) inputs** (Sum-up: "W. Price (manual)" / "Total Stock (manual)"):
   - Defaults: Price_max and actual stock of the Evaluation week. They reset when the week or the fit changes.
   - **Applied only on "Run Margin Model"** (user's choice).
   - If only Stock is changed, Price follows Price_max(stock) until the user edits Price. This was the default choice; the user never answered that question.
   - When the inputs differ from the defaults, the label shows "Price (manual)". Price_diff, M gain and Sold gain are then measured against the manual point.
   - Helper: `_render_manual_point_inputs` in the page. The session keys are `mm_price_manual_*`, `mm_stock_manual_*`, `mm_point_state_*`, and `sumup_mm_*` for Sum-up.
6. **Saved model dict:** each saved model now also holds `"target"` and `"metrics"`. Models saved before this change show N/A for the new fields until they are re-run.

New pure module **`core/optimization/margin_model_eval.py`**: `compute_model_sold`, `price_max_or_fallback`, `compute_margin_fit_metrics`, `evaluate_margin_target` (returns a plain `bool` `is_manual`).

UI helpers in `pages/01_Correlation_Analysis.py`: `_finite_or`, `_render_manual_point_inputs`, `_delta_text`, `_render_margin_model_results`.

`ui/product_bs_scope.py`: `clear_product_bs_scope_derived` resets the new `fit_*_indices` keys.

### D. Sum-up Total display options (UNCOMMITTED)

- One row of toggles at the top of the Sum-Up Total expander: **Line + Symbol**, **Colour by Quadweek**, **QW Average**.
  - Keys: `su_tog_line`, `su_tog_qw`, `su_tog_qw_avg`.
  - They apply to **all** Sum-up plots and replace the old `tog_stk` / `tog_su_line` toggles. The defaults are all off; Stock Progress line was previously on.
- New module **`visualizations/sumup_qw_charts.py`**, a new module because of the Cloud stale-module risk: `build_sumup_3panel_qw`, `build_sumup_cost_vs_price_qw`, `build_sumup_3d_qw`, `build_sumup_stock_sold_3d_qw`, `build_sumup_stock_m_3d_qw`, `build_combined_progress_qw`, `build_vertical_stack_from_specs_qw`, `sumup_quadweeks`.
- "Separate plots" uses the existing `build_metric_progress(quadweeks=…, use_qw_colors=…, show_qw_average=…)`.
- Combined multi-Y plot:
  - Quadweek colour fills the markers; the outline keeps the series colour.
  - QW Average draws dashed horizontal lines per quadweek on each series' own axis.
- Vertical Stack:
  - QW Average draws horizontal lines per panel.
  - With QW colour on, markers are shown even when Line is off.
- Fit-highlighted points use quadweek colours on the fitted points and grey on the others (same as Basket Detail).

---

## Tests run

- `python tests/test_e2e.py` → **ALL TESTS PASSED**. New coverage:
  - planner;
  - discount_hist columns;
  - restore of missing or live Streamlit classes;
  - button-key skip;
  - pyarrow → object;
  - margin metrics and manual point.
- **Real-data headless UI test** with Streamlit `AppTest`. The scripts are outside the repo:
  - `%TEMP%\pba_feature_test.py`
  - `%TEMP%\pba_build_test.py`
  - `%TEMP%\pba_probe.py`
- Test files (user-provided):
  - Project: `D:\Anton\UTires\Pricing\Reports\23_1 (26-40_26.09.28-26.10.04)\proj\discount_project_A-used_ALL_40_9.disc_proj`
  - Report: `...\23_1 (...)\hist. used A\TrackingBaskets Export\data - 2026-10-06T194241.487.A-used.26_17-26_40.PRODUCTBS.csv`
  - Discount hist: `...\23_1 (...)\discount_hist_Preveous\discount_hist_2026-40_A-used_ALL.csv`
- What the AppTest run did:
  - restored the project (OutByMinPrice is the active scope);
  - toggled all Sum-up options in all 3 progress views;
  - ran the Sum-up and Basket Detail (basket 1111) margin models with default and manual points.
  - Result: **all checks passed, no exceptions**. Values were checked against independent recalculation.
- Build-from-CSV backend test: all 4 categories build, and the new charts and metrics run.
  - Basket counts are lower than in the project, because the saved preprocessing filters were not applied in the script.
- AppTest tip: set `PYTHONIOENCODING=utf-8`, otherwise emoji labels crash the Windows console.
- AppTest tip: the metric lookup by label collides between Basket Detail and Sum-up. Filter by section if you rely on it.

---

## Remaining TODOs

1. **Commit + deploy** when the user asks (the user said "wait"): push `v1-1-test_1`, not `main`. Consider bumping `APP_VERSION`, but only if the user asks.
2. ~~Stock (manual) only~~: **decided**: Price follows Price_max(stock) until the user edits Price (current behaviour).
3. ~~Docs~~: **done** (uncommitted). `docs/architecture.md` and `docs/user-manual.md` cover the Planner, `.disc_proj` behaviour, margin-model metrics and manual point, the Sum-up toggles, the key naming rule and `width="stretch"`.
4. ~~Button skip list~~: **done** (uncommitted). `_WRITE_DISALLOWED_KEY_FRAGMENTS` is removed. Every keyed `st.button` / `download_button` / `form_submit_button` key now ends with `_btn` (`BUTTON_KEY_SUFFIX` in `project_io.py`), and uploader keys start with `fu_`. `_button_key_naming_violations()` in `tests/test_e2e.py` enforces this with an AST scan of `pages/` and `ui/`. Old `.disc_proj` files restore fine, because the old button key names no longer match any widget.
5. ~~`use_container_width`~~: **done** (uncommitted). 71 call sites changed: buttons, `dataframe` and `data_editor` use `width="stretch"`, while `plotly_chart` has no width argument (it stretches by default). `requirements.txt` now has `streamlit>=1.49.0`.

6. **Login gate** (uncommitted, 2026-10-08): `require_login()` from `ui/auth_gate.py` runs at the top of the Correlation Analysis page. Users and PBKDF2 hashes are read from `st.secrets["app_users"]`; hashes come from `scripts/hash_password.py`. See `docs/architecture.md` → Access control. **Before deploying, add `[app_users]` in Cloud Secrets**, or the page is locked. The local app is also locked until `.streamlit/secrets.toml` exists. AppTest scripts must set `at.secrets["app_users"]` and `at.session_state["_auth_user"]`; `%TEMP%\pba_auth_test.py` covers the gate.

Verified after 3–5: `python tests/test_e2e.py` → ALL TESTS PASSED, and the real-data AppTest (`%TEMP%\pba_feature_test_btn.py`, a copy of `pba_feature_test.py` with the new button keys) → ALL PASSED.

---

## Risks / gotchas

- **Cloud stale modules:** Streamlit Cloud can serve old copies of existing modules. Put new public names in **new modules**, and don't add kwargs to existing builders that pages call. This is why `margin_model_eval.py`, `sumup_qw_charts.py`, `selected_basket_margin.py` and `progress_stack.py` exist.
- **Restore + buttons:** Streamlit forbids setting button, download_button, data_editor or file_uploader values through session_state. New button keys must end with `_btn`, and the e2e test fails otherwise (see TODO 4).
- **Price_max meaning:** if the Sold fit slope vs Price is positive (`fit_sold.a > 0`), the formula's stationary point is the margin **minimum**, and "M surplus" comes out negative. This is a pre-existing model property and was seen on unfiltered Out data. The model fits are weak on real data: Adj R² is about 0.03 for basket 1111 and 0.24–0.40 for Sum-up.
- **Planner focus overrides** the single-basket detail: a Campaign selected with no Job means the whole Campaign is in focus.
- **Old `.disc_proj` margin models** lack `target` / `metrics` and show N/A until re-run. The page handles this gracefully.
- The local terminal app may not be running. Restart with `streamlit run app.py --server.port 8501`.
