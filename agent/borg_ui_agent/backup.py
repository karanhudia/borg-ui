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

from agent.borg_ui_agent.borg import is_warning_return_code
from agent.borg_ui_agent.cancel import (
    cancel_requested,
    start_cancel_poller,
    start_keepalive,
)
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


# borg prompts interactively on first access to an unknown *unencrypted* repo
# ("Attempting to access a previously unknown unencrypted repository! ... [yN]")
# and again when a repository looks relocated. A managed agent runs borg
# non-interactively, so those prompts hang (or abort with rc=2) every operation
# on such a repository — which surfaces in the UI as empty stats (0 archives /
# N/A size / never). Opt into non-interactive access exactly like the server
# side does. Respected by borg 1.x and borg 2.
_BORG_NONINTERACTIVE_ACCESS_DEFAULTS = {
    "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK": "yes",
    "BORG_RELOCATED_REPO_ACCESS_IS_OK": "yes",
    # Borg 2.0.0b23's pack cache: borgstore serves archive metadata as
    # whole-pack loads, so on remote repositories every listing re-transfers
    # packs. The writethrough cache under borg's own cache directory downloads
    # each pack once. Applied via setdefault like the flags above, so the
    # container environment can resize it or disable it (BORG_STORE_CACHE="").
    # Borg 1 ignores both variables.
    "BORG_STORE_CACHE": "1",
    "BORG_PACK_CACHE_SIZE": str(2 * 1024**3),
    # Borg's modern exit codes (0 success, 2-99 errors, 100-127 warnings), so
    # an agent's Borg 1 reports failures in the same vocabulary the server's
    # does and `is_warning_return_code` sees the range it already accepts.
    # Borg 2 uses them anyway. setdefault like the rest: an operator can pin
    # "legacy", and a per-job override from the server still wins.
    "BORG_EXIT_CODES": "modern",
}


def build_borg_env(overrides: Optional[dict[str, str]] = None) -> dict[str, str]:
    """Build the environment for a borg subprocess launched by the agent.

    Starts from the agent process environment, layers the non-interactive
    access defaults (only where not already set, so an explicit container
    setting still wins), then applies the per-job overrides last so a value
    sent by the server is never clobbered.
    """
    env = os.environ.copy()
    for key, value in _BORG_NONINTERACTIVE_ACCESS_DEFAULTS.items():
        env.setdefault(key, value)
    if overrides:
        env.update(overrides)
    return env


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
            progress = {"progress_percent": float(current / total * 100.0)}
            # `borg extract` names the file it is at in `info`
            info = payload.get("info")
            if isinstance(info, list) and info and isinstance(info[0], str):
                progress["current_file"] = info[0]
            return progress

    if msg_type == "file_status" and payload.get("path"):
        return {"current_file": payload["path"]}

    return None


def progress_replaces_log_line(progress: Optional[dict[str, Any]]) -> bool:
    """Whether the progress report parsed from a line says all the line did,
    so the line is not stored as a log line too. A `file_status` line
    (`create --list`) is both: it names the current file, and it is the
    listing the operator asked for."""
    return bool(progress) and set(progress) != {"current_file"}


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
    env = build_borg_env(payload.environment)

    sequence = 0
    client.send_log(
        job_id,
        sequence=sequence,
        stream="stdout",
        message=f"Starting backup.create: {shlex.join(cmd)}",
    )
    sequence += 1

    if cancel_requested(should_cancel):
        # Cancelled between dispatch and start (the log above may have
        # waited on the server): nothing to stop yet.
        client.cancel_job(job_id)
        return BackupExecutionResult(
            job_id=job_id,
            status="canceled",
            message="backup.create canceled before it started",
        )

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

    done = threading.Event()
    # The per-line check answers at once while borg reports progress; the
    # poller reaches a borg that is silent (a lock wait, a stalled store).
    cancelled = start_cancel_poller(process, should_cancel, done, _terminate_process)
    start_keepalive(process, client, job_id, done)
    try:
        if process.stderr is not None:
            for line in process.stderr:
                message = line.rstrip("\n")
                progress = parse_borg_progress(message)
                if progress:
                    client.send_progress(job_id, progress)
                if not progress_replaces_log_line(progress):
                    client.send_log(
                        job_id, sequence=sequence, stream="stderr", message=message
                    )
                    sequence += 1
                if cancel_requested(should_cancel) and process.poll() is None:
                    # not once Borg ended on its own while the check ran (it
                    # may have asked the server): that run is its verdict
                    cancelled.set()
                    _terminate_process(process)
                    break
        return_code = process.wait()
    except BaseException:
        # A report that failed (the server unreachable) unwinds this worker;
        # borg create must not run on unsupervised, holding the repository.
        _terminate_process(process)
        raise
    finally:
        done.set()
    stdout_thread.join()

    if cancelled.is_set():
        client.send_log(
            job_id,
            sequence=sequence,
            stream="stderr",
            message="Cancellation requested; stopped borg create",
        )
        client.cancel_job(job_id)
        return BackupExecutionResult(
            job_id=job_id,
            status="canceled",
            return_code=return_code,
            message="backup.create canceled",
        )
    if return_code == 0 or is_warning_return_code(return_code):
        # Warnings (rc 1 / 100-127) still produced an archive: complete the
        # job and let the server record completed_with_warnings from the
        # return code, matching how server-side backups are classified.
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
            status="completed" if return_code == 0 else "completed_with_warnings",
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
    if process.poll() is not None:
        # Already reaped: its pid may be another process's by now.
        return process.returncode
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
