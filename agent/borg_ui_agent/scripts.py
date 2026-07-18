"""Agent-side pre/post backup scripts.

The agent — not the server — owns the security boundary here. The server never
sends a path: it sends a bare script *name*, and the agent will only run a script
that is present in **one configured location on the agent** (its allow-list). How
that directory gets populated (a config-management drop, a mounted ConfigMap, …)
is out of scope; the agent only trusts what it finds there.

Kubernetes projected/ConfigMap volumes expose each key as a symlink into a hidden
``..data`` snapshot directory, so the allow-list check accepts symlinks that
resolve *within* the scripts directory tree while rejecting anything that escapes
it (``..`` traversal, absolute paths, symlinks pointing outside the tree).

Execution follows the same contract as the borg job handlers: ``stdout`` and
``stderr`` are kept strictly separate, both are streamed to the server as logs,
and the resolved ``return_code`` is reported back. The server classifies the
outcome (``0`` success, ``1`` warning, ``>1`` failure) — the agent only reports
the facts.
"""

from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from agent.borg_ui_agent.backup import _terminate_process

DEFAULT_SCRIPTS_DIR = "/etc/borg-ui-agent/scripts.d"

# Cap the stdout/stderr copied into the terminal result so a chatty script can't
# produce an oversized control-channel frame. The full output is still streamed
# line-by-line as job logs.
_MAX_CAPTURED_BYTES = 256 * 1024

# Cap a *single* streamed log line, independent of the aggregate result cap above.
# Also the per-read bound: readline(_MAX_LOG_MESSAGE_BYTES) stops a newline-free
# multi-MB stream from being buffered whole into one string before truncation.
_MAX_LOG_MESSAGE_BYTES = 64 * 1024

# Bound the cancel-path pump-thread joins: if a descendant keeps the pipe FDs
# open the daemon pump threads could otherwise hang cancellation forever.
_CANCEL_JOIN_TIMEOUT = 5.0


def _truncate_utf8(text: str, max_bytes: int) -> str:
    """Truncate ``text`` to at most ``max_bytes`` UTF-8 bytes, dropping any
    partial trailing character."""
    encoded = text.encode("utf-8", "replace")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", "ignore")


class ScriptNotAllowed(Exception):
    """A requested script name is not in the agent's allow-list."""


@dataclass(frozen=True)
class ScriptRunResult:
    job_id: int
    status: str
    return_code: Optional[int] = None
    message: str = ""


def scripts_dir() -> Path:
    """The single configured location the agent treats as its allow-list."""
    return Path(
        os.environ.get("BORG_UI_AGENT_SCRIPTS_DIR", DEFAULT_SCRIPTS_DIR)
    ).resolve()


def _is_within(path: Path, root: Path) -> bool:
    """True if the *real* ``path`` sits inside the ``root`` tree (root excluded)."""
    try:
        real = Path(os.path.realpath(path))
    except (OSError, ValueError):
        return False
    try:
        real.relative_to(root)
    except ValueError:
        return False
    return real != root


def _is_runnable(entry_path: Path, root: Path) -> bool:
    # realpath()/is_file()/os.access() raise ValueError on a malformed name (e.g.
    # an embedded null byte, which slips past the basename checks). Such a name
    # must be rejected as "not runnable", not crash the polling handler.
    try:
        real = Path(os.path.realpath(entry_path))
        return (
            _is_within(entry_path, root)
            and real.is_file()
            and os.access(entry_path, os.X_OK)
        )
    except (OSError, ValueError):
        return False


def _read_description(real_path: Path) -> Optional[str]:
    """Optional one-line description from a leading ``# borg-ui: <text>`` comment."""
    try:
        with open(real_path, encoding="utf-8", errors="replace") as handle:
            for _ in range(20):
                # Cap the read: only a short marker is expected, and a binary in
                # the allow-list dir could otherwise stream an arbitrarily long
                # "line" into memory.
                line = handle.readline(4096)
                if not line:
                    break
                stripped = line.strip()
                marker = "# borg-ui:"
                if stripped.startswith(marker):
                    text = stripped[len(marker) :].strip()
                    if text:
                        return text
    except OSError:
        return None
    return None


def list_allowed_scripts() -> list[dict[str, Any]]:
    """The scripts the agent publishes: executable regular files that live in the
    configured directory (following the ConfigMap ``..data`` symlink indirection),
    sorted by name. Never raises — an unreadable/absent directory yields ``[]``."""
    root = scripts_dir()
    scripts: list[dict[str, Any]] = []
    try:
        entries = list(os.scandir(root))
    except OSError:
        return []
    for entry in entries:
        name = entry.name
        # Skip Kubernetes projected-volume internals (``..data``, ``..2026_…``)
        # and any hidden files.
        if name.startswith("."):
            continue
        entry_path = Path(entry.path)
        if not _is_runnable(entry_path, root):
            continue
        item: dict[str, Any] = {"name": name}
        description = _read_description(Path(os.path.realpath(entry_path)))
        if description:
            item["description"] = description
        scripts.append(item)
    scripts.sort(key=lambda item: item["name"])
    return scripts


def resolve_allowed_script(name: Any) -> Path:
    """Map a server-supplied script *name* to a real, runnable path in the
    allow-list, or raise :class:`ScriptNotAllowed`. This is the single
    enforcement point — it never trusts a path, only a bare filename."""
    if not isinstance(name, str) or not name.strip():
        raise ScriptNotAllowed("missing script name")
    name = name.strip()
    # A name must be a bare filename: no directory components, no traversal, not
    # hidden (which also excludes the ``..data`` volume internals).
    if name in (".", "..") or name.startswith("."):
        raise ScriptNotAllowed(f"invalid script name: {name!r}")
    if name != os.path.basename(name) or os.sep in name or (os.altsep and os.altsep in name):
        raise ScriptNotAllowed(f"invalid script name: {name!r}")

    root = scripts_dir()
    candidate = root / name
    if not _is_runnable(candidate, root):
        raise ScriptNotAllowed(f"script not in allow-list: {name!r}")
    return Path(os.path.realpath(candidate))


def _build_env(payload_env: Any) -> dict[str, str]:
    # Allow-listed scripts are operator-provided and trusted, and often need the
    # agent's own environment to do their job (e.g. cluster DB dumps read
    # DB_BACKUP_LOCATION, DB configs, BORG_* vars) — exactly like the cronjob path
    # and `borg create` run them. Run with the agent's full environment, with the
    # server-provided BORG_UI_* context layered on top.
    env = os.environ.copy()
    if isinstance(payload_env, dict):
        for key, value in payload_env.items():
            # Only the documented BORG_UI_* context may be layered on top — the
            # server must not be able to override arbitrary execution-environment
            # vars (PATH, LD_PRELOAD, PYTHONPATH, …) for a trusted allow-listed
            # script. The agent owns the environment boundary. Also skip entries
            # that would make Popen(env=...) raise ValueError (NUL bytes, or "="
            # in the key).
            if (
                isinstance(key, str)
                and isinstance(value, str)
                and key.startswith("BORG_UI_")
                and "=" not in key
                and "\x00" not in key
                and "\x00" not in value
            ):
                env[key] = value
    return env


def _bounded_append(buffer: list[str], size: list[int], line: str) -> None:
    # Enforce the cap per append, in BYTES (multibyte output must not exceed the
    # byte budget), truncating a single oversized line to the remaining budget so
    # one huge line can't blow past _MAX_CAPTURED_BYTES.
    remaining = _MAX_CAPTURED_BYTES - size[0]
    if remaining <= 0:
        return
    encoded = line.encode("utf-8", "replace")
    if len(encoded) + 1 > remaining:
        line = _truncate_utf8(line, remaining)
        encoded = line.encode("utf-8", "replace")
    size[0] += len(encoded) + 1
    buffer.append(line)


def execute_script_run_job(
    job: dict[str, Any],
    client,
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> ScriptRunResult:
    """Run an allow-listed script on the agent node.

    stdout and stderr are streamed separately as job logs and also captured
    (bounded) into the terminal result together with the ``return_code``, so the
    server can persist them and classify the outcome (0/1/>1)."""
    job_id = int(job["id"])
    payload = job.get("payload") or {}
    script = payload.get("script") if isinstance(payload.get("script"), dict) else {}
    name = script.get("name")

    seq_lock = threading.Lock()
    seq = [0]

    def next_seq() -> int:
        with seq_lock:
            value = seq[0]
            seq[0] += 1
            return value

    def log(stream: str, message: str) -> None:
        client.send_log(job_id, sequence=next_seq(), stream=stream, message=message)

    try:
        resolved = resolve_allowed_script(name)
    except ScriptNotAllowed as exc:
        error_message = f"Script not allowed: {exc}"
        log("stderr", error_message)
        client.fail_job(job_id, error_message=error_message)
        return ScriptRunResult(job_id=job_id, status="failed", message=error_message)

    env = _build_env(payload.get("env"))
    log("stdout", f"Starting script.run: {resolved}")

    try:
        popen_kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            # Decode tolerantly: a script emitting non-UTF-8 bytes must not raise
            # UnicodeDecodeError inside the pump thread (which would drop output
            # and could stall the child once the pipe buffer fills).
            "encoding": "utf-8",
            "errors": "replace",
            "env": env,
        }
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen([str(resolved)], **popen_kwargs)
    except (OSError, ValueError) as exc:
        # ValueError: an invalid env entry that slipped through (belt-and-suspenders
        # with _build_env's filtering) — report it, don't drop the job silently.
        error_message = f"Failed to start script: {exc}"
        log("stderr", error_message)
        client.fail_job(job_id, error_message=error_message)
        return ScriptRunResult(job_id=job_id, status="failed", message=error_message)

    stdout_buf: list[str] = []
    stdout_size = [0]
    stderr_buf: list[str] = []
    stderr_size = [0]

    def pump(stream_name: str, pipe, buffer: list[str], size: list[int]) -> None:
        if pipe is None:
            return
        # Bounded reads: readline(limit) caps each read at the frame budget, so a
        # newline-free stream is drained in chunks instead of buffered whole.
        while True:
            try:
                line = pipe.readline(_MAX_LOG_MESSAGE_BYTES)
            except (OSError, ValueError):
                break
            if not line:
                break
            message = line.rstrip("\n")
            _bounded_append(buffer, size, message)
            try:
                # Bound the streamed frame too, not just the persisted aggregate.
                log(stream_name, _truncate_utf8(message, _MAX_LOG_MESSAGE_BYTES))
            except Exception:
                # A log-delivery failure must not stop draining — a full pipe
                # would otherwise block the child process forever.
                pass

    out_thread = threading.Thread(
        target=pump, args=("stdout", process.stdout, stdout_buf, stdout_size), daemon=True
    )
    err_thread = threading.Thread(
        target=pump, args=("stderr", process.stderr, stderr_buf, stderr_size), daemon=True
    )
    out_thread.start()
    err_thread.start()

    def _close_pipes() -> None:
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                try:
                    pipe.close()
                except OSError:
                    pass

    while True:
        try:
            return_code = process.wait(timeout=0.2)
            break
        except subprocess.TimeoutExpired:
            if should_cancel and should_cancel():
                cancel_message = "Cancellation requested; stopping script"
                log("stderr", cancel_message)
                return_code = _terminate_process(process)
                # Bounded joins so a descendant holding the pipe open can't hang
                # cancellation; _close_pipes() then unblocks any lingering read.
                out_thread.join(_CANCEL_JOIN_TIMEOUT)
                err_thread.join(_CANCEL_JOIN_TIMEOUT)
                _close_pipes()
                client.cancel_job(job_id)
                return ScriptRunResult(
                    job_id=job_id,
                    status="canceled",
                    return_code=return_code,
                    message="script.run canceled",
                )

    out_thread.join()
    err_thread.join()
    _close_pipes()

    # Report the facts; the server classifies 0 / 1 / >1. Even a non-zero exit is
    # a *completed* run of the agent job — the hook's pass/warn/fail verdict is
    # derived server-side from return_code.
    client.complete_job(
        job_id,
        result={
            "return_code": return_code,
            "stdout": "\n".join(stdout_buf),
            "stderr": "\n".join(stderr_buf),
        },
    )
    return ScriptRunResult(
        job_id=job_id,
        status="completed",
        return_code=return_code,
        message=f"script exited with code {return_code}",
    )
