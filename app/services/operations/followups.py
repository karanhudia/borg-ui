"""Follow-up chains (spec section 7.4). Created by the runner when a parent
operation reaches a success state. Phase 2 adds plan awareness here
(spec 11.2): history kinds are dropped for Community installs."""

from typing import Optional

from app.services.operations.vocab import validate_kind

FOLLOWUPS: dict[str, tuple[str, ...]] = {
    "import_connect": ("stats", "archive_sync", "history_index"),
    "backup": ("archive_sync", "history_index", "stats"),
    "prune": ("archive_sync", "history_merge", "stats"),
    "delete_archive": ("archive_sync", "history_merge", "stats"),
    "compact": ("stats",),
    "check": (),
    "wipe": ("archive_sync", "history_merge", "stats"),
    "restore": (),
    "restore_check": (),
    "rclone_sync": (),
    "package_install": (),
    "stats": (),
    "archive_sync": (),
    "history_index": (),
    "history_merge": (),
}


def chain_for(kind: str, *, available: Optional[set[str]] = None) -> list[str]:
    """Return the follow-up kinds for `kind`, in order.

    When `available` is given (the runner passes its registered executor
    kinds), kinds without an executor are dropped so no row is created that
    can never run.
    """
    validate_kind(kind)
    chain = list(FOLLOWUPS[kind])
    if available is not None:
        chain = [k for k in chain if k in available]
    return chain
