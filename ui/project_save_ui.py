"""
Sidebar UI for saving / restoring PBA session projects (.disc_proj).
"""

from __future__ import annotations

import streamlit as st

from core.persistence.project_io import (
    PROJECT_EXTENSION,
    apply_project_payload,
    build_project_payload,
    ensure_project_filename,
    pack_project_bytes,
    unpack_project_bytes,
)


@st.dialog("Save project")
def _save_project_dialog() -> None:
    """Name the project file, then download a ``.disc_proj`` snapshot."""
    default_name = st.session_state.get("_project_save_name", "discount_project")
    name = st.text_input(
        "Project file name",
        value=str(default_name),
        help=f"File will be saved with extension {PROJECT_EXTENSION}",
        key="_project_dialog_name",
    )
    st.session_state["_project_save_name"] = name
    try:
        payload = build_project_payload(st.session_state)
        data = pack_project_bytes(payload)
    except Exception as exc:
        st.error(f"Could not build project file: {exc}")
        return

    filename = ensure_project_filename(name)
    built = sum(
        1
        for scope in (payload.get("scopes") or {}).values()
        if isinstance(scope, dict) and scope.get("analysis") is not None
    )
    st.caption(
        f"{len(payload.get('ui') or {})} UI setting(s) · "
        f"{built} built scope(s) · "
        f"{len(data):,} bytes"
    )
    st.download_button(
        f"Download {filename}",
        data=data,
        file_name=filename,
        mime="application/octet-stream",
        type="primary",
        use_container_width=True,
        key="_project_dialog_download",
        help="Downloads the current session as a .disc_proj file.",
    )


def render_sidebar_project_panel() -> None:
    """Render Project expander (save dialog + restore upload)."""
    with st.expander("Project", expanded=False):
        st.caption(
            "Snapshot analysis results, Week Discount edits, filters, and UI settings. "
            "Original CSV uploads are not re-attached; restored sessions rely on saved analysis."
        )
        if st.button(
            "Save…",
            use_container_width=True,
            key="_project_open_save_dialog",
            help="Open a dialog to name and download a .disc_proj file.",
        ):
            _save_project_dialog()

        st.divider()
        st.markdown("**Restore**")
        uploaded = st.file_uploader(
            "Open project file",
            type=["disc_proj"],
            key="_project_upload",
            help="Load a previously saved .disc_proj snapshot.",
        )
        restore_clicked = st.button(
            "Restore",
            use_container_width=True,
            type="primary",
            disabled=uploaded is None,
            key="_project_restore_btn",
            help="Replace the current session with the uploaded project.",
        )
        if restore_clicked and uploaded is not None:
            try:
                st.session_state["_project_bytes"] = uploaded.getvalue()
                st.session_state["_do_project_restore"] = True
                st.rerun()
            except Exception as exc:
                st.error(f"Could not read project file: {exc}")

        message = st.session_state.pop("_project_restore_message", None)
        if message:
            st.success(message)


def apply_pending_project_restore() -> None:
    """If a restore was requested last run, apply it before widgets render."""
    if not st.session_state.pop("_do_project_restore", False):
        return
    raw = st.session_state.pop("_project_bytes", None)
    if not raw:
        st.session_state["_project_restore_message"] = "Restore failed: empty file."
        return
    try:
        payload = unpack_project_bytes(raw)
        log_lines = apply_project_payload(st.session_state, payload)
        st.session_state.log_messages = log_lines
        st.session_state["_project_restore_message"] = (
            f"Restored project from {payload.get('saved_at', 'saved file')}."
        )
    except Exception as exc:
        st.session_state["_project_restore_message"] = f"Restore failed: {exc}"
