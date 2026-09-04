"""Normalise `borg diff --json-lines` and `borg list --json-lines` output
into ChangeRecord values (spec 8.3). Borg 1.4 and Borg 2.0 use different key
names for several change types; see tests/fixtures/borg_output/README.md
for the real shapes this parser was built against."""

import json
from dataclasses import dataclass
from typing import Optional

PRESENCE_TYPES = {
    "added": "added",
    "removed": "removed",
    "added directory": "added",
    "removed directory": "removed",
    "added link": "added",
    "removed link": "removed",
}
DIRECTORY_TYPES = {"added directory", "removed directory"}
MODE_TYPES = {"mode", "changed mode"}
OWNER_TYPES = {"owner", "changed owner"}


@dataclass(frozen=True)
class ChangeRecord:
    path: str
    change: str  # added | removed | modified
    size_before: Optional[int] = None
    size_after: Optional[int] = None
    mode_changed: bool = False
    owner_changed: bool = False
    # modified regular files only: bytes added minus bytes removed, from
    # borg diff. Absolute sizes are resolved by the executor from the last
    # known size of the path in the series.
    size_delta: Optional[int] = None
    is_directory: bool = False


def _int(value) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _load(line: str) -> Optional[dict]:
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _presence_size(c: dict, kind: str) -> Optional[int]:
    """Borg 1 reports a plain `size`; Borg 2 reports `added`/`removed`
    counts on the same entry types (README)."""
    if "size" in c:
        return _int(c.get("size"))
    if kind == "added":
        return _int(c.get("added"))
    if kind == "removed":
        return _int(c.get("removed"))
    return None


def parse_diff_line(line: str) -> Optional[ChangeRecord]:
    data = _load(line)
    if data is None:
        return None
    path = data.get("path")
    changes = data.get("changes")
    if not path or not isinstance(changes, list) or not changes:
        return None
    changes = [c for c in changes if isinstance(c, dict)]
    types = [c.get("type", "") for c in changes]
    flags = {
        "mode_changed": any(t in MODE_TYPES for t in types),
        "owner_changed": any(t in OWNER_TYPES for t in types),
    }
    for c in changes:
        kind = c.get("type", "")
        if kind in PRESENCE_TYPES:
            change = PRESENCE_TYPES[kind]
            size = _presence_size(c, kind)
            return ChangeRecord(
                path,
                change,
                size_before=size if change == "removed" else None,
                size_after=size if change == "added" else None,
                is_directory=kind in DIRECTORY_TYPES,
                **flags,
            )
    for c in changes:
        if c.get("type") == "modified":
            added = _int(c.get("added")) or 0
            removed = _int(c.get("removed")) or 0
            return ChangeRecord(path, "modified", size_delta=added - removed, **flags)
    if "changed link" in types:
        return ChangeRecord(path, "modified", **flags)
    # Only metadata changed (mode, owner, mtime, ctime, or a directory's own
    # timestamp): content is the same.
    return ChangeRecord(path, "modified", size_delta=0, **flags)


def parse_list_line(line: str) -> Optional[ChangeRecord]:
    """A full listing entry becomes an `added` record (first archive in a
    series, spec 6.5). Only regular files carry a size; a symlink's `size`
    in the listing is its target string length, not real content."""
    data = _load(line)
    if data is None:
        return None
    path = data.get("path")
    if not path:
        return None
    entry_type = data.get("type", "-")
    return ChangeRecord(
        path,
        "added",
        size_after=_int(data.get("size")) if entry_type == "-" else None,
        is_directory=entry_type == "d",
    )
