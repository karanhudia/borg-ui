from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timezone
from types import SimpleNamespace
import structlog
import os
import asyncio
import json

from app.database.database import get_db, SessionLocal
from app.database.models import (
    User,
    Repository,
    AgentMachine,
    CheckJob,
    CompactJob,
    PruneJob,
    RestoreCheckJob,
    ScheduledJob,
    ScheduledJobRepository,
    SystemSettings,
    UserRepositoryPermission,
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
    ensure_no_running_job,
)
from app.core.authorization import authorize_request
from app.core.security import get_current_user, check_repo_access, decrypt_secret
from app.core.borg import BorgInterface
from app.core.borg_router import BorgRouter
from app.core.borg_errors import is_lock_error
from app.core.features import FEATURES, get_current_plan, plan_includes
from app.config import settings
from app.services.mqtt_service import mqtt_service
from app.services.restore_check_service import restore_check_service
from app.services.repository_command_lock import run_serialized_repository_command
from app.utils.datetime_utils import serialize_datetime
from app.utils.schedule_time import (
    DEFAULT_SCHEDULE_TIMEZONE,
    InvalidScheduleTimezone,
    calculate_next_cron_run,
    normalize_schedule_timezone,
)
from app.utils.archive_job_metadata import enrich_archives_with_backup_metadata
from app.utils.ssh_paths import apply_ssh_command_prefix
from app.utils.borg_env import (
    get_standard_ssh_opts as shared_get_standard_ssh_opts,
    setup_borg_env as shared_setup_borg_env,
    cleanup_temp_key_file,
)
from app.utils.ssh_utils import (
    resolve_repo_ssh_key_file,
)  # Backward-compatible patch target for tests

logger = structlog.get_logger()
router = APIRouter(tags=["repositories"], dependencies=[Depends(authorize_request)])

V2_ONLY_ENCRYPTION_MODES = {
    "repokey-aes-ocb",
    "repokey-chacha20-poly1305",
    "keyfile-aes-ocb",
    "keyfile-chacha20-poly1305",
}

# Initialize Borg interface
borg = BorgInterface()


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
    }


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


# Helper function to format datetime with timezone
def format_datetime(dt):
    """Format datetime to ISO8601 with UTC timezone indicator"""
    return serialize_datetime(dt)


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
    source_connection_id: Optional[int] = (
        None  # SSH connection ID for remote data source (pull-based backups)
    )
    execution_target: str = "local"  # local, ssh, agent
    agent_machine_id: Optional[int] = None  # Agent that executes backups


class RepositoryImport(BaseModel):
    name: str
    borg_version: Optional[int] = 1
    path: str
    encryption: str = "none"
    passphrase: Optional[str] = None  # Required if repository is encrypted
    compression: str = "lz4"  # Default compression for future backups
    source_directories: Optional[List[str]] = None  # List of directories to backup
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
    source_connection_id: Optional[int] = (
        None  # SSH connection ID for remote data source (pull-based backups)
    )
    keyfile_content: Optional[str] = (
        None  # Content of borg keyfile for keyfile/keyfile-blake2 encryption
    )
    execution_target: str = "local"  # local, ssh, agent
    agent_machine_id: Optional[int] = None  # Agent that executes backups


class RepositoryUpdate(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    compression: Optional[str] = None
    source_directories: Optional[List[str]] = None
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
    source_connection_id: Optional[int] = (
        None  # SSH connection ID for remote data source
    )
    execution_target: Optional[str] = None  # local, ssh, agent
    agent_machine_id: Optional[int] = None  # Agent that executes backups


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
    if agent.status in ("disabled", "revoked"):
        raise HTTPException(
            status_code=409,
            detail={"key": "backend.errors.agents.agentNotQueueable"},
        )
    return agent


def _validate_agent_repository_payload(
    repo_data: Union[RepositoryCreate, RepositoryImport], db: Session
) -> AgentMachine:
    if repo_data.mode == "full" and not repo_data.source_directories:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.atLeastOneSourceDirRequired"},
        )

    if repo_data.encryption in [
        "repokey",
        "keyfile",
        "repokey-blake2",
        "keyfile-blake2",
        "repokey-aes-ocb",
        "repokey-chacha20-poly1305",
        "keyfile-aes-ocb",
        "keyfile-chacha20-poly1305",
    ]:
        if not repo_data.passphrase or repo_data.passphrase.strip() == "":
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.repo.encryptedPassphraseRequired",
                    "params": {"mode": repo_data.encryption},
                },
            )

    return _require_queueable_agent(repo_data.agent_machine_id, db)


def _create_agent_repository_record(
    repo_data: Union[RepositoryCreate, RepositoryImport],
    current_user: User,
    db: Session,
    *,
    imported: bool,
):
    agent = _validate_agent_repository_payload(repo_data, db)
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

    source_directories_json = (
        json.dumps(repo_data.source_directories)
        if repo_data.source_directories
        else None
    )
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
        connection_id=repo_data.connection_id,
        remote_path=repo_data.remote_path,
        repository_type="ssh" if repo_path.startswith("ssh://") else "local",
        execution_target="agent",
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
        source_ssh_connection_id=None,
        borg_version=repo_data.borg_version or 1,
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)

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

    return {
        "success": True,
        "message": "backend.success.repo.repositoryImported"
        if imported
        else "backend.success.repo.repositoryCreated",
        "repository": {
            "id": repository.id,
            "name": repository.name,
            "path": repository.path,
            "encryption": repository.encryption,
            "compression": repository.compression,
            "execution_target": repository.execution_target,
            "agent_machine_id": repository.agent_machine_id,
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

            repo_list.append(
                {
                    "id": repo.id,
                    "name": repo.name,
                    "path": repo.path,
                    "encryption": repo.encryption,
                    "compression": repo.compression,
                    "source_directories": _decode_json_list_field(
                        repo.source_directories
                    ),
                    "exclude_patterns": _decode_json_list_field(repo.exclude_patterns),
                    "repository_type": repo.repository_type,
                    "execution_target": repo.execution_target or "local",
                    "agent_machine_id": repo.agent_machine_id,
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
            )

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
        if _uses_borg2_payload(repo_data):
            if _normalize_execution_target(repo_data.execution_target) == "agent":
                return _create_agent_repository_record(
                    repo_data, current_user, db, imported=False
                )
            _require_borg2_feature(db)
            from app.api.v2.repositories import (
                RepositoryV2Create,
                create_repository as create_repository_v2,
            )

            v2_payload = RepositoryV2Create(**repo_data.model_dump(exclude_none=True))
            return await create_repository_v2(v2_payload, current_user, db)

        if _normalize_execution_target(repo_data.execution_target) == "agent":
            return _create_agent_repository_record(
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
                detail={"key": "backend.errors.repo.failedToInitializeRepository"},
            )

        # Serialize source directories as JSON
        source_directories_json = None
        if repo_data.source_directories:
            source_directories_json = json.dumps(repo_data.source_directories)

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
            source_ssh_connection_id=repo_data.source_connection_id,
            execution_target=_normalize_execution_target(repo_data.execution_target),
            agent_machine_id=None,
        )

        db.add(repository)
        db.commit()
        db.refresh(repository)

        if repo_data.encryption in ["keyfile", "keyfile-blake2"]:
            repository.has_keyfile = True
            db.commit()

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

        return {
            "success": True,
            "message": message,
            "already_existed": already_existed,
            "repository": {
                "id": repository.id,
                "name": repository.name,
                "path": repository.path,
                "encryption": repository.encryption,
                "compression": repository.compression,
            },
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
        if _uses_borg2_payload(repo_data):
            if _normalize_execution_target(repo_data.execution_target) == "agent":
                return _create_agent_repository_record(
                    repo_data, current_user, db, imported=True
                )
            _require_borg2_feature(db)
            from app.api.v2.repositories import (
                RepositoryV2Import,
                import_repository as import_repository_v2,
            )

            v2_payload = RepositoryV2Import(**repo_data.model_dump(exclude_none=True))
            return await import_repository_v2(v2_payload, current_user, db)

        if _normalize_execution_target(repo_data.execution_target) == "agent":
            return _create_agent_repository_record(
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

        # Serialize source directories as JSON
        source_directories_json = None
        if repo_data.source_directories:
            source_directories_json = json.dumps(repo_data.source_directories)

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
            source_ssh_connection_id=repo_data.source_connection_id,
            execution_target=_normalize_execution_target(repo_data.execution_target),
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
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to import repository", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.failedToImportRepository"},
        )


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

        return {
            "success": True,
            "repository": {
                "id": repository.id,
                "name": repository.name,
                "path": repository.path,
                "encryption": repository.encryption,
                "compression": repository.compression,
                "execution_target": repository.execution_target or "local",
                "agent_machine_id": repository.agent_machine_id,
                "last_backup": format_datetime(repository.last_backup),
                "total_size": repository.total_size,
                "archive_count": repository.archive_count,
                "created_at": format_datetime(repository.created_at),
                "updated_at": format_datetime(repository.updated_at),
                "has_keyfile": repository.has_keyfile or False,
                "source_ssh_connection_id": repository.source_ssh_connection_id,
                "stats": stats,
            },
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
        if repo_data.path is not None:
            raw_path = repo_data.path.strip()

        # Handle connection_id - allow null to clear (switch to local)
        if "connection_id" in repo_data.model_dump(exclude_unset=True):
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
        if raw_path is not None or "connection_id" in repo_data.model_dump(
            exclude_unset=True
        ):
            # Determine the final connection_id (use updated value or existing)
            final_connection_id = (
                repo_data.connection_id
                if "connection_id" in repo_data.model_dump(exclude_unset=True)
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
                                detail={
                                    "key": "backend.errors.repo.failedToInitializeRepository"
                                },
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
                            detail={
                                "key": "backend.errors.repo.failedToInitializeRepository"
                            },
                        )

                    logger.info(
                        "Successfully initialized borg repository at new path after verification failure",
                        new_path=repository.path,
                        borg_version=repository.borg_version or 1,
                    )

        if repo_data.compression is not None:
            repository.compression = repo_data.compression

        if repo_data.source_directories is not None:
            repository.source_directories = (
                json.dumps(repo_data.source_directories)
                if repo_data.source_directories
                else None
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

        if repo_data.execution_target is not None:
            execution_target = _normalize_execution_target(repo_data.execution_target)
            if execution_target == "agent":
                agent = _require_queueable_agent(repo_data.agent_machine_id, db)
                repository.execution_target = "agent"
                repository.agent_machine_id = agent.id
                repository.source_ssh_connection_id = None
            else:
                repository.execution_target = execution_target
                repository.agent_machine_id = None

        elif "agent_machine_id" in repo_data.model_dump(exclude_unset=True):
            if (repository.execution_target or "local") != "agent":
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.repo.invalidExecutionTarget"},
                )
            agent = _require_queueable_agent(repo_data.agent_machine_id, db)
            repository.agent_machine_id = agent.id

        # Update source_connection_id - allow null to clear the field
        # The frontend always sends this field explicitly (either with value or null)
        # If not provided in the request body at all, Pydantic sets it to None (default)
        # Since we can't distinguish "not provided" from "provided as null" with current setup,
        # and the frontend wizard always sends this field, we check if it's in the request
        if "source_connection_id" in repo_data.model_dump(exclude_unset=True):
            if (repository.execution_target or "local") == "agent":
                repository.source_ssh_connection_id = None
            else:
                repository.source_ssh_connection_id = repo_data.source_connection_id

        repository.updated_at = datetime.utcnow()
        db.commit()

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

        check_job = start_background_maintenance_job(
            db,
            repository,
            CheckJob,
            error_key="backend.errors.repo.checkAlreadyRunning",
            dispatcher=lambda job,
            router_repo=SimpleNamespace(
                id=repository.id,
                borg_version=repository.borg_version,
            ): BorgRouter(router_repo).check(job.id),
            extra_fields={"max_duration": max_duration},
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
        compact_job = start_background_maintenance_job(
            db,
            repository,
            CompactJob,
            error_key="backend.errors.repo.compactAlreadyRunning",
            dispatcher=lambda job,
            router_repo=SimpleNamespace(
                id=repository.id,
                borg_version=repository.borg_version,
            ): BorgRouter(router_repo).compact(job.id),
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
        ensure_no_running_job(
            db,
            PruneJob,
            repo_id,
            error_key="backend.errors.repo.pruneAlreadyRunning",
        )

        # Extract retention policy from request
        keep_hourly = request.get("keep_hourly", 0)
        keep_daily = request.get("keep_daily", 7)
        keep_weekly = request.get("keep_weekly", 4)
        keep_monthly = request.get("keep_monthly", 6)
        keep_quarterly = request.get("keep_quarterly", 0)
        keep_yearly = request.get("keep_yearly", 1)
        dry_run = request.get("dry_run", False)

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
        await BorgRouter(repository).prune(
            prune_job.id,
            keep_hourly,
            keep_daily,
            keep_weekly,
            keep_monthly,
            keep_quarterly,
            keep_yearly,
            dry_run,
        )

        # Refresh job to get updated status and logs
        db.refresh(prune_job)

        # Read log file if it exists
        stdout_output = read_job_logs(prune_job, fallback_to_logs=True)
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
            "-i",
            temp_key_file,
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
) -> Dict[str, Any]:
    """Initialize a new Borg repository"""
    logger.info(
        "Starting repository initialization",
        path=path,
        encryption=encryption,
        has_passphrase=bool(passphrase),
        ssh_key_id=ssh_key_id,
        remote_path=remote_path,
    )
    repo_for_routing = SimpleNamespace(
        path=path,
        encryption=encryption,
        passphrase=passphrase,
        remote_path=remote_path,
        borg_version=1,
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
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.repositoryNotFound"},
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


@router.post("/{repository_id}/break-lock")
async def break_repository_lock(
    repository_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Break a stale lock on a repository

    Use this when a backup has crashed or been killed, leaving behind a lock file
    that prevents new backups from starting.

    WARNING: Only use this if you're CERTAIN no backup is currently running!
    """
    try:
        # Get repository from database
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.repositoryNotFound"},
            )
        _require_repository_access(db, current_user, repository, "operator")

        logger.info(
            "Breaking repository lock",
            repository=repository.path,
            user=current_user.username,
            repository_id=repository_id,
        )

        cmd = BorgRouter(repository).build_break_lock_command(
            repository_path=repository.path,
            remote_path=repository.remote_path,
        )

        returncode, stdout, stderr = await _run_repository_command(
            repository,
            db,
            cmd,
            30,
            log_message="Using SSH key for break-lock",
            log_fields={"repository_id": repository_id},
        )

        stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

        if returncode == 0:
            logger.info(
                "Successfully broke repository lock",
                repository=repository.path,
                user=current_user.username,
            )
            return {
                "success": True,
                "message": "backend.success.repo.lockRemoved",
                "repository": repository.path,
                "output": stdout_str,
            }
        else:
            logger.error(
                "Failed to break repository lock",
                repository=repository.path,
                returncode=returncode,
                stderr=stderr_str,
            )
            raise HTTPException(
                status_code=500, detail={"key": "backend.errors.repo.failedToBreakLock"}
            )

    except asyncio.TimeoutError:
        logger.error("Timeout breaking repository lock", repository_id=repository_id)
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.breakLockTimeout"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error breaking repository lock", repository_id=repository_id, error=str(e)
        )
        raise HTTPException(
            status_code=500, detail={"key": "backend.errors.repo.failedToBreakLock"}
        )


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
        return serialize_job_status(job, include_progress=True, include_logs=True)
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
        return {
            "jobs": [
                {
                    **serialize_job_summary(
                        job, include_progress=True, include_has_logs=True
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
            job, include_progress=True, include_logs=True, include_has_logs=True
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
        return {
            "jobs": [
                (
                    lambda probe_paths: {
                        **serialize_job_summary(
                            job, include_progress=True, include_has_logs=True
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
        return serialize_job_status(job, include_progress=True, include_logs=True)
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
        return {
            "jobs": [serialize_job_summary(job, include_progress=True) for job in jobs]
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
        return serialize_job_status(job, include_logs=True)
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
        return {
            "jobs": [serialize_job_summary(job, include_has_logs=True) for job in jobs]
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
            .filter(CheckJob.repository_id == repo_id, CheckJob.status == "running")
            .first()
        )

        compact_job = (
            db.query(CompactJob)
            .filter(CompactJob.repository_id == repo_id, CompactJob.status == "running")
            .first()
        )

        prune_job = (
            db.query(PruneJob)
            .filter(PruneJob.repository_id == repo_id, PruneJob.status == "running")
            .first()
        )

        restore_check_job = (
            db.query(RestoreCheckJob)
            .filter(
                RestoreCheckJob.repository_id == repo_id,
                RestoreCheckJob.status == "running",
            )
            .first()
        )

        result = {
            "has_running_jobs": bool(
                check_job or compact_job or prune_job or restore_check_job
            ),
            "check_job": {
                "id": check_job.id,
                "progress": check_job.progress,
                "progress_message": check_job.progress_message,
                "started_at": serialize_datetime(check_job.started_at),
            }
            if check_job
            else None,
            "compact_job": {
                "id": compact_job.id,
                "progress": compact_job.progress,
                "progress_message": compact_job.progress_message,
                "started_at": serialize_datetime(compact_job.started_at),
            }
            if compact_job
            else None,
            "prune_job": {
                "id": prune_job.id,
                "started_at": serialize_datetime(prune_job.started_at),
            }
            if prune_job
            else None,
            "restore_check_job": {
                "id": restore_check_job.id,
                "progress": restore_check_job.progress,
                "progress_message": restore_check_job.progress_message,
                "started_at": serialize_datetime(restore_check_job.started_at),
            }
            if restore_check_job
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
