from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

from agent.borg_ui_agent import __version__
from agent.borg_ui_agent.backup import execute_backup_create_job
from agent.borg_ui_agent.borg import detect_borg_binaries, detect_platform
from agent.borg_ui_agent.client import AgentClient
from agent.borg_ui_agent.config import AgentConfig
from agent.borg_ui_agent.filesystem import execute_filesystem_browse_job
from agent.borg_ui_agent.repository_ops import execute_repository_operation_job

DEFAULT_REPOSITORY_OPERATION_HANDLER = execute_repository_operation_job

DEFAULT_CAPABILITIES = [
    "session.commands",
    "jobs.poll",
    "jobs.claim",
    "jobs.report",
    "logs.stream",
    "artifact.upload",
    "backup.create",
    "backup.cancel",
    "diagnostics.run",
    "filesystem.browse",
    "repository.init",
    "repository.info",
    "repository.list_archives",
    "repository.list_archive_contents",
    "repository.extract_archive_file",
    "repository.restore",
    "repository.check",
    "repository.prune",
    "repository.compact",
    "repository.rclone_sync",
]

JOB_HANDLERS = {
    "backup.create": execute_backup_create_job,
    "filesystem.browse": execute_filesystem_browse_job,
    "repository.init": execute_repository_operation_job,
    "repository.info": execute_repository_operation_job,
    "repository.list_archives": execute_repository_operation_job,
    "repository.list_archive_contents": execute_repository_operation_job,
    "repository.extract_archive_file": execute_repository_operation_job,
    "repository.restore": execute_repository_operation_job,
    "repository.check": execute_repository_operation_job,
    "repository.prune": execute_repository_operation_job,
    "repository.compact": execute_repository_operation_job,
    "repository.rclone_sync": execute_repository_operation_job,
}


@dataclass(frozen=True)
class RunOnceResult:
    job_id: Optional[int]
    status: str
    message: str = ""


def get_capabilities() -> list[str]:
    return list(DEFAULT_CAPABILITIES)


def get_job_handler(job_kind: str):
    if job_kind == "backup.create":
        return execute_backup_create_job
    if job_kind == "filesystem.browse":
        return execute_filesystem_browse_job
    handler = JOB_HANDLERS.get(job_kind)
    if job_kind.startswith("repository."):
        if handler is not None and handler is not DEFAULT_REPOSITORY_OPERATION_HANDLER:
            return handler
        return execute_repository_operation_job
    return handler


class AgentRuntime:
    def __init__(self, config: AgentConfig, client: Optional[AgentClient] = None):
        self.config = config
        self.client = client or AgentClient.from_config(config)

    def heartbeat(self, *, running_job_ids: Optional[list[int]] = None) -> dict:
        machine = detect_platform()
        borg_versions = [binary.to_api_payload() for binary in detect_borg_binaries()]
        return self.client.heartbeat(
            agent_id=self.config.agent_id,
            hostname=machine["hostname"],
            agent_version=__version__,
            borg_versions=borg_versions,
            capabilities=get_capabilities(),
            running_job_ids=running_job_ids or [],
        )

    def run_once(self) -> RunOnceResult:
        self.heartbeat()
        polled = self.client.poll_jobs(limit=1)
        jobs = polled.get("jobs") or []
        if not jobs:
            return RunOnceResult(job_id=None, status="idle", message="No queued jobs")

        job = jobs[0]
        job_id = int(job["id"])
        self.client.claim_job(job_id)
        self.client.start_job(job_id)

        payload = job.get("payload") or {}
        job_kind = str(payload.get("job_kind") or job.get("type") or "")
        handler = get_job_handler(job_kind)
        if handler:
            result = handler(
                job,
                self.client,
                should_cancel=self._build_cancel_checker(job_id),
            )
            return RunOnceResult(
                job_id=result.job_id,
                status=result.status,
                message=result.message,
            )

        message = f"Unsupported agent job type: {job_kind}"
        self.client.send_log(job_id, sequence=0, stream="stderr", message=message)
        self.client.fail_job(job_id, error_message=message)
        return RunOnceResult(job_id=job_id, status="failed", message=message)

    def run_forever(
        self,
        *,
        poll_interval_seconds: int = 15,
        max_iterations: Optional[int] = None,
        initial_backoff_seconds: float = 1,
        max_backoff_seconds: float = 60,
    ) -> None:
        from agent.borg_ui_agent.session import AgentSessionRuntime

        _ = poll_interval_seconds
        AgentSessionRuntime(self.config).run_forever(
            max_iterations=max_iterations,
            initial_backoff_seconds=initial_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
        )

    def _build_cancel_checker(self, job_id: int) -> Callable[[], bool]:
        last_checked_at = 0.0

        def should_cancel() -> bool:
            nonlocal last_checked_at
            now = time.monotonic()
            if now - last_checked_at < 5:
                return False
            last_checked_at = now
            response = self.heartbeat(running_job_ids=[job_id])
            return job_id in response.get("cancel_job_ids", [])

        return should_cancel
