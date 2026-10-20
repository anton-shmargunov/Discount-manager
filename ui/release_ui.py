"""
Week Discount Release and next week's released defaults.

A release set is the project plus the exports made from it, saved as one
revision and marked ``_rlsd``:

- category set: project, Week Discount and "Discount history. Current";
- ALL set: project, "Discount history. All" and the Week Discount file of
  every ticked category (the flow's defaults: four files for A-used, one
  Aggregated file for B-used and NEW).
"""

from __future__ import annotations

import io
import zipfile
from typing import Any, Iterable, Optional

import streamlit as st

from core.persistence.file_naming import (
    ALL_TAG,
    KIND_DISCOUNT_HIST,
    KIND_PROJECT,
    KIND_WEEK_DISCOUNT,
    build_name,
    foreign_flow_tags,
    is_week,
)
from core.persistence.flow_storage import (
    FlowStorage,
    SetItem,
    history_tag_preference,
    save_set,
)
from core.persistence.gdrive import DriveClientError
from ui.flow_ui import build_current_project_bytes, current_flow, known_flow_ids
from ui.gdrive_secrets import try_drive_store
from ui.product_bs_scope import (
    AGGREGATED_DISCOUNT_HIST_CATEGORY,
    PRODUCT_BS_CATEGORY_OPTIONS,
    PRODUCT_BS_INPUT_MODES,
)
from ui.week_discount_exports import (
    built_categories,
    category_week_discount_csv,
    discount_hist_all_csv,
)

_RELEASED_HIST_KEY = "_gdrive_released_hist"
_PROJECT_LIST_KEY = "_gdrive_proj_list"

SET_CATEGORY = "category"
SET_ALL = "all"


class NamedUpload(io.BytesIO):
    """In-memory file with a ``name``, accepted wherever an uploaded CSV is."""

    def __init__(self, name: str, data: bytes) -> None:
        super().__init__(data)
        self.name = name


def export_file_name(kind: str, tag: str, week: str, fallback: str) -> str:
    """Download name per the naming rule (no revision); ``fallback`` without a flow."""
    flow = current_flow()
    if flow is None or not is_week(week):
        return fallback
    return build_name(kind, flow.flow_id, tag, week)


def release_set_items(
    set_kind: str,
    category: str,
    week: str,
    parts: dict[str, Any],
    project_bytes: bytes,
) -> list[SetItem]:
    """Files of a release set; raises ``ValueError`` when a part is missing.

    ``parts`` holds ``next_week`` and, for the category set, ``week_discount`` and
    ``hist_current``; for the ALL set, ``hist_all`` and ``week_discounts``
    (category -> CSV bytes of the ticked categories).
    """
    next_week = parts.get("next_week")
    if not next_week:
        raise ValueError("Next week is unknown; discount history cannot be exported.")
    if set_kind == SET_ALL:
        if not parts.get("hist_all"):
            raise ValueError("'Discount history. All' is empty; build and generate the categories first.")
        items = [
            SetItem(KIND_PROJECT, ALL_TAG, week, project_bytes),
            SetItem(KIND_DISCOUNT_HIST, ALL_TAG, next_week, parts["hist_all"]),
        ]
        for wd_category, data in (parts.get("week_discounts") or {}).items():
            if not data:
                raise ValueError(f"Week Discount export of {wd_category} is empty.")
            items.append(SetItem(KIND_WEEK_DISCOUNT, wd_category, week, data))
        return items
    if not parts.get("week_discount"):
        raise ValueError("Week Discount export is empty.")
    if not parts.get("hist_current"):
        raise ValueError("'Discount history. Current' export is empty.")
    return [
        SetItem(KIND_PROJECT, category, week, project_bytes),
        SetItem(KIND_WEEK_DISCOUNT, category, week, parts["week_discount"]),
        SetItem(KIND_DISCOUNT_HIST, category, next_week, parts["hist_current"]),
    ]


def week_discount_choices(input_mode: str, flow_categories: Iterable[str]) -> list[str]:
    """Categories offered in the Release ALL "Week discount" expander, in app order."""
    if input_mode not in PRODUCT_BS_INPUT_MODES:
        return [AGGREGATED_DISCOUNT_HIST_CATEGORY]
    wanted = {str(item).lower() for item in flow_categories}
    options = [item for item in PRODUCT_BS_CATEGORY_OPTIONS if item != "none"]
    limited = [item for item in options if item.lower() in wanted]
    return limited or options


def week_discount_defaults(
    flow_defaults: Iterable[str],
    built: Iterable[str],
    current_category: str,
) -> list[str]:
    """Ticked by default: the flow's Week Discount categories that are built.

    Falls back to the current category when the flow lists none.
    """
    built_set = set(built)
    wanted = list(flow_defaults) or [current_category]
    return [item for item in wanted if item in built_set]


def release_zip_bytes(flow_id: str, items: Iterable[SetItem]) -> tuple[str, bytes]:
    """Local release set: one zip with ``_rlsd`` names and no revision number."""
    buffer = io.BytesIO()
    names: list[str] = []
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in items:
            name = build_name(item.kind, flow_id, item.tag, item.name_week, released=True)
            archive.writestr(name, item.data)
            names.append(name)
    project = next((name for name in names if name.endswith(".disc_proj")), names[0])
    return project.rsplit(".", 1)[0] + ".zip", buffer.getvalue()


def _clear_drive_caches() -> None:
    st.session_state.pop(_RELEASED_HIST_KEY, None)
    st.session_state.pop(_PROJECT_LIST_KEY, None)


def _all_set_parts(
    parts: dict[str, Any],
    week: str,
    category: str,
    input_mode: str,
    flow: Any,
) -> dict[str, Any]:
    """ALL-set parts: "Discount history. All" plus the Week Discount files ticked in the expander."""
    ss = st.session_state
    hist_all = discount_hist_all_csv(ss, input_mode, category, week)
    built = built_categories(ss, input_mode, week)
    choices = week_discount_choices(input_mode, flow.categories)
    defaults = week_discount_defaults(flow.week_discount_categories, built, category)
    ticked: list[str] = []
    with st.expander("Week discount", expanded=True):
        st.caption(
            "Week Discount files released with ALL. Defaults come from the flow; "
            "categories not built in this session are disabled."
        )
        for choice in choices:
            is_built = choice in built
            checked = st.checkbox(
                choice,
                value=choice in defaults,
                disabled=not is_built,
                key=f"_release_wd_{flow.flow_id}_{choice}",
                help=None if is_built else "Not built in this session for this week.",
            )
            if checked and is_built:
                ticked.append(choice)
    week_discounts: dict[str, Optional[bytes]] = {}
    for choice in ticked:
        if choice == category and parts.get("week_discount"):
            week_discounts[choice] = parts["week_discount"]
        else:
            week_discounts[choice] = category_week_discount_csv(ss, input_mode, choice, week)
    return {
        "next_week": hist_all.next_week if hist_all else parts.get("next_week"),
        "hist_all": hist_all.data if hist_all else None,
        "week_discounts": week_discounts,
    }


@st.dialog("Release")
def _release_dialog(parts: dict[str, Any], week: str, category: str, input_mode: str) -> None:
    flow = current_flow()
    if flow is None:
        st.error("Choose a flow first.")
        return
    set_kind = st.radio(
        "Release set",
        [SET_CATEGORY, SET_ALL],
        format_func=lambda item: (
            f"Category {category}: project, Week Discount, Discount history. Current"
            if item == SET_CATEGORY
            else "ALL: project, Discount history. All, Week Discount files"
        ),
        key="_release_set_kind",
    )
    set_parts = (
        _all_set_parts(parts, week, category, input_mode, flow)
        if set_kind == SET_ALL
        else parts
    )
    try:
        project_bytes, _ = build_current_project_bytes()
        items = release_set_items(set_kind, category, week, set_parts, project_bytes)
    except Exception as exc:
        st.error(str(exc))
        return
    st.markdown("**Files**")
    for item in items:
        st.text(build_name(item.kind, flow.flow_id, item.tag, item.name_week, released=True))
    store, drive_error = try_drive_store()
    if drive_error:
        st.warning(drive_error)
    if store is None:
        st.caption(
            "Google Drive is not configured: download the release set and file it yourself. "
            "Later weeks will not load it automatically."
        )
        zip_name, zip_bytes = release_zip_bytes(flow.flow_id, items)
        st.download_button(
            "Download release set (zip)",
            data=zip_bytes,
            file_name=zip_name,
            mime="application/zip",
            type="primary",
            width="stretch",
            key="_release_zip_download_btn",
        )
        return
    storage = FlowStorage(store, flow.flow_id)
    tag = ALL_TAG if set_kind == SET_ALL else category
    try:
        current = storage.released_in_week(week, KIND_PROJECT, tag)
        newer = storage.newer_weeks(week)
    except DriveClientError as exc:
        st.error(str(exc))
        return
    st.caption(
        f"Saved to {flow.flow_id}/{week}/ as a new revision and marked released. "
        + (
            f"Currently released: {current[0].name} (the mark moves to the new set)."
            if current
            else "Nothing is released yet for this tag and week."
        )
    )
    if newer:
        st.warning(
            f"This flow already has newer week folder(s): {', '.join(newer)}. "
            "Sessions there may have used the earlier release."
        )
    if st.button("Release to Drive", type="primary", width="stretch", key="_release_confirm_btn"):
        try:
            result = save_set(storage, week, items, release=True)
        except (DriveClientError, ValueError) as exc:
            st.error(str(exc))
            return
        _clear_drive_caches()
        st.success(f"Released r{result.revision:02d}: " + ", ".join(result.names))
        if result.unreleased:
            st.caption("Release mark removed from: " + ", ".join(result.unreleased))
        for warning in result.warnings:
            st.warning(warning)


def render_release_button(
    parts: dict[str, Any],
    selected_week: str,
    category: str,
    *,
    input_mode: str,
    edit_mode: bool,
    key_suffix: str,
) -> None:
    """The Release button under the Week Discount export row."""
    if current_flow() is None:
        return
    release_col, _ = st.columns([1, 3])
    if release_col.button(
        "Release…",
        key=f"_release_open_{key_suffix}_btn",
        disabled=edit_mode or not is_week(selected_week) or not parts.get("next_week"),
        type="primary",
        width="stretch",
        help=(
            "Save the project and its exports as one revision and mark it released (_rlsd). "
            "Released files are next week's defaults. To save work without releasing, "
            "use Project → Save."
        ),
    ):
        _release_dialog(parts, selected_week, category, input_mode)


def render_released_history_option(category: str, uploaded_files: Any) -> Optional[dict]:
    """Offer next week's default discount history; returns the chosen Drive file or ``None``."""
    flow = current_flow()
    if flow is None:
        return None
    store, drive_error = try_drive_store()
    if store is None or drive_error:
        return None
    cache = st.session_state.get(_RELEASED_HIST_KEY)
    if not isinstance(cache, dict):
        cache = {}
    cache_key = f"{flow.flow_id}::{category}"
    if cache_key not in cache:
        try:
            found = FlowStorage(store, flow.flow_id).find_released_history(
                history_tag_preference(category)
            )
        except DriveClientError as exc:
            st.caption(f"Released history lookup failed: {exc}")
            return None
        cache[cache_key] = (
            {
                "name": found.name,
                "folder_id": found.folder_id,
                "file_id": found.file.id,
                "week": found.parsed.week if found.parsed else "",
            }
            if found is not None
            else {}
        )
        st.session_state[_RELEASED_HIST_KEY] = cache
    row = cache.get(cache_key) or {}
    if not row:
        st.caption(f"No released discount history on Drive for flow {flow.flow_id} yet.")
        return None
    if uploaded_files:
        st.caption(f"Uploaded file(s) are used instead of the released history {row['name']}.")
        return None
    use = st.checkbox(
        f"Use released discount history from Drive: {row['name']} (week {row['week']})",
        value=True,
        key="fi_use_released_hist",
        help="Released (_rlsd) history of this flow, preferring ALL, then this category.",
    )
    return row if use else None


def load_released_history(row: dict) -> NamedUpload:
    store, drive_error = try_drive_store()
    if store is None:
        raise DriveClientError(drive_error or "Google Drive is not configured.")
    data = store.download_file(row["folder_id"], row["file_id"])
    return NamedUpload(row["name"], data)


def warn_foreign_flow_uploads(files: Iterable[Any]) -> None:
    """Warn when an uploaded file name carries another flow's tag."""
    flow = current_flow()
    if flow is None:
        return
    flow_ids = known_flow_ids()
    for upload in files:
        name = str(getattr(upload, "name", "") or "")
        if not name:
            continue
        others = foreign_flow_tags(name, flow.flow_id, flow_ids)
        if others:
            st.warning(
                f"'{name}' looks like a file of flow {', '.join(others)}, "
                f"but this session is flow {flow.flow_id}."
            )
