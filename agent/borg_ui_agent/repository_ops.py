from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import selectors
import shlex
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from agent.borg_ui_agent.backup import (
    _extract_environment,
    build_borg_env,
    parse_borg_progress,
    progress_replaces_log_line,
)
from agent.borg_ui_agent.borg import is_warning_return_code
from agent.borg_ui_agent.cancel import (
    KILL_GROUP_AFTER_SECONDS,
    SELF_CANCELLING_JOB_KINDS,
    cancel_requested,
    kill_process_group,
    start_cancel_poller,
    start_keepalive,
)
from agent.borg_ui_agent.client import AgentClient
from agent.borg_ui_agent.compact_stats import (
    TAIL_LINES,
    has_compact_stats,
    parse_borg_version,
    parse_compact_stats,
)


REPOSITORY_JOB_KINDS = {
    "repository.init",
    "repository.info",
    "repository.rinfo",
    "repository.archive_info",
    "repository.list_archives",
    "repository.delete_archive",
    "repository.break_lock",
    "repository.list_archive_contents",
    "repository.extract_archive_file",
    "repository.export_archive_tar",
    "repository.restore",
    "repository.check",
    "repository.prune",
    "repository.compact",
    "repository.rclone_sync",
    "repository.disk_usage",
    "repository.storage_usage",
    "repository.diff",
}

# Kinds whose stdout the server parses timestamps out of. These run under
# TZ=UTC so borg1's naive rendering is UTC wall clock; borg2 renders an
# explicit offset either way. Contents listings (browse) stay in the machine
# zone - their mtimes are relayed for display, not interpreted.
MACHINE_PARSED_JOB_KINDS = {
    "repository.info",
    "repository.rinfo",
    "repository.archive_info",
    "repository.list_archives",
    "repository.diff",
}

# Borg 2.0.0b22 split repo-create's single --encryption value into the cipher,
# where the key is stored, and the id hash. The server sends the combined mode
# name it stores, so the agent translates it the same way the server does for
# its own repositories (app/core/borg2.py: BORG2_ENCRYPTION_FLAGS). The two are
# separate packages and share no imports, so the table is stated twice; a mode
# missing here is rejected up front with the mode name, mirroring the server —
# passing it to repo-create would fail with an argument-parsing error that
# does not name the actual problem. b23 folded the id hash into the mode name
# for the unencrypted modes (no alias for the plain b22 names); the sha256
# variants keep exactly what `authenticated`/`none` produced before.
BORG2_ENCRYPTION_FLAGS = {
    "repokey-aes-ocb": ["--encryption", "aes256-ocb", "--key-location", "repokey"],
    "repokey-chacha20-poly1305": [
        "--encryption",
        "chacha20-poly1305",
        "--key-location",
        "repokey",
    ],
    "keyfile-aes-ocb": ["--encryption", "aes256-ocb", "--key-location", "keyfile"],
    "keyfile-chacha20-poly1305": [
        "--encryption",
        "chacha20-poly1305",
        "--key-location",
        "keyfile",
    ],
    "authenticated": ["--encryption", "authenticated-sha256"],
    "none": ["--encryption", "none-sha256"],
}

# Kill a streaming extract only when no bytes have flowed for this long — a
# wedged borg, not a slow one. Idle (not an absolute cap) so a legitimately
# large/slow download is never truncated mid-transfer.
STREAM_EXTRACT_IDLE_SECONDS = 300

# A change listing prints a line per changed path and nothing while it
# compares unchanged ones, so stdout silence says nothing about a diff.
# Its bound is absolute instead: the server's budget from the payload
# (`timeout_seconds`), else an hour. A wedged borg looks like a healthy
# one comparing unchanged paths (the padding below keeps the upload
# alive either way), so the fallback is how long the repository may be
# held by a listing that never ends, not how long a listing may take: a
# longer one gets its budget from the server.
STREAM_DIFF_MAX_SECONDS = 3600

# While a stream runs, the job row on the server sees no activity: logs and
# the result arrive at the end, and the heartbeat only lists the job. The
# server reaps an in-flight job after 15 minutes without activity
# (app/services/agent_job_reaper.py), so the watchdog reports a progress
# keepalive this often. Well inside the reaper's window, and cheap.
STREAM_KEEPALIVE_SECONDS = 60

# A diff's upload carries no bytes while borg compares unchanged paths, and
# a reverse proxy in front of the server may cut a request body that is
# idle for a minute (nginx's proxy_read_timeout default). The diff stream
# is padded with a bare newline after this much silence; the server's
# parser of these lines (app/core/borg_diff.py) skips blank ones, and a
# consumer of this stream must keep doing so. Never for an extract: its
# bytes are the file.
STREAM_DIFF_PAD_IDLE_SECONDS = 30


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

    def build_command(
        self, *, rclone_config_path: Optional[str] = None, compact_stats: bool = True
    ) -> list[str]:
        if self.job_kind == "repository.disk_usage":
            if not self.repository_path:
                raise ValueError("repository.disk_usage requires a repository path")
            return ["du", "-sb", "--", self.repository_path]

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
                encryption_flags = BORG2_ENCRYPTION_FLAGS.get(encryption)
                if encryption_flags is None:
                    raise ValueError(
                        f"unsupported Borg 2 encryption mode {encryption!r}; "
                        "expected one of " + ", ".join(BORG2_ENCRYPTION_FLAGS)
                    )
                return [
                    *self._base_borg2("repo-create"),
                    *encryption_flags,
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

        if self.job_kind == "repository.rinfo":
            # Repository-level metadata (repository id, encryption). borg2 has a
            # dedicated repo-info; borg1 folds it into `info`.
            if self.borg_version == 2:
                return [*self._base_borg2("repo-info"), "--json"]
            return [*self._base_borg1("info"), "--json", self.repository_path]

        if self.job_kind == "repository.archive_info":
            archive = _operation_archive(self.operation, self.job_kind)
            if self.borg_version == 2:
                return [*self._base_borg2("info"), "--json", archive]
            return [
                *self._base_borg1("info"),
                "--json",
                f"{self.repository_path}::{archive}",
            ]

        if self.job_kind == "repository.delete_archive":
            # The server passes the exact selector (an `aid:<hex>` for a Borg 2
            # series, a unique name for Borg 1), so a series delete removes only
            # the intended archive. No extra flags: mirrors borg.delete_archive /
            # borg2.delete_archive. Space is reclaimed by a later compact.
            archive = _operation_archive(self.operation, self.job_kind)
            if self.borg_version == 2:
                return [*self._base_borg2("delete"), archive]
            return [
                *self._base_borg1("delete"),
                f"{self.repository_path}::{archive}",
            ]

        if self.job_kind == "repository.break_lock":
            # Break a stale lock on the node (mirrors borg.break_lock /
            # borg2.break_lock). borg1 takes the repo positionally; borg2 has it
            # in the -r base.
            if self.borg_version == 2:
                return [*self._base_borg2("break-lock")]
            return [*self._base_borg1("break-lock"), self.repository_path]

        if self.job_kind == "repository.list_archives":
            if self.borg_version == 2:
                # A bare `repo-list --json` fills its default keys by reading
                # every archive's metadata, which borgstore serves as
                # whole-pack loads on remote repositories — listing N archives
                # can transfer N packs. Restricting the keys to what the
                # server reads (name, id, time) keeps the listing to the
                # archives directory entries; the --json output shape is
                # unchanged, borg just emits the requested keys.
                return [
                    *self._base_borg2("repo-list"),
                    "--json",
                    "--format",
                    "{name}{id}{time}",
                ]
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

        if self.job_kind == "repository.diff":
            # The change listing the server's history index parses
            # (app/services/operations/executors/history.py), built the way
            # the server builds it for its own repositories. Without a
            # predecessor the archive is the first of its series and gets
            # the full listing, whose entries all read as added.
            # `--` closes the options: an archive name is data, whatever it
            # begins with.
            archive = _operation_archive(self.operation, self.job_kind)
            predecessor = _operation_predecessor(self.operation)
            if self.borg_version == 2:
                if predecessor is None:
                    return [*self._base_borg2("list"), "--json-lines", "--", archive]
                return [
                    *self._base_borg2("diff"),
                    "--json-lines",
                    "--",
                    predecessor,
                    archive,
                ]
            if predecessor is None:
                return [
                    *self._base_borg1("list"),
                    "--json-lines",
                    "--",
                    f"{self.repository_path}::{archive}",
                ]
            return [
                *self._base_borg1("diff"),
                "--json-lines",
                "--",
                f"{self.repository_path}::{predecessor}",
                archive,
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

        if self.job_kind == "repository.export_archive_tar":
            archive = _operation_archive(self.operation, self.job_kind)
            directory_path = _operation_directory_path(self.operation, self.job_kind)
            strip_components = _operation_strip_components(
                self.operation, self.job_kind
            )
            if self.borg_version == 2:
                cmd = [
                    *self._base_borg2("export-tar"),
                ]
                if strip_components:
                    cmd.extend(["--strip-components", str(strip_components)])
                return [*cmd, archive, "-", "--", directory_path]
            cmd = [
                *self._base_borg1("export-tar"),
            ]
            if strip_components:
                cmd.extend(["--strip-components", str(strip_components)])
            return [
                *cmd,
                f"{self.repository_path}::{archive}",
                "-",
                "--",
                directory_path,
            ]

        if self.job_kind == "repository.restore":
            archive = _operation_archive(self.operation, self.job_kind)
            operation = self.operation or {}
            paths = _restore_paths(operation)
            strip_components = _operation_strip_components(operation, self.job_kind)
            # Mirror BorgRouter.build_restore_extract_command so agent-side
            # restores behave identically to server-side ones. Borg only emits
            # JSON progress events when --progress is paired with --log-json, so
            # both borg versions get --progress here. A `--` separator guards
            # against user-supplied paths that start with "-".
            if self.borg_version == 2:
                cmd = [
                    *self._base_borg2("extract"),
                    "--progress",
                    "--log-json",
                    "--umask",
                    "0022",
                ]
                if strip_components:
                    cmd.extend(["--strip-components", str(strip_components)])
                cmd.append(archive)
                if paths:
                    cmd.append("--")
                    cmd.extend(paths)
                return cmd
            cmd = [
                *self._base_borg1("extract"),
                "--progress",
                "--log-json",
                "--umask",
                "0022",
            ]
            if strip_components:
                cmd.extend(["--strip-components", str(strip_components)])
            cmd.append(f"{self.repository_path}::{archive}")
            if paths:
                cmd.append("--")
                cmd.extend(paths)
            return cmd

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
                # --stats: the only place Borg 2 reports repository-wide
                # statistics; parsed from the tail of the output into the
                # completion report (`_execute_streaming_repository_operation`).
                # The flag exists from 2.0.0b15 (`compact_stats_supported`).
                cmd = [*self._base_borg2("compact")]
                if compact_stats:
                    cmd.append("--stats")
                cmd.extend(["--progress", "--verbose", "--log-json"])
                return cmd
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
            # Borg 2 prune has no --stats (Borg 1 does). Both versions spell
            # quarterly retention --keep-3monthly; borg 1.4 has no --keep-quarterly
            # (mirrors the server-side borg.py / borg2.py commands).
            keep_flags = [
                ("keep_hourly", "--keep-hourly"),
                ("keep_daily", "--keep-daily"),
                ("keep_weekly", "--keep-weekly"),
                ("keep_monthly", "--keep-monthly"),
                ("keep_quarterly", "--keep-3monthly"),
                ("keep_yearly", "--keep-yearly"),
            ]
            # --list names every removed archive; the server parses those
            # lines to drop the job records of pruned archives.
            if self.borg_version == 2:
                cmd = [
                    *self._base_borg2("prune"),
                    "--list",
                    "--progress",
                    "--show-rc",
                    "--log-json",
                ]
            else:
                cmd = [
                    *self._base_borg1("prune"),
                    "--list",
                    "--progress",
                    "--stats",
                    "--show-rc",
                    "--log-json",
                ]
            for key, flag in keep_flags:
                value = operation.get(key)
                # Emit only positive retentions (matches server-side `> 0`);
                # `--keep-* 0` (or negative) is meaningless and clutters the
                # command.
                if value and int(value) > 0:
                    cmd.extend([flag, str(int(value))])
            keep_within = operation.get("keep_within")
            if keep_within is not None and str(keep_within).strip():
                # Borg 2.0.0b22 removed --keep-within (and --keep-last) in
                # favour of --keep, which takes either form: a count or an
                # interval like "1d". Borg 1 keeps the old spelling.
                if self.borg_version == 2:
                    cmd.extend(["--keep", str(keep_within).strip()])
                else:
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


def _operation_timeout_seconds(operation: Any, default: float) -> float:
    """The server's budget for a job (`operation.timeout_seconds`), else
    `default`. Anything that is not a finite positive number (a missing or
    malformed payload, "inf", nan) falls back to the default so a stalled
    tool never runs without a deadline."""
    if not isinstance(operation, dict):
        return default
    raw = operation.get("timeout_seconds")
    if isinstance(raw, bool):
        return default
    try:
        value = float(raw or 0)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) and value > 0 else default


def _storage_usage_timeout(operation: Any) -> float:
    """The server's budget for a storage_usage job, else the measurement's
    own default."""
    return _operation_timeout_seconds(operation, 600.0)


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


def _operation_predecessor(operation: dict[str, Any] | None) -> Optional[str]:
    """The archive a diff runs against, or None for a full listing. The key
    must be present, `null` meaning the first archive of its series: a
    payload that lost the field would otherwise read as a full listing
    on top of an indexed predecessor, every path stored as added. An
    empty value is a payload error for the same reason."""
    if not isinstance(operation, dict) or "predecessor" not in operation:
        raise ValueError(
            "repository.diff requires operation.predecessor (null for a full listing)"
        )
    predecessor = operation.get("predecessor")
    if predecessor is None:
        return None
    if not isinstance(predecessor, str) or not predecessor.strip():
        raise ValueError("repository.diff requires a non-empty operation.predecessor")
    return predecessor.strip()


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


def _operation_directory_path(operation: dict[str, Any] | None, job_kind: str) -> str:
    if not isinstance(operation, dict):
        raise ValueError(f"{job_kind} requires operation.directory_path")
    directory_path = operation.get("directory_path")
    if not isinstance(directory_path, str) or not directory_path.strip():
        raise ValueError(f"{job_kind} requires operation.directory_path")
    normalized = directory_path.strip().strip("/")
    if not normalized:
        raise ValueError(f"{job_kind} requires operation.directory_path")
    return normalized


def _restore_paths(operation: dict[str, Any] | None) -> list[str]:
    paths = (operation or {}).get("paths")
    if paths is None:
        return []
    if not isinstance(paths, list):
        raise ValueError("repository.restore requires operation.paths to be a list")
    return [path for path in paths if isinstance(path, str) and path.strip()]


def _operation_strip_components(
    operation: dict[str, Any] | None, job_kind: str
) -> Optional[int]:
    value = (operation or {}).get("strip_components")
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{job_kind} strip_components must be an integer") from exc
    return number if number > 0 else None


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
        with_stats = _reports_compact_stats(payload) and compact_stats_supported(
            payload.borg_cmd
        )
        try:
            if payload.job_kind == "repository.rclone_sync":
                rclone_config_path = _write_temp_rclone_config(payload)
                cmd = payload.build_command(rclone_config_path=rclone_config_path)
            else:
                cmd = payload.build_command(compact_stats=with_stats)
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

    env = build_borg_env(payload.environment)
    if payload.job_kind in MACHINE_PARSED_JOB_KINDS:
        # The server parses timestamps out of these outputs; pin the render
        # zone so they come out UTC. Applied after the server-sent overrides:
        # the reported machine timezone is "UTC" on the same contract.
        env["TZ"] = "UTC"
    if with_stats:
        # Raw units print exact byte counts in the --stats lines instead of
        # the rounded human form, which follows whatever BORG_UNITS the
        # machine environment carries.
        env["BORG_UNITS"] = "raw"
    if payload.job_kind == "repository.init":
        # Repo creation must not touch the shared pack cache: borgstore
        # rejects an already-populated cache directory on create, and borg
        # misreports that as "repository already exists".
        env["BORG_STORE_CACHE"] = ""
    sequence = 0
    client.send_log(
        job_id,
        sequence=sequence,
        stream="stdout",
        message=f"Starting {payload.job_kind}: {shlex.join(cmd)}",
    )
    sequence += 1

    if payload.job_kind in SELF_CANCELLING_JOB_KINDS and cancel_requested(
        should_cancel
    ):
        # Cancelled between dispatch and start (the log above may have waited
        # on the server): a fast command (an archive delete) would be done
        # before the first poll, so it is not started.
        _remove_temp_file(rclone_config_path)
        client.cancel_job(job_id)
        return RepositoryOperationResult(
            job_id=job_id,
            status="canceled",
            message=f"{payload.job_kind} canceled before it started",
        )

    if payload.job_kind == "repository.delete_archive":
        # A write that holds the repository lock: a cancel has to end it.
        try:
            return _execute_short_repository_operation(
                job_id, payload, client, cmd, env, should_cancel=should_cancel
            )
        finally:
            _remove_temp_file(rclone_config_path)

    if payload.job_kind in {
        "repository.info",
        "repository.rinfo",
        "repository.archive_info",
        "repository.list_archives",
        "repository.break_lock",
        "repository.disk_usage",
    }:
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

    if payload.job_kind == "repository.diff":
        # Always the artifact path: a change listing of a large archive runs
        # to tens of megabytes, which the WebSocket result must not carry.
        # The listing is worthless unless the server consumed it, so a
        # rejected upload fails the job. Borg reports a warning when it
        # could not read part of an archive; the listing it did produce is
        # still consumed, as the server's own history index does for rc 1
        # (the agent's warning set also covers Borg's modern codes).
        try:
            return _execute_streaming_artifact_operation(
                job_id,
                payload,
                client,
                cmd,
                env,
                should_cancel=should_cancel,
                warnings_ok=True,
                idle_timeout_seconds=None,
                max_duration_seconds=_operation_timeout_seconds(
                    payload.operation, STREAM_DIFF_MAX_SECONDS
                ),
                keepalive_seconds=STREAM_KEEPALIVE_SECONDS,
                pad_idle_seconds=STREAM_DIFF_PAD_IDLE_SECONDS,
                delivery_required=True,
            )
        finally:
            _remove_temp_file(rclone_config_path)

    if payload.job_kind in {
        "repository.extract_archive_file",
        "repository.export_archive_tar",
    }:
        try:
            return _execute_binary_output_repository_operation(
                job_id, payload, client, cmd, env, should_cancel=should_cancel
            )
        finally:
            _remove_temp_file(rclone_config_path)

    if payload.job_kind == "repository.restore":
        try:
            return _execute_restore_operation(
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

    try:
        return _execute_streaming_repository_operation(
            job_id,
            payload,
            client,
            cmd,
            env,
            initial_sequence=sequence,
            should_cancel=should_cancel,
            compact_stats=with_stats,
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
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> RepositoryOperationResult:
    """Run a command that finishes within five minutes and report its
    captured output. With `should_cancel` it runs in its own process group
    under a cancel poller, which ends it when the server cancels the job."""
    try:
        if should_cancel is None:
            process = subprocess.run(
                cmd, text=True, capture_output=True, env=env, timeout=300
            )
        else:
            process, cancelled = _run_cancellable(cmd, env, should_cancel, timeout=300)
            if cancelled:
                client.cancel_job(job_id)
                return RepositoryOperationResult(
                    job_id=job_id,
                    status="canceled",
                    return_code=process.returncode,
                    message=f"{payload.job_kind} canceled",
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

    succeeded = process.returncode == 0 or is_warning_return_code(process.returncode)
    parsed = _parse_json_output(process.stdout) if succeeded else None
    if parsed is not None and payload.job_kind in MACHINE_PARSED_JOB_KINDS:
        # The parsed output travels in the completion report; the log keeps
        # one line about it. A failed run, or output that did not parse,
        # keeps what Borg printed: the server builds its error message from
        # these lines.
        client.send_log(
            job_id,
            sequence=1,
            stream="stdout",
            message=_output_summary(payload.job_kind, process, parsed),
        )
    elif process.stdout:
        client.send_log(
            job_id, sequence=1, stream="stdout", message=process.stdout.rstrip()
        )
    if process.stderr:
        client.send_log(
            job_id, sequence=2, stream="stderr", message=process.stderr.rstrip()
        )

    if succeeded:
        # Warnings (rc 1 / 100-127) mean the operation ran through; the server
        # records completed_with_warnings from the return code, matching the
        # classification its own borg processes get.
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
            status="completed"
            if process.returncode == 0
            else "completed_with_warnings",
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


def _output_summary(
    job_kind: str, process: subprocess.CompletedProcess, parsed: Any
) -> str:
    """The log line that stands for a machine-parsed kind's JSON output."""
    archives = parsed.get("archives") if isinstance(parsed, dict) else None
    if job_kind == "repository.list_archives" and isinstance(archives, list):
        detail = f"{len(archives)} archives"
    else:
        detail = f"{len(process.stdout)} characters of JSON"
    name = job_kind.removeprefix("repository.")
    return f"{name}: {detail}, rc {process.returncode}"


def _run_cancellable(
    cmd: list[str],
    env: dict[str, str],
    should_cancel: Callable[[], bool],
    *,
    timeout: float,
) -> tuple[subprocess.CompletedProcess, bool]:
    """`subprocess.run(capture_output=True, timeout=...)` with a cancel
    poller: returns the finished process and whether a cancel ended it.
    Raises `subprocess.TimeoutExpired` like `run` once borg is ended."""
    popen_kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "env": env,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    process = subprocess.Popen(cmd, **popen_kwargs)
    done = threading.Event()
    cancelled = _start_cancel_poller(process, should_cancel, done)
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_process(process)
            try:
                process.communicate(timeout=KILL_GROUP_AFTER_SECONDS)
            except subprocess.TimeoutExpired:
                # A child that ignored SIGTERM still holds the pipes.
                kill_process_group(process)
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            raise
        except BaseException:
            # Interrupted (Ctrl-C on `once`): borg runs in a session of its
            # own and would go on unsupervised, as `subprocess.run` never let
            # it.
            _terminate_process(process)
            raise
    finally:
        done.set()
    completed = subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)
    return completed, cancelled.is_set()


def _start_cancel_poller(
    process: subprocess.Popen,
    should_cancel: Optional[Callable[[], bool]],
    done: threading.Event,
) -> threading.Event:
    """`start_cancel_poller` ending the process group (`_terminate_process`)."""
    return start_cancel_poller(process, should_cancel, done, _terminate_process)


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

    With `pad_idle_seconds`, a read that finds no data for that long returns
    a bare newline instead of blocking on, so the upload connection carries
    something while the command is silent. Only for line-oriented output
    whose consumer skips blank lines. Reads then go to the pipe's file
    descriptor directly, unbuffered: the buffered `read(n)` of a Popen pipe
    blocks until it has n bytes, however long the command is silent after
    writing fewer, and a Python-side buffer would hide bytes from select.
    Output is passed on whole lines: the command flushes its output in
    blocks that can end inside a record, and a partial line is held back
    until its end arrives, so the padding never lands inside one. Padding
    is not counted as activity or as bytes read. A held-back partial line
    puts nothing on the wire and grows until its end arrives, so the
    output must be short lines, as borg's are. Needs a real pipe (posix);
    elsewhere reads block as before.
    """

    def __init__(self, stream: Any, *, pad_idle_seconds: Optional[float] = None):
        self._stream = stream
        self.last_activity = time.monotonic()
        self.bytes_read = 0
        self._pad_idle_seconds = pad_idle_seconds
        self._pending = b""
        self._fd: Optional[int] = None
        self._selector: Optional[selectors.BaseSelector] = None
        if pad_idle_seconds is not None and os.name == "posix":
            try:
                self._fd = stream.fileno()
                # The platform's selector, not select(): that one refuses a
                # descriptor beyond FD_SETSIZE, which an agent holding many
                # files can reach.
                self._selector = selectors.DefaultSelector()
                self._selector.register(self._fd, selectors.EVENT_READ)
            except (AttributeError, OSError, ValueError):
                self._fd = None
                self._selector = None

    def read(self, *args: Any) -> bytes:
        if self._fd is None:
            chunk = self._stream.read(*args)
            if chunk:
                self.last_activity = time.monotonic()
                self.bytes_read += len(chunk)
            return chunk
        if not (args and isinstance(args[0], int) and args[0] > 0):
            # A whole-output read would take one batch of lines for the
            # whole listing; the padded reader serves sized reads only.
            raise ValueError("padded reads need a size")
        size = args[0]
        while True:
            try:
                ready = self._selector.select(self._pad_idle_seconds)
            except (OSError, ValueError):
                ready = [None]  # a closed pipe: let the read report EOF
            if not ready:
                return b"\n"
            try:
                data = os.read(self._fd, size)
            except OSError:
                data = b""
            if not data:
                # End of output: the held-back tail goes out as it is, then
                # the empty read that ends the upload.
                self._selector.close()
                tail, self._pending = self._pending, b""
                return tail
            self.last_activity = time.monotonic()
            self.bytes_read += len(data)
            combined = self._pending + data
            cut = combined.rfind(b"\n")
            if cut < 0:
                self._pending = combined
                continue
            self._pending = combined[cut + 1 :]
            # May exceed `size`: whole lines only, and the held-back part of
            # a line joins the read that completes it. The upload's chunked
            # body loop takes what it gets.
            return combined[: cut + 1]

    def close(self) -> None:
        if self._selector is not None:
            self._selector.close()
        self._stream.close()


def _execute_streaming_artifact_operation(
    job_id: int,
    payload: RepositoryOperationPayload,
    client: AgentClient,
    cmd: list[str],
    env: dict[str, str],
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
    warnings_ok: bool = False,
    idle_timeout_seconds: Optional[float],
    max_duration_seconds: Optional[float] = None,
    keepalive_seconds: Optional[float] = None,
    pad_idle_seconds: Optional[float] = None,
    delivery_required: bool = False,
) -> RepositoryOperationResult:
    """Stream a command's stdout straight to the server over HTTP.

    The output never enters the WebSocket, so it works at any size. stderr
    is drained on a thread so a full stderr pipe can't deadlock the stdout the
    upload is reading. A watchdog terminates borg if it wedges past a deadline,
    and a poller of `should_cancel` terminates it on cancellation, so a hung
    process can't pin this worker — terminating closes stdout, which unblocks
    the upload read below.

    The deadline is `idle_timeout_seconds` without stdout activity (an extract
    that stopped producing bytes is wedged), `max_duration_seconds` since the
    start (a diff is silent while it compares unchanged paths, so only an
    absolute bound tells a long one from a stuck one), or both; None disables
    that bound.

    `warnings_ok` completes the job on a Borg warning exit code as well: the
    output was streamed in full and the server decides what the warning
    means for it. An extract keeps failing on a warning, since a partially
    served file is not a download.

    `keepalive_seconds` reports an empty progress keepalive this often, so
    the server sees the job alive while nothing else reaches it; a
    keepalive that fails to send is dropped, never fatal.
    `pad_idle_seconds` keeps the upload connection itself carrying bytes
    while the command is silent (see `_ActivityTrackingReader`).

    `delivery_required` fails the job unless the server confirms the upload
    (`accepted: true`); it answers `false` when no consumer was registered
    for the job or it left mid-stream. A download's consumer is a person who
    may have closed the tab; a listing nobody consumed is a job that did not
    happen, and a `completed` row would read as a delivered one.

    The stream itself carries no end marker: a kill by the watchdog closes
    stdout and the server sees a clean end of stream, the same as a run that
    finished. Whether the bytes are the whole output is the job's terminal
    status, which lands after the upload; a consumer commits nothing before
    it has read that status.
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

    timed_out = threading.Event()
    timeout_reason: list[str] = []
    watchdog_done = threading.Event()

    reader = _ActivityTrackingReader(process.stdout, pad_idle_seconds=pad_idle_seconds)
    started_at = time.monotonic()

    def _keepalive() -> None:
        # Its own thread: on the polling transport a send is an HTTP request
        # with retries, and a server that is down would otherwise hold the
        # watchdog (cancellation, deadline) for the length of those retries.
        # The session transport queues the message without blocking. A send
        # that fails is dropped; the next one is due a minute later.
        while not watchdog_done.wait(keepalive_seconds):
            if process.poll() is not None:
                return
            try:
                # No fields: the report is a sign of life, and every field
                # the progress schema offers is a backup statistic that
                # would be read as one.
                client.send_progress(job_id, {})
            except Exception:  # noqa: BLE001 - a keepalive is best effort
                pass

    def _watchdog() -> None:
        while not watchdog_done.wait(0.5):
            if process.poll() is not None:
                return
            now = time.monotonic()
            # Idle, not absolute: only kill borg once no bytes have flowed for
            # the timeout, so an actively-streaming large transfer is not cut off.
            if (
                idle_timeout_seconds is not None
                and now - reader.last_activity >= idle_timeout_seconds
            ):
                timeout_reason.append(f"no output for {idle_timeout_seconds:g}s")
                timed_out.set()
                _terminate_process(process)
                return
            if (
                max_duration_seconds is not None
                and now - started_at >= max_duration_seconds
            ):
                timeout_reason.append(f"ran longer than {max_duration_seconds:g}s")
                timed_out.set()
                _terminate_process(process)
                return

    watchdog = threading.Thread(target=_watchdog, daemon=True)
    watchdog.start()
    # Its own thread, apart from the watchdog: on the polling transport the
    # check is a heartbeat request with retries, and the deadlines must not
    # wait for an unreachable server to answer it.
    cancelled = _start_cancel_poller(process, should_cancel, watchdog_done)
    if keepalive_seconds is not None:
        threading.Thread(target=_keepalive, daemon=True).start()

    upload_error: Optional[BaseException] = None
    upload_response: Any = None
    try:
        upload_response = client.upload_artifact(job_id, reader)
    except BaseException as exc:  # noqa: BLE001 - reported below
        upload_error = exc
        # A broken upload leaves nobody reading stdout. Closing the pipe
        # ends borg only at its next write, and a diff comparing unchanged
        # paths may not write for a long time; end it now instead.
        _terminate_process(process)
    finally:
        # Closing stdout makes borg see EPIPE and exit if the upload broke;
        # the reader's selector goes with it.
        try:
            reader.close()
        except OSError:
            pass

    delivered = isinstance(upload_response, dict) and (
        upload_response.get("accepted") is True
    )
    if delivery_required and not delivered and process.poll() is None:
        # The server ended the request without a consumer while borg is
        # still comparing: nothing will take the rest, so borg does not
        # run it (it would otherwise hold the repository until the
        # deadline, kept alive by the keepalives).
        _terminate_process(process)

    return_code = process.wait()
    watchdog_done.set()
    watchdog.join(timeout=5)
    # The keepalive and cancel-poller threads are not joined: a request in
    # flight may be waiting out an unreachable server's retries, and the
    # verdict must not wait for it. They end on their own, and a progress
    # report that lands after the verdict is refused by the server as a
    # report on a final job.
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
        reason = timeout_reason[0] if timeout_reason else "deadline reached"
        if upload_error is not None:
            reason = f"{reason}; upload failed meanwhile: {upload_error}"
        if stderr:
            # Whatever borg said before it was ended is the operator's lead.
            client.send_log(
                job_id, sequence=1, stream="stderr", message=stderr.rstrip()
            )
        error_message = f"{payload.job_kind} stopped by the watchdog: {reason}"
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

    if delivery_required and not delivered:
        # The server answers 200 either way; only the body says whether a
        # consumer took the bytes, so anything but its explicit yes (a
        # bodyless answer from a proxy included) is not a delivery. Checked
        # before the exit code: a consumer that left mid-stream closes the
        # pipe and borg's EPIPE exit would otherwise name the wrong cause.
        # borg may have failed before writing a byte (a held lock, say): the
        # consumer gave up waiting, and its reason is on stderr.
        if stderr:
            client.send_log(
                job_id, sequence=1, stream="stderr", message=stderr.rstrip()
            )
        error_message = (
            f"{payload.job_kind} artifact not delivered: the server did not "
            f"confirm a consumer for it (borg exited with code {return_code})"
        )
        client.fail_job(job_id, error_message=error_message, return_code=return_code)
        return RepositoryOperationResult(
            job_id=job_id,
            status="failed",
            return_code=return_code,
            message=error_message,
        )

    if return_code == 0 or (warnings_ok and is_warning_return_code(return_code)):
        if return_code != 0 and stderr:
            client.send_log(
                job_id, sequence=1, stream="stderr", message=stderr.rstrip()
            )
        client.complete_job(
            job_id,
            result={"return_code": return_code, "command": cmd, "artifact": True},
        )
        return RepositoryOperationResult(
            job_id=job_id,
            status="completed" if return_code == 0 else "completed_with_warnings",
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
            job_id,
            payload,
            client,
            cmd,
            env,
            should_cancel=should_cancel,
            idle_timeout_seconds=STREAM_EXTRACT_IDLE_SECONDS,
            keepalive_seconds=STREAM_KEEPALIVE_SECONDS,
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
    compact_stats: bool = False,
) -> RepositoryOperationResult:
    """Run a Borg (or rclone) command to completion, streaming its output
    as log lines. `compact_stats`: the command is a Borg 2 `compact
    --stats`, whose statistics are parsed from the tail of the output into
    the completion report, and whose Borg warning exit code completes the
    job with warnings (`_warning_exit`)."""
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
    tail: deque[str] = deque(maxlen=TAIL_LINES)
    done = threading.Event()
    # The per-line check below answers at once while output flows; the
    # poller reaches a Borg that prints nothing (a lock wait, a compact).
    cancelled = _start_cancel_poller(process, should_cancel, done)
    start_keepalive(process, client, job_id, done)
    try:
        if process.stdout is not None:
            for line in process.stdout:
                message = line.rstrip("\n")
                if compact_stats:
                    tail.append(message)
                progress = parse_borg_progress(message)
                if progress:
                    client.send_progress(job_id, progress)
                if not progress_replaces_log_line(progress):
                    client.send_log(
                        job_id, sequence=sequence, stream="stdout", message=message
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
        # Borg must not run on unsupervised, holding the repository.
        _terminate_process(process)
        raise
    finally:
        done.set()

    if cancelled.is_set():
        client.cancel_job(job_id)
        return RepositoryOperationResult(
            job_id=job_id,
            status="canceled",
            return_code=return_code,
            message=f"{payload.job_kind} canceled",
        )

    if return_code == 0 or _warning_exit(payload, return_code):
        status = "completed" if return_code == 0 else "completed_with_warnings"
        result: dict[str, Any] = {
            "return_code": return_code,
            "command": cmd,
            "status": status,
        }
        if compact_stats:
            # The statistics ride with the completion report: the log lines
            # that carry them are queued behind it on the outbox, so the
            # server would otherwise have to wait for them.
            stats = parse_compact_stats(tail)
            if stats is not None:
                result["stats"] = stats
        client.complete_job(job_id, result=result)
        return RepositoryOperationResult(
            job_id=job_id,
            status=status,
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


def _reports_compact_stats(payload: RepositoryOperationPayload) -> bool:
    """Whether this job is a Borg 2 compact, the one operation with
    repository statistics (Borg 1 compact has none)."""
    return payload.job_kind == "repository.compact" and payload.borg_version == 2


def _warning_exit(payload: RepositoryOperationPayload, return_code: int) -> bool:
    """Whether `return_code` is a Borg warning that still leaves this job a
    completion: a compact that warned ran through and printed its
    statistics, as the short and backup paths and the server classify it.
    The other streamed kinds keep failing on any non-zero exit as they did:
    `check` exits 1 for consistency errors found, which must not count as
    a repository checked; `prune` is left as it was until its warning
    semantics are settled with the server's; rclone has no warning range
    at all."""
    if payload.job_kind != "repository.compact":
        return False
    return is_warning_return_code(return_code)


# Whether a Borg 2 binary accepts `compact --stats`, by binary file
# (path, mtime, size): probed once per file (`borg2 --version` is a
# subprocess), again when the file changes under a long-lived agent.
_COMPACT_STATS_SUPPORT: dict[tuple, bool] = {}


def _binary_key(binary: str) -> tuple:
    path = shutil.which(binary) or binary
    try:
        stat = os.stat(path)
    except OSError:
        return (path, None, None)
    return (path, stat.st_mtime_ns, stat.st_size)


def compact_stats_supported(binary: str) -> bool:
    """Whether `binary` accepts `compact --stats` (Borg 2.0.0b15 on, see
    `compact_stats.has_compact_stats`). A binary whose version cannot be
    read this time (a probe timeout, a banner without a version) does not
    get the flag: a wrong flag would fail the whole compact, a missing one
    only its statistics. It is probed again next time; only a read version
    is remembered."""
    key = _binary_key(binary)
    known = _COMPACT_STATS_SUPPORT.get(key)
    if known is not None:
        return known
    try:
        probe = subprocess.run(
            [binary, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        version = parse_borg_version(f"{probe.stdout}\n{probe.stderr}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # ValueError covers a `--version` output the locale cannot decode
        version = None
    if version is None:
        return False
    supported = has_compact_stats(version)
    _COMPACT_STATS_SUPPORT[key] = supported
    return supported


def _resolve_restore_target(operation: dict[str, Any]) -> tuple[str, bool]:
    """Return (target_dir, is_temp) for a repository.restore job.

    `target.type == "temp"` extracts into a throwaway directory the agent owns
    and deletes afterwards (used by restore checks); otherwise it extracts into
    the given absolute path on the node (used by ad-hoc restores).
    """
    target = operation.get("target")
    if not isinstance(target, dict):
        raise ValueError("repository.restore requires operation.target")
    if target.get("type") == "temp":
        return tempfile.mkdtemp(prefix="borg-ui-restore-"), True
    path = target.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("repository.restore requires operation.target.path")
    destination = Path(path.strip())
    # borg extract runs with cwd=destination, so a relative path would extract
    # into the agent service's working directory rather than the intended node
    # location. Require an absolute path.
    if not destination.is_absolute():
        raise ValueError("repository.restore operation.target.path must be absolute")
    destination.mkdir(parents=True, exist_ok=True)
    return str(destination), False


def _execute_restore_operation(
    job_id: int,
    payload: RepositoryOperationPayload,
    client: AgentClient,
    cmd: list[str],
    env: dict[str, str],
    *,
    initial_sequence: int,
    should_cancel: Optional[Callable[[], bool]],
) -> RepositoryOperationResult:
    """Run `borg extract` into a destination on the node, streaming progress.

    Extraction is relative to the working directory, so we run it with cwd set
    to the resolved target. Optionally verifies a restore-check canary on the
    node afterwards and reports the verdict in the completion result; the server
    maps that verdict onto the RestoreCheckJob status.
    """
    operation = payload.operation or {}
    try:
        target_dir, is_temp = _resolve_restore_target(operation)
    except (OSError, ValueError) as exc:
        error_message = f"Failed to prepare restore destination: {exc}"
        client.send_log(
            job_id, sequence=initial_sequence, stream="stderr", message=error_message
        )
        client.fail_job(job_id, error_message=error_message)
        return RepositoryOperationResult(
            job_id=job_id, status="failed", message=error_message
        )

    try:
        try:
            popen_kwargs: dict[str, Any] = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "env": env,
                "cwd": target_dir,
            }
            if os.name == "posix":
                popen_kwargs["start_new_session"] = True
            process = subprocess.Popen(cmd, **popen_kwargs)
        except OSError as exc:
            error_message = f"Failed to start {payload.job_kind}: {exc}"
            client.send_log(
                job_id,
                sequence=initial_sequence,
                stream="stderr",
                message=error_message,
            )
            client.fail_job(job_id, error_message=error_message)
            return RepositoryOperationResult(
                job_id=job_id, status="failed", message=error_message
            )

        sequence = initial_sequence
        done = threading.Event()
        # As in the streaming path: the poller reaches a silent extract.
        cancelled = _start_cancel_poller(process, should_cancel, done)
        start_keepalive(process, client, job_id, done)
        try:
            if process.stdout is not None:
                for line in process.stdout:
                    message = line.rstrip("\n")
                    progress = parse_borg_progress(message)
                    if progress:
                        client.send_progress(job_id, progress)
                    if not progress_replaces_log_line(progress):
                        client.send_log(
                            job_id,
                            sequence=sequence,
                            stream="stdout",
                            message=message,
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
            # As in the streaming path: never leave Borg unsupervised.
            _terminate_process(process)
            raise
        finally:
            done.set()

        if cancelled.is_set():
            client.cancel_job(job_id)
            return RepositoryOperationResult(
                job_id=job_id,
                status="canceled",
                return_code=return_code,
                message=f"{payload.job_kind} canceled",
            )

        warning = is_warning_return_code(return_code)

        # A hard borg failure has no meaningful verification verdict.
        if return_code != 0 and not warning:
            error_message = f"{payload.job_kind} exited with code {return_code}"
            client.fail_job(
                job_id, error_message=error_message, return_code=return_code
            )
            return RepositoryOperationResult(
                job_id=job_id,
                status="failed",
                return_code=return_code,
                message=error_message,
            )

        result_payload: dict[str, Any] = {
            "return_code": return_code,
            "command": cmd,
            "status": "completed",
            "warning": warning,
        }
        verify_spec = operation.get("verify")
        if verify_spec:
            verification = _verify_restore(target_dir, verify_spec)
            result_payload["verification"] = verification
            if verification.get("status") != "verified":
                client.send_log(
                    job_id,
                    sequence=sequence,
                    stream="stderr",
                    message=verification.get(
                        "message", "restore verification did not pass"
                    ),
                )

        client.complete_job(job_id, result=result_payload)
        return RepositoryOperationResult(
            job_id=job_id,
            status="completed",
            return_code=return_code,
            message=f"{payload.job_kind} exited with code {return_code}",
        )
    finally:
        if is_temp:
            shutil.rmtree(target_dir, ignore_errors=True)


def _verify_restore(target_dir: str, verify_spec: Any) -> dict[str, Any]:
    if isinstance(verify_spec, dict) and verify_spec.get("kind") == "canary":
        return _verify_canary(target_dir, verify_spec)
    # Unknown/absent verification: the extract itself succeeded, so treat as
    # verified rather than failing a restore that actually produced files.
    return {"status": "verified"}


def _verify_canary(target_dir: str, verify_spec: dict[str, Any]) -> dict[str, Any]:
    """Verify Borg UI restore-check canary files on the node.

    Data-driven mirror of app.services.restore_check_canary.verify_restored_canary:
    locate the manifest among the candidate archive-relative paths, then confirm
    each listed file's sha256 and size. The agent package cannot import app.*, so
    the logic is reproduced here but reads all expectations from the manifest.
    """
    # Resolve against the real restored root and reject any candidate/manifest
    # entry that escapes it (via "..") so verification can only ever read files
    # inside the just-restored tree, never arbitrary files on the agent.
    restore_root = Path(target_dir).resolve()
    manifest_path: Optional[Path] = None
    for candidate in verify_spec.get("manifest_candidates") or []:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        candidate_path = (restore_root / candidate.strip().strip("/")).resolve()
        if not candidate_path.is_relative_to(restore_root):
            continue
        if candidate_path.is_file():
            manifest_path = candidate_path
            break

    if manifest_path is None:
        return {
            "status": "needs_backup",
            "message": (
                "The Borg UI canary file was not found in the latest archive. "
                "Run a backup while canary mode is enabled, then run this restore "
                "check again."
            ),
        }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "failed", "message": f"Could not read canary manifest: {exc}"}

    base_dir = manifest_path.parent.parent
    verified_files: list[str] = []
    for entry in manifest.get("files", []):
        if not isinstance(entry, dict):
            continue
        relative_path = entry.get("path")
        if not isinstance(relative_path, str):
            continue
        target = (base_dir / relative_path).resolve()
        if not target.is_relative_to(restore_root):
            return {
                "status": "failed",
                "message": f"Canary path escapes restore root: {relative_path}",
            }
        if not target.is_file():
            return {
                "status": "failed",
                "message": f"Canary file missing after restore: {relative_path}",
            }
        content = target.read_bytes()
        if hashlib.sha256(content).hexdigest() != entry.get("sha256"):
            return {
                "status": "failed",
                "message": f"Canary hash mismatch for {relative_path}",
            }
        if len(content) != entry.get("size"):
            return {
                "status": "failed",
                "message": f"Canary size mismatch for {relative_path}",
            }
        verified_files.append(relative_path)

    return {"status": "verified", "verified_files": verified_files}


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


def execute_storage_usage_job(
    job: dict[str, Any],
    client: AgentClient,
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> RepositoryOperationResult:
    """`repository.storage_usage`: measure a Borg 2 repository read-only and
    report one JSON object (bytes, objects, source); see storage_usage.py."""
    from agent.borg_ui_agent import storage_usage

    job_id = int(job["id"])
    try:
        payload = RepositoryOperationPayload.from_job_payload(job.get("payload") or {})
    except (TypeError, ValueError) as exc:
        error_message = f"Invalid repository operation payload: {exc}"
        client.send_log(job_id, sequence=0, stream="stderr", message=error_message)
        client.fail_job(job_id, error_message=error_message)
        return RepositoryOperationResult(
            job_id=job_id, status="failed", message=error_message
        )
    env = build_borg_env(payload.environment)
    if payload.remote_path:
        # The index step runs through Borg's Python API, where the remote
        # path travels in the environment: the payload's value must win over
        # an inherited one, unlike --remote-path on the other handlers' argv.
        env["BORG_REMOTE_PATH"] = payload.remote_path
    # The server stops waiting after its info timeout; a measurement that
    # outlives it would hold the job open and refuse the next refresh.
    timeout = _storage_usage_timeout(payload.operation)
    try:
        data = storage_usage.measure(
            payload.repository_path,
            borg_version=payload.borg_version,
            borg_binary=payload.borg_cmd,
            env=env,
            timeout=timeout,
            should_cancel=should_cancel,
        )
    except storage_usage.Cancelled:
        client.cancel_job(job_id)
        return RepositoryOperationResult(
            job_id=job_id, status="canceled", message=f"{payload.job_kind} canceled"
        )
    except Exception as exc:
        error_message = f"storage usage failed: {exc}"
        client.send_log(job_id, sequence=0, stream="stderr", message=error_message)
        client.fail_job(job_id, error_message=error_message)
        return RepositoryOperationResult(
            job_id=job_id, status="failed", message=error_message
        )
    stdout = json.dumps(data)
    client.send_log(job_id, sequence=1, stream="stdout", message=stdout)
    client.complete_job(
        job_id,
        result={
            "return_code": 0,
            "command": ["repository.storage_usage"],
            "stdout": stdout,
            "stderr": "",
            "data": data,
        },
    )
    return RepositoryOperationResult(job_id=job_id, status="completed", return_code=0)
