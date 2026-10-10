"""
Print a secrets.toml entry for one app user.

Run from the project root:  python scripts/hash_password.py
The password is read without echo and is never written anywhere.
"""

import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.security.passwords import hash_password, normalize_username  # noqa: E402


def main() -> None:
    username = normalize_username(input("Login: "))
    if not username or not username.replace("_", "").replace("-", "").isalnum():
        raise SystemExit("Login must use letters, digits, '_' or '-'.")
    name = input("Display name (optional): ").strip()
    password = getpass.getpass("Password: ")
    if len(password) < 10:
        raise SystemExit("Use at least 10 characters.")
    if getpass.getpass("Repeat password: ") != password:
        raise SystemExit("Passwords do not match.")

    print("\nAdd to .streamlit/secrets.toml (local) or the app's Secrets on Streamlit Cloud:\n")
    print(f"[app_users.{username}]")
    print(f'password_hash = "{hash_password(password)}"')
    if name:
        print(f"name = {json.dumps(name)}")


if __name__ == "__main__":
    main()
