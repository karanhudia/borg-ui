from __future__ import annotations

import json
import os
import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional

from agent.borg_ui_agent.client import AgentClient


@dataclass(frozen=True)
class BackupCreatePayload:
    repository_path: str
    archive_name: str
    source_paths: list[str]
    borg_version: int = 1
    borg_binary: Optional[str] = None
    compression: str = "lz4"
    exclude_patterns: list[str] = field(default_factory=list)
    custom_flags: list[str] = field(default_factory=list)
    remote_path: Optional[str] = None
    environment: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_job_payload(cls, payload: dict[str, Any]) -> "BackupCreatePayload":
        repository = payload.get("repository") or {}
        backup = payload.get("backup") or {}

        repository_path = (
            repository.get("path")
            or payload.get("repository_path")
            or payload.get("repository")
        )
        archive_name = backup.get("archive_name") or payload.get("archive_name")
        source_paths = backup.get("source_paths") or payload.get("source_paths") or []

        if not isinstance(repository_path, str) or not repository_path.strip():
            raise ValueError("backup.create payload requires repository.path")
        if not isinstance(archive_name, str) or not archive_name.strip():
            raise ValueError("backup.create payload requires backup.archive_name")
        if not isinstance(source_paths, list) or not all(
            isinstance(path, str) and path.strip() for path in source_paths
        ):
            raise ValueError("backup.create payload requires backup.source_paths")

        custom_flags = backup.get("custom_flags", payload.get("custom_flags", []))
        if isinstance(custom_flags, str):
            custom_flags = shlex.split(custom_flags)
        if not isinstance(custom_flags, list) or not all(
            isinstance(flag, str) for flag in custom_flags
        ):
            raise ValueError("backup.create custom_flags must be a string or list")

        exclude_patterns = backup.get(
            "exclude_patterns", payload.get("exclude_patterns", [])
        )
        if not isinstance(exclude_patterns, list) or not all(
            isinstance(pattern, str) for pattern in exclude_patterns
        ):
            raise ValueError("backup.create exclude_patterns must be a list")

        borg_version = int(
            repository.get("borg_version") or payload.get("borg_version") or 1
        )
        environment = _extract_environment(payload, repository)

        return cls(
            repository_path=repository_path.strip(),
            archive_name=archive_name.strip(),
            source_paths=[path.strip() for path in source_paths],
            borg_version=borg_version,
            borg_binary=repository.get("borg_binary") or payload.get("borg_binary"),
            compression=backup.get("compression")
            or payload.get("compression")
            or "lz4",
            exclude_patterns=exclude_patterns,
            custom_flags=custom_flags,
            remote_path=repository.get("remote_path") or payload.get("remote_path"),
            environment=environment,
        )

    def build_command(self) -> list[str]:
        borg_cmd = self.borg_binary or ("borg2" if self.borg_version == 2 else "borg")
        if self.borg_version == 2:
            cmd = [
                borg_cmd,
                "--progress",
                "--show-rc",
                "--log-json",
                "-r",
                self.repository_path,
                "create",
                "--stats",
                "--compression",
                self.compression,
            ]
            for pattern in self.exclude_patterns:
                cmd.extend(["--exclude", pattern])
            cmd.extend(self.custom_flags)
            cmd.append(self.archive_name)
            cmd.extend(self.source_paths)
            return cmd

        cmd = [
            borg_cmd,
            "create",
            "--progress",
            "--stats",
            "--show-rc",
            "--log-json",
            "--compression",
            self.compression,
        ]
        if self.remote_path:
            cmd.extend(["--remote-path", self.remote_path])
        for pattern in self.exclude_patterns:
            cmd.extend(["--exclude", pattern])
        cmd.extend(self.custom_flags)
        cmd.append(f"{self.repository_path}::{self.archive_name}")
        cmd.extend(self.source_paths)
        return cmd


@dataclass(frozen=True)
class BackupExecutionResult:
    job_id: int
    status: str
    return_code: Optional[int] = None
    message: str = ""


def _extract_secret_value(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        direct_value = value.get("value")
        if isinstance(direct_value, str):
            return direct_value
    return None


def _extract_environment(
    payload: dict[str, Any], repository: dict[str, Any]
) -> dict[str, str]:
    environment: dict[str, str] = {}

    passphrase = repository.get("passphrase") or payload.get("passphrase")
    if isinstance(passphrase, str):
        environment["BORG_PASSPHRASE"] = passphrase

    for source_key in ("environment", "secrets"):
        source = payload.get(source_key) or {}
        if not isinstance(source, dict):
            continue
        secret_value = _extract_secret_value(source.get("BORG_PASSPHRASE"))
        if secret_value is not None:
            environment["BORG_PASSPHRASE"] = secret_value

    return environment


def parse_borg_progress(line: str) -> Optional[dict[str, Any]]:
    stripped = line.strip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None

    msg_type = payload.get("type")
    if msg_type == "archive_progress":
        progress: dict[str, Any] = {}
        for key in (
            "original_size",
            "compressed_size",
            "deduplicated_size",
            "nfiles",
        ):
            if key in payload:
                progress[key] = payload[key]
        if "path" in payload:
            progress["current_file"] = payload["path"]
        if payload.get("finished"):
            progress["progress_percent"] = 100.0
        return progress or None

    if msg_type == "progress_percent":
        if payload.get("finished"):
            return {"progress_percent": 100.0}
        current = payload.get("current")
        total = payload.get("total")
        if (
            isinstance(current, (int, float))
            and isinstance(total, (int, float))
            and total
        ):
            return {"progress_percent": float(current / total * 100.0)}

    if msg_type == "file_status" and payload.get("path"):
        return {"current_file": payload["path"]}

    return None


def execute_backup_create_job(
    job: dict[str, Any],
    client: AgentClient,
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> BackupExecutionResult:
    job_id = int(job["id"])
    try:
        payload = BackupCreatePayload.from_job_payload(job.get("payload") or {})
    except (TypeError, ValueError) as exc:
        error_message = f"Invalid backup.create payload: {exc}"
        client.send_log(job_id, sequence=0, stream="stderr", message=error_message)
        client.fail_job(job_id, error_message=error_message)
        return BackupExecutionResult(
            job_id=job_id, status="failed", message=error_message
        )

    cmd = payload.build_command()
    env = os.environ.copy()
    env.update(payload.environment)

    sequence = 0
    client.send_log(
        job_id,
        sequence=sequence,
        stream="stdout",
        message=f"Starting backup.create: {shlex.join(cmd)}",
    )
    sequence += 1

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
    except OSError as exc:
        error_message = f"Failed to start borg create: {exc}"
        client.send_log(
            job_id, sequence=sequence, stream="stderr", message=error_message
        )
        client.fail_job(job_id, error_message=error_message)
        return BackupExecutionResult(
            job_id=job_id, status="failed", message=error_message
        )

    if process.stdout is not None:
        for line in process.stdout:
            message = line.rstrip("\n")
            client.send_log(job_id, sequence=sequence, stream="stdout", message=message)
            sequence += 1
            progress = parse_borg_progress(message)
            if progress:
                client.send_progress(job_id, progress)
            if should_cancel and should_cancel():
                cancel_message = "Cancellation requested; stopping borg create"
                client.send_log(
                    job_id, sequence=sequence, stream="stderr", message=cancel_message
                )
                return_code = _terminate_process(process)
                client.cancel_job(job_id)
                return BackupExecutionResult(
                    job_id=job_id,
                    status="canceled",
                    return_code=return_code,
                    message="backup.create canceled",
                )

    return_code = process.wait()
    if return_code == 0:
        client.complete_job(
            job_id,
            result={
                "archive_name": payload.archive_name,
                "return_code": return_code,
                "command": cmd,
            },
        )
        return BackupExecutionResult(
            job_id=job_id,
            status="completed",
            return_code=return_code,
            message=f"borg create exited with code {return_code}",
        )

    error_message = f"borg create exited with code {return_code}"
    client.fail_job(job_id, error_message=error_message, return_code=return_code)
    return BackupExecutionResult(
        job_id=job_id,
        status="failed",
        return_code=return_code,
        message=error_message,
    )


def _terminate_process(process: subprocess.Popen) -> int:
    process.terminate()
    try:
        return process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait(timeout=5)
