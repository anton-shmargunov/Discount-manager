# PBA — User Manual

**Pricing Correlation & Bucket Analysis · Phase 1**

Version 1.0.2.t1 · Last updated 2026-10-10

---

## What this app does

PBA helps pricing analysts:

1. Upload weekly basket data (sales, price, margin, stock)
2. Compute correlations and cluster baskets
3. Drill into individual baskets and weeks
4. Review aggregate **Sum-Up** metrics
5. Group baskets into **Campaigns and Jobs**, each with its own discount / prom strategy
6. Plan **discounts and promotions** for a selected week using strategy rules or manual edits
7. Export results and updated discount history
8. Optionally **Save** the session as a `.disc_proj` file and **Restore** it later

**Live app:** https://discount-manager-v1-1.streamlit.app/

---

## Getting started

### Run locally

```powershell
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501

### Navigation

1. Open **Correlation Analysis** in the sidebar (main workflow)
2. The home page (`app.py`) shows a brief overview only

### Sign in

**Correlation Analysis** asks for a **Login** and **Password**. Your administrator gives you these.

- After 5 wrong attempts, that login is locked for 5 minutes.
- Refreshing the page or opening a new tab asks you to sign in again. Save a `.disc_proj` first if you need your work.
- **Log out** (sidebar) ends the session and clears unsaved work.

**Administrators:** run `python scripts/hash_password.py` and paste the printed entry into `.streamlit/secrets.toml` (local) or the app's **Settings → Secrets** (Streamlit Cloud). To remove access, delete the user's entry. Details: [architecture.md → Access control](architecture.md#access-control).

---

## Workflow overview

```
Upload data → Set filters → Build Project
       ↓
Optional: K-Means or Octants clustering
       ↓
Browse basket table → Click a row → Basket Detail
       ↓
Optional: Planner → Campaigns / Jobs
       ↓
Sum-Up section → Select a week
       ↓
Week Discount → Apply strategy → Generate / Edit → Export
       ↓
Optional: Project → Save… / Restore (.disc_proj)
```

Each major step is described below in order.

---

## ① Input Data

### Choose input format

| Format | When to use |
|--------|-------------|
| **TrackingBaskets_v2 report** | Single standard report CSV |
| **TrackingBaskets_v2 - product_BS. on date of sale** | Product BS report; metrics on date of sale (default) |
| **TrackingBaskets_v2 - product_BS. monthly av.** | Product BS report; monthly average SoldQty / Revenue |

### Upload files

1. **Main report CSV** — required for all modes
2. **Discount history (discount + prom)** — optional; populates historical Discount and Prom columns. You may upload **one combined file** and/or **several per-category CSVs**. They are merged by `(year_week, basket)` at **Build** (later non-blank cells overwrite earlier ones).

### Product BS Category

When using a **product_BS** input format, choose the category that matches your analysis:

- **Aggregated** — combined market view
- **In**, **Out**, **OutByCondition**, **OutByMinPrice**, **none** — market-specific columns

The discount history file must use columns that match the selected category (see [Discount history format](#discount-history-format)).

**Report mode** always uses **Aggregated** discount columns (`discount`, `prom with stock`) — there is no In/Out split.

> **Tip:** Each input mode + category keeps its own analysis state. After switching category or mode, click **Build Project** again.

---

## ② Preprocessing Filters & Settings

Exclude outlier data points before analysis. Leave a field blank for no limit.

| Filter | Effect |
|--------|--------|
| Sold Quantity Range | Drop weeks where sold is outside min/max |
| Avg Sale Price Range | Drop weeks where price is outside range (min defaults to **0**) |
| Margin (M) Range | Drop weeks where margin is outside range |
| Week (YYYY-WW) Range | Limit to a week interval, e.g. `2024-01` to `2024-52` |
| Number of Clusters (K) | Used when you run **K-Means** (default K = 2) |

---

## Build Project and clustering

### Build Project

Click **🔨 Build Project** after uploading the main report.

On success you will see:

- Basket and week counts
- A log in the **sidebar**
- Sections ③–⑥ below the build area

If build fails, check the sidebar log and verify CSV format.

### K-Means

Groups baskets by their 3-dimensional correlation profile (Sold/Price, M/Price, M/Sold).

1. Set **K** in section ②
2. Click **🔵 K-Means**

### Octants

Assigns baskets to one of 8 sign-based groups (+/− combinations of the three correlations).

Click **🟣 Octants** — independent of K-Means.

---

## ③ Correlation Clusters

- **Cluster summary table** — group sizes and average metrics
- **3D scatter plot** — baskets colored by cluster group

Use this section for a high-level view before drilling into individual baskets.

---

## ④ Detailed Basket Breakdown

Sortable table of all baskets with:

- Total sold, margin, weighted price, average stock
- Correlations: Corr(S/P), Corr(M/P), Corr(M/S)
- Stock trend metrics
- Cluster group
- **Campaign** and **Job** from the Planner (empty for unassigned baskets)

Buttons **Fit Price x Sold**, **Fit Price x Stock x Sold**, and **Fit Cost x Price** add extra columns only after they produce results. **Fit Cost x Price** lives in its own expander. **Skip last points** (default **4**) drops the latest weeks from the fit; **Skip 0** (on by default) drops weeks where Price = 0. **Cost correction** (default **From the last point**) plus **a_min** / **a_max** control **Cost Corrected** on Basket Detail. **Correct Margin** replaces skipped-week margin with **Margin Corrected** = Margin + Sold × (Cost − Cost Corrected). **Price_max** always uses the regression intercept (Option A), not the re-anchored intercept.

**Click any row** to open **⑤ Basket Detail** for that basket.

### Combination

The **Combination** expander shows several baskets summed together in Basket Detail (like Sum-Up):

| Control | Effect |
|---------|--------|
| **Group** | Preview one cluster or octant group |
| **Set a Job** | Create a new Job in the selected Planner Campaign from this Group |
| **Multiselect** | Tick several table rows to combine them |
| **Select All** (with Multiselect) | Use every basket in the table |
| **Weights** | Weight Discount and Prom by Stock, CountProduct or Sold |

Basket Detail uses the first of these that applies: **Group** → **Select All** → ticked table rows → **Planner focus** (the selected Jobs or, with no Job selected, the whole selected Campaign).

> **Tip:** To see a single basket again, set the Planner **Campaign** to **Select…**.

---

## ⑤ Basket Detail

Available after selecting a basket in section ④.

### Chart controls

| Toggle | Effect |
|--------|--------|
| Line + Symbol | Connect weekly points with lines |
| Colour by Quadweek | Color points by quadweek cycle |
| QW Average | Show quadweek average reference lines |

### Week Progress

Expand metrics to plot over time (Sold, Price, Margin, Stock, etc.). **Discount** and **Prom** appear when discount history was uploaded at build.

### Regression fits

Run plane and line fits on selected week ranges; view R², RMSE, MAPE. **Fit Plane** remembers which weeks it used; the margin model's error metrics are computed over the same weeks.

### Margin optimisation model

In the **3D Overview: Price × Stock × M + Margin Optimisation** expander. The model is

```
Sold(P, S) = z0 + a·P + b·S                      (Sold plane fit)
M(P, S)    = (P·(1 − a_cost) − z0_cost) · Sold(P, S)   (with the Cost line fit)
```

1. Fit the Cost line and the Sold plane.
2. Pick the **Evaluation Week**.
3. Optionally change **Price (manual)** / **Stock (manual)**. They default to Price_max and the actual stock of that week, and reset when the week or the fits change. If you change only Stock, Price follows Price_max for the new stock until you edit Price yourself.
4. Click **▶ Run Margin Model**. Manual inputs only take effect on this click.

Results are shown in four columns:

| Column | Shows |
|--------|-------|
| **Actual Results** | Price, Stock, Margin and Sold of the evaluation week |
| **Model Error Metrics** | Adj R², RMSE, MAPE of model M vs actual M over the Sold plane fit weeks |
| **Model at Price (actual)** | Model M, \|dM\| error, Error %, Sold (model) at the actual point |
| **Optimisation** | Price_max (delta = Price_diff vs actual price), M surplus (gain), Sold gain |

When the manual inputs differ from the defaults, the first Optimisation metric is labelled **Price (manual)**, and Price_diff, M surplus and Sold gain are measured at the manual point. With **Margin Corrected** on, actual M is the corrected (hybrid) margin.

> **Note:** If the Sold fit rises with Price, Price_max is a margin *minimum* and M surplus comes out negative. Check Adj R² before trusting Price_max. Models saved before this version show N/A for the new fields until you click Run again.

---

## ⑥ Sum-Up (All Filtered Baskets)

Weekly aggregates across all baskets that passed filters:

- Total sold, margin, stock, weighted price
- Overall correlation KPIs per week
- Monthly Reserve and related metrics

### Display toggles

One row of toggles at the top of the **Sum-Up Total** expander applies to **all** Sum-Up plots (all off by default):

| Toggle | Effect |
|--------|--------|
| **Line + Symbol** | Connect weekly points with lines |
| **Colour by Quadweek** | Colour markers by quadweek. In the combined multi-Y plot the fill shows the quadweek and the outline keeps the series colour |
| **QW Average** | Dashed horizontal line per quadweek (on each series' own axis in the combined plot; per panel in Vertical Stack) |

They work in all three progress views: **Separate plots**, **Combined multi-Y-axis plot** and **Vertical Stack**. On fitted charts, fitted weeks use quadweek colours and the rest are grey.

The Sum-Up margin model works like the [Basket Detail one](#margin-optimisation-model), with **W. Price (manual)** / **Total Stock (manual)** inputs and Total Sold metrics.

### Select a week

In the Sum-Up week selector, pick **one week** to drive the sections below:

- **📋 Weekly Detail** — all baskets for that week
- **📉 Week Discount** — discount planning (main operational section)
- **📅 Week Visualization** — 3-panel Plotly chart for the week

Only one week is active at a time.

---

## Campaign / Job Planner

The sidebar **Planner** expander (below **Project**) groups baskets for planning:

- A **Campaign** contains **Jobs**; a **Job** contains baskets.
- A basket belongs to **at most one Job**.
- Each Job keeps its own Discount and Prom strategy settings. Baskets with no Job use the **default** settings.
- The Planner is per Product BS category, is kept when you rebuild, and is saved in `.disc_proj`.

| Task | How |
|------|-----|
| Create a Campaign | Type a name → **Add** |
| Create a Job | Select the Campaign → type a Job name → **Add** |
| Rename / delete | Select one Campaign or one Job → **Rename** / **Delete** |
| Fill a Job from the table | Select exactly one Job, tick baskets in ④ (Multiselect) → **Update**. Unticked members leave the Job |
| Fill a new Job from a Group | ④ Combination → pick a **Group** → **Set a Job** |

If some baskets already belong to another Job, a **Job assignment conflicts** dialog lists them. Use **Approve all** / **Keep all** or tick rows, then **Confirm**. Only approved baskets move; **Cancel** changes nothing.

Selecting a Campaign or Jobs also sets the **Planner focus** used by Basket Detail (see [Combination](#combination)).

---

## Week Discount

Open **📉 Week Discount: {week}** after selecting a week in Sum-Up.

This is the primary tool for setting **New Discount** and **New Prom** values basket by basket. A progress bar is shown while rows are computed, generated, or applied.

### Column groups

Use toggles to show/hide metric groups:

- **Discount / Prom** — New values, deltas, historical levels at W, W−1, W−4, W−5
- **Stock, Margin, Sold, Price, …** — context metrics for strategy decisions

**Campaign** and **Job** columns follow the Prom columns.

Historical discount/prom columns use quadweek labels when available, e.g. `Discount[3,2]`.

### Highlight colors

| Column | Color |
|--------|-------|
| New Discount | Pink |
| New Prom | Light blue |
| dDiscount | Darker pink |
| dProm | Darker blue |

### Filters

Below the column toggles, a **min / max filter table** narrows visible baskets.

Set bounds on New Discount, Stock, dSt_QW, Margin, MtoSt, Monthly Reserve, etc. Only rows matching all active bounds are shown.

---

## Discount strategy

Expand **Discount strategy settings** in the Week Discount section.

### Which settings you are editing

The **Campaign** switch above the strategy settings decides what the on-screen settings belong to:

| Campaign switch | On-screen settings | **Apply** saves them to |
|-----------------|--------------------|-------------------------|
| Off | Default settings (baskets with no Job) | The default |
| On | The Job(s) selected in the Planner | Every selected Job (overwrites them) |

Assignment of baskets to Jobs is edited only in the [Planner](#campaign--job-planner).

### Generation mode

| Mode | Result |
|------|--------|
| **Based on Strategies** | Apply bin tables + margin/MtoSt rules (see formula below) |
| **Set previous discount** | New Discount = current historical discount |
| **Zero all Discounts** | New Discount = 0 |

### Formula (Based on Strategies)

```
New Discount = Discount[current] + (dDiscount(strategy) + Balance) × Multiplicator
```

**Strategy selection:**

- **Margin categories** — Conservative / Moderate / Strong based on current margin
- **Sold = 0** — separate strategy table + balance
- **MtoSt** (optional toggle) — alternate bins when margin trend conditions are met

### Strategy tables

Edit bin tables directly in the UI:

- **Conservative / Moderate / Strong** — map `dSt_QW` (stock change %) → `dDiscount`
- **MtoSt** — map `dMtoSt` → `dDiscount`

Defaults load from `configs/strategies/strategies.v1.csv`.

### Priority 1 — missing discount

If a basket has no discount history row for the current week, **Discount[current]** is treated as the **missing discount default** (UI default: **0** / n/a).

### Generate Discount

| Button | Baskets | Settings used | Earlier generated values |
|--------|---------|---------------|--------------------------|
| **Generate Discount**, Campaign switch off | Baskets with no Job | On-screen | Kept for other baskets |
| **Generate Discount**, Campaign switch on | Baskets of the selected Jobs | On-screen | Kept for other baskets |
| **Generate Discount all** | Every basket | Each Job's saved settings; saved default for baskets with no Job | Replaced |

Click **Apply** first if you want **Generate … all** to use settings you just changed on screen. **Generate Prom** / **Generate Prom all** work the same way.

---

## Prom strategy

Expand **Prom strategy settings**.

| Mode | Result |
|------|--------|
| **Set previous prom** | New Prom = Prom[current] |

Click **Generate Prom** (or **Generate Prom all**) separately from discount generation. Basket and settings selection follow the [Generate Discount](#generate-discount) rules.

**Order of operations:**

1. Generate Discount (optional)
2. Generate Prom (optional)
3. Edit manually (optional)
4. Review dDiscount / dProm

---

## Manual edit

1. Click **Edit** — table switches to editable mode for **New Discount** and **New Prom** only
2. Change values in the editor
3. Click **Apply** to save overrides and recalculate **dDiscount** / **dProm**
4. Click **Cancel** to discard unsaved edits

**Notes:**

- dDiscount and dProm update on **Apply**, not while typing (shown in edit-mode caption)
- Apply saves overrides for **all baskets currently visible** after filters
- Other columns remain read-only in edit mode

---

## Understanding dDiscount and dProm

| Column | Meaning |
|--------|---------|
| **dDiscount** | New Discount minus **historical** Discount[current] |
| **dProm** | New Prom minus **historical** Prom[current] |

**Missing value rule:** if either side is empty, it is treated as **0**.

Examples:

- Prom[current] = 2%, New Prom empty → **dProm = −2%**
- New Prom = 2%, no historical prom → **dProm = +2%**

Historical "current" comes from discount history uploaded at build, not from the New columns.

---

## Export

Open the **Export** expander below the Week Discount table. Buttons are disabled while **Edit** mode is on.

| Button | What you get |
|--------|----------------|
| **Week Discount** | Visible Week Discount columns (raw numeric values) for the current category |
| **Discount history. Current** | Discount-history CSV for the **current** Product BS category (report mode: Aggregated) |
| **Discount history. All** | One combined hist CSV with New Discount / New Prom from **every Product BS category already Built** this session (product_BS modes only) |

**Discount history. All** is empty until you **Build** (and generate/edit) each category you want included. Switching category and building again is required; categories not built in this session are omitted.

### Options

- **Include 'no stock'** — expand Week Discount and hist exports to the full canonical basket list (625 baskets); baskets without stock keep empty discount/prom cells
- **all history** (default **on**) — hist exports include uploaded history plus new week rows (same basket-week in the new week overwrites)

### Discount history week advance

Downloads use the **same format as the discount history input**, for **selected week + 1**:

| Field | Advance rule |
|-------|----------------|
| `week from y_w (1_52)` | +1 week (52 → 1, year +1) |
| `year_week` | Same separator as source (`2026-25` → `2026-26`) |
| `week in quad (1_4)` | 1→2→3→4→1 |
| `quadweek` | +1 only when new week in quad = 1 |

Requires discount history upload at **Build** for a full merge when **all history** is on. **Discount history. All** merges hist snapshots from each built category.

Export column set depends on Product BS Category (report mode uses Aggregated columns). Combined **All** files contain every category column; unused cells stay empty.

Discount-history exports end with four Planner columns: `campaign_id`, `campaign_name`, `job_id`, `job_name` (empty for baskets with no Job).

---

## Discount history format

Optional CSV with weekly discount and promotion per basket.

### Required metadata columns

- `quadweek`
- `year_week`
- `week from y_w (1_52)` (recommended)
- `week in quad (1_4)` (recommended)
- `basket`

### Value columns (by category)

| Category | Discount column | Prom column |
|----------|-----------------|-------------|
| Aggregated | `discount` | `prom with stock` |
| In | `BasketDiscountInMarket` | `Prom, BasketDiscountInMarket` |
| Out | `BasketDiscountOutOfMarket` | `Prom, BasketDiscountOutOfMarket` |
| OutByCondition | `BasketDiscountOutOfMarketByCondition` | `Prom, BasketDiscountOutOfMarketByCondition` |
| OutByMinPrice | `BasketDiscountOutOfMarketByMinPrice` | `Prom, BasketDiscountOutOfMarketByMinPrice` |
| none | `none` | `Prom, none` |

### Value rules

**Discount:** signed decimal; negative = price reduction (e.g. `-0.05` = −5%)

**Prom:**

- `n/a` or empty → 0
- Valid steps: 0, 0.02, 0.04, 0.06, … (even cent increments)
- Negative or odd-cent values (0.01, 0.03) are rejected at parse

Example file: `inputs/discount_hist_EXAMPLE_SHORT.csv`

Per-category files (only In columns, only Out columns, …) may be uploaded together; Build merges them into one wide table.

---

## Save and restore a project

The sidebar **Project** expander (above **Log**) snapshots the current session.

| Action | Result |
|--------|--------|
| **Save…** | Dialog for a file name → download a `.disc_proj` file |
| **Restore** | Upload a `.disc_proj` file, then click **Restore** |

What is saved:

- Built analysis for every Product BS category / input mode in the session, with discount history already merged
- The uploaded discount history (used by the **all history** export)
- The Planner: Campaigns, Jobs, memberships and their strategy settings
- Week Discount generated values and manual edits
- Fits and margin models
- Filters, clustering, and other UI settings
- Sidebar log

What is **not** saved:

- Your sign-in (you always sign in yourself)
- Original CSV uploads. You do not need to re-attach them after Restore; the uploaders are only read by **Build Project**
- Button clicks and table-selection widget states
- A remembered disk folder (the browser chooses where downloads go)

Project files saved on Streamlit Cloud open locally and vice versa.

Refresh or a new browser tab still starts empty unless you Restore a file.

---

## Sidebar log

The **Log** panel records:

- Input mode and upload row counts
- Product BS category and metric basis
- Discount history merge summary (including multi-file aggregation)
- K-Means / Octants completion
- Project restore
- Build errors

Use it for troubleshooting when results look unexpected.

---

## Typical session checklist

1. Select input format and upload report CSV
2. Optionally upload discount history (one combined file and/or several per-category files)
3. Set filters → **Build Project** (repeat for each Product BS category you need)
4. Optional: **K-Means** or **Octants**
5. Click a basket → review Basket Detail (optional)
6. Optional: **Planner** → create Campaigns / Jobs and fill them (**Update** or **Set a Job**)
7. In Sum-Up, select target week
8. Open **Week Discount**
9. Configure strategy → **Apply** (default with the Campaign switch off; Jobs with it on)
10. **Generate Discount** / **Generate Prom**, or **Generate Discount all** / **Generate Prom all**
11. **Edit** / **Apply** manual adjustments
12. Open **Export** → **Week Discount**, **Discount history. Current**, and/or **Discount history. All**
13. Re-import exported discount history on the next planning cycle
14. Optional: **Project → Save…** to download a `.disc_proj` snapshot

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| "Access is not configured" | No users in the app secrets | Administrator adds `[app_users]` entries |
| "Too many failed attempts" | 5 wrong passwords for that login | Wait 5 minutes |
| Asked to sign in again | Page refreshed or new tab | Expected; sign in, then Restore a saved project if needed |
| Sections below build are empty | Build not run or failed | Upload file, click Build, check sidebar log |
| K-Means / Octants disabled | No analysis in current scope | Build Project first |
| Discount/Prom columns empty | No discount history uploaded | Upload discount history and rebuild |
| Switching In/Out shows wrong values | Separate scope per category | Rebuild after category change; values are per-scope |
| dProm looks wrong after edit | Deltas update on Apply only | Click Apply after editing |
| **Discount history. All** empty / disabled | Category not Built this session | Build and generate/edit each Product BS category, then export |
| Export history missing old weeks | No hist at build or **all history** off | Upload hist before Build; enable **all history** |
| Prom export rejected on re-import | Invalid prom step | Use 0, 0.02, 0.04, … only |
| Restore failed / buttons error | Invalid file or widget-key conflict | Use a `.disc_proj` from this app version; retry Restore |
| Restored session has no CSV files | Uploads are not stored in the project file | Expected — analysis is restored from the snapshot |
| Basket Detail shows a combination instead of the clicked basket | A Planner Campaign / Job is selected (Planner focus) | Set the Planner **Campaign** to **Select…** |
| **Generate Discount** is disabled with the Campaign switch on | No Job selected in the Planner | Select one or more Jobs, or turn the switch off |
| **Update** is disabled | Not exactly one Job selected | Select a single Job |
| Margin model shows N/A for Sold / metrics | Model saved before this version | Click **▶ Run Margin Model** again |
| M surplus is negative | Sold fit rises with Price (weak fit) | Check Adj R²; refit with other weeks |

---

## Data persistence

- Analysis results and generated discounts live in **browser session state** until you save
- Refreshing the page or closing the tab **clears unsaved work**
- **Project → Save…** downloads a `.disc_proj` snapshot (including the Planner); **Restore** loads it in a new session
- Export CSV files to persist Week Discount and discount history outputs independently of the project file
- Strategy defaults reload from `configs/strategies/strategies.v1.csv` on each session (saved UI edits to bins are included in `.disc_proj`)

---

## Related documents

- [architecture.md](architecture.md) — technical structure for developers
- [README.md](../README.md) — install and quick start
- [CHANGELOG.md](../CHANGELOG.md) — what changed in each version
