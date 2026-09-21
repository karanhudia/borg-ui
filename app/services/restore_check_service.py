from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path

import structlog
from fastapi import HTTPException

from app.config import settings
from app.core.borg_errors import is_borg_warning_exit_code
from app.core.borg_router import BorgRouter
from app.database.database import SessionLocal
from app.database.models import Repository
from app.services.notification_service import NotificationService
from app.services.operations.job_facade import resolve_maintenance_job
from app.services.restore_check_canary import (
    CANARY_MANIFEST,
    get_legacy_restore_canary_archive_paths,
    get_restore_canary_archive_paths,
    verify_restored_canary,
)
from app.utils.borg_env import (
    build_repository_borg_env,
    cleanup_temp_key_file,
    effective_repository_remote_path,
)

from app.services.process_cancel import (
    terminate_process,
    terminate_tracked_process,
)

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


def _get_archive_selector(archive: dict | str | None, repository) -> str:
    """Selector that resolves to exactly one archive.

    Borg 2 archives in a series share one name and are told apart by id, so
    extract needs the aid: selector - a bare series name matches every
    archive in the series and borg refuses to pick one. Borg 1 names are
    unique and are passed as-is.
    """
    name = _get_archive_name(archive)
    if getattr(repository, "borg_version", 1) != 2:
        return name
    if isinstance(archive, dict):
        archive_id = archive.get("id")
        if isinstance(archive_id, str) and archive_id:
            return f"aid:{archive_id}"
    return name


# Upper bounds so a delegated restore-check cannot wait on the agent forever:
# fail if the job is never claimed (agent offline) or goes silent (agent died).
_AGENT_OP_CLAIM_TIMEOUT_SECONDS = 120
_AGENT_OP_STALL_TIMEOUT_SECONDS = 600
# An agent reports a keepalive while its Borg is silent (0.1.7), which holds
# off the stall timeout; this bounds how long a job may keep doing so without
# any progress, so a hung but live process is not waited on forever.
_AGENT_OP_NO_PROGRESS_MAX_SECONDS = 6 * 3600


def _http_detail_text(exc: HTTPException) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        return detail.get("message") or detail.get("key") or str(detail)
    return str(detail)


class RestoreCheckService:
    """Restore latest archive into a disposable temp directory to verify restorability."""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes: dict[int, asyncio.subprocess.Process] = {}
        # Checks whose cancel was requested while they ran: an extract must
        # not start after it (the canary's legacy-path retry included).
        self.cancelled_jobs: set[int] = set()
        self._active_jobs: set[int] = set()

    async def cancel_restore_check(self, job_id: int) -> bool:
        """Cancel a running restore check by terminating its tracked process."""
        if job_id in self._active_jobs:
            # Only a running check is remembered; its run clears the mark.
            self.cancelled_jobs.add(job_id)
        return await terminate_tracked_process(
            self.running_processes, job_id, "restore check"
        )

    def _save_job_logs(self, job, job_id: int, raw_logs: list[str]) -> None:
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
        job,
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
        self._active_jobs.add(job_id)
        db = SessionLocal()
        temp_key_file = None
        temp_restore_dir = None
        job = None
        repository: Repository | None = None
        raw_logs: list[str] = []
        logs_saved = False
        use_canary = False

        try:
            job = resolve_maintenance_job(db, job_id, "restore_check")
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

            from app.services.repository_executor import is_agent_executor

            if is_agent_executor(repository):
                # Agent-executor repos verify on the node: the server can't reach
                # the node's filesystem (or, for agent-owned repos, the repo).
                await self._execute_agent_restore_check(db, job, job_id, repository)
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
            archive_selector = _get_archive_selector(archive, repository)
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
                    archive_name=archive_selector,
                    paths=paths,
                    remote_path=effective_repository_remote_path(repository),
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

                # Reads the pipes while the process is terminated: its exit
                # is not seen while a full pipe goes unread.
                output = asyncio.ensure_future(process.communicate())
                if job_id in self.cancelled_jobs:
                    # The cancel landed while the process was starting and
                    # found nothing tracked to terminate.
                    await terminate_process(process, job_id, "restore check")

                stdout, stderr = await output
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
                if job_id in self.cancelled_jobs:
                    break
                if attempt_index > 0:
                    raw_logs.append(
                        "Retrying restore canary using legacy archive path: "
                        f"{', '.join(attempt_paths)}"
                    )

                returncode = await run_extract(attempt_paths)
                warning_exit = is_borg_warning_exit_code(returncode)

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

            warning_exit = is_borg_warning_exit_code(returncode)
            if job_id in self.cancelled_jobs:
                # Before any verdict from the exit code: a cancelled check
                # verified nothing, whatever its last extract returned. Not
                # a failure: no failure notification goes out for it, and the
                # runner keeps the row cancelled.
                job.status = "cancelled"
                job.progress = 100
                job.completed_at = datetime.utcnow()
                job.error_message = "Restore verification cancelled"
                job.progress_message = job.error_message
                raw_logs.append(job.error_message)
            elif canary_prerequisite_error:
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
                    job = resolve_maintenance_job(db, job_id, "restore_check")
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
            self.cancelled_jobs.discard(job_id)
            self._active_jobs.discard(job_id)
            cleanup_temp_key_file(temp_key_file)
            if temp_restore_dir:
                shutil.rmtree(temp_restore_dir, ignore_errors=True)
            db.close()

    async def _execute_agent_restore_check(
        self, db, job, job_id: int, repository: Repository
    ):
        """Run a restore check by delegating to the repository's managed agent.

        Lists archives on the node, extracts the latest one into a throwaway
        directory the agent owns, and (for canary mode) verifies the canary
        manifest on the node. The agent's verdict is mapped onto the
        restore check operation's status.
        """
        from app.services.agent_job_dispatcher import dispatch_agent_job_best_effort
        from app.services.repository_executor import (
            queue_agent_repository_operation_job,
        )

        raw_logs: list[str] = []
        job.status = "running"
        job.started_at = datetime.utcnow()
        job.progress = 5
        job.progress_message = "Selecting latest archive for restore verification"
        db.commit()

        full_archive = bool(job.full_archive)
        probe_paths = _parse_probe_paths(
            job.probe_paths or repository.restore_check_paths
        )
        use_canary = not full_archive and not probe_paths
        mode = (
            "Full Archive"
            if full_archive
            else "Canary"
            if use_canary
            else "Probe Paths"
        )
        raw_logs.append(
            f"Restore check started for repository: {repository.name} ({repository.id})"
        )
        raw_logs.append(f"Mode: {mode}")

        # 1. List archives on the node and pick the latest.
        try:
            archives = await self._agent_list_archives(db, repository)
        except HTTPException as exc:
            self._finish_agent_restore_check_failure(
                db,
                job,
                job_id,
                raw_logs,
                message=f"Could not list archives on the agent: {_http_detail_text(exc)}",
            )
            await self._send_completion_notification(
                db=db, repository=repository, job=job
            )
            return

        archive = _select_latest_archive(archives)
        archive_name = _get_archive_name(archive)
        archive_selector = _get_archive_selector(archive, repository)
        if not archive_name:
            job.status = "needs_backup" if use_canary else "failed"
            job.error_message = (
                "Canary mode needs a backup that contains the Borg UI canary file. "
                "Run a backup, then run this restore check again."
                if use_canary
                else "No archives available for restore verification. "
                "Run a backup, then run this restore check again."
            )
            job.progress = 100
            job.progress_message = "Restore verification needs a backup first"
            job.completed_at = datetime.utcnow()
            raw_logs.append(job.error_message)
            self._save_job_logs(job, job_id, raw_logs)
            db.commit()
            await self._send_completion_notification(
                db=db, repository=repository, job=job
            )
            return

        job.archive_name = archive_name
        job.progress = 15
        job.progress_message = (
            f"Restoring {mode.lower()} from {archive_name} on the agent"
        )
        db.commit()

        # 2. Build the restore operation (paths + optional canary verify).
        if full_archive:
            restore_paths: list[str] = []
            verify = None
        elif use_canary:
            primary = get_restore_canary_archive_paths(repository)
            legacy = get_legacy_restore_canary_archive_paths(repository)
            # Extract both the current and legacy canary locations in one pass;
            # borg simply warns for a path that isn't present in the archive.
            restore_paths = list(primary) + [p for p in legacy if p not in primary]
            verify = {
                "kind": "canary",
                "manifest_candidates": [
                    f"{base}/{CANARY_MANIFEST}" for base in restore_paths
                ],
            }
        else:
            restore_paths = probe_paths
            verify = None

        raw_logs.append(f"Archive: {archive_name}")
        raw_logs.append(
            "Restore paths: "
            + (", ".join(restore_paths) if restore_paths else "full archive")
        )

        operation: dict = {
            "archive": archive_selector,
            "paths": restore_paths,
            "target": {"type": "temp"},
        }
        if verify:
            operation["verify"] = verify

        # 3. Queue + dispatch the restore, then wait for the verdict.
        try:
            agent_job = queue_agent_repository_operation_job(
                db,
                repository,
                job_kind="repository.restore",
                operation=operation,
                maintenance_job_kind="restore_check",
                maintenance_job_id=job_id,
            )
        except HTTPException as exc:
            self._finish_agent_restore_check_failure(
                db,
                job,
                job_id,
                raw_logs,
                message=f"Could not start restore on the agent: {_http_detail_text(exc)}",
            )
            await self._send_completion_notification(
                db=db, repository=repository, job=job
            )
            return

        await dispatch_agent_job_best_effort(
            db, agent_job, repository_id=repository.id, archive=archive_selector
        )

        try:
            result = await self._await_agent_operation(db, agent_job.id, job=job)
        except HTTPException as exc:
            self._append_agent_logs(db, raw_logs, agent_job.id)
            self._finish_agent_restore_check_failure(
                db,
                job,
                job_id,
                raw_logs,
                message=f"Restore verification failed on the agent: {_http_detail_text(exc)}",
            )
            await self._send_completion_notification(
                db=db, repository=repository, job=job
            )
            return

        self._append_agent_logs(db, raw_logs, agent_job.id)
        self._apply_agent_restore_check_result(
            db, job, job_id, repository, result, raw_logs
        )
        await self._send_completion_notification(db=db, repository=repository, job=job)

    async def _agent_list_archives(self, db, repository: Repository) -> list:
        from app.services.agent_job_dispatcher import dispatch_agent_job_best_effort
        from app.services.repository_executor import (
            queue_agent_repository_operation_job,
            wait_for_agent_repository_operation_job,
        )

        list_job = queue_agent_repository_operation_job(
            db, repository, job_kind="repository.list_archives"
        )
        await dispatch_agent_job_best_effort(db, list_job, repository_id=repository.id)
        result = await wait_for_agent_repository_operation_job(
            db, list_job.id, timeout_seconds=120
        )
        data = result.get("data") if isinstance(result, dict) else None
        archives = (data or {}).get("archives") if isinstance(data, dict) else None
        return archives or []

    async def _await_agent_operation(
        self, db, agent_job_id: int, *, job=None, poll_interval_seconds: float = 1.0
    ) -> dict:
        from app.database.models import AgentJob
        from app.services.repository_executor import (
            SUCCESSFUL_AGENT_STATUSES,
            TERMINAL_AGENT_STATUSES,
            agent_operation_failed_detail,
        )

        started_at = time.monotonic()
        stale_since = started_at
        progress_since = started_at
        last_progress = None
        last_seen = None

        while True:
            db.expire_all()
            agent_job = db.query(AgentJob).filter(AgentJob.id == agent_job_id).first()
            if agent_job is None:
                raise HTTPException(
                    status_code=502,
                    detail={"key": "backend.errors.agents.jobNotFound"},
                )
            if agent_job.status in SUCCESSFUL_AGENT_STATUSES:
                return agent_job.result or {}
            if agent_job.status in TERMINAL_AGENT_STATUSES:
                raise HTTPException(
                    status_code=502,
                    detail=agent_operation_failed_detail(
                        agent_job.error_message or agent_job.status
                    ),
                )
            if job is not None and agent_job.progress_percent is not None:
                job.progress = max(15, min(99, int(agent_job.progress_percent)))
                db.commit()

            # Bound the wait so an unclaimed or dead-agent job can't hang forever.
            now = time.monotonic()
            progress = (
                agent_job.status,
                agent_job.progress_percent,
                agent_job.current_file,
            )
            if progress != last_progress:
                last_progress = progress
                progress_since = now
                stale_since = now
            if agent_job.updated_at != last_seen:
                # Any report, the agent's keepalive (0.1.7) included, shows
                # the agent alive: a silent extract is not a stalled one.
                last_seen = agent_job.updated_at
                stale_since = now
            never_claimed = (
                agent_job.status == "queued"
                and now - started_at > _AGENT_OP_CLAIM_TIMEOUT_SECONDS
            )
            went_silent = (
                now - stale_since > _AGENT_OP_STALL_TIMEOUT_SECONDS
                or now - progress_since > _AGENT_OP_NO_PROGRESS_MAX_SECONDS
            )
            if never_claimed or went_silent:
                from app.services.agent_job_dispatcher import (
                    dispatch_agent_cancel_if_connected,
                )

                # Conditional on the status just read: the agent's reports
                # land concurrently, and a verdict that got there first is the
                # check's result, not a timeout.
                now_utc = datetime.utcnow()
                if agent_job.status in ("claimed", "running", "cancel_requested"):
                    from app.services.operations.executors.maintenance import (
                        AGENT_WAIT_ABANDONED_MESSAGE,
                        agent_machine_stops_on_cancel,
                    )

                    # An agent runs it: ask it to stop, so Borg does not run
                    # on holding the repository after the check was failed.
                    # Only an agent that stops Borg on a cancel is asked: an
                    # older one reports `canceled` at once and lets a silent
                    # Borg run on, so its job stays live (admission keeps
                    # counting it) until it reports or the reaper closes it.
                    if agent_machine_stops_on_cancel(db, agent_job.agent_machine_id):
                        if agent_job.status != "cancel_requested":
                            # The message tells the runner that the agent's
                            # `canceled` answers this stop, not a user's
                            # cancel. A cancel already asked for keeps its
                            # own provenance and is only sent again.
                            changed = (
                                db.query(AgentJob)
                                .filter(
                                    AgentJob.id == agent_job.id,
                                    AgentJob.status.in_(("claimed", "running")),
                                )
                                .update(
                                    {
                                        AgentJob.status: "cancel_requested",
                                        AgentJob.error_message: (
                                            AGENT_WAIT_ABANDONED_MESSAGE
                                        ),
                                        AgentJob.updated_at: now_utc,
                                    },
                                    synchronize_session=False,
                                )
                            )
                            db.commit()
                            if not changed:
                                continue
                            db.refresh(agent_job)
                        await dispatch_agent_cancel_if_connected(agent_job)
                elif agent_job.status == "queued":
                    # Never claimed: close it so it cannot be claimed later.
                    changed = (
                        db.query(AgentJob)
                        .filter(
                            AgentJob.id == agent_job.id, AgentJob.status == "queued"
                        )
                        .update(
                            {
                                AgentJob.status: "failed",
                                AgentJob.error_message: (
                                    "restore check timed out waiting for the agent"
                                ),
                                AgentJob.completed_at: now_utc,
                                AgentJob.updated_at: now_utc,
                            },
                            synchronize_session=False,
                        )
                    )
                    db.commit()
                    if not changed:
                        continue
                raise HTTPException(
                    status_code=504,
                    detail={"key": "backend.errors.agents.repositoryOperationTimeout"},
                )
            await asyncio.sleep(poll_interval_seconds)

    def _append_agent_logs(self, db, raw_logs: list[str], agent_job_id: int) -> None:
        from app.database.models import AgentJobLog

        logs = (
            db.query(AgentJobLog)
            .filter(AgentJobLog.agent_job_id == agent_job_id)
            .order_by(AgentJobLog.sequence.asc(), AgentJobLog.id.asc())
            .all()
        )
        raw_logs.extend(log.message for log in logs)

    def _finish_agent_restore_check_failure(
        self,
        db,
        job,
        job_id: int,
        raw_logs: list[str],
        *,
        message: str,
    ) -> None:
        job.status = "failed"
        job.error_message = message
        job.progress = 100
        job.progress_message = "Restore verification failed"
        job.completed_at = datetime.utcnow()
        raw_logs.append(message)
        self._save_job_logs(job, job_id, raw_logs)
        db.commit()

    def _apply_agent_restore_check_result(
        self,
        db,
        job,
        job_id: int,
        repository: Repository,
        result: dict,
        raw_logs: list[str],
    ) -> None:
        job.completed_at = datetime.utcnow()
        job.progress = 100
        warning = bool(result.get("warning")) if isinstance(result, dict) else False
        verification = result.get("verification") if isinstance(result, dict) else None

        if isinstance(verification, dict):
            vstatus = verification.get("status")
            if vstatus == "verified":
                verified_files = verification.get("verified_files") or []
                if verified_files:
                    raw_logs.append(
                        f"Verified canary files: {', '.join(verified_files)}"
                    )
                job.status = "completed_with_warnings" if warning else "completed"
                job.progress_message = (
                    "Restore verification completed with warnings"
                    if warning
                    else "Restore verification completed successfully"
                )
                repository.last_restore_check = datetime.utcnow()
            elif vstatus == "needs_backup":
                job.status = "needs_backup"
                job.error_message = (
                    verification.get("message")
                    or "Restore verification needs a backup first"
                )
                job.progress_message = "Restore verification needs a backup first"
                raw_logs.append(job.error_message)
            else:
                job.status = "failed"
                job.error_message = (
                    verification.get("message") or "Restore verification failed"
                )
                job.progress_message = "Restore verification failed"
                raw_logs.append(job.error_message)
        else:
            # Full-archive / probe mode: success is the extract itself.
            job.status = "completed_with_warnings" if warning else "completed"
            job.progress_message = (
                "Restore verification completed with warnings"
                if warning
                else "Restore verification completed successfully"
            )
            repository.last_restore_check = datetime.utcnow()

        if warning and not job.error_message:
            job.error_message = "Restore verification completed with warnings"

        self._save_job_logs(job, job_id, raw_logs)
        db.commit()


restore_check_service = RestoreCheckService()
