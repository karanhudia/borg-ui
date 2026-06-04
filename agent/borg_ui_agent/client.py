from __future__ import annotations

import time
from typing import Any, Optional

import requests

from agent.borg_ui_agent.config import AgentConfig

AGENT_AUTH_HEADER = "X-Borg-Agent-Authorization"


class AgentClientError(RuntimeError):
    pass


class AgentClient:
    def __init__(
        self,
        server_url: str,
        agent_token: Optional[str] = None,
        *,
        session: Optional[requests.Session] = None,
        timeout_seconds: int = 30,
        max_report_attempts: int = 3,
        retry_backoff_seconds: float = 0.1,
    ):
        self.server_url = server_url.rstrip("/")
        self.agent_token = agent_token
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.max_report_attempts = max(1, max_report_attempts)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)

    @classmethod
    def from_config(
        cls,
        config: AgentConfig,
        *,
        session: Optional[requests.Session] = None,
        timeout_seconds: int = 30,
        max_report_attempts: int = 3,
        retry_backoff_seconds: float = 0.1,
    ) -> "AgentClient":
        return cls(
            config.server_url,
            agent_token=config.agent_token,
            session=session,
            timeout_seconds=timeout_seconds,
            max_report_attempts=max_report_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
        )

    def register(
        self,
        *,
        enrollment_token: str,
        name: str,
        hostname: str,
        os_name: str,
        arch: str,
        agent_version: str,
        borg_versions: list[dict[str, Any]],
        capabilities: list[str],
        labels: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/agents/register",
            authenticated=False,
            json={
                "enrollment_token": enrollment_token,
                "name": name,
                "hostname": hostname,
                "os": os_name,
                "arch": arch,
                "agent_version": agent_version,
                "borg_versions": borg_versions,
                "capabilities": capabilities,
                "labels": labels or {},
            },
        )

    def heartbeat(
        self,
        *,
        agent_id: str,
        hostname: str,
        agent_version: str,
        borg_versions: list[dict[str, Any]],
        capabilities: list[str],
        running_job_ids: Optional[list[int]] = None,
        last_error: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/agents/heartbeat",
            json={
                "agent_id": agent_id,
                "hostname": hostname,
                "agent_version": agent_version,
                "borg_versions": borg_versions,
                "capabilities": capabilities,
                "running_job_ids": running_job_ids or [],
                "last_error": last_error,
            },
        )

    def unregister(self) -> dict[str, Any]:
        return self._request("POST", "/api/agents/unregister", json={})

    def poll_jobs(self, *, limit: int = 1) -> dict[str, Any]:
        return self._request("GET", f"/api/agents/jobs/poll?limit={limit}")

    def claim_job(self, job_id: int) -> dict[str, Any]:
        return self._request("POST", f"/api/agents/jobs/{job_id}/claim")

    def start_job(self, job_id: int) -> dict[str, Any]:
        return self._request("POST", f"/api/agents/jobs/{job_id}/start", json={})

    def send_log(
        self,
        job_id: int,
        *,
        sequence: int,
        message: str,
        stream: str = "stdout",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/agents/jobs/{job_id}/logs",
            json={"sequence": sequence, "stream": stream, "message": message},
        )

    def send_progress(self, job_id: int, progress: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST", f"/api/agents/jobs/{job_id}/progress", json=progress
        )

    def complete_job(self, job_id: int, *, result: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST", f"/api/agents/jobs/{job_id}/complete", json={"result": result}
        )

    def fail_job(
        self, job_id: int, *, error_message: str, return_code: Optional[int] = None
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/agents/jobs/{job_id}/fail",
            json={"error_message": error_message, "return_code": return_code},
        )

    def cancel_job(self, job_id: int) -> dict[str, Any]:
        return self._request("POST", f"/api/agents/jobs/{job_id}/cancel", json={})

    def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        json: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        headers = {}
        if authenticated:
            if not self.agent_token:
                raise AgentClientError("Agent token is required for this request")
            headers[AGENT_AUTH_HEADER] = f"Bearer {self.agent_token}"

        last_error: Optional[BaseException] = None
        response: Optional[requests.Response] = None
        for attempt in range(self.max_report_attempts):
            try:
                response = self.session.request(
                    method,
                    f"{self.server_url}{path}",
                    headers=headers,
                    json=json,
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_report_attempts - 1:
                    time.sleep(self.retry_backoff_seconds)
                    continue
                raise AgentClientError(f"{method} {path} failed: {exc}") from exc

            if response.status_code < 500 or attempt == self.max_report_attempts - 1:
                break
            time.sleep(self.retry_backoff_seconds)

        if response is None:
            raise AgentClientError(f"{method} {path} failed: {last_error}")
        if response.status_code >= 400:
            raise AgentClientError(
                f"{method} {path} failed with HTTP {response.status_code}: {response.text}"
            )
        if not response.content:
            return {}
        return response.json()
