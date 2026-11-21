""" "This machine": the plan and repository Borg UI creates to protect its host.

Spec: docs/engineering/specs/2026-11-20-this-machine.md
"""

import asyncio
import fnmatch
import json
import os
import secrets
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import BackupPlan, BackupPlanRepository, Repository, User

THIS_MACHINE_ROLE = "this_machine"
# Set by setup around its calls to the create routes, which store it on the
# new row in the same transaction: a resource is either a system one from its
# first commit or not one at all, so nothing is ever adopted afterwards.
creating_system_role: ContextVar[Optional[str]] = ContextVar(
    "creating_system_role", default=None
)
# ponytail: one in-process lock (gunicorn runs a single worker); a second
# setup waits and then finds the first one's rows.
_setup_lock = asyncio.Lock()
PLAN_NAME = "This machine"
REPOSITORY_NAME = "This machine (local)"
HOST_SNAPSHOT_DIR = "var/backups/borg-ui"
DATA_VOLUME_SNAPSHOT_DIR = "this-machine"
SCHEDULE_CRON = "0 * * * *"
RESTORE_CHECK_CRON = "0 4 * * 0"
SOURCE_ROOTS = (
    "etc",
    "home",
    "root",
    "opt",
    "srv",
    "var/lib/docker/volumes",
    "usr/local/etc",
)
CACHE_EXCLUDES = (
    "**/.cache",
    "**/node_modules/.cache",
    "**/Cache",
    "**/.local/share/Trash",
    "**/tmp",
)
LIVE_DATABASE_EXCLUDES = ("**/borg.db", "**/borg.db-wal", "**/borg.db-shm")
# User plans that reach the Borg UI data volume never take the self-backup
# staging folder (a database copy and config export).
STAGING_EXCLUDE = "**/self-backup/staging"
HOST_EXCLUDES = ("var/lib/docker/overlay2", "var/lib/docker/image")
COMPACT_INTERVAL = timedelta(hours=24)


@dataclass(frozen=True)
class SetupResult:
    plan_id: int
    repository_id: int
    in_data_volume: bool
    skipped_roots: list[str]


@dataclass(frozen=True)
class SizeEstimate:
    bytes: int
    complete: bool


def require_system_delete_confirmed(
    system_role: Optional[str], confirmed: bool
) -> None:
    """Deleting a system plan or repository stops Borg UI protecting the host
    and itself, so the caller has to say it means it."""
    if system_role and not confirmed:
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.thisMachine.confirmDelete"},
        )


def _same_inode(a: Path, b: Path) -> bool:
    try:
        sa, sb = a.stat(), b.stat()
    except OSError:
        return False
    return (sa.st_dev, sa.st_ino) == (sb.st_dev, sb.st_ino)


def find_host_root(
    mount_points: list[str],
    container_root: Path = Path("/"),
    in_docker: Optional[bool] = None,
) -> Optional[Path]:
    """The folder where the host's own `/` is visible to Borg UI, if any.

    Native installs run on the host, so it is `/`. In Docker it is the first
    configured mount point that looks like a Linux root and is not the
    container's own root (the default compose file mounts host `/` at
    `/local`)."""
    if in_docker is None:
        in_docker = Path("/.dockerenv").exists()
    if not in_docker:
        return Path("/")
    for mount in mount_points:
        candidate = Path(mount)
        if (candidate / "etc" / "os-release").is_file() and not _same_inode(
            candidate, container_root
        ):
            return candidate
    return None


def _host_root() -> Optional[Path]:
    return find_host_root(settings.get_local_mount_points())


def snapshot_location(host_root: Optional[Path], data_dir: Path) -> tuple[Path, bool]:
    """Where "This machine (local)" lives, and whether that is inside the Borg
    UI data volume (so it would be lost with the volume)."""
    if host_root is not None and _writable(host_root / HOST_SNAPSHOT_DIR):
        return host_root / HOST_SNAPSHOT_DIR, False
    return data_dir / DATA_VOLUME_SNAPSHOT_DIR, True


def _writable(path: Path) -> bool:
    """Whether Borg UI can create or write `path`: the path itself if it
    exists, else its nearest existing parent (rootless Docker and read-only
    mounts show the host but cannot hold the snapshots)."""
    for candidate in (path, *path.parents):
        try:
            if candidate.exists():
                return os.access(candidate, os.W_OK)
        except OSError:
            return False
    return False


def _maybe_dir(path: Path) -> bool:
    """A root-only parent (Docker keeps /var/lib/docker at 0710) hides the
    folder from the app user, while Borg with read-all can still reach it."""
    try:
        return path.is_dir()
    except PermissionError:
        return True


def source_directories(host_root: Path) -> list[str]:
    return [
        str(host_root / root) for root in SOURCE_ROOTS if _maybe_dir(host_root / root)
    ]


def exclude_patterns(
    host_root: Path, repo_path: Path, data_dir: Path, in_data_volume: bool = False
) -> list[str]:
    patterns = [*CACHE_EXCLUDES, *LIVE_DATABASE_EXCLUDES]
    patterns += [str(host_root / path) for path in HOST_EXCLUDES]
    patterns.append(str(repo_path))
    if in_data_volume:
        # ponytail: a data volume under /var/lib/docker/volumes shows the
        # fallback repository at a host path we cannot predict, so exclude it
        # by name. Only in fallback mode; a host repository has an exact path.
        patterns.append(f"**/{DATA_VOLUME_SNAPSHOT_DIR}")
    return patterns


def compact_due(
    system_role: Optional[str], last_compact: Optional[datetime], now: datetime
) -> bool:
    """User plans compact after every run, as before. The system plan runs
    hourly, so it compacts at most once a day."""
    if not system_role or last_compact is None:
        return True
    return now - last_compact >= COMPACT_INTERVAL


def _excluded(path: str, patterns: list[str]) -> bool:
    return any(path == p or fnmatch.fnmatch(path, p) for p in patterns)


def estimate_size(
    paths: list[str], excludes: list[str], time_cap_s: float = 5.0
) -> SizeEstimate:
    """A fast walk for the first-start screen. Stops at the time cap and says
    the number is a lower bound."""
    deadline = time.monotonic() + time_cap_s
    total = 0
    for root in paths:
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _e: None):
            if time.monotonic() > deadline:
                return SizeEstimate(bytes=total, complete=False)
            dirnames[:] = [
                d for d in dirnames if not _excluded(os.path.join(dirpath, d), excludes)
            ]
            for name in filenames:
                full = os.path.join(dirpath, name)
                if _excluded(full, excludes):
                    continue
                try:
                    total += os.lstat(full).st_size
                except OSError:
                    continue
    return SizeEstimate(bytes=total, complete=True)


def repository_in_data_volume(repository: Repository) -> bool:
    """Where an existing This machine repository actually lives."""
    data_dir = Path(settings.data_dir).resolve()
    path = Path(repository.path).resolve()
    return path == data_dir or data_dir in path.parents


def system_plan(db: Session) -> Optional[BackupPlan]:
    return (
        db.query(BackupPlan).filter(BackupPlan.system_role == THIS_MACHINE_ROLE).first()
    )


def system_repository(db: Session) -> Optional[Repository]:
    return (
        db.query(Repository).filter(Repository.system_role == THIS_MACHINE_ROLE).first()
    )


def plan_sources() -> tuple[list[str], list[str], Path, bool]:
    """Source folders, excludes, repository path and data-volume flag for the
    current host."""
    host_root = _host_root()
    data_dir = Path(settings.data_dir)
    repo_path, in_data_volume = snapshot_location(host_root, data_dir)
    if host_root is None:
        # Without the host mounted, Borg UI can only protect itself: the plan
        # backs up the self-backup folder the pre-backup step fills.
        self_backup = data_dir / "self-backup"
        self_backup.mkdir(parents=True, exist_ok=True)
        return (
            [str(self_backup)],
            [*LIVE_DATABASE_EXCLUDES, str(repo_path)],
            repo_path,
            True,
        )
    return (
        source_directories(host_root),
        exclude_patterns(host_root, repo_path, data_dir, in_data_volume),
        repo_path,
        in_data_volume,
    )


async def _create_repository(db: Session, user: User, path: Path) -> Repository:
    from app.api.repositories import RepositoryCreate, create_repository

    token = creating_system_role.set(THIS_MACHINE_ROLE)
    try:
        response = await create_repository(
            RepositoryCreate(
                name=REPOSITORY_NAME,
                path=str(path),
                borg_version=1,
                encryption="repokey-blake2",
                compression="lz4",
                passphrase=secrets.token_urlsafe(32),
            ),
            user,
            db,
        )
    finally:
        creating_system_role.reset(token)
    return db.get(Repository, response["repository"]["id"])


async def _create_plan(
    db: Session,
    user: User,
    repository: Repository,
    sources: list[str],
    excludes: list[str],
) -> BackupPlan:
    from app.api.backup_plans import (
        BackupPlanPayload,
        BackupPlanRepositoryPayload,
        create_backup_plan,
    )

    token = creating_system_role.set(THIS_MACHINE_ROLE)
    try:
        body = await create_backup_plan(
            BackupPlanPayload(
                name=PLAN_NAME,
                description="Protects this machine and Borg UI itself.",
                source_directories=sources,
                exclude_patterns=excludes,
                archive_name_template="this-machine-{now}",
                schedule_enabled=True,
                cron_expression=SCHEDULE_CRON,
                timezone="UTC",
                run_prune_after=True,
                run_compact_after=True,
                prune_keep_hourly=24,
                prune_keep_daily=7,
                prune_keep_weekly=4,
                prune_keep_monthly=6,
                prune_keep_yearly=0,
                repositories=[
                    BackupPlanRepositoryPayload(
                        repository_id=repository.id, execution_order=1
                    )
                ],
            ),
            user,
            db,
        )
    finally:
        creating_system_role.reset(token)
    return db.get(BackupPlan, body["id"])


def _linked_repository(db: Session, plan: BackupPlan) -> Optional[Repository]:
    repository = system_repository(db)
    if repository is not None:
        return repository
    link = (
        db.query(BackupPlanRepository)
        .filter(BackupPlanRepository.backup_plan_id == plan.id)
        .order_by(BackupPlanRepository.execution_order)
        .first()
    )
    return db.get(Repository, link.repository_id) if link else None


async def _ensure_restore_check(
    db: Session, user: User, repository: Repository
) -> None:
    if repository.restore_check_cron_expression:
        return
    from app.api.repositories import update_restore_check_schedule

    await update_restore_check_schedule(
        repository.id,
        {"cron_expression": RESTORE_CHECK_CRON, "timezone": "UTC"},
        user,
        db,
    )
    db.refresh(repository)


def _excludes_for(
    host_root: Optional[Path],
    repository: Repository,
    planned: list[str],
    planned_repo_path: Path,
) -> list[str]:
    repo_path = Path(repository.path)
    if host_root is None:
        return [p for p in planned if p != str(planned_repo_path)] + [str(repo_path)]
    return exclude_patterns(
        host_root,
        repo_path,
        Path(settings.data_dir),
        repository_in_data_volume(repository),
    )


def _ensure_repository_excluded(
    db: Session, plan: BackupPlan, repository: Repository
) -> None:
    """A reused plan must not back up the repository setup selected. Only
    adds; every existing exclude, an admin's included, stays."""
    current = json.loads(plan.exclude_patterns) if plan.exclude_patterns else []
    needed = [repository.path]
    if repository_in_data_volume(repository):
        needed.append(f"**/{DATA_VOLUME_SNAPSHOT_DIR}")
    missing = [p for p in needed if p not in current]
    if missing:
        plan.exclude_patterns = json.dumps([*current, *missing])
        db.commit()


def _ensure_link(db: Session, plan: BackupPlan, repository: Repository) -> None:
    """The system plan must back up to the system repository."""
    link = (
        db.query(BackupPlanRepository)
        .filter(
            BackupPlanRepository.backup_plan_id == plan.id,
            BackupPlanRepository.repository_id == repository.id,
        )
        .first()
    )
    if link is not None and link.enabled:
        return
    if link is None:
        last = (
            db.query(BackupPlanRepository.execution_order)
            .filter(BackupPlanRepository.backup_plan_id == plan.id)
            .order_by(BackupPlanRepository.execution_order.desc())
            .first()
        )
        link = BackupPlanRepository(
            backup_plan_id=plan.id,
            repository_id=repository.id,
            execution_order=(last[0] + 1) if last else 1,
            created_at=datetime.utcnow(),
        )
        db.add(link)
    link.enabled = True
    db.commit()


def _refuse_taken_names(db: Session, repo_path: Path, need_plan: bool) -> None:
    """A user's own plan or repository with the name or path setup would use
    is theirs; setup stops rather than create a clash or take it over."""
    clash = (
        db.query(Repository)
        .filter(
            Repository.system_role.is_(None),
            (Repository.name == REPOSITORY_NAME) | (Repository.path == str(repo_path)),
        )
        .first()
    )
    if clash is None and need_plan:
        clash = (
            db.query(BackupPlan)
            .filter(BackupPlan.system_role.is_(None), BackupPlan.name == PLAN_NAME)
            .first()
        )
    if clash is not None:
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.thisMachine.nameTaken"},
        )


async def setup_this_machine(db: Session, user: User) -> SetupResult:
    """Create the "This machine" plan and repository. Safe to call again: an
    existing setup is returned as it is and finished if a step is missing
    (restore check, plan, link). Resources carry the system role from their
    first commit, so nothing a user made is ever taken over."""
    async with _setup_lock:
        return await _setup(db, user)


async def _setup(db: Session, user: User) -> SetupResult:
    sources, excludes, repo_path, _ = plan_sources()
    host_root = _host_root()
    skipped = (
        [root for root in SOURCE_ROOTS if not _maybe_dir(host_root / root)]
        if host_root is not None
        else list(SOURCE_ROOTS)
    )
    try:
        plan = system_plan(db)
        repository = system_repository(db) or (plan and _linked_repository(db, plan))
        if repository is None:
            _refuse_taken_names(db, repo_path, need_plan=plan is None)
            repository = await _create_repository(db, user, repo_path)
        elif plan is None:
            _refuse_taken_names(db, Path(repository.path), need_plan=True)
        await _ensure_restore_check(db, user, repository)
        # Exclude the repository setup actually uses, which may be an earlier
        # one in the data volume even when the host is writable now.
        excludes = _excludes_for(host_root, repository, excludes, repo_path)
        if plan is None:
            plan = await _create_plan(db, user, repository, sources, excludes)
        else:
            _ensure_repository_excluded(db, plan, repository)
        _ensure_link(db, plan, repository)
    except IntegrityError:
        # Another process won the race for the one system plan or repository.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.thisMachine.setupInProgress"},
        )
    return SetupResult(
        plan_id=plan.id,
        repository_id=repository.id,
        in_data_volume=repository_in_data_volume(repository),
        skipped_roots=skipped,
    )


def read_all_marker() -> Path:
    """Written at start-up (entrypoint, or the native installer) once Borg's
    read-all interpreter has been proven to run in this container or host."""
    return Path(os.environ.get("BORG_UI_READ_ALL_MARKER", "/run/borg-ui/read-all"))


def has_read_all(
    host_root: Optional[Path],
    euid: Optional[int] = None,
    marker: Optional[Path] = None,
) -> bool:
    """Whether Borg can read every file on the host, including root-only ones."""
    if host_root is None:
        return False
    if (os.geteuid() if euid is None else euid) == 0:
        return True
    return (marker or read_all_marker()).exists()
