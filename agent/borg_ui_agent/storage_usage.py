"""Measure a Borg 2 repository on the agent, read-only (`repository.storage_usage`).

Same order as the server's app/services/storage_usage.py, in synchronous
form for the agent:

1. the chunk-index sum through Borg's own Python API, with the interpreter
   next to the resolved Borg 2 binary (a venv install); a standalone binary
   has none: the bytes of every indexed object;
2. a store-level measurement per URL scheme ("storage used": file bytes
   including pack headers and the index);
3. nothing: the result says so instead of reporting 0.

Every measurement is a child process in its own process group, so a
cancelled or timed-out job ends it and whatever it spawned (ssh, rclone)
instead of leaving it running; the REST walk is a child too, because a
thread blocked on a socket cannot be ended. `measure` spreads one time
budget over its steps.
"""

import inspect
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Callable, Optional
from urllib.parse import unquote, urlsplit

SOURCE_BORG2_INDEX = "borg2_index"
SOURCE_STORAGE_USED = "storage_used"
# storage_used's second slot names the tool that ran; this sentinel means
# no tool ran because the URL cannot be a store (impossible port).
INVALID_URL = "invalid_url"
POLL_SECONDS = 0.5
TERMINATE_GRACE_SECONDS = 5
REQUEST_TIMEOUT = 60  # one request inside the REST walk

ShouldCancel = Optional[Callable[[], bool]]


class Cancelled(Exception):
    """The job was cancelled while a measurement was running."""


def _check_cancel(should_cancel: ShouldCancel) -> None:
    if should_cancel is not None and should_cancel():
        raise Cancelled()


# Keep in sync with app/services/storage_usage.py. The URL arrives in the
# child's environment (REPOSITORY_URL_ENV), never on the command line: it
# may carry credentials and a process list shows arguments.
logger = logging.getLogger(__name__)

REPOSITORY_URL_ENV = "BORG_UI_REPOSITORY_URL"
INDEX_SUM_SCRIPT = """
import json, os
from borg.logger import setup_logging
setup_logging()
from borg.repository import Repository
from borg.helpers import Location
total = objects = 0
marker = None
with Repository(Location(os.environ["BORG_UI_REPOSITORY_URL"]), exclusive=False, lock=False) as repo:
    while True:
        batch = repo.list(limit=100000, marker=marker)
        if not batch:
            break
        for chunk_id, size in batch:
            total += size
            objects += 1
        marker = batch[-1][0]
print(json.dumps({"objects": objects, "bytes": total}))
"""


_URL_CREDENTIALS = re.compile(r"://([^/@\s]*?):([^/@\s]*)@")


def _redact(text: str) -> str:
    """Mask the password of any URL credentials in `text`: Borg prints the
    repository location into its error messages."""
    return _URL_CREDENTIALS.sub(r"://\1:***@", text)


def _venv_python(binary: str) -> Optional[str]:
    """The python of the venv `binary` lives in, or None. The binary is
    resolved through symlinks, the python is not (a venv's python is a
    symlink to the base interpreter; running it by its venv path selects
    the venv's site-packages). Without a pyvenv.cfg next to the bin
    directory it is a system interpreter, where borg is not importable."""
    path = shutil.which(binary) or binary
    real = os.path.realpath(path)
    bindir = os.path.dirname(real)
    candidate = os.path.join(bindir, "python")
    if not os.access(candidate, os.X_OK):
        return None
    if not os.path.isfile(os.path.join(os.path.dirname(bindir), "pyvenv.cfg")):
        return None
    return candidate


def borg2_interpreter(borg_binary: str, env: Optional[dict] = None) -> Optional[str]:
    """The python of the Borg 2 venv, or None for a standalone binary.
    BORG2_BINARY from the job environment is tried first: the command on
    PATH is a wrapper script in the agent image, and the python next to
    it is the system one."""
    candidates = []
    pointed = (env if env is not None else os.environ).get("BORG2_BINARY")
    if pointed:
        candidates.append(pointed)
    candidates.append(borg_binary)
    for binary in candidates:
        python = _venv_python(binary)
        if python is not None:
            return python
    return None


def _signal_group(process: subprocess.Popen, sig: int) -> None:
    """Signal the child's process group (it is a session leader, see _run),
    so ssh, rclone and other descendants get it too; the child alone
    where there is no group."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, sig)
            return
        except ProcessLookupError:
            return
        except PermissionError:
            pass
    try:
        process.send_signal(sig)
    except ProcessLookupError:
        pass


def _group_alive(pgid: int) -> bool:
    """True while any process of the group exists (signal 0 probes)."""
    if os.name != "posix":
        return False
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _stat_is_live(stat: str, pgid: int) -> bool:
    """One `/proc/<pid>/stat` line: True for a member of `pgid` that is not
    a zombie. The command name sits in parentheses and may itself contain
    spaces or parentheses, so the fields are read after the last `)`."""
    try:
        fields = stat[stat.rindex(")") + 1 :].split()
        state, pgrp = fields[0], int(fields[2])
    except (ValueError, IndexError):
        return False
    return pgrp == pgid and state not in ("Z", "X")


def _group_live(pgid: int) -> bool:
    """True while a process of the group is alive and not a zombie. A
    zombie is dead work waiting for its adopter (init, a subreaper) to reap
    it, which is not this process's to do and may never happen in a
    container without an init; `_group_alive` alone would see it forever."""
    if not _group_alive(pgid):
        return False
    if os.path.isdir("/proc"):
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/stat", encoding="utf-8") as handle:
                    if _stat_is_live(handle.read(), pgid):
                        return True
            except OSError:
                continue
        return False
    try:
        listing = subprocess.run(
            ["ps", "-o", "stat=", "-g", str(pgid)],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return True
    return any(
        line.strip() and not line.strip().startswith("Z")
        for line in listing.splitlines()
    )


def _end_group(process: subprocess.Popen) -> None:
    """End the child and every descendant in its process group. The child
    exiting on SIGTERM says nothing about a descendant that ignored it, so
    the group is probed independently of the child's own exit; SIGKILL
    follows after the grace period while any member is still live. Every
    wait is bounded by the grace period, the one after SIGKILL included:
    the signal cannot be caught, so whatever is left is dying, a zombie,
    or a child stuck in uninterruptible sleep that no signal reaches, and
    none of them is worth blocking a cancellation for. Returns within
    about three grace periods in the worst case; a child that never
    became waitable is not reaped by this function, only abandoned."""
    pgid = process.pid
    _signal_group(process, signal.SIGTERM)
    deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
    try:
        process.wait(timeout=TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass
    while process.poll() is None or _group_live(pgid):
        if time.monotonic() >= deadline:
            _signal_group(process, signal.SIGKILL)
            kill_deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
            # SIGKILL is not delivered to a child in uninterruptible sleep
            # (a hung network mount under du, ssh or rclone), so this wait
            # is bounded too. Such a child stays in subprocess._active and
            # is polled when a later Popen is created; nothing reaps it
            # promptly, the cancellation just stops waiting for it.
            try:
                process.wait(timeout=TERMINATE_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                pass
            while _group_live(pgid) and time.monotonic() < kill_deadline:
                time.sleep(POLL_SECONDS / 5)
            break
        time.sleep(POLL_SECONDS / 5)


def _run(
    cmd: list[str],
    *,
    timeout: float,
    env: Optional[dict] = None,
    should_cancel: ShouldCancel = None,
) -> subprocess.CompletedProcess:
    """subprocess.run with a deadline and a cancel check; both end the child
    and its process group (terminate, then kill) and return only once the
    child and its descendants have exited."""
    _check_cancel(should_cancel)
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=os.name == "posix",
    )
    deadline = time.monotonic() + timeout
    cancelled = False
    try:
        while True:
            try:
                stdout, stderr = process.communicate(timeout=POLL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                if should_cancel is not None and should_cancel():
                    cancelled = True
                    raise
                if time.monotonic() >= deadline:
                    raise
    except subprocess.TimeoutExpired:
        _end_group(process)
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()
        if cancelled:
            raise Cancelled()
        raise
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


def index_size(
    url: str,
    *,
    borg_binary: str,
    env: Optional[dict],
    timeout: float,
    should_cancel: ShouldCancel = None,
) -> Optional[tuple[int, int]]:
    python = borg2_interpreter(borg_binary, env)
    if python is None:
        return None
    child_env = dict(env if env is not None else os.environ)
    child_env[REPOSITORY_URL_ENV] = url
    try:
        proc = _run(
            [python, "-c", INDEX_SUM_SCRIPT],
            timeout=timeout,
            env=child_env,
            should_cancel=should_cancel,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("borg2 index size did not run: %s", _redact(str(exc)))
        return None
    if proc.returncode != 0:
        # The store measurement that follows reports its own reason; without
        # this line the index failure would leave no trace.
        logger.warning(
            "borg2 index size failed rc=%s stderr=%s",
            proc.returncode,
            _redact((proc.stderr or "")[-300:]),
        )
        return None
    try:
        data = json.loads(proc.stdout or "{}")
        return int(data["bytes"]), int(data["objects"])
    except (ValueError, KeyError, TypeError):
        logger.warning("borg2 index size printed no usable result")
        return None


def _rclone_value(value: str) -> str:
    if any(ch in value for ch in ',:"'):
        return '"' + value.replace('"', '""') + '"'
    return value


def valid_target(url: str) -> bool:
    """False when the URL carries a port Borg could never connect to
    (`urlsplit(...).port` raises for a non-numeric or out-of-range one);
    such a URL is unmeasurable rather than measured elsewhere."""
    try:
        urlsplit(url).port
    except ValueError:
        return False
    return True


def rclone_remote_for(url: str) -> Optional[str]:
    # the scheme is case-insensitive, the remote name after it is not
    if url[: len("rclone:")].lower() == "rclone:":
        return url[len("rclone:") :] or None
    parts = urlsplit(url)
    if parts.scheme != "sftp" or not parts.hostname:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    options = [f"host={_rclone_value(parts.hostname)}"]
    if parts.username:
        options.append(f"user={_rclone_value(unquote(parts.username))}")
    if port:
        options.append(f"port={port}")
    path = unquote(parts.path)
    if path.startswith("/./") or path.startswith("/~/"):
        path = path[3:]
    return f":sftp,{','.join(options)}:{path}"


def rclone_storage_used(
    url: str,
    *,
    timeout: float,
    env: Optional[dict] = None,
    should_cancel: ShouldCancel = None,
) -> Optional[int]:
    """`rclone size --json` in the job's environment: that is where the
    server-sent RCLONE_CONFIG (and any other rclone variable) lives, not
    in the agent process environment."""
    remote = rclone_remote_for(url)
    rclone = shutil.which("rclone")
    if remote is None or rclone is None:
        return None
    try:
        proc = _run(
            [rclone, "size", "--json", remote],
            timeout=timeout,
            env=env,
            should_cancel=should_cancel,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("rclone size did not run: %s", _redact(str(exc)))
        return None
    if proc.returncode != 0:
        logger.warning(
            "rclone size failed rc=%s stderr=%s",
            proc.returncode,
            _redact((proc.stderr or "")[-300:]),
        )
        return None
    try:
        value = int(json.loads(proc.stdout or "{}")["bytes"])
    except (ValueError, KeyError, TypeError):
        logger.warning("rclone size printed no usable result")
        return None
    return value if value > 0 else None


def _http_walk(
    url: str,
    timeout: float,
    *,
    max_depth: int = 16,
    max_listing_bytes: int = 64 * 1024 * 1024,
) -> int:
    """Sum the sizes a borgstore REST server lists (`GET <dir>/`).

    Self-contained on purpose: the child process runs this function's
    source (see _http_walk_command), so it imports what it needs itself
    and carries its limits as defaults. Same guards as the server's walk
    (app/services/storage_usage.py): no redirect is followed (the store
    could send the credentials and the walk to another origin), one
    listing is read in chunks up to `max_listing_bytes`, and a listing
    nested deeper than a borgstore layout ends the walk. The outer process
    deadline bounds the whole traversal.
    """
    import json
    from urllib.parse import unquote, urlsplit

    import requests

    parts = urlsplit(url)
    auth = (
        (unquote(parts.username), unquote(parts.password or ""))
        if parts.username
        else None
    )
    host = parts.hostname or ""
    if ":" in host:  # IPv6 literal: urlsplit strips the brackets
        host = f"[{host}]"
    netloc = host + (f":{parts.port}" if parts.port else "")
    root = f"{parts.scheme}://{netloc}{parts.path.rstrip('/')}"
    headers = {"Accept": "application/vnd.x.borgstore.rest.v1"}
    total = 0

    def fetch(target: str) -> list:
        response = requests.get(
            target,
            auth=auth,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )
        try:
            if 300 <= response.status_code < 400:
                raise RuntimeError("REST store redirected the listing")
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                body += chunk
                if len(body) > max_listing_bytes:
                    raise RuntimeError("REST listing larger than a borgstore directory")
        finally:
            response.close()
        return json.loads(bytes(body))

    def walk(name: str, depth: int = 0) -> None:
        nonlocal total
        if depth > max_depth:
            raise RuntimeError("REST listing nested deeper than a borgstore layout")
        for item in fetch(f"{root}/{name}/" if name else f"{root}/"):
            child = f"{name}/{item['name']}" if name else item["name"]
            if item.get("directory"):
                walk(child, depth + 1)
            else:
                total += int(item.get("size") or 0)

    walk("")
    return total


def _http_walk_command() -> list[str]:
    """The walk as a child of this interpreter. The URL travels in the
    environment (BORG_UI_STORE_URL), not on the command line: it may carry
    credentials, and a process list shows arguments."""
    script = (
        "import json, os\n"
        + inspect.getsource(_http_walk)
        + "\nprint(json.dumps({'bytes': _http_walk("
        "os.environ['BORG_UI_STORE_URL'], "
        "float(os.environ['BORG_UI_REQUEST_TIMEOUT']))}))\n"
    )
    return [sys.executable, "-c", script]


def http_storage_used(
    url: str, *, timeout: float, should_cancel: ShouldCancel = None
) -> Optional[int]:
    """`timeout` bounds the whole traversal; each request inside it gets at
    most REQUEST_TIMEOUT. Cancellation ends the child like any other."""
    env = dict(os.environ)
    env["BORG_UI_STORE_URL"] = url
    env["BORG_UI_REQUEST_TIMEOUT"] = str(min(timeout, REQUEST_TIMEOUT))
    try:
        proc = _run(
            _http_walk_command(), timeout=timeout, env=env, should_cancel=should_cancel
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("REST store walk did not run: %s", _redact(str(exc)))
        return None
    if proc.returncode != 0:
        # the child's traceback names the cause (401, redirect, cap, depth)
        logger.warning(
            "REST store walk failed rc=%s stderr=%s",
            proc.returncode,
            _redact((proc.stderr or "")[-300:]),
        )
        return None
    try:
        value = int(json.loads(proc.stdout or "{}")["bytes"])
    except (ValueError, KeyError, TypeError):
        logger.warning("REST store walk printed no usable result")
        return None
    return value if value > 0 else None


def du_storage_used(
    path: str, *, timeout: float, should_cancel: ShouldCancel = None
) -> Optional[int]:
    try:
        proc = _run(
            ["du", "-sb", "--", path], timeout=timeout, should_cancel=should_cancel
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("du did not run: %s", _redact(str(exc)))
        return None
    if proc.returncode != 0:
        logger.warning(
            "du failed rc=%s stderr=%s",
            proc.returncode,
            _redact((proc.stderr or "")[-300:]),
        )
        return None
    fields = (proc.stdout or "").split()
    if fields and fields[0].isdigit() and int(fields[0]) > 0:
        return int(fields[0])
    return None


def store_target(url: str) -> tuple[str, Optional[str]]:
    """(tool, target) for the store-level fallback, or ("", None).

    `rest://user@host/path` runs borgstore's REST server over ssh behind a
    forced command, so no shell command reaches its files; only `rest:///`
    (local) is measurable with du.
    """
    # URI schemes are case-insensitive; the target keeps the text as given.
    lowered = url.lower()
    if lowered.startswith(("http://", "https://")):
        return "http", url
    if lowered.startswith(("sftp://", "rclone:")):
        return "rclone", url
    if lowered.startswith("rest://"):
        parts = urlsplit(url)
        return ("", None) if parts.hostname else ("du", parts.path)
    if "://" not in url and not lowered.startswith(("s3:", "b2:")):
        return "du", url
    return "", None


def storage_used(
    url: str,
    *,
    timeout: float,
    env: Optional[dict] = None,
    should_cancel: ShouldCancel = None,
) -> tuple[Optional[int], str]:
    """Store-level bytes by scheme. `env` (the job environment) reaches
    rclone; du reads no Borg or rclone variables and the REST walk takes
    the URL alone. A URL with an impossible port is unknown."""
    if not valid_target(url):
        return None, INVALID_URL
    tool, target = store_target(url)
    if tool == "http":
        return (
            http_storage_used(target, timeout=timeout, should_cancel=should_cancel),
            tool,
        )
    if tool == "rclone":
        return (
            rclone_storage_used(
                target, timeout=timeout, env=env, should_cancel=should_cancel
            ),
            tool,
        )
    if tool == "du":
        return (
            du_storage_used(target, timeout=timeout, should_cancel=should_cancel),
            tool,
        )
    return None, ""


def measure(
    url: str,
    *,
    borg_version: int,
    borg_binary: str,
    env: Optional[dict] = None,
    timeout: float = 600,
    should_cancel: ShouldCancel = None,
) -> dict[str, Any]:
    """The job result: bytes, objects and source, or an explicit reason.
    `timeout` is one budget for all steps together. Raises Cancelled when
    the job is cancelled between or during steps."""
    if borg_version != 2:
        return {
            "bytes": None,
            "objects": None,
            "source": None,
            "reason": "borg1_uses_rinfo",
        }
    deadline = time.monotonic() + timeout

    def remaining() -> float:
        return max(0.0, deadline - time.monotonic())

    _check_cancel(should_cancel)
    indexed = index_size(
        url,
        borg_binary=borg_binary,
        env=env,
        timeout=remaining(),
        should_cancel=should_cancel,
    )
    if indexed is not None and indexed[0] > 0:
        size, objects = indexed
        return {"bytes": size, "objects": objects, "source": SOURCE_BORG2_INDEX}
    # An empty index is not an empty store (config, keys, packs the index
    # does not cover yet): measure the store, or say why that failed.
    _check_cancel(should_cancel)
    budget = remaining()
    if budget <= 0:
        return {"bytes": None, "objects": None, "source": None, "reason": "timeout"}
    used, tool = storage_used(url, timeout=budget, env=env, should_cancel=should_cancel)
    if used:
        return {
            "bytes": used,
            "objects": None,
            "source": SOURCE_STORAGE_USED,
            "tool": tool,
        }
    if tool == INVALID_URL:
        reason = INVALID_URL
    elif not tool:
        reason = "unsupported_scheme"
    else:
        reason = f"{tool}_failed"
    return {"bytes": None, "objects": None, "source": None, "reason": reason}
