"""Per-repository index mode (spec section 6.8).

The mode says how much derived data a repository keeps up to date. It is
applied in exactly two places, `followups.chain_for` and
`reconcile.reconcile_kinds`, so a stage a mode excludes is never created and
then skipped (the Community rule in spec 11.2, Appendix B). This module owns
the table from 6.8 and nothing else.
"""

from typing import Iterable, Optional

DEFAULT_INDEX_MODE = "full"
INDEX_MODES: tuple[str, ...] = ("full", "archives", "off")

# The four kinds the mode governs. Anything else in a chain is work someone
# asked for and is never dropped here.
INDEX_KINDS: frozenset[str] = frozenset(
    {"stats", "archive_sync", "history_index", "history_merge"}
)

# Spec 6.8: what each mode keeps refreshing.
MODE_KINDS: dict[str, frozenset[str]] = {
    "full": frozenset({"stats", "archive_sync", "history_index", "history_merge"}),
    "archives": frozenset({"stats", "archive_sync"}),
    "off": frozenset(),
}


def normalize(mode: Optional[str]) -> str:
    """A mode this version understands. A null column (a row that predates
    the column) and an unrecognised value both read as `full`: indexing
    everything is the reading that keeps the repository working."""
    return mode if mode in MODE_KINDS else DEFAULT_INDEX_MODE


def mode_of(repository) -> str:
    return normalize(getattr(repository, "index_mode", None))


def mode_for_repository(db, repository_id: Optional[int]) -> str:
    """The mode of one repository, by id, for the follow-up chain. Work with
    no repository (a package install) is never index work, so it reads as
    the default."""
    if repository_id is None:
        return DEFAULT_INDEX_MODE
    from app.database.models import Repository

    value = (
        db.query(Repository.index_mode).filter(Repository.id == repository_id).scalar()
    )
    return normalize(value)


def allows(mode: str, kind: str) -> bool:
    if kind not in INDEX_KINDS:
        return True
    return kind in MODE_KINDS[normalize(mode)]


def filter_kinds(mode: str, kinds: Iterable[str]) -> list[str]:
    """`kinds` minus the index kinds this mode does not refresh."""
    resolved = normalize(mode)
    return [k for k in kinds if allows(resolved, k)]


def indexes_history(mode: str) -> bool:
    """True when the mode keeps file history (spec 6.5) up to date."""
    return "history_index" in MODE_KINDS[normalize(mode)]
