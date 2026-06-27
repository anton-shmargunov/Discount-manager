# Pricing Correlation & Bucket Analysis — Phase 1

**AI-Assisted Analytical Web Application · Streamlit Prototype**

---

## Overview

This is Phase 1 of the PCBA (Pricing Correlation & Bucket Analysis) platform.
It provides multidimensional pricing analytics, basket clustering, and margin optimisation
over weekly time-series data.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the application
streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Documentation

| Document | Audience |
|---|---|
| [docs/user-manual.md](docs/user-manual.md) | Analysts and operators — workflows, Week Discount, exports |
| [docs/architecture.md](docs/architecture.md) | Developers — modules, data flow, session state, extension points |

---

## Input CSV Format

Each of the four required CSV files must have:

| Column | Description |
|---|---|
| `year_week` | Week identifier — e.g. `2024-01` (YYYY-WW) |
| `quadweek` | 4-week cycle label — used for trend analysis |
| `<BasketCode>` | One column per basket; values are the metric for that week |

The four files are:
1. **SoldIn** — units sold per basket per week
2. **AvgSalePrice_In** — average sale price per basket per week
3. **M_In** — margin (revenue − cost) per basket per week
4. **Stock** — stock quantity per basket per week

---

## Architecture

```
project_root/
│
├── app.py                     ← Thin Streamlit entry point
│
├── pages/
│   └── 01_Correlation_Analysis.py  ← Main analysis UI page
│
├── core/                      ← Pure analytical engine (no Streamlit)
│   ├── models.py              ← Shared dataclasses
│   ├── analytics/             ← High-level workflows
│   ├── clustering/            ← K-Means, Octants
│   ├── modeling/              ← MLR, SLR, PCA, fit stats
│   ├── optimization/          ← Pricing optimisation model
│   ├── statistics/            ← Pearson, rolling metrics
│   └── transforms/            ← ETL, feature engineering
│
├── services/                  ← Future: reporting, forecasting, AI agents
├── data/                      ← raw/, processed/, duckdb/, cache/, exports/
├── pipelines/                 ← Future: ETL orchestration
├── visualizations/            ← Reusable Plotly chart builders
├── configs/                   ← Constants and settings
└── tests/                     ← Analytical unit tests
```

### Core Architectural Rule

> **UI can depend on analytics. Analytics must NEVER depend on UI.**

The `core/` layer has zero Streamlit imports and can be reused directly in
FastAPI, background workers, Jupyter notebooks, or tests.

---

## Analytical Features

| Feature | Description |
|---|---|
| **Pearson correlations** | Corr(Sold/Price), Corr(M/Price), Corr(M/Sold) per basket |
| **K-Means clustering** | Group baskets by 3D correlation profile |
| **Octant clustering** | Sign-based 8-way grouping of correlation space |
| **Stock trend metrics** | Within-quadweek slope and between-quadweek jump |
| **MLR plane fit** | `Sold = z₀ + a·Price + b·Stock` |
| **PCA plane fit** | Orthogonal distance minimisation |
| **Cost line fit** | `Cost = z₀ + a·Price`; derives leverage price Pl |
| **Margin optimisation** | Analytical `Price_max(Stock)` from combined fits |
| **Sum-Up** | Weekly aggregates with overall correlation KPIs |

---

## Dependency Flow

```
data
  ↓
transforms
  ↓
statistics / modeling / clustering
  ↓
optimization
  ↓
analytics
  ↓
services / UI / API
```

---

## Phase 2 Migration Path

The `core/`, `services/`, and `pipelines/` folders are designed for direct
migration into a production SaaS architecture:

```
Next.js Frontend
      ↓
FastAPI API Layer
      ↓
Analytical Core Services  (core/ migrates here as-is)
      ↓
Pipelines / Workers
      ↓
PostgreSQL + TimescaleDB + DuckDB
```

---

## Requirements

- Python ≥ 3.11
- See `requirements.txt` for full dependency list
