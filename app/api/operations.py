"""Operations API (spec section 9.1)."""

import os
from datetime import datetime, timedelta
from time import monotonic
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, text
from sqlalchemy.orm import Session

from app.api.activity import _paginate_log_text
from app.api.archive_index import sync_state_from
from app.core.security import (
    check_repo_access,
    get_current_admin_user,
    get_current_download_user,
    get_current_user,
    require_any_role,
)
from app.database.database import get_db
from app.database.models import (
    Archive,
    Operation,
    Repository,
    SystemSettings,
    User,
    UserRepositoryPermission,
    utc_now,
)
from app.services.log_policy import get_log_save_policy, job_has_logs_by_policy
from app.services.operations.followups import (
    HistoryCapability,
    history_capability,
    history_enabled,
)
from app.services.operations.lanes import lane_free, running_count
from app.services.operations.models import is_terminal, serialize_operation
from app.services.operations.index_mode import mode_of as index_mode_of
from app.services.operations.reconcile import (
    DEFAULT_INTERVAL_MINUTES,
    enqueue_reconcile_runs,
)
from app.services.operations.runner import operation_runner
from app.services.operations.vocab import INDEX_KINDS, SUCCESS_STATUSES

router = APIRouter()

MAX_LIMIT = 500
RECENT_WINDOW = timedelta(seconds=60)
NOT_FOUND = {"key": "backend.errors.operations.notFound"}
ALREADY_FINISHED = {"key": "backend.errors.operations.alreadyFinished"}


class OperationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activity_key: Optional[str] = None
    id: int
    type: str
    kind: str
    category: str
    status: str
    trigger: str
    priority: int
    run_id: str
    depends_on_id: Optional[int] = None
    repository_id: Optional[int] = None
    repository: Optional[str] = None
    repository_path: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    error_message: Optional[str] = None
    skip_reason: Optional[str] = None
    log_file_path: Optional[str] = None
    triggered_by: str = "manual"
    schedule_id: Optional[int] = None
    schedule_name: Optional[str] = None
    backup_plan_id: Optional[int] = None
    backup_plan_run_id: Optional[int] = None
    backup_plan_name: Optional[str] = None
    archive_name: Optional[str] = None
    archive_pruned_at: Optional[datetime] = None
    package_name: Optional[str] = None
    has_logs: bool = False
    progress_percent: Optional[float] = None
    progress_current: Optional[int] = None
    progress_total: Optional[int] = None
    progress_message: Optional[str] = None
    execution_mode: Optional[str] = None
    params: Optional[dict] = None
    result: Optional[dict] = None
    followups: list["OperationItem"] = Field(default_factory=list)


OperationItem.model_rebuild()


class OperationDetail(OperationItem):
    run: list[OperationItem] = Field(default_factory=list)


class OperationListResponse(BaseModel):
    items: list[OperationItem]
    next_cursor: Optional[int] = None


class QueueLimits(BaseModel):
    index_workers: int
    index_running: int
    max_concurrent_backups: int
    max_concurrent_scheduled_backups: int
    max_concurrent_scheduled_checks: int


class QueueRepository(BaseModel):
    repository_id: Optional[int]
    repository_name: str
    lane_busy: bool
    operations: list[OperationItem]


class QueueResponse(BaseModel):
    repositories: list[QueueRepository]
    limits: QueueLimits
    paused: bool


class LimitsUpdate(BaseModel):
    index_workers: int = Field(ge=1, le=32)


class HistorySummary(BaseModel):
    indexed: int = 0
    pending: int = 0
    failed: int = 0
    skipped: int = 0
    truncated: int = 0
    rows: int = 0


class HubRepository(BaseModel):
    """One repository's derived data at rest (spec 6.4, 6.5): how fresh the
    archive list is, how much of the file history is built, and how big it
    has grown. The queue route carries what is happening; this carries what
    the last runs left behind."""

    repository_id: int
    repository_name: str
    repository_type: Optional[str] = None
    # Spec 6.8. Defaulted rather than optional so a client mid-deploy reads
    # the value every install had before the mode existed.
    index_mode: str = "full"
    sync_state: str
    last_synced_at: Optional[datetime] = None
    last_stats_at: Optional[datetime] = None
    last_history_at: Optional[datetime] = None
    archives: int = 0
    history: HistorySummary
    # Whether the history stage exists for this repository: `available`,
    # `plan_locked`, or `agent_unsupported` (a managed agent's repository
    # cannot be diffed). The board offers no history stage otherwise.
    history_capability: HistoryCapability = "available"


class HubTotals(BaseModel):
    repositories: int
    archives: int
    history_rows: int
    # On-disk size of the archive_changes table when the engine can report
    # it (PostgreSQL always, SQLite only with the dbstat module). Null means
    # unknown, never zero.
    history_bytes: Optional[int] = None


class HubResponse(BaseModel):
    repositories: list[HubRepository]
    totals: HubTotals
    last_reconcile_at: Optional[datetime] = None
    reconcile_interval_minutes: int
    history_available: bool


class HubArchive(BaseModel):
    id: int
    name: str
    start: datetime
    history_attempts: int = 0
    history_rows: Optional[int] = None


class HubRepositoryDetail(BaseModel):
    repository_id: int
    failed_archives: list[HubArchive]
    truncated_archives: list[HubArchive]


HUB_DETAIL_LIMIT = 50


# -- helpers ---------------------------------------------------------------------


def _repositories_by_id(db: Session, ops: list[Operation]) -> dict[int, Repository]:
    ids = {op.repository_id for op in ops if op.repository_id is not None}
    if not ids:
        return {}
    return {r.id: r for r in db.query(Repository).filter(Repository.id.in_(ids)).all()}


def _item(op: Operation, repos: dict[int, Repository], policy: str) -> dict:
    repo = repos.get(op.repository_id) if op.repository_id is not None else None
    has_logs = job_has_logs_by_policy(
        op, policy, output_text=[op.error_message], file_path=op.log_file_path
    )
    return serialize_operation(
        op,
        repository_name=repo.name if repo else None,
        repository_path=repo.path if repo else None,
        has_logs=has_logs,
    )


def _get_or_404(db: Session, operation_id: int) -> Operation:
    op = db.get(Operation, operation_id)
    if op is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return op


def _get_operation_with_access(
    db: Session, user: User, operation_id: int, required_role: str
) -> Operation:
    """Load a row and enforce repository RBAC. Rows without a repository
    (system kinds) are readable by any user and controllable by admins."""
    op = _get_or_404(db, operation_id)
    if op.repository_id is not None:
        repo = db.get(Repository, op.repository_id)
        if repo is not None:
            check_repo_access(db, user, repo, required_role)
    elif required_role != "viewer":
        require_any_role(user, "admin")
    return op


def _require_logs_by_policy(db: Session, op: Operation) -> None:
    """Serve operation logs only when the save policy says they exist, so the
    `has_logs` flag on the list routes and these routes cannot disagree."""
    if not job_has_logs_by_policy(
        op,
        get_log_save_policy(db),
        output_text=[op.error_message],
        file_path=op.log_file_path,
    ):
        raise HTTPException(status_code=404, detail=NOT_FOUND)


def accessible_repository_ids(db: Session, user: User) -> Optional[set]:
    """Repository ids the user may view, or None for "all" (admin or a
    wildcard `all_repositories_role` grant)."""
    if user.role == "admin" or getattr(user, "all_repositories_role", None):
        return None
    return {
        p.repository_id
        for p in db.query(UserRepositoryPermission).filter_by(user_id=user.id).all()
    }


def _scope_to_accessible_repos(q, accessible: Optional[set]):
    """Restrict an Operation query to rows the user may see: system rows
    (no repository) plus rows for repositories they're permitted on."""
    if accessible is None:
        return q
    return q.filter(
        (Operation.repository_id.is_(None)) | (Operation.repository_id.in_(accessible))
    )


def _settings_row(db: Session) -> SystemSettings:
    settings = db.query(SystemSettings).first()
    if settings is None:
        settings = SystemSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _limits(db: Session, settings: SystemSettings) -> QueueLimits:
    return QueueLimits(
        index_workers=(
            settings.index_workers if settings.index_workers is not None else 2
        ),
        index_running=running_count(db, kinds=INDEX_KINDS),
        max_concurrent_backups=settings.max_concurrent_backups or 1,
        max_concurrent_scheduled_backups=settings.max_concurrent_scheduled_backups or 2,
        max_concurrent_scheduled_checks=settings.max_concurrent_scheduled_checks or 4,
    )


def _reconcile_interval(settings: SystemSettings) -> int:
    value = settings.stats_refresh_interval_minutes
    return value if value is not None else DEFAULT_INTERVAL_MINUTES


# The scan below walks the whole archive_changes b-tree on SQLite, and the
# Background work board polls this route every 30 seconds, so the answer is
# measured at most once per interval and shared by every caller.
HISTORY_BYTES_TTL_SECONDS = 300
_history_bytes_cache: Optional[tuple[float, Optional[int]]] = None


def _measure_history_table_bytes(db: Session) -> Optional[int]:
    """Best-effort on-disk size of archive_changes. Returns None when the
    engine cannot say, so the client never renders a made-up number."""
    dialect = db.get_bind().dialect.name
    try:
        if dialect == "postgresql":
            row = db.execute(
                text("SELECT pg_total_relation_size('archive_changes')")
            ).scalar()
        elif dialect == "sqlite":
            row = db.execute(
                text("SELECT SUM(pgsize) FROM dbstat WHERE name = 'archive_changes'")
            ).scalar()
        else:
            return None
    except Exception:
        db.rollback()
        return None
    return int(row) if row is not None else None


def _history_table_bytes(db: Session) -> Optional[int]:
    global _history_bytes_cache
    now = monotonic()
    if _history_bytes_cache is not None:
        measured_at, value = _history_bytes_cache
        if now - measured_at < HISTORY_BYTES_TTL_SECONDS:
            return value
    value = _measure_history_table_bytes(db)
    _history_bytes_cache = (now, value)
    return value


def _latest_completed_by_repository(
    db: Session, kind: str, repository_ids: Optional[set]
) -> dict[int, datetime]:
    q = db.query(Operation.repository_id, func.max(Operation.completed_at)).filter(
        Operation.kind == kind,
        Operation.status.in_(SUCCESS_STATUSES),
        Operation.repository_id.isnot(None),
    )
    if repository_ids is not None:
        q = q.filter(Operation.repository_id.in_(repository_ids))
    rows = q.group_by(Operation.repository_id).all()
    return {repo_id: at for repo_id, at in rows if at is not None}


def _history_by_repository(
    db: Session, repository_ids: Optional[set]
) -> dict[int, dict]:
    def count_state(state: str):
        return func.sum(case((Archive.history_state == state, 1), else_=0))

    q = db.query(
        Archive.repository_id,
        func.count(Archive.id),
        count_state("indexed"),
        count_state("pending"),
        count_state("failed"),
        count_state("skipped"),
        func.sum(case((Archive.history_truncated.is_(True), 1), else_=0)),
        func.coalesce(func.sum(Archive.history_rows), 0),
        func.max(Archive.history_indexed_at),
    )
    if repository_ids is not None:
        q = q.filter(Archive.repository_id.in_(repository_ids))
    rows = q.group_by(Archive.repository_id).all()
    return {
        repo_id: {
            "archives": archives,
            "summary": HistorySummary(
                indexed=indexed or 0,
                pending=pending or 0,
                failed=failed or 0,
                skipped=skipped or 0,
                truncated=truncated or 0,
                rows=int(history_rows or 0),
            ),
            "last_history_at": last_history_at,
        }
        for (
            repo_id,
            archives,
            indexed,
            pending,
            failed,
            skipped,
            truncated,
            history_rows,
            last_history_at,
        ) in rows
    }


# -- routes ------------------------------------------------------------------------
# Fixed paths are declared before /{operation_id} so FastAPI does not try to
# parse "queue", "pause", "resume", "limits", "repositories", or "reconcile"
# as an id.


@router.get("/", response_model=OperationListResponse)
async def list_operations(
    repository_id: Optional[int] = None,
    category: Optional[list[str]] = Query(default=None),
    kind: Optional[list[str]] = Query(default=None),
    status: Optional[list[str]] = Query(default=None),
    trigger: Optional[list[str]] = Query(default=None),
    run_id: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    cursor: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    accessible = accessible_repository_ids(db, current_user)
    if repository_id is not None:
        repo = db.get(Repository, repository_id)
        if repo is not None:
            check_repo_access(db, current_user, repo, "viewer")
    q = db.query(Operation)
    q = _scope_to_accessible_repos(q, accessible)
    if repository_id is not None:
        q = q.filter(Operation.repository_id == repository_id)
    if category:
        q = q.filter(Operation.category.in_(category))
    if kind:
        q = q.filter(Operation.kind.in_(kind))
    if status:
        q = q.filter(Operation.status.in_(status))
    if trigger:
        q = q.filter(Operation.trigger.in_(trigger))
    if run_id:
        q = q.filter(Operation.run_id == run_id)
    if since is not None:
        q = q.filter(Operation.created_at >= since)
    if cursor is not None:
        q = q.filter(Operation.id < cursor)
    ops = q.order_by(Operation.id.desc()).limit(limit).all()
    repos = _repositories_by_id(db, ops)
    policy = get_log_save_policy(db)
    items = [_item(op, repos, policy) for op in ops]
    next_cursor = ops[-1].id if len(ops) == limit else None
    return OperationListResponse(items=items, next_cursor=next_cursor)


@router.get("/queue", response_model=QueueResponse)
async def get_queue(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cutoff = utc_now() - RECENT_WINDOW
    accessible = accessible_repository_ids(db, current_user)
    q = db.query(Operation).filter(
        (Operation.status.in_(("queued", "running")))
        | (Operation.completed_at >= cutoff)
    )
    q = _scope_to_accessible_repos(q, accessible)
    ops = q.order_by(Operation.priority.asc(), Operation.id.asc()).all()
    repos = _repositories_by_id(db, ops)
    policy = get_log_save_policy(db)
    groups: dict[Optional[int], list[dict]] = {}
    for op in ops:
        groups.setdefault(op.repository_id, []).append(_item(op, repos, policy))
    repositories = []
    for repository_id, items in groups.items():
        repo = repos.get(repository_id) if repository_id is not None else None
        repositories.append(
            QueueRepository(
                repository_id=repository_id,
                repository_name=repo.name if repo else "System",
                lane_busy=(
                    (not lane_free(db, repository_id))
                    if repository_id is not None
                    else False
                ),
                operations=items,
            )
        )
    settings = _settings_row(db)
    return QueueResponse(
        repositories=repositories,
        limits=_limits(db, settings),
        paused=bool(settings.background_paused),
    )


@router.get("/repositories", response_model=HubResponse)
async def get_repositories_hub(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One row per repository the user may see, with the state of its
    derived data, plus totals and the reconcile cadence. Two grouped
    queries for archives and operations, not one per repository."""
    accessible = accessible_repository_ids(db, current_user)
    q = db.query(Repository)
    if accessible is not None:
        q = q.filter(Repository.id.in_(accessible))
    # The plan lookup commits the session; read it before the rows so the
    # commit cannot expire them (one refresh per repository otherwise).
    history_plan = history_enabled(db)
    repositories = q.order_by(func.lower(Repository.name), Repository.id).all()

    settings = _settings_row(db)
    interval = _reconcile_interval(settings)
    history = _history_by_repository(db, accessible)
    last_sync = _latest_completed_by_repository(db, "archive_sync", accessible)
    last_stats = _latest_completed_by_repository(db, "stats", accessible)
    syncing_q = db.query(Operation.repository_id).filter(
        Operation.kind == "archive_sync",
        Operation.status.in_(("queued", "running")),
    )
    if accessible is not None:
        syncing_q = syncing_q.filter(Operation.repository_id.in_(accessible))
    syncing = {repo_id for (repo_id,) in syncing_q.distinct()}

    rows = []
    for repo in repositories:
        facts = history.get(repo.id)
        last_at = last_sync.get(repo.id)
        rows.append(
            HubRepository(
                repository_id=repo.id,
                repository_name=repo.name,
                repository_type=repo.repository_type,
                index_mode=index_mode_of(repo),
                sync_state=sync_state_from(repo.id in syncing, last_at, interval or 60),
                last_synced_at=last_at,
                last_stats_at=last_stats.get(repo.id),
                last_history_at=facts["last_history_at"] if facts else None,
                archives=facts["archives"] if facts else 0,
                history=facts["summary"] if facts else HistorySummary(),
                history_capability=history_capability(db, repo, history=history_plan),
            )
        )

    last_reconcile_q = db.query(func.max(Operation.created_at)).filter(
        Operation.trigger == "reconcile"
    )
    if accessible is not None:
        last_reconcile_q = last_reconcile_q.filter(
            Operation.repository_id.in_(accessible)
        )
    last_reconcile = last_reconcile_q.scalar()
    return HubResponse(
        repositories=rows,
        totals=HubTotals(
            repositories=len(rows),
            archives=sum(r.archives for r in rows),
            history_rows=sum(r.history.rows for r in rows),
            # A whole-table figure, so only a caller who sees every
            # repository is told it.
            history_bytes=(_history_table_bytes(db) if accessible is None else None),
        ),
        last_reconcile_at=last_reconcile,
        reconcile_interval_minutes=interval,
        history_available=history_plan,
    )


@router.get("/repositories/{repository_id}", response_model=HubRepositoryDetail)
async def get_repository_hub_detail(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The archives behind a row's failed and truncated counts, newest
    first, so the person can see which ones and how many attempts."""
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    check_repo_access(db, current_user, repo, "viewer")

    def archives(*filters):
        return [
            HubArchive(
                id=a.id,
                name=a.name,
                start=a.start,
                history_attempts=a.history_attempts or 0,
                history_rows=a.history_rows,
            )
            for a in db.query(Archive)
            .filter(Archive.repository_id == repo.id, *filters)
            .order_by(Archive.start.desc(), Archive.id.desc())
            .limit(HUB_DETAIL_LIMIT)
            .all()
        ]

    return HubRepositoryDetail(
        repository_id=repo.id,
        failed_archives=archives(Archive.history_state == "failed"),
        truncated_archives=archives(Archive.history_truncated.is_(True)),
    )


@router.post("/reconcile")
async def reconcile_now(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Run the reconcile tick now instead of waiting for the interval
    (spec 7.5). Repositories with index work already queued are skipped,
    exactly as the scheduler skips them."""
    count = enqueue_reconcile_runs(db)
    operation_runner.wake()
    return {"repositories": count}


@router.post("/pause")
async def pause_background(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    settings = _settings_row(db)
    settings.background_paused = True
    db.commit()
    return {"paused": True}


@router.post("/resume")
async def resume_background(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    settings = _settings_row(db)
    settings.background_paused = False
    db.commit()
    operation_runner.wake()
    return {"paused": False}


@router.put("/limits", response_model=QueueLimits)
async def update_limits(
    body: LimitsUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    settings = _settings_row(db)
    settings.index_workers = body.index_workers
    db.commit()
    operation_runner.wake()
    return _limits(db, settings)


@router.get("/{operation_id}", response_model=OperationDetail)
async def get_operation(
    operation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    op = _get_operation_with_access(db, current_user, operation_id, "viewer")
    run_ops = (
        db.query(Operation)
        .filter(Operation.run_id == op.run_id)
        .order_by(Operation.id)
        .all()
    )
    repos = _repositories_by_id(db, run_ops + [op])
    policy = get_log_save_policy(db)
    data = _item(op, repos, policy)
    data["run"] = [_item(r, repos, policy) for r in run_ops]
    return data


@router.post("/{operation_id}/cancel")
async def cancel_operation(
    operation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    op = _get_operation_with_access(db, current_user, operation_id, "operator")
    if is_terminal(op):
        raise HTTPException(status_code=409, detail=ALREADY_FINISHED)
    accepted = await operation_runner.request_cancel(op.id)
    if not accepted:
        raise HTTPException(status_code=409, detail=ALREADY_FINISHED)
    return {"status": "cancel_requested"}


@router.get("/{operation_id}/logs")
async def get_operation_logs(
    operation_id: int,
    offset: int = 0,
    limit: int = 500,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    op = _get_operation_with_access(db, current_user, operation_id, "viewer")
    _require_logs_by_policy(db, op)
    text = ""
    if op.log_file_path:
        try:
            with open(op.log_file_path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            text = ""
    return _paginate_log_text(text, offset, limit)


@router.get("/{operation_id}/logs/download")
async def download_operation_logs(
    operation_id: int,
    current_user: User = Depends(get_current_download_user),
    db: Session = Depends(get_db),
):
    op = _get_operation_with_access(db, current_user, operation_id, "viewer")
    _require_logs_by_policy(db, op)
    if (
        op.status == "running"
        or not op.log_file_path
        or not os.path.exists(op.log_file_path)
    ):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return FileResponse(
        op.log_file_path, media_type="text/plain", filename=f"operation_{op.id}.log"
    )
