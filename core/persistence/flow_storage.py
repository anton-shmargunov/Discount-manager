"""
Per-flow Drive layout, revisioned saves and the release mark. No Streamlit imports.

Layout under the Drive root::

    <flow>/<week>/input/
    <flow>/<week>/proj/
    <flow>/<week>/week_discount/
    <flow>/<week>/discount_history/

``<week>`` is the analysed data week W. Revision numbers are unique per flow and
week folder; one released (``_rlsd``) file exists per flow, week, kind and tag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from core.persistence.file_naming import (
    INPUT_FOLDER,
    KIND_DISCOUNT_HIST,
    KIND_FOLDERS,
    KIND_MIME,
    KIND_PROJECT,
    KINDS,
    ParsedName,
    build_name,
    is_week,
    normalize_tag,
    parse_name,
    released_variant,
)
from core.persistence.gdrive import DriveClientError, DriveFile, DriveStore

DEFAULT_LOOKBACK_WEEKS = 6


@dataclass(frozen=True)
class FlowFile:
    file: DriveFile
    folder_id: str
    week_folder: str
    parsed: Optional[ParsedName]

    @property
    def name(self) -> str:
        return self.file.name

    @property
    def released(self) -> bool:
        return bool(self.parsed and self.parsed.released and not self.parsed.legacy)


@dataclass(frozen=True)
class SetItem:
    """One file of a save / release set. ``name_week`` is the week written in the name."""

    kind: str
    tag: str
    name_week: str
    data: bytes


@dataclass
class SaveResult:
    week: str
    revision: int
    names: list[str] = field(default_factory=list)
    released: bool = False
    unreleased: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class FlowStorage:
    """Drive folders and files of one flow."""

    def __init__(self, store: DriveStore, flow_id: str) -> None:
        self.store = store
        self.flow_id = str(flow_id)

    def flow_folder(self, *, create: bool = False) -> Optional[str]:
        return self.store.folder_path([self.flow_id], create=create)

    def weeks(self) -> list[str]:
        """Week folders of this flow, newest first."""
        folder = self.flow_folder()
        if not folder:
            return []
        return sorted(
            (item.name for item in self.store.list_subfolders(folder) if is_week(item.name)),
            reverse=True,
        )

    def week_folder(self, week: str, *, create: bool = False) -> Optional[str]:
        if not is_week(week):
            raise ValueError(f"Week must look like 2026-40, got {week!r}.")
        return self.store.folder_path([self.flow_id, week], create=create)

    def kind_folder(self, week: str, kind: str, *, create: bool = False) -> Optional[str]:
        sub = INPUT_FOLDER if kind == INPUT_FOLDER else KIND_FOLDERS[kind]
        return self.store.folder_path([self.flow_id, week, sub], create=create)

    def kind_files(self, week: str, kind: str) -> list[FlowFile]:
        folder = self.kind_folder(week, kind)
        if not folder:
            return []
        return [
            FlowFile(item, folder, week, parse_name(item.name))
            for item in self.store.list_files(folder)
        ]

    def week_names(self, week: str) -> list[str]:
        names: list[str] = []
        for kind in KINDS:
            names.extend(item.name for item in self.kind_files(week, kind))
        return names

    def next_revision(self, week: str) -> int:
        highest = 0
        for name in self.week_names(week):
            parsed = parse_name(name)
            if parsed and not parsed.legacy and parsed.flow_id == self.flow_id and parsed.revision:
                highest = max(highest, parsed.revision)
        return highest + 1

    def save_input(self, week: str, filename: str, data: bytes) -> DriveFile:
        folder = self.kind_folder(week, INPUT_FOLDER, create=True)
        return self.store.upload_bytes(folder, filename, data, "text/csv")

    def newer_weeks(self, week: str) -> list[str]:
        return [item for item in self.weeks() if item > week]

    def recent_files(
        self, kind: str, *, max_weeks: int = DEFAULT_LOOKBACK_WEEKS
    ) -> list[FlowFile]:
        files: list[FlowFile] = []
        for week in self.weeks()[:max_weeks]:
            files.extend(self.kind_files(week, kind))
        return files

    def list_projects(self, *, max_weeks: int = DEFAULT_LOOKBACK_WEEKS) -> list[FlowFile]:
        """Project files, newest week first; released first within a week."""
        files = [
            item
            for item in self.recent_files(KIND_PROJECT, max_weeks=max_weeks)
            if item.name.lower().endswith(".disc_proj")
        ]
        return sorted(files, key=_project_sort_key)

    def find_released_history(
        self,
        tag_preference: Sequence[str],
        *,
        max_weeks: int = DEFAULT_LOOKBACK_WEEKS,
    ) -> Optional[FlowFile]:
        """Newest released discount history whose tag is in ``tag_preference``.

        Newer target week wins; within a week the earlier tag in the list wins,
        then the higher revision.
        """
        prefs = [normalize_tag(tag) for tag in tag_preference]
        candidates = [
            item
            for item in self.recent_files(KIND_DISCOUNT_HIST, max_weeks=max_weeks)
            if item.released
            and item.parsed is not None
            and item.parsed.flow_id == self.flow_id
            and item.parsed.tag in prefs
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda item: (
                _neg_week(item.parsed.week),
                prefs.index(item.parsed.tag),
                -(item.parsed.revision or 0),
            ),
        )

    def released_in_week(self, week: str, kind: str, tag: str) -> list[FlowFile]:
        wanted = normalize_tag(tag)
        found = [
            item
            for item in self.kind_files(week, kind)
            if item.released
            and item.parsed is not None
            and item.parsed.flow_id == self.flow_id
            and item.parsed.tag == wanted
        ]
        return sorted(found, key=lambda item: -(item.parsed.revision or 0))

    def download(self, item: FlowFile) -> bytes:
        return self.store.download_file(item.folder_id, item.file.id)


def _neg_week(week: str) -> tuple[int, int]:
    try:
        year, num = str(week).split("-", 1)
        return (-int(year), -int(num))
    except ValueError:
        return (0, 0)


def _project_sort_key(item: FlowFile) -> tuple:
    parsed = item.parsed
    revision = parsed.revision if parsed and parsed.revision else 0
    return (
        _neg_week(item.week_folder),
        0 if item.released else (1 if parsed and not parsed.legacy else 2),
        -revision,
        item.name,
    )


def save_set(
    storage: FlowStorage,
    week: str,
    items: Sequence[SetItem],
    *,
    release: bool = False,
) -> SaveResult:
    """Upload ``items`` as one new revision; with ``release`` move the ``_rlsd`` mark to it.

    Order for a release: upload, tag the new files, then untag the previous
    released files of the same kind and tag. A reader never sees zero released
    files; if it sees two, the higher revision wins.
    """
    if not items:
        raise ValueError("Nothing to save.")
    revision = storage.next_revision(week)
    result = SaveResult(week=week, revision=revision, released=release)
    newer = storage.newer_weeks(week)
    if release and newer:
        result.warnings.append(
            f"Flow {storage.flow_id} already has newer week folder(s): {', '.join(newer)}. "
            "Sessions started there may have used the earlier release."
        )
    uploaded: list[tuple[SetItem, str, DriveFile]] = []
    for item in items:
        folder = storage.kind_folder(week, item.kind, create=True)
        name = build_name(item.kind, storage.flow_id, item.tag, item.name_week, revision)
        uploaded.append((item, folder, storage.store.upload_bytes(folder, name, item.data, KIND_MIME[item.kind])))
    if not release:
        result.names = [saved.name for _, _, saved in uploaded]
        result.warnings.extend(storage.store.warnings)
        storage.store.warnings.clear()
        return result
    for item, folder, saved in uploaded:
        renamed = storage.store.rename_file(folder, saved.id, released_variant(saved.name, True))
        result.names.append(renamed.name)
    for item, folder, saved in uploaded:
        for old in storage.released_in_week(week, item.kind, item.tag):
            if old.parsed is None or old.parsed.revision == revision:
                continue
            try:
                storage.store.rename_file(
                    old.folder_id, old.file.id, released_variant(old.name, False)
                )
                result.unreleased.append(old.name)
            except DriveClientError as exc:
                result.warnings.append(f"Could not remove the release mark from {old.name}: {exc}")
    result.warnings.extend(storage.store.warnings)
    storage.store.warnings.clear()
    return result


def history_tag_preference(category: str, all_tag: str = "ALL") -> list[str]:
    """Discount-history tags to try for next week's default, best first."""
    prefs = [all_tag, normalize_tag(category), ""]
    seen: list[str] = []
    for tag in prefs:
        if tag not in seen:
            seen.append(tag)
    return seen
