"""
Sidebar UI for saving / restoring PBA session projects (.disc_proj).
"""

from __future__ import annotations

from typing import Optional

import streamlit as st

from core.flows import Flow, check_project_flow
from core.persistence.file_naming import (
    ALL_TAG,
    KIND_DISCOUNT_HIST,
    KIND_PROJECT,
    build_name,
    is_week,
)
from core.persistence.flow_storage import FlowStorage, SetItem, save_set
from core.persistence.gdrive import DriveClientError, DriveStore
from core.persistence.project_io import (
    PROJECT_EXTENSION,
    apply_project_payload,
    ensure_project_filename,
    unpack_project_bytes,
)
from ui.flow_ui import (
    build_current_project_bytes,
    current_category_tag,
    current_flow,
    current_scope_week,
    default_project_name,
    known_flow_ids,
)
from ui.gdrive_secrets import try_drive_store
from ui.week_discount_exports import (
    HistExport,
    discount_hist_all_csv,
    discount_hist_category_csv,
)

_PROJECT_LIST_KEY = "_gdrive_proj_list"


def _project_caption(payload: object, data: bytes) -> str:
    built = sum(
        1
        for scope in (payload.get("scopes") or {}).values()
        if isinstance(scope, dict) and scope.get("analysis") is not None
    )
    return (
        f"{len(payload.get('ui') or {})} UI setting(s) · "
        f"{built} built scope(s) · "
        f"{len(data):,} bytes"
    )


def _clear_project_list() -> None:
    st.session_state.pop(_PROJECT_LIST_KEY, None)


def project_save_items(
    tag: str,
    week: str,
    project_bytes: bytes,
    history: Optional[HistExport],
) -> list[SetItem]:
    """Files of a Project → Save: the project, plus the discount history when included."""
    items = [SetItem(KIND_PROJECT, tag, week, project_bytes)]
    if history is not None:
        items.append(SetItem(KIND_DISCOUNT_HIST, tag, history.next_week, history.data))
    return items


def _session_history(tag: str, week: str) -> Optional[HistExport]:
    ss = st.session_state
    mode = str(ss.get("input_mode") or "")
    category = current_category_tag()
    if tag == ALL_TAG:
        return discount_hist_all_csv(ss, mode, category, week)
    return discount_hist_category_csv(ss, mode, category, week)


@st.dialog("Save project")
def _save_project_dialog() -> None:
    """Name the project file, then download and optionally save to Drive."""
    category = current_category_tag()
    tag = st.selectbox(
        "Tag",
        [ALL_TAG, category],
        format_func=lambda item: (
            f"{item} (all built categories)" if item == ALL_TAG else f"{item} (current category)"
        ),
        key="_project_dialog_tag",
        help="Part of the file names: ALL, or the current Product BS category.",
    )
    name = st.text_input(
        "Project file name",
        value=default_project_name(tag),
        help=f"File will be saved with extension {PROJECT_EXTENSION}",
        key=f"_project_dialog_name_{tag}",
    )
    include_history = st.checkbox(
        "discount_history",
        value=True,
        key="_project_dialog_hist",
        help=(
            "Also save the discount history for next week's analysis: "
            "'Discount history. All' for ALL, 'Discount history. Current' for a category."
        ),
    )
    try:
        data, payload = build_current_project_bytes()
    except Exception as exc:
        st.error(f"Could not build project file: {exc}")
        return

    week = current_scope_week()
    history: Optional[HistExport] = None
    if include_history:
        history = _session_history(tag, week) if is_week(week) else None
        if history is None:
            st.caption(
                "Discount history is not available yet: build the analysis and "
                "generate or edit Week Discount first. Only the project is saved."
            )

    filename = ensure_project_filename(name)
    st.caption(_project_caption(payload, data))
    st.download_button(
        f"Download {filename}",
        data=data,
        file_name=filename,
        mime="application/octet-stream",
        type="primary",
        width="stretch",
        key="_project_dialog_download_btn",
        help="Downloads the current session as a .disc_proj file.",
    )
    flow = current_flow()
    if history is not None:
        hist_name = (
            build_name(KIND_DISCOUNT_HIST, flow.flow_id, tag, history.next_week)
            if flow is not None
            else f"discount_hist_{history.next_week}.csv"
        )
        st.download_button(
            f"Download {hist_name}",
            data=history.data,
            file_name=hist_name,
            mime="text/csv",
            width="stretch",
            key="_project_dialog_hist_download_btn",
            help="Discount history in the input format, for next week's analysis.",
        )
    store, drive_error = try_drive_store()
    if drive_error:
        st.warning(drive_error)
        return
    if store is None or flow is None:
        return
    if not is_week(week):
        st.caption("Build the analysis first; Drive saves go into the week folder.")
        return
    if st.button(
        f"Save to Drive as a new revision ({flow.flow_id}/{week})",
        width="stretch",
        key="_project_dialog_save_drive_btn",
        help=(
            "Project to proj/ and discount history to discount_history/, one revision. "
            "Never overwrites. Use Week Discount → Release to mark the released set."
        ),
    ):
        try:
            result = save_set(
                FlowStorage(store, flow.flow_id),
                week,
                project_save_items(tag, week, data, history),
            )
            _clear_project_list()
            st.success("Saved to Drive: " + ", ".join(result.names))
            for warning in result.warnings:
                st.warning(warning)
        except (DriveClientError, ValueError) as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Could not save to Drive: {exc}")


def _drive_project_files(store: DriveStore, flow: Flow) -> list[dict]:
    cached = st.session_state.get(_PROJECT_LIST_KEY)
    if isinstance(cached, dict) and cached.get("flow_id") == flow.flow_id:
        return cached["files"]
    files = FlowStorage(store, flow.flow_id).list_projects()
    rows = [
        {
            "id": item.file.id,
            "folder_id": item.folder_id,
            "name": item.name,
            "week": item.week_folder,
            "released": item.released,
            "tag": item.parsed.tag if item.parsed else "",
        }
        for item in files
    ]
    st.session_state[_PROJECT_LIST_KEY] = {"flow_id": flow.flow_id, "files": rows}
    return rows


def _default_project_index(rows: list[dict], category: str) -> int:
    for wanted in (category, ALL_TAG):
        for index, row in enumerate(rows):
            if row["released"] and row["tag"] == wanted:
                return index
    for index, row in enumerate(rows):
        if row["released"]:
            return index
    return 0


def _render_drive_restore(store: DriveStore, flow: Flow) -> None:
    st.markdown("**Restore from Drive**")
    if st.button("Refresh list", key="_project_drive_refresh_btn", width="stretch"):
        _clear_project_list()
        st.rerun()
    try:
        rows = _drive_project_files(store, flow)
    except DriveClientError as exc:
        st.error(str(exc))
        return
    if not rows:
        st.caption(f"No .disc_proj files in Drive for flow {flow.flow_id} yet.")
        return
    by_id = {row["id"]: row for row in rows}
    ids = [row["id"] for row in rows]
    choice = st.selectbox(
        "Cloud project",
        ids,
        index=_default_project_index(rows, current_category_tag()),
        format_func=lambda file_id: (
            f"{by_id[file_id]['week']} · {by_id[file_id]['name']}"
            + ("  [released]" if by_id[file_id]["released"] else "")
        ),
        key=f"_project_drive_choice_{flow.flow_id}",
        help="Latest weeks of this flow; released projects are listed first in each week.",
    )
    if st.button(
        "Restore from Drive",
        width="stretch",
        type="primary",
        disabled=not choice,
        key="_project_restore_drive_btn",
        help="Replace the current session with the selected Drive project.",
    ):
        row = by_id[choice]
        try:
            raw = store.download_file(row["folder_id"], str(choice))
            st.session_state["_project_bytes"] = raw
            st.session_state["_project_restore_name"] = row["name"]
            st.session_state["_do_project_restore"] = True
            st.rerun()
        except Exception as exc:
            st.error(f"Could not read Drive project: {exc}")


def render_sidebar_project_panel() -> None:
    """Render Project expander (save dialog + restore upload + Drive)."""
    with st.expander("Project", expanded=False):
        st.caption(
            "Snapshot analysis results, Week Discount edits, filters, and UI settings. "
            "Original CSV uploads are not re-attached; restored sessions rely on saved analysis."
        )
        if st.button(
            "Save…",
            width="stretch",
            key="_project_open_save_dialog_btn",
            help=(
                "Open a dialog to download or save the .disc_proj file "
                "and the discount history to Drive."
            ),
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
            width="stretch",
            type="primary",
            disabled=uploaded is None,
            key="_project_restore_btn",
            help="Replace the current session with the uploaded project.",
        )
        if restore_clicked and uploaded is not None:
            try:
                st.session_state["_project_bytes"] = uploaded.getvalue()
                st.session_state["_project_restore_name"] = str(uploaded.name or "")
                st.session_state["_do_project_restore"] = True
                st.rerun()
            except Exception as exc:
                st.error(f"Could not read project file: {exc}")

        flow = current_flow()
        store, drive_error = try_drive_store()
        if drive_error:
            st.warning(drive_error)
        elif store is not None and flow is not None:
            st.divider()
            _render_drive_restore(store, flow)
        elif store is None:
            st.caption("Google Drive is not configured. Download and upload still work.")

        message = st.session_state.pop("_project_restore_message", None)
        if message:
            if str(message).startswith("Restore failed"):
                st.error(message)
            else:
                st.success(message)


def apply_pending_project_restore() -> None:
    """If a restore was requested last run, apply it before widgets render."""
    if not st.session_state.pop("_do_project_restore", False):
        return
    raw = st.session_state.pop("_project_bytes", None)
    filename = str(st.session_state.pop("_project_restore_name", "") or "")
    if not raw:
        st.session_state["_project_restore_message"] = "Restore failed: empty file."
        return
    try:
        payload = unpack_project_bytes(raw)
        flow = current_flow()
        warning: Optional[str] = None
        if flow is not None:
            warning = check_project_flow(
                payload,
                flow.flow_id,
                filename=filename,
                known_flow_ids=known_flow_ids(),
            )
        log_lines = apply_project_payload(st.session_state, payload)
        if warning:
            log_lines.append(warning)
        st.session_state.log_messages = log_lines
        st.session_state["_project_restore_message"] = (
            f"Restored project from {payload.get('saved_at', 'saved file')}."
            + (f" {warning}" if warning else "")
        )
    except Exception as exc:
        st.session_state["_project_restore_message"] = f"Restore failed: {exc}"
