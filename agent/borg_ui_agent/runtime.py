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

DEFAULT_CAPABILITIES = [
    "jobs.poll",
    "jobs.claim",
    "jobs.report",
    "logs.stream",
    "backup.create",
    "backup.cancel",
]


@dataclass(frozen=True)
class RunOnceResult:
    job_id: Optional[int]
    status: str
    message: str = ""


def get_capabilities() -> list[str]:
    return list(DEFAULT_CAPABILITIES)


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
        if job_kind == "backup.create":
            result = execute_backup_create_job(
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
        self, *, poll_interval_seconds: int = 15, max_iterations: Optional[int] = None
    ) -> None:
        iterations = 0
        while True:
            self.run_once()
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                return
            time.sleep(poll_interval_seconds)

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
