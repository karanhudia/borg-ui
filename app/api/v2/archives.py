"""Borg 2 archive endpoints — mounted at /api/v2/archives/

Mirrors the shape of api/archives.py but uses borg2 exclusively.
All routes accept a `repository` query param (the repo path).
"""

import json
import os
import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import structlog

from app.api.archive_download import extract_file_download
from app.database.database import get_db
from app.database.models import User, Repository, DeleteArchiveJob
from app.core.security import get_current_user, get_current_download_user
from app.core.features import require_feature
from app.core.borg2 import borg2
from app.services.cache_service import archive_cache
from app.utils.borg_env import repository_borg_env

logger = structlog.get_logger()
router = APIRouter(tags=["Archives v2"], dependencies=[require_feature("borg_v2")])

ARCHIVE_ID_RE = re.compile(r"^[0-9a-fA-F]{16,}$")


def _repo_needs_custom_env(repo: Repository) -> bool:
    return bool(
        getattr(repo, "repository_type", None) == "ssh"
        or getattr(repo, "connection_id", None)
        or str(getattr(repo, "path", "")).startswith("ssh://")
    )


def _get_v2_repo(repository: str, db: Session) -> Repository:
    """Resolve and validate a Borg 2 repository by ID or path.

    BorgApiClient sends the integer ID as a string; legacy callers may send
    the repository path. Both are supported.
    """
    repo = None
    try:
        repo_id = int(repository)
        repo = (
            db.query(Repository)
            .filter(Repository.id == repo_id, Repository.borg_version == 2)
            .first()
        )
    except (ValueError, TypeError):
        pass

    if repo is None:
        repo = (
            db.query(Repository)
            .filter(Repository.path == repository, Repository.borg_version == 2)
            .first()
        )

    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.restore.repositoryNotFound"},
        )
    return repo


async def _resolve_archive_name(repo: Repository, archive_ref: str, db: Session) -> str:
    """Resolve an archive route parameter to the actual Borg archive name.

    The frontend may pass either the archive name or the archive ID/hash. Borg 2
    commands such as `list` are most reliable when given the real archive name.
    """
    if not archive_ref:
        return archive_ref

    # Fast path for normal archive names.
    if not ARCHIVE_ID_RE.fullmatch(archive_ref):
        return archive_ref

    if _repo_needs_custom_env(repo):
        with repository_borg_env(repo, db) as env:
            result = await borg2.list_archives(
                repo.path,
                passphrase=repo.passphrase,
                remote_path=repo.remote_path,
                bypass_lock=repo.bypass_lock,
                env=env,
            )
    else:
        result = await borg2.list_archives(
            repo.path,
            passphrase=repo.passphrase,
            remote_path=repo.remote_path,
            bypass_lock=repo.bypass_lock,
        )
    if not result["success"]:
        return archive_ref

    try:
        payload = json.loads(result["stdout"])
        archives = payload.get("archives", [])
    except Exception:
        return archive_ref

    for archive in archives:
        if archive.get("id") == archive_ref:
            return archive.get("name") or archive_ref
        if archive.get("name") == archive_ref:
            return archive_ref

    return archive_ref


def _get_archive_selector(archive_ref: str) -> str:
    if not archive_ref:
        return archive_ref
    if archive_ref.startswith("aid:"):
        return archive_ref
    if ARCHIVE_ID_RE.fullmatch(archive_ref):
        return f"aid:{archive_ref}"
    return archive_ref


def _get_browse_cache_key(archive_ref: str, path: str) -> str:
    archive_key = _get_archive_selector(archive_ref)
    normalized_path = path.strip("/")
    if not normalized_path:
        return archive_key
    return f"{archive_key}::path::{normalized_path}"


def _get_archive_root_depth(repo: Repository) -> int:
    if not repo.source_directories:
        return 1
    try:
        source_directories = json.loads(repo.source_directories)
    except (json.JSONDecodeError, TypeError):
        return 1

    depths = []
    for source_dir in source_directories:
        if not isinstance(source_dir, str):
            continue
        parts = [part for part in source_dir.strip("/").split("/") if part]
        if parts:
            depths.append(len(parts))

    return min(depths) if depths else 1


def _get_browse_depth(repo: Repository, path: str) -> int:
    normalized_path = path.strip("/")
    path_depth = len([part for part in normalized_path.split("/") if part])
    return _get_archive_root_depth(repo) + path_depth


# ── List archives ──────────────────────────────────────────────────────────────


@router.get("/list")
async def list_archives(
    repository: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List archives in a Borg 2 repository."""
    repo = _get_v2_repo(repository, db)
    if _repo_needs_custom_env(repo):
        with repository_borg_env(repo, db) as env:
            result = await borg2.list_archives(
                repo.path,
                passphrase=repo.passphrase,
                remote_path=repo.remote_path,
                bypass_lock=repo.bypass_lock,
                env=env,
            )
    else:
        result = await borg2.list_archives(
            repo.path,
            passphrase=repo.passphrase,
            remote_path=repo.remote_path,
            bypass_lock=repo.bypass_lock,
        )
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list archives: {result['stderr']}",
        )
    return {"archives": result["stdout"]}


# ── Archive info ───────────────────────────────────────────────────────────────


@router.get("/{archive_id}/info")
async def get_archive_info(
    repository: str,
    archive_id: str,
    include_files: bool = False,
    file_limit: int = 1000,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get detailed information about a Borg 2 archive."""
    repo = _get_v2_repo(repository, db)
    archive_selector = _get_archive_selector(archive_id)
    if _repo_needs_custom_env(repo):
        with repository_borg_env(repo, db) as env:
            result = await borg2.info_archive(
                repo.path,
                archive_selector,
                passphrase=repo.passphrase,
                remote_path=repo.remote_path,
                bypass_lock=repo.bypass_lock,
                env=env,
            )
    else:
        result = await borg2.info_archive(
            repo.path,
            archive_selector,
            passphrase=repo.passphrase,
            remote_path=repo.remote_path,
            bypass_lock=repo.bypass_lock,
        )
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get archive info: {result['stderr']}",
        )

    try:
        archive_data = json.loads(result["stdout"])
        archives = archive_data.get("archives", [])
        archive_info = archives[0] if archives else {}

        enhanced_info = {
            "name": archive_info.get("name"),
            "id": archive_info.get("id"),
            "start": archive_info.get("start"),
            "end": archive_info.get("end"),
            "duration": archive_info.get("duration"),
            "stats": archive_info.get("stats", {}),
            "command_line": archive_info.get("command_line", []),
            "hostname": archive_info.get("hostname"),
            "username": archive_info.get("username"),
            "chunker_params": archive_info.get("chunker_params"),
            "limits": archive_info.get("limits", {}),
            "comment": archive_info.get("comment", ""),
            "repository": archive_data.get("repository", {}),
            "encryption": archive_data.get("encryption", {}),
            "cache": archive_data.get("cache", {}),
        }

        if include_files:
            if _repo_needs_custom_env(repo):
                with repository_borg_env(repo, db) as env:
                    list_result = await borg2.list_archive_contents(
                        repo.path,
                        archive_selector,
                        passphrase=repo.passphrase,
                        remote_path=repo.remote_path,
                        bypass_lock=repo.bypass_lock,
                        env=env,
                    )
            else:
                list_result = await borg2.list_archive_contents(
                    repo.path,
                    archive_selector,
                    passphrase=repo.passphrase,
                    remote_path=repo.remote_path,
                    bypass_lock=repo.bypass_lock,
                )
            if list_result["success"]:
                files = []
                for line in list_result["stdout"].strip().split("\n"):
                    if line and len(files) < file_limit:
                        try:
                            f = json.loads(line)
                            files.append(
                                {
                                    "path": f.get("path"),
                                    "type": f.get("type"),
                                    "mode": f.get("mode"),
                                    "user": f.get("user"),
                                    "group": f.get("group"),
                                    "size": f.get("size"),
                                    "mtime": f.get("mtime"),
                                    "healthy": f.get("healthy", True),
                                }
                            )
                        except json.JSONDecodeError:
                            continue
                enhanced_info["files"] = files
                enhanced_info["file_count"] = len(files)
            else:
                enhanced_info["files"] = []
                enhanced_info["file_count"] = 0

        return {"info": enhanced_info}
    except json.JSONDecodeError:
        return {"info": result["stdout"]}


# ── Archive contents ───────────────────────────────────────────────────────────


@router.get("/{archive_id}/contents")
async def get_archive_contents(
    repository: str,
    archive_id: str,
    path: str = "",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get contents of a Borg 2 archive, filtered to `path`.

    Returns {"items": [...]} matching the v1 /browse/ response shape so
    ArchiveContentsDialog works without version branching.
    """
    repo = _get_v2_repo(repository, db)
    archive_selector = _get_archive_selector(archive_id)
    cache_key = _get_browse_cache_key(archive_id, path)

    cached_items = await archive_cache.get(repo.id, cache_key)
    if cached_items is not None:
        logger.info(
            "Using cached borg2 archive contents",
            repository_id=repo.id,
            archive=archive_selector,
            path=path,
            items_count=len(cached_items),
        )
        return {"items": cached_items}

    if _repo_needs_custom_env(repo):
        with repository_borg_env(repo, db) as env:
            result = await borg2.list_archive_contents(
                repo.path,
                archive_selector,
                path=path,
                passphrase=repo.passphrase,
                remote_path=repo.remote_path,
                bypass_lock=repo.bypass_lock,
                browse_depth=_get_browse_depth(repo, path),
                env=env,
            )
    else:
        result = await borg2.list_archive_contents(
            repo.path,
            archive_selector,
            path=path,
            passphrase=repo.passphrase,
            remote_path=repo.remote_path,
            bypass_lock=repo.bypass_lock,
            browse_depth=_get_browse_depth(repo, path),
        )
    # borg2 list exits with 1 on warnings but stdout is still valid JSONL —
    # treat any result that produced stdout as usable.
    stdout = result.get("stdout", "")
    logger.info(
        "borg2 list_archive_contents result",
        archive=archive_selector,
        path=path,
        return_code=result.get("return_code"),
        success=result.get("success"),
        stdout_len=len(stdout),
        stderr=result.get("stderr", "")[:200],
    )
    if not stdout and not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get archive contents: {result.get('stderr', 'unknown error')}",
        )

    # Parse ALL entries first (needed for recursive directory size calculation)
    all_items = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry_path = entry.get("path", "").strip("/")
        if not entry_path:
            continue
        all_items.append(
            {
                "path": entry_path,
                "type": entry.get("type", ""),
                "size": entry.get("size", 0) or 0,
                "mtime": entry.get("mtime", ""),
            }
        )

    def calculate_directory_size(dir_path: str) -> int:
        """Sum sizes of all files recursively under dir_path."""
        total = 0
        prefix = f"{dir_path}/"
        for item in all_items:
            item_path = item["path"]
            if item_path.startswith(prefix) or item_path == dir_path:
                if item["type"] != "d" and item["size"]:
                    total += item["size"]
        return total

    # Filter items for the requested path and build the response
    base_path = path.strip("/")
    items = []
    seen_dirs: set = set()

    for item in all_items:
        item_path = item["path"]

        if base_path:
            if item_path == base_path:
                continue  # skip the directory itself
            if not item_path.startswith(base_path + "/"):
                continue
            relative = item_path[len(base_path) + 1 :]
        else:
            relative = item_path

        parts = relative.split("/")
        if not parts or not parts[0]:
            continue

        if len(parts) == 1:
            # Direct child
            if item_path in seen_dirs:
                continue
            seen_dirs.add(item_path)
            entry_type = item["type"]
            is_dir = entry_type == "d"
            if is_dir:
                items.append(
                    {
                        "name": parts[0],
                        "path": item_path,
                        "size": calculate_directory_size(item_path),
                        "type": "directory",
                        "mtime": item["mtime"],
                    }
                )
            else:
                items.append(
                    {
                        "name": parts[0],
                        "path": item_path,
                        "size": item["size"],
                        "type": "file",
                        "mtime": item["mtime"],
                    }
                )
        else:
            # Deeper descendant — surface the intermediate directory once
            dir_name = parts[0]
            dir_path = (base_path + "/" + dir_name).strip("/")
            if dir_path not in seen_dirs:
                seen_dirs.add(dir_path)
                items.append(
                    {
                        "name": dir_name,
                        "path": dir_path,
                        "size": calculate_directory_size(dir_path),
                        "type": "directory",
                        "mtime": "",
                    }
                )

    cache_success = await archive_cache.set(repo.id, cache_key, items)
    if cache_success:
        logger.info(
            "Cached borg2 archive contents",
            repository_id=repo.id,
            archive=archive_selector,
            path=path,
            items_count=len(items),
        )
    else:
        logger.warning(
            "Failed to cache borg2 archive contents",
            repository_id=repo.id,
            archive=archive_selector,
            path=path,
            items_count=len(items),
        )

    return {"items": items}


# ── Delete archive ─────────────────────────────────────────────────────────────


@router.delete("/{archive_id}")
async def delete_archive(
    repository: str,
    archive_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a Borg 2 archive (non-blocking background job).

    Space is NOT freed immediately in Borg 2 — a compact() call is required.
    The scheduled compact after prune/delete handles this automatically.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail={"key": "backend.errors.archives.adminAccessRequired"},
        )

    repo = _get_v2_repo(repository, db)
    archive_name = await _resolve_archive_name(repo, archive_id, db)

    running_job = (
        db.query(DeleteArchiveJob)
        .filter(
            DeleteArchiveJob.repository_id == repo.id,
            DeleteArchiveJob.archive_name == archive_name,
            DeleteArchiveJob.status == "running",
        )
        .first()
    )
    if running_job:
        raise HTTPException(
            status_code=409,
            detail={
                "key": "backend.errors.archives.deleteAlreadyRunning",
                "params": {"jobId": running_job.id},
            },
        )

    delete_job = DeleteArchiveJob(
        repository_id=repo.id,
        repository_path=repo.path,
        archive_name=archive_name,
        status="pending",
    )
    db.add(delete_job)
    db.commit()
    db.refresh(delete_job)

    from app.services.v2.delete_archive_service import delete_archive_v2_service

    asyncio.create_task(
        delete_archive_v2_service.execute_delete(
            delete_job.id, repo.id, archive_name, None
        )
    )

    logger.info(
        "Borg2 delete archive job created",
        job_id=delete_job.id,
        repository_id=repo.id,
        archive=archive_name,
    )
    return {
        "job_id": delete_job.id,
        "status": "pending",
        "message": "backend.success.archives.deletionStarted",
        "note": "compact required to free space",
    }


# ── Download file from archive ─────────────────────────────────────────────────


@router.get("/download")
async def download_file_from_archive(
    repository: str,
    archive: str,
    file_path: str,
    current_user: User = Depends(get_current_download_user),
    db: Session = Depends(get_db),
):
    """Extract and download a specific file from a Borg 2 archive."""
    repo = _get_v2_repo(repository, db)
    archive_selector = _get_archive_selector(archive)
    try:

        async def extract(temp_dir: str):
            if _repo_needs_custom_env(repo):
                with repository_borg_env(repo, db) as env:
                    return await borg2.extract_archive(
                        repo.path,
                        archive_selector,
                        [file_path],
                        temp_dir,
                        passphrase=repo.passphrase,
                        remote_path=repo.remote_path,
                        bypass_lock=repo.bypass_lock,
                        env=env,
                    )
            return await borg2.extract_archive(
                repo.path,
                archive_selector,
                [file_path],
                temp_dir,
                passphrase=repo.passphrase,
                remote_path=repo.remote_path,
                bypass_lock=repo.bypass_lock,
            )

        return await extract_file_download(file_path, extract)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to download file: {str(e)}"
        )


# ── Delete job status ──────────────────────────────────────────────────────────


@router.get("/delete-jobs/{job_id}")
async def get_delete_job_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get status of a Borg 2 archive delete job."""
    job = db.query(DeleteArchiveJob).filter(DeleteArchiveJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.archives.deleteJobNotFound"}
        )

    logs = None
    if job.log_file_path and os.path.exists(job.log_file_path):
        try:
            with open(job.log_file_path) as f:
                logs = f.read()
        except Exception:
            pass

    return {
        "id": job.id,
        "repository_id": job.repository_id,
        "archive_name": job.archive_name,
        "status": job.status,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "progress": job.progress,
        "progress_message": job.progress_message,
        "error_message": job.error_message,
        "logs": logs,
        "has_logs": job.has_logs,
    }
