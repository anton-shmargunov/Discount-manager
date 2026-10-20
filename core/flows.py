"""
Flows: independent product groups (A-used, B-used, NEW, ...). No Streamlit imports.

Each flow owns its report, discount history, projects and Week Discount files.
With Google Drive, every folder under the root that holds a ``flow.json`` is a
flow, so new flows need no code change. ``configs/flows.csv`` seeds the list
and is the only source when Drive is not configured.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from configs.settings import PROJECT_ROOT
from core.persistence.file_naming import detect_flow_tags, is_week, parse_name
from core.persistence.gdrive import DriveClientError, DriveStore

FLOWS_SEED_PATH = PROJECT_ROOT / "configs" / "flows.csv"
FLOW_META_FILENAME = "flow.json"
FLOW_ID_MIN_LEN = 2
FLOW_ID_MAX_LEN = 20
_FLOW_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")

SOURCE_SEED = "seed"
SOURCE_DRIVE = "drive"
SOURCE_SESSION = "session"


@dataclass(frozen=True)
class Flow:
    flow_id: str
    label: str = ""
    categories: tuple[str, ...] = ()
    strategies_file: str = ""
    week_discount_categories: tuple[str, ...] = ()
    hidden: bool = False
    source: str = SOURCE_SEED
    folder_id: str = ""
    last_week: str = ""
    weeks: tuple[str, ...] = field(default_factory=tuple)

    @property
    def display(self) -> str:
        label = self.label.strip()
        if not label or label == self.flow_id:
            return self.flow_id
        return f"{label} ({self.flow_id})"

    def to_meta(self, *, created_by: str = "", created_at: str = "") -> dict[str, Any]:
        meta: dict[str, Any] = {
            "flow_id": self.flow_id,
            "label": self.label or self.flow_id,
            "categories": list(self.categories),
            "strategies_file": self.strategies_file,
            "week_discount_categories": list(self.week_discount_categories),
        }
        if created_by:
            meta["created_by"] = created_by
        if created_at:
            meta["created_at"] = created_at
        if self.hidden:
            meta["hidden"] = True
        return meta

    def to_session(self) -> dict[str, Any]:
        data = self.to_meta()
        data["source"] = self.source
        data["folder_id"] = self.folder_id
        data["last_week"] = self.last_week
        data["weeks"] = list(self.weeks)
        return data

    @classmethod
    def from_meta(cls, data: Mapping[str, Any], *, source: str = SOURCE_SEED) -> "Flow":
        return cls(
            flow_id=str(data.get("flow_id") or "").strip(),
            label=str(data.get("label") or "").strip(),
            categories=_category_tuple(data.get("categories")),
            strategies_file=str(data.get("strategies_file") or "").strip(),
            week_discount_categories=_category_tuple(data.get("week_discount_categories")),
            hidden=bool(data.get("hidden", False)),
            source=str(data.get("source") or source),
            folder_id=str(data.get("folder_id") or ""),
            last_week=str(data.get("last_week") or ""),
            weeks=tuple(str(item) for item in (data.get("weeks") or ())),
        )


def parse_categories(text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in str(text or "").split(";") if part.strip())


def _category_tuple(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return parse_categories(value)
    return tuple(str(item).strip() for item in value if str(item).strip())


def validate_flow_id(flow_id: str, existing_ids: Iterable[str] = ()) -> Optional[str]:
    """Error message for an invalid or duplicate id; ``None`` when it can be used."""
    text = str(flow_id or "").strip()
    if not text:
        return "Enter a flow id."
    if not (FLOW_ID_MIN_LEN <= len(text) <= FLOW_ID_MAX_LEN):
        return f"Use {FLOW_ID_MIN_LEN}–{FLOW_ID_MAX_LEN} characters."
    if not _FLOW_ID_RE.match(text):
        return "Start with a letter; use only letters, digits and '-'."
    if text.lower() in {"all", "shared"} or text.startswith("_"):
        return f"'{text}' is reserved."
    if text.lower() in {str(item).lower() for item in existing_ids}:
        return f"Flow '{text}' already exists."
    return None


def load_seed_flows(path: Optional[Path] = None) -> list[Flow]:
    """Flows listed in ``configs/flows.csv``; invalid or duplicate rows are skipped."""
    seed_path = Path(path or FLOWS_SEED_PATH)
    if not seed_path.exists():
        return []
    flows: list[Flow] = []
    seen: set[str] = set()
    with seed_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            flow_id = str(row.get("flow_id") or "").strip()
            if validate_flow_id(flow_id, seen) is not None:
                continue
            seen.add(flow_id)
            flows.append(
                Flow(
                    flow_id=flow_id,
                    label=str(row.get("label") or "").strip(),
                    categories=parse_categories(row.get("categories") or ""),
                    strategies_file=str(row.get("strategies_file") or "").strip(),
                    week_discount_categories=parse_categories(
                        row.get("week_discount_categories") or ""
                    ),
                    source=SOURCE_SEED,
                )
            )
    return flows


def merge_flows(seed: Iterable[Flow], others: Iterable[Flow]) -> list[Flow]:
    """Seed order first, then other flows by id. Later sources win; hidden flows are dropped."""
    by_id: dict[str, Flow] = {}
    order: list[str] = []
    for flow in list(seed) + list(others):
        key = flow.flow_id.lower()
        if key not in by_id:
            order.append(key)
        by_id[key] = flow
    return [by_id[key] for key in order if not by_id[key].hidden]


def _read_flow_meta(store: DriveStore, folder_id: str, file_id: str) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(store.download_file(folder_id, file_id).decode("utf-8-sig"))
    except (DriveClientError, ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def list_drive_flows(store: DriveStore, seed: Iterable[Flow] = ()) -> list[Flow]:
    """Flows found under the Drive root, with their week folders.

    A folder counts when it has a valid ``flow.json``, or when its name is a seed flow id.
    """
    seed_by_id = {flow.flow_id.lower(): flow for flow in seed}
    flows: dict[str, Flow] = {}
    folders = sorted(
        store.list_subfolders(store.root_id),
        key=lambda item: (item.created_time or item.modified_time, item.id),
    )
    for folder in folders:
        name = folder.name.strip()
        if not name or name.startswith("_") or name.lower() in flows:
            if name.lower() in flows:
                store.warnings.append(
                    f"Drive has more than one '{name}' flow folder; using the oldest."
                )
            continue
        week_names = sorted(
            (item.name for item in store.list_subfolders(folder.id) if is_week(item.name)),
            reverse=True,
        )
        meta_files = [
            item for item in store.list_files(folder.id) if item.name == FLOW_META_FILENAME
        ]
        meta = _read_flow_meta(store, folder.id, meta_files[0].id) if meta_files else None
        seed_flow = seed_by_id.get(name.lower())
        if meta is not None and str(meta.get("flow_id") or "").strip().lower() == name.lower():
            base = Flow.from_meta(meta, source=SOURCE_DRIVE)
        elif seed_flow is not None:
            base = seed_flow
        else:
            continue
        week_discount_categories = base.week_discount_categories
        if not week_discount_categories and seed_flow is not None:
            week_discount_categories = seed_flow.week_discount_categories
        flows[name.lower()] = Flow(
            flow_id=name,
            label=base.label,
            categories=base.categories,
            strategies_file=base.strategies_file,
            week_discount_categories=week_discount_categories,
            hidden=base.hidden,
            source=SOURCE_DRIVE,
            folder_id=folder.id,
            last_week=week_names[0] if week_names else "",
            weeks=tuple(week_names),
        )
    return list(flows.values())


def write_flow_meta(store: DriveStore, flow: Flow, *, created_by: str = "") -> str:
    """Create ``<flow>/`` and its ``flow.json`` when missing. Returns the folder id."""
    folder_id = store.ensure_subfolder(store.root_id, flow.flow_id)
    names = {item.name for item in store.list_files(folder_id)}
    if FLOW_META_FILENAME not in names:
        meta = flow.to_meta(
            created_by=created_by,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        store.upload_bytes(
            folder_id,
            FLOW_META_FILENAME,
            json.dumps(meta, indent=2).encode("utf-8"),
            "application/json",
        )
    return folder_id


def create_flow(
    store: Optional[DriveStore],
    flow_id: str,
    label: str,
    categories: Iterable[str],
    *,
    week_discount_categories: Iterable[str] = (),
    existing_ids: Iterable[str] = (),
    created_by: str = "",
) -> Flow:
    """Create a flow on Drive (or a session-only flow without Drive)."""
    flow_id = str(flow_id or "").strip()
    known = list(existing_ids)
    if store is not None:
        known += [flow.flow_id for flow in list_drive_flows(store)]
    error = validate_flow_id(flow_id, known)
    if error:
        raise ValueError(error)
    flow = Flow(
        flow_id=flow_id,
        label=str(label or "").strip() or flow_id,
        categories=_category_tuple(list(categories)),
        week_discount_categories=_category_tuple(list(week_discount_categories)),
        source=SOURCE_SESSION if store is None else SOURCE_DRIVE,
    )
    if store is None:
        return flow
    folder_id = write_flow_meta(store, flow, created_by=created_by)
    return replace(flow, folder_id=folder_id)


def flow_category_options(flow: Optional[Flow], all_options: Iterable[str]) -> list[str]:
    """The flow's Product BS categories in app order; every option when none are listed."""
    options = list(all_options)
    if flow is None or not flow.categories:
        return options
    wanted = {item.lower() for item in flow.categories}
    limited = [item for item in options if item.lower() in wanted]
    return limited or options


def stamp_project_flow(payload: dict[str, Any], flow_id: str) -> dict[str, Any]:
    payload["flow_id"] = str(flow_id)
    return payload


def check_project_flow(
    payload: Mapping[str, Any],
    flow_id: str,
    *,
    filename: str = "",
    known_flow_ids: Iterable[str] = (),
) -> Optional[str]:
    """Raise ``ValueError`` when the project belongs to another flow.

    Returns a warning for projects saved before flows existed.
    """
    saved = str(payload.get("flow_id") or "").strip()
    if saved:
        if saved.lower() != str(flow_id).lower():
            raise ValueError(
                f"This project belongs to flow '{saved}', not '{flow_id}'. "
                "Switch flow first."
            )
        return None
    parsed = parse_name(filename) if filename else None
    name_flow = parsed.flow_id if parsed is not None else None
    if not name_flow and filename:
        tags = detect_flow_tags(filename, known_flow_ids)
        name_flow = tags[0] if len(tags) == 1 else None
    if name_flow and name_flow.lower() != str(flow_id).lower():
        raise ValueError(
            f"The file name says flow '{name_flow}', not '{flow_id}'. Switch flow first."
        )
    return (
        "This project was saved before flows existed; "
        f"it was opened in flow '{flow_id}'."
    )
