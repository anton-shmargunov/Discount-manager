# PBA — Access Setup (Login / Password)

How to give people access to the **Correlation Analysis** page.

---

## Why the page says "Access is not configured"

The page is locked until at least one user is configured. If no users exist, it stays closed rather than opening to anyone.

---

## How it works

1. The list of allowed users lives in the app's **secrets**, outside the code and outside git:
   - **Locally:** `.streamlit/secrets.toml` (gitignored, never pushed)
   - **Streamlit Cloud:** the app's **Settings → Secrets** box
2. Each user is stored as a login plus a **password hash**, never the password itself.
3. When someone opens Correlation Analysis, the page shows a **Login / Password** form. It hashes what they type and compares it with the stored hash. On a match, the page opens for that browser session.

---

## One-time setup (local)

1. In the project folder, run:

   ```powershell
   python scripts/hash_password.py
   ```

   Enter a login, an optional display name, and a password of at least 10 characters (typed twice, not shown on screen). It prints something like:

   ```toml
   [app_users.anton]
   password_hash = "pbkdf2_sha256$600000$9f2c...$4be1..."
   name = "Anton"
   ```

2. Create `.streamlit/secrets.toml` (next to `config.toml`) and paste that block into it. For more users, run the script again and add each block below the previous one. If the project folder is synced to the cloud, use the global file instead (see the next section).
3. Refresh the browser. Streamlit usually picks up the new secrets file automatically; if the message stays, restart:

   ```powershell
   streamlit run app.py --server.port 8501
   ```

   You should then see the **Sign in** form.

### If the project folder is synced (Google Drive, OneDrive, …)

Google Drive for desktop can't exclude a single file or subfolder inside a synced folder (its only ignore options are RAW photos and screenshots). A `.streamlit/secrets.toml` inside the project would be uploaded with everything else.

Keep the secrets file **outside the synced folder** instead. Streamlit also reads a global secrets file in your user profile and merges it with the project one:

```
C:\Users\<you>\.streamlit\secrets.toml
```

1. Create the folder `C:\Users\<you>\.streamlit\` if it doesn't exist.
2. Put the `[app_users]` block(s) there instead of in the project's `.streamlit/secrets.toml`. If you already created the project copy, move it.
3. Restart `streamlit run app.py --server.port 8501` and check that you can sign in.
4. If a project copy was synced before, delete it from the Google Drive **trash** too (Drive keeps deleted files for 30 days), and check its version history on drive.google.com.

The global file applies to every Streamlit app on this PC. That's harmless here: other apps ignore the `[app_users]` section.

Other workarounds, not recommended:
- **`secrets.files` in `config.toml`:** points Streamlit to any path, but puts a machine-specific path into a file that goes to git and Cloud.
- **Symlink / junction:** Drive's handling of links isn't documented, so don't rely on it for secrets.

Risk if the file does get synced: it holds only password hashes, not passwords. Still, anyone with the file could try to guess weak passwords offline, so use long passwords. Keeping the file out of Drive matters more if it later holds real API keys, or if the Drive folder is shared.

---

## Streamlit Cloud

Before pushing the login change, open the app's **Settings → Secrets** and paste the same block(s). Otherwise the deployed page shows "Access is not configured". You can reuse the local hashes or create separate Cloud users.

---

## Managing users

| Task | How |
|------|-----|
| Add someone | Run the script and add their block |
| Change a password | Run the script and replace that user's `password_hash` line |
| Remove someone | Delete their block. They are signed out on their next action |

---

## What users should know

- After **5 wrong attempts**, that login is locked for **5 minutes**.
- Refreshing the page or opening a new tab asks you to sign in again. Save a `.disc_proj` first if you need your work.
- **Log out** (sidebar) ends the session and clears unsaved work.
- Sign-in is never stored in `.disc_proj` files.
