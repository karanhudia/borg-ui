"""Operations API (spec section 9.1)."""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.activity import _paginate_log_text
from app.core.security import (
    check_repo_access,
    get_current_admin_user,
    get_current_download_user,
    get_current_user,
    require_any_role,
)
from app.database.database import get_db
from app.database.models import (
    Operation,
    Repository,
    SystemSettings,
    User,
    UserRepositoryPermission,
    utc_now,
)
from app.services.log_policy import get_log_save_policy, job_has_logs_by_policy
from app.services.operations.lanes import lane_free, running_count
from app.services.operations.models import is_terminal, serialize_operation
from app.services.operations.runner import operation_runner
from app.services.operations.vocab import INDEX_KINDS

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


# -- routes ------------------------------------------------------------------------
# Fixed paths are declared before /{operation_id} so FastAPI does not try to
# parse "queue", "pause", "resume", or "limits" as an id.


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
    if not op.log_file_path or not os.path.exists(op.log_file_path):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return FileResponse(
        op.log_file_path, media_type="text/plain", filename=f"operation_{op.id}.log"
    )
