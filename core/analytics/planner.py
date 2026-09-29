"""
Campaign / Job planner — exclusive basket membership and per-Job strategies.

Kept in its own module so Streamlit Cloud can load it even when older
modules are served from a stale snapshot.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from core.analytics.discount_strategy import (
    DiscountStrategySettings,
    MarginCategory,
    StrategyBin,
    StrategyTable,
    default_discount_strategy_settings,
)
from core.analytics.prom_strategy import PromStrategySettings

PLANNER_ID_DIGITS = 10
# v1 planners were seeded from built-in strategy tables instead of strategies.v1.csv.
PLANNER_SETTINGS_VERSION = 2


@dataclass
class CampaignRecord:
    id: str
    name: str


@dataclass
class JobRecord:
    id: str
    name: str
    campaign_id: str
    basket_ids: list[str] = field(default_factory=list)
    discount_settings: dict[str, Any] = field(default_factory=dict)
    prom_settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class BasketAssignment:
    campaign_id: str
    campaign_name: str
    job_id: str
    job_name: str


@dataclass
class AssignmentConflict:
    basket: str
    current_campaign_id: str
    current_campaign_name: str
    current_job_id: str
    current_job_name: str
    new_job_id: str
    new_job_name: str


def new_planner_id(existing: set[str]) -> str:
    """Return a 10-digit id that is unique within *existing*."""
    known = {str(item) for item in existing}
    for _ in range(80):
        value = f"{random.randint(0, 10 ** PLANNER_ID_DIGITS - 1):0{PLANNER_ID_DIGITS}d}"
        if value not in known:
            return value
    raise RuntimeError("Could not allocate a unique planner id.")


def empty_planner_dict(
    default_discount: DiscountStrategySettings | None = None,
    default_prom: PromStrategySettings | None = None,
) -> dict[str, Any]:
    discount = default_discount or default_discount_strategy_settings()
    prom = default_prom or PromStrategySettings()
    return {
        "campaigns": [],
        "jobs": [],
        "selected_campaign_id": None,
        "selected_job_ids": [],
        "default_discount_settings": serialize_discount_settings(discount),
        "default_prom_settings": serialize_prom_settings(prom),
        "pending_assignment": None,
        "last_message": "",
        "settings_version": PLANNER_SETTINGS_VERSION,
    }


def ensure_planner_dict(
    raw: object,
    default_discount: DiscountStrategySettings | None = None,
    default_prom: PromStrategySettings | None = None,
) -> dict[str, Any]:
    """Return a planner dict, filling missing keys from an empty planner."""
    blank = empty_planner_dict(default_discount, default_prom)
    if not isinstance(raw, dict):
        return blank
    out = dict(blank)
    out.update(raw)
    out["campaigns"] = [dict(item) for item in (out.get("campaigns") or []) if isinstance(item, dict)]
    out["jobs"] = [dict(item) for item in (out.get("jobs") or []) if isinstance(item, dict)]
    out["selected_job_ids"] = [str(item) for item in (out.get("selected_job_ids") or [])]
    if out.get("selected_campaign_id") is not None:
        out["selected_campaign_id"] = str(out["selected_campaign_id"])
    if not isinstance(out.get("default_discount_settings"), dict):
        out["default_discount_settings"] = blank["default_discount_settings"]
    if not isinstance(out.get("default_prom_settings"), dict):
        out["default_prom_settings"] = blank["default_prom_settings"]
    if raw.get("settings_version") != PLANNER_SETTINGS_VERSION:
        builtin = serialize_discount_settings(default_discount_strategy_settings())
        if out["default_discount_settings"] == builtin:
            out["default_discount_settings"] = blank["default_discount_settings"]
        for job in out["jobs"]:
            if job.get("discount_settings") == builtin:
                job["discount_settings"] = dict(blank["default_discount_settings"])
        out["settings_version"] = PLANNER_SETTINGS_VERSION
    return out


def _serialize_table(table: StrategyTable) -> dict[str, Any]:
    return {
        "name": table.name,
        "bins": [
            {"lower": bin.lower, "upper": bin.upper, "d_discount": bin.d_discount}
            for bin in table.bins
        ],
    }


def _deserialize_table(raw: object, fallback: StrategyTable) -> StrategyTable:
    if not isinstance(raw, dict):
        return StrategyTable(fallback.name, list(fallback.bins))
    bins: list[StrategyBin] = []
    for item in raw.get("bins") or []:
        if not isinstance(item, dict):
            continue
        try:
            bins.append(
                StrategyBin(
                    float(item["lower"]),
                    float(item["upper"]),
                    float(item["d_discount"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    name = str(raw.get("name") or fallback.name)
    return StrategyTable(name, bins or list(fallback.bins))


def serialize_discount_settings(settings: DiscountStrategySettings) -> dict[str, Any]:
    return {
        "mode": settings.mode,
        "balance": float(settings.balance),
        "multiplicator": float(settings.multiplicator),
        "zero_d_st_negative": bool(settings.zero_d_st_negative),
        "zero_d_st_positive": bool(settings.zero_d_st_positive),
        "missing_discount_default": float(settings.missing_discount_default),
        "sold_zero_strategy": settings.sold_zero_strategy,
        "sold_zero_balance": float(settings.sold_zero_balance),
        "mtost_strategy_enabled": bool(settings.mtost_strategy_enabled),
        "mtost_balance": float(settings.mtost_balance),
        "mtost": _serialize_table(settings.mtost),
        "margin_mode": settings.margin_mode,
        "default_strategy": settings.default_strategy,
        "conservative": _serialize_table(settings.conservative),
        "moderate": _serialize_table(settings.moderate),
        "strong": _serialize_table(settings.strong),
        "margin_categories": [
            {"lower": cat.lower, "upper": cat.upper, "strategy": cat.strategy}
            for cat in settings.margin_categories
        ],
    }


def deserialize_discount_settings(raw: object) -> DiscountStrategySettings:
    fallback = default_discount_strategy_settings()
    if not isinstance(raw, dict):
        return fallback
    categories: list[MarginCategory] = []
    for item in raw.get("margin_categories") or []:
        if not isinstance(item, dict):
            continue
        try:
            categories.append(
                MarginCategory(
                    float(item["lower"]),
                    float(item["upper"]),
                    str(item.get("strategy") or "Moderate"),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return DiscountStrategySettings(
        mode=str(raw.get("mode") or fallback.mode),
        balance=float(raw.get("balance", fallback.balance)),
        multiplicator=float(raw.get("multiplicator", fallback.multiplicator)),
        zero_d_st_negative=bool(raw.get("zero_d_st_negative", fallback.zero_d_st_negative)),
        zero_d_st_positive=bool(raw.get("zero_d_st_positive", fallback.zero_d_st_positive)),
        missing_discount_default=float(
            raw.get("missing_discount_default", fallback.missing_discount_default)
        ),
        sold_zero_strategy=str(raw.get("sold_zero_strategy") or fallback.sold_zero_strategy),
        sold_zero_balance=float(raw.get("sold_zero_balance", fallback.sold_zero_balance)),
        mtost_strategy_enabled=bool(
            raw.get("mtost_strategy_enabled", fallback.mtost_strategy_enabled)
        ),
        mtost_balance=float(raw.get("mtost_balance", fallback.mtost_balance)),
        mtost=_deserialize_table(raw.get("mtost"), fallback.mtost),
        margin_mode=str(raw.get("margin_mode") or fallback.margin_mode),
        default_strategy=str(raw.get("default_strategy") or fallback.default_strategy),
        conservative=_deserialize_table(raw.get("conservative"), fallback.conservative),
        moderate=_deserialize_table(raw.get("moderate"), fallback.moderate),
        strong=_deserialize_table(raw.get("strong"), fallback.strong),
        margin_categories=categories or list(fallback.margin_categories),
    )


def serialize_prom_settings(settings: PromStrategySettings) -> dict[str, Any]:
    return {"mode": settings.mode}


def deserialize_prom_settings(raw: object) -> PromStrategySettings:
    if not isinstance(raw, dict):
        return PromStrategySettings()
    return PromStrategySettings(mode=str(raw.get("mode") or "Set previous prom"))


def unique_planner_name(base: str, existing: list[str]) -> str:
    name = str(base or "").strip() or "Untitled"
    known = {str(item) for item in existing}
    if name not in known:
        return name
    idx = 2
    while f"{name} ({idx})" in known:
        idx += 1
    return f"{name} ({idx})"


def _all_ids(planner: dict[str, Any]) -> set[str]:
    ids = {str(item.get("id", "")) for item in planner.get("campaigns") or []}
    ids.update(str(item.get("id", "")) for item in planner.get("jobs") or [])
    ids.discard("")
    return ids


def list_campaigns(planner: dict[str, Any]) -> list[dict[str, Any]]:
    return list(planner.get("campaigns") or [])


def list_jobs(planner: dict[str, Any], campaign_id: str | None = None) -> list[dict[str, Any]]:
    jobs = list(planner.get("jobs") or [])
    if campaign_id is None:
        return jobs
    return [job for job in jobs if str(job.get("campaign_id")) == str(campaign_id)]


def get_campaign(planner: dict[str, Any], campaign_id: str | None) -> dict[str, Any] | None:
    if not campaign_id:
        return None
    for item in planner.get("campaigns") or []:
        if str(item.get("id")) == str(campaign_id):
            return item
    return None


def get_job(planner: dict[str, Any], job_id: str | None) -> dict[str, Any] | None:
    if not job_id:
        return None
    for item in planner.get("jobs") or []:
        if str(item.get("id")) == str(job_id):
            return item
    return None


def add_campaign(planner: dict[str, Any], name: str) -> dict[str, Any]:
    names = [str(item.get("name", "")) for item in planner.get("campaigns") or []]
    campaign = {
        "id": new_planner_id(_all_ids(planner)),
        "name": unique_planner_name(name or "Campaign", names),
    }
    planner.setdefault("campaigns", []).append(campaign)
    planner["selected_campaign_id"] = campaign["id"]
    planner["selected_job_ids"] = []
    return campaign


def add_job(
    planner: dict[str, Any],
    campaign_id: str,
    name: str,
    *,
    basket_ids: list[str] | None = None,
    discount_settings: dict[str, Any] | None = None,
    prom_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if get_campaign(planner, campaign_id) is None:
        raise ValueError("Campaign not found.")
    names = [str(job.get("name", "")) for job in list_jobs(planner, campaign_id)]
    job = {
        "id": new_planner_id(_all_ids(planner)),
        "name": unique_planner_name(name or "Job", names),
        "campaign_id": str(campaign_id),
        "basket_ids": [str(item) for item in (basket_ids or [])],
        "discount_settings": dict(
            discount_settings or planner.get("default_discount_settings") or {}
        ),
        "prom_settings": dict(prom_settings or planner.get("default_prom_settings") or {}),
    }
    planner.setdefault("jobs", []).append(job)
    planner["selected_campaign_id"] = str(campaign_id)
    planner["selected_job_ids"] = [job["id"]]
    return job


def rename_campaign(planner: dict[str, Any], campaign_id: str, name: str) -> None:
    campaign = get_campaign(planner, campaign_id)
    if campaign is None:
        raise ValueError("Campaign not found.")
    others = [
        str(item.get("name", ""))
        for item in planner.get("campaigns") or []
        if str(item.get("id")) != str(campaign_id)
    ]
    campaign["name"] = unique_planner_name(name, others)


def rename_job(planner: dict[str, Any], job_id: str, name: str) -> None:
    job = get_job(planner, job_id)
    if job is None:
        raise ValueError("Job not found.")
    others = [
        str(item.get("name", ""))
        for item in list_jobs(planner, str(job.get("campaign_id")))
        if str(item.get("id")) != str(job_id)
    ]
    job["name"] = unique_planner_name(name, others)


def delete_campaign(planner: dict[str, Any], campaign_id: str) -> None:
    planner["jobs"] = [
        job
        for job in planner.get("jobs") or []
        if str(job.get("campaign_id")) != str(campaign_id)
    ]
    planner["campaigns"] = [
        item
        for item in planner.get("campaigns") or []
        if str(item.get("id")) != str(campaign_id)
    ]
    if str(planner.get("selected_campaign_id")) == str(campaign_id):
        planner["selected_campaign_id"] = None
        planner["selected_job_ids"] = []


def delete_job(planner: dict[str, Any], job_id: str) -> None:
    planner["jobs"] = [
        job for job in planner.get("jobs") or [] if str(job.get("id")) != str(job_id)
    ]
    planner["selected_job_ids"] = [
        item for item in planner.get("selected_job_ids") or [] if str(item) != str(job_id)
    ]


def assignment_lookup(planner: dict[str, Any]) -> dict[str, BasketAssignment]:
    campaigns = {
        str(item.get("id")): str(item.get("name") or "")
        for item in planner.get("campaigns") or []
    }
    out: dict[str, BasketAssignment] = {}
    for job in planner.get("jobs") or []:
        campaign_id = str(job.get("campaign_id") or "")
        assignment = BasketAssignment(
            campaign_id=campaign_id,
            campaign_name=campaigns.get(campaign_id, ""),
            job_id=str(job.get("id") or ""),
            job_name=str(job.get("name") or ""),
        )
        for basket in job.get("basket_ids") or []:
            key = str(basket)
            if key:
                out[key] = assignment
    return out


def annotate_week_discount_rows(
    rows: list[dict],
    planner: dict[str, Any],
) -> list[dict]:
    lookup = assignment_lookup(planner)
    annotated: list[dict] = []
    for row in rows:
        copy = dict(row)
        info = lookup.get(str(copy.get("Basket", "")))
        copy["Campaign"] = info.campaign_name if info else ""
        copy["Job"] = info.job_name if info else ""
        annotated.append(copy)
    return annotated


def assignment_columns(planner: dict[str, Any], basket: str) -> tuple[str, str]:
    info = assignment_lookup(planner).get(str(basket))
    if info is None:
        return "", ""
    return info.campaign_name, info.job_name


def focused_baskets(planner: dict[str, Any]) -> list[str]:
    """Baskets belonging to the Planner selection (jobs, else whole campaign)."""
    selected_jobs = [str(item) for item in planner.get("selected_job_ids") or []]
    names: list[str] = []
    seen: set[str] = set()

    def _add(job: dict[str, Any]) -> None:
        for basket in job.get("basket_ids") or []:
            key = str(basket)
            if key and key not in seen:
                seen.add(key)
                names.append(key)

    if selected_jobs:
        for job_id in selected_jobs:
            job = get_job(planner, job_id)
            if job is not None:
                _add(job)
        return names

    campaign_id = planner.get("selected_campaign_id")
    if campaign_id:
        for job in list_jobs(planner, str(campaign_id)):
            _add(job)
    return names


def selected_job_targets(planner: dict[str, Any]) -> list[dict[str, Any]]:
    """Jobs that Apply / scoped Generate should use."""
    selected_jobs = [str(item) for item in planner.get("selected_job_ids") or []]
    if selected_jobs:
        return [job for job_id in selected_jobs if (job := get_job(planner, job_id))]
    campaign_id = planner.get("selected_campaign_id")
    if campaign_id:
        return list_jobs(planner, str(campaign_id))
    return []


def find_assignment_conflicts(
    planner: dict[str, Any],
    target_job_id: str,
    baskets: list[str],
) -> list[AssignmentConflict]:
    target = get_job(planner, target_job_id)
    if target is None:
        raise ValueError("Job not found.")
    lookup = assignment_lookup(planner)
    conflicts: list[AssignmentConflict] = []
    seen: set[str] = set()
    for basket in baskets:
        key = str(basket)
        if not key or key in seen:
            continue
        seen.add(key)
        current = lookup.get(key)
        if current is None or current.job_id == str(target_job_id):
            continue
        conflicts.append(
            AssignmentConflict(
                basket=key,
                current_campaign_id=current.campaign_id,
                current_campaign_name=current.campaign_name,
                current_job_id=current.job_id,
                current_job_name=current.job_name,
                new_job_id=str(target["id"]),
                new_job_name=str(target.get("name") or ""),
            )
        )
    return conflicts


def apply_job_assignment(
    planner: dict[str, Any],
    target_job_id: str,
    candidate_baskets: list[str],
    approved_baskets: set[str],
) -> dict[str, int]:
    """
    Set target Job membership to approved candidates.

    Unassigned and already-in-target baskets join without approval.
    Other-job baskets join only if listed in *approved_baskets*.
    Baskets currently in the target but omitted from candidates are unassigned.
    """
    target = get_job(planner, target_job_id)
    if target is None:
        raise ValueError("Job not found.")
    lookup = assignment_lookup(planner)
    desired: list[str] = []
    seen: set[str] = set()
    added = 0
    moved = 0
    kept = 0
    for basket in candidate_baskets:
        key = str(basket)
        if not key or key in seen:
            continue
        seen.add(key)
        current = lookup.get(key)
        if current is None:
            desired.append(key)
            added += 1
            continue
        if current.job_id == str(target_job_id):
            desired.append(key)
            continue
        if key in approved_baskets:
            desired.append(key)
            moved += 1
        else:
            kept += 1

    desired_set = set(desired)
    for job in planner.get("jobs") or []:
        remaining: list[str] = []
        for basket in job.get("basket_ids") or []:
            key = str(basket)
            if str(job.get("id")) == str(target_job_id):
                if key in desired_set:
                    remaining.append(key)
                continue
            if key in desired_set:
                continue
            remaining.append(key)
        job["basket_ids"] = remaining
    target["basket_ids"] = desired
    return {
        "added": added,
        "moved": moved,
        "kept": kept,
        "size": len(desired),
    }


def apply_settings_to_jobs(
    planner: dict[str, Any],
    jobs: list[dict[str, Any]],
    discount_settings: DiscountStrategySettings,
    prom_settings: PromStrategySettings,
) -> int:
    payload_d = serialize_discount_settings(discount_settings)
    payload_p = serialize_prom_settings(prom_settings)
    count = 0
    for job in jobs:
        job["discount_settings"] = dict(payload_d)
        job["prom_settings"] = dict(payload_p)
        count += 1
    return count


def store_default_settings(
    planner: dict[str, Any],
    discount_settings: DiscountStrategySettings,
    prom_settings: PromStrategySettings,
) -> None:
    planner["default_discount_settings"] = serialize_discount_settings(discount_settings)
    planner["default_prom_settings"] = serialize_prom_settings(prom_settings)


def target_baskets_for_generate(
    planner: dict[str, Any],
    all_baskets: list[str],
    *,
    campaign_switch_on: bool,
    all_jobs: bool,
) -> set[str]:
    """Basket ids that a Generate click should rewrite."""
    lookup = assignment_lookup(planner)
    universe = [str(name) for name in all_baskets if str(name)]
    if all_jobs:
        return set(universe)
    if not campaign_switch_on:
        return {name for name in universe if name not in lookup}
    selected: set[str] = set()
    for job in selected_job_targets(planner):
        selected.update(str(item) for item in job.get("basket_ids") or [])
    return selected


def generate_discount_all_jobs(
    rows: list[dict],
    column_meta: dict[str, dict[str, object]],
    filter_map: dict[str, str],
    planner: dict[str, Any],
) -> dict[str, float]:
    """New Discount for every row: each Job's stored settings, else default."""
    from core.analytics.discount_strategy import generate_week_discount_values

    lookup = assignment_lookup(planner)
    generated: dict[str, float] = {}
    default_settings = deserialize_discount_settings(
        planner.get("default_discount_settings")
    )
    by_job: dict[str, list[dict]] = {}
    default_rows: list[dict] = []
    for row in rows:
        basket = str(row.get("Basket", ""))
        info = lookup.get(basket)
        if info is None:
            default_rows.append(row)
        else:
            by_job.setdefault(info.job_id, []).append(row)
    if default_rows:
        generated.update(
            generate_week_discount_values(
                default_rows, column_meta, filter_map, default_settings,
            )
        )
    for job_id, job_rows in by_job.items():
        job = get_job(planner, job_id)
        settings = deserialize_discount_settings(
            (job or {}).get("discount_settings")
        )
        generated.update(
            generate_week_discount_values(
                job_rows, column_meta, filter_map, settings,
            )
        )
    return generated


def generate_prom_all_jobs(
    rows: list[dict],
    filter_map: dict[str, str],
    planner: dict[str, Any],
) -> dict[str, float]:
    """New Prom for every row: each Job's stored settings, else default."""
    from core.analytics.prom_strategy import generate_week_prom_values

    lookup = assignment_lookup(planner)
    generated: dict[str, float] = {}
    default_settings = deserialize_prom_settings(planner.get("default_prom_settings"))
    by_job: dict[str, list[dict]] = {}
    default_rows: list[dict] = []
    for row in rows:
        basket = str(row.get("Basket", ""))
        info = lookup.get(basket)
        if info is None:
            default_rows.append(row)
        else:
            by_job.setdefault(info.job_id, []).append(row)
    if default_rows:
        generated.update(generate_week_prom_values(default_rows, filter_map, default_settings))
    for job_id, job_rows in by_job.items():
        job = get_job(planner, job_id)
        settings = deserialize_prom_settings((job or {}).get("prom_settings"))
        generated.update(generate_week_prom_values(job_rows, filter_map, settings))
    return generated


def conflict_rows(conflicts: list[AssignmentConflict]) -> list[dict[str, Any]]:
    return [
        {
            "Basket": item.basket,
            "Current Campaign": item.current_campaign_name,
            "Current Job": item.current_job_name,
            "New Job": item.new_job_name,
            "Approve": True,
        }
        for item in conflicts
    ]
