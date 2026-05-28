from __future__ import annotations

import os
import shlex
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import Repository, RepositoryStorage, RcloneRemote
from app.services.rclone_service import RcloneService, rclone_service


VALID_SYNC_POLICIES = {"after_success", "manual", "scheduled"}


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
    ):
        self.cache_root = cache_root or settings.rclone_cache_root
        self.service = service or rclone_service

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
            "cache_present": bool(
                storage.cache_path and os.path.isdir(storage.cache_path)
            ),
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
        return RepositoryStorage(
            repository_id=repository_id,
            backend="rclone",
            rclone_remote_id=remote_id,
            rclone_remote_path=normalize_rclone_relative_path(remote_path),
            cache_path=normalized_source,
            sync_policy=sync_policy,
            sync_direction="primary_to_remote",
            sync_status="pending",
            extra_flags=normalize_extra_flags(extra_flags),
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
        try:
            result = await self.service.sync(
                storage.cache_path,
                target,
                timeout=timeout or settings.rclone_sync_timeout,
                extra_flags=storage.extra_flags or [],
            )
        except Exception as exc:
            storage.sync_status = "failed"
            storage.last_sync_error = _exception_message(exc)
            db.commit()
            return self.serialize_status(repository, storage, remote)
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
    return str(exc) or exc.__class__.__name__


rclone_repository_service = RcloneRepositoryService()
