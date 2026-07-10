from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import threading
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
    upload_ratelimit_kib: Optional[int] = None
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
        upload_ratelimit_kib = backup.get(
            "upload_ratelimit_kib", payload.get("upload_ratelimit_kib")
        )
        if upload_ratelimit_kib is not None:
            upload_ratelimit_kib = int(upload_ratelimit_kib)
            if upload_ratelimit_kib <= 0:
                raise ValueError("backup.create upload_ratelimit_kib must be positive")
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
            upload_ratelimit_kib=upload_ratelimit_kib,
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
                "--json",
                "--compression",
                self.compression,
            ]
            if self.upload_ratelimit_kib:
                cmd.extend(["--upload-ratelimit", str(self.upload_ratelimit_kib)])
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
            "--json",
            "--show-rc",
            "--log-json",
            "--compression",
            self.compression,
        ]
        if self.remote_path:
            cmd.extend(["--remote-path", self.remote_path])
        if self.upload_ratelimit_kib:
            cmd.extend(["--upload-ratelimit", str(self.upload_ratelimit_kib)])
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


def _parse_created_archive_name(stdout: str) -> Optional[str]:
    """Extract the resolved archive name from ``borg create --json`` stdout.

    borg expands placeholders such as ``{now:%Y-%m-%d-%s}`` when it creates the
    archive and reports the resolved name as ``archive.name`` in the JSON result
    document (borg1 and borg2 alike). Returns None when the output is absent or
    unparseable so the caller can fall back to the requested (template) name.
    """
    if not stdout or not stdout.strip():
        return None
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    archive = data.get("archive")
    if isinstance(archive, dict):
        name = archive.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
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
        popen_kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "env": env,
        }
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(cmd, **popen_kwargs)
    except OSError as exc:
        error_message = f"Failed to start borg create: {exc}"
        client.send_log(
            job_id, sequence=sequence, stream="stderr", message=error_message
        )
        client.fail_job(job_id, error_message=error_message)
        return BackupExecutionResult(
            job_id=job_id, status="failed", message=error_message
        )

    # `borg create --json` writes its result document (with the resolved archive
    # name) to stdout only at the very end, while --progress/--log-json stream to
    # stderr throughout. Drain stdout in a background thread so borg never blocks
    # on a full stdout pipe while we stream stderr line by line.
    stdout_chunks: list[str] = []

    def _drain_stdout() -> None:
        if process.stdout is not None:
            stdout_chunks.append(process.stdout.read())

    stdout_thread = threading.Thread(target=_drain_stdout, daemon=True)
    stdout_thread.start()

    if process.stderr is not None:
        for line in process.stderr:
            message = line.rstrip("\n")
            client.send_log(job_id, sequence=sequence, stream="stderr", message=message)
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
                stdout_thread.join()
                client.cancel_job(job_id)
                return BackupExecutionResult(
                    job_id=job_id,
                    status="canceled",
                    return_code=return_code,
                    message="backup.create canceled",
                )

    return_code = process.wait()
    stdout_thread.join()
    if return_code == 0:
        resolved_archive_name = (
            _parse_created_archive_name("".join(stdout_chunks)) or payload.archive_name
        )
        client.complete_job(
            job_id,
            result={
                "archive_name": resolved_archive_name,
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
    if os.name == "posix" and getattr(process, "pid", None):
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except OSError:
            process.terminate()
    else:
        process.terminate()

    try:
        return process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "posix" and getattr(process, "pid", None):
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except OSError:
                process.kill()
        else:
            process.kill()
        return process.wait(timeout=5)
