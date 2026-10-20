# PBA — Google Drive setup (flows, projects, releases)

The Cloud app writes to **one personal Google Drive** (the operator's account). PBA users sign in with the app login; they do not sign in with Google.

Keep browser **Download / Upload**. Drive is an extra Save / Release / Restore path.

---

## What you create in Drive

One dedicated **root folder**, for example `PBA Cloud`. Share nothing; the app uses the owner's account. The owner has full rights, so no extra Editor sharing is needed.

Open the folder in the browser. The URL looks like `https://drive.google.com/drive/folders/1AbC…`. The last part is the **folder id**.

Do not point the app at the root of My Drive.

The app creates everything below the root itself:

```
PBA Cloud/
  A-used/
    flow.json
    2026-40/
      input/              report and history the week was built from
      proj/               discount_project_A-used_ALL_2026-40_r03_rlsd.disc_proj
      week_discount/      week_discount_A-used_In_2026-40_r03_rlsd.csv, ...
      discount_history/   discount_hist_A-used_ALL_2026-41_r03_rlsd.csv
  B-used/
  NEW/
```

- A **flow** is a folder with a `flow.json`. New flows are created from the app's start screen.
- Every save is a new revision `rNN` (per flow and week folder). Nothing is overwritten.
- `_rlsd` marks the **released** file: one per flow, week, kind and tag. Released files are next week's defaults.
- Category tags in file names: `In`, `Out`, `ByCondition`, `ByMinPrice`, `Aggregated`, or `ALL`.

Old `proj` and `reports` folders from the earlier setup are no longer used; delete or keep them.

---

## One-time Google Cloud setup

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create or pick a project.
2. **APIs & Services → Library**: search **Google Drive API** and click **Enable**.
3. **Google Auth Platform** (left menu, or search "Google Auth Platform"):
   - **Branding**: app name and support e-mail (the wizard "Create branding" asks for these first).
   - **Audience**: User type **External** (or Internal on Workspace). While the app is in **Testing**, add your Google account under **Test users**.
   - **Clients → Create client → Desktop app**. Copy the client id and secret.
4. From the project folder:

   ```powershell
   pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
   python scripts/gdrive_oauth.py
   ```

   The script asks for the client id, secret and the **root folder id**. A browser window asks you to allow Drive access; sign in as the Drive owner. The script prints a `[gdrive]` block.

5. Paste that block into secrets (same places as `[app_users]`):
   - Local, if the project is on Google Drive: `C:\Users\<you>\.streamlit\secrets.toml`
   - Otherwise: `.streamlit/secrets.toml` (gitignored)
   - Streamlit Cloud: **Settings → Secrets**

```toml
[gdrive]
client_id = "….apps.googleusercontent.com"
client_secret = "…"
refresh_token = "…"
root_folder_id = "1AbC…"
```

6. Restart `streamlit run app.py --server.port 8501`. The start screen lists the flows found on Drive; the Project expander gets **Save to Drive** and **Restore from Drive**; Week Discount **Export** gets **Release…**.

---

## Corporate network: certificate errors (Windows)

Behind a proxy that inspects HTTPS, two things can fail with `CERTIFICATE_VERIFY_FAILED`:

- **pip install**: add `--trusted-host pypi.org --trusted-host files.pythonhosted.org`, or install `pip-system-certs` once.
- **The app** (`ssl.SSLCertVerificationError` from `httplib2`): handled by the app. On Windows it builds a CA bundle from `certifi` plus the Windows certificate store (`%TEMP%\pba_ca_bundle.pem`) and uses it for Drive calls. If it still fails, ask IT for the proxy's root certificate and install it into the Windows **Trusted Root Certification Authorities** store.

When Cursor or VS Code offers to create a virtual environment during install, either is fine; install the packages into the interpreter that runs `streamlit`.

---

## Secrets on Streamlit Cloud

Add the same `[gdrive]` block **before** people rely on Cloud save. If it is missing, Drive buttons stay hidden; download / upload still work, and Release downloads a zip.

The refresh token is equivalent to “this app may use my Drive.” Never commit it. Keep it out of a synced project folder (see [access-setup.md](access-setup.md) for the user-profile secrets file).

---

## Revoke or refresh

- Google Account → Security → Third-party access → remove the app, then run `scripts/gdrive_oauth.py` again.
- Unused refresh tokens can expire (in Testing mode after about 7 days); run the script again and replace `refresh_token`.

---

## What the app does

| Action | Drive |
|--------|-------|
| Start screen → Create flow | `<root>/<flow>/flow.json` |
| Project → Save → Save to Drive | new revision in `<flow>/<week>/proj/` and, with **discount_history** ticked, `<flow>/<week>/discount_history/`. Not released. |
| Project → Restore from Drive | lists the flow's `.disc_proj` files, released first |
| Week Discount → Export → Release… | project, discount history and Week Discount files as one revision, marked `_rlsd`; the mark moves off the previous release of the same tag |
| Next week: Discount history | offers the latest released history of the flow (ALL first) |

The app only touches folders it reached from the root folder, and never overwrites a file.
