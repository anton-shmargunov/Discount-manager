# PBA v1 — Handoff (2026-06-18)

## Start here

This handoff covers **Basket Detail chart work** from the 2026-06-18 session (panel layout, quadweek coloring, QW averages).

For the full MVP baseline — input modes, product-BS parsing, Sum-Up table, theme bootstrap, architecture — read **`handoff_260617.md`** first.

---

## Project Root

`d:\Anton\UTires\Code\Pricing\Pricing Correlation and Bucket Analysis\streamlit\PBA.v.1.250525\`

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
```

**Rule:** analytics never depend on UI; chart builders return Plotly figures only.

---

## Basket Detail (section ⑤)

Location: `pages/01_Correlation_Analysis.py` (~lines 1240–1500), shown when `ss.selected_basket` is set.

### Global chart toggles (per basket)

Three toggles in a row, **before** expanders:

| Order | Toggle | Session state | Default |
|---|---|---|---|
| 1 | **Line + Symbol** | `show_line` | `False` |
| 2 | **Colour by Quadweek** | `show_qw_colors` | `False` |
| 3 | **QW Average** | `show_qw_average` | `False` |

- Toggle widget keys are per basket: `tog_line_{basket}`, `tog_qw_{basket}`, `tog_qw_avg_{basket}`.
- Chart widget keys include all three states: `chart_state_key = f"{show_qw}_{show_line}_{show_qw_avg}"` — required so Streamlit re-renders when toggles change.

All Basket Detail charts receive:

- `use_qw_colors=show_qw`
- `show_line=show_line`
- `show_qw_average=show_qw_avg`

### Expanders

1. **Week Progress** (expanded by default)
   - 8 metric toggles: Stock, CountProduct, Price, Purchase, Sold, Revenue, Margin, Cost/Sold
   - Defaults ON: Stock, Price, Sold, Margin
   - Revenue = `sold × price` (computed in `_basket_week_progress_specs`)
   - Charts via `build_metric_progress()` in `sumup_charts.py`
   - 2-column grid layout

2. **Sold vs Price · Margin vs Price · Margin vs Sold**
   - 3-panel scatter via `build_basket_scatter_3panel()` (4-panel alias kept for compatibility)

3. **Cost vs Price**
   - Line fit scope + manual point selection
   - Fit highlight on chart **only** when scope is **Manual Selection**

4. **3D Price × Sold × M**

5. **3D Price × Stock × Sold**
   - Plane fit; fit highlight only for Manual Selection

6. **3D Price × Stock × M + Margin Optimisation**
   - Optional margin surface overlay from saved margin model

### Quadweek data source

`BasketTimeSeries.quadweeks` — populated in `core/transforms/data_prep.py` from report `quadweek` per week (`sold_dict[w]["quadweek"]`).

---

## Chart behaviour — Colour by Quadweek

Implemented in `visualizations/detail_charts.py`.

**Design:** one connected trace per series; do **not** split into multiple traces by QW (that breaks line continuity).

| Element | When QW colors ON |
|---|---|
| Markers | Per-point color from `qw_color_map()` |
| Line | Single series color (unchanged) |
| Manual fit highlight | Selected points keep QW color; unselected → grey translucent. Without QW colors, selected → red, unselected → grey |

Key helpers:

- `normalize_quadweek()` — consistent QW label keys
- `qw_color_map()` — distinct color per unique QW (`CLUSTER_COLORS` cycle)
- `marker_colors_for_points()` — marker colors + optional fit highlighting

**Week Progress** uses the same marker coloring via `build_metric_progress(..., use_qw_colors=...)`.

**Important fix (this session):** Cost vs Price and 3D charts previously always passed fit indices, which overwrote QW colors. Now `fitted_indices` / `highlight_*` is passed **only** when fit scope is **Manual Selection**.

---

## Chart behaviour — QW Average

Overlay only; main series unchanged.

| Chart | Overlay |
|---|---|
| Week Progress | Dashed horizontal segment per **contiguous** QW span at mean of that metric within the QW (`add_qw_average_hlines`) |
| 2D scatter panels | Diamond marker at mean (x, y) per QW (`add_qw_average_markers_2d`) |
| Cost vs Price | Diamond at mean price / mean cost per QW |
| 3D charts | Diamond at mean (price, stock, sold or M) per QW (`add_qw_average_markers_3d`) |

Helpers:

- `qw_index_groups()` — indices per QW
- `qw_index_spans()` — contiguous QW blocks in week order
- `qw_value_averages()` — mean metric per QW

QW average overlays use `qw_color_map()` colors **independently** of whether **Colour by Quadweek** is on.

---

## Files changed (2026-06-18 session)

| File | Changes |
|---|---|
| `pages/01_Correlation_Analysis.py` | Basket Detail layout; 3 global toggles; Week Progress expander + specs; wired QW color/average to all detail charts; `chart_state_key` on plot keys; helpers `_basket_week_progress_specs`, `_basket_series_values` |
| `visualizations/detail_charts.py` | QW color helpers; QW average helpers; `show_qw_average` on scatter, cost, 3D builders; single-trace QW marker coloring; conditional fit highlighting |
| `visualizations/sumup_charts.py` | `build_metric_progress()` extended with `quadweeks`, `use_qw_colors`, `show_qw_average`; imports `add_qw_average_hlines` from `detail_charts` |
| `configs/theme_bootstrap.py` | *(earlier in session)* centralized theme hydration — see `handoff_260617.md` |

**Also from prior session (still relevant):** `handoff_260617.md` documents theme bootstrap, product-BS modes, Sum-Up exports, etc.

---

## Session state (Basket Detail related)

```python
"show_line":        False,
"show_qw_colors":   False,
"show_qw_average":  False,
"fit_cost":         {},   # {basket: Linefit}
"fit_sold":         {},   # {basket: Planefit}
"fit_sold_m":       {},   # {basket: Planefit}
"margin_model":     {},   # {basket: margin model output}
```

---

## Tests

```powershell
python -m py_compile visualizations/detail_charts.py visualizations/sumup_charts.py pages/01_Correlation_Analysis.py
python tests/test_e2e.py
```

**Last result:** `ALL TESTS PASSED`

**Not covered by e2e:**

- Streamlit toggle interactions (Line / QW color / QW average)
- Visual verification of QW dashed lines and diamond overlays
- Browser theme cold-load checklist (see `handoff_260617.md`)

**Manual smoke checklist — Basket Detail:**

1. Select a basket with multiple weeks spanning 2+ quadweeks
2. Toggle **Colour by Quadweek** — markers change color; lines stay connected
3. Toggle **QW Average** — dashed means on Week Progress; diamonds on scatter/3D/cost
4. Cost vs Price / 3D Sold fit: switch scope to **Manual Selection** — only then should non-selected points grey out
5. Toggle all three controls — charts refresh (keys include all three booleans)

---

## Known gaps / next work

1. **Sum-Up section** — has its own `show_line` toggles; no QW Average toggle there yet (Basket Detail only)
2. **Large UI file** — `pages/01_Correlation_Analysis.py` ~2080 lines; consider extracting Basket Detail block to a helper module
3. **Phase 2 architecture** — DuckDB, pipelines, services not started (see spec)
4. **No UI automation tests** — manual verification only
5. **Theme bootstrap** — if flaky on Streamlit 1.49, upgrade to `>=1.52` (see `handoff_260617.md`)

---

## Risks

| Risk | Detail |
|---|---|
| QW average vs y-axis range | Week Progress y-range is padded from point min/max; QW means should lie within range but edge cases with sparse QWs worth watching |
| Chart key proliferation | Every toggle change forces full chart rebuild; acceptable for MVP |
| Fit highlight + QW color interaction | Only Manual Selection passes indices; regression if scope logic changes |
| `detail_charts` ↔ `sumup_charts` import | `sumup_charts` imports `add_qw_average_hlines` from `detail_charts`; avoid circular imports if moving helpers |

---

## Key reference paths

| Topic | Path |
|---|---|
| Basket Detail UI | `pages/01_Correlation_Analysis.py` |
| Scatter / 3D / QW helpers | `visualizations/detail_charts.py` |
| Week progress charts | `visualizations/sumup_charts.py` → `build_metric_progress` |
| Quadweek on time series | `core/transforms/data_prep.py`, `core/models.py` → `BasketTimeSeries.quadweeks` |
| Full MVP handoff | `handoff_260617.md` |
| E2E tests | `tests/test_e2e.py` |
| Past chat (this session) | `41a3d315-1af7-4fc7-b326-1ea74312f5d7` |

---

## Suggested first message for fresh chat

> Continue PBA Streamlit MVP at `PBA.v.1.250525`. Read `handoff_260618.md` (Basket Detail) and `handoff_260617.md` (full MVP). Basket Detail has three toggles: Line + Symbol, Colour by Quadweek, QW Average — all wired to Week Progress, 3-panel scatter, Cost vs Price, and 3D charts. QW coloring uses single connected traces with per-point marker colors; QW Average adds dashed horizontal means (week charts) and diamond means (scatter/3D). Last test: `python tests/test_e2e.py` → ALL TESTS PASSED.
