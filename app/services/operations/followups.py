"""Follow-up chains (spec section 7.4). Created by the runner when a parent
operation reaches a success state. Phase 2 adds plan awareness here
(spec 11.2): history kinds are dropped for Community installs."""

from typing import Any, Literal, Mapping, Optional

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
    "archive_sync": ("prune_compare",),
    "history_index": (),
    "history_merge": (),
    "prune_compare": (),
}

HISTORY_KINDS: frozenset[str] = frozenset({"history_index", "history_merge"})

# Of the two, only history_index writes the change rows. history_merge is
# what deletes the rows of archives that are gone from the repository, and
# apply_listing deliberately leaves that deletion to it, so an install that
# dropped it would keep every pruned archive in the table. The name is
# historical: these kinds were plan gated until 2026-09-21, and what drops
# history_index now is the executor, not the plan.
PLAN_GATED_KINDS: frozenset[str] = frozenset({"history_index"})


def followup_wanted(kind: str, operation) -> bool:
    """Spec 4.5: a retention comparison is worth four dry runs only when the
    listing that finished changed the archive set. Every other follow-up is
    unconditional."""
    if kind != "prune_compare":
        return True
    result = operation.result or {}
    return bool(result.get("new")) or bool(result.get("removed_archive_ids"))


def chain_for(
    kind: str,
    *,
    available: Optional[set[str]] = None,
    history: bool = True,
    mode: str = DEFAULT_INDEX_MODE,
) -> list[str]:
    """Return the follow-up kinds for `kind`, in order.

    `available` drops kinds without an executor. `history=False` drops the
    kinds that write change history when this repository cannot have it
    built (an agent that does not produce the listing): the stage does not
    exist rather than being created and skipped (Appendix B). The plan no
    longer decides this; the index is built on every plan and
    `archive_history` gates the reads instead (spec
    2026-09-21-community-teasers-and-feature-trials, section 2).
    history_merge is never dropped; see PLAN_GATED_KINDS. `mode` drops the kinds the
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
    available: Optional[set[str]] = None,
) -> list[str]:
    """`chain_for` with this install's executors, this repository's index
    mode, and this repository's executor. Every follow-up site calls this,
    so the gates are read in one place rather than six.

    The plan is not one of them: history is indexed on every plan and
    `archive_history` gates who may read the rows. What can still drop the
    history stage is the executor, a repository executed by a managed agent
    whose agent cannot produce the change listing (`history_capability`),
    and the index mode: a stage that will never run does not exist.

    `available` is for the runner, which carries its own registry and must
    not be told about executors it was not given.
    """
    from app.services.operations.executors import registered_kinds

    history = history_possible_for(db, repository_id)
    if available is None:
        available = registered_kinds()
    return chain_for(
        kind,
        available=available,
        history=history,
        mode=mode_for_repository(db, repository_id),
    )


def queued_chain_covering(
    db, repository_id: Optional[int], kinds: list[str]
) -> Optional[list]:
    """The queued rows that already cover every kind in `kinds` on this
    repository and will run: each one's dependency chain bottoms out in a
    satisfied (or absent) row rather than a failed one. None when any kind
    is uncovered.

    A queued refresh starts after now, so it sees everything the caller's
    operation just did. Enqueueing another copy behind it would list, fold,
    and count the same repository twice within seconds: a plan backup with
    inline prune and compact produced three stats refreshes and two archive
    listings per run before this check.
    """
    from app.database.models import Operation
    from app.services.operations.vocab import SUCCESS_STATUSES

    queued = (
        db.query(Operation)
        .filter(Operation.repository_id == repository_id, Operation.status == "queued")
        .all()
    )
    by_id = {op.id: op for op in queued}

    def will_run(op) -> bool:
        seen: set[int] = set()
        while op.depends_on_id is not None:
            parent = by_id.get(op.depends_on_id)
            if parent is None:
                dependency = db.get(Operation, op.depends_on_id)
                if dependency is None:
                    # The runner skips a row whose dependency is gone.
                    return False
                # The runner's skip semantics (#917): an intentional skip
                # satisfies; dependency_failed propagates.
                return dependency.status in SUCCESS_STATUSES or (
                    dependency.status == "skipped"
                    and dependency.skip_reason != "dependency_failed"
                )
            if parent.id in seen:
                return False
            seen.add(parent.id)
            op = parent
        return True

    live = [op for op in queued if will_run(op)]
    if not all(kind in {op.kind for op in live} for kind in kinds):
        return None
    return live


def followups_already_queued(
    db, repository_id: Optional[int], kinds: list[str]
) -> bool:
    return not kinds or queued_chain_covering(db, repository_id, kinds) is not None


def enqueue_followups(
    db,
    operation,
    *,
    depends_on_id: Optional[int] = None,
    available: Optional[set[str]] = None,
    commit: bool = True,
) -> list:
    """Enqueue the follow-up chain a finished `operation` calls for (spec
    7.4), unless an equivalent chain already waits queued on the repository
    (see `queued_chain_covering`). Every site that reacts to a finished
    operation goes through here, so the dedupe is read in one place.

    When the waiting chain belongs to the same run (a plan backup's chain,
    found by the inline prune or compact that ran after it), its head is
    re-hung on this operation: the refresh is the last thing a run does, and
    the row reads that way (backup, prune, compact, then the refresh steps)
    instead of showing the refresh under the backup with maintenance after.

    `depends_on_id` is the row the chain hangs off; callers pass the finished
    row's id, or None when the row failed but still changed the repository
    (a partial wipe, a backup whose archive exists) and the chain must not
    inherit that failure.
    """
    from app.services.operations.enqueue import enqueue_chain

    kinds = chain_for_repository(
        db, operation.kind, operation.repository_id, available=available
    )
    kinds = [k for k in kinds if followup_wanted(k, operation)]
    if not kinds:
        return []
    covering = queued_chain_covering(db, operation.repository_id, kinds)
    if covering is not None:
        if depends_on_id is not None:
            queued_ids = {op.id for op in covering}
            heads = [
                op
                for op in covering
                if op.run_id == operation.run_id
                and op.depends_on_id not in queued_ids
                and op.depends_on_id != depends_on_id
            ]
            for head in heads:
                head.depends_on_id = depends_on_id
            if heads and commit:
                db.commit()
        return []
    return enqueue_chain(
        db,
        kinds,
        repository_id=operation.repository_id,
        trigger="followup",
        run_id=operation.run_id,
        depends_on_id=depends_on_id,
        triggered_by_user_id=operation.triggered_by_user_id,
        scheduled_job_id=operation.scheduled_job_id,
        backup_plan_run_id=operation.backup_plan_run_id,
        commit=commit,
    )


def history_enabled(db) -> bool:
    """True when the current plan includes the archive_history feature
    (spec 11.2). Imported lazily: app.core.features pulls in the licensing
    service, which must not be an import-time dependency of the runner."""
    from app.core.features import Plan, get_current_plan, plan_includes

    return plan_includes(get_current_plan(db), Plan.PRO)


HistoryCapability = Literal["available", "plan_locked", "agent_unsupported"]
HISTORY_AVAILABLE: HistoryCapability = "available"
HISTORY_PLAN_LOCKED: HistoryCapability = "plan_locked"
HISTORY_AGENT_UNSUPPORTED: HistoryCapability = "agent_unsupported"


def history_capability(
    db,
    repository,
    *,
    history: Optional[bool] = None,
    agents: Optional[Mapping[int, Any]] = None,
) -> HistoryCapability:
    """Whether change history can be built for `repository`, and if not, why.

    `agent_unsupported`: the repository is executed by a managed agent that
    does not advertise the `repository.diff` job (an agent from before
    0.1.6, or none assigned), so `history_index` would only ever skip it:
    the server cannot reach an agent's repository, and only the agent can
    produce the listing. An agent that advertises the job builds it on its
    machine, and the plan decides as it does for any repository.
    `plan_locked`: the plan lacks the feature (spec 11.2). The executor is
    read first: its reason outlasts any plan change, and a plan chip on
    such a repository would promise what an upgrade cannot deliver.
    Derived at read time from the executor, the agent's capabilities and
    the plan rather than stored: they are facts about the repository, not
    about one run. `history` is the plan gate when the caller already read
    it, `agents` a page's machines by id when it loaded them once (the
    repositories hub); single-repository callers leave both out.
    """
    from app.services.repository_executor import (
        AGENT_DIFF_JOB_KIND,
        agent_supports_job,
        is_agent_executor,
    )

    if (
        repository is not None
        and is_agent_executor(repository)
        and not agent_supports_job(db, repository, AGENT_DIFF_JOB_KIND, agents=agents)
    ):
        return HISTORY_AGENT_UNSUPPORTED
    if history is None:
        history = history_enabled(db)
    if not history:
        return HISTORY_PLAN_LOCKED
    return HISTORY_AVAILABLE


def history_possible(db, repository) -> bool:
    """The `history` argument for `chain_for`: the history stage exists for
    this repository (it is not merely created and skipped, Appendix B).
    Plan independent since 2026-09-21: only the executor can refuse."""
    return history_capability(db, repository, history=True) == HISTORY_AVAILABLE


def history_possible_for(db, repository_id: Optional[int]) -> bool:
    """`history_possible` for a caller holding only the repository id (the
    runner, the follow-up enqueuers). A missing repository reads as
    possible; the executor skips its chain as `repository_missing` anyway."""
    from app.database.models import Repository

    repository = (
        db.get(Repository, repository_id) if repository_id is not None else None
    )
    return history_possible(db, repository)


def enqueue_backup_followups(
    db,
    repository_id: int,
    *,
    scheduled_job_id: Optional[int] = None,
    backup_plan_run_id: Optional[int] = None,
    commit: bool = True,
) -> list:
    """Enqueue the `backup` chain for a backup that completed outside the
    runner: an agent completion report for a row written before phase 8, or
    for an operation the runner is no longer running (failed by restart
    recovery and finished by the agent afterwards). Every other backup gets
    its chain from the runner (spec 7.4).

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
    kinds = chain_for_repository(db, "backup", repository_id)
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
