from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import structlog

from app.config import settings
from app.core.borg_router import BorgRouter
from app.database.database import SessionLocal
from app.database.models import Repository, RestoreCheckJob
from app.services.notification_service import NotificationService
from app.services.restore_check_canary import (
    get_legacy_restore_canary_archive_paths,
    get_restore_canary_archive_paths,
    verify_restored_canary,
)
from app.utils.borg_env import build_repository_borg_env, cleanup_temp_key_file

logger = structlog.get_logger()


def get_process_start_time(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/stat", "r") as handle:
            stat_data = handle.read()
        fields = stat_data.split(")")[1].split()
        return int(fields[19])
    except Exception as exc:
        logger.error(
            "Failed to read process start time for restore check",
            pid=pid,
            error=str(exc),
        )
        return 0


def _parse_probe_paths(raw_probe_paths: str | None) -> list[str]:
    if not raw_probe_paths:
        return []
    try:
        parsed = json.loads(raw_probe_paths)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [path for path in parsed if isinstance(path, str) and path.strip()]


def _coerce_archive_timestamp(archive: dict | str) -> str:
    if isinstance(archive, str):
        return archive
    for key in ("start", "time", "end", "ts"):
        value = archive.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _select_latest_archive(archives: list[dict | str]) -> dict | str | None:
    if not archives:
        return None
    return max(archives, key=_coerce_archive_timestamp)


def _get_archive_name(archive: dict | str | None) -> str:
    if isinstance(archive, str):
        return archive
    if not isinstance(archive, dict):
        return ""
    for key in ("name", "archive", "id"):
        value = archive.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _is_borg_warning_exit_code(returncode: int | None) -> bool:
    return returncode == 1 or (returncode is not None and 100 <= returncode <= 127)


class RestoreCheckService:
    """Restore latest archive into a disposable temp directory to verify restorability."""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes: dict[int, asyncio.subprocess.Process] = {}

    def _save_job_logs(
        self, job: RestoreCheckJob, job_id: int, raw_logs: list[str]
    ) -> None:
        if not raw_logs:
            return

        log_file = (
            self.log_dir
            / f"restore_check_job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        try:
            log_file.write_text("\n".join(raw_logs), encoding="utf-8")
            job.log_file_path = str(log_file)
            job.has_logs = True
            job.logs = f"Logs saved to: {log_file.name}"
        except Exception as exc:
            job.has_logs = False
            job.logs = f"Failed to save logs: {exc}"

    async def _send_completion_notification(
        self,
        *,
        db,
        repository: Repository,
        job: RestoreCheckJob,
    ) -> None:
        if job.status not in {
            "completed",
            "completed_with_warnings",
            "failed",
            "needs_backup",
        }:
            return

        try:
            duration_seconds = None
            if job.started_at and job.completed_at:
                duration_seconds = int(
                    (job.completed_at - job.started_at).total_seconds()
                )

            full_archive = bool(job.full_archive)
            probe_paths = _parse_probe_paths(
                job.probe_paths or repository.restore_check_paths
            )
            mode = (
                "full_archive"
                if full_archive
                else "probe_paths"
                if probe_paths
                else "canary"
            )

            await NotificationService.send_restore_check_completion(
                db=db,
                repository_name=repository.name,
                repository_path=repository.path,
                status=job.status,
                mode=mode,
                archive_name=job.archive_name,
                duration_seconds=duration_seconds,
                error_message=job.error_message,
                check_type="scheduled" if job.scheduled_restore_check else "manual",
                probe_paths=probe_paths,
                full_archive=full_archive,
            )
            logger.info(
                "Restore check notification sent", job_id=job.id, status=job.status
            )
        except Exception as exc:
            logger.error(
                "Failed to send restore check notification",
                job_id=job.id,
                error=str(exc),
            )

    async def execute_restore_check(self, job_id: int, repository_id: int):
        db = SessionLocal()
        temp_key_file = None
        temp_restore_dir = None
        job: RestoreCheckJob | None = None
        repository: Repository | None = None
        raw_logs: list[str] = []
        logs_saved = False
        use_canary = False

        try:
            job = db.query(RestoreCheckJob).filter(RestoreCheckJob.id == job_id).first()
            if not job:
                logger.error("Restore check job not found", job_id=job_id)
                return

            repository = (
                db.query(Repository).filter(Repository.id == repository_id).first()
            )
            if not repository:
                job.status = "failed"
                job.error_message = f"Repository not found (ID: {repository_id})"
                job.completed_at = datetime.utcnow()
                db.commit()
                return

            job.status = "running"
            job.started_at = datetime.utcnow()
            job.progress = 5
            job.progress_message = "Selecting latest archive for restore verification"
            db.commit()

            env, temp_key_file = build_repository_borg_env(
                repository,
                db,
                keepalive=True,
                show_progress=True,
            )
            full_archive = bool(job.full_archive)
            probe_paths = _parse_probe_paths(
                job.probe_paths or repository.restore_check_paths
            )
            use_canary = not full_archive and not probe_paths
            archives = await BorgRouter(repository).list_archives(env=env)
            archive = _select_latest_archive(archives)
            archive_name = _get_archive_name(archive)
            if not archive_name:
                job.status = "needs_backup" if use_canary else "failed"
                job.error_message = (
                    "Canary mode needs a backup that contains the Borg UI canary file. "
                    "Run a backup, then run this restore check again."
                    if use_canary
                    else "No archives available for restore verification. Run a backup, then run this restore check again."
                )
                job.progress = 100
                job.progress_message = "Restore verification needs a backup first"
                job.completed_at = datetime.utcnow()
                raw_logs.extend(
                    [
                        f"Restore check started for repository: {repository.name} ({repository.id})",
                        (
                            "Mode: Canary"
                            if use_canary
                            else "Mode: Full Archive"
                            if full_archive
                            else "Mode: Probe Paths"
                        ),
                        job.error_message,
                    ]
                )
                self._save_job_logs(job, job_id, raw_logs)
                logs_saved = True
                db.commit()
                await self._send_completion_notification(
                    db=db, repository=repository, job=job
                )
                return

            job.archive_name = archive_name
            job.progress = 15
            job.progress_message = (
                f"Restoring full archive {archive_name} to temporary directory"
                if full_archive
                else "Restoring managed canary payload to temporary directory"
                if use_canary
                else f"Restoring selected probe paths from {archive_name} to temporary directory"
            )
            db.commit()

            temp_restore_dir = tempfile.mkdtemp(
                prefix=f"restore-check-{repository.id}-",
                dir=settings.data_dir,
            )

            if full_archive:
                restore_paths = []
                restore_mode = "Full Archive"
            elif use_canary:
                restore_paths = get_restore_canary_archive_paths(repository)
                restore_mode = "Canary"
            else:
                restore_paths = probe_paths
                restore_mode = "Probe Paths"

            raw_logs.extend(
                [
                    f"Restore check started for repository: {repository.name} ({repository.id})",
                    f"Archive: {archive_name}",
                    f"Mode: {restore_mode}",
                    f"Restore paths: {', '.join(restore_paths) if restore_paths else 'full archive'}",
                ]
            )

            async def run_extract(paths: list[str]) -> int | None:
                cmd = BorgRouter(repository).build_restore_extract_command(
                    repository_path=repository.path,
                    archive_name=archive_name,
                    paths=paths,
                    remote_path=repository.remote_path,
                    bypass_lock=repository.bypass_lock,
                )

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=temp_restore_dir,
                    env=env,
                )

                self.running_processes[job_id] = process
                job.process_pid = process.pid
                job.process_start_time = get_process_start_time(process.pid)
                db.commit()

                stdout, stderr = await process.communicate()
                if stdout:
                    raw_logs.extend(
                        stdout.decode("utf-8", errors="replace").splitlines()
                    )
                if stderr:
                    raw_logs.extend(
                        stderr.decode("utf-8", errors="replace").splitlines()
                    )
                return process.returncode

            restore_path_attempts = [restore_paths]
            if use_canary:
                legacy_paths = get_legacy_restore_canary_archive_paths(repository)
                if legacy_paths != restore_paths:
                    restore_path_attempts.append(legacy_paths)

            returncode = None
            verification = None
            canary_prerequisite_error = None
            for attempt_index, attempt_paths in enumerate(restore_path_attempts):
                if attempt_index > 0:
                    raw_logs.append(
                        "Retrying restore canary using legacy archive path: "
                        f"{', '.join(attempt_paths)}"
                    )

                returncode = await run_extract(attempt_paths)
                warning_exit = _is_borg_warning_exit_code(returncode)

                if not use_canary:
                    break

                if returncode == 0 or warning_exit:
                    try:
                        verification = verify_restored_canary(
                            repository, temp_restore_dir
                        )
                        restore_paths = attempt_paths
                        break
                    except FileNotFoundError as exc:
                        if attempt_index < len(restore_path_attempts) - 1:
                            raw_logs.append(
                                "Canary manifest not found at this archive path; "
                                "trying the legacy path"
                            )
                            continue
                        canary_prerequisite_error = str(exc)
                        raw_logs.append(canary_prerequisite_error)
                        break
                elif attempt_index < len(restore_path_attempts) - 1:
                    raw_logs.append(
                        f"Canary extract failed with exit code {returncode}; "
                        "trying the legacy path"
                    )
                    continue
                break

            warning_exit = _is_borg_warning_exit_code(returncode)
            if canary_prerequisite_error:
                job.status = "needs_backup"
                job.progress = 100
                job.completed_at = datetime.utcnow()
                job.error_message = canary_prerequisite_error
                job.progress_message = "Restore verification needs a backup first"
                raw_logs.append(job.progress_message)
            elif returncode == 0 or warning_exit:
                if use_canary and verification:
                    raw_logs.append(
                        f"Verified canary files: {', '.join(verification['verified_files'])}"
                    )
                job.status = "completed_with_warnings" if warning_exit else "completed"
                job.progress = 100
                job.progress_message = (
                    f"Restore verification completed with warnings (exit code {returncode})"
                    if warning_exit
                    else "Restore verification completed successfully"
                )
                raw_logs.append(job.progress_message)
                if warning_exit:
                    job.error_message = f"Restore verification completed with warnings (exit code {returncode})"
                job.completed_at = datetime.utcnow()
                repository.last_restore_check = datetime.utcnow()
            else:
                job.status = "failed"
                job.progress = 100
                job.completed_at = datetime.utcnow()
                job.error_message = (
                    f"Restore verification failed with exit code {returncode}"
                )
                job.progress_message = "Restore verification failed"
                raw_logs.append(job.error_message)

            if raw_logs:
                self._save_job_logs(job, job_id, raw_logs)
                logs_saved = True

            db.commit()
            await self._send_completion_notification(
                db=db, repository=repository, job=job
            )
        except Exception as exc:
            logger.error(
                "Restore check execution failed", job_id=job_id, error=str(exc)
            )
            raw_logs.append(f"Restore check execution failed: {exc}")
            try:
                db.rollback()
                if job is None:
                    job = (
                        db.query(RestoreCheckJob)
                        .filter(RestoreCheckJob.id == job_id)
                        .first()
                    )
                if job:
                    job.status = "failed"
                    job.error_message = str(exc)
                    job.progress = 100
                    job.progress_message = "Restore verification failed"
                    job.completed_at = datetime.utcnow()
                    if raw_logs and not logs_saved:
                        self._save_job_logs(job, job_id, raw_logs)
                    db.commit()
                    if repository:
                        await self._send_completion_notification(
                            db=db, repository=repository, job=job
                        )
            except Exception:
                db.rollback()
        finally:
            self.running_processes.pop(job_id, None)
            cleanup_temp_key_file(temp_key_file)
            if temp_restore_dir:
                shutil.rmtree(temp_restore_dir, ignore_errors=True)
            db.close()


restore_check_service = RestoreCheckService()
