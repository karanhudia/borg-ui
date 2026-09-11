"""Follow-up chains (spec section 7.4). Created by the runner when a parent
operation reaches a success state. Phase 2 adds plan awareness here
(spec 11.2): history kinds are dropped for Community installs."""

from typing import Optional

from app.services.operations.index_mode import (
    DEFAULT_INDEX_MODE,
    filter_kinds,
    mode_for_repository,
)
from app.services.operations.vocab import validate_kind

FOLLOWUPS: dict[str, tuple[str, ...]] = {
    "import_connect": ("stats", "archive_sync", "history_index"),
    "backup": ("archive_sync", "history_merge", "history_index", "stats"),
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
    kind: str,
    *,
    available: Optional[set[str]] = None,
    history: bool = True,
    mode: str = DEFAULT_INDEX_MODE,
) -> list[str]:
    """Return the follow-up kinds for `kind`, in order.

    `available` drops kinds without an executor. `history=False` drops the
    plan gated kinds for Community installs (spec 11.2): the stage does not
    exist rather than being created and skipped (Appendix B). history_merge
    is not gated; see PLAN_GATED_KINDS. `mode` drops the kinds the
    repository's index mode does not refresh (spec 6.8), by the same rule:
    a stage that will never run does not exist.
    """
    validate_kind(kind)
    chain = list(FOLLOWUPS[kind])
    if available is not None:
        chain = [k for k in chain if k in available]
    if not history:
        chain = [k for k in chain if k not in PLAN_GATED_KINDS]
    return filter_kinds(mode, chain)


def chain_for_repository(
    db,
    kind: str,
    repository_id: Optional[int],
    *,
    history: Optional[bool] = None,
    available: Optional[set[str]] = None,
) -> list[str]:
    """`chain_for` with this install's executors, this install's plan, and
    this repository's index mode. Every follow-up site calls this, so the
    two gates are read in one place rather than six.

    `history` is the plan gate; left None it is read here, which goes
    through the licensing service and commits the session. A caller that
    wraps this call in a savepoint reads it beforehand and passes it in.

    `available` is for the runner, which carries its own registry and must
    not be told about executors it was not given.
    """
    from app.services.operations.executors import registered_kinds

    if history is None:
        history = history_enabled(db)
    if available is None:
        available = registered_kinds()
    return chain_for(
        kind,
        available=available,
        history=history,
        mode=mode_for_repository(db, repository_id),
    )


def history_enabled(db) -> bool:
    """True when the current plan includes the archive_history feature
    (spec 11.2). Imported lazily: app.core.features pulls in the licensing
    service, which must not be an import-time dependency of the runner."""
    from app.core.features import Plan, get_current_plan, plan_includes

    return plan_includes(get_current_plan(db), Plan.PRO)


def enqueue_backup_followups(
    db,
    repository_id: int,
    *,
    scheduled_job_id: Optional[int] = None,
    backup_plan_run_id: Optional[int] = None,
    commit: bool = True,
    history: Optional[bool] = None,
) -> list:
    """Enqueue the `backup` chain for a backup that completed outside the
    runner: an agent completion report for a row written before phase 8, or
    for an operation the runner is no longer running (failed by restart
    recovery and finished by the agent afterwards). Every other backup gets
    its chain from the runner (spec 7.4).

    `history` is the plan gate; left None it is read here, which goes
    through the licensing service and commits the session. A caller that
    wraps this call in a savepoint reads it beforehand and passes it in.

    Skipped only when an archive listing is queued and its dependency is
    already satisfied (or absent). Other queued index work cannot replace
    a listing. A running listing may predate this backup and does not count.

    The check is best-effort, like the reconcile scheduler's: a second chain
    from a lost race is one extra listing, serialized per repository by the
    executors and idempotent (archives upsert by id), not a correctness
    problem, so it is not worth a lock or a uniqueness constraint.
    """
    from sqlalchemy import and_, or_
    from sqlalchemy.orm import aliased

    from app.database.models import Operation
    from app.services.operations.enqueue import enqueue_chain
    from app.services.operations.vocab import SUCCESS_STATUSES

    dependency = aliased(Operation)
    queued = (
        db.query(Operation.id)
        .outerjoin(dependency, Operation.depends_on_id == dependency.id)
        .filter(
            Operation.repository_id == repository_id,
            Operation.kind == "archive_sync",
            Operation.status == "queued",
            # Match the runner's corrected skip semantics (#917): an
            # intentional skip satisfies; dependency_failed propagates.
            or_(
                Operation.depends_on_id.is_(None),
                dependency.status.in_(SUCCESS_STATUSES),
                and_(
                    dependency.status == "skipped",
                    or_(
                        dependency.skip_reason.is_(None),
                        dependency.skip_reason != "dependency_failed",
                    ),
                ),
            ),
        )
        .first()
    )
    if queued is not None:
        return []
    if history is None:
        history = history_enabled(db)
    kinds = chain_for_repository(db, "backup", repository_id, history=history)
    if not kinds:
        return []
    return enqueue_chain(
        db,
        kinds,
        repository_id=repository_id,
        trigger="followup",
        scheduled_job_id=scheduled_job_id,
        backup_plan_run_id=backup_plan_run_id,
        commit=commit,
    )
