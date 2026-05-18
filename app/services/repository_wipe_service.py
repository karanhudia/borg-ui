import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.borg_router import BorgRouter
from app.database.database import SessionLocal
from app.database.models import (
    BackupJob,
    CheckJob,
    CompactJob,
    DeleteArchiveJob,
    PruneJob,
    Repository,
    RepositoryWipeJob,
    RestoreCheckJob,
    RestoreJob,
    User,
)
from app.services.repository_command_lock import run_serialized_repository_command
from app.utils.borg_env import build_repository_borg_env, cleanup_temp_key_file
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()

RUNNING_STATUSES = ("pending", "running")
TERMINAL_EXECUTION_STATUSES = {
    "completed",
    "completed_compaction_failed",
    "completed_with_warnings",
    "failed",
    "failed_partial",
    "cancelled",
}


class WipeArchiveSetChanged(Exception):
    """Raised when execution no longer matches the previewed archive set."""


class WipeValidationError(Exception):
    """Raised when an execution request fails confirmation validation."""

    def __init__(self, detail_key: str, *, status_code: int = 400):
        self.detail_key = detail_key
        self.status_code = status_code
        super().__init__(detail_key)


def _archive_display_name(archive: dict[str, Any]) -> str:
    value = archive.get("name") or archive.get("archive") or archive.get("id")
    return str(value) if value is not None else ""


def normalize_archive_manifest(
    *, borg_version: int, archives: list[Any]
) -> list[dict[str, Any]]:
    """Return a stable, secret-free archive manifest for fingerprinting/UI."""
    manifest: list[dict[str, Any]] = []
    for archive in archives:
        if not isinstance(archive, dict):
            archive = {"name": str(archive)}

        identity_value = (
            archive.get("id")
            if borg_version == 2
            else archive.get("name") or archive.get("archive")
        )
        if identity_value is None:
            identity_value = archive.get("name") or archive.get("archive")
        if identity_value is None:
            raise ValueError("Archive identity is missing")

        tags = archive.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]

        manifest.append(
            {
                "identity": str(identity_value),
                "name": _archive_display_name(archive),
                "time": archive.get("time") or archive.get("start"),
                "id": archive.get("id"),
                "protected": "@PROT" in tags,
            }
        )
    return manifest


def compute_archive_fingerprint(manifest: list[dict[str, Any]]) -> str:
    """Compute a stable fingerprint over the archive identity set only."""
    canonical = [
        {"identity": str(item["identity"])}
        for item in sorted(manifest, key=lambda value: str(value["identity"]))
    ]
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decode_json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _command_output(result: dict[str, Any]) -> str:
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    return "\n".join(part for part in [stdout, stderr] if part)


def _partial_delete_signal(output: str) -> bool:
    lowered = output.lower()
    return any(
        marker in lowered
        for marker in (
            "deleting archive",
            "deleted data",
            "would delete",
            "archive deleted",
        )
    )


class RepositoryWipeService:
    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_no_conflicting_operations(
        self,
        db: Session,
        repository: Repository,
        *,
        exclude_wipe_job_id: int | None = None,
    ) -> None:
        repo_id = repository.id
        running_by_repository_id = [
            (BackupJob, "backend.errors.repo.operationAlreadyRunning"),
            (CheckJob, "backend.errors.repo.operationAlreadyRunning"),
            (CompactJob, "backend.errors.repo.operationAlreadyRunning"),
            (PruneJob, "backend.errors.repo.operationAlreadyRunning"),
            (RestoreCheckJob, "backend.errors.repo.operationAlreadyRunning"),
            (DeleteArchiveJob, "backend.errors.repo.operationAlreadyRunning"),
        ]

        for model, error_key in running_by_repository_id:
            if (
                db.query(model)
                .filter(
                    model.repository_id == repo_id, model.status.in_(RUNNING_STATUSES)
                )
                .first()
            ):
                raise HTTPException(status_code=409, detail={"key": error_key})

        if (
            db.query(RestoreJob)
            .filter(
                RestoreJob.repository == repository.path,
                RestoreJob.status.in_(RUNNING_STATUSES),
            )
            .first()
        ):
            raise HTTPException(
                status_code=409,
                detail={"key": "backend.errors.repo.operationAlreadyRunning"},
            )

        wipe_query = db.query(RepositoryWipeJob).filter(
            RepositoryWipeJob.repository_id == repo_id,
            RepositoryWipeJob.status.in_(RUNNING_STATUSES),
        )
        if exclude_wipe_job_id is not None:
            wipe_query = wipe_query.filter(RepositoryWipeJob.id != exclude_wipe_job_id)
        if wipe_query.first():
            raise HTTPException(
                status_code=409,
                detail={"key": "backend.errors.repo.wipeAlreadyRunning"},
            )

    async def create_preview(
        self,
        db: Session,
        repository: Repository,
        current_user: User,
        *,
        run_compact: bool = True,
    ) -> dict[str, Any]:
        async def operation() -> dict[str, Any]:
            self._ensure_no_conflicting_operations(db, repository)
            temp_key_file = None
            try:
                env, temp_key_file = build_repository_borg_env(
                    repository, db, keepalive=True
                )
                router = BorgRouter(repository)
                archives = await router.list_archives(env=env)
                manifest = normalize_archive_manifest(
                    borg_version=repository.borg_version or 1,
                    archives=archives,
                )
                fingerprint = compute_archive_fingerprint(manifest)
                protected_archives = [
                    item["name"] or item["identity"]
                    for item in manifest
                    if item.get("protected")
                ]
                blocking_reason = "protected_archives" if protected_archives else None
                dry_run_output = ""
                if manifest and not blocking_reason:
                    dry_run_result = await router.run_wipe_delete(dry_run=True, env=env)
                    dry_run_output = _command_output(dry_run_result)
                    if not dry_run_result.get("success"):
                        blocking_reason = "dry_run_failed"

                job = RepositoryWipeJob(
                    repository_id=repository.id,
                    repository_path=repository.path,
                    repository_name=repository.name,
                    borg_version=repository.borg_version or 1,
                    status="previewed",
                    phase="preview",
                    archive_count=len(manifest),
                    archive_fingerprint=fingerprint,
                    archive_manifest_json=json.dumps(manifest, sort_keys=True),
                    dry_run_output=dry_run_output,
                    blocking_reason=blocking_reason,
                    protected_archives_json=json.dumps(protected_archives),
                    run_compact=bool(run_compact),
                    requested_by_user_id=current_user.id,
                    progress=0,
                    progress_message="Wipe preview generated",
                )
                db.add(job)
                db.commit()
                db.refresh(job)
                logger.info(
                    "Repository wipe preview generated",
                    repository_id=repository.id,
                    job_id=job.id,
                    archive_count=len(manifest),
                    blocked=bool(blocking_reason),
                    actor=current_user.username,
                )
                return self.serialize_job(job, include_preview=True)
            finally:
                cleanup_temp_key_file(temp_key_file)

        return await run_serialized_repository_command(
            repository.id, operation, scope="wipe"
        )

    async def start_execution(
        self,
        db: Session,
        repository: Repository,
        current_user: User,
        *,
        preview_id: int,
        preview_fingerprint: str,
        confirmation_phrase: str,
        understood: bool,
        run_compact: bool,
    ) -> RepositoryWipeJob:
        preview = (
            db.query(RepositoryWipeJob)
            .filter(
                RepositoryWipeJob.id == preview_id,
                RepositoryWipeJob.repository_id == repository.id,
            )
            .first()
        )
        if not preview:
            raise WipeValidationError(
                "backend.errors.repo.wipePreviewNotFound", status_code=404
            )
        if preview.status != "previewed":
            raise WipeValidationError(
                "backend.errors.repo.wipePreviewNotFresh", status_code=409
            )
        if preview.blocking_reason:
            raise WipeValidationError(
                "backend.errors.repo.wipePreviewBlocked", status_code=409
            )
        if not understood:
            raise WipeValidationError("backend.errors.repo.wipeUnderstandingRequired")
        expected_phrase = f"WIPE {repository.name}"
        if confirmation_phrase != expected_phrase:
            raise WipeValidationError("backend.errors.repo.wipeConfirmationMismatch")
        if preview.archive_fingerprint != preview_fingerprint:
            raise WipeValidationError(
                "backend.errors.repo.wipePreviewNotFresh", status_code=409
            )

        async def operation() -> RepositoryWipeJob:
            self._ensure_no_conflicting_operations(
                db, repository, exclude_wipe_job_id=preview.id
            )
            temp_key_file = None
            try:
                env, temp_key_file = build_repository_borg_env(
                    repository, db, keepalive=True
                )
                current_archives = await BorgRouter(repository).list_archives(env=env)
                current_manifest = normalize_archive_manifest(
                    borg_version=repository.borg_version or 1,
                    archives=current_archives,
                )
                current_fingerprint = compute_archive_fingerprint(current_manifest)
            finally:
                cleanup_temp_key_file(temp_key_file)

            if current_fingerprint != preview_fingerprint:
                preview.phase = "stale"
                db.commit()
                raise WipeArchiveSetChanged()

            preview.status = "pending"
            preview.phase = "queued"
            preview.confirmed_by_user_id = current_user.id
            preview.confirmed_at = datetime.utcnow()
            preview.run_compact = bool(run_compact)
            preview.progress = 0
            preview.progress_message = "Repository wipe queued"
            db.commit()
            db.refresh(preview)
            logger.warning(
                "Repository wipe execution queued",
                repository_id=repository.id,
                job_id=preview.id,
                archive_count=preview.archive_count,
                run_compact=bool(run_compact),
                actor=current_user.username,
            )
            return preview

        return await run_serialized_repository_command(
            repository.id, operation, scope="wipe"
        )

    async def execute_wipe(self, job_id: int, repository_id: int) -> None:
        db = SessionLocal()
        close_db = getattr(SessionLocal, "return_value", None) is not db
        temp_key_file = None
        log_lines: list[str] = []
        job: RepositoryWipeJob | None = None
        try:
            job = (
                db.query(RepositoryWipeJob)
                .filter(RepositoryWipeJob.id == job_id)
                .first()
            )
            repository = (
                db.query(Repository).filter(Repository.id == repository_id).first()
            )
            if not job or not repository:
                return

            async def operation() -> None:
                nonlocal temp_key_file, log_lines
                env, temp_key_file = build_repository_borg_env(
                    repository, db, keepalive=True, show_progress=True
                )
                router = BorgRouter(repository)

                job.status = "running"
                job.phase = "delete"
                job.started_at = datetime.utcnow()
                job.progress = 10
                job.progress_message = "Deleting repository archives"
                db.commit()

                delete_result = await router.run_wipe_delete(dry_run=False, env=env)
                delete_output = _command_output(delete_result)
                if delete_output:
                    log_lines.append(delete_output)

                if not delete_result.get("success"):
                    job.status = (
                        "failed_partial"
                        if _partial_delete_signal(delete_output)
                        else "failed"
                    )
                    job.phase = "delete_failed"
                    job.error_message = delete_output or "Repository wipe delete failed"
                    job.progress_message = "Repository wipe delete failed"
                    job.progress = 100
                    await self._best_effort_post_wipe_refresh(db, repository)
                    return

                if job.run_compact:
                    job.phase = "compact"
                    job.progress = 75
                    job.progress_message = "Compacting repository after wipe"
                    db.commit()
                    compact_result = await router.run_wipe_compact(env=env)
                    compact_output = _command_output(compact_result)
                    if compact_output:
                        log_lines.append(compact_output)
                    if not compact_result.get("success"):
                        job.status = "completed_compaction_failed"
                        job.phase = "compact_failed"
                        job.error_message = (
                            compact_output
                            or "Archives were deleted, but compact failed."
                        )
                    else:
                        job.status = "completed"
                        job.phase = "completed"
                else:
                    job.status = "completed_with_warnings"
                    job.phase = "compact_skipped"
                    job.error_message = (
                        "Archives were deleted, but compact was skipped. "
                        "Repository disk usage may not shrink yet."
                    )

                job.progress = 100
                job.progress_message = "Repository contents wipe completed"
                await self._best_effort_post_wipe_refresh(db, repository)

            await run_serialized_repository_command(
                repository_id, operation, scope="wipe"
            )
        except Exception as exc:
            logger.error(
                "Repository wipe execution failed", job_id=job_id, error=str(exc)
            )
            if job is not None:
                job.status = "failed"
                job.phase = "error"
                job.error_message = str(exc)
                job.progress_message = "Repository wipe failed"
        finally:
            if job is not None:
                if log_lines:
                    log_file_path = self.log_dir / f"repository_wipe_{job.id}.log"
                    log_file_path.write_text("\n".join(log_lines))
                    job.log_file_path = str(log_file_path)
                    job.has_logs = True
                    job.logs = "\n".join(log_lines[-50:])
                if job.status in TERMINAL_EXECUTION_STATUSES:
                    job.completed_at = datetime.utcnow()
                db.commit()
            cleanup_temp_key_file(temp_key_file)
            if close_db:
                db.close()

    async def _best_effort_post_wipe_refresh(
        self, db: Session, repository: Repository
    ) -> None:
        try:
            await BorgRouter(repository).update_stats(db)
        except Exception as exc:
            logger.warning(
                "Failed to refresh repository stats after wipe",
                repository_id=repository.id,
                error=str(exc),
            )
        try:
            from app.services.cache_service import archive_cache

            await archive_cache.clear_repository(repository.id)
        except Exception as exc:
            logger.warning(
                "Failed to clear archive cache after wipe",
                repository_id=repository.id,
                error=str(exc),
            )
        try:
            from app.services.mqtt_service import mqtt_service

            mqtt_service.sync_state_with_db(db, reason="repository wipe")
        except Exception as exc:
            logger.warning(
                "Failed to sync MQTT after repository wipe",
                repository_id=repository.id,
                error=str(exc),
            )

    def cancel_preview(
        self,
        db: Session,
        repository: Repository,
        current_user: User,
        *,
        job_id: int,
    ) -> dict[str, Any]:
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
        if job.status not in ("previewed", "pending"):
            raise HTTPException(
                status_code=409,
                detail={"key": "backend.errors.repo.wipeCannotCancelRunning"},
            )
        job.status = "cancelled"
        job.phase = "cancelled"
        job.completed_at = datetime.utcnow()
        job.progress_message = "Wipe preview cancelled"
        db.commit()
        db.refresh(job)
        logger.info(
            "Repository wipe preview cancelled",
            repository_id=repository.id,
            job_id=job.id,
            actor=current_user.username,
        )
        return self.serialize_job(job, include_preview=True)

    def serialize_job(
        self,
        job: RepositoryWipeJob,
        *,
        include_preview: bool = False,
        include_logs: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "id": job.id,
            "repository_id": job.repository_id,
            "status": job.status,
            "phase": job.phase,
            "started_at": serialize_datetime(job.started_at),
            "confirmed_at": serialize_datetime(job.confirmed_at),
            "completed_at": serialize_datetime(job.completed_at),
            "error_message": job.error_message,
            "progress": job.progress,
            "progress_message": job.progress_message,
            "archive_count": job.archive_count,
            "archive_fingerprint": job.archive_fingerprint,
            "run_compact": bool(job.run_compact),
            "has_logs": bool(job.has_logs),
        }
        if include_preview:
            manifest = _decode_json_list(job.archive_manifest_json)
            protected_archives = _decode_json_list(job.protected_archives_json)
            payload.update(
                {
                    "archives": manifest,
                    "dry_run_output": job.dry_run_output or "",
                    "blocked": bool(job.blocking_reason),
                    "blocking_reason": job.blocking_reason,
                    "protected_archives": protected_archives,
                }
            )
        if include_logs:
            payload["logs"] = self._read_logs(job)
        return payload

    def _read_logs(self, job: RepositoryWipeJob) -> str:
        if job.log_file_path:
            path = Path(job.log_file_path)
            if path.exists():
                try:
                    return path.read_text()
                except Exception as exc:
                    return f"Failed to read log file: {exc}"
        return job.logs or ""


repository_wipe_service = RepositoryWipeService()
