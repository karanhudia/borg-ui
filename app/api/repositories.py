from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timezone
from functools import partial
from pathlib import Path as FilesystemPath
from types import SimpleNamespace
import structlog
import os
import asyncio
import json
import shutil
import uuid

from app.database.database import get_db, SessionLocal
from app.database.models import (
    User,
    Repository,
    RepositoryStorage,
    RcloneRemote,
    RcloneSyncJob,
    AgentMachine,
    CheckJob,
    CompactJob,
    PruneJob,
    RestoreCheckJob,
    ScheduledJob,
    ScheduledJobRepository,
    SystemSettings,
    UserRepositoryPermission,
    RepositoryWipeJob,
)
from app.api.maintenance_jobs import (
    create_maintenance_job,
    start_background_maintenance_job,
    get_job_with_repository,
    get_repository_jobs,
    get_repository_with_access,
    read_job_logs,
    serialize_job_status,
    serialize_job_summary,
)
from app.core.authorization import authorize_request
from app.core.security import get_current_user, check_repo_access, decrypt_secret
from app.core.borg import BorgInterface
from app.core.borg_router import BorgRouter
from app.core.borg_errors import is_lock_error
from app.core.features import (
    FEATURES,
    get_current_plan,
    plan_includes,
    require_feature_access,
)
from app.config import settings
from app.services.mqtt_service import mqtt_service
from app.services.restore_check_service import restore_check_service
from app.services.repository_wipe_service import (
    WipeArchiveSetChanged,
    WipeValidationError,
    repository_wipe_service,
)
from app.services.repository_executor import (
    is_agent_executor,
    legacy_execution_target,
    normalize_executor_type,
    queue_agent_repository_operation_job,
    repository_executor_type,
    wait_for_agent_repository_operation_job,
)
from app.services.check_flag_validation import (
    CheckFlagConflictError,
    validate_check_flags_for_max_duration,
)
from app.services.agent_job_dispatcher import dispatch_agent_job_best_effort
from app.services.agent_connection_manager import (
    agent_connection_manager,
    AgentConnectionUnavailable,
    AgentCommandTimeout,
    AgentCommandError,
)
from app.core.agent_constants import AGENT_FILESYSTEM_BROWSE_TIMEOUT_SECONDS
from app.services.job_admission import (
    OPERATION_CHECK,
    OPERATION_COMPACT,
    OPERATION_PRUNE,
    ensure_repository_admission,
)
from app.services.log_policy import get_log_save_policy, job_has_logs_by_policy
from app.services.repository_command_lock import run_serialized_repository_command
from app.services.rclone_repository_service import (
    SYNC_DIRECTION_AGENT_TO_REMOTE,
    SYNC_DIRECTION_PRIMARY_TO_REMOTE,
    SYNC_DIRECTION_SSHFS_TO_REMOTE,
    VALID_SYNC_POLICIES,
    normalize_extra_flags,
    normalize_rclone_relative_path,
    rclone_repository_service,
)
from app.utils.datetime_utils import serialize_datetime
from app.utils.schedule_time import (
    DEFAULT_SCHEDULE_TIMEZONE,
    InvalidScheduleTimezone,
    calculate_next_cron_run,
    normalize_schedule_timezone,
)
from app.utils.archive_job_metadata import enrich_archives_with_backup_metadata
from app.utils.ssh_paths import apply_ssh_command_prefix
from app.utils.repository_paths import build_ssh_repository_path, strip_ssh_url_path
from app.utils.source_locations import (
    decode_source_locations,
    legacy_source_fields,
    normalize_source_locations,
)
from app.utils.borg_env import (
    get_standard_ssh_opts as shared_get_standard_ssh_opts,
    setup_borg_env as shared_setup_borg_env,
    cleanup_temp_key_file,
)
from app.utils.ssh_utils import (
    resolve_repo_ssh_key_file,
    ssh_key_auth_args,
)  # Backward-compatible patch target for tests

logger = structlog.get_logger()
router = APIRouter(tags=["repositories"], dependencies=[Depends(authorize_request)])

V2_ONLY_ENCRYPTION_MODES = {
    "repokey-aes-ocb",
    "repokey-chacha20-poly1305",
    "keyfile-aes-ocb",
    "keyfile-chacha20-poly1305",
}


def _router_repo_snapshot(repository: Repository) -> SimpleNamespace:
    return SimpleNamespace(id=repository.id, borg_version=repository.borg_version)


def _dispatch_router_check(router_repo: SimpleNamespace, job: CheckJob):
    return BorgRouter(router_repo).check(job.id)


def _dispatch_router_compact(router_repo: SimpleNamespace, job: CompactJob):
    return BorgRouter(router_repo).compact(job.id)


def _dispatch_router_prune(
    router_repo: SimpleNamespace,
    keep_hourly: int,
    keep_daily: int,
    keep_weekly: int,
    keep_monthly: int,
    keep_quarterly: int,
    keep_yearly: int,
    keep_within: str | None,
    job: PruneJob,
):
    args = (
        job.id,
        keep_hourly,
        keep_daily,
        keep_weekly,
        keep_monthly,
        keep_quarterly,
        keep_yearly,
        False,
    )
    kwargs = {"keep_within": keep_within} if keep_within is not None else {}
    return BorgRouter(router_repo).prune(*args, **kwargs)


AGENT_RCLONE_SYNC_CAPABILITY = "repository.rclone_sync"
AGENT_REPOSITORY_INIT_CAPABILITY = "repository.init"
DIRECT_RCLONE_STORAGE_BACKEND = "rclone_direct"
RCLONE_FEATURE = "rclone"
MANAGED_AGENTS_FEATURE = "managed_agents"
ACTIVE_MAINTENANCE_JOB_STATUSES = ("pending", "running")

# Initialize Borg interface
borg = BorgInterface()


class RepositoryWipePreviewRequest(BaseModel):
    run_compact: bool = True


class RepositoryWipeExecuteRequest(BaseModel):
    preview_id: int
    preview_fingerprint: str
    confirmation_phrase: str
    understood: bool
    run_compact: bool = True


class RepositoryPermanentDeleteRequest(BaseModel):
    confirmation_phrase: str
    understood: bool


def _normalize_restore_check_paths(paths: Any) -> list[str]:
    if not paths:
        return []
    if not isinstance(paths, list):
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.invalidRestoreCheckPaths"},
        )

    normalized_paths: list[str] = []
    for path in paths:
        if not isinstance(path, str) or not path.strip():
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.repo.invalidRestoreCheckPaths"},
            )
        normalized_paths.append(path.strip())
    return normalized_paths


def _normalize_optional_flags(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _validate_upload_ratelimit_kib(value: Optional[int]) -> None:
    if value is not None and value <= 0:
        raise HTTPException(
            status_code=422,
            detail={"key": "backend.errors.repo.invalidUploadLimit"},
        )


def _raise_check_flag_conflict(exc: CheckFlagConflictError) -> None:
    raise HTTPException(
        status_code=422,
        detail={
            "key": "backend.errors.repo.checkFlagsRequireUnlimitedDuration",
            "params": {"flags": ", ".join(exc.conflicting_flags)},
        },
    ) from exc


def _resolve_restore_check_targets(
    *,
    request: Optional[dict],
    repository: Repository,
) -> tuple[list[str], bool]:
    request = request or {}
    if "paths" in request:
        probe_paths = _normalize_restore_check_paths(request.get("paths"))
    else:
        probe_paths = _normalize_restore_check_paths(
            json.loads(repository.restore_check_paths)
            if repository.restore_check_paths
            else []
        )

    full_archive = request.get("full_archive")
    if full_archive is None:
        full_archive = bool(repository.restore_check_full_archive)
    else:
        full_archive = bool(full_archive)

    return probe_paths, full_archive


def _get_restore_check_mode(*, probe_paths: list[str], full_archive: bool) -> str:
    if full_archive:
        return "full_archive"
    if probe_paths:
        return "probe_paths"
    return "canary"


def _is_restore_check_canary_mode(
    *, probe_paths: list[str], full_archive: bool
) -> bool:
    return (
        _get_restore_check_mode(probe_paths=probe_paths, full_archive=full_archive)
        == "canary"
    )


def _ensure_restore_check_mode_allowed(
    *, repository: Repository, probe_paths: list[str], full_archive: bool
) -> None:
    if repository.mode == "observe" and _is_restore_check_canary_mode(
        probe_paths=probe_paths, full_archive=full_archive
    ):
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.restoreCheckCanaryUnsupportedObserve"},
        )


def get_connection_details(connection_id: int, db: Session) -> Dict[str, Any]:
    """
    Get SSH connection details from connection_id.
    Returns dict with host, username, port, ssh_key_id, ssh_path_prefix.
    Raises HTTPException if connection not found.
    """
    from app.database.models import SSHConnection

    connection = (
        db.query(SSHConnection).filter(SSHConnection.id == connection_id).first()
    )
    if not connection:
        raise HTTPException(
            status_code=404,
            detail={
                "key": "backend.errors.repo.sshConnectionNotFound",
                "params": {"id": connection_id},
            },
        )

    return {
        "host": connection.host,
        "username": connection.username,
        "port": connection.port,
        "ssh_key_id": connection.ssh_key_id,
        "ssh_path_prefix": connection.ssh_path_prefix,
    }


def _require_repository_access(
    db: Session, user: User, repository: Repository, required_role: str
) -> None:
    check_repo_access(db, user, repository, required_role)


def _empty_running_jobs_response() -> Dict[str, Any]:
    return {
        "has_running_jobs": False,
        "check_job": None,
        "compact_job": None,
        "prune_job": None,
        "restore_check_job": None,
        "wipe_job": None,
    }


def _permanent_delete_target(repository: Repository) -> FilesystemPath:
    repository_type = (repository.repository_type or "local").strip().lower()
    execution_target = (repository.execution_target or "local").strip().lower()
    executor_type = (repository.executor_type or "server").strip().lower()

    if (
        repository_type != "local"
        or execution_target != "local"
        or executor_type == "agent"
        or repository.connection_id
        or repository.agent_machine_id
    ):
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.permanentDeleteLocalOnly"},
        )

    raw_path = (repository.path or "").strip()
    if not raw_path or "://" in raw_path:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.permanentDeleteLocalOnly"},
        )

    target = FilesystemPath(os.path.expanduser(raw_path))
    if not target.is_absolute():
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.permanentDeleteUnsafePath"},
        )

    if not target.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "key": "backend.errors.repo.permanentDeletePathMissing",
                "params": {"path": raw_path},
            },
        )

    if target.is_symlink() or not target.is_dir():
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.permanentDeleteUnsafePath"},
        )

    resolved_target = target.resolve()
    if resolved_target != target:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.permanentDeleteUnsafePath"},
        )

    if resolved_target.parent == resolved_target or len(resolved_target.parts) <= 2:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.permanentDeleteUnsafePath"},
        )

    if (
        not (resolved_target / "config").is_file()
        or not (resolved_target / "data").is_dir()
    ):
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.permanentDeleteNotBorgRepository"},
        )

    return resolved_target


# Helper function to get standard SSH options
def _borg_keyfile_name(repo_path: str) -> str:
    """Derive a keyfile filename from the repository path.

    Matches the convention used by existing keyfiles:
      /local/Users/foo/test-backups/my-repo  →  local_Users_foo_test_backups_my_repo
      ssh://user@host:22/backups/repo        →  user_host_22_backups_repo

    Rules: strip the ssh:// scheme or leading slash, then replace all
    non-alphanumeric characters with '_'. No prefix added, no file extension.
    """
    import re

    if repo_path.startswith("ssh://"):
        path = repo_path[len("ssh://") :]
    else:
        path = repo_path.lstrip("/")
    return re.sub(r"[^a-zA-Z0-9]", "_", path)


def _write_borg_keyfile(repo_path: str, keyfile_content: str) -> str:
    keyfile_dir = os.path.expanduser("~/.config/borg/keys")
    os.makedirs(keyfile_dir, exist_ok=True)
    keyfile_path = os.path.join(keyfile_dir, _borg_keyfile_name(repo_path))
    with open(keyfile_path, "w") as f:
        f.write(keyfile_content)
    os.chmod(keyfile_path, 0o600)
    return keyfile_path


def get_standard_ssh_opts(include_key_path=None):
    """Backwards-compatible wrapper for shared Borg SSH options."""
    return shared_get_standard_ssh_opts(include_key_path=include_key_path)


# Helper function to setup Borg environment with proper lock configuration
def setup_borg_env(base_env=None, passphrase=None, ssh_opts=None):
    """Backwards-compatible wrapper for shared Borg environment setup."""
    return shared_setup_borg_env(
        base_env=base_env, passphrase=passphrase, ssh_opts=ssh_opts
    )


def _prepare_repository_borg_env(repository: Repository, db: Session):
    """Build Borg execution environment for a stored repository.

    Returns the environment plus any temporary SSH key file that must be
    cleaned up by the caller.
    """
    temp_key_file = resolve_repo_ssh_key_file(repository, db)
    ssh_opts = get_standard_ssh_opts(include_key_path=temp_key_file)
    env = setup_borg_env(
        passphrase=repository.passphrase,
        ssh_opts=ssh_opts,
    )
    return env, temp_key_file


def _repository_stats_borg_env(env: Dict[str, str]) -> Dict[str, str]:
    """Return a Borg environment that renders archive timestamps in UTC."""
    stats_env = env.copy()
    stats_env["TZ"] = "UTC"
    return stats_env


def _parse_borg_archive_time(value: Any) -> Optional[datetime]:
    """Parse a Borg archive timestamp as a naive UTC database value."""
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)

    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return None

    dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)


def _load_repository_with_access(
    repo_id: int,
    current_user: User,
    db: Session,
    required_role: str = "viewer",
) -> Repository:
    return get_repository_with_access(
        db, current_user, repo_id, required_role=required_role
    )


def _lock_source(repository_enabled: bool, system_enabled: bool) -> str:
    if repository_enabled:
        return "repo_setting"
    if system_enabled:
        return "system_setting"
    return "none"


def _resolve_bypass_lock(
    repository: Repository, db: Session, setting_name: str
) -> tuple[bool, str]:
    system_settings = db.query(SystemSettings).first()
    system_enabled = bool(
        system_settings and getattr(system_settings, setting_name, False)
    )
    use_bypass_lock = bool(repository.bypass_lock or system_enabled)
    return use_bypass_lock, _lock_source(repository.bypass_lock, system_enabled)


def _get_repository_schedule_summary(repo_id: int, db: Session) -> Dict[str, Any]:
    """Return one preferred schedule summary for a repository.

    Enabled schedules win over disabled ones. We support both legacy single-repo
    schedules and multi-repo schedules through the junction table.
    """

    direct_matches = (
        db.query(ScheduledJob).filter(ScheduledJob.repository_id == repo_id).all()
    )
    linked_schedule_ids = [
        row.scheduled_job_id
        for row in db.query(ScheduledJobRepository.scheduled_job_id)
        .filter(ScheduledJobRepository.repository_id == repo_id)
        .all()
    ]
    linked_matches = (
        db.query(ScheduledJob).filter(ScheduledJob.id.in_(linked_schedule_ids)).all()
        if linked_schedule_ids
        else []
    )

    matched = direct_matches + linked_matches
    if not matched:
        return {
            "has_schedule": False,
            "schedule_enabled": False,
            "schedule_name": None,
            "schedule_timezone": None,
            "next_run": None,
        }

    preferred = next((job for job in matched if job.enabled), matched[0])
    return {
        "has_schedule": True,
        "schedule_enabled": bool(preferred.enabled),
        "schedule_name": preferred.name,
        "schedule_timezone": preferred.timezone or DEFAULT_SCHEDULE_TIMEZONE,
        "next_run": format_datetime(preferred.next_run)
        if preferred.enabled and preferred.next_run
        else None,
    }


async def _run_repository_command(
    repository: Repository,
    db: Session,
    cmd: List[str],
    timeout: int,
    *,
    log_message: Optional[str] = None,
    log_fields: Optional[Dict[str, Any]] = None,
):
    """Execute a repository-scoped Borg command with common SSH/env handling."""
    env, temp_key_file = _prepare_repository_borg_env(repository, db)
    try:
        if temp_key_file and log_message:
            logger.info(log_message, **(log_fields or {}))

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        return process.returncode, stdout, stderr
    finally:
        try:
            cleanup_temp_key_file(temp_key_file)
        except Exception:
            pass


async def _run_repository_command_with_retries(
    repository: Repository,
    db: Session,
    *,
    repo_id: int,
    cmd: List[str],
    timeout: int,
    bypass_lock: bool,
    source: str,
    command_label: str,
    ssh_log_message: str,
    failure_key: str,
):
    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            logger.info(
                command_label,
                repo_id=repo_id,
                command=" ".join(cmd),
                bypass_lock=bypass_lock,
                source=source,
            )

            returncode, stdout, stderr = await _run_repository_command(
                repository,
                db,
                cmd,
                timeout,
                log_message=ssh_log_message,
                log_fields={"repo_id": repo_id},
            )

            if returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                if is_lock_error(exit_code=returncode):
                    logger.warning(
                        f"Lock error detected on attempt {attempt + 1}/{max_retries}",
                        repo_id=repo_id,
                        borg_exit_code=returncode,
                        error=error_msg,
                    )
                    raise HTTPException(
                        status_code=423,
                        detail={
                            "error": "repository_locked",
                            "message": "backend.errors.repo.repositoryLocked",
                            "suggestion": "If no backup is currently running, this is likely a stale lock. You can break the lock to continue.",
                            "repository_id": repo_id,
                            "can_break_lock": True,
                        },
                    )

                logger.error(failure_key, repo_id=repo_id, error=error_msg)
                raise HTTPException(status_code=500, detail={"key": failure_key})

            return stdout
        except HTTPException:
            raise
        except asyncio.TimeoutError:
            error_msg = "Operation timed out after 200 seconds. This can happen with slow SSH connections or large repositories."
            if attempt < max_retries - 1:
                logger.warning(
                    f"Timeout on attempt {attempt + 1}/{max_retries}, retrying",
                    repo_id=repo_id,
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            logger.error(
                "Repository command timed out after retries",
                repo_id=repo_id,
                failure_key=failure_key,
            )
            raise HTTPException(status_code=504, detail=error_msg)
        except Exception as exc:
            error_msg = str(exc) if str(exc) else f"Unknown error: {type(exc).__name__}"
            if attempt < max_retries - 1:
                logger.warning(
                    f"Error on attempt {attempt + 1}/{max_retries}, retrying",
                    repo_id=repo_id,
                    error=error_msg,
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            logger.error(
                "Repository command failed after retries",
                repo_id=repo_id,
                error=error_msg,
                failure_key=failure_key,
            )
            raise HTTPException(status_code=500, detail={"key": failure_key})


def _parse_agent_json_result(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data")
    if isinstance(data, dict):
        return data
    stdout = result.get("stdout")
    if isinstance(stdout, str) and stdout.strip():
        try:
            parsed = json.loads(stdout)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _agent_prune_operation_payload(request: dict) -> dict[str, Any]:
    keep_within = _normalize_prune_keep_within(request.get("keep_within"))
    return {
        "keep_hourly": request.get("keep_hourly", 0),
        "keep_daily": request.get("keep_daily", 7),
        "keep_weekly": request.get("keep_weekly", 4),
        "keep_monthly": request.get("keep_monthly", 6),
        "keep_quarterly": request.get("keep_quarterly", 0),
        "keep_yearly": request.get("keep_yearly", 1),
        "keep_within": keep_within,
        "dry_run": request.get("dry_run", False),
    }


def _normalize_prune_keep_within(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(
            status_code=422,
            detail={"key": "backend.errors.repo.invalidPruneKeepWithin"},
        )
    value = value.strip()
    return value or None


# Helper function to get operation timeouts from DB settings (with fallback to config)
def get_operation_timeouts(db: Session = None) -> dict:
    """
    Get operation timeouts from database settings, with fallback to config values.
    UI settings take priority over environment variables.

    Returns:
        dict with keys: info_timeout, list_timeout, init_timeout, backup_timeout
    """
    timeouts = {
        "info_timeout": settings.borg_info_timeout,
        "list_timeout": settings.borg_list_timeout,
        "init_timeout": settings.borg_init_timeout,
        "backup_timeout": settings.backup_timeout,
    }

    try:
        # Use provided session or create one
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            system_settings = db.query(SystemSettings).first()
            if system_settings:
                # Override with DB values if they exist
                if system_settings.info_timeout:
                    timeouts["info_timeout"] = system_settings.info_timeout
                if system_settings.list_timeout:
                    timeouts["list_timeout"] = system_settings.list_timeout
                if system_settings.init_timeout:
                    timeouts["init_timeout"] = system_settings.init_timeout
                if system_settings.backup_timeout:
                    timeouts["backup_timeout"] = system_settings.backup_timeout
        finally:
            if close_session:
                db.close()
    except Exception as e:
        logger.warning(
            "Failed to get timeouts from DB, using config defaults", error=str(e)
        )

    return timeouts


# Helper function to update repository archive count
async def update_repository_stats(repository: Repository, db: Session) -> bool:
    """
    Update the archive count and repository size stats by querying Borg.
    Returns True if successful, False otherwise.
    """
    if is_agent_executor(repository):
        logger.info(
            "Skipping server-side stats refresh for agent-owned repository",
            repository=repository.name,
            repository_id=repository.id,
        )
        return True

    temp_key_file = None
    try:
        # Check system-wide bypass_lock_on_list setting
        from app.database.models import SystemSettings

        system_settings = db.query(SystemSettings).first()
        use_bypass_lock = repository.bypass_lock or (
            system_settings and system_settings.bypass_lock_on_list
        )
        env, temp_key_file = _prepare_repository_borg_env(repository, db)
        stats_env = _repository_stats_borg_env(env)

        router = BorgRouter(repository)

        # Get archive list and count
        archives = await router.list_archives(env=stats_env)

        archive_count = 0
        total_size = None
        last_backup_time = None

        try:
            if isinstance(archives, str):
                archives_data = json.loads(archives)
                archives = (
                    archives_data.get("archives", [])
                    if isinstance(archives_data, dict)
                    else archives_data
                )

            if isinstance(archives, list):
                archive_count = len(archives)

                archive_times = []
                for archive in archives:
                    archive_time = archive.get("time") or archive.get("start")
                    if not archive_time:
                        continue

                    try:
                        parsed_time = _parse_borg_archive_time(archive_time)
                    except ValueError as te:
                        logger.warning(
                            "Failed to parse archive timestamp",
                            repository=repository.name,
                            timestamp=archive_time,
                            error=str(te),
                        )
                        continue

                    if parsed_time:
                        archive_times.append(parsed_time)

                if archive_times:
                    last_backup_time = max(archive_times)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse archive list JSON",
                repository=repository.name,
                error=str(e),
                stdout=str(archives)[:200],
            )

        # Get timeouts from DB settings (with fallback to config)
        timeouts = get_operation_timeouts(db)

        try:
            total_size_bytes = await router.calculate_total_size_bytes(
                env=env,
                info_timeout=timeouts["info_timeout"],
                use_bypass_lock=use_bypass_lock,
                temp_key_file=temp_key_file,
            )
            if total_size_bytes > 0:
                total_size = format_bytes(total_size_bytes)
        except Exception as e:
            logger.warning(
                "Failed to get repository size",
                repository=repository.name,
                error=str(e),
            )

        # Update repository
        old_count = repository.archive_count
        old_size = repository.total_size
        old_last_backup = repository.last_backup
        repository.archive_count = archive_count
        if total_size:
            repository.total_size = total_size
        if last_backup_time:
            repository.last_backup = last_backup_time

        db.commit()
        logger.info(
            "Updated repository stats",
            repository=repository.name,
            archive_count_old=old_count,
            archive_count_new=archive_count,
            size_old=old_size,
            size_new=total_size,
            last_backup_old=old_last_backup,
            last_backup_new=last_backup_time,
        )
        return True

    except Exception as e:
        logger.error(
            "Exception while updating repository stats",
            repository=repository.name,
            error=str(e),
        )
        return False
    finally:
        if temp_key_file and os.path.exists(temp_key_file):
            try:
                os.unlink(temp_key_file)
            except Exception:
                pass


# Helper function to format bytes to human readable format
def format_bytes(bytes_size: int) -> str:
    """Format bytes to human readable string (e.g., '1.23 GB')"""
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} EB"


def _decode_json_list_field(value):
    """Normalize repository JSON-list fields that may already be decoded."""
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    return json.loads(value)


def _repository_source_locations(repository: Repository) -> list[Dict[str, Any]]:
    source_directories = _decode_json_list_field(repository.source_directories)
    return decode_source_locations(
        repository.source_locations,
        source_type="remote" if repository.source_ssh_connection_id else "local",
        source_ssh_connection_id=repository.source_ssh_connection_id,
        source_directories=source_directories,
    )


def _normalize_repository_source_payload(
    *,
    source_locations: Optional[List[Dict[str, Any]]],
    source_connection_id: Optional[int],
    source_directories: Optional[List[str]],
) -> tuple[list[Dict[str, Any]], Optional[int], list[str]]:
    try:
        normalized = normalize_source_locations(
            source_locations,
            source_type="remote" if source_connection_id else "local",
            source_ssh_connection_id=source_connection_id,
            source_directories=source_directories,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"key": "backend.errors.repo.sourceConnectionRequired"},
        ) from exc

    if not normalized:
        return [], source_connection_id, source_directories or []

    _source_type, legacy_connection_id, flattened_paths = legacy_source_fields(
        normalized
    )
    return normalized, legacy_connection_id, flattened_paths


# Helper function to format datetime with timezone
def format_datetime(dt):
    """Format datetime to ISO8601 with UTC timezone indicator"""
    return serialize_datetime(dt)


def _borg_result_error(result: Dict[str, Any]) -> Optional[str]:
    for key in ("error", "stderr", "stdout"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return_code = result.get("return_code")
    if return_code is not None:
        return f"Borg command exited with status {return_code}"

    return None


def _repository_init_failure_detail(result: Dict[str, Any]) -> Dict[str, Any]:
    detail: Dict[str, Any] = {"key": "backend.errors.repo.failedToInitializeRepository"}
    error = _borg_result_error(result)
    if error:
        detail["params"] = {"error": error}
    return detail


# Pydantic models
from pydantic import BaseModel


class RepositoryCreate(BaseModel):
    name: str
    borg_version: Optional[int] = 1
    path: str
    encryption: str = "repokey"  # repokey, keyfile, none
    compression: str = "lz4"  # lz4, zstd, zlib, none
    passphrase: Optional[str] = None
    source_directories: Optional[List[str]] = None  # List of directories to backup
    source_locations: Optional[List[Dict[str, Any]]] = None
    exclude_patterns: Optional[List[str]] = (
        None  # List of exclude patterns (e.g., ["*.log", "*.tmp"])
    )
    connection_id: Optional[int] = None  # SSH connection ID for repository location
    remote_path: Optional[str] = (
        None  # Path to borg on remote server (e.g., /usr/local/bin/borg)
    )
    pre_backup_script: Optional[str] = None  # Script to run before backup
    post_backup_script: Optional[str] = None  # Script to run after backup
    hook_timeout: Optional[int] = (
        300  # Hook timeout in seconds (legacy, use pre/post_hook_timeout)
    )
    pre_hook_timeout: Optional[int] = 300  # Pre-backup hook timeout in seconds
    post_hook_timeout: Optional[int] = 300  # Post-backup hook timeout in seconds
    continue_on_hook_failure: Optional[bool] = (
        False  # Continue backup if pre-hook fails
    )
    skip_on_hook_failure: Optional[bool] = (
        False  # Skip backup gracefully if pre-hook fails
    )
    mode: str = "full"  # full: backups + observability, observe: observability-only
    bypass_lock: bool = (
        False  # Use --bypass-lock for read-only storage access (observe-only repos)
    )
    custom_flags: Optional[str] = (
        None  # Custom command-line flags for borg create (e.g., "--stats --list")
    )
    upload_ratelimit_kib: Optional[int] = None
    source_connection_id: Optional[int] = (
        None  # SSH connection ID for remote data source (pull-based backups)
    )
    execution_target: str = "local"  # local, ssh, agent
    executor_type: Optional[str] = None  # server, agent
    agent_machine_id: Optional[int] = None  # Agent that executes backups
    storage_backend: str = "local"  # local, ssh, agent_local, rclone
    rclone_remote_id: Optional[int] = None
    rclone_remote_path: Optional[str] = None
    cloud_mirror_enabled: bool = False
    rclone_remote_path_verified: bool = False
    rclone_sync_policy: str = "after_success"
    rclone_sync_cron_expression: Optional[str] = None
    rclone_sync_timezone: Optional[str] = None
    rclone_extra_flags: Optional[List[str]] = None
    rclone_cache_path: Optional[str] = None


class RepositoryImport(BaseModel):
    name: str
    borg_version: Optional[int] = 1
    path: str
    encryption: str = "none"
    passphrase: Optional[str] = None  # Required if repository is encrypted
    compression: str = "lz4"  # Default compression for future backups
    source_directories: Optional[List[str]] = None  # List of directories to backup
    source_locations: Optional[List[Dict[str, Any]]] = None
    exclude_patterns: Optional[List[str]] = None  # List of exclude patterns
    connection_id: Optional[int] = None  # SSH connection ID for repository location
    remote_path: Optional[str] = None  # Path to borg on remote server
    pre_backup_script: Optional[str] = None  # Script to run before backup
    post_backup_script: Optional[str] = None  # Script to run after backup
    hook_timeout: Optional[int] = (
        300  # Hook timeout in seconds (legacy, use pre/post_hook_timeout)
    )
    pre_hook_timeout: Optional[int] = 300  # Pre-backup hook timeout in seconds
    post_hook_timeout: Optional[int] = 300  # Post-backup hook timeout in seconds
    continue_on_hook_failure: Optional[bool] = (
        False  # Continue backup if pre-hook fails
    )
    skip_on_hook_failure: Optional[bool] = (
        False  # Skip backup gracefully if pre-hook fails
    )
    mode: str = "full"  # full: backups + observability, observe: observability-only
    bypass_lock: bool = (
        False  # Use --bypass-lock for read-only storage access (observe-only repos)
    )
    custom_flags: Optional[str] = (
        None  # Custom command-line flags for borg create (e.g., "--stats --list")
    )
    upload_ratelimit_kib: Optional[int] = None
    source_connection_id: Optional[int] = (
        None  # SSH connection ID for remote data source (pull-based backups)
    )
    keyfile_content: Optional[str] = (
        None  # Content of borg keyfile for keyfile/keyfile-blake2 encryption
    )
    execution_target: str = "local"  # local, ssh, agent
    executor_type: Optional[str] = None  # server, agent
    agent_machine_id: Optional[int] = None  # Agent that executes backups
    storage_backend: str = "local"  # local, ssh, agent_local, rclone
    rclone_remote_id: Optional[int] = None
    rclone_remote_path: Optional[str] = None
    cloud_mirror_enabled: bool = False
    rclone_remote_path_verified: bool = False
    rclone_sync_policy: str = "after_success"
    rclone_sync_cron_expression: Optional[str] = None
    rclone_sync_timezone: Optional[str] = None
    rclone_extra_flags: Optional[List[str]] = None
    rclone_cache_path: Optional[str] = None


class RepositoryUpdate(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    compression: Optional[str] = None
    source_directories: Optional[List[str]] = None
    source_locations: Optional[List[Dict[str, Any]]] = None
    exclude_patterns: Optional[List[str]] = None
    connection_id: Optional[int] = None  # SSH connection ID for repository location
    remote_path: Optional[str] = None
    pre_backup_script: Optional[str] = None
    post_backup_script: Optional[str] = None
    pre_backup_script_parameters: Optional[Dict[str, Any]] = None
    post_backup_script_parameters: Optional[Dict[str, Any]] = None
    hook_timeout: Optional[int] = None  # Legacy, use pre/post_hook_timeout
    pre_hook_timeout: Optional[int] = None
    post_hook_timeout: Optional[int] = None
    continue_on_hook_failure: Optional[bool] = None
    skip_on_hook_failure: Optional[bool] = (
        None  # Skip backup gracefully if pre-hook fails
    )
    mode: Optional[str] = (
        None  # full: backups + observability, observe: observability-only
    )
    bypass_lock: Optional[bool] = None  # Use --bypass-lock for read-only storage access
    custom_flags: Optional[str] = None  # Custom command-line flags for borg create
    upload_ratelimit_kib: Optional[int] = None
    source_connection_id: Optional[int] = (
        None  # SSH connection ID for remote data source
    )
    execution_target: Optional[str] = None  # local, ssh, agent
    executor_type: Optional[str] = None  # server, agent
    agent_machine_id: Optional[int] = None  # Agent that executes backups
    storage_backend: Optional[str] = None
    rclone_remote_id: Optional[int] = None
    rclone_remote_path: Optional[str] = None
    cloud_mirror_enabled: Optional[bool] = None
    rclone_remote_path_verified: Optional[bool] = None
    rclone_sync_policy: Optional[str] = None
    rclone_sync_cron_expression: Optional[str] = None
    rclone_sync_timezone: Optional[str] = None
    rclone_extra_flags: Optional[List[str]] = None
    rclone_cache_path: Optional[str] = None


class RepositoryInfo(BaseModel):
    id: int
    name: str
    path: str
    encryption: str
    compression: str
    source_directories: Optional[List[str]]
    last_backup: Optional[str]
    total_size: Optional[str]
    archive_count: int
    is_active: bool
    created_at: str
    updated_at: Optional[str]


def _uses_borg2_payload(data: Union[RepositoryCreate, RepositoryImport]) -> bool:
    requested_version = getattr(data, "borg_version", 1) or 1
    return requested_version == 2 or data.encryption in V2_ONLY_ENCRYPTION_MODES


def _is_rclone_payload(data: Union[RepositoryCreate, RepositoryImport]) -> bool:
    return (getattr(data, "storage_backend", "local") or "local") == "rclone"


def _payload_uses_rclone(data: Union[RepositoryCreate, RepositoryImport]) -> bool:
    return (
        _is_rclone_payload(data)
        or _is_direct_rclone_payload(data)
        or getattr(data, "cloud_mirror_enabled", False) is True
    )


def _require_rclone_feature(db: Session) -> None:
    require_feature_access(db, RCLONE_FEATURE)


def _require_managed_agents_feature(db: Session) -> None:
    require_feature_access(db, MANAGED_AGENTS_FEATURE)


def _is_direct_rclone_payload(
    data: Union[RepositoryCreate, RepositoryImport, RepositoryUpdate],
) -> bool:
    return (
        getattr(data, "storage_backend", "local") or "local"
    ).lower() == DIRECT_RCLONE_STORAGE_BACKEND


def _is_direct_rclone_url(path: Optional[str]) -> bool:
    return bool((path or "").strip().startswith("rclone:"))


def _normalize_direct_rclone_url(path: Optional[str]) -> str:
    repo_path = (path or "").strip()
    if (
        not repo_path
        or not repo_path.startswith("rclone:")
        or repo_path in {"rclone:", "rclone://"}
    ):
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.directInvalidUrl"},
        )
    return repo_path


def _is_cloud_mirror_payload(
    data: Union[RepositoryCreate, RepositoryImport, RepositoryUpdate],
) -> bool:
    return bool(getattr(data, "cloud_mirror_enabled", False))


def _primary_storage_backend(repository: Repository) -> str:
    if repository.repository_type == "rclone":
        if (repository.borg_version or 1) == 2 and _is_direct_rclone_url(
            repository.path
        ):
            return DIRECT_RCLONE_STORAGE_BACKEND
        return "rclone"
    if repository_executor_type(repository) == "agent":
        return "agent_local"
    if repository.connection_id or repository.repository_type == "ssh":
        return "ssh"
    return "local"


def _mirror_source_backend_for_payload(
    data: Union[RepositoryCreate, RepositoryImport],
) -> str:
    if _normalize_repository_executor(data) == "agent":
        return "agent"
    storage_backend = (getattr(data, "storage_backend", "local") or "local").lower()
    if data.connection_id or storage_backend == "ssh":
        return "ssh"
    return "local"


def _mirror_source_backend_for_repository(repository: Repository) -> str:
    if repository_executor_type(repository) == "agent":
        return "agent"
    if (
        repository.connection_id
        or repository.repository_type == "ssh"
        or (repository.path or "").startswith("ssh://")
    ):
        return "ssh"
    return "local"


def _require_agent_capability(agent: AgentMachine, capability: str) -> None:
    capabilities = agent.capabilities or []
    if capability not in capabilities:
        raise HTTPException(
            status_code=409,
            detail={
                "key": "backend.errors.agents.capabilityMissing",
                "params": {"capability": capability},
            },
        )


def _require_agent_rclone_sync_capability(
    agent_machine_id: Optional[int], db: Session
) -> AgentMachine:
    agent = _require_queueable_agent(agent_machine_id, db)
    _require_agent_capability(agent, AGENT_RCLONE_SYNC_CAPABILITY)
    return agent


def _repository_has_cloud_mirror(
    repository: Repository, storage: RepositoryStorage | None
) -> bool:
    return bool(
        storage
        and storage.backend == "rclone"
        and repository.repository_type != "rclone"
    )


def _is_direct_rclone_repository(
    repository: Repository, storage: RepositoryStorage | None = None
) -> bool:
    return bool(
        repository.repository_type == "rclone"
        and (repository.borg_version or 1) == 2
        and _is_direct_rclone_url(repository.path)
        and storage is None
    )


def _apply_mirror_source_strategy(
    storage: RepositoryStorage, repository: Repository
) -> None:
    source_backend = _mirror_source_backend_for_repository(repository)
    if source_backend == "agent":
        storage.cache_path = None
        storage.sync_direction = SYNC_DIRECTION_AGENT_TO_REMOTE
    elif source_backend == "ssh":
        storage.cache_path = None
        storage.sync_direction = SYNC_DIRECTION_SSHFS_TO_REMOTE
    else:
        storage.cache_path = repository.path
        storage.sync_direction = SYNC_DIRECTION_PRIMARY_TO_REMOTE


def _reject_unsupported_rclone_borg2(
    data: Union[RepositoryCreate, RepositoryImport],
) -> None:
    if _is_rclone_payload(data) and _uses_borg2_payload(data):
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.borgV2Unsupported"},
        )


def _raise_direct_rclone_incompatible_payload() -> None:
    raise HTTPException(
        status_code=400,
        detail={"key": "backend.errors.rclone.directIncompatiblePayload"},
    )


def _validate_direct_rclone_payload(
    data: Union[RepositoryCreate, RepositoryImport],
    db: Session,
) -> str:
    if (data.borg_version or 1) != 2:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.directBorg2Required"},
        )

    if (
        getattr(data, "rclone_cache_path", None)
        or data.connection_id
        or _normalize_repository_executor(data) == "agent"
        or _normalize_execution_target(data.execution_target) != "local"
        or data.agent_machine_id is not None
        or data.cloud_mirror_enabled
        or data.rclone_remote_id is not None
        or bool((data.rclone_remote_path or "").strip())
        or bool(data.rclone_extra_flags)
        or data.rclone_sync_policy != "after_success"
        or bool((data.rclone_sync_cron_expression or "").strip())
        or bool((data.rclone_sync_timezone or "").strip())
    ):
        _raise_direct_rclone_incompatible_payload()

    repo_path = _normalize_direct_rclone_url(data.path)
    _require_borg2_feature(db)
    return repo_path


def _validate_direct_rclone_update(
    repo_data: RepositoryUpdate,
    update_data: dict[str, Any],
) -> None:
    if (
        repo_data.cloud_mirror_enabled is True
        or repo_data.rclone_remote_path_verified is True
        or bool((repo_data.rclone_cache_path or "").strip())
        or repo_data.rclone_remote_id is not None
        or bool((repo_data.rclone_remote_path or "").strip())
        or bool(repo_data.rclone_extra_flags)
        or bool((repo_data.rclone_sync_cron_expression or "").strip())
        or bool((repo_data.rclone_sync_timezone or "").strip())
        or (
            "rclone_sync_policy" in update_data
            and repo_data.rclone_sync_policy != "after_success"
        )
        or repo_data.connection_id is not None
        or _normalize_repository_executor(repo_data) == "agent"
        or (
            repo_data.execution_target is not None
            and _normalize_execution_target(repo_data.execution_target) != "local"
        )
        or repo_data.agent_machine_id is not None
    ):
        _raise_direct_rclone_incompatible_payload()

    if (
        "storage_backend" in update_data
        and repo_data.storage_backend != DIRECT_RCLONE_STORAGE_BACKEND
    ):
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.updateUnsupported"},
        )

    if repo_data.path is not None:
        _normalize_direct_rclone_url(repo_data.path)


def _strip_direct_rclone_noop_update_fields(update_data: dict[str, Any]) -> None:
    for key in (
        "storage_backend",
        "rclone_remote_id",
        "rclone_remote_path",
        "rclone_sync_policy",
        "rclone_sync_cron_expression",
        "rclone_sync_timezone",
        "rclone_extra_flags",
        "rclone_cache_path",
        "cloud_mirror_enabled",
        "rclone_remote_path_verified",
        "connection_id",
        "agent_machine_id",
    ):
        update_data.pop(key, None)


def _strip_cached_rclone_noop_update_fields(
    repo_data: RepositoryUpdate, update_data: dict[str, Any]
) -> None:
    if "storage_backend" in update_data and repo_data.storage_backend != "rclone":
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.updateUnsupported"},
        )

    if "connection_id" in update_data:
        if repo_data.connection_id is not None:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.rclone.updateUnsupported"},
            )
        update_data.pop("connection_id", None)

    if "execution_target" in update_data:
        if _normalize_execution_target(repo_data.execution_target) != "local":
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.rclone.updateUnsupported"},
            )
        update_data.pop("execution_target", None)

    if "executor_type" in update_data:
        if _normalize_repository_executor(repo_data) != "server":
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.rclone.updateUnsupported"},
            )
        update_data.pop("executor_type", None)

    if "agent_machine_id" in update_data:
        if repo_data.agent_machine_id is not None:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.rclone.updateUnsupported"},
            )
        update_data.pop("agent_machine_id", None)


def _strip_disabled_rclone_noop_update_fields(update_data: dict[str, Any]) -> None:
    default_values = {
        "cloud_mirror_enabled": {None, False},
        "rclone_remote_id": {None},
        "rclone_remote_path": {None, ""},
        "rclone_remote_path_verified": {None, False},
        "rclone_sync_policy": {None, "after_success"},
        "rclone_sync_cron_expression": {None, ""},
        "rclone_sync_timezone": {None, ""},
    }
    for key, allowed_values in default_values.items():
        if key in update_data and update_data[key] in allowed_values:
            update_data.pop(key, None)
    if "rclone_extra_flags" in update_data and update_data["rclone_extra_flags"] in (
        None,
        [],
    ):
        update_data.pop("rclone_extra_flags", None)


def _rclone_feature_gate_updates(
    repo_data: RepositoryUpdate,
    update_data: dict[str, Any],
    requested_rclone_updates: set[str],
) -> set[str]:
    if repo_data.cloud_mirror_enabled is True:
        return requested_rclone_updates

    exempt_updates = {"cloud_mirror_enabled"}
    if update_data.get("storage_backend") in (None, "local", "ssh", "agent_local"):
        exempt_updates.add("storage_backend")

    default_values = {
        "rclone_remote_id": {None},
        "rclone_remote_path": {None, ""},
        "rclone_remote_path_verified": {None, False},
        "rclone_sync_policy": {None, "after_success"},
        "rclone_sync_cron_expression": {None, ""},
        "rclone_sync_timezone": {None, ""},
        "rclone_cache_path": {None, ""},
    }
    for key, allowed_values in default_values.items():
        if key in update_data and update_data[key] in allowed_values:
            exempt_updates.add(key)

    if update_data.get("rclone_extra_flags") in (None, []):
        exempt_updates.add("rclone_extra_flags")

    return requested_rclone_updates - exempt_updates


def _raise_rclone_schedule_error(exc: Exception) -> None:
    message = str(exc) or exc.__class__.__name__
    if isinstance(exc, InvalidScheduleTimezone):
        key = "backend.errors.rclone.invalidScheduleTimezone"
    elif "cron expression is required" in message:
        key = "backend.errors.rclone.scheduleCronRequired"
    elif "invalid rclone sync policy" in message:
        key = "backend.errors.rclone.invalidSyncPolicy"
    else:
        key = "backend.errors.rclone.invalidScheduleCron"
    raise HTTPException(
        status_code=400,
        detail={"key": key, "message": message},
    ) from exc


def _validate_rclone_schedule_payload(
    data: Union[RepositoryCreate, RepositoryImport, RepositoryUpdate],
    *,
    storage: RepositoryStorage | None = None,
) -> None:
    policy = (
        data.rclone_sync_policy
        if data.rclone_sync_policy is not None
        else (storage.sync_policy if storage else "after_success")
    )
    if policy not in VALID_SYNC_POLICIES:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.invalidSyncPolicy"},
        )
    if policy != "scheduled":
        timezone_value = data.rclone_sync_timezone
        if timezone_value is not None:
            try:
                normalize_schedule_timezone(timezone_value)
            except InvalidScheduleTimezone as exc:
                _raise_rclone_schedule_error(exc)
        return

    cron_expression = (
        data.rclone_sync_cron_expression
        if data.rclone_sync_cron_expression is not None
        else (storage.sync_cron_expression if storage else None)
    )
    cron_expression = (cron_expression or "").strip()
    if not cron_expression:
        _raise_rclone_schedule_error(
            ValueError("rclone schedule cron expression is required")
        )

    timezone_value = (
        data.rclone_sync_timezone
        if data.rclone_sync_timezone is not None
        else (storage.sync_timezone if storage else DEFAULT_SCHEDULE_TIMEZONE)
    )
    try:
        timezone_name = normalize_schedule_timezone(timezone_value)
        calculate_next_cron_run(
            cron_expression,
            datetime.now(timezone.utc),
            timezone_name,
        )
    except Exception as exc:
        _raise_rclone_schedule_error(exc)


def _validate_rclone_payload(
    data: Union[RepositoryCreate, RepositoryImport],
    db: Session,
) -> RcloneRemote:
    if getattr(data, "rclone_cache_path", None):
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.cachePathServerOwned"},
        )
    if _normalize_repository_executor(data) == "agent":
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.agentUnsupported"},
        )
    if data.connection_id:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.sshConnectionUnsupported"},
        )
    if not data.rclone_remote_id:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.remoteRequired"},
        )
    if not data.rclone_remote_path:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.remotePathRequired"},
        )
    if data.rclone_sync_policy not in VALID_SYNC_POLICIES:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.invalidSyncPolicy"},
        )
    _validate_rclone_schedule_payload(data)
    remote = (
        db.query(RcloneRemote).filter(RcloneRemote.id == data.rclone_remote_id).first()
    )
    if not remote:
        raise HTTPException(
            status_code=404,
            detail={"key": "backend.errors.rclone.remoteNotFound"},
        )
    try:
        normalize_extra_flags(data.rclone_extra_flags)
        rclone_repository_service.build_storage(
            repository_id=1,
            remote_id=remote.id,
            remote_path=data.rclone_remote_path,
            sync_policy=data.rclone_sync_policy,
            extra_flags=data.rclone_extra_flags,
            sync_cron_expression=data.rclone_sync_cron_expression,
            sync_timezone=data.rclone_sync_timezone,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.invalidPayload", "message": str(exc)},
        ) from exc
    return remote


def _validate_cloud_mirror_payload(
    data: Union[RepositoryCreate, RepositoryImport],
    db: Session,
) -> RcloneRemote | None:
    if getattr(data, "rclone_cache_path", None):
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.cachePathServerOwned"},
        )
    if not _is_cloud_mirror_payload(data):
        return None
    source_backend = _mirror_source_backend_for_payload(data)
    if source_backend == "agent":
        _require_agent_rclone_sync_capability(data.agent_machine_id, db)
    if source_backend == "ssh" and not data.connection_id:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.mirrorUnsupportedPrimary"},
        )
    if not data.rclone_remote_id:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.remoteRequired"},
        )
    if not data.rclone_remote_path:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.remotePathRequired"},
        )
    if data.rclone_sync_policy not in VALID_SYNC_POLICIES:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.invalidSyncPolicy"},
        )
    _validate_rclone_schedule_payload(data)
    remote = (
        db.query(RcloneRemote).filter(RcloneRemote.id == data.rclone_remote_id).first()
    )
    if not remote:
        raise HTTPException(
            status_code=404,
            detail={"key": "backend.errors.rclone.remoteNotFound"},
        )
    try:
        normalize_extra_flags(data.rclone_extra_flags)
        normalize_rclone_relative_path(data.rclone_remote_path)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.invalidPayload", "message": str(exc)},
        ) from exc
    return remote


async def _preflight_cloud_mirror_path(
    data: Union[RepositoryCreate, RepositoryImport],
    remote: RcloneRemote | None,
) -> None:
    if not remote:
        return
    try:
        await rclone_repository_service.preflight_remote_path(
            remote,
            data.rclone_remote_path or "",
            verified_non_empty=bool(data.rclone_remote_path_verified),
        )
    except ValueError as exc:
        message = str(exc)
        key = (
            "backend.errors.rclone.remotePathNotVerified"
            if "not empty" in message
            else "backend.errors.rclone.remotePathPreflightFailed"
        )
        raise HTTPException(
            status_code=400,
            detail={"key": key, "message": message},
        ) from exc


def _discard_rclone_repository_record(
    db: Session,
    repository: Repository,
    storage: RepositoryStorage,
) -> None:
    repository_id = repository.id
    cache_path = storage.cache_path
    db.rollback()
    if repository_id is not None:
        db.query(RepositoryStorage).filter(
            RepositoryStorage.repository_id == repository_id
        ).delete(synchronize_session=False)
        db.query(Repository).filter(Repository.id == repository_id).delete(
            synchronize_session=False
        )
        db.commit()
    if cache_path:
        shutil.rmtree(cache_path, ignore_errors=True)


def _serialize_rclone_storage(
    repository: Repository, db: Session, *, log_save_policy: str | None = None
) -> Optional[Dict[str, Any]]:
    storage = (
        db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .first()
    )
    if not storage or storage.backend != "rclone":
        return None
    remote = (
        db.query(RcloneRemote)
        .filter(RcloneRemote.id == storage.rclone_remote_id)
        .first()
    )
    status = rclone_repository_service.serialize_status(repository, storage, remote)
    status.update(_agent_machine_summary(repository, db))
    latest_job = (
        db.query(RcloneSyncJob)
        .filter(RcloneSyncJob.repository_id == repository.id)
        .order_by(RcloneSyncJob.created_at.desc(), RcloneSyncJob.id.desc())
        .first()
    )
    if log_save_policy is None:
        log_save_policy = get_log_save_policy(db)
    status["latest_sync_job"] = (
        {
            "id": latest_job.id,
            "triggered_by": latest_job.triggered_by,
            "status": latest_job.status,
            "scheduled_for": format_datetime(latest_job.scheduled_for),
            "started_at": format_datetime(latest_job.started_at),
            "completed_at": format_datetime(latest_job.completed_at),
            "error_text": latest_job.error_text,
            "operation": latest_job.operation,
            "has_log": job_has_logs_by_policy(
                latest_job,
                log_save_policy,
                output_text=[latest_job.log_text, latest_job.error_text],
                file_path=latest_job.log_path,
            ),
        }
        if latest_job
        else None
    )
    return status


def _mark_background_rclone_sync_failed(job_id: int, message: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(RcloneSyncJob).filter(RcloneSyncJob.id == job_id).first()
        if not job:
            return
        storage = (
            db.query(RepositoryStorage)
            .filter(RepositoryStorage.repository_id == job.repository_id)
            .first()
        )
        if storage:
            storage.sync_status = "failed"
            storage.last_sync_error = message
        job.status = "failed"
        job.completed_at = datetime.now(timezone.utc)
        job.error_text = message
        job.log_text = (
            f"{job.log_text.rstrip()}\n{message}" if job.log_text else message
        )
        db.commit()
    finally:
        db.close()


async def _run_background_rclone_sync_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.query(RcloneSyncJob).filter(RcloneSyncJob.id == job_id).first()
        if job is None:
            logger.warning("Skipping missing background rclone sync job", job_id=job_id)
            return
        repository = (
            db.query(Repository).filter(Repository.id == job.repository_id).first()
        )
        if repository is None:
            raise ValueError(f"repository {job.repository_id} was not found")

        async def run_sync():
            return await rclone_repository_service.sync_repository(
                db,
                repository,
                triggered_by=job.triggered_by,
                scheduled_for=job.scheduled_for,
                job_id=job.id,
            )

        await run_serialized_repository_command(repository.id, run_sync, scope="rclone")
    except asyncio.CancelledError:
        message = "Background rclone sync job was cancelled"
        logger.info(message, job_id=job_id)
        db.rollback()
        _mark_background_rclone_sync_failed(job_id, message)
        raise
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        logger.error(
            "Background rclone sync job failed",
            job_id=job_id,
            error=message,
        )
        db.rollback()
        _mark_background_rclone_sync_failed(job_id, message)
    finally:
        db.close()


def _log_background_rclone_sync_task_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        logger.info("Background rclone sync job was cancelled")
    except Exception as exc:
        logger.error("Background rclone sync task raised", error=str(exc))


def _queue_initial_cloud_mirror_sync(db: Session, repository: Repository) -> None:
    storage = (
        db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .first()
    )
    if not storage or storage.backend != "rclone":
        return
    sync_job = RcloneSyncJob(
        repository_id=repository.id,
        direction=storage.sync_direction,
        operation="sync",
        status="pending",
        triggered_by="initial",
    )
    db.add(sync_job)
    storage.sync_status = "pending"
    storage.last_sync_error = None
    db.commit()
    db.refresh(sync_job)
    task = asyncio.create_task(_run_background_rclone_sync_job(sync_job.id))
    task.add_done_callback(_log_background_rclone_sync_task_result)


def resume_pending_initial_cloud_mirror_sync_jobs() -> int:
    db = SessionLocal()
    try:
        jobs = (
            db.query(RcloneSyncJob)
            .filter(
                RcloneSyncJob.operation == "sync",
                RcloneSyncJob.triggered_by == "initial",
                RcloneSyncJob.status.in_(("pending", "running")),
            )
            .order_by(RcloneSyncJob.id.asc())
            .all()
        )
        dispatched = 0
        for job in jobs:
            storage = (
                db.query(RepositoryStorage)
                .filter(RepositoryStorage.repository_id == job.repository_id)
                .first()
            )
            if storage:
                storage.sync_status = "pending"
                storage.last_sync_error = None
            job.status = "pending"
            job.completed_at = None
            job.error_text = None
            db.commit()
            task = asyncio.create_task(_run_background_rclone_sync_job(job.id))
            task.add_done_callback(_log_background_rclone_sync_task_result)
            dispatched += 1
        return dispatched
    finally:
        db.close()


def _agent_machine_summary(repository: Repository, db: Session) -> Dict[str, Any]:
    if not repository.agent_machine_id:
        return {
            "agent_machine_name": None,
            "agent_machine_status": None,
        }
    agent = (
        db.query(AgentMachine)
        .filter(AgentMachine.id == repository.agent_machine_id)
        .first()
    )
    return {
        "agent_machine_name": agent.name if agent else None,
        "agent_machine_status": agent.status if agent else None,
    }


def _require_borg2_feature(db: Session) -> None:
    current_plan = get_current_plan(db)
    required = FEATURES["borg_v2"]
    if not plan_includes(current_plan, required):
        raise HTTPException(
            status_code=403,
            detail={
                "key": "backend.errors.plan.featureNotAvailable",
                "feature": "borg_v2",
                "required": required.value,
                "current": current_plan.value,
            },
        )


def _normalize_execution_target(value: Optional[str]) -> str:
    execution_target = (value or "local").strip().lower()
    if execution_target not in {"local", "ssh", "agent"}:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.invalidExecutionTarget"},
        )
    return execution_target


def _normalize_repository_executor(
    repo_data: Union[RepositoryCreate, RepositoryImport, RepositoryUpdate],
) -> str:
    return normalize_executor_type(
        getattr(repo_data, "executor_type", None),
        execution_target=getattr(repo_data, "execution_target", None),
    )


def _strip_ssh_url_path(path: str) -> str:
    return strip_ssh_url_path(path)


def _build_repository_path_from_connection(
    raw_path: str, connection_id: int, db: Session
) -> str:
    connection_details = get_connection_details(connection_id, db)
    return build_ssh_repository_path(raw_path, connection_details)


def _require_queueable_agent(
    agent_machine_id: Optional[int], db: Session
) -> AgentMachine:
    if agent_machine_id is None:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.agents.agentRequired"},
        )

    agent = db.query(AgentMachine).filter(AgentMachine.id == agent_machine_id).first()
    if not agent:
        raise HTTPException(
            status_code=404,
            detail={"key": "backend.errors.agents.agentNotFound"},
        )
    if agent.deleted_at is not None or agent.status in ("disabled", "revoked"):
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.agents.agentNotQueueable"},
        )
    return agent


def _reject_agent_repository_ssh_target(
    *,
    path: Optional[str],
    connection_id: Optional[int],
    execution_target: Optional[str],
) -> None:
    """Reject only a server-managed SSH connection for an agent repository.

    An agent reaches its repository over its OWN SSH setup (mounted key /
    known_hosts), so ``ssh://`` paths and ``execution_target="ssh"`` are fully
    supported: the agent backup/operation payload already carries the path +
    remote_path and the agent runs ``borg ... --remote-path`` itself. Only a
    server-managed ``connection_id`` (an ``ssh_connections`` row that only the
    Borg UI server can use, not the agent) stays unsupported.
    """
    if connection_id:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.agentRepositorySshUnsupported"},
        )


async def _validate_agent_repository_payload(
    repo_data: Union[RepositoryCreate, RepositoryImport], db: Session
) -> AgentMachine:
    _reject_agent_repository_ssh_target(
        path=repo_data.path,
        connection_id=repo_data.connection_id,
        execution_target=repo_data.execution_target,
    )
    agent = _require_queueable_agent(repo_data.agent_machine_id, db)

    encrypted = repo_data.encryption in [
        "repokey",
        "keyfile",
        "repokey-blake2",
        "keyfile-blake2",
        "repokey-aes-ocb",
        "repokey-chacha20-poly1305",
        "keyfile-aes-ocb",
        "keyfile-chacha20-poly1305",
    ]
    if encrypted and not (repo_data.passphrase or "").strip():
        # Agent repos run every borg op on the agent, so the server never needs
        # the passphrase — but confirm the agent has one, or the repo would be
        # openable by neither. The agent returns a boolean, never the value.
        if not await _agent_has_passphrase(agent):
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.repo.agentPassphraseUnavailable",
                    "params": {"mode": repo_data.encryption},
                },
            )

    return agent


async def _agent_has_passphrase(agent: AgentMachine) -> bool:
    """Ask the agent whether it has a ``$BORG_PASSPHRASE`` of its own — a
    boolean, never the passphrase value. False when the agent is offline or does
    not set one."""
    try:
        result = await agent_connection_manager.send_command(
            agent.id,
            command="agent.repository_defaults",
            payload={},
            timeout_seconds=AGENT_FILESYSTEM_BROWSE_TIMEOUT_SECONDS,
            wait_for_result=True,
        )
    except (AgentConnectionUnavailable, AgentCommandTimeout, AgentCommandError):
        return False
    except Exception:
        # Fail closed: any unexpected error reaching the agent (e.g. the websocket
        # layer re-raising a connection reset) must not surface as a 500 — treat it
        # as "passphrase not confirmed" so the caller asks for one instead.
        logger.warning(
            "Failed to confirm agent passphrase; treating as unavailable",
            agent_id=agent.id,
            exc_info=True,
        )
        return False
    return bool(isinstance(result, dict) and result.get("has_passphrase"))


async def _create_agent_repository_record(
    repo_data: Union[RepositoryCreate, RepositoryImport],
    current_user: User,
    db: Session,
    *,
    imported: bool,
):
    cloud_mirror_remote = _validate_cloud_mirror_payload(repo_data, db)
    await _preflight_cloud_mirror_path(repo_data, cloud_mirror_remote)
    agent = await _validate_agent_repository_payload(repo_data, db)
    if not imported:
        _require_agent_capability(agent, AGENT_REPOSITORY_INIT_CAPABILITY)
    if cloud_mirror_remote:
        _require_agent_capability(agent, AGENT_RCLONE_SYNC_CAPABILITY)
    repo_path = repo_data.path.strip()
    if not repo_path:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.pathRequired"},
        )

    if db.query(Repository).filter(Repository.name == repo_data.name).first():
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.repositoryNameExists"},
        )

    if db.query(Repository).filter(Repository.path == repo_path).first():
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.repositoryPathExists"},
        )

    (
        source_locations,
        source_connection_id,
        source_directories,
    ) = _normalize_repository_source_payload(
        source_locations=repo_data.source_locations,
        source_connection_id=repo_data.source_connection_id,
        source_directories=repo_data.source_directories,
    )
    source_directories_json = (
        json.dumps(source_directories) if source_directories else None
    )
    source_locations_json = json.dumps(source_locations) if source_locations else None
    exclude_patterns_json = (
        json.dumps(repo_data.exclude_patterns) if repo_data.exclude_patterns else None
    )

    repository = Repository(
        name=repo_data.name,
        path=repo_path,
        encryption=repo_data.encryption,
        compression=repo_data.compression,
        passphrase=repo_data.passphrase,
        source_directories=source_directories_json,
        exclude_patterns=exclude_patterns_json,
        connection_id=None,
        remote_path=repo_data.remote_path,
        repository_type="local",
        execution_target="agent",
        executor_type="agent",
        agent_machine_id=agent.id,
        pre_backup_script=repo_data.pre_backup_script,
        post_backup_script=repo_data.post_backup_script,
        hook_timeout=repo_data.hook_timeout,
        pre_hook_timeout=repo_data.pre_hook_timeout,
        post_hook_timeout=repo_data.post_hook_timeout,
        continue_on_hook_failure=repo_data.continue_on_hook_failure,
        skip_on_hook_failure=repo_data.skip_on_hook_failure,
        mode=repo_data.mode,
        bypass_lock=repo_data.bypass_lock,
        custom_flags=repo_data.custom_flags,
        upload_ratelimit_kib=repo_data.upload_ratelimit_kib,
        source_ssh_connection_id=source_connection_id,
        source_locations=source_locations_json,
        borg_version=repo_data.borg_version or 1,
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)

    if not imported:
        repository_id = repository.id
        try:
            agent_job = queue_agent_repository_operation_job(
                db,
                repository,
                job_kind=AGENT_REPOSITORY_INIT_CAPABILITY,
                operation={"encryption": repository.encryption},
            )
            await dispatch_agent_job_best_effort(
                db,
                agent_job,
                repository_id=repository.id,
            )
            await wait_for_agent_repository_operation_job(
                db,
                agent_job.id,
                timeout_seconds=get_operation_timeouts(db)["init_timeout"],
            )
        except Exception:
            db.rollback()
            repository_to_delete = (
                db.query(Repository).filter(Repository.id == repository_id).first()
            )
            if repository_to_delete:
                db.delete(repository_to_delete)
                db.commit()
            raise

    if cloud_mirror_remote:
        storage = rclone_repository_service.build_mirror_storage(
            repository_id=repository.id,
            source_path=repository.path,
            source_backend="agent",
            remote_id=cloud_mirror_remote.id,
            remote_path=repo_data.rclone_remote_path or "",
            sync_policy=repo_data.rclone_sync_policy,
            extra_flags=repo_data.rclone_extra_flags,
            sync_cron_expression=repo_data.rclone_sync_cron_expression,
            sync_timezone=repo_data.rclone_sync_timezone,
        )
        db.add(storage)
        db.commit()
        if repo_data.rclone_sync_policy == "after_success":
            await rclone_repository_service.sync_repository(db, repository)

    logger.info(
        "Agent-managed repository recorded",
        name=repository.name,
        path=repository.path,
        agent_id=agent.agent_id,
        imported=imported,
        user=current_user.username,
    )

    try:
        mqtt_service.sync_state_with_db(db, reason="agent repository creation")
    except Exception as e:
        logger.warning(
            "Failed to sync repositories with MQTT after agent repository creation",
            repo_id=repository.id,
            error=str(e),
        )

    repository_payload = {
        "id": repository.id,
        "name": repository.name,
        "path": repository.path,
        "encryption": repository.encryption,
        "compression": repository.compression,
        "execution_target": repository.execution_target,
        "executor_type": repository.executor_type,
        "agent_machine_id": repository.agent_machine_id,
        **_agent_machine_summary(repository, db),
        "upload_ratelimit_kib": repository.upload_ratelimit_kib,
    }
    rclone_storage = _serialize_rclone_storage(repository, db)
    if rclone_storage:
        repository_payload["storage_backend"] = _primary_storage_backend(repository)
        repository_payload["rclone_storage"] = rclone_storage

    return {
        "success": True,
        "message": "backend.success.repo.repositoryImported"
        if imported
        else "backend.success.repo.repositoryCreated",
        "repository": repository_payload,
    }


def _validate_repository_name_available(name: str, db: Session) -> None:
    existing_repo = db.query(Repository).filter(Repository.name == name).first()
    if existing_repo:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.repositoryNameExists"},
        )


def _repository_common_values(
    repo_data: Union[RepositoryCreate, RepositoryImport],
) -> dict[str, Any]:
    return {
        "name": repo_data.name,
        "encryption": repo_data.encryption,
        "compression": repo_data.compression,
        "passphrase": repo_data.passphrase,
        "connection_id": None,
        "remote_path": repo_data.remote_path,
        "pre_backup_script": repo_data.pre_backup_script,
        "post_backup_script": repo_data.post_backup_script,
        "hook_timeout": repo_data.hook_timeout,
        "pre_hook_timeout": repo_data.pre_hook_timeout,
        "post_hook_timeout": repo_data.post_hook_timeout,
        "continue_on_hook_failure": repo_data.continue_on_hook_failure,
        "skip_on_hook_failure": repo_data.skip_on_hook_failure,
        "mode": repo_data.mode,
        "bypass_lock": repo_data.bypass_lock,
        "custom_flags": repo_data.custom_flags,
        "upload_ratelimit_kib": repo_data.upload_ratelimit_kib,
        "execution_target": "local",
        "executor_type": "server",
        "agent_machine_id": None,
        "repository_type": "rclone",
        "borg_version": repo_data.borg_version or 1,
    }


async def _create_rclone_repository_record(
    repo_data: RepositoryCreate,
    current_user: User,
    db: Session,
):
    _validate_rclone_payload(repo_data, db)
    _validate_repository_name_available(repo_data.name, db)

    valid_encryption_modes = {
        "repokey",
        "keyfile",
        "repokey-blake2",
        "keyfile-blake2",
        "none",
    }
    if repo_data.encryption not in valid_encryption_modes:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.invalidEncryptionMode"},
        )
    if repo_data.encryption != "none" and not (repo_data.passphrase or "").strip():
        raise HTTPException(
            status_code=400,
            detail={
                "key": "backend.errors.repo.encryptedPassphraseRequired",
                "params": {"mode": repo_data.encryption},
            },
        )

    (
        source_locations,
        source_connection_id,
        source_directories,
    ) = _normalize_repository_source_payload(
        source_locations=repo_data.source_locations,
        source_connection_id=repo_data.source_connection_id,
        source_directories=repo_data.source_directories,
    )
    exclude_patterns_json = (
        json.dumps(repo_data.exclude_patterns) if repo_data.exclude_patterns else None
    )
    repository = Repository(
        path=f"__rclone_pending__/{uuid.uuid4()}",
        source_directories=json.dumps(source_directories)
        if source_directories
        else None,
        source_locations=json.dumps(source_locations) if source_locations else None,
        exclude_patterns=exclude_patterns_json,
        source_ssh_connection_id=source_connection_id,
        **_repository_common_values(repo_data),
    )
    db.add(repository)
    db.flush()
    storage = rclone_repository_service.build_storage(
        repository_id=repository.id,
        remote_id=repo_data.rclone_remote_id,
        remote_path=repo_data.rclone_remote_path,
        sync_policy=repo_data.rclone_sync_policy,
        extra_flags=repo_data.rclone_extra_flags,
        sync_cron_expression=repo_data.rclone_sync_cron_expression,
        sync_timezone=repo_data.rclone_sync_timezone,
    )
    repository.path = storage.cache_path
    db.add(storage)

    try:
        os.makedirs(storage.cache_path, exist_ok=True)
        init_result = await initialize_borg_repository(
            storage.cache_path,
            repo_data.encryption,
            repo_data.passphrase,
            None,
            None,
        )
        if not init_result["success"]:
            raise HTTPException(
                status_code=500,
                detail=_repository_init_failure_detail(init_result),
            )
        db.commit()
        db.refresh(repository)
        if repo_data.rclone_sync_policy == "after_success":
            await rclone_repository_service.sync_repository(db, repository)
    except HTTPException:
        _discard_rclone_repository_record(db, repository, storage)
        raise
    except Exception as exc:
        _discard_rclone_repository_record(db, repository, storage)
        logger.error(
            "Unexpected rclone repository create failure",
            name=repo_data.name,
            error=str(exc),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.repo.failedToCreateRepository",
                "message": str(exc) or exc.__class__.__name__,
            },
        ) from exc

    logger.info(
        "Rclone repository created",
        name=repository.name,
        path=repository.path,
        user=current_user.username,
    )
    return {
        "success": True,
        "message": "backend.success.repo.repositoryCreated",
        "repository": {
            "id": repository.id,
            "name": repository.name,
            "path": repository.path,
            "encryption": repository.encryption,
            "compression": repository.compression,
            "storage_backend": "rclone",
            "rclone_storage": _serialize_rclone_storage(repository, db),
            "upload_ratelimit_kib": repository.upload_ratelimit_kib,
        },
    }


async def _create_direct_rclone_repository_record(
    repo_data: RepositoryCreate,
    current_user: User,
    db: Session,
):
    repo_path = _validate_direct_rclone_payload(repo_data, db)
    _validate_repository_name_available(repo_data.name, db)

    valid_encryption_modes = V2_ONLY_ENCRYPTION_MODES | {"none"}
    if repo_data.encryption not in valid_encryption_modes:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.invalidEncryptionMode"},
        )
    if repo_data.encryption != "none" and not (repo_data.passphrase or "").strip():
        raise HTTPException(
            status_code=400,
            detail={
                "key": "backend.errors.repo.encryptedPassphraseRequired",
                "params": {"mode": repo_data.encryption},
            },
        )

    existing_path = db.query(Repository).filter(Repository.path == repo_path).first()
    if existing_path:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.repositoryPathExists"},
        )

    init_result = await initialize_borg_repository(
        repo_path,
        repo_data.encryption,
        repo_data.passphrase,
        None,
        None,
        borg_version=2,
    )
    if not init_result["success"]:
        raise HTTPException(
            status_code=500,
            detail=_repository_init_failure_detail(init_result),
        )

    (
        source_locations,
        source_connection_id,
        source_directories,
    ) = _normalize_repository_source_payload(
        source_locations=repo_data.source_locations,
        source_connection_id=repo_data.source_connection_id,
        source_directories=repo_data.source_directories,
    )
    repository = Repository(
        path=repo_path,
        source_directories=json.dumps(source_directories)
        if source_directories
        else None,
        source_locations=json.dumps(source_locations) if source_locations else None,
        exclude_patterns=json.dumps(repo_data.exclude_patterns)
        if repo_data.exclude_patterns
        else None,
        source_ssh_connection_id=source_connection_id,
        **_repository_common_values(repo_data),
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)

    try:
        mqtt_service.sync_state_with_db(db, reason="repository creation")
        logger.info(
            "Synced repositories with MQTT after direct rclone creation",
            repo_id=repository.id,
        )
    except Exception as e:
        logger.warning(
            "Failed to sync repositories with MQTT after direct rclone creation",
            repo_id=repository.id,
            error=str(e),
        )

    logger.info(
        "Direct Borg 2 rclone repository created",
        name=repository.name,
        path=repository.path,
        user=current_user.username,
    )
    return {
        "success": True,
        "message": "backend.success.repo.repositoryCreated",
        "repository": {
            "id": repository.id,
            "name": repository.name,
            "path": repository.path,
            "encryption": repository.encryption,
            "compression": repository.compression,
            "execution_target": repository.execution_target,
            "executor_type": repository.executor_type,
            "agent_machine_id": repository.agent_machine_id,
            "repository_type": "rclone",
            "borg_version": 2,
            "storage_backend": DIRECT_RCLONE_STORAGE_BACKEND,
            "upload_ratelimit_kib": repository.upload_ratelimit_kib,
        },
    }


async def _import_rclone_repository_record(
    repo_data: RepositoryImport,
    current_user: User,
    db: Session,
):
    _validate_rclone_payload(repo_data, db)
    _validate_repository_name_available(repo_data.name, db)

    (
        source_locations,
        source_connection_id,
        source_directories,
    ) = _normalize_repository_source_payload(
        source_locations=repo_data.source_locations,
        source_connection_id=repo_data.source_connection_id,
        source_directories=repo_data.source_directories,
    )
    repository = Repository(
        path=f"__rclone_pending__/{uuid.uuid4()}",
        source_directories=json.dumps(source_directories)
        if source_directories
        else None,
        source_locations=json.dumps(source_locations) if source_locations else None,
        exclude_patterns=json.dumps(repo_data.exclude_patterns)
        if repo_data.exclude_patterns
        else None,
        source_ssh_connection_id=source_connection_id,
        archive_count=0,
        **_repository_common_values(repo_data),
    )
    db.add(repository)
    db.flush()
    storage = rclone_repository_service.build_storage(
        repository_id=repository.id,
        remote_id=repo_data.rclone_remote_id,
        remote_path=repo_data.rclone_remote_path,
        sync_policy=repo_data.rclone_sync_policy,
        extra_flags=repo_data.rclone_extra_flags,
        sync_cron_expression=repo_data.rclone_sync_cron_expression,
        sync_timezone=repo_data.rclone_sync_timezone,
    )
    repository.path = storage.cache_path
    db.add(storage)
    db.flush()

    try:
        hydrate_status = await rclone_repository_service.hydrate_repository(
            db, repository
        )
        if hydrate_status.get("sync_status") != "current":
            storage.sync_status = "failed"
            storage.last_sync_error = (
                hydrate_status.get("last_sync_error") or "rclone hydrate failed"
            )
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.repo.failedToImportRepository"},
            )

        verify_result = await verify_existing_repository(
            repository.path,
            repo_data.passphrase,
            None,
            None,
            repo_data.bypass_lock,
        )
        if not verify_result["success"]:
            storage.sync_status = "failed"
            storage.last_sync_error = (
                verify_result.get("error") or "Borg verification failed"
            )
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.repo.failedToVerifyRepository"},
            )

        repo_info = verify_result.get("info", {})
        repository.encryption = repo_info.get("encryption", {}).get(
            "mode", repo_data.encryption
        )
        db.commit()
        db.refresh(repository)
    except HTTPException:
        _discard_rclone_repository_record(db, repository, storage)
        raise
    except Exception as exc:
        _discard_rclone_repository_record(db, repository, storage)
        logger.error(
            "Unexpected rclone repository import failure",
            name=repo_data.name,
            error=str(exc),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.repo.failedToImportRepository",
                "message": str(exc) or exc.__class__.__name__,
            },
        ) from exc

    logger.info(
        "Rclone repository imported",
        name=repository.name,
        path=repository.path,
        user=current_user.username,
    )
    return {
        "success": True,
        "message": "backend.success.repo.repositoryImported",
        "repository": {
            "id": repository.id,
            "name": repository.name,
            "path": repository.path,
            "encryption": repository.encryption,
            "compression": repository.compression,
            "archive_count": repository.archive_count,
            "storage_backend": "rclone",
            "rclone_storage": _serialize_rclone_storage(repository, db),
            "upload_ratelimit_kib": repository.upload_ratelimit_kib,
        },
    }


async def _import_direct_rclone_repository_record(
    repo_data: RepositoryImport,
    current_user: User,
    db: Session,
):
    repo_path = _validate_direct_rclone_payload(repo_data, db)
    _validate_repository_name_available(repo_data.name, db)

    existing_path = db.query(Repository).filter(Repository.path == repo_path).first()
    if existing_path:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.repositoryPathExists"},
        )

    keyfile_path = None
    if repo_data.keyfile_content:
        keyfile_path = _write_borg_keyfile(repo_path, repo_data.keyfile_content)
        logger.info(
            "Wrote keyfile before direct rclone verification",
            keyfile_path=keyfile_path,
        )

    verify_result = await verify_existing_repository(
        path=repo_path,
        passphrase=repo_data.passphrase,
        ssh_key_id=None,
        remote_path=None,
        bypass_lock=repo_data.bypass_lock,
        borg_version=2,
    )
    if not verify_result["success"]:
        if keyfile_path and os.path.exists(keyfile_path):
            os.unlink(keyfile_path)
            logger.info(
                "Removed keyfile after failed direct rclone verification",
                keyfile_path=keyfile_path,
            )

        error_msg = verify_result.get("error", "Unknown error")
        if "passphrase" in error_msg.lower() or "encrypted" in error_msg.lower():
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.repo.encryptedPassphraseIncorrect"},
            )
        if "not a valid repository" in error_msg.lower():
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.repo.notValidBorgRepository",
                    "params": {"path": repo_path},
                },
            )
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToVerifyRepository"},
        )

    (
        source_locations,
        source_connection_id,
        source_directories,
    ) = _normalize_repository_source_payload(
        source_locations=repo_data.source_locations,
        source_connection_id=repo_data.source_connection_id,
        source_directories=repo_data.source_directories,
    )
    repo_info = verify_result.get("info", {})
    encryption_mode = repo_info.get("encryption", {}).get("mode", repo_data.encryption)
    repository = Repository(
        path=repo_path,
        source_directories=json.dumps(source_directories)
        if source_directories
        else None,
        source_locations=json.dumps(source_locations) if source_locations else None,
        exclude_patterns=json.dumps(repo_data.exclude_patterns)
        if repo_data.exclude_patterns
        else None,
        source_ssh_connection_id=source_connection_id,
        archive_count=0,
        **_repository_common_values(repo_data),
    )
    repository.encryption = encryption_mode
    db.add(repository)
    db.commit()
    db.refresh(repository)

    if keyfile_path:
        repository.has_keyfile = True
        db.commit()
        db.refresh(repository)

    try:
        mqtt_service.sync_state_with_db(db, reason="repository import")
        logger.info(
            "Synced repositories with MQTT after direct rclone import",
            repo_id=repository.id,
        )
    except Exception as e:
        logger.warning(
            "Failed to sync repositories with MQTT after direct rclone import",
            repo_id=repository.id,
            error=str(e),
        )

    logger.info(
        "Direct Borg 2 rclone repository imported",
        name=repository.name,
        path=repository.path,
        user=current_user.username,
    )
    return {
        "success": True,
        "message": "backend.success.repo.repositoryImported",
        "repository": {
            "id": repository.id,
            "name": repository.name,
            "path": repository.path,
            "encryption": repository.encryption,
            "compression": repository.compression,
            "archive_count": repository.archive_count,
            "execution_target": repository.execution_target,
            "executor_type": repository.executor_type,
            "agent_machine_id": repository.agent_machine_id,
            "repository_type": "rclone",
            "borg_version": 2,
            "storage_backend": DIRECT_RCLONE_STORAGE_BACKEND,
            "upload_ratelimit_kib": repository.upload_ratelimit_kib,
        },
    }


@router.get("/")
async def get_repositories(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get all repositories"""
    try:
        # Admins and wildcard-assigned users see all repos.
        if current_user.role == "admin" or current_user.all_repositories_role:
            repositories = db.query(Repository).all()
        else:
            permitted_ids = {
                p.repository_id
                for p in db.query(UserRepositoryPermission)
                .filter_by(user_id=current_user.id)
                .all()
            }
            repositories = (
                db.query(Repository).filter(Repository.id.in_(permitted_ids)).all()
            )

        # Check for running maintenance jobs for each repository
        repo_list = []
        log_save_policy = get_log_save_policy(db)
        for repo in repositories:
            # Check if this repository has running check, compact, or prune jobs
            has_check = (
                db.query(CheckJob)
                .filter(CheckJob.repository_id == repo.id, CheckJob.status == "running")
                .first()
                is not None
            )

            has_compact = (
                db.query(CompactJob)
                .filter(
                    CompactJob.repository_id == repo.id, CompactJob.status == "running"
                )
                .first()
                is not None
            )

            has_prune = (
                db.query(PruneJob)
                .filter(PruneJob.repository_id == repo.id, PruneJob.status == "running")
                .first()
                is not None
            )
            schedule_summary = _get_repository_schedule_summary(repo.id, db)
            source_directories = _decode_json_list_field(repo.source_directories)

            repo_payload = {
                "id": repo.id,
                "name": repo.name,
                "path": repo.path,
                "encryption": repo.encryption,
                "compression": repo.compression,
                "source_directories": source_directories,
                "source_locations": decode_source_locations(
                    repo.source_locations,
                    source_type="remote" if repo.source_ssh_connection_id else "local",
                    source_ssh_connection_id=repo.source_ssh_connection_id,
                    source_directories=source_directories,
                ),
                "exclude_patterns": _decode_json_list_field(repo.exclude_patterns),
                "repository_type": repo.repository_type,
                "execution_target": repo.execution_target or "local",
                "executor_type": repository_executor_type(repo),
                "agent_machine_id": repo.agent_machine_id,
                **_agent_machine_summary(repo, db),
                "host": repo.host,
                "port": repo.port,
                "username": repo.username,
                "ssh_key_id": repo.ssh_key_id,
                "remote_path": repo.remote_path,
                "last_backup": format_datetime(repo.last_backup),
                "last_check": format_datetime(repo.last_check),
                "last_compact": format_datetime(repo.last_compact),
                "total_size": repo.total_size,
                "archive_count": repo.archive_count,
                "created_at": format_datetime(repo.created_at),
                "updated_at": format_datetime(repo.updated_at),
                "pre_backup_script": repo.pre_backup_script,
                "post_backup_script": repo.post_backup_script,
                "pre_backup_script_parameters": repo.pre_backup_script_parameters,
                "post_backup_script_parameters": repo.post_backup_script_parameters,
                "hook_timeout": repo.hook_timeout,
                "pre_hook_timeout": repo.pre_hook_timeout,
                "post_hook_timeout": repo.post_hook_timeout,
                "continue_on_hook_failure": repo.continue_on_hook_failure,
                "skip_on_hook_failure": repo.skip_on_hook_failure,
                "mode": repo.mode
                or "full",  # Default to "full" for backward compatibility
                "bypass_lock": repo.bypass_lock or False,
                "custom_flags": repo.custom_flags,
                "upload_ratelimit_kib": repo.upload_ratelimit_kib,
                "has_running_maintenance": has_check or has_compact or has_prune,
                "has_schedule": schedule_summary["has_schedule"],
                "schedule_enabled": schedule_summary["schedule_enabled"],
                "schedule_name": schedule_summary["schedule_name"],
                "schedule_timezone": schedule_summary["schedule_timezone"],
                "next_run": schedule_summary["next_run"],
                "has_keyfile": repo.has_keyfile or False,
                "source_ssh_connection_id": repo.source_ssh_connection_id,
                "borg_version": repo.borg_version or 1,
            }
            rclone_storage = _serialize_rclone_storage(
                repo, db, log_save_policy=log_save_policy
            )
            if rclone_storage:
                repo_payload["storage_backend"] = _primary_storage_backend(repo)
                repo_payload["rclone_storage"] = rclone_storage
                if repo.repository_type == "rclone":
                    repo_payload["repository_type"] = "rclone"
            elif _is_direct_rclone_repository(repo):
                repo_payload["storage_backend"] = DIRECT_RCLONE_STORAGE_BACKEND
                repo_payload["repository_type"] = "rclone"
            repo_list.append(repo_payload)

        return {"success": True, "repositories": repo_list}
    except Exception as e:
        logger.error("Failed to get repositories", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToRetrieveRepositories"},
        )


@router.post("/")
async def create_repository(
    repo_data: RepositoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new repository"""
    try:
        executor_type = _normalize_repository_executor(repo_data)
        _validate_upload_ratelimit_kib(repo_data.upload_ratelimit_kib)
        if _payload_uses_rclone(repo_data):
            _require_rclone_feature(db)
        if executor_type == "agent":
            _require_managed_agents_feature(db)
        if _is_direct_rclone_payload(repo_data):
            return await _create_direct_rclone_repository_record(
                repo_data, current_user, db
            )
        _reject_unsupported_rclone_borg2(repo_data)
        if _is_rclone_payload(repo_data):
            return await _create_rclone_repository_record(repo_data, current_user, db)
        if _uses_borg2_payload(repo_data):
            _require_borg2_feature(db)
            if executor_type == "agent":
                return await _create_agent_repository_record(
                    repo_data, current_user, db, imported=False
                )
            from app.api.v2.repositories import (
                RepositoryV2Create,
                create_repository as create_repository_v2,
            )

            v2_payload = RepositoryV2Create(**repo_data.model_dump(exclude_none=True))
            return await create_repository_v2(v2_payload, current_user, db)

        if executor_type == "agent":
            return await _create_agent_repository_record(
                repo_data, current_user, db, imported=False
            )

        valid_encryption_modes = {
            "repokey",
            "keyfile",
            "repokey-blake2",
            "keyfile-blake2",
            "none",
        }
        if repo_data.encryption not in valid_encryption_modes:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.repo.invalidEncryptionMode"},
            )

        # Validate passphrase for encrypted repositories
        if repo_data.encryption in [
            "repokey",
            "keyfile",
            "repokey-blake2",
            "keyfile-blake2",
        ]:
            if not repo_data.passphrase or repo_data.passphrase.strip() == "":
                raise HTTPException(
                    status_code=400,
                    detail={
                        "key": "backend.errors.repo.encryptedPassphraseRequired",
                        "params": {"mode": repo_data.encryption},
                    },
                )

        # Validate connection_id and path
        repo_path = repo_data.path.strip()

        # Initialize SSH connection details
        ssh_host = None
        ssh_username = None
        ssh_port = None
        ssh_key_id_for_init = None

        if not repo_data.connection_id:
            # Local repository
            # Ensure path is absolute
            # But first check if path looks like an SSH URL
            if repo_path.startswith("ssh://"):
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.repo.sshUrlWithoutConnectionId"},
                )

            if not os.path.isabs(repo_path):
                # If relative path, make it relative to data directory
                repo_path = os.path.join(settings.data_dir, repo_path)

            # Validate that the path is a valid absolute path
            repo_path = os.path.abspath(repo_path)
        else:
            # Remote repository - get connection details
            connection_details = get_connection_details(repo_data.connection_id, db)
            ssh_host = connection_details["host"]
            ssh_username = connection_details["username"]
            ssh_port = connection_details["port"]
            ssh_key_id_for_init = connection_details["ssh_key_id"]

            # Note: We don't check if borg is installed on the remote machine.
            # Some SSH hosts (like Hetzner Storagebox) use restricted shells that block
            # diagnostic commands like "which borg", but Borg commands still work.
            # If Borg is truly not installed, the borg init command will fail with a clear error.
            logger.info(
                "Skipping remote borg check for SSH repository",
                host=ssh_host,
                username=ssh_username,
            )

            # Build SSH repository path
            # If path already starts with ssh://, extract just the remote path
            if repo_path.startswith("ssh://"):
                # Parse the SSH URL to extract the path component
                import re

                match = re.match(r"ssh://[^/]+(/.*)", repo_path)
                if match:
                    repo_path = match.group(1)
                else:
                    # Fallback: strip ssh:// and extract path after host
                    repo_path = (
                        repo_path.split("/", 3)[-1] if "/" in repo_path else repo_path
                    )

            # Apply SSH path prefix if configured (e.g., /volume1 for Synology)
            # The prefix is prepended ONLY for SSH commands, not for SFTP browsing
            ssh_path_prefix = connection_details.get("ssh_path_prefix")
            if ssh_path_prefix:
                repo_path_for_ssh = apply_ssh_command_prefix(repo_path, ssh_path_prefix)
                logger.info(
                    "Applying SSH path prefix",
                    original_path=repo_path,
                    prefix=ssh_path_prefix,
                    final_path=repo_path_for_ssh,
                )
                repo_path = repo_path_for_ssh

            repo_path = (
                f"ssh://{ssh_username}@{ssh_host}:{ssh_port}/{repo_path.lstrip('/')}"
            )

        # Check if repository name already exists
        existing_repo = (
            db.query(Repository).filter(Repository.name == repo_data.name).first()
        )
        if existing_repo:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.repo.repositoryNameExists"},
            )

        # Check if repository path already exists
        existing_path = (
            db.query(Repository).filter(Repository.path == repo_path).first()
        )
        if existing_path:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.repo.repositoryPathExists"},
            )

        cloud_mirror_remote = _validate_cloud_mirror_payload(repo_data, db)
        await _preflight_cloud_mirror_path(repo_data, cloud_mirror_remote)

        # Create repository directory if local (but not if using /local mount)
        if not repo_data.connection_id:
            # Skip directory creation if path is within /local mount (host filesystem)
            # User must ensure parent directory exists with proper permissions
            if not repo_path.startswith("/local/"):
                # Paths without /local/ prefix are inside the container
                # Try to create the directory, but provide helpful error if permission denied
                try:
                    os.makedirs(repo_path, exist_ok=True)
                except PermissionError as e:
                    logger.error(
                        "Permission denied creating repository directory",
                        path=repo_path,
                        error=str(e),
                    )
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "key": "backend.errors.repo.permissionDeniedCreateDirectory",
                            "params": {"path": repo_path},
                        },
                    )
            else:
                # For /local/ paths, we need to ensure the parent directory exists
                # Let's try to create the full path up to the repository directory
                parent_dir = os.path.dirname(repo_path)
                logger.info(
                    "Checking /local mount path",
                    repo_path=repo_path,
                    parent_dir=parent_dir,
                    parent_exists=os.path.exists(parent_dir),
                )

                # Try to create parent directories if they don't exist
                try:
                    os.makedirs(parent_dir, exist_ok=True)
                    logger.info("Created parent directories", parent_dir=parent_dir)
                except PermissionError as e:
                    logger.error(
                        "Permission denied creating parent directories",
                        parent_dir=parent_dir,
                        error=str(e),
                    )
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "key": "backend.errors.repo.permissionDeniedCreateParentDirectory",
                            "params": {"path": parent_dir},
                        },
                    )
                except Exception as e:
                    logger.error(
                        "Failed to create parent directories",
                        parent_dir=parent_dir,
                        error=str(e),
                    )
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "key": "backend.errors.repo.failedToCreateParentDirectory"
                        },
                    )

                # Verify parent directory is writable
                if not os.access(parent_dir, os.W_OK):
                    logger.error(
                        "Parent directory is not writable", parent_dir=parent_dir
                    )
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "key": "backend.errors.repo.parentDirectoryNotWritable",
                            "params": {"path": parent_dir},
                        },
                    )

        # Initialize Borg repository
        init_result = await initialize_borg_repository(
            repo_path,
            repo_data.encryption,
            repo_data.passphrase,
            ssh_key_id_for_init,
            repo_data.remote_path,
        )

        if not init_result["success"]:
            raise HTTPException(
                status_code=500,
                detail=_repository_init_failure_detail(init_result),
            )

        (
            source_locations,
            source_connection_id,
            source_directories,
        ) = _normalize_repository_source_payload(
            source_locations=repo_data.source_locations,
            source_connection_id=repo_data.source_connection_id,
            source_directories=repo_data.source_directories,
        )
        source_directories_json = (
            json.dumps(source_directories) if source_directories else None
        )
        source_locations_json = (
            json.dumps(source_locations) if source_locations else None
        )

        # Serialize exclude patterns as JSON
        exclude_patterns_json = None
        if repo_data.exclude_patterns:
            exclude_patterns_json = json.dumps(repo_data.exclude_patterns)

        # Create repository record
        repository = Repository(
            name=repo_data.name,
            path=repo_path,
            encryption=repo_data.encryption,
            compression=repo_data.compression,
            passphrase=repo_data.passphrase,  # Store passphrase for backups
            source_directories=source_directories_json,
            exclude_patterns=exclude_patterns_json,
            connection_id=repo_data.connection_id,
            remote_path=repo_data.remote_path,
            pre_backup_script=repo_data.pre_backup_script,
            post_backup_script=repo_data.post_backup_script,
            hook_timeout=repo_data.hook_timeout,
            pre_hook_timeout=repo_data.pre_hook_timeout,
            post_hook_timeout=repo_data.post_hook_timeout,
            continue_on_hook_failure=repo_data.continue_on_hook_failure,
            skip_on_hook_failure=repo_data.skip_on_hook_failure,
            mode=repo_data.mode,
            bypass_lock=repo_data.bypass_lock,
            custom_flags=repo_data.custom_flags,
            upload_ratelimit_kib=repo_data.upload_ratelimit_kib,
            source_ssh_connection_id=source_connection_id,
            source_locations=source_locations_json,
            execution_target=legacy_execution_target(
                executor_type="server",
                repository_location="ssh" if repo_data.connection_id else "local",
            ),
            executor_type="server",
            agent_machine_id=None,
        )

        db.add(repository)
        db.commit()
        db.refresh(repository)

        if repo_data.encryption in ["keyfile", "keyfile-blake2"]:
            repository.has_keyfile = True
            db.commit()

        if cloud_mirror_remote:
            storage = rclone_repository_service.build_mirror_storage(
                repository_id=repository.id,
                source_path=repository.path,
                source_backend=_mirror_source_backend_for_repository(repository),
                remote_id=cloud_mirror_remote.id,
                remote_path=repo_data.rclone_remote_path or "",
                sync_policy=repo_data.rclone_sync_policy,
                extra_flags=repo_data.rclone_extra_flags,
                sync_cron_expression=repo_data.rclone_sync_cron_expression,
                sync_timezone=repo_data.rclone_sync_timezone,
            )
            db.add(storage)
            db.commit()
            if repo_data.rclone_sync_policy == "after_success":
                await rclone_repository_service.sync_repository(db, repository)

        # Determine response message
        already_existed = init_result.get("already_existed", False)
        if already_existed:
            message = "backend.success.repo.repositoryAlreadyExists"
            logger.info(
                "Existing repository added",
                name=repo_data.name,
                path=repo_path,
                user=current_user.username,
            )
        else:
            message = "backend.success.repo.repositoryCreated"
            logger.info(
                "Repository created",
                name=repo_data.name,
                path=repo_path,
                user=current_user.username,
            )

        # Sync repositories with MQTT to publish new repository
        try:
            mqtt_service.sync_state_with_db(db, reason="repository creation")
            logger.info(
                "Synced repositories with MQTT after creation", repo_id=repository.id
            )
        except Exception as e:
            logger.warning(
                "Failed to sync repositories with MQTT after creation",
                repo_id=repository.id,
                error=str(e),
            )

        repository_payload = {
            "id": repository.id,
            "name": repository.name,
            "path": repository.path,
            "encryption": repository.encryption,
            "compression": repository.compression,
            "execution_target": repository.execution_target,
            "executor_type": repository.executor_type,
            "agent_machine_id": repository.agent_machine_id,
            **_agent_machine_summary(repository, db),
            "upload_ratelimit_kib": repository.upload_ratelimit_kib,
        }
        rclone_storage = _serialize_rclone_storage(repository, db)
        if rclone_storage:
            repository_payload["storage_backend"] = _primary_storage_backend(repository)
            repository_payload["rclone_storage"] = rclone_storage
            if repository.repository_type == "rclone":
                repository_payload["repository_type"] = "rclone"
        elif _is_direct_rclone_repository(repository):
            repository_payload["storage_backend"] = DIRECT_RCLONE_STORAGE_BACKEND
            repository_payload["repository_type"] = "rclone"

        return {
            "success": True,
            "message": message,
            "already_existed": already_existed,
            "repository": repository_payload,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create repository", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToCreateRepository"},
        )


@router.post("/import")
async def import_repository(
    repo_data: RepositoryImport,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import an existing Borg repository"""
    try:
        executor_type = _normalize_repository_executor(repo_data)
        _validate_upload_ratelimit_kib(repo_data.upload_ratelimit_kib)
        if _payload_uses_rclone(repo_data):
            _require_rclone_feature(db)
        if executor_type == "agent":
            _require_managed_agents_feature(db)
        if _is_direct_rclone_payload(repo_data):
            return await _import_direct_rclone_repository_record(
                repo_data, current_user, db
            )
        _reject_unsupported_rclone_borg2(repo_data)
        if _is_rclone_payload(repo_data):
            return await _import_rclone_repository_record(repo_data, current_user, db)
        if _uses_borg2_payload(repo_data):
            _require_borg2_feature(db)
            if executor_type == "agent":
                return await _create_agent_repository_record(
                    repo_data, current_user, db, imported=True
                )
            from app.api.v2.repositories import (
                RepositoryV2Import,
                import_repository as import_repository_v2,
            )

            v2_payload = RepositoryV2Import(**repo_data.model_dump(exclude_none=True))
            return await import_repository_v2(v2_payload, current_user, db)

        if executor_type == "agent":
            return await _create_agent_repository_record(
                repo_data, current_user, db, imported=True
            )

        # Validate connection_id and path
        repo_path = repo_data.path.strip()

        # Initialize SSH connection details
        ssh_host = None
        ssh_username = None
        ssh_port = None
        ssh_key_id_for_verify = None

        if not repo_data.connection_id:
            # Local repository
            # Ensure path is absolute
            # But first check if path looks like an SSH URL
            if repo_path.startswith("ssh://"):
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.repo.sshUrlWithoutConnectionId"},
                )

            if not os.path.isabs(repo_path):
                # If relative path, make it relative to data directory
                repo_path = os.path.join(settings.data_dir, repo_path)

            # Validate that the path is a valid absolute path
            repo_path = os.path.abspath(repo_path)

            # Check if repository directory exists
            if not os.path.exists(repo_path):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "key": "backend.errors.repo.repositoryDirNotExist",
                        "params": {"path": repo_path},
                    },
                )

            # Check if it's a valid Borg repository by looking for Borg's config file.
            # A normal data directory can also contain a "config" subdirectory, which
            # Borg will later reject with IsADirectoryError during backup.
            config_path = os.path.join(repo_path, "config")
            if not os.path.isfile(config_path):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "key": "backend.errors.repo.notValidBorgRepository",
                        "params": {"path": repo_path},
                    },
                )

        else:
            # Remote repository - get connection details
            connection_details = get_connection_details(repo_data.connection_id, db)
            ssh_host = connection_details["host"]
            ssh_username = connection_details["username"]
            ssh_port = connection_details["port"]
            ssh_key_id_for_verify = connection_details["ssh_key_id"]

            # Note: We don't check if borg is installed on the remote machine.
            # Some SSH hosts (like Hetzner Storagebox) use restricted shells that block
            # diagnostic commands like "which borg", but Borg commands still work.
            # If Borg is truly not installed, the borg info command will fail with a clear error.
            logger.info(
                "Skipping remote borg check for SSH repository",
                host=ssh_host,
                username=ssh_username,
            )

            # Build SSH repository path
            if repo_path.startswith("ssh://"):
                # Parse the SSH URL to extract the path component
                import re

                match = re.match(r"ssh://[^/]+(/.*)", repo_path)
                if match:
                    repo_path = match.group(1)
                else:
                    repo_path = (
                        repo_path.split("/", 3)[-1] if "/" in repo_path else repo_path
                    )

            # Apply SSH path prefix if configured (e.g., /volume1 for Synology)
            ssh_path_prefix = connection_details.get("ssh_path_prefix")
            if ssh_path_prefix:
                repo_path_for_ssh = apply_ssh_command_prefix(repo_path, ssh_path_prefix)
                logger.info(
                    "Applying SSH path prefix",
                    original_path=repo_path,
                    prefix=ssh_path_prefix,
                    final_path=repo_path_for_ssh,
                )
                repo_path = repo_path_for_ssh

            repo_path = (
                f"ssh://{ssh_username}@{ssh_host}:{ssh_port}/{repo_path.lstrip('/')}"
            )

        # Check if repository name already exists
        existing_repo = (
            db.query(Repository).filter(Repository.name == repo_data.name).first()
        )
        if existing_repo:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.repo.repositoryNameExists"},
            )

        # Check if repository path already exists in database
        existing_path = (
            db.query(Repository).filter(Repository.path == repo_path).first()
        )
        if existing_path:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.repo.repositoryPathExists"},
            )

        cloud_mirror_remote = _validate_cloud_mirror_payload(repo_data, db)
        await _preflight_cloud_mirror_path(repo_data, cloud_mirror_remote)

        # Write keyfile to disk before verification so borg can find it
        keyfile_path = None
        if repo_data.keyfile_content:
            keyfile_dir = os.path.expanduser("~/.config/borg/keys")
            os.makedirs(keyfile_dir, exist_ok=True)
            keyfile_name = _borg_keyfile_name(repo_path)
            keyfile_path = os.path.join(keyfile_dir, keyfile_name)
            with open(keyfile_path, "w") as f:
                f.write(repo_data.keyfile_content)
            os.chmod(keyfile_path, 0o600)
            logger.info("Wrote keyfile before verification", keyfile_path=keyfile_path)

        # Verify repository is accessible by running borg info
        logger.info("Verifying repository accessibility", path=repo_path)
        verify_result = await verify_existing_repository(
            repo_path,
            repo_data.passphrase,
            ssh_key_id_for_verify,
            repo_data.remote_path,
            repo_data.bypass_lock,
        )

        if not verify_result["success"]:
            # Clean up keyfile we wrote — verification failed so don't leave it on disk
            if keyfile_path and os.path.exists(keyfile_path):
                os.unlink(keyfile_path)
                logger.info(
                    "Removed keyfile after failed verification",
                    keyfile_path=keyfile_path,
                )

            error_msg = verify_result.get("error", "Unknown error")

            # Provide helpful error messages
            if "passphrase" in error_msg.lower() or "encrypted" in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.repo.encryptedPassphraseIncorrect"},
                )
            elif "not a valid repository" in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail={
                        "key": "backend.errors.repo.notValidBorgRepository",
                        "params": {"path": repo_path},
                    },
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail={"key": "backend.errors.repo.failedToVerifyRepository"},
                )

        # Extract repository info from verification
        repo_info = verify_result.get("info", {})
        encryption_mode = repo_info.get("encryption", {}).get("mode", "unknown")

        (
            source_locations,
            source_connection_id,
            source_directories,
        ) = _normalize_repository_source_payload(
            source_locations=repo_data.source_locations,
            source_connection_id=repo_data.source_connection_id,
            source_directories=repo_data.source_directories,
        )
        source_directories_json = (
            json.dumps(source_directories) if source_directories else None
        )
        source_locations_json = (
            json.dumps(source_locations) if source_locations else None
        )

        # Serialize exclude patterns as JSON
        exclude_patterns_json = None
        if repo_data.exclude_patterns:
            exclude_patterns_json = json.dumps(repo_data.exclude_patterns)

        # Create repository record
        # Note: archive_count will be updated after creation via borg list
        repository = Repository(
            name=repo_data.name,
            path=repo_path,
            encryption=encryption_mode,
            compression=repo_data.compression,
            passphrase=repo_data.passphrase,
            source_directories=source_directories_json,
            exclude_patterns=exclude_patterns_json,
            connection_id=repo_data.connection_id,
            remote_path=repo_data.remote_path,
            archive_count=0,  # Will be updated below
            pre_backup_script=repo_data.pre_backup_script,
            post_backup_script=repo_data.post_backup_script,
            hook_timeout=repo_data.hook_timeout,
            pre_hook_timeout=repo_data.pre_hook_timeout,
            post_hook_timeout=repo_data.post_hook_timeout,
            continue_on_hook_failure=repo_data.continue_on_hook_failure,
            skip_on_hook_failure=repo_data.skip_on_hook_failure,
            mode=repo_data.mode,
            bypass_lock=repo_data.bypass_lock,
            custom_flags=repo_data.custom_flags,
            upload_ratelimit_kib=repo_data.upload_ratelimit_kib,
            source_ssh_connection_id=source_connection_id,
            source_locations=source_locations_json,
            execution_target=legacy_execution_target(
                executor_type="server",
                repository_location="ssh" if repo_data.connection_id else "local",
            ),
            executor_type="server",
            agent_machine_id=None,
        )

        db.add(repository)
        db.commit()
        db.refresh(repository)

        if keyfile_path:
            repository.has_keyfile = True
            db.commit()

        # Update archive count by listing archives (non-blocking - don't fail import)
        try:
            from app.core.borg_router import BorgRouter

            await BorgRouter(repository).update_stats(db)
        except Exception as e:
            # Log but don't fail the import - stats can be updated later
            logger.warning(
                "Failed to update repository stats after import",
                repository=repository.name,
                error=str(e),
            )

        if cloud_mirror_remote:
            storage = rclone_repository_service.build_mirror_storage(
                repository_id=repository.id,
                source_path=repository.path,
                source_backend=_mirror_source_backend_for_repository(repository),
                remote_id=cloud_mirror_remote.id,
                remote_path=repo_data.rclone_remote_path or "",
                sync_policy=repo_data.rclone_sync_policy,
                extra_flags=repo_data.rclone_extra_flags,
                sync_cron_expression=repo_data.rclone_sync_cron_expression,
                sync_timezone=repo_data.rclone_sync_timezone,
            )
            db.add(storage)
            db.commit()
            if repo_data.rclone_sync_policy == "after_success":
                await rclone_repository_service.sync_repository(db, repository)

        logger.info(
            "Repository imported successfully",
            name=repo_data.name,
            path=repo_path,
            user=current_user.username,
        )

        # Sync repositories with MQTT to publish new repository
        try:
            mqtt_service.sync_state_with_db(db, reason="repository import")
            logger.info(
                "Synced repositories with MQTT after import", repo_id=repository.id
            )
        except Exception as e:
            logger.warning(
                "Failed to sync repositories with MQTT after import",
                repo_id=repository.id,
                error=str(e),
            )

        repository_payload = {
            "id": repository.id,
            "name": repository.name,
            "path": repository.path,
            "encryption": repository.encryption,
            "compression": repository.compression,
            "archive_count": repository.archive_count,
            "execution_target": repository.execution_target,
            "executor_type": repository.executor_type,
            "agent_machine_id": repository.agent_machine_id,
            **_agent_machine_summary(repository, db),
            "upload_ratelimit_kib": repository.upload_ratelimit_kib,
        }
        rclone_storage = _serialize_rclone_storage(repository, db)
        if rclone_storage:
            repository_payload["storage_backend"] = _primary_storage_backend(repository)
            repository_payload["rclone_storage"] = rclone_storage
            if repository.repository_type == "rclone":
                repository_payload["repository_type"] = "rclone"
        elif _is_direct_rclone_repository(repository):
            repository_payload["storage_backend"] = DIRECT_RCLONE_STORAGE_BACKEND
            repository_payload["repository_type"] = "rclone"

        return {
            "success": True,
            "message": "backend.success.repo.repositoryImported",
            "repository": repository_payload,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to import repository", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToImportRepository"},
        )


@router.get("/{repo_id}/rclone/status")
async def get_repository_rclone_status(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_rclone_feature(db)
    repository = _load_repository_with_access(repo_id, current_user, db, "viewer")
    try:
        return _serialize_rclone_storage(repository, db) or {}
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.rclone.invalidStorage", "message": str(exc)},
        ) from exc


@router.post("/{repo_id}/rclone/sync")
async def sync_repository_rclone(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_rclone_feature(db)
    repository = _load_repository_with_access(repo_id, current_user, db, "operator")

    async def _operation():
        try:
            return await rclone_repository_service.sync_repository(db, repository)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.rclone.invalidStorage",
                    "message": str(exc),
                },
            ) from exc

    return await run_serialized_repository_command(repo_id, _operation, scope="rclone")


@router.post("/{repo_id}/rclone/hydrate")
async def hydrate_repository_rclone(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_rclone_feature(db)
    repository = _load_repository_with_access(repo_id, current_user, db, "operator")

    async def _operation():
        try:
            return await rclone_repository_service.hydrate_repository(db, repository)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.rclone.invalidStorage",
                    "message": str(exc),
                },
            ) from exc

    return await run_serialized_repository_command(repo_id, _operation, scope="rclone")


@router.post("/{repo_id}/keyfile")
async def upload_keyfile(
    repo_id: int, keyfile: UploadFile = File(...), db: Session = Depends(get_db)
):
    """
    Upload a keyfile for a repository that uses keyfile or keyfile-blake2 encryption.

    This endpoint allows uploading keyfiles for existing repositories that were created
    elsewhere and use keyfile-based encryption modes.
    """
    try:
        # Get repository
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.repositoryNotFound"},
            )

        # Verify repository uses keyfile encryption
        if repository.encryption not in ["keyfile", "keyfile-blake2"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.repo.encryptionKeyfileNotRequired",
                    "params": {"mode": repository.encryption},
                },
            )

        # Validate keyfile content
        content = await keyfile.read()
        if not content:
            raise HTTPException(
                status_code=400, detail={"key": "backend.errors.repo.keyfileEmpty"}
            )

        keyfile_name = _borg_keyfile_name(repository.path)

        # Store keyfile in ~/.config/borg/keys/ — the standard Borg keyfile location.
        # In Docker, entrypoint.sh symlinks ~/.config/borg/keys -> /data/borg_keys so files
        # go to the persistent volume automatically.  Running natively this resolves to the
        # real ~/.config/borg/keys/ directory that borg already scans.
        keyfile_dir = os.path.expanduser("~/.config/borg/keys")
        os.makedirs(keyfile_dir, exist_ok=True)

        keyfile_path = os.path.join(keyfile_dir, keyfile_name)

        # Write keyfile
        with open(keyfile_path, "wb") as f:
            f.write(content)

        # Set proper permissions (600 - owner read/write only)
        os.chmod(keyfile_path, 0o600)

        # Update repository to indicate it has a keyfile
        repository.has_keyfile = True
        db.commit()

        logger.info(
            "Keyfile uploaded successfully",
            repo_id=repo_id,
            repo_name=repository.name,
            keyfile_path=keyfile_path,
        )

        return {
            "success": True,
            "message": "backend.success.repo.keyfileUploaded",
            "keyfile_name": keyfile_name,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to upload keyfile", repo_id=repo_id, error=str(e))
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToUploadKeyfile"}
        )


@router.get("/{repo_id}/keyfile")
async def download_keyfile(repo_id: int, db: Session = Depends(get_db)):
    """Export and download the keyfile for a repository that uses keyfile encryption.

    Uses 'borg key export' so it works regardless of what the keyfile is named on disk
    (Borg-created repos use a hash-based filename; imported repos use our path-based convention).
    """
    repository = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repository:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.repo.repositoryNotFound"}
        )

    if not repository.has_keyfile:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.repo.repoHasNoKeyfile"}
        )

    try:
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".key") as tmp:
            tmp_path = tmp.name

        try:
            result = await BorgRouter(repository).export_keyfile(tmp_path)
            if not result["success"]:
                raise HTTPException(
                    status_code=500,
                    detail={"key": "backend.errors.repo.failedToExportKeyfile"},
                )

            with open(tmp_path, "rb") as f:
                content = f.read()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        download_name = _borg_keyfile_name(repository.path)
        return Response(
            content=content,
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to download keyfile", repo_id=repo_id, error=str(e))
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedExportKeyfile"}
        )


@router.get("/{repo_id}")
async def get_repository(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get repository details"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.repositoryNotFound"},
            )
        _require_repository_access(db, current_user, repository, "viewer")

        # Check system-wide bypass_lock_on_list setting
        from app.database.models import SystemSettings

        system_settings = db.query(SystemSettings).first()
        use_bypass_lock = repository.bypass_lock or (
            system_settings and system_settings.bypass_lock_on_list
        )

        # Get repository statistics
        stats = await get_repository_stats(repository, db, bypass_lock=use_bypass_lock)

        repository_payload = {
            "id": repository.id,
            "name": repository.name,
            "path": repository.path,
            "encryption": repository.encryption,
            "compression": repository.compression,
            "execution_target": repository.execution_target or "local",
            "executor_type": repository_executor_type(repository),
            "agent_machine_id": repository.agent_machine_id,
            **_agent_machine_summary(repository, db),
            "last_backup": format_datetime(repository.last_backup),
            "total_size": repository.total_size,
            "archive_count": repository.archive_count,
            "created_at": format_datetime(repository.created_at),
            "updated_at": format_datetime(repository.updated_at),
            "has_keyfile": repository.has_keyfile or False,
            "source_ssh_connection_id": repository.source_ssh_connection_id,
            "source_directories": _decode_json_list_field(
                repository.source_directories
            ),
            "source_locations": _repository_source_locations(repository),
            "upload_ratelimit_kib": repository.upload_ratelimit_kib,
            "stats": stats,
        }
        rclone_storage = _serialize_rclone_storage(repository, db)
        if rclone_storage:
            repository_payload["storage_backend"] = _primary_storage_backend(repository)
            repository_payload["rclone_storage"] = rclone_storage
            if repository.repository_type == "rclone":
                repository_payload["repository_type"] = "rclone"
        elif _is_direct_rclone_repository(repository):
            repository_payload["storage_backend"] = DIRECT_RCLONE_STORAGE_BACKEND
            repository_payload["repository_type"] = "rclone"

        return {
            "success": True,
            "repository": repository_payload,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get repository", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToRetrieveRepository"},
        )


@router.put("/{repo_id}")
async def update_repository(
    repo_id: int,
    repo_data: RepositoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update repository"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.repositoryNotFound"},
            )
        _require_repository_access(db, current_user, repository, "operator")

        update_data = repo_data.model_dump(exclude_unset=True)
        if "upload_ratelimit_kib" in update_data:
            _validate_upload_ratelimit_kib(repo_data.upload_ratelimit_kib)

        # Update fields
        if repo_data.name is not None:
            # Check if name already exists
            existing_repo = (
                db.query(Repository)
                .filter(Repository.name == repo_data.name, Repository.id != repo_id)
                .first()
            )
            if existing_repo:
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.repo.repositoryNameExists"},
                )
            repository.name = repo_data.name

        # Store raw path first (will be reconstructed for SSH below)
        raw_path = None
        target_executor_type = (
            normalize_executor_type(
                repo_data.executor_type if "executor_type" in update_data else None,
                execution_target=repo_data.execution_target
                if repo_data.execution_target is not None
                else repository.execution_target,
            )
            if (
                "executor_type" in update_data or repo_data.execution_target is not None
            )
            else repository_executor_type(repository)
        )

        target_connection_id = (
            repo_data.connection_id
            if "connection_id" in update_data
            else repository.connection_id
        )
        existing_rclone_storage = (
            db.query(RepositoryStorage)
            .filter(RepositoryStorage.repository_id == repository.id)
            .first()
        )
        existing_direct_rclone_repository = _is_direct_rclone_repository(
            repository, existing_rclone_storage
        )
        existing_cached_rclone_repository = bool(
            existing_rclone_storage
            and existing_rclone_storage.backend == "rclone"
            and repository.repository_type == "rclone"
            and not existing_direct_rclone_repository
        )
        rclone_update_fields = {
            "storage_backend",
            "rclone_remote_id",
            "rclone_remote_path",
            "rclone_sync_policy",
            "rclone_sync_cron_expression",
            "rclone_sync_timezone",
            "rclone_extra_flags",
            "rclone_cache_path",
            "cloud_mirror_enabled",
            "rclone_remote_path_verified",
        }
        if existing_cached_rclone_repository:
            _strip_cached_rclone_noop_update_fields(repo_data, update_data)
        elif (
            not existing_rclone_storage
            and not existing_direct_rclone_repository
            and repo_data.cloud_mirror_enabled is not True
        ):
            _strip_disabled_rclone_noop_update_fields(update_data)
        requested_rclone_updates = rclone_update_fields.intersection(update_data)
        if (
            _is_direct_rclone_payload(repo_data)
            and not existing_direct_rclone_repository
        ):
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.rclone.updateUnsupported"},
            )
        if existing_direct_rclone_repository:
            _validate_direct_rclone_update(repo_data, update_data)
            _strip_direct_rclone_noop_update_fields(update_data)
            requested_rclone_updates = set()
        rclone_gate_updates = _rclone_feature_gate_updates(
            repo_data, update_data, requested_rclone_updates
        )
        if rclone_gate_updates or (
            existing_direct_rclone_repository and bool(update_data)
        ):
            _require_rclone_feature(db)
        if target_executor_type == "agent":
            _require_managed_agents_feature(db)
        sync_cloud_mirror_after_update = False
        if requested_rclone_updates:
            storage = existing_rclone_storage
            is_direct_rclone_repository = repository.repository_type == "rclone"
            if "rclone_cache_path" in update_data:
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.rclone.cachePathServerOwned"},
                )

            if (
                "storage_backend" in update_data
                and repo_data.storage_backend == "rclone"
                and not is_direct_rclone_repository
            ):
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.rclone.updateUnsupported"},
                )

            if (
                repo_data.cloud_mirror_enabled is False
                and storage
                and storage.backend == "rclone"
                and not is_direct_rclone_repository
            ):
                db.delete(storage)
                existing_rclone_storage = None
                storage = None
                _strip_disabled_rclone_noop_update_fields(update_data)

            should_enable_or_update_mirror = not is_direct_rclone_repository and (
                repo_data.cloud_mirror_enabled is True
                or (
                    bool(storage)
                    and storage.backend == "rclone"
                    and repo_data.cloud_mirror_enabled is not False
                )
            )

            should_update_direct_rclone = (
                bool(storage)
                and storage.backend == "rclone"
                and is_direct_rclone_repository
            )

            if not should_enable_or_update_mirror and not should_update_direct_rclone:
                has_meaningful_rclone_values = any(
                    update_data.get(key)
                    for key in (
                        "rclone_remote_id",
                        "rclone_remote_path",
                        "rclone_sync_policy",
                        "rclone_sync_cron_expression",
                        "rclone_sync_timezone",
                        "rclone_extra_flags",
                    )
                )
                if (
                    has_meaningful_rclone_values
                    or repo_data.storage_backend == "rclone"
                ):
                    raise HTTPException(
                        status_code=400,
                        detail={"key": "backend.errors.rclone.updateUnsupported"},
                    )

            if should_enable_or_update_mirror:
                if target_executor_type == "agent":
                    target_agent_id = (
                        repo_data.agent_machine_id
                        if "agent_machine_id" in update_data
                        else repository.agent_machine_id
                    )
                    _require_agent_rclone_sync_capability(target_agent_id, db)
                elif (
                    _mirror_source_backend_for_repository(repository) == "ssh"
                    and not target_connection_id
                ):
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "key": "backend.errors.rclone.mirrorUnsupportedPrimary"
                        },
                    )

            if should_enable_or_update_mirror and storage is None:
                if not repo_data.rclone_remote_id:
                    raise HTTPException(
                        status_code=400,
                        detail={"key": "backend.errors.rclone.remoteRequired"},
                    )
                if not repo_data.rclone_remote_path:
                    raise HTTPException(
                        status_code=400,
                        detail={"key": "backend.errors.rclone.remotePathRequired"},
                    )
                effective_sync_policy = repo_data.rclone_sync_policy or "after_success"
                if effective_sync_policy not in VALID_SYNC_POLICIES:
                    raise HTTPException(
                        status_code=400,
                        detail={"key": "backend.errors.rclone.invalidSyncPolicy"},
                    )
                _validate_rclone_schedule_payload(repo_data)
                remote = (
                    db.query(RcloneRemote)
                    .filter(RcloneRemote.id == repo_data.rclone_remote_id)
                    .first()
                )
                if not remote:
                    raise HTTPException(
                        status_code=404,
                        detail={"key": "backend.errors.rclone.remoteNotFound"},
                    )
                try:
                    await rclone_repository_service.preflight_remote_path(
                        remote,
                        repo_data.rclone_remote_path,
                        verified_non_empty=bool(repo_data.rclone_remote_path_verified),
                    )
                    storage = rclone_repository_service.build_mirror_storage(
                        repository_id=repository.id,
                        source_path=repository.path,
                        source_backend=_mirror_source_backend_for_repository(
                            repository
                        ),
                        remote_id=remote.id,
                        remote_path=repo_data.rclone_remote_path,
                        sync_policy=effective_sync_policy,
                        extra_flags=repo_data.rclone_extra_flags,
                        sync_cron_expression=repo_data.rclone_sync_cron_expression,
                        sync_timezone=repo_data.rclone_sync_timezone,
                    )
                except ValueError as exc:
                    message = str(exc)
                    key = (
                        "backend.errors.rclone.remotePathNotVerified"
                        if "not empty" in message
                        else "backend.errors.rclone.remotePathPreflightFailed"
                    )
                    raise HTTPException(
                        status_code=400,
                        detail={"key": key, "message": message},
                    ) from exc
                db.add(storage)
                existing_rclone_storage = storage
                sync_cloud_mirror_after_update = storage.sync_policy == "after_success"

            if should_enable_or_update_mirror and storage is not None:
                rclone_remote_changed = "rclone_remote_id" in update_data
                rclone_remote_path_changed = "rclone_remote_path" in update_data
                if "rclone_remote_id" in update_data:
                    if not repo_data.rclone_remote_id:
                        raise HTTPException(
                            status_code=400,
                            detail={"key": "backend.errors.rclone.remoteRequired"},
                        )
                    remote = (
                        db.query(RcloneRemote)
                        .filter(RcloneRemote.id == repo_data.rclone_remote_id)
                        .first()
                    )
                    if not remote:
                        raise HTTPException(
                            status_code=404,
                            detail={"key": "backend.errors.rclone.remoteNotFound"},
                        )
                else:
                    remote = (
                        db.query(RcloneRemote)
                        .filter(RcloneRemote.id == storage.rclone_remote_id)
                        .first()
                    )
                    if not remote:
                        raise HTTPException(
                            status_code=404,
                            detail={"key": "backend.errors.rclone.remoteNotFound"},
                        )
                if rclone_remote_changed or rclone_remote_path_changed:
                    candidate_remote_path = (
                        repo_data.rclone_remote_path
                        if rclone_remote_path_changed
                        else storage.rclone_remote_path
                    )
                    if not candidate_remote_path:
                        raise HTTPException(
                            status_code=400,
                            detail={"key": "backend.errors.rclone.remotePathRequired"},
                        )
                    try:
                        await rclone_repository_service.preflight_remote_path(
                            remote,
                            candidate_remote_path,
                            verified_non_empty=bool(
                                repo_data.rclone_remote_path_verified
                            ),
                        )
                        if rclone_remote_changed:
                            storage.rclone_remote_id = remote.id
                        if rclone_remote_path_changed:
                            storage.rclone_remote_path = normalize_rclone_relative_path(
                                candidate_remote_path
                            )
                    except ValueError as exc:
                        message = str(exc)
                        key = (
                            "backend.errors.rclone.remotePathNotVerified"
                            if "not empty" in message
                            else "backend.errors.rclone.remotePathPreflightFailed"
                        )
                        raise HTTPException(
                            status_code=400,
                            detail={"key": key, "message": message},
                        ) from exc
                schedule_fields_changed = {
                    "rclone_sync_policy",
                    "rclone_sync_cron_expression",
                    "rclone_sync_timezone",
                }.intersection(update_data)
                if schedule_fields_changed:
                    try:
                        rclone_repository_service.configure_schedule(
                            storage,
                            sync_policy=repo_data.rclone_sync_policy
                            if "rclone_sync_policy" in update_data
                            else storage.sync_policy,
                            sync_cron_expression=repo_data.rclone_sync_cron_expression
                            if "rclone_sync_cron_expression" in update_data
                            else None,
                            sync_timezone=repo_data.rclone_sync_timezone
                            if "rclone_sync_timezone" in update_data
                            else None,
                        )
                    except Exception as exc:
                        _raise_rclone_schedule_error(exc)
                if "rclone_extra_flags" in update_data:
                    try:
                        storage.extra_flags = normalize_extra_flags(
                            repo_data.rclone_extra_flags
                        )
                    except ValueError as exc:
                        raise HTTPException(
                            status_code=400,
                            detail={
                                "key": "backend.errors.rclone.invalidPayload",
                                "message": str(exc),
                            },
                        ) from exc
                _apply_mirror_source_strategy(storage, repository)

            if should_update_direct_rclone:
                storage = existing_rclone_storage
                if not storage or storage.backend != "rclone":
                    raise HTTPException(
                        status_code=400,
                        detail={"key": "backend.errors.rclone.updateUnsupported"},
                    )
            if (
                "storage_backend" in update_data
                and repo_data.storage_backend != "rclone"
                and is_direct_rclone_repository
            ):
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.rclone.updateUnsupported"},
                )
            if should_update_direct_rclone and "rclone_remote_id" in update_data:
                if not repo_data.rclone_remote_id:
                    raise HTTPException(
                        status_code=400,
                        detail={"key": "backend.errors.rclone.remoteRequired"},
                    )
                remote = (
                    db.query(RcloneRemote)
                    .filter(RcloneRemote.id == repo_data.rclone_remote_id)
                    .first()
                )
                if not remote:
                    raise HTTPException(
                        status_code=404,
                        detail={"key": "backend.errors.rclone.remoteNotFound"},
                    )
                storage.rclone_remote_id = remote.id
            if should_update_direct_rclone and "rclone_remote_path" in update_data:
                if not repo_data.rclone_remote_path:
                    raise HTTPException(
                        status_code=400,
                        detail={"key": "backend.errors.rclone.remotePathRequired"},
                    )
                try:
                    storage.rclone_remote_path = normalize_rclone_relative_path(
                        repo_data.rclone_remote_path
                    )
                except ValueError as exc:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "key": "backend.errors.rclone.invalidPayload",
                            "message": str(exc),
                        },
                    ) from exc
            if should_update_direct_rclone and {
                "rclone_sync_policy",
                "rclone_sync_cron_expression",
                "rclone_sync_timezone",
            }.intersection(update_data):
                try:
                    rclone_repository_service.configure_schedule(
                        storage,
                        sync_policy=repo_data.rclone_sync_policy
                        if "rclone_sync_policy" in update_data
                        else storage.sync_policy,
                        sync_cron_expression=repo_data.rclone_sync_cron_expression
                        if "rclone_sync_cron_expression" in update_data
                        else None,
                        sync_timezone=repo_data.rclone_sync_timezone
                        if "rclone_sync_timezone" in update_data
                        else None,
                    )
                except Exception as exc:
                    _raise_rclone_schedule_error(exc)
            if should_update_direct_rclone and "rclone_extra_flags" in update_data:
                try:
                    storage.extra_flags = normalize_extra_flags(
                        repo_data.rclone_extra_flags
                    )
                except ValueError as exc:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "key": "backend.errors.rclone.invalidPayload",
                            "message": str(exc),
                        },
                    ) from exc

        if (
            existing_rclone_storage
            and existing_rclone_storage.backend == "rclone"
            and repository.repository_type == "rclone"
            and "path" in update_data
        ):
            update_data.pop("path")

        if "path" in update_data and repo_data.path is not None:
            raw_path = repo_data.path.strip()

        target_path = raw_path if raw_path is not None else repository.path
        if target_executor_type == "agent":
            _reject_agent_repository_ssh_target(
                path=target_path,
                connection_id=target_connection_id,
                execution_target=repo_data.execution_target,
            )

        # Handle connection_id - allow null to clear (switch to local)
        if "connection_id" in update_data:
            repository.connection_id = repo_data.connection_id
            # Clear legacy fields when switching repository type
            if repo_data.connection_id is None:
                # Switching to local - clear SSH-related legacy fields
                repository.repository_type = "local"
                repository.host = None
                repository.port = 22
                repository.username = None
                repository.ssh_key_id = None
            else:
                # Switching to SSH - set repository_type (for backward compatibility with old code)
                repository.repository_type = "ssh"

        # Reconstruct path if connection_id or path changed (similar to create endpoint logic)
        path_changed = False
        old_path = repository.path
        if raw_path is not None or "connection_id" in update_data:
            # Determine the final connection_id (use updated value or existing)
            final_connection_id = (
                repo_data.connection_id
                if "connection_id" in update_data
                else repository.connection_id
            )

            # Use the raw_path if provided, otherwise use existing path
            path_to_use = raw_path if raw_path is not None else repository.path

            if final_connection_id:
                # Remote repository - reconstruct SSH URL
                connection_details = get_connection_details(final_connection_id, db)

                # Extract plain path if it's already in SSH URL format
                if path_to_use.startswith("ssh://"):
                    # Extract path part from SSH URL
                    import re

                    match = re.match(r"ssh://[^/]+(/.*)", path_to_use)
                    if match:
                        path_to_use = match.group(1)
                    else:
                        path_to_use = (
                            path_to_use.split("/", 3)[-1]
                            if "/" in path_to_use
                            else path_to_use
                        )

                # Apply SSH path prefix if configured
                ssh_path_prefix = connection_details.get("ssh_path_prefix")
                if ssh_path_prefix:
                    path_to_use = apply_ssh_command_prefix(path_to_use, ssh_path_prefix)
                    logger.info(
                        "Applying SSH path prefix",
                        original_path=path_to_use,
                        prefix=ssh_path_prefix,
                    )

                # Reconstruct SSH URL
                final_path = f"ssh://{connection_details['username']}@{connection_details['host']}:{connection_details['port']}/{path_to_use.lstrip('/')}"

                # Check if path already exists (for a different repository)
                existing_path = (
                    db.query(Repository)
                    .filter(Repository.path == final_path, Repository.id != repo_id)
                    .first()
                )
                if existing_path:
                    raise HTTPException(
                        status_code=400,
                        detail={"key": "backend.errors.repo.repositoryPathExists"},
                    )

                path_changed = final_path != old_path
                repository.path = final_path
            else:
                # Local repository - use path as-is
                existing_path = (
                    db.query(Repository)
                    .filter(Repository.path == path_to_use, Repository.id != repo_id)
                    .first()
                )
                if existing_path:
                    raise HTTPException(
                        status_code=400,
                        detail={"key": "backend.errors.repo.repositoryPathExists"},
                    )

                path_changed = path_to_use != old_path
                repository.path = path_to_use

            # If path changed, check if new path is a valid borg repository
            # If not, initialize it (like create mode does)
            if path_changed:
                logger.info(
                    "Repository path changed - checking if new path is valid borg repository",
                    repo_id=repo_id,
                    old_path=old_path,
                    new_path=repository.path,
                )

                # Get SSH key ID if using remote connection
                ssh_key_id_for_init = None
                if repository.connection_id:
                    connection_details = get_connection_details(
                        repository.connection_id, db
                    )
                    ssh_key_id_for_init = connection_details["ssh_key_id"]

                try:
                    router = BorgRouter(repository)
                    info_result = await router.verify_repository(
                        ssh_key_id=ssh_key_id_for_init,
                        timeout=get_operation_timeouts(db)["info_timeout"],
                    )

                    if info_result.get("success"):
                        logger.info(
                            "New path is already a valid borg repository - no initialization needed",
                            new_path=repository.path,
                        )
                    else:
                        logger.warning(
                            "New path is not a valid borg repository - initializing",
                            new_path=repository.path,
                            old_path=old_path,
                            borg_version=repository.borg_version or 1,
                        )

                        init_result = await router.initialize_repository(
                            ssh_key_id=ssh_key_id_for_init,
                            init_timeout=get_operation_timeouts(db)["init_timeout"],
                        )

                        if not init_result["success"]:
                            raise HTTPException(
                                status_code=500,
                                detail=_repository_init_failure_detail(init_result),
                            )

                        logger.info(
                            "Successfully initialized borg repository at new path",
                            new_path=repository.path,
                            borg_version=repository.borg_version or 1,
                        )
                except Exception as e:
                    logger.info(
                        "Could not verify borg repository - attempting initialization",
                        new_path=repository.path,
                        error=str(e),
                        borg_version=repository.borg_version or 1,
                    )

                    init_result = await BorgRouter(repository).initialize_repository(
                        ssh_key_id=ssh_key_id_for_init,
                        init_timeout=get_operation_timeouts(db)["init_timeout"],
                    )

                    if not init_result["success"]:
                        raise HTTPException(
                            status_code=500,
                            detail=_repository_init_failure_detail(init_result),
                        )

                    logger.info(
                        "Successfully initialized borg repository at new path after verification failure",
                        new_path=repository.path,
                        borg_version=repository.borg_version or 1,
                    )

        if repo_data.compression is not None:
            repository.compression = repo_data.compression

        source_settings_changed = any(
            key in update_data
            for key in (
                "source_locations",
                "source_directories",
                "source_connection_id",
            )
        )
        if source_settings_changed:
            if "source_locations" in update_data:
                if repo_data.source_locations:
                    source_locations_input = repo_data.source_locations
                    source_directories_input = None
                    source_connection_id_input = None
                elif "source_directories" in update_data and any(
                    str(path).strip() for path in repo_data.source_directories or []
                ):
                    source_locations_input = None
                    source_directories_input = repo_data.source_directories
                    source_connection_id_input = (
                        repo_data.source_connection_id
                        if "source_connection_id" in update_data
                        else repository.source_ssh_connection_id
                    )
                else:
                    source_locations_input = []
                    source_directories_input = None
                    source_connection_id_input = None
            else:
                source_locations_input = None
                source_directories_input = (
                    repo_data.source_directories
                    if "source_directories" in update_data
                    else _decode_json_list_field(repository.source_directories)
                )
                source_connection_id_input = (
                    repo_data.source_connection_id
                    if "source_connection_id" in update_data
                    else repository.source_ssh_connection_id
                )

            (
                source_locations,
                source_connection_id,
                source_directories,
            ) = _normalize_repository_source_payload(
                source_locations=source_locations_input,
                source_connection_id=source_connection_id_input,
                source_directories=source_directories_input,
            )
            repository.source_directories = (
                json.dumps(source_directories) if source_directories else None
            )
            repository.source_ssh_connection_id = source_connection_id
            repository.source_locations = (
                json.dumps(source_locations) if source_locations else None
            )

        if repo_data.exclude_patterns is not None:
            repository.exclude_patterns = (
                json.dumps(repo_data.exclude_patterns)
                if repo_data.exclude_patterns
                else None
            )

        if repo_data.remote_path is not None:
            repository.remote_path = repo_data.remote_path

        if repo_data.pre_backup_script is not None:
            repository.pre_backup_script = repo_data.pre_backup_script

        if repo_data.post_backup_script is not None:
            repository.post_backup_script = repo_data.post_backup_script

        if repo_data.pre_backup_script_parameters is not None:
            repository.pre_backup_script_parameters = (
                repo_data.pre_backup_script_parameters
            )

        if repo_data.post_backup_script_parameters is not None:
            repository.post_backup_script_parameters = (
                repo_data.post_backup_script_parameters
            )

        if repo_data.hook_timeout is not None:
            repository.hook_timeout = repo_data.hook_timeout

        if repo_data.pre_hook_timeout is not None:
            repository.pre_hook_timeout = repo_data.pre_hook_timeout

        if repo_data.post_hook_timeout is not None:
            repository.post_hook_timeout = repo_data.post_hook_timeout

        if repo_data.continue_on_hook_failure is not None:
            repository.continue_on_hook_failure = repo_data.continue_on_hook_failure

        if repo_data.skip_on_hook_failure is not None:
            repository.skip_on_hook_failure = repo_data.skip_on_hook_failure

        if repo_data.mode is not None:
            repository.mode = repo_data.mode
            # If switching to observe mode, log it
            if repo_data.mode == "observe":
                logger.info(
                    "Repository switched to observability-only mode", repo_id=repo_id
                )

        if repo_data.bypass_lock is not None:
            repository.bypass_lock = repo_data.bypass_lock

        if repo_data.custom_flags is not None:
            repository.custom_flags = repo_data.custom_flags

        if "upload_ratelimit_kib" in update_data:
            repository.upload_ratelimit_kib = repo_data.upload_ratelimit_kib

        executor_changed = (
            "executor_type" in update_data or repo_data.execution_target is not None
        )
        if executor_changed:
            if target_executor_type == "agent":
                requested_agent_id = (
                    repo_data.agent_machine_id
                    if "agent_machine_id" in update_data
                    else repository.agent_machine_id
                )
                if _repository_has_cloud_mirror(repository, existing_rclone_storage):
                    agent = _require_agent_rclone_sync_capability(
                        requested_agent_id, db
                    )
                else:
                    agent = _require_queueable_agent(requested_agent_id, db)
                repository.executor_type = "agent"
                repository.execution_target = "agent"
                repository.agent_machine_id = agent.id
            else:
                repository.executor_type = "server"
                repository.execution_target = legacy_execution_target(
                    executor_type="server",
                    repository_location="ssh" if repository.connection_id else "local",
                )
                repository.agent_machine_id = None

        elif (
            "connection_id" in update_data
            and repository_executor_type(repository) == "server"
        ):
            repository.execution_target = legacy_execution_target(
                executor_type="server",
                repository_location="ssh" if repository.connection_id else "local",
            )

        elif "agent_machine_id" in update_data:
            if repository_executor_type(repository) != "agent":
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.repo.invalidExecutionTarget"},
                )
            if _repository_has_cloud_mirror(repository, existing_rclone_storage):
                agent = _require_agent_rclone_sync_capability(
                    repo_data.agent_machine_id, db
                )
            else:
                agent = _require_queueable_agent(repo_data.agent_machine_id, db)
            repository.agent_machine_id = agent.id

        if (
            existing_rclone_storage
            and existing_rclone_storage.backend == "rclone"
            and repository.repository_type != "rclone"
        ):
            _apply_mirror_source_strategy(existing_rclone_storage, repository)

        repository.updated_at = datetime.utcnow()
        db.commit()

        if sync_cloud_mirror_after_update:
            try:
                _queue_initial_cloud_mirror_sync(db, repository)
            except Exception as e:
                db.rollback()
                logger.error(
                    "Failed to queue initial cloud mirror sync after repository update",
                    repo_id=repository.id,
                    repo_name=repository.name,
                    error=str(e),
                )

        logger.info("Repository updated", repo_id=repo_id, user=current_user.username)

        # Publish full MQTT state from DB after repository changes.
        try:
            mqtt_service.sync_state_with_db(db, reason="repository update")
            logger.info("Synced repositories with MQTT after update", repo_id=repo_id)
        except Exception as e:
            logger.warning(
                "Failed to sync repositories with MQTT after update",
                repo_id=repo_id,
                error=str(e),
            )

        return {"success": True, "message": "backend.success.repo.repositoryUpdated"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        logger.error("Failed to update repository", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToUpdateRepository"},
        )


@router.delete("/{repo_id}")
async def delete_repository(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete repository (admin only)"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.repositoryNotFound"},
            )
        _require_repository_access(db, current_user, repository, "operator")

        # CRITICAL: Clean up all foreign key references before deleting repository
        # Some tables don't have CASCADE delete, so we must manually handle them

        from app.database.models import (
            RepositoryScript,
            RestoreJob,
            CheckJob,
            RestoreCheckJob,
            PruneJob,
            CompactJob,
            ScheduledJob,
            ScheduledJobRepository,
            BackupJob,
            ScriptExecution,
        )

        # 1. Delete job records (these don't have CASCADE)
        # Note: RestoreJob stores repository path (string), not repository_id (int)
        restore_jobs = (
            db.query(RestoreJob).filter(RestoreJob.repository == repository.path).all()
        )
        for job in restore_jobs:
            db.delete(job)
        if restore_jobs:
            logger.info(
                "Deleted restore jobs", repo_id=repo_id, count=len(restore_jobs)
            )

        check_jobs = db.query(CheckJob).filter(CheckJob.repository_id == repo_id).all()
        for job in check_jobs:
            db.delete(job)
        if check_jobs:
            logger.info("Deleted check jobs", repo_id=repo_id, count=len(check_jobs))

        restore_check_jobs = (
            db.query(RestoreCheckJob)
            .filter(RestoreCheckJob.repository_id == repo_id)
            .all()
        )
        for job in restore_check_jobs:
            db.delete(job)
        if restore_check_jobs:
            logger.info(
                "Deleted restore check jobs",
                repo_id=repo_id,
                count=len(restore_check_jobs),
            )

        prune_jobs = db.query(PruneJob).filter(PruneJob.repository_id == repo_id).all()
        for job in prune_jobs:
            db.delete(job)
        if prune_jobs:
            logger.info("Deleted prune jobs", repo_id=repo_id, count=len(prune_jobs))

        compact_jobs = (
            db.query(CompactJob).filter(CompactJob.repository_id == repo_id).all()
        )
        for job in compact_jobs:
            db.delete(job)
        if compact_jobs:
            logger.info(
                "Deleted compact jobs", repo_id=repo_id, count=len(compact_jobs)
            )

        # 2. Set repository path to NULL (preserve historical backup jobs)
        # Note: BackupJob stores repository path (string), not repository_id (int)
        backup_jobs = (
            db.query(BackupJob).filter(BackupJob.repository == repository.path).all()
        )
        for job in backup_jobs:
            job.repository = None
        if backup_jobs:
            logger.info("Unlinked backup jobs", repo_id=repo_id, count=len(backup_jobs))

        # 3. Handle scheduled jobs
        # Set ScheduledJob.repository_id to NULL (for single-repo schedules)
        scheduled_jobs = (
            db.query(ScheduledJob).filter(ScheduledJob.repository_id == repo_id).all()
        )
        for job in scheduled_jobs:
            job.repository_id = None
        if scheduled_jobs:
            logger.info(
                "Unlinked scheduled jobs", repo_id=repo_id, count=len(scheduled_jobs)
            )

        # Delete junction table entries (this has CASCADE but delete manually to be safe)
        junction_entries = (
            db.query(ScheduledJobRepository)
            .filter(ScheduledJobRepository.repository_id == repo_id)
            .all()
        )
        for entry in junction_entries:
            db.delete(entry)
        if junction_entries:
            logger.info(
                "Deleted schedule-repository links",
                repo_id=repo_id,
                count=len(junction_entries),
            )

        # 4. Delete script associations (has CASCADE but delete manually to be explicit)
        script_associations = (
            db.query(RepositoryScript)
            .filter(RepositoryScript.repository_id == repo_id)
            .all()
        )
        for assoc in script_associations:
            db.delete(assoc)
        if script_associations:
            logger.info(
                "Deleted script associations",
                repo_id=repo_id,
                count=len(script_associations),
            )

        # 5. Null out script execution references (repository_id is nullable, preserve history)
        script_exec_count = (
            db.query(ScriptExecution)
            .filter(ScriptExecution.repository_id == repo_id)
            .update({"repository_id": None}, synchronize_session=False)
        )
        if script_exec_count:
            logger.info(
                "Unlinked script executions", repo_id=repo_id, count=script_exec_count
            )

        # 6. Finally, delete the repository itself
        db.delete(repository)
        db.commit()

        logger.info("Repository deleted", repo_id=repo_id, user=current_user.username)

        # Queue + publish MQTT cleanup for deleted repository
        try:
            mqtt_service.queue_deleted_repository_cleanup(db, repo_id)
            mqtt_service.sync_state_with_db(db, reason="repository deletion")
            logger.info("Queued MQTT cleanup for deleted repository", repo_id=repo_id)
        except Exception as e:
            logger.warning(
                "Failed to queue/publish MQTT cleanup for deleted repository",
                repo_id=repo_id,
                error=str(e),
            )

        return {"success": True, "message": "backend.success.repo.repositoryDeleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete repository", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToDeleteRepository"},
        )


@router.post("/{repo_id}/permanent-delete")
async def permanently_delete_repository(
    repo_id: int,
    request: RepositoryPermanentDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a local repository directory, then remove the Borg UI record."""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.repositoryNotFound"},
            )
        _require_repository_access(db, current_user, repository, "operator")

        if not request.understood or request.confirmation_phrase != repository.name:
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.repo.permanentDeleteConfirmationMismatch"
                },
            )

        repository_wipe_service._ensure_no_conflicting_operations(db, repository)
        target = _permanent_delete_target(repository)

        try:
            shutil.rmtree(target)
        except OSError as exc:
            logger.error(
                "Failed to remove repository files",
                repo_id=repo_id,
                path=repository.path,
                error=str(exc),
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "key": "backend.errors.repo.failedToRemoveRepositoryFiles",
                    "params": {"path": repository.path},
                },
            ) from exc

        await delete_repository(repo_id, current_user, db)
        logger.info(
            "Repository permanently deleted",
            repo_id=repo_id,
            path=str(target),
            user=current_user.username,
        )
        return {
            "success": True,
            "message": "backend.success.repo.repositoryPermanentlyDeleted",
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Failed to permanently delete repository", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToPermanentlyDeleteRepository"},
        )


@router.post("/{repo_id}/check")
async def check_repository(
    repo_id: int,
    request: dict = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a background check job for repository integrity"""
    try:
        repository = get_repository_with_access(
            db, current_user, repo_id, required_role="operator"
        )

        # Extract max_duration from request body (default to 3600)
        max_duration = request.get("max_duration", 3600) if request else 3600
        check_extra_flags = (
            _normalize_optional_flags(request.get("check_extra_flags"))
            if request
            else None
        )
        try:
            validate_check_flags_for_max_duration(check_extra_flags, max_duration)
        except CheckFlagConflictError as exc:
            _raise_check_flag_conflict(exc)

        if is_agent_executor(repository):
            ensure_repository_admission(
                db,
                repository,
                OPERATION_CHECK,
                duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
            )
            check_job = create_maintenance_job(
                db,
                CheckJob,
                repository,
                extra_fields={
                    "max_duration": max_duration,
                    "extra_flags": check_extra_flags,
                },
            )
            agent_job = queue_agent_repository_operation_job(
                db,
                repository,
                job_kind="repository.check",
                operation={
                    "max_duration": max_duration,
                    "check_extra_flags": check_extra_flags,
                },
                maintenance_job_kind="check",
                maintenance_job_id=check_job.id,
            )
            await dispatch_agent_job_best_effort(db, agent_job, repository_id=repo_id)
            logger.info(
                "Agent repository check job queued",
                job_id=check_job.id,
                agent_job_id=agent_job.id,
                repository_id=repo_id,
                user=current_user.username,
            )
            return {
                "job_id": check_job.id,
                "status": "pending",
                "message": "backend.success.repo.checkJobStarted",
            }

        check_job = start_background_maintenance_job(
            db,
            repository,
            CheckJob,
            error_key="backend.errors.repo.checkAlreadyRunning",
            dispatcher=partial(
                _dispatch_router_check,
                _router_repo_snapshot(repository),
            ),
            extra_fields={
                "max_duration": max_duration,
                "extra_flags": check_extra_flags,
            },
        )

        logger.info(
            "Check job created",
            job_id=check_job.id,
            repository_id=repo_id,
            user=current_user.username,
        )

        return {
            "job_id": check_job.id,
            "status": "pending",
            "message": "backend.success.repo.checkJobStarted",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start check job", error=str(e))
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToStartCheck"}
        )


@router.post("/{repo_id}/restore-check")
async def restore_check_repository(
    repo_id: int,
    request: dict = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a background restore verification job using the latest archive."""
    try:
        repository = get_repository_with_access(
            db, current_user, repo_id, required_role="operator"
        )
        probe_paths, full_archive = _resolve_restore_check_targets(
            request=request,
            repository=repository,
        )
        _ensure_restore_check_mode_allowed(
            repository=repository,
            probe_paths=probe_paths,
            full_archive=full_archive,
        )
        is_canary_mode = _is_restore_check_canary_mode(
            probe_paths=probe_paths, full_archive=full_archive
        )
        if is_canary_mode:
            repository.restore_check_canary_enabled = True
            repository.restore_check_paths = json.dumps([])
            repository.restore_check_full_archive = False

        restore_check_job = start_background_maintenance_job(
            db,
            repository,
            RestoreCheckJob,
            error_key="backend.errors.repo.restoreCheckAlreadyRunning",
            dispatcher=lambda job: restore_check_service.execute_restore_check(
                job.id, repository.id
            ),
            extra_fields={
                "probe_paths": json.dumps(probe_paths),
                "full_archive": full_archive,
                "scheduled_restore_check": False,
            },
        )

        logger.info(
            "Restore check job created",
            job_id=restore_check_job.id,
            repository_id=repo_id,
            user=current_user.username,
        )

        return {
            "job_id": restore_check_job.id,
            "status": "pending",
            "message": "backend.success.repo.restoreCheckJobStarted",
        }
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.invalidRestoreCheckPaths"},
        )
    except Exception as e:
        logger.error("Failed to start restore check job", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToStartRestoreCheck"},
        )


@router.post("/{repo_id}/compact")
async def compact_repository(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a background compact job to free space"""
    try:
        repository = get_repository_with_access(
            db, current_user, repo_id, required_role="operator"
        )
        if is_agent_executor(repository):
            ensure_repository_admission(
                db,
                repository,
                OPERATION_COMPACT,
                duplicate_error_key="backend.errors.repo.compactAlreadyRunning",
            )
            compact_job = create_maintenance_job(
                db,
                CompactJob,
                repository,
                extra_fields={"scheduled_compact": False},
            )
            agent_job = queue_agent_repository_operation_job(
                db,
                repository,
                job_kind="repository.compact",
                maintenance_job_kind="compact",
                maintenance_job_id=compact_job.id,
            )
            await dispatch_agent_job_best_effort(db, agent_job, repository_id=repo_id)
            logger.info(
                "Agent repository compact job queued",
                job_id=compact_job.id,
                agent_job_id=agent_job.id,
                repository_id=repo_id,
                user=current_user.username,
            )
            return {
                "job_id": compact_job.id,
                "status": "pending",
                "message": "backend.success.repo.compactJobStarted",
            }

        compact_job = start_background_maintenance_job(
            db,
            repository,
            CompactJob,
            error_key="backend.errors.repo.compactAlreadyRunning",
            dispatcher=partial(
                _dispatch_router_compact,
                _router_repo_snapshot(repository),
            ),
            extra_fields={"scheduled_compact": False},
        )

        logger.info(
            "Compact job created",
            job_id=compact_job.id,
            repository_id=repo_id,
            user=current_user.username,
        )

        return {
            "job_id": compact_job.id,
            "status": "pending",
            "message": "backend.success.repo.compactJobStarted",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start compact job", error=str(e))
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToStartCompact"}
        )


@router.post("/{repo_id}/prune")
async def prune_repository(
    repo_id: int,
    request: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a background prune job to remove old archives based on retention policy"""
    try:
        repository = get_repository_with_access(
            db, current_user, repo_id, required_role="operator"
        )
        ensure_repository_admission(
            db,
            repository,
            OPERATION_PRUNE,
            duplicate_error_key="backend.errors.repo.pruneAlreadyRunning",
        )

        # Extract retention policy from request
        keep_hourly = request.get("keep_hourly", 0)
        keep_daily = request.get("keep_daily", 7)
        keep_weekly = request.get("keep_weekly", 4)
        keep_monthly = request.get("keep_monthly", 6)
        keep_quarterly = request.get("keep_quarterly", 0)
        keep_yearly = request.get("keep_yearly", 1)
        keep_within = _normalize_prune_keep_within(request.get("keep_within"))
        dry_run = request.get("dry_run", False)

        if is_agent_executor(repository):
            prune_job = create_maintenance_job(
                db,
                PruneJob,
                repository,
                extra_fields={
                    "scheduled_prune": False,
                },
            )
            agent_job = queue_agent_repository_operation_job(
                db,
                repository,
                job_kind="repository.prune",
                operation=_agent_prune_operation_payload(request),
                maintenance_job_kind="prune",
                maintenance_job_id=prune_job.id,
            )
            await dispatch_agent_job_best_effort(db, agent_job, repository_id=repo_id)
            logger.info(
                "Agent repository prune job queued",
                job_id=prune_job.id,
                agent_job_id=agent_job.id,
                repository_id=repo_id,
                dry_run=dry_run,
                user=current_user.username,
            )
            if not dry_run:
                return {
                    "job_id": prune_job.id,
                    "status": "pending",
                    "message": "backend.success.repo.pruneJobStarted",
                }

            result = await wait_for_agent_repository_operation_job(db, agent_job.id)
            db.refresh(prune_job)
            if prune_job.status == "pending":
                prune_job.status = "completed"
                prune_job.completed_at = datetime.utcnow()
                db.commit()
                db.refresh(prune_job)
            stdout_output = read_job_logs(
                prune_job, fallback_to_logs=True, log_save_policy="all_jobs"
            )
            if not stdout_output:
                stdout_output = str(result.get("stdout") or "")
            return {
                "job_id": prune_job.id,
                "status": prune_job.status,
                "dry_run": dry_run,
                "prune_result": {
                    "success": prune_job.status == "completed",
                    "stdout": stdout_output,
                    "stderr": prune_job.error_message
                    or str(result.get("stderr") or ""),
                },
            }

        if not dry_run:
            prune_job = start_background_maintenance_job(
                db,
                repository,
                PruneJob,
                error_key="backend.errors.repo.pruneAlreadyRunning",
                dispatcher=partial(
                    _dispatch_router_prune,
                    _router_repo_snapshot(repository),
                    keep_hourly,
                    keep_daily,
                    keep_weekly,
                    keep_monthly,
                    keep_quarterly,
                    keep_yearly,
                    keep_within,
                ),
                extra_fields={"scheduled_prune": False},
            )

            logger.info(
                "Prune job created",
                job_id=prune_job.id,
                repository_id=repo_id,
                user=current_user.username,
            )

            return {
                "job_id": prune_job.id,
                "status": "pending",
                "message": "backend.success.repo.pruneJobStarted",
            }

        prune_job = create_maintenance_job(
            db,
            PruneJob,
            repository,
            extra_fields={
                "scheduled_prune": False,
            },
        )

        logger.info(
            "Starting prune job",
            job_id=prune_job.id,
            repository_id=repo_id,
            dry_run=dry_run,
            user=current_user.username,
        )

        # Wait for prune to complete and get logs
        prune_kwargs = {"keep_within": keep_within} if keep_within is not None else {}
        await BorgRouter(repository).prune(
            prune_job.id,
            keep_hourly,
            keep_daily,
            keep_weekly,
            keep_monthly,
            keep_quarterly,
            keep_yearly,
            dry_run,
            **prune_kwargs,
        )

        # Refresh job to get updated status and logs
        db.refresh(prune_job)

        # Read log file if it exists
        stdout_output = read_job_logs(
            prune_job, fallback_to_logs=True, log_save_policy="all_jobs"
        )
        stderr_output = ""

        # Return results in format expected by frontend
        return {
            "job_id": prune_job.id,
            "status": prune_job.status,
            "dry_run": dry_run,
            "prune_result": {
                "success": prune_job.status == "completed",
                "stdout": stdout_output,
                "stderr": stderr_output
                if stderr_output or prune_job.error_message
                else (prune_job.error_message or ""),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start prune job", error=str(e))
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToStartPrune"}
        )


@router.post("/{repo_id}/wipe-preview")
async def preview_repository_wipe(
    repo_id: int,
    request: RepositoryWipePreviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a guarded dry-run preview for wiping repository archives."""
    try:
        repository = get_repository_with_access(
            db, current_user, repo_id, required_role="operator"
        )
        return await repository_wipe_service.create_preview(
            db,
            repository,
            current_user,
            run_compact=request.run_compact,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate repository wipe preview", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToPreviewWipe"},
        )


@router.post("/{repo_id}/wipe")
async def execute_repository_wipe(
    repo_id: int,
    request: RepositoryWipeExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Validate the preview and start repository contents wipe execution."""
    try:
        repository = get_repository_with_access(
            db, current_user, repo_id, required_role="operator"
        )
        job = await repository_wipe_service.start_execution(
            db,
            repository,
            current_user,
            preview_id=request.preview_id,
            preview_fingerprint=request.preview_fingerprint,
            confirmation_phrase=request.confirmation_phrase,
            understood=request.understood,
            run_compact=request.run_compact,
        )
        asyncio.create_task(repository_wipe_service.execute_wipe(job.id, repo_id))
        return repository_wipe_service.serialize_job(job)
    except WipeArchiveSetChanged:
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.repo.wipePreviewStale"},
        )
    except WipeValidationError as e:
        raise HTTPException(status_code=e.status_code, detail={"key": e.detail_key})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start repository wipe", error=str(e))
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToStartWipe"}
        )


@router.get("/{repo_id}/wipe-jobs/{job_id}")
async def get_repository_wipe_job(
    repo_id: int,
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get repository wipe job status and logs."""
    try:
        repository = get_repository_with_access(
            db, current_user, repo_id, required_role="operator"
        )
        job = (
            db.query(RepositoryWipeJob)
            .filter(
                RepositoryWipeJob.id == job_id,
                RepositoryWipeJob.repository_id == repository.id,
            )
            .first()
        )
        if not job:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.wipeJobNotFound"},
            )
        return repository_wipe_service.serialize_job(
            job,
            include_preview=True,
            include_logs=True,
            log_save_policy=get_log_save_policy(db),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get repository wipe job", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToGetWipeJob"}
        )


@router.post("/{repo_id}/wipe-jobs/{job_id}/cancel")
async def cancel_repository_wipe_preview(
    repo_id: int,
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record cancellation for a previewed or queued wipe job."""
    try:
        repository = get_repository_with_access(
            db, current_user, repo_id, required_role="operator"
        )
        return repository_wipe_service.cancel_preview(
            db,
            repository,
            current_user,
            job_id=job_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to cancel repository wipe preview", error=str(e), job_id=job_id
        )
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToCancelWipe"},
        )


@router.get("/{repo_id}/stats")
async def get_repository_statistics(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get repository statistics"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.repositoryNotFound"},
            )
        _require_repository_access(db, current_user, repository, "viewer")

        # Check system-wide bypass_lock_on_list setting
        from app.database.models import SystemSettings

        system_settings = db.query(SystemSettings).first()
        use_bypass_lock = repository.bypass_lock or (
            system_settings and system_settings.bypass_lock_on_list
        )

        # Get detailed statistics
        stats = await get_repository_stats(repository, db, bypass_lock=use_bypass_lock)

        return {"success": True, "stats": stats}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get repository statistics", error=str(e))
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToGetStatistics"}
        )


async def check_remote_borg_installation(
    host: str, username: str, port: int, ssh_key_id: int
) -> Dict[str, Any]:
    """Check if borg is installed on remote machine"""
    temp_key_file = None
    try:
        logger.info(
            "Checking remote borg installation", host=host, username=username, port=port
        )

        # Get SSH key from database
        from app.database.models import SSHKey
        from app.database.database import get_db
        import tempfile

        db = next(get_db())
        ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_key_id).first()
        if not ssh_key:
            return {"success": False, "error": "SSH key not found", "has_borg": False}

        # Decrypt private key
        private_key = decrypt_secret(ssh_key.private_key)

        # Ensure private key ends with newline
        if not private_key.endswith("\n"):
            private_key += "\n"

        # Create temporary key file
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(private_key)
            temp_key_file = f.name

        os.chmod(temp_key_file, 0o600)

        # Check for borg
        borg_cmd = [
            "ssh",
            *ssh_key_auth_args(temp_key_file),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=10",
            "-p",
            str(port),
            f"{username}@{host}",
            "which borg",
        ]

        borg_process = await asyncio.create_subprocess_exec(
            *borg_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        borg_stdout, borg_stderr = await asyncio.wait_for(
            borg_process.communicate(), timeout=15
        )
        has_borg = borg_process.returncode == 0

        logger.info("Remote borg check completed", host=host, has_borg=has_borg)

        return {
            "success": True,
            "has_borg": has_borg,
            "borg_path": borg_stdout.decode().strip() if has_borg else None,
        }

    except asyncio.TimeoutError:
        logger.error("Remote borg check timed out", host=host)
        return {
            "success": False,
            "error": "Connection timeout while checking remote borg installation",
            "has_borg": False,
        }
    except Exception as e:
        logger.error(
            "Failed to check remote borg installation", host=host, error=str(e)
        )
        return {"success": False, "error": str(e), "has_borg": False}
    finally:
        if temp_key_file and os.path.exists(temp_key_file):
            try:
                os.unlink(temp_key_file)
            except Exception as e:
                logger.warning("Failed to clean up temp SSH key", error=str(e))


async def verify_existing_repository(
    path: str,
    passphrase: str = None,
    ssh_key_id: int = None,
    remote_path: str = None,
    bypass_lock: bool = False,
    borg_version: int = 1,
) -> Dict[str, Any]:
    """Verify an existing Borg repository by running borg info"""
    try:
        logger.info(
            "Verifying existing repository",
            path=path,
            has_passphrase=bool(passphrase),
            bypass_lock=bypass_lock,
        )
        repo_for_routing = SimpleNamespace(
            path=path,
            passphrase=passphrase,
            remote_path=remote_path,
            borg_version=borg_version,
            bypass_lock=bypass_lock,
        )
        return await BorgRouter(repo_for_routing).verify_repository(
            ssh_key_id=ssh_key_id,
            timeout=get_operation_timeouts()["info_timeout"],
        )
    except Exception as e:
        logger.error("Failed to verify repository", path=path, error=str(e))
        return {"success": False, "error": str(e)}


async def initialize_borg_repository(
    path: str,
    encryption: str,
    passphrase: str = None,
    ssh_key_id: int = None,
    remote_path: str = None,
    borg_version: int = 1,
) -> Dict[str, Any]:
    """Initialize a new Borg repository"""
    logger.info(
        "Starting repository initialization",
        path=path,
        encryption=encryption,
        has_passphrase=bool(passphrase),
        ssh_key_id=ssh_key_id,
        remote_path=remote_path,
        borg_version=borg_version,
    )
    repo_for_routing = SimpleNamespace(
        path=path,
        encryption=encryption,
        passphrase=passphrase,
        remote_path=remote_path,
        borg_version=borg_version,
    )
    result = await BorgRouter(repo_for_routing).initialize_repository(
        ssh_key_id=ssh_key_id,
        init_timeout=get_operation_timeouts()["init_timeout"],
    )
    if result.get("success"):
        result.setdefault("message", "backend.success.repo.repositoryInitialized")
        result.setdefault("already_existed", False)
    elif (
        result.get("return_code") == 2
        and "repository already exists" in (result.get("stderr") or "").lower()
    ):
        return {
            "success": True,
            "message": "backend.success.repo.repositoryAlreadyExists",
            "already_existed": True,
        }
    return result


@router.get("/{repo_id}/archives")
async def list_repository_archives(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all archives in a repository using borg list"""

    async def _operation():
        repository = _load_repository_with_access(repo_id, current_user, db, "viewer")
        if is_agent_executor(repository):
            agent_job = queue_agent_repository_operation_job(
                db,
                repository,
                job_kind="repository.list_archives",
            )
            await dispatch_agent_job_best_effort(db, agent_job, repository_id=repo_id)
            result = await wait_for_agent_repository_operation_job(db, agent_job.id)
            archives_data = _parse_agent_json_result(result)
            archives = archives_data.get("archives", [])
            archives = enrich_archives_with_backup_metadata(archives, repository, db)
            logger.info(
                "Agent repository archives listed successfully",
                repo_id=repo_id,
                agent_job_id=agent_job.id,
                count=len(archives),
            )
            return {
                "success": True,
                "archives": archives,
                "repository": {
                    "id": repository.id,
                    "name": repository.name,
                    "path": repository.path,
                },
            }

        use_bypass_lock, source = _resolve_bypass_lock(
            repository, db, "bypass_lock_on_list"
        )
        router = BorgRouter(repository)
        cmd = router.build_repo_list_command(repository.path)
        if repository.remote_path:
            cmd.extend(["--remote-path", repository.remote_path])
        if use_bypass_lock:
            cmd.append("--bypass-lock")

        stdout = await _run_repository_command_with_retries(
            repository,
            db,
            repo_id=repo_id,
            cmd=cmd,
            timeout=get_operation_timeouts(db)["list_timeout"],
            bypass_lock=use_bypass_lock,
            source=source,
            command_label="Executing borg list command",
            ssh_log_message="Using SSH key for archive list",
            failure_key="backend.errors.repo.failedToListArchives",
        )
        # Parse JSON output
        try:
            archives_data = json.loads(stdout.decode())
            archives = archives_data.get("archives", [])
            archives = enrich_archives_with_backup_metadata(archives, repository, db)

            logger.info(
                "Archives listed successfully", repo_id=repo_id, count=len(archives)
            )

            return {
                "success": True,
                "archives": archives,
                "repository": {
                    "id": repository.id,
                    "name": repository.name,
                    "path": repository.path,
                },
            }
        except json.JSONDecodeError as e:
            logger.error("Failed to parse borg list output", error=str(e))
            raise HTTPException(
                status_code=500,
                detail={"key": "backend.errors.repo.failedParseArchiveList"},
            )

    return await run_serialized_repository_command(repo_id, _operation)


@router.get("/{repo_id}/info")
async def get_repository_info(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get detailed repository information using borg info"""

    async def _operation():
        repository = _load_repository_with_access(repo_id, current_user, db, "viewer")
        if is_agent_executor(repository):
            agent_job = queue_agent_repository_operation_job(
                db,
                repository,
                job_kind="repository.info",
            )
            await dispatch_agent_job_best_effort(db, agent_job, repository_id=repo_id)
            result = await wait_for_agent_repository_operation_job(db, agent_job.id)
            info_data = _parse_agent_json_result(result)
            logger.info(
                "Agent repository info retrieved successfully",
                repo_id=repo_id,
                agent_job_id=agent_job.id,
            )
            return {
                "success": True,
                "info": {
                    "repository": info_data.get("repository", {}),
                    "cache": info_data.get("cache", {}),
                    "encryption": info_data.get("encryption", {}),
                },
                "raw_output": info_data,
            }

        use_bypass_lock, source = _resolve_bypass_lock(
            repository, db, "bypass_lock_on_info"
        )
        router = BorgRouter(repository)
        cmd = router.build_repo_info_command(repository.path)
        if repository.remote_path:
            cmd.extend(["--remote-path", repository.remote_path])
        if use_bypass_lock:
            cmd.append("--bypass-lock")

        stdout = await _run_repository_command_with_retries(
            repository,
            db,
            repo_id=repo_id,
            cmd=cmd,
            timeout=get_operation_timeouts(db)["info_timeout"],
            bypass_lock=use_bypass_lock,
            source=source,
            command_label="Executing borg info command",
            ssh_log_message="Using SSH key for repository info",
            failure_key="backend.errors.repo.failedToGetRepositoryInfo",
        )
        # Parse JSON output
        try:
            info_data = json.loads(stdout.decode())

            # Extract relevant information
            repository_info = info_data.get("repository", {})
            cache_info = info_data.get("cache", {})
            encryption_info = info_data.get("encryption", {})

            logger.info("Repository info retrieved successfully", repo_id=repo_id)

            return {
                "success": True,
                "info": {
                    "repository": repository_info,
                    "cache": cache_info,
                    "encryption": encryption_info,
                },
                "raw_output": info_data,
            }
        except HTTPException:
            raise
        except json.JSONDecodeError as e:
            logger.error("Failed to parse borg info output", error=str(e))
            raise HTTPException(
                status_code=500,
                detail={"key": "backend.errors.repo.failedParseRepositoryInfo"},
            )
        except Exception as e:
            logger.error("Failed to get repository info", error=str(e))
            raise HTTPException(
                status_code=500,
                detail={"key": "backend.errors.repo.failedToGetRepositoryInfo"},
            )

    return await run_serialized_repository_command(repo_id, _operation)


@router.post("/{repo_id}/break-lock")
async def break_repository_lock(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Break a stale lock on a repository (user-initiated)"""
    try:
        repository = _load_repository_with_access(repo_id, current_user, db, "operator")
        settings = db.query(SystemSettings).first()
        if settings and not settings.lock_breaking_enabled:
            raise HTTPException(
                status_code=403,
                detail={"key": "backend.errors.repo.lockBreakingDisabled"},
            )

        logger.warning(
            "User requested lock break", repo_id=repo_id, user=current_user.username
        )

        # Break the lock using borg break-lock
        env, temp_key_file = _prepare_repository_borg_env(repository, db)
        try:
            result = await BorgRouter(repository).break_lock(env=env)
        finally:
            cleanup_temp_key_file(temp_key_file)

        if result.get("success"):
            logger.info(
                "Successfully broke repository lock",
                repo_id=repo_id,
                user=current_user.username,
            )
            return {"success": True, "message": "backend.success.repo.lockBroken"}
        else:
            error_msg = result.get("stderr", "Unknown error")
            logger.error("Failed to break lock", repo_id=repo_id, error=error_msg)
            raise HTTPException(
                status_code=500, detail={"key": "backend.errors.repo.failedToBreakLock"}
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error breaking repository lock", repo_id=repo_id, error=str(e))
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToBreakLock"}
        )


async def get_repository_stats(
    repository: Repository, db: Session, bypass_lock: bool = False
) -> Dict[str, Any]:
    """Get repository statistics"""
    if is_agent_executor(repository):
        return {
            "total_size": repository.total_size or "Unknown",
            "compressed_size": "Unknown",
            "deduplicated_size": "Unknown",
            "archive_count": repository.archive_count or 0,
            "last_modified": format_datetime(repository.updated_at),
            "encryption": repository.encryption or "Unknown",
            "executor": "agent",
        }

    temp_key_file = None
    try:
        env, temp_key_file = _prepare_repository_borg_env(repository, db)

        router = BorgRouter(repository)
        cmd = router.build_repo_info_command(repository.path)
        if bypass_lock:
            cmd.append("--bypass-lock")
        if repository.remote_path:
            cmd.extend(["--remote-path", repository.remote_path])
        info_result = await borg._execute_command(cmd, env=env)

        if not info_result["success"]:
            return {
                "error": "Failed to get repository info",
                "details": info_result["stderr"],
            }

        # Parse repository info (basic implementation)
        # In a real implementation, you would parse the borg info output
        stats = {
            "total_size": "Unknown",
            "compressed_size": "Unknown",
            "deduplicated_size": "Unknown",
            "archive_count": 0,
            "last_modified": None,
            "encryption": "Unknown",
        }

        # Try to get archive count
        archives_data = await router.list_archives(env=env)
        if archives_data is not None:
            try:
                if archives_data:
                    stats["archive_count"] = len(archives_data)
            except:
                pass

        return stats
    except Exception as e:
        logger.error("Failed to get repository stats", error=str(e))
        return {"error": str(e)}
    finally:
        if temp_key_file and os.path.exists(temp_key_file):
            try:
                os.unlink(temp_key_file)
            except Exception:
                pass


# Check job endpoints
@router.get("/check-jobs/{job_id}")
async def get_check_job_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get status of a check job"""
    try:
        job, _ = get_job_with_repository(
            db,
            current_user,
            CheckJob,
            job_id,
            not_found_key="backend.errors.repo.checkJobNotFound",
        )
        return serialize_job_status(
            job,
            include_progress=True,
            include_logs=True,
            log_save_policy=get_log_save_policy(db),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get check job status", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToGetJobStatus"}
        )


@router.get("/{repo_id}/check-jobs")
async def get_repository_check_jobs(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 10,
    scheduled_only: bool = False,
):
    """Get recent check jobs for a repository"""
    try:
        jobs = get_repository_jobs(db, current_user, repo_id, CheckJob, limit=limit)
        if scheduled_only:
            jobs = [job for job in jobs if bool(getattr(job, "scheduled_check", False))]
        log_save_policy = get_log_save_policy(db)
        return {
            "jobs": [
                {
                    **serialize_job_summary(
                        job,
                        include_progress=True,
                        include_has_logs=True,
                        log_save_policy=log_save_policy,
                    ),
                    "scheduled_check": bool(getattr(job, "scheduled_check", False)),
                }
                for job in jobs
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get check jobs", error=str(e), repository_id=repo_id)
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToGetCheckJobs"}
        )


@router.get("/restore-check-jobs/{job_id}")
async def get_restore_check_job_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get status of a restore verification job."""
    try:
        job, _ = get_job_with_repository(
            db,
            current_user,
            RestoreCheckJob,
            job_id,
            not_found_key="backend.errors.repo.restoreCheckJobNotFound",
        )
        payload = serialize_job_status(
            job,
            include_progress=True,
            include_logs=True,
            include_has_logs=True,
            log_save_policy=get_log_save_policy(db),
        )
        probe_paths = json.loads(job.probe_paths) if job.probe_paths else []
        payload["archive_name"] = job.archive_name
        payload["probe_paths"] = probe_paths
        payload["full_archive"] = bool(job.full_archive)
        payload["mode"] = _get_restore_check_mode(
            probe_paths=probe_paths,
            full_archive=bool(job.full_archive),
        )
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get restore check job status", error=str(e), job_id=job_id
        )
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToGetJobStatus"}
        )


@router.get("/{repo_id}/restore-check-jobs")
async def get_repository_restore_check_jobs(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 10,
):
    """Get recent restore verification jobs for a repository."""
    try:
        jobs = get_repository_jobs(
            db, current_user, repo_id, RestoreCheckJob, limit=limit
        )
        log_save_policy = get_log_save_policy(db)
        return {
            "jobs": [
                (
                    lambda probe_paths: {
                        **serialize_job_summary(
                            job,
                            include_progress=True,
                            include_has_logs=True,
                            log_save_policy=log_save_policy,
                        ),
                        "archive_name": job.archive_name,
                        "probe_paths": probe_paths,
                        "full_archive": bool(job.full_archive),
                        "mode": _get_restore_check_mode(
                            probe_paths=probe_paths,
                            full_archive=bool(job.full_archive),
                        ),
                    }
                )(json.loads(job.probe_paths) if job.probe_paths else [])
                for job in jobs
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get restore check jobs", error=str(e), repository_id=repo_id
        )
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToGetRestoreCheckJobs"},
        )


# Compact job endpoints
@router.get("/compact-jobs/{job_id}")
async def get_compact_job_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get status of a compact job"""
    try:
        job, _ = get_job_with_repository(
            db,
            current_user,
            CompactJob,
            job_id,
            not_found_key="backend.errors.repo.compactJobNotFound",
        )
        return serialize_job_status(
            job,
            include_progress=True,
            include_logs=True,
            log_save_policy=get_log_save_policy(db),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get compact job status", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToGetJobStatus"}
        )


@router.get("/{repo_id}/compact-jobs")
async def get_repository_compact_jobs(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 10,
):
    """Get recent compact jobs for a repository"""
    try:
        jobs = get_repository_jobs(db, current_user, repo_id, CompactJob, limit=limit)
        log_save_policy = get_log_save_policy(db)
        return {
            "jobs": [
                serialize_job_summary(
                    job,
                    include_progress=True,
                    log_save_policy=log_save_policy,
                )
                for job in jobs
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get compact jobs", error=str(e), repository_id=repo_id)
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToGetCompactJobs"},
        )


@router.get("/prune-jobs/{job_id}")
async def get_prune_job_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get status of a prune job"""
    try:
        job, _ = get_job_with_repository(
            db,
            current_user,
            PruneJob,
            job_id,
            not_found_key="backend.errors.repo.pruneJobNotFound",
        )
        return serialize_job_status(
            job,
            include_logs=True,
            log_save_policy=get_log_save_policy(db),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get prune job status", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToGetJobStatus"}
        )


@router.get("/{repo_id}/prune-jobs")
async def get_repository_prune_jobs(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 10,
):
    """Get recent prune jobs for a repository"""
    try:
        jobs = get_repository_jobs(db, current_user, repo_id, PruneJob, limit=limit)
        log_save_policy = get_log_save_policy(db)
        return {
            "jobs": [
                serialize_job_summary(
                    job,
                    include_has_logs=True,
                    log_save_policy=log_save_policy,
                )
                for job in jobs
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get prune jobs", error=str(e), repository_id=repo_id)
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToGetPruneJobs"}
        )


# Helper endpoint to check if repository has running maintenance jobs
@router.get("/{repo_id}/running-jobs")
async def get_running_jobs(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if repository has any running check, compact, or prune jobs"""
    try:
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            return _empty_running_jobs_response()
        _require_repository_access(db, current_user, repository, "viewer")
        # Force refresh from database to get latest values
        db.expire_all()

        check_job = (
            db.query(CheckJob)
            .filter(
                CheckJob.repository_id == repo_id,
                CheckJob.status.in_(ACTIVE_MAINTENANCE_JOB_STATUSES),
            )
            .first()
        )

        compact_job = (
            db.query(CompactJob)
            .filter(
                CompactJob.repository_id == repo_id,
                CompactJob.status.in_(ACTIVE_MAINTENANCE_JOB_STATUSES),
            )
            .first()
        )

        prune_job = (
            db.query(PruneJob)
            .filter(
                PruneJob.repository_id == repo_id,
                PruneJob.status.in_(ACTIVE_MAINTENANCE_JOB_STATUSES),
            )
            .first()
        )

        restore_check_job = (
            db.query(RestoreCheckJob)
            .filter(
                RestoreCheckJob.repository_id == repo_id,
                RestoreCheckJob.status.in_(ACTIVE_MAINTENANCE_JOB_STATUSES),
            )
            .first()
        )

        wipe_job = (
            db.query(RepositoryWipeJob)
            .filter(
                RepositoryWipeJob.repository_id == repo_id,
                RepositoryWipeJob.status.in_(("pending", "running")),
            )
            .first()
        )

        result = {
            "has_running_jobs": bool(
                check_job or compact_job or prune_job or restore_check_job or wipe_job
            ),
            "check_job": {
                "id": check_job.id,
                "status": check_job.status,
                "progress": check_job.progress,
                "progress_message": check_job.progress_message,
                "started_at": serialize_datetime(check_job.started_at),
            }
            if check_job
            else None,
            "compact_job": {
                "id": compact_job.id,
                "status": compact_job.status,
                "progress": compact_job.progress,
                "progress_message": compact_job.progress_message,
                "started_at": serialize_datetime(compact_job.started_at),
            }
            if compact_job
            else None,
            "prune_job": {
                "id": prune_job.id,
                "status": prune_job.status,
                "started_at": serialize_datetime(prune_job.started_at),
            }
            if prune_job
            else None,
            "restore_check_job": {
                "id": restore_check_job.id,
                "status": restore_check_job.status,
                "progress": restore_check_job.progress,
                "progress_message": restore_check_job.progress_message,
                "started_at": serialize_datetime(restore_check_job.started_at),
            }
            if restore_check_job
            else None,
            "wipe_job": {
                "id": wipe_job.id,
                "status": wipe_job.status,
                "phase": wipe_job.phase,
                "progress": wipe_job.progress,
                "progress_message": wipe_job.progress_message,
                "started_at": serialize_datetime(wipe_job.started_at),
            }
            if wipe_job
            else None,
        }

        logger.info("Running jobs API response", repository_id=repo_id, result=result)

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get running jobs", error=str(e), repository_id=repo_id)
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToGetRunningJobs"},
        )


@router.put("/{repo_id}/check-schedule")
async def update_check_schedule(
    repo_id: int,
    request: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update scheduled check configuration for repository"""
    try:
        repo = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repo:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.repositoryNotFound"},
            )
        _require_repository_access(db, current_user, repo, "operator")

        # Update check schedule settings
        if "timezone" in request or "check_timezone" in request:
            try:
                repo.check_timezone = normalize_schedule_timezone(
                    request.get("timezone", request.get("check_timezone"))
                )
            except InvalidScheduleTimezone as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "key": "backend.errors.schedule.invalidTimezone",
                        "params": {"error": str(e)},
                    },
                )

        cron_expression = request.get("cron_expression")
        if cron_expression is not None:
            # Set to None if empty string or "disabled"
            if not cron_expression or cron_expression.strip() == "":
                repo.check_cron_expression = None
                # Clearing the cron is "remove schedule" — also force toggle off
                # so the row reflects a clean removed state.
                repo.check_schedule_enabled = False
            else:
                # Validate cron expression
                try:
                    calculate_next_cron_run(
                        cron_expression,
                        schedule_timezone=repo.check_timezone
                        or DEFAULT_SCHEDULE_TIMEZONE,
                    )
                    repo.check_cron_expression = cron_expression
                except InvalidScheduleTimezone as e:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "key": "backend.errors.schedule.invalidTimezone",
                            "params": {"error": str(e)},
                        },
                    )
                except Exception:
                    raise HTTPException(
                        status_code=400,
                        detail={"key": "backend.errors.repo.invalidCronExpression"},
                    )
                # Setting a cron implies the user wants it active. The toggle
                # request body can still override this by sending schedule_enabled
                # below.
                repo.check_schedule_enabled = True

        # Explicit toggle (independent of cron). Allows pause/resume without
        # losing the cron expression.
        schedule_enabled = request.get("schedule_enabled")
        if schedule_enabled is not None:
            repo.check_schedule_enabled = bool(schedule_enabled)

        max_duration = request.get("max_duration")
        if max_duration is not None:
            repo.check_max_duration = max_duration

        if "check_extra_flags" in request:
            repo.check_extra_flags = _normalize_optional_flags(
                request.get("check_extra_flags")
            )

        if repo.check_cron_expression and repo.check_schedule_enabled:
            try:
                validate_check_flags_for_max_duration(
                    repo.check_extra_flags, repo.check_max_duration
                )
            except CheckFlagConflictError as exc:
                _raise_check_flag_conflict(exc)

        notify_on_success = request.get("notify_on_success")
        if notify_on_success is not None:
            repo.notify_on_check_success = notify_on_success

        notify_on_failure = request.get("notify_on_failure")
        if notify_on_failure is not None:
            repo.notify_on_check_failure = notify_on_failure

        # Calculate next check time from cron expression
        if repo.check_cron_expression and repo.check_schedule_enabled:
            try:
                repo.next_scheduled_check = calculate_next_cron_run(
                    repo.check_cron_expression,
                    schedule_timezone=repo.check_timezone or DEFAULT_SCHEDULE_TIMEZONE,
                )
            except Exception as e:
                logger.error(
                    "Failed to calculate next check time", error=str(e), repo_id=repo_id
                )
                repo.next_scheduled_check = None
        else:
            # Disabled - clear next scheduled check
            repo.next_scheduled_check = None

        db.commit()
        db.refresh(repo)

        logger.info(
            "Check schedule updated",
            repo_id=repo_id,
            cron_expression=repo.check_cron_expression,
            check_timezone=repo.check_timezone,
            next_check=repo.next_scheduled_check,
        )

        return {
            "success": True,
            "repository": {
                "id": repo.id,
                "name": repo.name,
                "check_cron_expression": repo.check_cron_expression,
                "check_schedule_enabled": bool(repo.check_schedule_enabled),
                "check_timezone": repo.check_timezone or DEFAULT_SCHEDULE_TIMEZONE,
                "timezone": repo.check_timezone or DEFAULT_SCHEDULE_TIMEZONE,
                "last_scheduled_check": serialize_datetime(repo.last_scheduled_check),
                "next_scheduled_check": serialize_datetime(repo.next_scheduled_check),
                "check_max_duration": repo.check_max_duration,
                "check_extra_flags": repo.check_extra_flags,
                "notify_on_check_success": repo.notify_on_check_success,
                "notify_on_check_failure": repo.notify_on_check_failure,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update check schedule", error=str(e), repo_id=repo_id)
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToUpdateCheckSchedule"},
        )


@router.put("/{repo_id}/restore-check-schedule")
async def update_restore_check_schedule(
    repo_id: int,
    request: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update scheduled restore verification configuration for a repository."""
    try:
        repo = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repo:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.repositoryNotFound"},
            )
        _require_repository_access(db, current_user, repo, "operator")

        if repo.mode == "observe":
            if "paths" in request:
                requested_paths = _normalize_restore_check_paths(request.get("paths"))
            else:
                requested_paths = _normalize_restore_check_paths(
                    json.loads(repo.restore_check_paths)
                    if repo.restore_check_paths
                    else []
                )
            requested_full_archive = (
                bool(request.get("full_archive"))
                if "full_archive" in request
                else bool(repo.restore_check_full_archive)
            )
            requested_cron_expression = request.get(
                "cron_expression", repo.restore_check_cron_expression
            )
            if requested_cron_expression and requested_cron_expression.strip():
                _ensure_restore_check_mode_allowed(
                    repository=repo,
                    probe_paths=requested_paths,
                    full_archive=requested_full_archive,
                )

        if "timezone" in request or "restore_check_timezone" in request:
            try:
                repo.restore_check_timezone = normalize_schedule_timezone(
                    request.get("timezone", request.get("restore_check_timezone"))
                )
            except InvalidScheduleTimezone as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "key": "backend.errors.schedule.invalidTimezone",
                        "params": {"error": str(e)},
                    },
                )

        cron_expression = request.get("cron_expression")
        if cron_expression is not None:
            if not cron_expression or cron_expression.strip() == "":
                repo.restore_check_cron_expression = None
                repo.restore_check_schedule_enabled = False
            else:
                try:
                    calculate_next_cron_run(
                        cron_expression,
                        schedule_timezone=repo.restore_check_timezone
                        or DEFAULT_SCHEDULE_TIMEZONE,
                    )
                    repo.restore_check_cron_expression = cron_expression
                except InvalidScheduleTimezone as e:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "key": "backend.errors.schedule.invalidTimezone",
                            "params": {"error": str(e)},
                        },
                    )
                except Exception:
                    raise HTTPException(
                        status_code=400,
                        detail={"key": "backend.errors.repo.invalidCronExpression"},
                    )
                repo.restore_check_schedule_enabled = True

        # Explicit toggle (independent of cron).
        schedule_enabled = request.get("schedule_enabled")
        if schedule_enabled is not None:
            repo.restore_check_schedule_enabled = bool(schedule_enabled)

        if "paths" in request:
            repo.restore_check_paths = json.dumps(
                _normalize_restore_check_paths(request.get("paths"))
            )

        full_archive = request.get("full_archive")
        if full_archive is not None:
            repo.restore_check_full_archive = bool(full_archive)

        restore_check_mode_changed = "paths" in request or full_archive is not None
        restore_check_paths = (
            json.loads(repo.restore_check_paths) if repo.restore_check_paths else []
        )
        restore_check_enabled = bool(repo.restore_check_cron_expression)
        if restore_check_enabled:
            _ensure_restore_check_mode_allowed(
                repository=repo,
                probe_paths=restore_check_paths,
                full_archive=bool(repo.restore_check_full_archive),
            )

        if cron_expression is not None and (
            not cron_expression or cron_expression.strip() == ""
        ):
            repo.restore_check_canary_enabled = False
        elif repo.mode == "observe":
            repo.restore_check_canary_enabled = False
        elif repo.restore_check_cron_expression and (
            cron_expression is not None or restore_check_mode_changed
        ):
            repo.restore_check_canary_enabled = _is_restore_check_canary_mode(
                probe_paths=restore_check_paths,
                full_archive=bool(repo.restore_check_full_archive),
            )

        notify_on_success = request.get("notify_on_success")
        if notify_on_success is not None:
            repo.notify_on_restore_check_success = notify_on_success

        notify_on_failure = request.get("notify_on_failure")
        if notify_on_failure is not None:
            repo.notify_on_restore_check_failure = notify_on_failure

        if repo.restore_check_cron_expression and repo.restore_check_schedule_enabled:
            try:
                repo.next_scheduled_restore_check = calculate_next_cron_run(
                    repo.restore_check_cron_expression,
                    schedule_timezone=repo.restore_check_timezone
                    or DEFAULT_SCHEDULE_TIMEZONE,
                )
            except Exception as e:
                logger.error(
                    "Failed to calculate next restore check time",
                    error=str(e),
                    repo_id=repo_id,
                )
                repo.next_scheduled_restore_check = None
        else:
            repo.next_scheduled_restore_check = None

        db.commit()
        db.refresh(repo)

        restore_check_paths = (
            json.loads(repo.restore_check_paths) if repo.restore_check_paths else []
        )

        return {
            "success": True,
            "repository": {
                "id": repo.id,
                "name": repo.name,
                "restore_check_cron_expression": repo.restore_check_cron_expression,
                "restore_check_schedule_enabled": bool(
                    repo.restore_check_schedule_enabled
                ),
                "restore_check_timezone": repo.restore_check_timezone
                or DEFAULT_SCHEDULE_TIMEZONE,
                "timezone": repo.restore_check_timezone or DEFAULT_SCHEDULE_TIMEZONE,
                "restore_check_paths": restore_check_paths,
                "restore_check_full_archive": repo.restore_check_full_archive,
                "restore_check_canary_enabled": repo.restore_check_canary_enabled,
                "restore_check_mode": _get_restore_check_mode(
                    probe_paths=restore_check_paths,
                    full_archive=bool(repo.restore_check_full_archive),
                ),
                "last_restore_check": serialize_datetime(repo.last_restore_check),
                "last_scheduled_restore_check": serialize_datetime(
                    repo.last_scheduled_restore_check
                ),
                "next_scheduled_restore_check": serialize_datetime(
                    repo.next_scheduled_restore_check
                ),
                "notify_on_restore_check_success": repo.notify_on_restore_check_success,
                "notify_on_restore_check_failure": repo.notify_on_restore_check_failure,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to update restore check schedule", error=str(e), repo_id=repo_id
        )
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToUpdateRestoreCheckSchedule"},
        )


@router.get("/{repo_id}/check-schedule")
async def get_check_schedule(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get scheduled check configuration for repository"""
    try:
        repo = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repo:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.repositoryNotFound"},
            )
        _require_repository_access(db, current_user, repo, "viewer")

        cron_set = (
            repo.check_cron_expression is not None and repo.check_cron_expression != ""
        )
        return {
            "repository_id": repo.id,
            "repository_name": repo.name,
            "repository_path": repo.path,
            "check_cron_expression": repo.check_cron_expression,
            "check_schedule_enabled": bool(repo.check_schedule_enabled),
            "check_timezone": repo.check_timezone or DEFAULT_SCHEDULE_TIMEZONE,
            "timezone": repo.check_timezone or DEFAULT_SCHEDULE_TIMEZONE,
            "last_scheduled_check": serialize_datetime(repo.last_scheduled_check),
            "next_scheduled_check": serialize_datetime(repo.next_scheduled_check),
            "check_max_duration": repo.check_max_duration,
            "check_extra_flags": repo.check_extra_flags,
            "notify_on_check_success": repo.notify_on_check_success,
            "notify_on_check_failure": repo.notify_on_check_failure,
            # "enabled" means "will actually run": cron is set AND toggle is on.
            "enabled": cron_set and bool(repo.check_schedule_enabled),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get check schedule", error=str(e), repo_id=repo_id)
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToGetCheckSchedule"},
        )


@router.get("/{repo_id}/restore-check-schedule")
async def get_restore_check_schedule(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get scheduled restore verification configuration for a repository."""
    try:
        repo = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repo:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.repositoryNotFound"},
            )
        _require_repository_access(db, current_user, repo, "viewer")

        restore_check_paths = (
            json.loads(repo.restore_check_paths) if repo.restore_check_paths else []
        )

        cron_set = (
            repo.restore_check_cron_expression is not None
            and repo.restore_check_cron_expression != ""
        )
        return {
            "repository_id": repo.id,
            "repository_name": repo.name,
            "repository_path": repo.path,
            "restore_check_cron_expression": repo.restore_check_cron_expression,
            "restore_check_schedule_enabled": bool(repo.restore_check_schedule_enabled),
            "restore_check_timezone": repo.restore_check_timezone
            or DEFAULT_SCHEDULE_TIMEZONE,
            "timezone": repo.restore_check_timezone or DEFAULT_SCHEDULE_TIMEZONE,
            "restore_check_paths": restore_check_paths,
            "restore_check_full_archive": repo.restore_check_full_archive,
            "restore_check_canary_enabled": repo.restore_check_canary_enabled,
            "restore_check_mode": _get_restore_check_mode(
                probe_paths=restore_check_paths,
                full_archive=bool(repo.restore_check_full_archive),
            ),
            "last_restore_check": serialize_datetime(repo.last_restore_check),
            "last_scheduled_restore_check": serialize_datetime(
                repo.last_scheduled_restore_check
            ),
            "next_scheduled_restore_check": serialize_datetime(
                repo.next_scheduled_restore_check
            ),
            "notify_on_restore_check_success": repo.notify_on_restore_check_success,
            "notify_on_restore_check_failure": repo.notify_on_restore_check_failure,
            "enabled": cron_set and bool(repo.restore_check_schedule_enabled),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get restore check schedule", error=str(e), repo_id=repo_id
        )
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToGetRestoreCheckSchedule"},
        )
