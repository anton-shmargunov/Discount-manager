"""
Project session persistence (.disc_proj).

Saves and restores Streamlit session scopes, analysis results, and UI settings
as a gzip-compressed pickle with a short magic header.
"""

from __future__ import annotations

import gzip
import pickle
from datetime import datetime, timezone
from typing import Any

PROJECT_FORMAT = "pba_disc_proj"
PROJECT_FORMAT_VERSION = 1
PROJECT_EXTENSION = ".disc_proj"
PROJECT_MAGIC = b"PBA1DISC"

# Keys we manage separately or that must not be pickled from session_state.
_SKIP_SESSION_KEYS = frozenset({
    "_pbs_scopes",
    "_project_bytes",
    "_do_project_restore",
    "_project_restore_message",
    "_project_save_name",
})

# Restored from payload["scopes"] — never delete during widget-key cleanup.
_RESTORE_MANAGED_KEYS = frozenset({"_pbs_scopes"})

_SKIP_KEY_PREFIXES = (
    "fu_",               # file uploaders (binary handles)
    "_project_",         # save/restore panel widgets (buttons disallowed)
    "FormSubmitter",
    "UploadFile",
)

# Streamlit forbids assigning session_state for button / download_button keys.
# Fragments match keys used across pages/ and ui/.
_WRITE_DISALLOWED_KEY_FRAGMENTS = (
    "generate_discount",
    "generate_prom",
    "manual_apply",
    "manual_cancel",
    "manual_edit_btn",
    "run_model",
    "run_sumup_margin",
    "btn_cost",
    "btn_plane",
    "btn_line",
    "week_discount_export",
    "week_discount_hist_export",
    "week_detail_export",
    "export_total",
    "tb_raw",
    "open_save_dialog",
    "restore_btn",
    "dialog_download",
)


def ensure_project_filename(name: str) -> str:
    """Return a safe filename ending with ``.disc_proj``."""
    text = str(name or "").strip() or "project"
    for sep in ("/", "\\"):
        text = text.replace(sep, "_")
    text = text.rstrip(". ")
    if not text:
        text = "project"
    if not text.lower().endswith(PROJECT_EXTENSION):
        text = f"{text}{PROJECT_EXTENSION}"
    return text


def _is_write_disallowed_widget_key(key: str) -> bool:
    """True for Streamlit button/download_button keys that forbid session assignment."""
    if key in _SKIP_SESSION_KEYS:
        return True
    if any(key.startswith(prefix) for prefix in _SKIP_KEY_PREFIXES):
        return True
    # Auto-generated or explicit button keys often include "::btn_" / "_btn_".
    if "::btn_" in key or key.startswith("btn_") or "_btn_" in key:
        return True
    if key.endswith("_btn"):
        return True
    lowered = key.lower()
    return any(fragment in lowered for fragment in _WRITE_DISALLOWED_KEY_FRAGMENTS)


def _can_pickle(value: object) -> bool:
    try:
        pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        return True
    except Exception:
        return False


def collect_ui_session_state(session_state: Any) -> dict[str, Any]:
    """Copy picklable UI/widget values from Streamlit session state."""
    ui: dict[str, Any] = {}
    for key in list(session_state.keys()):
        key_str = str(key)
        if _is_write_disallowed_widget_key(key_str):
            continue
        try:
            value = session_state[key]
        except Exception:
            continue
        # Uploaded files / Streamlit internal widgets often fail pickling.
        type_name = type(value).__name__
        if type_name in {"UploadedFile", "PagedUploadFile", "DeltaGenerator"}:
            continue
        if not _can_pickle(value):
            continue
        ui[key_str] = value
    return ui


def build_project_payload(session_state: Any) -> dict[str, Any]:
    """Assemble a full project snapshot from the current session."""
    scopes = getattr(session_state, "_pbs_scopes", None)
    if scopes is None and "_pbs_scopes" in session_state:
        scopes = session_state["_pbs_scopes"]
    if not isinstance(scopes, dict):
        scopes = {}

    return {
        "format": PROJECT_FORMAT,
        "version": PROJECT_FORMAT_VERSION,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "ui": collect_ui_session_state(session_state),
        "scopes": scopes,
        "log_messages": list(getattr(session_state, "log_messages", ["Ready."])),
    }


def pack_project_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize payload to ``.disc_proj`` bytes (magic + gzip pickle)."""
    raw = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    return PROJECT_MAGIC + gzip.compress(raw, compresslevel=6)


def unpack_project_bytes(data: bytes) -> dict[str, Any]:
    """Deserialize a ``.disc_proj`` file into a payload dict."""
    if not data:
        raise ValueError("Empty project file.")
    if data.startswith(PROJECT_MAGIC):
        body = data[len(PROJECT_MAGIC):]
    else:
        body = data
    try:
        raw = gzip.decompress(body)
    except OSError as exc:
        raise ValueError("Project file is not a valid .disc_proj archive.") from exc
    try:
        payload = pickle.loads(raw)
    except Exception as exc:
        raise ValueError(
            "Project file could not be read (corrupt or incompatible)."
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("Project file payload is invalid.")
    if payload.get("format") != PROJECT_FORMAT:
        raise ValueError(
            f"Unsupported project format {payload.get('format')!r}; "
            f"expected {PROJECT_FORMAT!r}."
        )
    version = int(payload.get("version", 0))
    if version < 1 or version > PROJECT_FORMAT_VERSION:
        raise ValueError(
            f"Unsupported project version {version}; "
            f"this app supports 1..{PROJECT_FORMAT_VERSION}."
        )
    return payload


def _clear_write_disallowed_keys(session_state: Any) -> None:
    """Drop button/download keys so Streamlit can recreate those widgets."""
    for key in list(session_state.keys()):
        key_str = str(key)
        if key_str in _RESTORE_MANAGED_KEYS:
            continue
        if _is_write_disallowed_widget_key(key_str):
            try:
                del session_state[key]
            except Exception:
                pass


def apply_project_payload(session_state: Any, payload: dict[str, Any]) -> list[str]:
    """
    Restore payload into ``session_state``.

    Returns a short status message list for the log.
    """
    ui = payload.get("ui") or {}
    scopes = payload.get("scopes") or {}
    log_messages = payload.get("log_messages")

    if not isinstance(ui, dict) or not isinstance(scopes, dict):
        raise ValueError("Project payload is missing ui/scopes.")

    # Remove forbidden widget keys before restore (also cleans older .disc_proj files).
    _clear_write_disallowed_keys(session_state)

    session_state._pbs_scopes = scopes

    restored_keys = 0
    for key, value in ui.items():
        key_str = str(key)
        if _is_write_disallowed_widget_key(key_str):
            continue
        session_state[key_str] = value
        restored_keys += 1

    # Ensure project-panel button keys are not left behind after restore.
    _clear_write_disallowed_keys(session_state)

    if isinstance(log_messages, list) and log_messages:
        session_state.log_messages = [str(line) for line in log_messages]
    else:
        session_state.log_messages = ["Ready."]

    built = sum(
        1
        for scope in scopes.values()
        if isinstance(scope, dict) and scope.get("analysis") is not None
    )
    saved_at = str(payload.get("saved_at", ""))
    return [
        f"Project restored ({saved_at or 'unknown time'}).",
        f"UI keys restored: {restored_keys}.",
        f"Built scopes restored: {built}.",
    ]
