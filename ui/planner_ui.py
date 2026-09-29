"""
Sidebar Planner: Campaigns, Jobs, membership Update, assignment conflicts.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from core.analytics.planner import (
    add_campaign,
    add_job,
    apply_job_assignment,
    delete_campaign,
    delete_job,
    ensure_planner_dict,
    find_assignment_conflicts,
    focused_baskets,
    get_campaign,
    get_job,
    list_campaigns,
    list_jobs,
    rename_campaign,
    rename_job,
)
from core.analytics.prom_strategy import PromStrategySettings
from ui.product_bs_scope import scoped_widget_key


def planner_from_scope(scope: dict[str, Any]) -> dict[str, Any]:
    from ui.week_discount_ui import _cached_discount_strategy_defaults

    planner = ensure_planner_dict(
        scope.get("planner"),
        _cached_discount_strategy_defaults(),
        PromStrategySettings(),
    )
    scope["planner"] = planner
    return planner


def _open_conflict_dialog() -> None:
    _render_assignment_conflict_dialog()


@st.dialog("Job assignment conflicts")
def _render_assignment_conflict_dialog() -> None:
    pending = st.session_state.get("_planner_pending_assignment")
    if not isinstance(pending, dict):
        st.caption("No pending assignment.")
        return
    conflicts = pending.get("conflicts") or []
    target_name = str(pending.get("new_job_name") or "Job")
    st.caption(
        f"Move selected baskets into **{target_name}**. "
        "Unchecked rows stay in their current Job."
    )
    editor_rev = int(st.session_state.get("_planner_conflict_rev", 0))
    approve_default = bool(st.session_state.get("_planner_conflict_approve_all", True))
    rows = conflict_rows_from_pending(conflicts, approve_default)
    edited = st.data_editor(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        disabled=["Basket", "Current Campaign", "Current Job", "New Job"],
        column_config={
            "Approve": st.column_config.CheckboxColumn("Approve", default=True),
        },
        key=f"_planner_conflict_editor_{editor_rev}",
    )
    all_col, none_col, _ = st.columns([1, 1, 2])
    if all_col.button("Approve all", use_container_width=True):
        st.session_state["_planner_conflict_approve_all"] = True
        st.session_state["_planner_conflict_rev"] = editor_rev + 1
        st.rerun()
    if none_col.button("Keep all", use_container_width=True):
        st.session_state["_planner_conflict_approve_all"] = False
        st.session_state["_planner_conflict_rev"] = editor_rev + 1
        st.rerun()

    confirm_col, cancel_col, _ = st.columns([1, 1, 2])
    if confirm_col.button("Confirm", type="primary", use_container_width=True):
        approved = {
            str(row["Basket"])
            for _, row in edited.iterrows()
            if bool(row.get("Approve"))
        }
        st.session_state["_planner_conflict_approved"] = approved
        st.session_state["_planner_apply_pending"] = True
        st.rerun()
    if cancel_col.button("Cancel", use_container_width=True):
        st.session_state["_planner_cancel_pending"] = True
        st.rerun()


def conflict_rows_from_pending(
    conflicts: list[dict[str, Any]],
    approve_default: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in conflicts:
        rows.append({
            "Basket": item.get("basket", ""),
            "Current Campaign": item.get("current_campaign_name", ""),
            "Current Job": item.get("current_job_name", ""),
            "New Job": item.get("new_job_name", ""),
            "Approve": approve_default,
        })
    return rows


def _conflicts_to_dicts(conflicts) -> list[dict[str, Any]]:
    return [
        {
            "basket": item.basket,
            "current_campaign_id": item.current_campaign_id,
            "current_campaign_name": item.current_campaign_name,
            "current_job_id": item.current_job_id,
            "current_job_name": item.current_job_name,
            "new_job_id": item.new_job_id,
            "new_job_name": item.new_job_name,
        }
        for item in conflicts
    ]


def begin_job_assignment(
    planner: dict[str, Any],
    target_job_id: str,
    candidate_baskets: list[str],
) -> None:
    """Apply immediately, or open the conflict dialog when steals exist."""
    job = get_job(planner, target_job_id)
    if job is None:
        planner["last_message"] = "Job not found."
        return
    conflicts = find_assignment_conflicts(planner, target_job_id, candidate_baskets)
    if not conflicts:
        stats = apply_job_assignment(planner, target_job_id, candidate_baskets, set())
        planner["pending_assignment"] = None
        planner["last_message"] = (
            f"{job.get('name')}: {stats['added']} added, "
            f"{stats['moved']} moved, {stats['kept']} left in other Jobs."
        )
        return
    pending = {
        "target_job_id": target_job_id,
        "new_job_name": str(job.get("name") or ""),
        "candidate_baskets": [str(item) for item in candidate_baskets],
        "conflicts": _conflicts_to_dicts(conflicts),
    }
    planner["pending_assignment"] = pending
    st.session_state["_planner_pending_assignment"] = pending
    st.session_state["_planner_conflict_approve_all"] = True
    st.session_state["_planner_conflict_rev"] = (
        int(st.session_state.get("_planner_conflict_rev", 0)) + 1
    )


def apply_pending_planner_actions(planner: dict[str, Any]) -> None:
    if st.session_state.pop("_planner_cancel_pending", False):
        planner["pending_assignment"] = None
        st.session_state.pop("_planner_pending_assignment", None)
        planner["last_message"] = "Assignment cancelled."
        return
    if not st.session_state.pop("_planner_apply_pending", False):
        if planner.get("pending_assignment"):
            st.session_state["_planner_pending_assignment"] = planner["pending_assignment"]
            _open_conflict_dialog()
        return
    pending = planner.get("pending_assignment") or st.session_state.get(
        "_planner_pending_assignment"
    )
    approved = set(st.session_state.pop("_planner_conflict_approved", set()) or [])
    st.session_state.pop("_planner_pending_assignment", None)
    planner["pending_assignment"] = None
    if not isinstance(pending, dict):
        planner["last_message"] = "Pending assignment was empty."
        return
    target_id = str(pending.get("target_job_id") or "")
    if get_job(planner, target_id) is None:
        planner["last_message"] = "Job no longer exists."
        return
    stats = apply_job_assignment(
        planner,
        target_id,
        list(pending.get("candidate_baskets") or []),
        approved,
    )
    job = get_job(planner, target_id)
    planner["last_message"] = (
        f"{(job or {}).get('name')}: {stats['added']} added, "
        f"{stats['moved']} moved, {stats['kept']} left in other Jobs."
    )


def _planner_section_label(text: str) -> None:
    st.markdown(
        f'<p style="font-size:1.05rem;font-weight:600;margin:0 0 0.25rem 0;">{text}</p>',
        unsafe_allow_html=True,
    )


def render_sidebar_planner_panel(
    scope: dict[str, Any],
    scope_key: str,
    selected_baskets: list[str] | None = None,
) -> dict[str, Any]:
    """Render Planner after Project. Returns the planner dict on *scope*."""
    planner = planner_from_scope(scope)
    apply_pending_planner_actions(planner)

    def wk(name: str) -> str:
        return scoped_widget_key(scope_key, name)

    with st.sidebar:
        with st.expander("Planner", expanded=True):
            st.caption(
                "Campaign → Jobs. Each basket belongs to at most one Job. "
                "Strategy is edited from the selected Campaign or Job."
            )
            campaigns = list_campaigns(planner)
            campaign_ids = [str(item["id"]) for item in campaigns]
            campaign_labels = {
                str(item["id"]): str(item.get("name") or item["id"])
                for item in campaigns
            }
            selected_campaign = planner.get("selected_campaign_id")
            if selected_campaign not in campaign_ids:
                selected_campaign = campaign_ids[0] if campaign_ids else None
            _planner_section_label("Campaign")
            campaign_choice = st.selectbox(
                "Campaign",
                ["—"] + campaign_ids,
                label_visibility="collapsed",
                index=(
                    campaign_ids.index(str(selected_campaign)) + 1
                    if selected_campaign in campaign_ids
                    else 0
                ),
                format_func=lambda value: (
                    "Select…" if value == "—" else campaign_labels.get(value, value)
                ),
                key=wk("planner_campaign"),
            )
            planner["selected_campaign_id"] = (
                None if campaign_choice == "—" else str(campaign_choice)
            )

            add_c1, add_c2 = st.columns(2)
            new_campaign_name = add_c1.text_input(
                "New Campaign",
                value="",
                key=wk("planner_new_campaign_name"),
                label_visibility="collapsed",
                placeholder="Campaign name",
            )
            if add_c2.button("Add", use_container_width=True, key=wk("planner_add_campaign")):
                add_campaign(planner, new_campaign_name)
                st.rerun()

            campaign = get_campaign(planner, planner.get("selected_campaign_id"))
            if campaign is not None:
                rename_c1, rename_c2 = st.columns([2, 1])
                renamed = rename_c1.text_input(
                    "Rename Campaign",
                    value=str(campaign.get("name") or ""),
                    key=wk(f"planner_rename_campaign_{campaign['id']}"),
                    label_visibility="collapsed",
                )
                if rename_c2.button("Rename", use_container_width=True, key=wk("planner_rename_campaign_btn")):
                    rename_campaign(planner, str(campaign["id"]), renamed)
                    st.rerun()
                if st.button("Delete Campaign", use_container_width=True, key=wk("planner_delete_campaign")):
                    delete_campaign(planner, str(campaign["id"]))
                    st.rerun()

                jobs = list_jobs(planner, str(campaign["id"]))
                job_ids = [str(job["id"]) for job in jobs]
                job_labels = {
                    str(job["id"]): str(job.get("name") or job["id"])
                    for job in jobs
                }
                kept_jobs = [
                    job_id
                    for job_id in planner.get("selected_job_ids") or []
                    if job_id in job_ids
                ]
                st.divider()
                _planner_section_label("Jobs")
                selected_jobs = st.multiselect(
                    "Jobs",
                    job_ids,
                    label_visibility="collapsed",
                    default=kept_jobs,
                    format_func=lambda value: job_labels.get(value, value),
                    key=wk(f"planner_jobs_{campaign['id']}"),
                    help="Select one or more Jobs. Strategy Apply uses this selection.",
                )
                planner["selected_job_ids"] = [str(item) for item in selected_jobs]

                add_j1, add_j2 = st.columns(2)
                new_job_name = add_j1.text_input(
                    "New Job",
                    value="",
                    key=wk("planner_new_job_name"),
                    label_visibility="collapsed",
                    placeholder="Job name",
                )
                if add_j2.button("Add", use_container_width=True, key=wk("planner_add_job")):
                    add_job(planner, str(campaign["id"]), new_job_name)
                    st.rerun()

                if len(planner["selected_job_ids"]) == 1:
                    job = get_job(planner, planner["selected_job_ids"][0])
                    if job is not None:
                        job_rename, job_btn = st.columns([2, 1])
                        job_new_name = job_rename.text_input(
                            "Rename Job",
                            value=str(job.get("name") or ""),
                            key=wk(f"planner_rename_job_{job['id']}"),
                            label_visibility="collapsed",
                        )
                        if job_btn.button("Rename", use_container_width=True, key=wk("planner_rename_job_btn")):
                            rename_job(planner, str(job["id"]), job_new_name)
                            st.rerun()
                        if st.button("Delete Job", use_container_width=True, key=wk("planner_delete_job")):
                            delete_job(planner, str(job["id"]))
                            st.rerun()
                        n_members = len(job.get("basket_ids") or [])
                        st.caption(
                            f"{n_members} basket(s) in this Job · id {job['id']}"
                        )

                update_disabled = len(planner["selected_job_ids"]) != 1
                if st.button(
                    "Update",
                    use_container_width=True,
                    type="primary",
                    disabled=update_disabled,
                    key=wk("planner_update_job"),
                    help=(
                        "Set the selected Job to the current table selection "
                        "(Multiselect ticks). Unchecked members are unassigned."
                    ),
                ):
                    begin_job_assignment(
                        planner,
                        planner["selected_job_ids"][0],
                        list(selected_baskets or []),
                    )
                    st.rerun()
                if update_disabled:
                    st.caption("Select exactly one Job to Update membership.")
            else:
                planner["selected_job_ids"] = []

            if planner.get("last_message"):
                st.caption(planner["last_message"])
            focus = focused_baskets(planner)
            if focus:
                st.caption(f"Focus: {len(focus)} basket(s) from Planner selection.")

    return planner
