"""
File names for flow outputs. No Streamlit imports.

Rule: ``<kind>_<flow>[_<tag>]_<week>_r<NN>[_rlsd].<ext>``

- ``kind``: ``discount_project``, ``week_discount`` or ``discount_hist``.
- ``tag``: Product BS category, or ``ALL`` for the set built from every category.
  ``OutByCondition`` and ``OutByMinPrice`` are written as ``ByCondition`` and
  ``ByMinPrice``; parsing maps them back to the category.
- ``week``: ``YYYY-WW``. Projects and Week Discount use the analysed week W;
  discount history uses the week it is meant for (W+1).
- ``rNN``: revision, unique per flow and week folder.
- ``rlsd``: released. One released file per flow, week, kind and tag.

Older names (``discount_hist_2026-40_A-used_ALL.csv``,
``discount_project_A-used_In_40_2.disc_proj``) are parsed as legacy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

KIND_PROJECT = "discount_project"
KIND_WEEK_DISCOUNT = "week_discount"
KIND_DISCOUNT_HIST = "discount_hist"
KINDS = (KIND_PROJECT, KIND_WEEK_DISCOUNT, KIND_DISCOUNT_HIST)

KIND_FOLDERS = {
    KIND_PROJECT: "proj",
    KIND_WEEK_DISCOUNT: "week_discount",
    KIND_DISCOUNT_HIST: "discount_history",
}
INPUT_FOLDER = "input"
KIND_EXTENSIONS = {
    KIND_PROJECT: ".disc_proj",
    KIND_WEEK_DISCOUNT: ".csv",
    KIND_DISCOUNT_HIST: ".csv",
}
KIND_MIME = {
    KIND_PROJECT: "application/octet-stream",
    KIND_WEEK_DISCOUNT: "text/csv",
    KIND_DISCOUNT_HIST: "text/csv",
}

RELEASED_POSTFIX = "rlsd"
ALL_TAG = "ALL"

FLOW_TOKEN = r"[A-Za-z][A-Za-z0-9-]*"
WEEK_PATTERN = re.compile(r"^\d{4}-\d{2}$")

_SHORT_TAGS = {
    "ByCondition": "OutByCondition",
    "ByMinPrice": "OutByMinPrice",
}
_FILE_TAGS = {category: short for short, category in _SHORT_TAGS.items()}

_NEW_NAME = re.compile(
    r"^(?P<kind>discount_project|week_discount|discount_hist)"
    rf"_(?P<flow>{FLOW_TOKEN})"
    r"(?:_(?P<tag>[A-Za-z][A-Za-z0-9]*))?"
    r"_(?P<week>\d{4}-\d{2})"
    r"(?:_r(?P<rev>\d{1,4}))?"
    r"(?P<rlsd>_rlsd)?"
    r"\.(?P<ext>disc_proj|csv)$"
)
_DUP_SUFFIX = r"(?:\s*\(\d+\))?"
_LEGACY_PROJECT = re.compile(
    rf"^discount_project_(?P<flow>{FLOW_TOKEN}?)"
    r"(?:_(?P<tag>[A-Za-z][A-Za-z0-9]*))?"
    r"_(?P<week>\d{1,2})(?:_(?P<rev>\d+))?"
    rf"{_DUP_SUFFIX}\.disc_proj$"
)
_LEGACY_HIST = re.compile(
    r"^discount_hist_(?P<week>\d{4}-\d{2})"
    rf"(?:_(?P<flow>{FLOW_TOKEN}?))?"
    r"(?:_(?P<tag>[A-Za-z][A-Za-z0-9]*))?"
    rf"{_DUP_SUFFIX}\.csv$"
)
_LEGACY_HIST_ALL_BS = re.compile(
    rf"^discount_hist_all_bs_(?P<week>\d{{4}}-\d{{2}}){_DUP_SUFFIX}\.csv$"
)
_LEGACY_WEEK_DISCOUNT = re.compile(
    r"^week_discount_(?P<week>\d{4}-\d{2})"
    rf"(?:[-_ ](?P<flow>{FLOW_TOKEN}))?"
    rf"{_DUP_SUFFIX}\.csv$"
)


@dataclass(frozen=True)
class ParsedName:
    kind: str
    flow_id: Optional[str]
    tag: str
    week: str
    revision: Optional[int]
    released: bool = False
    legacy: bool = False


def normalize_tag(tag: Optional[str]) -> str:
    """App category for a tag (``ByCondition`` -> ``OutByCondition``)."""
    text = str(tag or "").strip()
    return _SHORT_TAGS.get(text, text)


def file_tag(tag: Optional[str]) -> str:
    """Tag as written in file names (``OutByCondition`` -> ``ByCondition``)."""
    text = normalize_tag(tag)
    return _FILE_TAGS.get(text, text)


def build_name(
    kind: str,
    flow_id: str,
    tag: Optional[str],
    week: str,
    revision: Optional[int] = None,
    released: bool = False,
) -> str:
    """Return a file name following the naming rule.

    Without ``revision`` (local downloads) the ``rNN`` part is omitted.
    """
    if kind not in KIND_EXTENSIONS:
        raise ValueError(f"Unknown file kind: {kind!r}")
    parts = [kind, str(flow_id)]
    tag_text = file_tag(tag)
    if tag_text:
        parts.append(tag_text)
    parts.append(str(week))
    if revision is not None:
        parts.append(f"r{int(revision):02d}")
    if released:
        parts.append(RELEASED_POSTFIX)
    return "_".join(parts) + KIND_EXTENSIONS[kind]


def parse_name(name: str) -> Optional[ParsedName]:
    """Parse a new-style or legacy name; ``None`` when it does not match."""
    text = str(name or "").strip()
    match = _LEGACY_HIST_ALL_BS.match(text)
    if match:
        return ParsedName(
            KIND_DISCOUNT_HIST, None, ALL_TAG, match.group("week"), None, legacy=True
        )
    match = _NEW_NAME.match(text)
    if match:
        kind = match.group("kind")
        if KIND_EXTENSIONS[kind] != "." + match.group("ext"):
            return None
        return ParsedName(
            kind=kind,
            flow_id=match.group("flow"),
            tag=normalize_tag(match.group("tag")),
            week=match.group("week"),
            revision=int(match.group("rev")) if match.group("rev") else None,
            released=bool(match.group("rlsd")),
        )
    for pattern, kind in (
        (_LEGACY_PROJECT, KIND_PROJECT),
        (_LEGACY_HIST, KIND_DISCOUNT_HIST),
        (_LEGACY_WEEK_DISCOUNT, KIND_WEEK_DISCOUNT),
    ):
        match = pattern.match(text)
        if not match:
            continue
        groups = match.groupdict()
        rev = groups.get("rev")
        return ParsedName(
            kind=kind,
            flow_id=groups.get("flow") or None,
            tag=normalize_tag(groups.get("tag")),
            week=groups["week"],
            revision=int(rev) if rev else None,
            legacy=True,
        )
    return None


def released_variant(name: str, released: bool) -> str:
    """Same file name with the ``_rlsd`` postfix added or removed."""
    parsed = parse_name(name)
    if parsed is None or parsed.legacy or parsed.flow_id is None:
        raise ValueError(f"Not a flow file name: {name!r}")
    stem, _, ext = name.rpartition(".")
    postfix = f"_{RELEASED_POSTFIX}"
    if parsed.released:
        stem = stem[: -len(postfix)]
    return f"{stem}{postfix if released else ''}.{ext}"


def next_revision(names: Iterable[str]) -> int:
    """Highest ``rNN`` among new-style names plus one (1 when none)."""
    highest = 0
    for name in names:
        parsed = parse_name(name)
        if parsed is None or parsed.legacy or parsed.revision is None:
            continue
        highest = max(highest, parsed.revision)
    return highest + 1


def released_matches(
    names: Iterable[str],
    *,
    kind: str,
    flow_id: str,
    tag: Optional[str] = None,
    week: Optional[str] = None,
) -> list[str]:
    """Released new-style names for ``kind`` / ``flow`` (/ ``tag`` / ``week``), newest revision first."""
    tag_text = None if tag is None else normalize_tag(tag)
    found: list[tuple[int, str]] = []
    for name in names:
        parsed = parse_name(name)
        if parsed is None or parsed.legacy or not parsed.released:
            continue
        if parsed.kind != kind or parsed.flow_id != flow_id:
            continue
        if tag_text is not None and parsed.tag != tag_text:
            continue
        if week is not None and parsed.week != week:
            continue
        found.append((parsed.revision or 0, name))
    return [name for _, name in sorted(found, reverse=True)]


def pick_by_tag_preference(
    names: Sequence[str], tag_preference: Sequence[str]
) -> Optional[str]:
    """First name whose tag comes earliest in ``tag_preference``; order within a tag is kept."""
    parsed = [(name, parse_name(name)) for name in names]
    for tag in tag_preference:
        wanted = normalize_tag(tag)
        for name, info in parsed:
            if info is not None and info.tag == wanted:
                return name
    return None


def detect_flow_tags(name: str, flow_ids: Iterable[str]) -> list[str]:
    """Flow ids that appear as separate tokens in ``name`` (case-insensitive)."""
    text = str(name or "")
    found: list[str] = []
    for flow_id in flow_ids:
        pattern = (
            r"(?<![A-Za-z0-9-])" + re.escape(str(flow_id)) + r"(?![A-Za-z0-9-])"
        )
        if re.search(pattern, text, flags=re.IGNORECASE):
            found.append(str(flow_id))
    return found


def foreign_flow_tags(name: str, current_flow_id: str, flow_ids: Iterable[str]) -> list[str]:
    """Other flows' tags found in ``name`` when the current flow's tag is absent."""
    tags = detect_flow_tags(name, flow_ids)
    if any(tag.lower() == str(current_flow_id).lower() for tag in tags):
        return []
    return [tag for tag in tags if tag.lower() != str(current_flow_id).lower()]


def is_week(text: str) -> bool:
    return bool(WEEK_PATTERN.match(str(text or "")))
