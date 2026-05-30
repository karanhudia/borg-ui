from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import tempfile
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
    "repository.check",
    "repository.prune",
    "repository.compact",
    "repository.rclone_sync",
}


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
                return [*self._base_borg2("list"), "--json"]
            return [*self._base_borg1("list"), "--json", self.repository_path]

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
