# PBA — User Manual

**Pricing Correlation & Bucket Analysis · Phase 1**

Version 1.0.0 · Last updated 2026-09-12

---

## What this app does

PBA helps pricing analysts:

1. Upload weekly basket data (sales, price, margin, stock)
2. Compute correlations and cluster baskets
3. Drill into individual baskets and weeks
4. Review aggregate **Sum-Up** metrics
5. Plan **discounts and promotions** for a selected week using strategy rules or manual edits
6. Export results and updated discount history
7. Optionally **Save** the session as a `.disc_proj` file and **Restore** it later

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

---

## Workflow overview

```
Upload data → Set filters → Build Project
       ↓
Optional: K-Means or Octants clustering
       ↓
Browse basket table → Click a row → Basket Detail
       ↓
Sum-Up section → Select a week
       ↓
Week Discount → Generate / Edit → Export
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

Buttons **Fit Price x Sold**, **Fit Price x Stock x Sold**, and **Fit Cost x Price** add extra columns only after they produce results. **Fit Cost x Price** lives in its own expander. **Skip last points** (default **4**) drops the latest weeks from the fit; **Skip 0** (on by default) drops weeks where Price = 0. **Cost correction** (default **From the last point**) plus **a_min** / **a_max** control **Cost Corrected** on Basket Detail. **Correct Margin** replaces skipped-week margin with **Margin Corrected** = Margin + Sold × (Cost − Cost Corrected). **Price_max** always uses the regression intercept (Option A), not the re-anchored intercept.

**Click any row** to open **⑤ Basket Detail** for that basket.

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

Run plane and line fits on selected week ranges; view R², RMSE, MAPE. **Margin model** shows analytical optimal price for the selected week.

---

## ⑥ Sum-Up (All Filtered Baskets)

Weekly aggregates across all baskets that passed filters:

- Total sold, margin, stock, weighted price
- Overall correlation KPIs per week
- Monthly Reserve and related metrics

### Select a week

In the Sum-Up week selector, pick **one week** to drive the sections below:

- **📋 Weekly Detail** — all baskets for that week
- **📉 Week Discount** — discount planning (main operational section)
- **📅 Week Visualization** — 3-panel Plotly chart for the week

Only one week is active at a time.

---

## Week Discount

Open **📉 Week Discount: {week}** after selecting a week in Sum-Up.

This is the primary tool for setting **New Discount** and **New Prom** values basket by basket. A progress bar is shown while rows are computed, generated, or applied.

### Column groups

Use toggles to show/hide metric groups:

- **Discount / Prom** — New values, deltas, historical levels at W, W−1, W−4, W−5
- **Stock, Margin, Sold, Price, …** — context metrics for strategy decisions

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

Click **Generate Discount** to compute **New Discount** for all visible baskets using the current strategy settings.

---

## Prom strategy

Expand **Prom strategy settings**.

| Mode | Result |
|------|--------|
| **Set previous prom** | New Prom = Prom[current] |

Click **Generate Prom** separately from discount generation.

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

- Built analysis for every Product BS category / input mode in the session
- Week Discount generated values and manual edits
- Filters, clustering, and other UI settings
- Sidebar log

What is **not** saved:

- Original CSV uploads (you do not need to re-attach them after Restore — analysis is in the snapshot)
- A remembered disk folder (the browser chooses where downloads go)

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
6. In Sum-Up, select target week
7. Open **Week Discount**
8. Configure strategy → **Generate Discount** → **Generate Prom**
9. **Edit** / **Apply** manual adjustments
10. Open **Export** → **Week Discount**, **Discount history. Current**, and/or **Discount history. All**
11. Re-import exported discount history on the next planning cycle
12. Optional: **Project → Save…** to download a `.disc_proj` snapshot

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
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

---

## Data persistence

- Analysis results and generated discounts live in **browser session state** until you save
- Refreshing the page or closing the tab **clears unsaved work**
- **Project → Save…** downloads a `.disc_proj` snapshot; **Restore** loads it in a new session
- Export CSV files to persist Week Discount and discount history outputs independently of the project file
- Strategy defaults reload from `configs/strategies/strategies.v1.csv` on each session (saved UI edits to bins are included in `.disc_proj`)

---

## Related documents

- [architecture.md](architecture.md) — technical structure for developers
- [README.md](../README.md) — install and quick start
