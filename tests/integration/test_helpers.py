#!/usr/bin/env python3
"""
Shared utilities for integration tests.

Provides helpers for Docker environment detection, path conversion, and polling
long-running API jobs.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.utils.jobs import wait_for_payload_status
from tests.utils.borg import make_borg_test_env


def make_borg_env(base_path: str) -> dict:
    """Backwards-compatible wrapper around the shared Borg test env helper."""
    return make_borg_test_env(base_path)


class DockerPathHelper:
    """
    Helper class for handling path conversions between host and Docker container.

    When the Borg UI backend runs in a Docker container, it mounts the host's root
    filesystem at /local inside the container. This helper detects the environment
    and converts paths accordingly.
    """

    def __init__(self, base_url: str = "http://localhost:8081", container_mode: bool = False):
        """
        Initialize path helper with environment detection.

        Args:
            base_url: URL of the backend server
            container_mode: Explicit override to enable container mode
        """
        # Determine if backend server is running in Docker container
        # Port-based detection: 8081/8082 = Docker, 8000 = local dev
        # Can be overridden with container_mode parameter or BORG_UI_CONTAINER env var
        is_container_port = base_url.endswith(":8081") or base_url.endswith(":8082")
        env_container_mode = os.environ.get('BORG_UI_CONTAINER', '').lower() in ('true', '1', 'yes')

        # Use /local prefix if:
        # 1. Explicitly set via container_mode parameter, OR
        # 2. Explicitly set via BORG_UI_CONTAINER env var, OR
        # 3. Port suggests Docker AND not explicitly disabled
        self.use_local_prefix = (
            container_mode or
            env_container_mode or
            (is_container_port and os.environ.get('BORG_UI_CONTAINER', '').lower() not in ('false', '0', 'no'))
        )

        self.base_url = base_url

    def to_container_path(self, host_path: str) -> str:
        """
        Convert host path to container path if needed.

        Args:
            host_path: Path on the host filesystem

        Returns:
            Path that the backend can access (with /local prefix if in Docker)
        """
        if not self.use_local_prefix or not host_path:
            return host_path

        # Already has /local prefix
        if host_path.startswith('/local/'):
            return host_path

        # Add /local prefix for absolute paths
        if host_path.startswith('/'):
            return f'/local{host_path}'

        return host_path

    def to_host_path(self, container_path: str) -> str:
        """
        Convert container path back to host path.

        Args:
            container_path: Path from the backend (may have /local prefix)

        Returns:
            Path on the host filesystem (without /local prefix)
        """
        if not container_path:
            return container_path

        # Remove /local prefix if present
        if container_path.startswith('/local/'):
            return container_path[6:]  # Remove '/local' prefix

        return container_path

    def log_environment(self, logger_func=print):
        """
        Log detected environment configuration.

        Args:
            logger_func: Function to call for logging (default: print)
        """
        if self.use_local_prefix:
            logger_func("ℹ️  Docker backend detected (paths will use /local prefix)")
            logger_func(f"   Backend URL: {self.base_url}")
        else:
            logger_func("ℹ️  Local/CI backend detected (direct filesystem access)")
            logger_func(f"   Backend URL: {self.base_url}")


def wait_for_job_terminal_status(
    test_client,
    job_endpoint: str,
    job_id: int,
    headers: dict,
    *,
    timeout: float = 30.0,
    poll_interval: float = 0.25,
    terminal_statuses=("completed", "completed_with_warnings", "failed", "cancelled"),
):
    """Poll a job endpoint until it reaches a terminal state."""
    def fetch_payload():
        response = test_client.get(f"{job_endpoint}/{job_id}", headers=headers)
        response.raise_for_status()
        return response.json()

    return wait_for_payload_status(
        fetch_payload,
        expected=set(terminal_statuses),
        timeout=timeout,
        poll_interval=poll_interval,
        terminal=set(terminal_statuses),
        description=f"job {job_id} at {job_endpoint}",
    )


def parse_archives_payload(payload: dict) -> list:
    """Normalize the archives API payload into a list of archive dicts."""
    archives_raw = payload.get("archives", "{}")
    if isinstance(archives_raw, str):
        archives_data = json.loads(archives_raw)
    else:
        archives_data = archives_raw
    return archives_data.get("archives", [])
