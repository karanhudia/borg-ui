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

HISTORY_KINDS: frozenset[str] = frozenset({"history_index", "history_merge"})

# Of the two, only history_index is a Pro feature. history_merge is what
# deletes the rows of archives that are gone from the repository, and
# apply_listing deliberately leaves that deletion to it, so a Community
# install that dropped it would keep every pruned archive in the table.
PLAN_GATED_KINDS: frozenset[str] = frozenset({"history_index"})


def chain_for(
    kind: str, *, available: Optional[set[str]] = None, history: bool = True
) -> list[str]:
    """Return the follow-up kinds for `kind`, in order.

    `available` drops kinds without an executor. `history=False` drops the
    plan gated kinds for Community installs (spec 11.2): the stage does not
    exist rather than being created and skipped (Appendix B). history_merge
    is not gated; see PLAN_GATED_KINDS.
    """
    validate_kind(kind)
    chain = list(FOLLOWUPS[kind])
    if available is not None:
        chain = [k for k in chain if k in available]
    if not history:
        chain = [k for k in chain if k not in PLAN_GATED_KINDS]
    return chain


def history_enabled(db) -> bool:
    """True when the current plan includes the archive_history feature
    (spec 11.2). Imported lazily: app.core.features pulls in the licensing
    service, which must not be an import-time dependency of the runner."""
    from app.core.features import Plan, get_current_plan, plan_includes

    return plan_includes(get_current_plan(db), Plan.PRO)
