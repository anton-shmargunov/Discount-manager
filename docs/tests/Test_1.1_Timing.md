# Test 1.1. Timing

**Type:** Performance / UX (UI freeze + progress feedback)  
**App version baseline:** `1.0.3.t2` (branch `v1-0-test_2`)  
**First run:** 2026-11-14  
**Owner:** Pricing / PBA

---

## 1. Purpose

Measure wall-clock time of operations that **grey out** the Streamlit UI (full script rerun or long Drive I/O), and verify each long wait shows a **spinner / progress** indicator instead of a silent freeze.

Secondary goals:

- Rank grey-out causes (Drive vs Build vs page redraw vs hist export).
- Confirm Week Discount hist caching keeps category/toggle redraws fast when warm.
- Catch regressions that reintroduce mid-page hangs with no feedback (e.g. Start → Input form, Restore).

---

## 2. Scope

| In scope | Out of scope |
|----------|----------------|
| Drive connect, list flows, list/download projects | Full functional scenario (see A-used/In scenario script) |
| Flow Start / Switch / Refresh | Cloud deploy latency |
| Project Save / Restore feedback | Browser paint profiling |
| Build, Product BS category switch, Fit, Release prep | Exact ms SLOs for every chart |
| Released-history lookup / page warmup | |

---

## 3. Environment

- **Machine:** local Windows, `streamlit run app.py` (or headless timing script).
- **Secrets:** `~/.streamlit/secrets.toml` → `[gdrive]` configured (same as app).
- **Flow / week:** `A-used`, week `2026-45`, category focus `In` (also build `Out`, `OutByCondition` for multi-cat timing).
- **Inputs (attachments / known fixtures):**
  - Tracking: `data_-_2026-11-10T135536.366.A-used.26_20-26_45.csv`
  - Discount history: `discount_hist_A-used_ALL_2026-45_r07_rlsd.csv`
  - Drive project: `discount_project_A-used_ALL_2026-45_r09_rlsd.disc_proj`
- **Working tree:** repo root `PBA.v.1.250525`.

---

## 4. Metrics

For each timed step record:

| Field | Meaning |
|-------|---------|
| `seconds` | Wall time (`perf_counter`) |
| `greys_ui` | Yes if Streamlit full-page grey / blocking rerun is expected |
| `progress` | `spinner` / `progress` / `partial` / `none` **as shown in the UI** (not only code intent) |
| `note` | Where it appears (start screen, sidebar, Build, Export, …) |

**Pass rule (UX):** any step with `greys_ui` and typical duration **≥ ~1 s** must show a visible spinner/status on the **main** content (not only inside a collapsed sidebar expander). Silent grey-out = **FAIL**.

**Pass rule (perf, soft):** warm Product BS switch / Monthly Reserve proxy should stay **≪ cold** hist path (baseline: cold ~2 s CPU slice, warm ~0.2 s for measured rebuild work; browser overhead extra).

---

## 5. Procedure

### 5.A Automated timing probe (primary)

Script used on first run (copy into repo or keep under `%TEMP%` if not checked in):

```text
%TEMP%\pba_timing_greyout.py
```

Run from repo root:

```powershell
$env:PYTHONIOENCODING='utf-8'
python $env:TEMP\pba_timing_greyout.py
```

The script must time at least:

1. **Drive:** open store + token refresh  
2. **Drive:** `list_drive_flows` (Choose a flow / Refresh)  
3. **Drive:** list `.disc_proj` for `A-used` (Project Restore list)  
4. **Drive:** download `r09` project  
5. **Project:** unpack + `apply_project_payload` + hist sync  
6. **Build:** read Tracking + hist CSVs; Build `In`, `Out`, `OutByCondition`  
7. **Page grey-out proxies:** switch category cold/warm; Monthly Reserve proxy; after Fit  
8. **Exports:** `hist_all` cold/cached; `hist_current`; project pack  
9. **Flow switch** proxy (re-list flows after wipe path)

Print:

- Grey-out ranking (slowest first)  
- Progress coverage table (required vs observed)  
- Sum of measured slices  

### 5.B Manual UI checks (required after spinner work)

With the live app (`streamlit run app.py`), confirm **visible** feedback:

| # | Action | Expect |
|---|--------|--------|
| M1 | Open **Choose a flow** (cold flow list) | Spinner in start-screen body (“Loading flows…”) — **no duplicate** Start-work widgets |
| M2 | **Start** on `A-used` | Spinner while starting; then **Opening flow…** (released-hist warmup) before Input widgets; **no** 5 s silent grey with blank/partial form |
| M3 | Sidebar **Project** → **Load list** | Spinner only after Load (not on every page paint) |
| M4 | **Restore from Drive** (download + apply) | Download spinner; restore spinner; then Opening-flow / warmup if needed — Input form must not hang after Discount history with no spinner |
| M5 | Cold **released discount history** after uploaders | Spinner in the history option slot (or already warmed) |
| M6 | **Build** | Existing “Parsing and computing…” spinner |
| M7 | Bulk **Fit** / detail **Fit Line|Plane** / margin model | Spinner on click |
| M8 | **Release…** prepare / zip / Drive upload | Spinners on each blocking step |
| M9 | **Refresh** flow list | Spinner; no greyed duplicate Start form |

---

## 6. Progress coverage checklist

Update the “Observed” column when re-running. Baseline “Before busy UX” is the 2026-11-14 automated probe (`progress=none` on Drive paths). “After” is expected on current `v1-0-test_2` after busy + stale-UI fixes.

| Action | Before (2026-11-14) | After (expected) |
|--------|---------------------|------------------|
| Choose a flow / list flows | none | spinner (stable `st.empty`) |
| Refresh flow list | none | spinner |
| Start / Switch flow | none | spinner + page warmup |
| Project Drive list | none (auto on every load) | on-demand **Load list** + spinner |
| Project Restore download | none | spinner |
| Project Restore apply | none | spinner + `_drive_warmup_needed` |
| Project Save / Drive upload | none | spinner |
| Build | spinner | spinner (OK) |
| Switch Product BS (built) | partial | no mid-page cost-correction spinner; page may still grey (Streamlit) |
| Fit click | none | spinner then rerun |
| Generate Discount | progress | progress (OK) |
| Release dialog / upload | none | spinner |
| Released-hist lookup | none (silent mid-form) | prefetch on Start/Restore **or** slot spinner |
| K-Means / Octants | spinner | spinner (OK) |

---

## 7. Baseline results (2026-11-14, automated)

Branch `v1-0-test_2` / `1.0.3.t2`, before busy-indicator + stale-UI fixes. Times are **CPU/Drive slices**; Streamlit widget/chart send adds more wall time in the browser.

### Grey-out ranking (top)

| s | progress | Operation |
|--:|----------|-----------|
| 8.73 | none | Drive: list projects (`A-used`) |
| 7.64 | none | Drive: list flows |
| 5.42 | none | Flow switch proxy (re-list flows) |
| 4.07 | none | Drive: download r09 (~1.8 MB) |
| 2.25 | spinner | Build OutByCondition |
| 2.06 | partial | Page switch → In (cold hist) |
| 2.03 | spinner | Build Out |
| 1.95 | partial | Page switch → Out |
| 1.78 | spinner | Build In |
| 1.05 | none | Drive: open store / token |
| 0.87 | none | hist_all cold (3 categories) |
| ~0.18 | partial | Page switch In (hist cached) / after Fit |
| ~0.00 | none | hist_all cached |

**Sum of measured slices:** ~40 s class (see script footer on re-run).

### Interpretation (then)

1. Longest silent greys were **Drive list projects / flows / download**, not Build.  
2. Hist cache worked: category switch cold ~2 s → warm ~0.2 s for measured work.  
3. Fit math itself was tiny; grey was the **full page redraw**.  
4. Required follow-up: busy indicators + stop auto project-list on every page load + warmup released-hist before Input widgets.

---

## 8. Pass / fail

**PASS** when:

1. Automated probe completes without error and prints ranking + coverage.  
2. Manual checks **M1–M9** show visible feedback (no silent ≥1 s grey on those paths).  
3. No duplicate Start-work widgets during flow load/start.  
4. Warm hist path remains clearly faster than cold in the probe.

**FAIL** when:

- Any M1–M9 path greys ≥ ~1 s with **no** spinner/status on the main view.  
- Choose a flow shows **duplicated** Start widgets while loading.  
- Start/Restore leaves the page stuck on Input widgets through Discount history with no spinner (~5 s class).  
- Warm hist / category switch regresses to cold-class times without explanation.

---

## 9. Related artifacts

| Artifact | Role |
|----------|------|
| `%TEMP%\pba_timing_greyout.py` | Automated timing + coverage probe (first implementation) |
| `%TEMP%\pba_scenario_a_used_in.py` | Full functional A-used/In scenario (not this test) |
| `tests/test_e2e.py` | Unit/regression suite |
| `ui/busy.py` | Shared spinner helpers (`busy`, `busy_in`) |
| `CHANGELOG.md` · `1.0.3.t2` | Busy indicators + stale-UI / warmup notes |

---

## 10. Re-run notes

1. Prefer a quiet network; Drive times dominate.  
2. Cold vs warm: clear Streamlit session (or new browser profile) for cold Drive/flow list.  
3. After code changes to spinners, re-run **§5.B** even if automated times look fine — Streamlit stale-element bugs are visual.  
4. Optionally check the timing script into `tests/timing_greyout.py` and update paths in this plan when that happens.
