"""Borg 2 repository endpoints — mounted at /api/v2/repositories/

Handles create (rcreate), import, info, and delete for Borg 2 repositories.
The borg2 core wrapper is the ONLY borg binary interaction here — never borg.py.
"""

import json
import os
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Any, Optional
import structlog

from app.database.database import get_db
from app.database.models import User, Repository, SystemSettings
from app.core.security import get_current_user
from app.core.features import require_feature
from app.core.borg2 import borg2, BORG2_ENCRYPTION_MODES
from app.core.borg_errors import is_lock_error
from app.services.repository_command_lock import run_serialized_repository_command
from app.services.v2.repository_service import repository_v2_service
from app.utils.fs import calculate_path_size_bytes
from app.utils.borg_env import repository_borg_env
from app.utils.archive_job_metadata import enrich_archives_with_backup_metadata
from app.utils.source_locations import legacy_source_fields, normalize_source_locations

logger = structlog.get_logger()
router = APIRouter(tags=["Repositories v2"], dependencies=[require_feature("borg_v2")])


# ── Pydantic schemas ───────────────────────────────────────────────────────────


class RepositoryV2Create(BaseModel):
    name: str
    path: str
    encryption: str = "repokey-aes-ocb"
    compression: str = "lz4"
    passphrase: Optional[str] = None
    connection_id: Optional[int] = None
    remote_path: Optional[str] = None
    source_directories: Optional[list[str]] = None
    source_locations: Optional[list[dict[str, Any]]] = None
    exclude_patterns: Optional[list[str]] = None
    mode: str = "full"
    bypass_lock: bool = False
    custom_flags: Optional[str] = None
    pre_backup_script: Optional[str] = None
    post_backup_script: Optional[str] = None
    pre_hook_timeout: int = 300
    post_hook_timeout: int = 300
    continue_on_hook_failure: bool = False
    skip_on_hook_failure: bool = False
    source_connection_id: Optional[int] = None


class RepositoryV2Import(BaseModel):
    name: str
    path: str
    encryption: str = "repokey-aes-ocb"
    passphrase: Optional[str] = None
    compression: str = "lz4"
    connection_id: Optional[int] = None
    remote_path: Optional[str] = None
    source_directories: Optional[list[str]] = None
    source_locations: Optional[list[dict[str, Any]]] = None
    exclude_patterns: Optional[list[str]] = None
    mode: str = "full"
    bypass_lock: bool = False
    custom_flags: Optional[str] = None
    pre_backup_script: Optional[str] = None
    post_backup_script: Optional[str] = None
    pre_hook_timeout: int = 300
    post_hook_timeout: int = 300
    continue_on_hook_failure: bool = False
    skip_on_hook_failure: bool = False
    source_connection_id: Optional[int] = None
    keyfile_content: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_init_timeout(db: Session) -> int:
    sys_settings = db.query(SystemSettings).first()
    if sys_settings and sys_settings.init_timeout:
        return sys_settings.init_timeout
    return 300


def _get_info_timeout(db: Session) -> int:
    sys_settings = db.query(SystemSettings).first()
    if sys_settings and sys_settings.info_timeout:
        return sys_settings.info_timeout
    return 600


def _resolve_bypass_lock(repo: Repository, db: Session, setting_name: str) -> bool:
    system_settings = db.query(SystemSettings).first()
    return bool(
        repo.bypass_lock
        or (system_settings and getattr(system_settings, setting_name, False))
    )


def _is_borg2_lock_like_failure(result: dict) -> bool:
    stderr = result.get("stderr", "") or ""
    return (
        is_lock_error(exit_code=result.get("return_code"))
        or "ObjectNotFound: locks/" in stderr
    )


def _normalize_source_payload(
    *,
    source_locations: Optional[list[dict[str, Any]]],
    source_connection_id: Optional[int],
    source_directories: Optional[list[str]],
) -> tuple[list[dict[str, Any]], Optional[int], list[str]]:
    try:
        normalized = normalize_source_locations(
            source_locations,
            source_type="remote" if source_connection_id else "local",
            source_ssh_connection_id=source_connection_id,
            source_directories=source_directories,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.repo.sourceConnectionRequired"},
        ) from exc

    if not normalized:
        return [], source_connection_id, source_directories or []

    _source_type, legacy_connection_id, flattened_paths = legacy_source_fields(
        normalized
    )
    return normalized, legacy_connection_id, flattened_paths


def _borg_keyfile_name(repo_path: str) -> str:
    """Derive a stable keyfile filename from the repository path."""
    path = (
        repo_path[len("ssh://") :]
        if repo_path.startswith("ssh://")
        else repo_path.lstrip("/")
    )
    return re.sub(r"[^a-zA-Z0-9]", "_", path)


async def _rcreate(
    path: str,
    encryption: str,
    passphrase: Optional[str],
    ssh_key_id: Optional[int],
    remote_path: Optional[str],
    init_timeout: int,
) -> dict:
    """Run borg2 rcreate with proper SSH env if needed."""
    result = await repository_v2_service.initialize_repository(
        path=path,
        encryption=encryption,
        passphrase=passphrase,
        ssh_key_id=ssh_key_id,
        remote_path=remote_path,
        init_timeout=init_timeout,
    )
    result["already_existed"] = result.get("return_code") == 2
    return result


async def _rinfo(
    path: str,
    passphrase: Optional[str],
    ssh_key_id: Optional[int],
    remote_path: Optional[str],
    timeout: int,
) -> dict:
    """Run borg2 repo-info with proper SSH env if needed."""
    return await repository_v2_service.verify_repository(
        path=path,
        passphrase=passphrase,
        ssh_key_id=ssh_key_id,
        remote_path=remote_path,
        timeout=timeout,
    )


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("/encryption-modes")
async def list_encryption_modes(current_user: User = Depends(get_current_user)):
    """Return supported encryption modes for Borg 2 repositories."""
    return {"encryption_modes": BORG2_ENCRYPTION_MODES}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_repository(
    data: RepositoryV2Create,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create and initialise a new Borg 2 repository (borg2 rcreate)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail={"key": "backend.errors.repo.adminAccessRequired"}
        )

    if data.encryption not in BORG2_ENCRYPTION_MODES:
        raise HTTPException(
            status_code=400,
            detail={
                "key": "backend.errors.repo.invalidEncryption",
                "params": {"mode": data.encryption, "valid": BORG2_ENCRYPTION_MODES},
            },
        )

    # Resolve SSH connection details if given
    ssh_key_id = None
    if data.connection_id:
        from app.database.models import SSHConnection

        conn = (
            db.query(SSHConnection)
            .filter(SSHConnection.id == data.connection_id)
            .first()
        )
        if not conn:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.sshConnectionNotFound"},
            )
        ssh_key_id = conn.ssh_key_id

    # Check for duplicate name/path
    if db.query(Repository).filter(Repository.name == data.name).first():
        raise HTTPException(
            status_code=409, detail={"key": "backend.errors.repo.nameExists"}
        )
    if db.query(Repository).filter(Repository.path == data.path).first():
        raise HTTPException(
            status_code=409, detail={"key": "backend.errors.repo.pathExists"}
        )

    init_timeout = _get_init_timeout(db)

    logger.info(
        "Initialising borg2 repository", path=data.path, encryption=data.encryption
    )
    result = await _rcreate(
        path=data.path,
        encryption=data.encryption,
        passphrase=data.passphrase,
        ssh_key_id=ssh_key_id,
        remote_path=data.remote_path,
        init_timeout=init_timeout,
    )

    if not result["success"] and not result.get("already_existed"):
        logger.error("borg2 rcreate failed", stderr=result["stderr"])
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.repo.initFailed",
                "params": {"error": result["stderr"]},
            },
        )

    (
        source_locations,
        source_connection_id,
        source_directories,
    ) = _normalize_source_payload(
        source_locations=data.source_locations,
        source_connection_id=data.source_connection_id,
        source_directories=data.source_directories,
    )
    source_dirs_json = json.dumps(source_directories) if source_directories else None
    source_locations_json = json.dumps(source_locations) if source_locations else None
    exclude_patterns_json = (
        json.dumps(data.exclude_patterns) if data.exclude_patterns else None
    )

    repo = Repository(
        name=data.name,
        path=data.path,
        encryption=data.encryption,
        compression=data.compression,
        passphrase=data.passphrase,
        source_directories=source_dirs_json,
        exclude_patterns=exclude_patterns_json,
        connection_id=data.connection_id,
        remote_path=data.remote_path,
        mode=data.mode,
        bypass_lock=data.bypass_lock,
        custom_flags=data.custom_flags,
        pre_backup_script=data.pre_backup_script,
        post_backup_script=data.post_backup_script,
        pre_hook_timeout=data.pre_hook_timeout,
        post_hook_timeout=data.post_hook_timeout,
        continue_on_hook_failure=data.continue_on_hook_failure,
        skip_on_hook_failure=data.skip_on_hook_failure,
        source_ssh_connection_id=source_connection_id,
        source_locations=source_locations_json,
        borg_version=2,
        repository_type="ssh" if data.connection_id else "local",
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)

    logger.info(
        "Borg2 repository created",
        repo_id=repo.id,
        path=repo.path,
        already_existed=result.get("already_existed"),
    )
    return {
        "id": repo.id,
        "name": repo.name,
        "path": repo.path,
        "borg_version": 2,
        "already_existed": result.get("already_existed", False),
        "message": "backend.success.repo.created",
    }


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_repository(
    data: RepositoryV2Import,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import an existing Borg 2 repository (no rcreate — repo already exists)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail={"key": "backend.errors.repo.adminAccessRequired"}
        )

    # Check for duplicate name/path
    if db.query(Repository).filter(Repository.name == data.name).first():
        raise HTTPException(
            status_code=409, detail={"key": "backend.errors.repo.nameExists"}
        )
    if db.query(Repository).filter(Repository.path == data.path).first():
        raise HTTPException(
            status_code=409, detail={"key": "backend.errors.repo.pathExists"}
        )

    # Resolve SSH connection details if given
    ssh_key_id = None
    if data.connection_id:
        from app.database.models import SSHConnection

        conn = (
            db.query(SSHConnection)
            .filter(SSHConnection.id == data.connection_id)
            .first()
        )
        if not conn:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.sshConnectionNotFound"},
            )
        ssh_key_id = conn.ssh_key_id

    keyfile_path = None
    if data.keyfile_content:
        keyfile_dir = os.path.join(os.path.expanduser("~"), ".config", "borg", "keys")
        os.makedirs(keyfile_dir, exist_ok=True)
        keyfile_path = os.path.join(keyfile_dir, _borg_keyfile_name(data.path))
        with open(keyfile_path, "w", encoding="utf-8") as f:
            f.write(data.keyfile_content)
        os.chmod(keyfile_path, 0o600)

    # Verify the repo is accessible with borg2 rinfo
    logger.info("Verifying borg2 repository exists", path=data.path)
    result = await _rinfo(
        path=data.path,
        passphrase=data.passphrase,
        ssh_key_id=ssh_key_id,
        remote_path=data.remote_path,
        timeout=_get_info_timeout(db),
    )
    if not result["success"]:
        if keyfile_path and os.path.exists(keyfile_path):
            os.unlink(keyfile_path)
        logger.error("borg2 rinfo verification failed", stderr=result["stderr"])
        raise HTTPException(
            status_code=400,
            detail={
                "key": "backend.errors.repo.verificationFailed",
                "params": {"error": result["stderr"]},
            },
        )

    (
        source_locations,
        source_connection_id,
        source_directories,
    ) = _normalize_source_payload(
        source_locations=data.source_locations,
        source_connection_id=data.source_connection_id,
        source_directories=data.source_directories,
    )
    source_dirs_json = json.dumps(source_directories) if source_directories else None
    source_locations_json = json.dumps(source_locations) if source_locations else None
    exclude_patterns_json = (
        json.dumps(data.exclude_patterns) if data.exclude_patterns else None
    )

    repo = Repository(
        name=data.name,
        path=data.path,
        encryption=data.encryption,
        compression=data.compression,
        passphrase=data.passphrase,
        source_directories=source_dirs_json,
        exclude_patterns=exclude_patterns_json,
        connection_id=data.connection_id,
        remote_path=data.remote_path,
        mode=data.mode,
        bypass_lock=data.bypass_lock,
        custom_flags=data.custom_flags,
        pre_backup_script=data.pre_backup_script,
        post_backup_script=data.post_backup_script,
        pre_hook_timeout=data.pre_hook_timeout,
        post_hook_timeout=data.post_hook_timeout,
        continue_on_hook_failure=data.continue_on_hook_failure,
        skip_on_hook_failure=data.skip_on_hook_failure,
        source_ssh_connection_id=source_connection_id,
        source_locations=source_locations_json,
        has_keyfile=bool(keyfile_path),
        borg_version=2,
        repository_type="ssh" if data.connection_id else "local",
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)

    logger.info("Borg2 repository imported", repo_id=repo.id, path=repo.path)
    return {
        "id": repo.id,
        "name": repo.name,
        "path": repo.path,
        "borg_version": 2,
        "message": "backend.success.repo.imported",
    }


@router.get("/{repo_id}/info")
async def get_repository_info(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get Borg 2 repository-level information via borg2 rinfo."""

    async def _operation():
        repo = (
            db.query(Repository)
            .filter(Repository.id == repo_id, Repository.borg_version == 2)
            .first()
        )
        if not repo:
            raise HTTPException(
                status_code=404, detail={"key": "backend.errors.repo.notFound"}
            )

        info_timeout = _get_info_timeout(db)
        bypass_lock = _resolve_bypass_lock(repo, db, "bypass_lock_on_info")
        with repository_borg_env(repo, db) as env:
            result = await borg2.info_repo(
                repository=repo.path,
                passphrase=repo.passphrase,
                remote_path=repo.remote_path,
                bypass_lock=bypass_lock,
                timeout=info_timeout,
                env=env,
            )
        if (
            not result["success"]
            and not bypass_lock
            and _is_borg2_lock_like_failure(result)
        ):
            logger.warning(
                "Retrying borg2 info_repo with bypass lock after lock-like failure",
                repo_id=repo.id,
                path=repo.path,
            )
            with repository_borg_env(repo, db) as env:
                result = await borg2.info_repo(
                    repository=repo.path,
                    passphrase=repo.passphrase,
                    remote_path=repo.remote_path,
                    bypass_lock=True,
                    timeout=info_timeout,
                    env=env,
                )
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail={
                    "key": "backend.errors.repo.infoFailed",
                    "params": {"error": result["stderr"]},
                },
            )

        try:
            info_data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            info_data = {"raw": result["stdout"]}

        # borg2 info --json has per-archive original_size but no repo-level disk usage.
        # borg2 repo-info --json has cache.path only — no cache.stats like borg1.
        # Pull repository/encryption metadata from rinfo, then compute disk usage separately.
        with repository_borg_env(repo, db) as env:
            rinfo_result = await borg2.rinfo(
                repository=repo.path,
                passphrase=repo.passphrase,
                remote_path=repo.remote_path,
                env=env,
            )
        if rinfo_result["success"]:
            try:
                rinfo_data = json.loads(rinfo_result["stdout"])
                if rinfo_data.get("repository") and not info_data.get("repository"):
                    info_data["repository"] = rinfo_data["repository"]
                if rinfo_data.get("encryption") and not info_data.get("encryption"):
                    info_data["encryption"] = rinfo_data["encryption"]
            except json.JSONDecodeError:
                pass

        # For local repos compute actual on-disk size via du (borg2 has no JSON equivalent).
        # Remote repos (SSH/SFTP) get no rinfo_stats — frontend treats missing as unavailable.
        is_local = repo.path.startswith("/") and not repo.host
        if is_local:
            try:
                disk_bytes = await calculate_path_size_bytes([repo.path], timeout=30)
                if disk_bytes > 0:
                    info_data["rinfo_stats"] = {
                        "unique_csize": disk_bytes,
                        "unique_size": disk_bytes,
                    }
            except Exception:
                pass

        return {"info": info_data, "borg_version": 2}

    return await run_serialized_repository_command(repo_id, _operation)


@router.get("/{repo_id}/archives")
async def list_archives(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all archives in a Borg 2 repository."""

    async def _operation():
        repo = (
            db.query(Repository)
            .filter(Repository.id == repo_id, Repository.borg_version == 2)
            .first()
        )
        if not repo:
            raise HTTPException(
                status_code=404, detail={"key": "backend.errors.repo.notFound"}
            )

        from app.database.models import SystemSettings

        system_settings = db.query(SystemSettings).first()
        bypass_lock = repo.bypass_lock or (
            system_settings and system_settings.bypass_lock_on_list
        )

        with repository_borg_env(repo, db) as env:
            result = await borg2.list_archives(
                repo.path,
                passphrase=repo.passphrase,
                remote_path=repo.remote_path,
                bypass_lock=bypass_lock,
                env=env,
            )
        if not result["success"]:
            raise HTTPException(
                status_code=500,
                detail={
                    "key": "backend.errors.repo.listFailed",
                    "params": {"error": result["stderr"]},
                },
            )

        try:
            data = json.loads(result.get("stdout", "{}"))
        except json.JSONDecodeError:
            data = {}

        archives = enrich_archives_with_backup_metadata(
            data.get("archives", []), repo, db
        )
        return {"archives": archives, "borg_version": 2}

    return await run_serialized_repository_command(repo_id, _operation)


@router.get("/{repo_id}/stats")
async def get_repository_stats(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get storage statistics for a Borg 2 repository via borg2 rinfo."""
    repo = (
        db.query(Repository)
        .filter(Repository.id == repo_id, Repository.borg_version == 2)
        .first()
    )
    if not repo:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.repo.notFound"}
        )

    info_timeout = _get_info_timeout(db)
    with repository_borg_env(repo, db) as env:
        result = await borg2.rinfo(
            repository=repo.path,
            passphrase=repo.passphrase,
            remote_path=repo.remote_path,
            bypass_lock=_resolve_bypass_lock(repo, db, "bypass_lock_on_info"),
            timeout=info_timeout,
            env=env,
        )
    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.repo.infoFailed",
                "params": {"error": result["stderr"]},
            },
        )

    try:
        stats_data = json.loads(result["stdout"])
    except json.JSONDecodeError:
        stats_data = {}

    return {"stats": stats_data, "borg_version": 2}
