# Changelog

Main updates only, newest first. Details live in `handoff_*.md` and `docs/`.

**Status as of 2026-10-10.** Changes are dated by when the work was done; releases by commit.

---

## 1.0.2.t1: 2026-10-06 – 2026-10-10 (deployed to the test app)

### Added
- **2026-10-08 · Login / password** for the Correlation Analysis page. Users and PBKDF2 password hashes live in the app secrets (`[app_users]`). Includes login throttling and `scripts/hash_password.py`. The page stays locked until at least one user is configured.
- **2026-10-06 – 10-08 · Margin Optimisation table** (Basket Detail and Sum-up): new **Model Error Metrics** column (Adj R², RMSE, MAPE of model M vs actual M over the Sold plane fit weeks). New Sold metrics: actual, model and gain.
- **2026-10-06 – 10-08 · Price / Stock (manual)** inputs for the margin model, applied on **Run Margin Model**. Price follows Price_max of the entered stock until edited.
- **2026-10-08 · Sum-up display toggles**: Line + Symbol, Colour by Quadweek and QW Average, applied to all Sum-up plots.
- **2026-10-08 · `CHANGELOG.md`** (this file).

### Changed
- **2026-10-06 – 10-08 · Basket Detail Price_diff** is shown as a delta under Price_max, as in Sum-up.
- **2026-10-08 · Button key naming**: every button / download button key now ends with `_btn`. This replaces the name list in `project_io.py`, and an e2e test enforces it.
- **2026-10-08 · `use_container_width` → `width="stretch"`** everywhere (charts drop the argument). `requirements.txt` now needs `streamlit>=1.49.0`.
- **2026-10-08 · Docs**: `docs/architecture.md` and `docs/user-manual.md` updated for the Planner, project restore, the margin model, the Sum-up toggles and the key naming rule.
- **2026-10-10 · Docs**: new `docs/access-setup.md`: how to add users locally and on Cloud, and how to keep secrets out of a Google Drive–synced folder.
- **2026-10-10 · Version** `1.0.1.t1` → `1.0.2.t1`.

### New modules
- `core/optimization/margin_model_eval.py` (2026-10-06)
- `visualizations/sumup_qw_charts.py` (2026-10-08)
- `core/security/passwords.py`, `ui/auth_gate.py`, `scripts/hash_password.py` (2026-10-08)

---

## 1.0.1: 2026-09-29 – 2026-09-30 (deployed to the test app)

### Added
- **2026-09-29 · Campaign / Job Planner** layer (sidebar): exclusive basket membership, per-Job Discount / Prom settings, a conflict approval dialog, and **Set a Job** from a Group.
- **2026-09-29 · Generate Discount all / Generate Prom all**: every Job with its stored settings, plus the default for unassigned baskets.
- **2026-09-29 · Campaign** and **Job** columns in the basket and Week Discount tables. Four Planner columns at the end of the discount-history export.

### Fixed
- **2026-09-30 · Project restore on Streamlit Cloud**: `.disc_proj` files now load across Streamlit and NumPy versions, and button keys are no longer restored.
