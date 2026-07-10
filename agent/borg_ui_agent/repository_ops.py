from __future__ import annotations

import base64
import json
import os
import shlex
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from agent.borg_ui_agent.backup import _extract_environment, parse_borg_progress
from agent.borg_ui_agent.client import AgentClient


REPOSITORY_JOB_KINDS = {
    "repository.init",
    "repository.info",
    "repository.list_archives",
    "repository.list_archive_contents",
    "repository.extract_archive_file",
    "repository.check",
    "repository.prune",
    "repository.compact",
    "repository.rclone_sync",
}

# Kill a streaming extract only when no bytes have flowed for this long — a
# wedged borg, not a slow one. Idle (not an absolute cap) so a legitimately
# large/slow download is never truncated mid-transfer.
STREAM_EXTRACT_IDLE_SECONDS = 300


@dataclass(frozen=True)
class RepositoryOperationResult:
    job_id: int
    status: str
    return_code: Optional[int] = None
    message: str = ""


@dataclass(frozen=True)
class RepositoryOperationPayload:
    job_kind: str
    repository_path: str
    borg_version: int = 1
    borg_binary: Optional[str] = None
    remote_path: Optional[str] = None
    operation: dict[str, Any] | None = None
    environment: dict[str, str] | None = None

    @classmethod
    def from_job_payload(cls, payload: dict[str, Any]) -> "RepositoryOperationPayload":
        repository = payload.get("repository") or {}
        job_kind = str(payload.get("job_kind") or "")
        if job_kind not in REPOSITORY_JOB_KINDS:
            raise ValueError(f"unsupported repository job kind: {job_kind}")

        repository_path = repository.get("path") or payload.get("repository_path")
        if not isinstance(repository_path, str) or not repository_path.strip():
            raise ValueError("repository operation payload requires repository.path")

        borg_version = int(
            repository.get("borg_version") or payload.get("borg_version") or 1
        )
        return cls(
            job_kind=job_kind,
            repository_path=repository_path.strip(),
            borg_version=borg_version,
            borg_binary=repository.get("borg_binary") or payload.get("borg_binary"),
            remote_path=repository.get("remote_path") or payload.get("remote_path"),
            operation=payload.get("operation") or {},
            environment=_extract_environment(payload, repository),
        )

    @property
    def borg_cmd(self) -> str:
        return self.borg_binary or ("borg2" if self.borg_version == 2 else "borg")

    def _base_borg1(self, subcommand: str) -> list[str]:
        cmd = [self.borg_cmd, subcommand]
        if self.remote_path:
            cmd.extend(["--remote-path", self.remote_path])
        return cmd

    def _base_borg2(self, subcommand: str) -> list[str]:
        cmd = [self.borg_cmd, "-r", self.repository_path, subcommand]
        if self.remote_path:
            cmd.extend(["--remote-path", self.remote_path])
        return cmd

    def build_command(self, *, rclone_config_path: Optional[str] = None) -> list[str]:
        if self.job_kind == "repository.rclone_sync":
            rclone = _rclone_operation(self.operation)
            remote_name = _require_non_empty_string(
                rclone.get("remote_name"), "rclone remote_name"
            )
            remote_path = _require_non_empty_string(
                rclone.get("remote_path"), "rclone remote_path"
            )
            source_path = (
                str(rclone.get("source_path")).strip()
                if rclone.get("source_path")
                else self.repository_path
            )
            if not source_path:
                raise ValueError("repository.rclone_sync requires a source path")
            if not rclone_config_path:
                raise ValueError("repository.rclone_sync requires a rclone config path")
            return [
                "rclone",
                "--config",
                rclone_config_path,
                "sync",
                source_path,
                f"{remote_name}:{remote_path}",
                *_split_flags(rclone.get("extra_flags")),
            ]

        if self.job_kind == "repository.init":
            operation = self.operation or {}
            if not isinstance(operation, dict):
                raise ValueError("repository.init requires operation.encryption")
            encryption = operation.get("encryption")
            if not isinstance(encryption, str) or not encryption.strip():
                raise ValueError("repository.init requires operation.encryption")
            encryption = encryption.strip()
            if self.borg_version == 2:
                return [
                    *self._base_borg2("repo-create"),
                    "--encryption",
                    encryption,
                ]
            return [
                *self._base_borg1("init"),
                "--encryption",
                encryption,
                self.repository_path,
            ]

        if self.job_kind == "repository.info":
            if self.borg_version == 2:
                return [*self._base_borg2("info"), "--json"]
            return [*self._base_borg1("info"), "--json", self.repository_path]

        if self.job_kind == "repository.list_archives":
            if self.borg_version == 2:
                return [*self._base_borg2("repo-list"), "--json"]
            return [*self._base_borg1("list"), "--json", self.repository_path]

        if self.job_kind == "repository.list_archive_contents":
            archive = _operation_archive(self.operation, self.job_kind)
            if self.borg_version == 2:
                cmd = [*self._base_borg2("list"), "--json-lines", archive]
                path = (self.operation or {}).get("path")
                if isinstance(path, str) and path.strip():
                    normalized_path = path.strip("/")
                    if normalized_path:
                        cmd.append(normalized_path)
                return cmd
            return [
                *self._base_borg1("list"),
                f"{self.repository_path}::{archive}",
                "--json-lines",
            ]

        if self.job_kind == "repository.extract_archive_file":
            archive = _operation_archive(self.operation, self.job_kind)
            file_path = _operation_file_path(self.operation, self.job_kind)
            if self.borg_version == 2:
                return [
                    *self._base_borg2("extract"),
                    "--stdout",
                    archive,
                    file_path,
                ]
            return [
                *self._base_borg1("extract"),
                "--stdout",
                f"{self.repository_path}::{archive}",
                file_path,
            ]

        if self.job_kind == "repository.check":
            extra_flags = _split_flags((self.operation or {}).get("check_extra_flags"))
            max_duration = (self.operation or {}).get("max_duration")
            if self.borg_version == 2:
                cmd = [*self._base_borg2("check"), "--progress", "--log-json"]
            else:
                cmd = [*self._base_borg1("check"), "--progress", "--log-json"]
            if max_duration:
                cmd.extend(["--repository-only", "--max-duration", str(max_duration)])
            cmd.extend(extra_flags)
            if self.borg_version == 1:
                cmd.append(self.repository_path)
            return cmd

        if self.job_kind == "repository.compact":
            if self.borg_version == 2:
                return [
                    *self._base_borg2("compact"),
                    "--progress",
                    "--verbose",
                    "--log-json",
                ]
            return [
                *self._base_borg1("compact"),
                "--progress",
                "--verbose",
                "--log-json",
                self.repository_path,
            ]

        if self.job_kind == "repository.prune":
            operation = self.operation or {}
            dry_run = bool(operation.get("dry_run", False))
            keep_flags = [
                ("keep_hourly", "--keep-hourly"),
                ("keep_daily", "--keep-daily"),
                ("keep_weekly", "--keep-weekly"),
                ("keep_monthly", "--keep-monthly"),
                ("keep_quarterly", "--keep-quarterly"),
                ("keep_yearly", "--keep-yearly"),
            ]
            if self.borg_version == 2:
                cmd = [
                    *self._base_borg2("prune"),
                    "--progress",
                    "--stats",
                    "--show-rc",
                    "--log-json",
                ]
            else:
                cmd = [
                    *self._base_borg1("prune"),
                    "--progress",
                    "--stats",
                    "--show-rc",
                    "--log-json",
                ]
            for key, flag in keep_flags:
                value = operation.get(key)
                if value is not None:
                    cmd.extend([flag, str(int(value))])
            keep_within = operation.get("keep_within")
            if keep_within is not None and str(keep_within).strip():
                cmd.append(f"--keep-within={str(keep_within).strip()}")
            if dry_run:
                cmd.append("--dry-run")
            if self.borg_version == 1:
                cmd.append(self.repository_path)
            return cmd

        raise ValueError(f"unsupported repository job kind: {self.job_kind}")


def _split_flags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return shlex.split(value)
    raise ValueError("repository operation flags must be a string or list")


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"repository.rclone_sync requires {field_name}")
    return value.strip()


def _rclone_operation(operation: dict[str, Any] | None) -> dict[str, Any]:
    rclone = (operation or {}).get("rclone")
    if not isinstance(rclone, dict):
        raise ValueError("repository.rclone_sync requires operation.rclone")
    return rclone


def _operation_archive(operation: dict[str, Any] | None, job_kind: str) -> str:
    if not isinstance(operation, dict):
        raise ValueError(f"{job_kind} requires operation.archive")
    archive = operation.get("archive")
    if not isinstance(archive, str) or not archive.strip():
        raise ValueError(f"{job_kind} requires operation.archive")
    return archive.strip()


def _operation_file_path(operation: dict[str, Any] | None, job_kind: str) -> str:
    if not isinstance(operation, dict):
        raise ValueError(f"{job_kind} requires operation.file_path")
    file_path = operation.get("file_path")
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError(f"{job_kind} requires operation.file_path")
    normalized = file_path.strip().strip("/")
    if not normalized:
        raise ValueError(f"{job_kind} requires operation.file_path")
    return normalized


def _write_temp_rclone_config(payload: RepositoryOperationPayload) -> str:
    rclone = _rclone_operation(payload.operation)
    remote_name = _require_non_empty_string(rclone.get("remote_name"), "remote_name")
    config = rclone.get("config")
    if not isinstance(config, dict) or not config:
        raise ValueError("repository.rclone_sync requires rclone config")
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", prefix="borg-ui-rclone-", suffix=".conf", delete=False
    )
    path = Path(handle.name)
    try:
        try:
            handle.write(f"[{remote_name}]\n")
            for key, value in config.items():
                if value is None or not str(key).strip():
                    continue
                handle.write(f"{key} = {_stringify_config_value(value)}\n")
        finally:
            handle.close()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return str(path)


def _stringify_config_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def execute_repository_operation_job(
    job: dict[str, Any],
    client: AgentClient,
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> RepositoryOperationResult:
    job_id = int(job["id"])
    rclone_config_path: Optional[str] = None
    try:
        payload = RepositoryOperationPayload.from_job_payload(job.get("payload") or {})
        try:
            if payload.job_kind == "repository.rclone_sync":
                rclone_config_path = _write_temp_rclone_config(payload)
                cmd = payload.build_command(rclone_config_path=rclone_config_path)
            else:
                cmd = payload.build_command()
        except Exception:
            _remove_temp_file(rclone_config_path)
            raise
    except (TypeError, ValueError) as exc:
        error_message = f"Invalid repository operation payload: {exc}"
        client.send_log(job_id, sequence=0, stream="stderr", message=error_message)
        client.fail_job(job_id, error_message=error_message)
        return RepositoryOperationResult(
            job_id=job_id, status="failed", message=error_message
        )

    env = os.environ.copy()
    env.update(payload.environment or {})
    sequence = 0
    client.send_log(
        job_id,
        sequence=sequence,
        stream="stdout",
        message=f"Starting {payload.job_kind}: {shlex.join(cmd)}",
    )
    sequence += 1

    if payload.job_kind in {"repository.info", "repository.list_archives"}:
        try:
            return _execute_short_repository_operation(
                job_id, payload, client, cmd, env
            )
        finally:
            _remove_temp_file(rclone_config_path)

    if payload.job_kind == "repository.list_archive_contents":
        try:
            return _execute_limited_output_repository_operation(
                job_id, payload, client, cmd, env
            )
        finally:
            _remove_temp_file(rclone_config_path)

    if payload.job_kind == "repository.extract_archive_file":
        try:
            return _execute_binary_output_repository_operation(
                job_id, payload, client, cmd, env, should_cancel=should_cancel
            )
        finally:
            _remove_temp_file(rclone_config_path)

    try:
        return _execute_streaming_repository_operation(
            job_id,
            payload,
            client,
            cmd,
            env,
            initial_sequence=sequence,
            should_cancel=should_cancel,
        )
    finally:
        _remove_temp_file(rclone_config_path)


def _remove_temp_file(path: Optional[str]) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _execute_short_repository_operation(
    job_id: int,
    payload: RepositoryOperationPayload,
    client: AgentClient,
    cmd: list[str],
    env: dict[str, str],
) -> RepositoryOperationResult:
    try:
        process = subprocess.run(
            cmd, text=True, capture_output=True, env=env, timeout=300
        )
    except OSError as exc:
        error_message = f"Failed to start {payload.job_kind}: {exc}"
        client.send_log(job_id, sequence=1, stream="stderr", message=error_message)
        client.fail_job(job_id, error_message=error_message)
        return RepositoryOperationResult(
            job_id=job_id, status="failed", message=error_message
        )
    except subprocess.TimeoutExpired:
        error_message = f"{payload.job_kind} timed out"
        client.send_log(job_id, sequence=1, stream="stderr", message=error_message)
        client.fail_job(job_id, error_message=error_message)
        return RepositoryOperationResult(
            job_id=job_id, status="failed", message=error_message
        )

    if process.stdout:
        client.send_log(
            job_id, sequence=1, stream="stdout", message=process.stdout.rstrip()
        )
    if process.stderr:
        client.send_log(
            job_id, sequence=2, stream="stderr", message=process.stderr.rstrip()
        )

    if process.returncode == 0:
        parsed = _parse_json_output(process.stdout)
        client.complete_job(
            job_id,
            result={
                "return_code": process.returncode,
                "command": cmd,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "data": parsed,
            },
        )
        return RepositoryOperationResult(
            job_id=job_id,
            status="completed",
            return_code=process.returncode,
            message=f"{payload.job_kind} exited with code {process.returncode}",
        )

    error_message = f"{payload.job_kind} exited with code {process.returncode}"
    client.fail_job(job_id, error_message=error_message, return_code=process.returncode)
    return RepositoryOperationResult(
        job_id=job_id,
        status="failed",
        return_code=process.returncode,
        message=error_message,
    )


def _execute_limited_output_repository_operation(
    job_id: int,
    payload: RepositoryOperationPayload,
    client: AgentClient,
    cmd: list[str],
    env: dict[str, str],
) -> RepositoryOperationResult:
    max_lines = _operation_max_lines(payload.operation)
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=os.name == "posix",
        )
    except OSError as exc:
        error_message = f"Failed to start {payload.job_kind}: {exc}"
        client.send_log(job_id, sequence=1, stream="stderr", message=error_message)
        client.fail_job(job_id, error_message=error_message)
        return RepositoryOperationResult(
            job_id=job_id, status="failed", message=error_message
        )

    stdout_lines: list[str] = []
    line_count = 0
    line_count_exceeded = False
    return_code: int | None = None
    if process.stdout is not None:
        for line in process.stdout:
            line_count += 1
            if line_count > max_lines:
                line_count_exceeded = True
                return_code = _terminate_process(process)
                break
            stdout_lines.append(line.rstrip("\n"))

    stderr = process.stderr.read() if process.stderr is not None else ""
    if return_code is None:
        return_code = process.wait()

    result = {
        "return_code": return_code,
        "command": cmd,
        "stdout": "\n".join(stdout_lines),
        "stderr": stderr,
        "success": return_code == 0 and not line_count_exceeded,
        "line_count_exceeded": line_count_exceeded,
        "lines_read": line_count,
    }

    if line_count_exceeded:
        message = f"{payload.job_kind} exceeded max line count"
        client.send_log(job_id, sequence=1, stream="stderr", message=message)
        client.complete_job(job_id, result=result)
        return RepositoryOperationResult(
            job_id=job_id,
            status="completed",
            return_code=return_code,
            message=message,
        )

    if return_code == 0:
        client.complete_job(job_id, result=result)
        return RepositoryOperationResult(
            job_id=job_id,
            status="completed",
            return_code=return_code,
            message=f"{payload.job_kind} exited with code {return_code}",
        )

    if stderr:
        client.send_log(job_id, sequence=1, stream="stderr", message=stderr.rstrip())
    error_message = f"{payload.job_kind} exited with code {return_code}"
    client.fail_job(job_id, error_message=error_message, return_code=return_code)
    return RepositoryOperationResult(
        job_id=job_id,
        status="failed",
        return_code=return_code,
        message=error_message,
    )


def _operation_max_lines(operation: dict[str, Any] | None) -> int:
    value = (operation or {}).get("max_lines")
    try:
        max_lines = int(value)
    except (TypeError, ValueError):
        return 1_000_000
    return max(1, max_lines)


class _ActivityTrackingReader:
    """Wrap a readable stream and record when it last yielded data.

    Lets the streaming watchdog tell an actively-transferring extract (bytes
    flowing) from a wedged one (read blocked, no data) without capping the total
    duration, so legitimately large/slow downloads are never truncated.
    """

    def __init__(self, stream: Any):
        self._stream = stream
        self.last_activity = time.monotonic()

    def read(self, *args: Any) -> bytes:
        chunk = self._stream.read(*args)
        if chunk:
            self.last_activity = time.monotonic()
        return chunk

    def close(self) -> None:
        self._stream.close()


def _execute_streaming_artifact_operation(
    job_id: int,
    payload: RepositoryOperationPayload,
    client: AgentClient,
    cmd: list[str],
    env: dict[str, str],
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> RepositoryOperationResult:
    """Stream `borg extract --stdout` straight to the server over HTTP.

    The file content never enters the WebSocket, so it works at any size. stderr
    is drained on a thread so a full stderr pipe can't deadlock the stdout the
    upload is reading. A watchdog terminates borg on cancellation or if it wedges
    past a deadline, so a hung process can't pin this worker — terminating closes
    stdout, which unblocks the upload read below.
    """
    try:
        popen_kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "env": env,
        }
        if os.name == "posix":
            # Own session so the watchdog's process-group SIGTERM hits only borg.
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(cmd, **popen_kwargs)
    except OSError as exc:
        error_message = f"Failed to start {payload.job_kind}: {exc}"
        client.send_log(job_id, sequence=1, stream="stderr", message=error_message)
        client.fail_job(job_id, error_message=error_message)
        return RepositoryOperationResult(
            job_id=job_id, status="failed", message=error_message
        )

    stderr_chunks: list[bytes] = []

    def _drain_stderr() -> None:
        if process.stderr is not None:
            stderr_chunks.append(process.stderr.read())

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    cancelled = threading.Event()
    timed_out = threading.Event()
    watchdog_done = threading.Event()

    reader = _ActivityTrackingReader(process.stdout)

    def _watchdog() -> None:
        while not watchdog_done.wait(0.5):
            if process.poll() is not None:
                return
            if should_cancel is not None and should_cancel():
                cancelled.set()
                _terminate_process(process)
                return
            # Idle, not absolute: only kill borg once no bytes have flowed for
            # the timeout, so an actively-streaming large transfer is not cut off.
            if time.monotonic() - reader.last_activity >= STREAM_EXTRACT_IDLE_SECONDS:
                timed_out.set()
                _terminate_process(process)
                return

    watchdog = threading.Thread(target=_watchdog, daemon=True)
    watchdog.start()

    upload_error: Optional[BaseException] = None
    try:
        client.upload_artifact(job_id, reader)
    except BaseException as exc:  # noqa: BLE001 - reported below
        upload_error = exc
    finally:
        # Closing stdout makes borg see EPIPE and exit if the upload broke.
        if process.stdout is not None:
            try:
                process.stdout.close()
            except OSError:
                pass

    return_code = process.wait()
    watchdog_done.set()
    watchdog.join(timeout=5)
    stderr_thread.join()
    stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")

    if cancelled.is_set():
        client.cancel_job(job_id)
        return RepositoryOperationResult(
            job_id=job_id,
            status="canceled",
            return_code=return_code,
            message=f"{payload.job_kind} canceled",
        )

    if timed_out.is_set():
        error_message = (
            f"{payload.job_kind} stalled: no output for {STREAM_EXTRACT_IDLE_SECONDS}s"
        )
        client.fail_job(job_id, error_message=error_message, return_code=return_code)
        return RepositoryOperationResult(
            job_id=job_id,
            status="failed",
            return_code=return_code,
            message=error_message,
        )

    if upload_error is not None:
        error_message = f"{payload.job_kind} artifact upload failed: {upload_error}"
        client.fail_job(job_id, error_message=error_message, return_code=return_code)
        return RepositoryOperationResult(
            job_id=job_id,
            status="failed",
            return_code=return_code,
            message=error_message,
        )

    if return_code == 0:
        client.complete_job(
            job_id,
            result={"return_code": return_code, "command": cmd, "artifact": True},
        )
        return RepositoryOperationResult(
            job_id=job_id,
            status="completed",
            return_code=return_code,
            message=f"{payload.job_kind} exited with code {return_code}",
        )

    if stderr:
        client.send_log(job_id, sequence=1, stream="stderr", message=stderr.rstrip())
    error_message = f"{payload.job_kind} exited with code {return_code}"
    client.fail_job(job_id, error_message=error_message, return_code=return_code)
    return RepositoryOperationResult(
        job_id=job_id,
        status="failed",
        return_code=return_code,
        message=error_message,
    )


def _execute_binary_output_repository_operation(
    job_id: int,
    payload: RepositoryOperationPayload,
    client: AgentClient,
    cmd: list[str],
    env: dict[str, str],
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> RepositoryOperationResult:
    operation = payload.operation or {}
    if operation.get("delivery") == "artifact" and hasattr(client, "upload_artifact"):
        return _execute_streaming_artifact_operation(
            job_id, payload, client, cmd, env, should_cancel=should_cancel
        )

    try:
        process = subprocess.run(cmd, capture_output=True, env=env, timeout=300)
    except OSError as exc:
        error_message = f"Failed to start {payload.job_kind}: {exc}"
        client.send_log(job_id, sequence=1, stream="stderr", message=error_message)
        client.complete_job(
            job_id,
            result={
                "return_code": None,
                "command": cmd,
                "stdout": "",
                "stderr": error_message,
                "success": False,
            },
        )
        return RepositoryOperationResult(
            job_id=job_id, status="completed", message=error_message
        )
    except subprocess.TimeoutExpired:
        error_message = f"{payload.job_kind} timed out"
        client.send_log(job_id, sequence=1, stream="stderr", message=error_message)
        client.complete_job(
            job_id,
            result={
                "return_code": None,
                "command": cmd,
                "stdout": "",
                "stderr": error_message,
                "success": False,
            },
        )
        return RepositoryOperationResult(
            job_id=job_id, status="completed", message=error_message
        )

    stderr = process.stderr.decode("utf-8", errors="replace")
    result = {
        "return_code": process.returncode,
        "command": cmd,
        "stdout": "",
        "stderr": stderr,
        "success": process.returncode == 0,
    }
    if process.returncode == 0:
        result["content_base64"] = base64.b64encode(process.stdout).decode("ascii")
        client.complete_job(job_id, result=result)
        return RepositoryOperationResult(
            job_id=job_id,
            status="completed",
            return_code=process.returncode,
            message=f"{payload.job_kind} exited with code {process.returncode}",
        )

    if stderr:
        client.send_log(job_id, sequence=1, stream="stderr", message=stderr.rstrip())
    client.complete_job(job_id, result=result)
    return RepositoryOperationResult(
        job_id=job_id,
        status="completed",
        return_code=process.returncode,
        message=f"{payload.job_kind} exited with code {process.returncode}",
    )


def _execute_streaming_repository_operation(
    job_id: int,
    payload: RepositoryOperationPayload,
    client: AgentClient,
    cmd: list[str],
    env: dict[str, str],
    *,
    initial_sequence: int,
    should_cancel: Optional[Callable[[], bool]],
) -> RepositoryOperationResult:
    try:
        popen_kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "env": env,
        }
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(cmd, **popen_kwargs)
    except OSError as exc:
        error_message = f"Failed to start {payload.job_kind}: {exc}"
        client.send_log(
            job_id, sequence=initial_sequence, stream="stderr", message=error_message
        )
        client.fail_job(job_id, error_message=error_message)
        return RepositoryOperationResult(
            job_id=job_id, status="failed", message=error_message
        )

    sequence = initial_sequence
    if process.stdout is not None:
        for line in process.stdout:
            message = line.rstrip("\n")
            client.send_log(job_id, sequence=sequence, stream="stdout", message=message)
            sequence += 1
            progress = parse_borg_progress(message)
            if progress:
                client.send_progress(job_id, progress)
            if should_cancel and should_cancel():
                return_code = _terminate_process(process)
                client.cancel_job(job_id)
                return RepositoryOperationResult(
                    job_id=job_id,
                    status="canceled",
                    return_code=return_code,
                    message=f"{payload.job_kind} canceled",
                )

    return_code = process.wait()
    if return_code == 0:
        client.complete_job(
            job_id,
            result={"return_code": return_code, "command": cmd, "status": "completed"},
        )
        return RepositoryOperationResult(
            job_id=job_id,
            status="completed",
            return_code=return_code,
            message=f"{payload.job_kind} exited with code {return_code}",
        )

    error_message = f"{payload.job_kind} exited with code {return_code}"
    client.fail_job(job_id, error_message=error_message, return_code=return_code)
    return RepositoryOperationResult(
        job_id=job_id,
        status="failed",
        return_code=return_code,
        message=error_message,
    )


def _parse_json_output(stdout: str) -> Any:
    if not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _terminate_process(process: subprocess.Popen) -> int | None:
    if process.poll() is not None:
        return process.returncode
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()
        return process.wait(timeout=10)
    except Exception:
        try:
            process.kill()
        except Exception:
            return process.poll()
        return process.wait(timeout=10)
