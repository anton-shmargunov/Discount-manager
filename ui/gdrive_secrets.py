"""Read Google Drive config from Streamlit secrets. UI-only."""

from __future__ import annotations

from typing import Optional

import streamlit as st

from core.persistence.gdrive import (
    DriveClientError,
    DriveConfig,
    DriveStore,
    open_drive_store,
    parse_drive_config,
)

SECRETS_SECTION = "gdrive"


def load_drive_config() -> Optional[DriveConfig]:
    try:
        section = st.secrets.get(SECRETS_SECTION)
    except Exception:
        return None
    return parse_drive_config(section)


def get_drive_store() -> Optional[DriveStore]:
    config = load_drive_config()
    if config is None:
        return None
    cached = st.session_state.get("_gdrive_store")
    if isinstance(cached, DriveStore) and cached.config == config:
        return cached
    store = open_drive_store(config)
    st.session_state["_gdrive_store"] = store
    return store


def try_drive_store() -> tuple[Optional[DriveStore], Optional[str]]:
    """``(store, None)`` when ready; ``(None, None)`` if not configured; ``(None, error)`` on failure."""
    if load_drive_config() is None:
        return None, None
    try:
        return get_drive_store(), None
    except DriveClientError as exc:
        st.session_state.pop("_gdrive_store", None)
        return None, str(exc)
