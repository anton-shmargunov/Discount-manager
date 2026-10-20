"""
One-time Google sign-in that prints a [gdrive] secrets block.

Run from the project root:  python scripts/gdrive_oauth.py

Needs a Desktop OAuth client (client id + secret) from Google Cloud Console.
The refresh token is printed, never written to a file. Paste it into secrets.
See docs/gdrive-setup.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.persistence.gdrive import DRIVE_SCOPE, TOKEN_URI  # noqa: E402


def main() -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise SystemExit(
            "Install google-auth-oauthlib first:  pip install google-auth-oauthlib"
        )

    client_id = input("OAuth client id: ").strip()
    client_secret = input("OAuth client secret: ").strip()
    if not client_id or not client_secret:
        raise SystemExit("Client id and secret are required.")
    root_folder_id = input("Drive root folder id for PBA (optional now): ").strip()

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": TOKEN_URI,
                "redirect_uris": ["http://localhost"],
            }
        },
        scopes=[DRIVE_SCOPE],
    )
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )
    refresh = getattr(creds, "refresh_token", None)
    if not refresh:
        raise SystemExit(
            "Google did not return a refresh token. Revoke the app under "
            "Google Account → Security → Third-party access, then run this again."
        )

    print("\nAdd to secrets (local user-profile secrets.toml or Streamlit Cloud Secrets):\n")
    print("[gdrive]")
    print(f'client_id = "{client_id}"')
    print(f'client_secret = "{client_secret}"')
    print(f'refresh_token = "{refresh}"')
    print(f'root_folder_id = "{root_folder_id}"')
    print("\nFolder id: open the folder in Drive; the URL ends with /folders/<id>")


if __name__ == "__main__":
    main()
