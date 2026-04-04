"""Borg 2 repository endpoints — mounted at /api/v2/repositories/

Handles create (rcreate), import, info, and delete for Borg 2 repositories.
The borg2 core wrapper is the ONLY borg binary interaction here — never borg.py.
"""

import asyncio
import json
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import structlog

from app.database.database import get_db, SessionLocal
from app.database.models import User, Repository, SystemSettings
from app.core.security import get_current_user, decrypt_secret
from app.core.features import require_feature
from app.core.borg2 import borg2, BORG2_ENCRYPTION_MODES
from app.config import settings
from app.utils.fs import calculate_path_size_bytes

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


class RepositoryV2Import(BaseModel):
    name: str
    path: str
    encryption: str = "repokey-aes-ocb"
    passphrase: Optional[str] = None
    compression: str = "lz4"
    connection_id: Optional[int] = None
    remote_path: Optional[str] = None
    source_directories: Optional[list[str]] = None
    exclude_patterns: Optional[list[str]] = None
    mode: str = "full"
    bypass_lock: bool = False


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


def _get_ssh_key_rsh(ssh_key_id: int, path: str) -> Optional[str]:
    """Decrypt and write SSH key to a temp file; return (BORG_RSH value, temp_path).

    Returns None if no key is needed (local repo or no key ID).
    Caller is responsible for deleting the temp file.
    """
    if not ssh_key_id or not path.startswith("ssh://"):
        return None, None

    from app.database.models import SSHKey

    db = SessionLocal()
    try:
        ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_key_id).first()
        if not ssh_key:
            raise ValueError(f"SSH key {ssh_key_id} not found")

        private_key = decrypt_secret(ssh_key.private_key)
    finally:
        db.close()

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(private_key)
        temp_path = f.name
    os.chmod(temp_path, 0o600)

    ssh_opts = [
        "-i", temp_path,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", "RequestTTY=no",
        "-o", "PermitLocalCommand=no",
    ]
    return f"ssh {' '.join(ssh_opts)}", temp_path


async def _rcreate(path: str, encryption: str, passphrase: Optional[str],
                   ssh_key_id: Optional[int], remote_path: Optional[str],
                   init_timeout: int) -> dict:
    """Run borg2 rcreate with proper SSH env if needed."""
    borg_rsh, temp_key_file = _get_ssh_key_rsh(ssh_key_id, path)
    try:
        env = {}
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase
        env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
        env["BORG_RELOCATED_REPO_ACCESS_IS_OK"] = "yes"
        if borg_rsh:
            env["BORG_RSH"] = borg_rsh

        cmd = [borg2.borg_cmd, "-r", path, "repo-create", "--encryption", encryption]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])

        exec_env = os.environ.copy()
        exec_env.update(env)
        exec_env["BORG_LOCK_WAIT"] = "20"
        exec_env["BORG_HOSTNAME_IS_UNIQUE"] = "yes"

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=exec_env,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=init_timeout)
        return_code = process.returncode
        return {
            "success": return_code == 0,
            "return_code": return_code,
            "stdout": stdout.decode() if stdout else "",
            "stderr": stderr.decode() if stderr else "",
            "already_existed": return_code == 2,
        }
    finally:
        if temp_key_file and os.path.exists(temp_key_file):
            os.unlink(temp_key_file)


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
        raise HTTPException(status_code=403, detail={"key": "backend.errors.repo.adminAccessRequired"})

    if data.encryption not in BORG2_ENCRYPTION_MODES:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.invalidEncryption",
                    "params": {"mode": data.encryption, "valid": BORG2_ENCRYPTION_MODES}},
        )

    # Resolve SSH connection details if given
    ssh_key_id = None
    if data.connection_id:
        from app.database.models import SSHConnection
        conn = db.query(SSHConnection).filter(SSHConnection.id == data.connection_id).first()
        if not conn:
            raise HTTPException(status_code=404, detail={"key": "backend.errors.repo.sshConnectionNotFound"})
        ssh_key_id = conn.ssh_key_id

    # Check for duplicate name/path
    if db.query(Repository).filter(Repository.name == data.name).first():
        raise HTTPException(status_code=409, detail={"key": "backend.errors.repo.nameExists"})
    if db.query(Repository).filter(Repository.path == data.path).first():
        raise HTTPException(status_code=409, detail={"key": "backend.errors.repo.pathExists"})

    init_timeout = _get_init_timeout(db)

    logger.info("Initialising borg2 repository", path=data.path, encryption=data.encryption)
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
            detail={"key": "backend.errors.repo.initFailed", "params": {"error": result["stderr"]}},
        )

    source_dirs_json = json.dumps(data.source_directories) if data.source_directories else None
    exclude_patterns_json = json.dumps(data.exclude_patterns) if data.exclude_patterns else None

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
        borg_version=2,
        repository_type="ssh" if data.connection_id else "local",
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)

    logger.info("Borg2 repository created", repo_id=repo.id, path=repo.path,
                already_existed=result.get("already_existed"))
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
        raise HTTPException(status_code=403, detail={"key": "backend.errors.repo.adminAccessRequired"})

    # Check for duplicate name/path
    if db.query(Repository).filter(Repository.name == data.name).first():
        raise HTTPException(status_code=409, detail={"key": "backend.errors.repo.nameExists"})
    if db.query(Repository).filter(Repository.path == data.path).first():
        raise HTTPException(status_code=409, detail={"key": "backend.errors.repo.pathExists"})

    # Verify the repo is accessible with borg2 rinfo
    logger.info("Verifying borg2 repository exists", path=data.path)
    result = await borg2.rinfo(
        repository=data.path,
        passphrase=data.passphrase,
        remote_path=data.remote_path,
    )
    if not result["success"]:
        logger.error("borg2 rinfo verification failed", stderr=result["stderr"])
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.repo.verificationFailed",
                    "params": {"error": result["stderr"]}},
        )

    source_dirs_json = json.dumps(data.source_directories) if data.source_directories else None
    exclude_patterns_json = json.dumps(data.exclude_patterns) if data.exclude_patterns else None

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
    repo = db.query(Repository).filter(
        Repository.id == repo_id, Repository.borg_version == 2
    ).first()
    if not repo:
        raise HTTPException(status_code=404, detail={"key": "backend.errors.repo.notFound"})

    info_timeout = _get_info_timeout(db)
    result = await borg2.info_repo(
        repository=repo.path,
        passphrase=repo.passphrase,
        remote_path=repo.remote_path,
        bypass_lock=repo.bypass_lock,
        timeout=info_timeout,
    )
    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.infoFailed", "params": {"error": result["stderr"]}},
        )

    try:
        info_data = json.loads(result["stdout"])
    except json.JSONDecodeError:
        info_data = {"raw": result["stdout"]}

    # borg2 info --json has per-archive original_size but no repo-level disk usage.
    # borg2 repo-info --json has cache.path only — no cache.stats like borg1.
    # Pull repository/encryption metadata from rinfo, then compute disk usage separately.
    rinfo_result = await borg2.rinfo(
        repository=repo.path,
        passphrase=repo.passphrase,
        remote_path=repo.remote_path,
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
                info_data["rinfo_stats"] = {"unique_csize": disk_bytes, "unique_size": disk_bytes}
        except Exception:
            pass

    return {"info": info_data, "borg_version": 2}


@router.get("/{repo_id}/archives")
async def list_archives(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all archives in a Borg 2 repository."""
    repo = db.query(Repository).filter(
        Repository.id == repo_id, Repository.borg_version == 2
    ).first()
    if not repo:
        raise HTTPException(status_code=404, detail={"key": "backend.errors.repo.notFound"})

    from app.database.models import SystemSettings
    system_settings = db.query(SystemSettings).first()
    bypass_lock = repo.bypass_lock or (system_settings and system_settings.bypass_lock_on_list)

    result = await borg2.list_archives(
        repo.path,
        passphrase=repo.passphrase,
        remote_path=repo.remote_path,
        bypass_lock=bypass_lock,
    )
    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.listFailed", "params": {"error": result["stderr"]}},
        )

    try:
        data = json.loads(result.get("stdout", "{}"))
    except json.JSONDecodeError:
        data = {}

    return {"archives": data.get("archives", []), "borg_version": 2}


@router.get("/{repo_id}/stats")
async def get_repository_stats(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get storage statistics for a Borg 2 repository via borg2 rinfo."""
    repo = db.query(Repository).filter(
        Repository.id == repo_id, Repository.borg_version == 2
    ).first()
    if not repo:
        raise HTTPException(status_code=404, detail={"key": "backend.errors.repo.notFound"})

    info_timeout = _get_info_timeout(db)
    result = await borg2.rinfo(
        repository=repo.path,
        passphrase=repo.passphrase,
        remote_path=repo.remote_path,
        bypass_lock=repo.bypass_lock,
        timeout=info_timeout,
    )
    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail={"key": "backend.errors.repo.infoFailed", "params": {"error": result["stderr"]}},
        )

    try:
        stats_data = json.loads(result["stdout"])
    except json.JSONDecodeError:
        stats_data = {}

    return {"stats": stats_data, "borg_version": 2}
