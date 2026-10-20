"""
Flow choice for a session: start screen, sidebar badge, header caption.

One flow per browser session. Switching flow clears the session after a confirm.
"""

from __future__ import annotations

from typing import Any, Optional

import streamlit as st

from core.flows import (
    SOURCE_SESSION,
    Flow,
    create_flow,
    list_drive_flows,
    load_seed_flows,
    merge_flows,
    stamp_project_flow,
    validate_flow_id,
    write_flow_meta,
)
from core.persistence.file_naming import KIND_PROJECT, build_name
from core.persistence.gdrive import DriveClientError, DriveStore
from core.persistence.project_io import build_project_payload, pack_project_bytes
from ui.gdrive_secrets import try_drive_store
from ui.product_bs_scope import (
    AGGREGATED_DISCOUNT_HIST_CATEGORY,
    PRODUCT_BS_CATEGORY_OPTIONS,
    PRODUCT_BS_INPUT_MODES,
    PRODUCT_BS_ON_DATE_MODE,
    product_bs_scope_key,
)

FLOW_ID_KEY = "_flow_id"
FLOW_INFO_KEY = "_flow_info"
FLOW_LIST_KEY = "_flow_list_cache"
SESSION_FLOWS_KEY = "_flow_session_flows"
_KEEP_ON_SWITCH_PREFIXES = ("_auth_",)
_KEEP_ON_SWITCH_KEYS = frozenset({"_gdrive_store", FLOW_LIST_KEY, SESSION_FLOWS_KEY})


def current_flow() -> Optional[Flow]:
    info = st.session_state.get(FLOW_INFO_KEY)
    if not st.session_state.get(FLOW_ID_KEY) or not isinstance(info, dict):
        return None
    return Flow.from_meta(info)


def known_flow_ids() -> list[str]:
    cached = st.session_state.get(FLOW_LIST_KEY) or []
    ids = [str(item.get("flow_id")) for item in cached if isinstance(item, dict)]
    return ids or [flow.flow_id for flow in load_seed_flows()]


def _set_current_flow(flow: Flow) -> None:
    st.session_state[FLOW_ID_KEY] = flow.flow_id
    st.session_state[FLOW_INFO_KEY] = flow.to_session()


def _session_flows() -> list[Flow]:
    return [
        Flow.from_meta(item, source=SOURCE_SESSION)
        for item in st.session_state.get(SESSION_FLOWS_KEY) or []
        if isinstance(item, dict)
    ]


def _load_flows(store: Optional[DriveStore]) -> list[Flow]:
    cached = st.session_state.get(FLOW_LIST_KEY)
    if isinstance(cached, list):
        return [Flow.from_meta(item) for item in cached if isinstance(item, dict)]
    seed = load_seed_flows()
    drive_flows: list[Flow] = []
    if store is not None:
        drive_flows = list_drive_flows(store, seed)
    flows = merge_flows(seed, drive_flows + _session_flows())
    st.session_state[FLOW_LIST_KEY] = [flow.to_session() for flow in flows]
    return flows


def _clear_flow_list() -> None:
    st.session_state.pop(FLOW_LIST_KEY, None)


def clear_session_for_flow_switch(session_state: Any) -> None:
    """Drop everything except login, the Drive client and flow lists."""
    for key in list(session_state.keys()):
        key_str = str(key)
        if key_str in _KEEP_ON_SWITCH_KEYS or key_str.startswith(_KEEP_ON_SWITCH_PREFIXES):
            continue
        try:
            del session_state[key]
        except Exception:
            pass


def current_category_tag(session_state: Any = None) -> str:
    """Product BS category of the active scope (``Aggregated`` for the plain report mode)."""
    ss = session_state if session_state is not None else st.session_state
    mode = ss.get("input_mode") or PRODUCT_BS_ON_DATE_MODE
    if mode in PRODUCT_BS_INPUT_MODES:
        return str(ss.get("fi_product_bs_category") or PRODUCT_BS_CATEGORY_OPTIONS[0])
    return AGGREGATED_DISCOUNT_HIST_CATEGORY


def current_scope_week(session_state: Any = None) -> str:
    """Selected week of the active scope, else its latest analysed week, else ``''``."""
    ss = session_state if session_state is not None else st.session_state
    mode = ss.get("input_mode") or PRODUCT_BS_ON_DATE_MODE
    category = ss.get("fi_product_bs_category") or PRODUCT_BS_CATEGORY_OPTIONS[0]
    scopes = ss.get("_pbs_scopes") or {}
    scope = scopes.get(product_bs_scope_key(mode, category)) if isinstance(scopes, dict) else None
    if not isinstance(scope, dict):
        return ""
    if scope.get("selected_week"):
        return str(scope["selected_week"])
    weeks = getattr(scope.get("analysis"), "all_weeks", None) or []
    return str(max(weeks)) if weeks else ""


def build_current_project_bytes() -> tuple[bytes, dict]:
    """Project payload of this session, stamped with the current flow."""
    payload = build_project_payload(st.session_state)
    flow = current_flow()
    if flow is not None:
        stamp_project_flow(payload, flow.flow_id)
    return pack_project_bytes(payload), payload


def default_project_name(tag: Optional[str] = None) -> str:
    flow = current_flow()
    week = current_scope_week()
    if flow is None or not week:
        return "discount_project"
    name = build_name(KIND_PROJECT, flow.flow_id, tag or current_category_tag(), week)
    return name[: -len(".disc_proj")]


def render_flow_caption() -> None:
    flow = current_flow()
    if flow is not None:
        st.caption(f"Flow: **{flow.display}**")


@st.dialog("Switch flow")
def _switch_flow_dialog() -> None:
    st.write(
        "Switching flow clears this session: analysis, Week Discount edits and the Planner. "
        "Download the project first if you still need it."
    )
    try:
        data, _ = build_current_project_bytes()
        st.download_button(
            "Download project first",
            data=data,
            file_name=default_project_name() + ".disc_proj",
            mime="application/octet-stream",
            width="stretch",
            key="_flow_switch_download_btn",
        )
    except Exception as exc:
        st.caption(f"Project could not be built: {exc}")
    confirm, cancel = st.columns(2)
    if confirm.button("Switch flow", type="primary", width="stretch", key="_flow_switch_confirm_btn"):
        clear_session_for_flow_switch(st.session_state)
        st.rerun()
    if cancel.button("Cancel", width="stretch", key="_flow_switch_cancel_btn"):
        st.rerun()


def _render_flow_sidebar(flow: Flow) -> None:
    with st.sidebar:
        st.markdown(f"**Flow:** {flow.display}")
        if flow.source == SOURCE_SESSION:
            st.caption("Session-only flow (Drive not configured).")
        if st.button("Switch flow…", width="stretch", key="_flow_switch_btn"):
            _switch_flow_dialog()


@st.dialog("Create flow")
def _create_flow_dialog(
    flow_id: str,
    label: str,
    categories: list[str],
    week_discount_categories: list[str],
    username: str,
) -> None:
    store, drive_error = try_drive_store()
    if drive_error:
        st.error(drive_error)
        return
    if store is not None:
        st.write(f"Folder **{flow_id}/** with `flow.json` will be created in the PBA Drive folder.")
    else:
        st.write(f"Flow **{flow_id}** will exist for this session only (Drive is not configured).")
    st.write(f"Label: **{label or flow_id}** · Categories: {', '.join(categories) or 'all'}")
    st.write(
        "Week Discount files on release: "
        + (", ".join(week_discount_categories) or "current category")
    )
    st.caption("A flow cannot be deleted or renamed from the app.")
    confirm, cancel = st.columns(2)
    if confirm.button("Create", type="primary", width="stretch", key="_flow_create_confirm_btn"):
        try:
            flow = create_flow(
                store,
                flow_id,
                label,
                categories,
                week_discount_categories=week_discount_categories,
                existing_ids=known_flow_ids(),
                created_by=username,
            )
        except (ValueError, DriveClientError) as exc:
            st.error(str(exc))
            return
        if store is None:
            session_flows = list(st.session_state.get(SESSION_FLOWS_KEY) or [])
            session_flows.append(flow.to_session())
            st.session_state[SESSION_FLOWS_KEY] = session_flows
        elif store.warnings:
            st.session_state["_flow_notice"] = " ".join(store.warnings)
            store.warnings.clear()
        _clear_flow_list()
        _set_current_flow(flow)
        st.rerun()
    if cancel.button("Cancel", width="stretch", key="_flow_create_cancel_btn"):
        st.rerun()


def _flow_option_label(flow: Flow) -> str:
    if flow.last_week:
        return f"{flow.display} — last week {flow.last_week}"
    return flow.display


def _start_flow(flow: Flow, store: Optional[DriveStore], username: str) -> None:
    if store is not None and not flow.folder_id:
        folder_id = write_flow_meta(store, flow, created_by=username)
        flow = Flow.from_meta({**flow.to_session(), "folder_id": folder_id, "source": "drive"})
        _clear_flow_list()
    _set_current_flow(flow)
    st.rerun()


def _render_start_screen(username: str) -> None:
    st.title("Choose a flow")
    st.caption(
        "A flow is an independent product group with its own report, discount history, "
        "projects and Week Discount files. Pick one to start; switch later from the sidebar."
    )
    store, drive_error = try_drive_store()
    if drive_error:
        st.warning(drive_error)
    elif store is None:
        st.info(
            "Google Drive is not configured. Flows come from `configs/flows.csv`; "
            "a flow created here lasts for this session only."
        )
    try:
        flows = _load_flows(store)
    except DriveClientError as exc:
        st.error(f"Could not read flows from Drive: {exc}")
        flows = merge_flows(load_seed_flows(), _session_flows())
    if store is not None and store.warnings:
        st.warning(" ".join(store.warnings))
        store.warnings.clear()

    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.subheader("Start work")
        if flows:
            by_id = {flow.flow_id: flow for flow in flows}
            choice = st.selectbox(
                "Flow",
                list(by_id),
                format_func=lambda flow_id: _flow_option_label(by_id[flow_id]),
                key="_flow_start_choice",
            )
            start_col, refresh_col = st.columns([2, 1])
            if start_col.button("Start", type="primary", width="stretch", key="_flow_start_btn"):
                try:
                    _start_flow(by_id[choice], store, username)
                except DriveClientError as exc:
                    st.error(str(exc))
            if refresh_col.button("Refresh list", width="stretch", key="_flow_refresh_btn"):
                _clear_flow_list()
                st.rerun()
        else:
            st.caption("No flows yet. Create the first one below.")

        with st.expander("Create new flow", expanded=not flows):
            new_id = st.text_input(
                "Flow id",
                key="_flow_new_id",
                placeholder="e.g. C-used",
                help=(
                    "Folder name and file tag. Starts with a letter; letters, digits and '-'; "
                    "2–20 characters. It cannot be changed later."
                ),
            ).strip()
            id_error = validate_flow_id(new_id, [flow.flow_id for flow in flows]) if new_id else None
            if id_error:
                st.error(id_error)
            new_label = st.text_input("Label", key="_flow_new_label", placeholder="e.g. Used C")
            new_categories = st.multiselect(
                "Product BS categories",
                PRODUCT_BS_CATEGORY_OPTIONS,
                key="_flow_new_categories",
                help="Categories offered in this flow. Leave empty to offer all.",
            )
            wd_options = [
                item for item in (list(new_categories) or PRODUCT_BS_CATEGORY_OPTIONS)
                if item != "none"
            ]
            new_wd_categories = st.multiselect(
                "Week Discount files on release",
                wd_options,
                default=[item for item in ("Aggregated",) if item in wd_options],
                key="_flow_new_wd_categories_" + "-".join(wd_options),
                help=(
                    "Week Discount files ticked by default in Release → ALL: one aggregated "
                    "file, or one file per category (e.g. In, Out, ByCondition, ByMinPrice)."
                ),
            )
            if st.button(
                "Create flow…",
                disabled=not new_id or bool(id_error),
                width="stretch",
                key="_flow_create_btn",
            ):
                _create_flow_dialog(
                    new_id,
                    new_label.strip(),
                    list(new_categories),
                    list(new_wd_categories),
                    username,
                )


def require_flow(username: str = "") -> Flow:
    """Return the session's flow; otherwise show the start screen and stop the page."""
    flow = current_flow()
    if flow is not None:
        notice = st.session_state.pop("_flow_notice", None)
        if notice:
            st.warning(notice)
        _render_flow_sidebar(flow)
        return flow
    _render_start_screen(username)
    st.stop()
    raise RuntimeError("unreachable")
