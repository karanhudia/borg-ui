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
from urllib.parse import urlsplit

from agent.borg_ui_agent.borg import is_warning_return_code
from agent.borg_ui_agent.borg_flags import parse_borg_flags
from agent.borg_ui_agent.cancel import (
    cancel_requested,
    start_cancel_poller,
    start_keepalive,
)
from agent.borg_ui_agent.client import AgentClient
from agent.borg_ui_agent.failure_report import FailureTail, failure_report


# Borg 2.0.0b25 replaced rest:// by ssh:// (REST over ssh, same path rules)
# and does not reject the old scheme: a URL it does not know is read as a
# local path, so `rest://user@host/repo` names the directory
# `./rest:/user@host/repo` under the working directory. repo-create and
# create succeed there, and the backup never leaves the machine. Stated on
# the server as well (app/core/borg2.py); the two share no imports.
REMOVED_REPOSITORY_URL_MESSAGE = (
    "rest:// repository URLs were removed in Borg 2.0.0b25, which reads one as "
    "a local directory. Use ssh://[user@]host[:port]/path instead (the path "
    "rules are the same), and create the repository anew: 2.0.0b25 cannot "
    "read a repository written by an earlier Borg 2 beta."
)


def ensure_borg2_repository_url(repository: Optional[str]) -> None:
    """Raise ValueError for a repository URL Borg 2 would misread."""
    if (repository or "").strip().lower().startswith("rest://"):
        raise ValueError(REMOVED_REPOSITORY_URL_MESSAGE)


def job_borg_major(repository: dict[str, Any], payload: dict[str, Any]) -> int:
    """The Borg major a job runs on, 1 when the job names none. Every job
    decoder reads it here: anything but 1 or 2 is refused, so no later
    `== 2` check can take an unknown major for Borg 1."""
    value = repository.get("borg_version") or payload.get("borg_version") or 1
    try:
        major = int(value)
    except (TypeError, ValueError):
        major = None
    # int() would also take 2.5 for 2
    if major not in (1, 2) or str(value).strip() != str(major):
        raise ValueError(f"Unsupported Borg major: {value!r}")
    return major


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
        if not isinstance(custom_flags, (str, list)) or (
            isinstance(custom_flags, list)
            and not all(isinstance(flag, str) for flag in custom_flags)
        ):
            raise ValueError("backup.create custom_flags must be a string or list")

        exclude_patterns = backup.get(
            "exclude_patterns", payload.get("exclude_patterns", [])
        )
        if not isinstance(exclude_patterns, list) or not all(
            isinstance(pattern, str) for pattern in exclude_patterns
        ):
            raise ValueError("backup.create exclude_patterns must be a list")

        borg_version = job_borg_major(repository, payload)
        if borg_version == 2:
            ensure_borg2_repository_url(repository_path)
        custom_flags = parse_borg_flags(custom_flags, "create", borg_version)
        upload_ratelimit_kib = backup.get(
            "upload_ratelimit_kib", payload.get("upload_ratelimit_kib")
        )
        if upload_ratelimit_kib is not None:
            upload_ratelimit_kib = int(upload_ratelimit_kib)
            if upload_ratelimit_kib <= 0:
                raise ValueError("backup.create upload_ratelimit_kib must be positive")
        environment = _extract_environment(payload, repository)
        if (
            borg_version == 2
            and upload_ratelimit_kib
            and repository_path.strip().startswith("rclone:")
        ):
            # Borg 2 has no --upload-ratelimit; its rclone backend runs
            # rclone, which reads this (K is KiB) (#1307)
            environment["RCLONE_BWLIMIT"] = f"{upload_ratelimit_kib}K"

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
            # No --upload-ratelimit: Borg 2.0.0b22 removed it (behind rclone the
            # limit is RCLONE_BWLIMIT in the environment instead, #1307). A
            # server before agent 0.1.17 still sends a repository's limit.
            for pattern in self.exclude_patterns:
                cmd.extend(["--exclude", pattern])
            cmd.extend(self.custom_flags)
            cmd.append(self.archive_name)
            cmd.extend(self.source_paths)
            return cmd

        cmd = [
            borg_cmd,
            *borg1_lock_wait_args(self.environment),
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

    # A lock wait sent with the job wins over the agent's default, for the
    # Borg 1 flag and the Borg 2 variable alike.
    environment_source = payload.get("environment")
    if isinstance(environment_source, dict):
        lock_wait = environment_source.get("BORG_LOCK_WAIT")
        if isinstance(lock_wait, str) and lock_wait.isdigit():
            environment["BORG_LOCK_WAIT"] = lock_wait

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
    # Borg 2's pack cache: borgstore serves archive metadata as
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
    # How long borg waits for a held repository lock, the server's value for
    # background jobs. Borg 2 reads it from the environment; Borg 1 ignores
    # the variable and gets it as a flag (borg1_lock_wait_args).
    "BORG_LOCK_WAIT": "180",
}


def env_with_repository_port(
    env: dict[str, str], repository_path: Optional[str]
) -> dict[str, str]:
    """`env` with the port of an ssh:// repository URL in the remote shell
    it names (BORG_RSH, BORGSTORE_RSH), in place.

    Borg 2 hands a remote shell it was given to the store as it is and adds
    the URL's port only to the ssh command it builds itself, so with
    BORG_RSH set `ssh://host:2222/path` connects to port 22. Borg 1 adds the
    port to either; the same port twice does no harm. A remote shell that
    names a port keeps it, and an environment without one needs nothing.
    """
    if not (repository_path or "").startswith("ssh://"):
        return env
    try:
        port = urlsplit(repository_path).port
    except ValueError:
        return env
    if port is None:
        return env
    for name in ("BORG_RSH", "BORGSTORE_RSH"):
        rsh = env.get(name)
        if not rsh:
            continue
        try:
            words = shlex.split(rsh)
        except ValueError:
            continue
        if any(
            word == "-p" or (word.startswith("-p") and word[2:].isdigit())
            for word in words
        ):
            continue
        env[name] = f"{rsh} -p {port}"
    return env


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


def borg1_lock_wait_args(overrides: Optional[dict[str, str]] = None) -> list[str]:
    """`--lock-wait` for a Borg 1 command line, from the same environment the
    command runs with. Borg 1.4 never reads BORG_LOCK_WAIT and defaults to
    1 second, so a held lock fails the job almost at once (#1216)."""
    return ["--lock-wait", build_borg_env(overrides)["BORG_LOCK_WAIT"]]


# The counters `archive_progress` reports while `borg create` runs
ARCHIVE_STATS_FIELDS = (
    "original_size",
    "compressed_size",
    "deduplicated_size",
    "nfiles",
)


# The logger Borg's progress indicators print through
PROGRESS_LOGGER = "borg.output.progress"


def parse_borg_progress(line: str) -> Optional[dict[str, Any]]:
    """The progress report a Borg `--log-json` line makes: None for a line
    that is not a progress line, an empty report for one that has nothing
    to report (a step such as the cache transaction, which no reader
    shows)."""
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
        for key in ARCHIVE_STATS_FIELDS:
            if key in payload:
                progress[key] = payload[key]
        if "path" in payload:
            progress["current_file"] = payload["path"]
        if payload.get("finished"):
            progress["progress_percent"] = 100.0
        return progress

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

    # A progress indicator prints JSON only when it is the only one
    # running; one that starts while another runs (the cache transaction
    # during a prune) prints through the progress logger as a
    # `log_message` instead.
    if msg_type == "progress_message" or (
        msg_type == "log_message" and payload.get("name") == PROGRESS_LOGGER
    ):
        return {}

    return None


def progress_replaces_log_line(progress: Optional[dict[str, Any]]) -> bool:
    """Whether the progress report parsed from a line says all the line did,
    so the line is not stored as a log line too. A `file_status` line
    (`create --list`) is both: it names the current file, and it is the
    listing the operator asked for."""
    return progress is not None and set(progress) != {"current_file"}


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


def _parse_created_archive_id(stdout: str) -> Optional[str]:
    """The id borg reported for the archive it made (``archive.id`` of the
    ``borg create --json`` document), or None when there is none."""
    if not stdout or not stdout.strip():
        return None
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    archive = data.get("archive") if isinstance(data, dict) else None
    archive_id = archive.get("id") if isinstance(archive, dict) else None
    if isinstance(archive_id, str) and archive_id.strip():
        return archive_id.strip()
    return None


def _parse_created_archive_stats(stdout: str) -> Optional[dict[str, int]]:
    """The final counters of the archive ``borg create --json`` made
    (``archive.stats``), or None when there are none.

    Borg reports ``archive_progress`` at most once a second, and its last
    one (``finished``) carries no counters, so the progress reports never
    hold the final figures. Borg 2 reports no ``compressed_size`` or
    ``deduplicated_size`` here; only the fields present are returned.
    """
    if not stdout or not stdout.strip():
        return None
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    archive = data.get("archive") if isinstance(data, dict) else None
    stats = archive.get("stats") if isinstance(archive, dict) else None
    if not isinstance(stats, dict):
        return None
    counters = {
        key: stats[key]
        for key in ARCHIVE_STATS_FIELDS
        if isinstance(stats.get(key), int) and not isinstance(stats[key], bool)
    }
    return counters or None


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
    env_with_repository_port(env, payload.repository_path)
    if payload.borg_version == 2 and payload.remote_path:
        # Borg 2 has no --remote-path.
        env["BORG_REMOTE_PATH"] = payload.remote_path

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
    # The last plain lines borg wrote, for the failure report.
    failure_tail = FailureTail()
    try:
        if process.stderr is not None:
            for line in process.stderr:
                message = line.rstrip("\n")
                failure_tail.append(message)
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
        stdout = "".join(stdout_chunks)
        result: dict[str, Any] = {
            "archive_name": _parse_created_archive_name(stdout) or payload.archive_name,
            "return_code": return_code,
            "command": cmd,
        }
        # The final counters travel with the outcome: the progress reports
        # go another way and may arrive after it, or never hold them.
        archive_stats = _parse_created_archive_stats(stdout)
        if archive_stats:
            result["archive_stats"] = archive_stats
        # The server's post-backup restore check targets this exact archive.
        archive_id = _parse_created_archive_id(stdout)
        if archive_id:
            result["archive_id"] = archive_id
        client.complete_job(job_id, result=result)
        return BackupExecutionResult(
            job_id=job_id,
            status="completed" if return_code == 0 else "completed_with_warnings",
            return_code=return_code,
            message=f"borg create exited with code {return_code}",
        )

    error_message = f"borg create exited with code {return_code}"
    client.fail_job(
        job_id,
        error_message=error_message,
        return_code=return_code,
        **failure_report(return_code, failure_tail.lines()),
    )
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
