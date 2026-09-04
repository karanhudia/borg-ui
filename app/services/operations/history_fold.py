"""Fold one archive's change delta into the delta that follows it
(spec section 8.4). Used by history_merge when a pruned archive's rows move
to its successor, and by the changes route when `compare_to` is older than
the predecessor (spec 9.2). Pure functions over plain values."""

from dataclasses import dataclass, replace
from typing import Iterable, Optional

from app.database.models import ArchiveChange


@dataclass(frozen=True)
class Change:
    path: str
    change: str  # added | removed | modified | summary
    size_before: Optional[int] = None
    size_after: Optional[int] = None
    mode_changed: bool = False
    owner_changed: bool = False
    summary_count: Optional[int] = None


def _flags(older: Change, newer: Change) -> dict:
    return {
        "mode_changed": older.mode_changed or newer.mode_changed,
        "owner_changed": older.owner_changed or newer.owner_changed,
    }


def fold_pair(older: dict[str, Change], newer: dict[str, Change]) -> dict[str, Change]:
    """Return the delta from older's base to newer's target.

    Rows follow the spec 8.4 table. Pairs the table does not list cannot
    occur in a consistent sequence (added after added, removed after
    removed, added after modified, modified after removed); newer wins for
    those so a corrupt history never raises.
    """
    result: dict[str, Change] = dict(newer)
    for path, r in older.items():
        s = newer.get(path)
        if r.change == "summary":
            if s is None:
                result[path] = r
            else:
                result[path] = replace(
                    s, summary_count=(s.summary_count or 0) + (r.summary_count or 0)
                )
            continue
        if s is None:
            result[path] = r
            continue
        if s.change == "summary":
            continue
        flags = _flags(r, s)
        if r.change == "added":
            if s.change == "modified":
                result[path] = replace(s, change="added", size_before=None, **flags)
            elif s.change == "removed":
                del result[path]
        elif r.change == "modified":
            if s.change in ("modified", "removed"):
                result[path] = replace(s, size_before=r.size_before, **flags)
        elif r.change == "removed":
            if s.change == "added":
                result[path] = replace(
                    s,
                    change="modified",
                    size_before=r.size_before,
                    size_after=s.size_after,
                    **flags,
                )
    return result


def fold_sequence(deltas: Iterable[dict[str, Change]]) -> dict[str, Change]:
    """Fold deltas oldest first into one delta. Empty input gives {}."""
    result: Optional[dict[str, Change]] = None
    for delta in deltas:
        result = delta if result is None else fold_pair(result, delta)
    return result if result is not None else {}


def change_from_row(row: ArchiveChange) -> Change:
    return Change(
        path=row.path,
        change=row.change,
        size_before=row.size_before,
        size_after=row.size_after,
        mode_changed=bool(row.mode_changed),
        owner_changed=bool(row.owner_changed),
        summary_count=row.summary_count,
    )


def rows_to_changes(rows: Iterable[ArchiveChange]) -> dict[str, Change]:
    return {row.path: change_from_row(row) for row in rows}


def change_to_row_dict(change: Change, archive_id: int) -> dict:
    """Mapping for `Session.bulk_insert_mappings(ArchiveChange, ...)`."""
    return {
        "archive_id": archive_id,
        "path": change.path,
        "change": change.change,
        "size_before": change.size_before,
        "size_after": change.size_after,
        "mode_changed": change.mode_changed,
        "owner_changed": change.owner_changed,
        "summary_count": change.summary_count,
    }
