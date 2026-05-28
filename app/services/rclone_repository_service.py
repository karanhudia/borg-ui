from __future__ import annotations

import os
import shlex
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import Repository, RepositoryStorage, RcloneRemote
from app.services.repository_executor import (
    queue_agent_repository_operation_job,
    wait_for_agent_repository_operation_job,
)
from app.services.rclone_service import RcloneService, rclone_service


VALID_SYNC_POLICIES = {"after_success", "manual", "scheduled"}
SYNC_DIRECTION_CACHE_TO_REMOTE = "cache_to_remote"
SYNC_DIRECTION_PRIMARY_TO_REMOTE = "primary_to_remote"
SYNC_DIRECTION_SSHFS_TO_REMOTE = "sshfs_mount_to_remote"
SYNC_DIRECTION_AGENT_TO_REMOTE = "agent_to_remote"


def normalize_rclone_relative_path(value: str) -> str:
    normalized = "/".join(part for part in value.strip().split("/") if part)
    if not normalized:
        raise ValueError("rclone remote path is required")
    if value.strip().startswith("/") or normalized.startswith("../"):
        raise ValueError("rclone remote path must be relative")
    if any(part == ".." for part in normalized.split("/")):
        raise ValueError("rclone remote path cannot traverse directories")
    if ":" in normalized.split("/", 1)[0]:
        raise ValueError("rclone remote path must not include a remote prefix")
    return normalized


def normalize_extra_flags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part for part in shlex.split(value) if part]
    if isinstance(value, list):
        return [str(part) for part in value if str(part).strip()]
    raise ValueError("rclone extra flags must be a list or string")


class RcloneRepositoryService:
    def __init__(
        self,
        *,
        cache_root: str | None = None,
        service: RcloneService | None = None,
        ssh_mount_service: Any | None = None,
    ):
        self.cache_root = cache_root or settings.rclone_cache_root
        self.service = service or rclone_service
        self.ssh_mount_service = ssh_mount_service

    def derive_cache_path(self, repository_id: int) -> str:
        return str(Path(self.cache_root) / "repositories" / str(repository_id))

    def compose_target(self, remote: RcloneRemote, relative_path: str) -> str:
        return f"{remote.name}:{normalize_rclone_relative_path(relative_path)}"

    def serialize_status(
        self,
        repository: Repository,
        storage: RepositoryStorage,
        remote: RcloneRemote | None,
    ) -> dict[str, Any]:
        return {
            "repository_id": repository.id,
            "backend": storage.backend,
            "rclone_remote_id": storage.rclone_remote_id,
            "rclone_remote_name": remote.name if remote else None,
            "rclone_remote_path": storage.rclone_remote_path,
            "rclone_target": self.compose_target(remote, storage.rclone_remote_path)
            if remote and storage.rclone_remote_path
            else None,
            "cache_path": storage.cache_path,
            "cache_present": self._cache_present(storage),
            "sync_policy": storage.sync_policy,
            "sync_direction": storage.sync_direction,
            "sync_status": storage.sync_status,
            "last_synced_at": _iso(storage.last_synced_at),
            "last_hydrated_at": _iso(storage.last_hydrated_at),
            "last_remote_check_at": _iso(storage.last_remote_check_at),
            "last_sync_error": storage.last_sync_error,
            "extra_flags": storage.extra_flags or [],
        }

    def get_storage(self, db: Session, repository_id: int) -> RepositoryStorage:
        storage = (
            db.query(RepositoryStorage)
            .filter(RepositoryStorage.repository_id == repository_id)
            .first()
        )
        if not storage or storage.backend != "rclone":
            raise ValueError("repository is not rclone-backed")
        return storage

    def get_remote(self, db: Session, storage: RepositoryStorage) -> RcloneRemote:
        remote = (
            db.query(RcloneRemote)
            .filter(RcloneRemote.id == storage.rclone_remote_id)
            .first()
        )
        if not remote:
            raise ValueError("rclone remote not found")
        return remote

    def build_storage(
        self,
        *,
        repository_id: int,
        remote_id: int,
        remote_path: str,
        sync_policy: str = "after_success",
        extra_flags: Any = None,
    ) -> RepositoryStorage:
        if sync_policy not in VALID_SYNC_POLICIES:
            raise ValueError("invalid rclone sync policy")
        return RepositoryStorage(
            repository_id=repository_id,
            backend="rclone",
            rclone_remote_id=remote_id,
            rclone_remote_path=normalize_rclone_relative_path(remote_path),
            cache_path=self.derive_cache_path(repository_id),
            sync_policy=sync_policy,
            sync_status="pending",
            extra_flags=normalize_extra_flags(extra_flags),
        )

    def build_mirror_storage(
        self,
        *,
        repository_id: int,
        source_path: str,
        source_backend: str = "local",
        remote_id: int,
        remote_path: str,
        sync_policy: str = "after_success",
        extra_flags: Any = None,
    ) -> RepositoryStorage:
        if sync_policy not in VALID_SYNC_POLICIES:
            raise ValueError("invalid rclone sync policy")
        normalized_source = str(source_path).strip()
        if not normalized_source:
            raise ValueError("repository path is required for cloud mirror")
        source_backend = (source_backend or "local").strip().lower()
        if source_backend == "ssh":
            cache_path = None
            sync_direction = SYNC_DIRECTION_SSHFS_TO_REMOTE
        elif source_backend == "agent":
            cache_path = None
            sync_direction = SYNC_DIRECTION_AGENT_TO_REMOTE
        else:
            cache_path = normalized_source
            sync_direction = SYNC_DIRECTION_PRIMARY_TO_REMOTE
        return RepositoryStorage(
            repository_id=repository_id,
            backend="rclone",
            rclone_remote_id=remote_id,
            rclone_remote_path=normalize_rclone_relative_path(remote_path),
            cache_path=cache_path,
            sync_policy=sync_policy,
            sync_direction=sync_direction,
            sync_status="pending",
            extra_flags=normalize_extra_flags(extra_flags),
        )

    def _cache_present(self, storage: RepositoryStorage) -> bool:
        if storage.sync_direction in {
            SYNC_DIRECTION_SSHFS_TO_REMOTE,
            SYNC_DIRECTION_AGENT_TO_REMOTE,
        }:
            return True
        if not storage.cache_path:
            return False
        return os.path.isdir(storage.cache_path)

    def _get_ssh_mount_service(self):
        if self.ssh_mount_service is not None:
            return self.ssh_mount_service
        from app.services.mount_service import mount_service

        return mount_service

    def _ssh_repository_remote_path(self, repository: Repository) -> str:
        source = (repository.path or "").strip()
        if not source:
            raise ValueError("SSH repository path is required for cloud mirror")
        if source.startswith("ssh://"):
            parsed = urlparse(source)
            return parsed.path or "/"
        return source

    async def _mount_ssh_repository_source(
        self, repository: Repository
    ) -> tuple[str, str, Any]:
        if not repository.connection_id:
            raise ValueError("SSH cloud mirror requires a stored SSH connection")
        remote_path = self._ssh_repository_remote_path(repository)
        mount_service = self._get_ssh_mount_service()
        _temp_root, mount_id = await mount_service.mount_ssh_directory(
            repository.connection_id, remote_path
        )
        mount_info = mount_service.active_mounts.get(mount_id)
        mount_point = getattr(mount_info, "mount_point", None)
        if not mount_point:
            await mount_service.unmount(mount_id, force=True)
            raise ValueError("SSH cloud mirror mount did not return a mount point")
        return mount_point, mount_id, mount_service

    def _agent_rclone_config(self, remote: RcloneRemote) -> dict[str, str]:
        values = dict(remote.redacted_config or {})
        values["type"] = str(values.get("type") or remote.provider).strip()
        return {
            str(key): _stringify_config_value(value)
            for key, value in values.items()
            if value is not None and str(key).strip()
        }

    async def _sync_agent_repository_source(
        self,
        db: Session,
        repository: Repository,
        storage: RepositoryStorage,
        remote: RcloneRemote,
        *,
        timeout: int,
    ):
        agent_job = queue_agent_repository_operation_job(
            db,
            repository,
            job_kind="repository.rclone_sync",
            operation={
                "rclone": {
                    "source_path": repository.path,
                    "remote_name": remote.name,
                    "remote_path": storage.rclone_remote_path,
                    "config": self._agent_rclone_config(remote),
                    "extra_flags": storage.extra_flags or [],
                }
            },
        )
        result = await wait_for_agent_repository_operation_job(
            db,
            agent_job.id,
            timeout_seconds=timeout,
        )
        result_payload = result if isinstance(result, dict) else {}
        success = result_payload.get("success")
        if success is None:
            return_code = result_payload.get(
                "return_code",
                result_payload.get("exit_code", result_payload.get("code", 1)),
            )
            success = return_code == 0
        return SimpleNamespace(
            success=bool(success),
            stdout=str(result_payload.get("stdout", "")),
            stderr=str(result_payload.get("stderr", "")),
        )

    async def preflight_remote_path(
        self,
        remote: RcloneRemote,
        relative_path: str,
        *,
        verified_non_empty: bool = False,
        timeout: int = 60,
    ) -> None:
        target = self.compose_target(remote, relative_path)
        try:
            entries = await self.service.lsjson(target, timeout=timeout)
        except Exception as exc:
            message = _exception_message(exc)
            lowered = message.lower()
            not_found_markers = (
                "not found",
                "not exist",
                "doesn't exist",
                "directory not found",
                "object not found",
            )
            if any(marker in lowered for marker in not_found_markers):
                return
            raise ValueError(f"unable to verify rclone remote path: {message}") from exc

        if entries and not verified_non_empty:
            raise ValueError(
                "rclone remote path is not empty; browse the target path before syncing"
            )

    async def sync_repository(
        self,
        db: Session,
        repository: Repository,
        *,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        storage = self.get_storage(db, repository.id)
        remote = self.get_remote(db, storage)
        target = self.compose_target(remote, storage.rclone_remote_path)
        storage.sync_status = "syncing"
        storage.last_sync_error = None
        db.commit()
        mount_id = None
        mount_service = None
        try:
            source = storage.cache_path
            if storage.sync_direction == SYNC_DIRECTION_AGENT_TO_REMOTE:
                result = await self._sync_agent_repository_source(
                    db,
                    repository,
                    storage,
                    remote,
                    timeout=timeout or settings.rclone_sync_timeout,
                )
            elif storage.sync_direction == SYNC_DIRECTION_SSHFS_TO_REMOTE:
                (
                    source,
                    mount_id,
                    mount_service,
                ) = await self._mount_ssh_repository_source(repository)
                if not source:
                    raise ValueError("rclone sync source path is not available")
                result = await self.service.sync(
                    source,
                    target,
                    timeout=timeout or settings.rclone_sync_timeout,
                    extra_flags=storage.extra_flags or [],
                )
            else:
                if not source:
                    raise ValueError("rclone sync source path is not available")
                result = await self.service.sync(
                    source,
                    target,
                    timeout=timeout or settings.rclone_sync_timeout,
                    extra_flags=storage.extra_flags or [],
                )
        except Exception as exc:
            storage.sync_status = "failed"
            storage.last_sync_error = _exception_message(exc)
            db.commit()
            return self.serialize_status(repository, storage, remote)
        finally:
            if mount_id and mount_service:
                try:
                    await mount_service.unmount(mount_id, force=True)
                except Exception:
                    pass
        now = datetime.now(timezone.utc)
        if result.success:
            storage.sync_status = "current"
            storage.last_synced_at = now
            storage.last_sync_error = None
        else:
            storage.sync_status = "failed"
            storage.last_sync_error = result.stderr or "rclone sync failed"
        db.commit()
        return self.serialize_status(repository, storage, remote)

    async def hydrate_repository(
        self,
        db: Session,
        repository: Repository,
        *,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        storage = self.get_storage(db, repository.id)
        remote = self.get_remote(db, storage)
        target = self.compose_target(remote, storage.rclone_remote_path)
        parent = Path(storage.cache_path).parent
        parent.mkdir(parents=True, exist_ok=True)
        temp_dir = tempfile.mkdtemp(
            prefix=f".hydrate-{repository.id}-", dir=str(parent)
        )
        storage.sync_status = "hydrating"
        storage.last_sync_error = None
        db.commit()
        try:
            result = await self.service.sync(
                target,
                temp_dir,
                timeout=timeout or settings.rclone_hydrate_timeout,
                extra_flags=storage.extra_flags or [],
            )
        except Exception as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            storage.sync_status = "failed"
            storage.last_sync_error = _exception_message(exc)
            db.commit()
            return self.serialize_status(repository, storage, remote)
        now = datetime.now(timezone.utc)
        if result.success:
            try:
                if os.path.exists(storage.cache_path):
                    shutil.rmtree(storage.cache_path)
                os.replace(temp_dir, storage.cache_path)
                repository.path = storage.cache_path
                storage.sync_status = "current"
                storage.last_hydrated_at = now
                storage.last_sync_error = None
            except Exception as exc:
                shutil.rmtree(temp_dir, ignore_errors=True)
                storage.sync_status = "failed"
                storage.last_sync_error = _exception_message(exc)
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)
            storage.sync_status = "failed"
            storage.last_sync_error = result.stderr or "rclone hydrate failed"
        db.commit()
        return self.serialize_status(repository, storage, remote)


def _iso(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _exception_message(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        message = detail.get("message") or detail.get("key")
        if message:
            return str(message)
    if isinstance(detail, str) and detail:
        return detail
    return str(exc) or exc.__class__.__name__


def _stringify_config_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, separators=(",", ":"))
    return str(value)


rclone_repository_service = RcloneRepositoryService()
