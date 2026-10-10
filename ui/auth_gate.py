"""
Login / password gate for protected pages.

Users live in ``st.secrets`` (``.streamlit/secrets.toml`` locally, the app's
Secrets setting on Streamlit Cloud), with hashed passwords only::

    [app_users.anton]
    password_hash = "pbkdf2_sha256$600000$<salt>$<hash>"
    name = "Anton"          # optional display name

Generate hashes with ``python scripts/hash_password.py``. If no users are
configured, the page stays locked.
"""

from __future__ import annotations

import time
from typing import Any

import streamlit as st

from core.security.passwords import LoginThrottle, authenticate, normalize_username

AUTH_USER_KEY = "_auth_user"
AUTH_NAME_KEY = "_auth_name"
SECRETS_SECTION = "app_users"
FAILURE_DELAY_SECONDS = 1.0

_THROTTLE = LoginThrottle()


def _configured_users() -> dict[str, dict[str, Any]]:
    try:
        section = st.secrets.get(SECRETS_SECTION)
    except Exception:
        return {}
    if not section:
        return {}
    users: dict[str, dict[str, Any]] = {}
    for name, entry in dict(section).items():
        try:
            entry_dict = dict(entry)
        except (TypeError, ValueError):
            continue
        if entry_dict.get("password_hash"):
            users[normalize_username(name)] = entry_dict
    return users


def _render_login_form(users: dict[str, dict[str, Any]]) -> None:
    _, center, _ = st.columns([1, 1, 1])
    with center:
        st.subheader("Sign in")
        with st.form("_auth_login_form", clear_on_submit=True):
            username = st.text_input("Login", autocomplete="username")
            password = st.text_input(
                "Password", type="password", autocomplete="current-password"
            )
            submitted = st.form_submit_button(
                "Sign in", type="primary", width="stretch", key="_auth_sign_in_btn"
            )
        if not submitted:
            return
        locked = _THROTTLE.seconds_locked(username)
        if locked > 0:
            st.error(f"Too many failed attempts. Try again in {int(locked) + 1} s.")
            return
        user = authenticate(
            username,
            password,
            {name: str(entry["password_hash"]) for name, entry in users.items()},
        )
        if user is None:
            _THROTTLE.record_failure(username)
            time.sleep(FAILURE_DELAY_SECONDS)
            st.error("Incorrect login or password.")
            return
        _THROTTLE.record_success(user)
        st.session_state[AUTH_USER_KEY] = user
        st.session_state[AUTH_NAME_KEY] = str(users[user].get("name") or user)
        st.rerun()


def _render_signed_in_sidebar() -> None:
    with st.sidebar:
        st.caption(f"Signed in as **{st.session_state.get(AUTH_NAME_KEY, '')}**")
        if st.button("Log out", key="_auth_logout_btn", width="stretch"):
            st.session_state.clear()
            st.rerun()


def require_login() -> str:
    """Stop the page unless a configured user is signed in. Returns the username."""
    users = _configured_users()
    user = st.session_state.get(AUTH_USER_KEY)
    if user and user in users:
        _render_signed_in_sidebar()
        return str(user)
    st.session_state.pop(AUTH_USER_KEY, None)
    st.session_state.pop(AUTH_NAME_KEY, None)
    if not users:
        st.error(
            "Access is not configured. An administrator must add users under "
            f"`[{SECRETS_SECTION}]` in the app secrets."
        )
        st.stop()
    _render_login_form(users)
    st.stop()
    return ""
