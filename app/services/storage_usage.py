"""Repository size, read-only, from the best source Borg offers (#934).

Order for Borg 2, which reports no size through any command:

1. the chunk-index sum through Borg's own Python API, run with the
   interpreter next to the configured Borg 2 binary (a venv install): the
   bytes of every indexed object, no lock, no pack access, works while a
   backup holds the lock;
2. a store-level measurement per URL scheme, which counts file bytes
   including pack headers and the index ("storage used");
3. nothing: the caller leaves the stored size alone, which a Borg 2
   compact's `--stats` figure then fills (`compact_stats`, written by
   maintenance_state, never over a measurement from 1).

These are different quantities, which is why the caller records the source
next to the value. `compact --stats` reports pack file bytes, which include
data no index entry covers (an interrupted write, before compact); on a
repository whose packs are fully indexed the index sum matched it byte for
byte in every measurement taken (b23, b24), but the two are not identical
by definition. Storage used adds the index and other store files on top.

Borg 1 keeps `info --json` `cache.stats.unique_csize`. Both versions also
report `repository.last_modified` (the last manifest write), which the
caller persists alongside.
"""

import asyncio
import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import unquote, urlsplit

import structlog

from app.utils.datetime_utils import parse_borg_archive_time

logger = structlog.get_logger()

SOURCE_BORG1_CACHE_STATS = "borg1_cache_stats"
SOURCE_BORG2_INDEX = "borg2_index"
SOURCE_STORAGE_USED = "storage_used"
# Written by the compact paths (maintenance_state), not measured here.
SOURCE_COMPACT_STATS = "compact_stats"


def _port(parts) -> Optional[int]:
    """The URL port, or None when there is none. Raises ValueError for a
    port that is not a number in 0..65535 (`urlsplit` defers that check to
    the `.port` property)."""
    return parts.port


def valid_target(url: str) -> bool:
    """False when the URL carries a port Borg could never connect to. Such
    a URL is rejected as unmeasurable rather than measured against some
    other endpoint."""
    try:
        _port(urlsplit(url))
    except ValueError:
        return False
    return True


def _host_port(parts) -> str:
    """host[:port] for a netloc, IPv6 literals back in brackets."""
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    port = _port(parts)
    return f"{host}:{port}" if port is not None else host


def safe_url(url: str) -> str:
    """A repository URL for logs: the credentials replaced by `***`.

    `user:secret@host` becomes `user:***@host`. A userinfo without a
    password is masked whole (`token@host` becomes `***@host`): a REST
    store takes it as the Basic-auth credential, so it is the secret.

    Never raises and never keeps a credential fragment: this runs while a
    failure is being logged. The userinfo is cut at the last `@` (a
    password may contain `@`), the host:port text is kept as written
    without validating the port, and a URL that does not even parse
    becomes a fixed placeholder rather than its own text."""
    try:
        parts = urlsplit(url)
        if parts.username is None and not parts.password:
            return url
        userinfo, _, hostport = parts.netloc.rpartition("@")
        if parts.password:
            redacted = f"{userinfo.split(':', 1)[0]}:***"
        else:
            redacted = "***"
        return parts._replace(netloc=f"{redacted}@{hostport}").geturl()
    except ValueError:
        return "<unparseable repository url>"


# Sums Repository.list() storage sizes; lock=False reads while another borg
# holds the exclusive lock (like --bypass-lock). Needs no key: the index is
# not encrypted. Prints one JSON object. The URL arrives in the environment
# (REPOSITORY_URL_ENV), never on the command line: it may carry credentials
# and a process list shows arguments.
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


@dataclass
class SizeResult:
    bytes: Optional[int] = None
    objects: Optional[int] = None
    source: Optional[str] = None
    last_modified: Optional[datetime] = None


async def _communicate(process, timeout: int) -> tuple[bytes, bytes]:
    """communicate() with a deadline that also ends the child: wait_for only
    cancels the wait, a timed-out (or cancelled) borg or rclone would keep
    running."""
    try:
        return await asyncio.wait_for(process.communicate(), timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        try:
            process.kill()
        except ProcessLookupError:
            # already gone; kill() would otherwise replace the cancellation
            # with an OSError that the callers treat as "failed to start"
            pass
        await process.wait()
        raise


# -- Borg 2 chunk index --------------------------------------------------------


def _venv_python(binary: str) -> Optional[str]:
    """The python of the venv that `binary` lives in, or None. The binary is
    resolved through symlinks, the python is not (a venv's python is a
    symlink to the base interpreter; running it by its venv path is what
    selects the venv's site-packages). A python without a `pyvenv.cfg`
    next to its bin directory is a system interpreter, where `borg` is not
    importable, so it does not count."""
    path = shutil.which(binary) or binary
    real = os.path.realpath(path)
    bindir = os.path.dirname(real)
    candidate = os.path.join(bindir, "python")
    if not os.access(candidate, os.X_OK):
        return None
    if not os.path.isfile(os.path.join(os.path.dirname(bindir), "pyvenv.cfg")):
        return None
    return candidate


def borg2_interpreter(borg2_binary: str, env: Optional[dict] = None) -> Optional[str]:
    """The python of the Borg 2 venv, or None for a standalone binary.

    `BORG2_BINARY` in the prepared environment (the deployment's own
    pointer at the real binary) is tried first: the command on PATH is
    often a wrapper script whose directory holds the system python."""
    candidates = []
    pointed = (env if env is not None else os.environ).get("BORG2_BINARY")
    if pointed:
        candidates.append(pointed)
    candidates.append(borg2_binary)
    for binary in candidates:
        python = _venv_python(binary)
        if python is not None:
            return python
    return None


async def borg2_index_size(
    repository_url: str,
    *,
    borg2_binary: str,
    env: Optional[dict] = None,
    timeout: int = 60,
) -> Optional[tuple[int, int]]:
    """(bytes, objects) from the chunk index, or None when Borg is not
    importable next to the binary or the read failed."""
    python = borg2_interpreter(borg2_binary, env)
    if python is None:
        return None
    child_env = dict(env if env is not None else os.environ)
    child_env[REPOSITORY_URL_ENV] = repository_url
    try:
        process = await asyncio.create_subprocess_exec(
            python,
            "-c",
            INDEX_SUM_SCRIPT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=child_env,
        )
        stdout, stderr = await _communicate(process, timeout)
    except asyncio.TimeoutError:
        logger.warning(
            "borg2 index size timed out", repository=safe_url(repository_url)
        )
        return None
    except OSError as exc:
        logger.warning("borg2 index size failed to start", error=str(exc))
        return None
    if process.returncode != 0:
        logger.warning(
            "borg2 index size failed",
            repository=safe_url(repository_url),
            stderr=stderr.decode(errors="replace")[-300:],
        )
        return None
    try:
        data = json.loads(stdout.decode() or "{}")
        return int(data["bytes"]), int(data["objects"])
    except (ValueError, KeyError, TypeError):
        return None


# -- store-level fallbacks --------------------------------------------------------


def _rclone_value(value: str) -> str:
    """Quote a connection-string parameter value when rclone's syntax needs
    it (commas, colons, quotes); quotes inside are doubled."""
    if any(ch in value for ch in ',:"'):
        return '"' + value.replace('"', '""') + '"'
    return value


def rclone_remote_for(url: str, *, key_file: Optional[str] = None) -> Optional[str]:
    """An rclone on-the-fly remote for a Borg store URL, or None.

    `sftp://user@host:port/./rel` addresses a path relative to the login
    directory, `sftp://user@host:port/abs` an absolute one; `rclone:remote:path`
    is passed through.
    """
    # the scheme is case-insensitive, the remote name after it is not
    if url[: len("rclone:")].lower() == "rclone:":
        return url[len("rclone:") :] or None
    parts = urlsplit(url)
    if parts.scheme != "sftp" or not parts.hostname:
        return None
    try:
        port = _port(parts)
    except ValueError:
        return None  # an impossible port: nothing rclone could connect to
    options = [f"host={_rclone_value(parts.hostname)}"]
    if parts.username:
        options.append(f"user={_rclone_value(unquote(parts.username))}")
    if port is not None:
        options.append(f"port={port}")
    if key_file:
        options.append(f"key_file={_rclone_value(key_file)}")
    path = unquote(parts.path)
    if path.startswith("/./"):
        path = path[3:]
    elif path.startswith("/~/"):
        path = path[3:]
    return f":sftp,{','.join(options)}:{path}"


async def rclone_storage_used(
    url: str,
    *,
    key_file: Optional[str] = None,
    env: Optional[dict] = None,
    timeout: int = 600,
) -> Optional[int]:
    """`rclone size --json`. `env` is the prepared Borg environment: it
    carries `RCLONE_CONFIG` for the managed remotes, which an inherited
    process environment does not."""
    remote = rclone_remote_for(url, key_file=key_file)
    rclone = shutil.which("rclone")
    if remote is None or rclone is None:
        return None
    try:
        process = await asyncio.create_subprocess_exec(
            rclone,
            "size",
            "--json",
            remote,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await _communicate(process, timeout)
    except (asyncio.TimeoutError, OSError) as exc:
        logger.warning("rclone size failed", repository=safe_url(url), error=str(exc))
        return None
    if process.returncode != 0:
        logger.warning(
            "rclone size failed",
            repository=safe_url(url),
            stderr=stderr.decode(errors="replace")[-300:],
        )
        return None
    try:
        value = int(json.loads(stdout.decode() or "{}")["bytes"])
    except (ValueError, KeyError, TypeError):
        return None
    return value if value > 0 else None


# A borgstore layout nests a few levels (data/xx/yy); a listing deeper than
# this is a loop or not a store.
HTTP_WALK_MAX_DEPTH = 16
# One directory listing is bounded too: a server that keeps sending must
# neither fill memory nor outlive the walk.
HTTP_LISTING_MAX_BYTES = 64 * 1024 * 1024
HTTP_CHUNK_BYTES = 64 * 1024


def _http_walk(base_url: str, timeout: int, budget: int = 600) -> Optional[int]:
    """Sum the sizes a borgstore REST server lists (`GET <dir>/`).

    `timeout` bounds one request, `budget` the whole walk: a listing that
    points back at an ancestor, or one large enough, must not keep the
    worker thread past the caller's time."""
    import requests

    parts = urlsplit(base_url)
    # urlsplit keeps credentials percent-encoded; requests wants the values.
    auth = (
        (unquote(parts.username), unquote(parts.password or ""))
        if parts.username
        else None
    )
    root = f"{parts.scheme}://{_host_port(parts)}{parts.path.rstrip('/')}"
    headers = {"Accept": "application/vnd.x.borgstore.rest.v1"}
    total = 0
    deadline = time.monotonic() + budget

    def fetch(url: str) -> list:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("REST store walk exceeded its time budget")
        # requests' timeout bounds each socket operation, not the request:
        # cap it at what is left of the budget and check the clock between
        # chunks, so a server that keeps sending cannot outlive the walk.
        # Never follow a redirect: the store could send the credentials and
        # the walk to another origin.
        response = requests.get(
            url,
            auth=auth,
            headers=headers,
            timeout=min(timeout, remaining),
            allow_redirects=False,
            stream=True,
        )
        try:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_content(chunk_size=HTTP_CHUNK_BYTES):
                body += chunk
                if len(body) > HTTP_LISTING_MAX_BYTES:
                    raise RuntimeError("REST listing larger than a borgstore directory")
                if time.monotonic() > deadline:
                    raise TimeoutError("REST store walk exceeded its time budget")
        finally:
            response.close()
        return json.loads(bytes(body))

    def walk(name: str, depth: int = 0) -> None:
        nonlocal total
        if depth > HTTP_WALK_MAX_DEPTH:
            raise RuntimeError("REST listing nested deeper than a borgstore layout")
        for item in fetch(f"{root}/{name}/" if name else f"{root}/"):
            child = f"{name}/{item['name']}" if name else item["name"]
            if item.get("directory"):
                walk(child, depth + 1)
            else:
                total += int(item.get("size") or 0)

    walk("")
    return total


async def http_storage_used(
    url: str, *, timeout: int = 60, budget: int = 600
) -> Optional[int]:
    """`http(s)://` borgstore REST servers list directories with sizes."""
    try:
        value = await asyncio.to_thread(_http_walk, url, timeout, budget)
    except Exception as exc:
        logger.warning(
            "REST store walk failed", repository=safe_url(url), error=str(exc)
        )
        return None
    return value if value and value > 0 else None


async def du_storage_used(
    url_or_path: str, *, key_file: Optional[str] = None, timeout: int = 600
) -> Optional[int]:
    """`du -sb` locally or over ssh (`ssh://user@host:port/path`)."""
    from app.utils.fs import calculate_path_size_bytes

    value = await calculate_path_size_bytes(
        [url_or_path], timeout=timeout, key_file=key_file
    )
    return value if value and value > 0 else None


def store_target(repository_path: str) -> tuple[str, Optional[str]]:
    """(tool, target) for the store-level fallback, or ("", None).

    `rest://user@host:port/path` is borgstore's "ssh to host and run the REST
    server on stdio" form. The key on such a host is normally bound to that
    server (`command="...",restrict` in authorized_keys), so a shell command
    over ssh does not run: no store-level measurement, only the chunk index
    through Borg itself. `rest:///path` is local. `http(s)://` is a REST
    server listing.
    """
    # URI schemes are case-insensitive; the target keeps the text as given.
    lowered = repository_path.lower()
    if lowered.startswith(("http://", "https://")):
        return "http", repository_path
    if lowered.startswith(("sftp://", "rclone:")):
        return "rclone", repository_path
    if lowered.startswith("rest://"):
        parts = urlsplit(repository_path)
        if parts.hostname:
            return "", None
        return "du", parts.path
    if lowered.startswith("ssh://"):
        return "du", repository_path
    if "://" not in repository_path and not lowered.startswith(("s3:", "b2:")):
        return "du", repository_path
    return "", None


async def storage_used(
    repository_path: str,
    *,
    key_file: Optional[str] = None,
    env: Optional[dict] = None,
    timeout: int = 600,
) -> Optional[int]:
    """Store-level bytes by scheme. `env` reaches rclone; du takes the key
    file only (ssh reads no Borg variables) and the REST walk needs neither.
    A URL with an impossible port is unknown, not measured elsewhere."""
    if not valid_target(repository_path):
        logger.warning(
            "repository URL has an invalid port", repository=safe_url(repository_path)
        )
        return None
    tool, target = store_target(repository_path)
    if tool == "http":
        return await http_storage_used(target, timeout=min(timeout, 60), budget=timeout)
    if tool == "rclone":
        return await rclone_storage_used(
            target, key_file=key_file, env=env, timeout=timeout
        )
    if tool == "du":
        return await du_storage_used(target, key_file=key_file, timeout=timeout)
    return None


# -- the source order -------------------------------------------------------------


def _last_modified(payload: dict, *, timezone_name: str = "UTC") -> Optional[datetime]:
    value = (payload.get("repository") or {}).get("last_modified")
    return parse_borg_archive_time(value, timezone_name=timezone_name)


async def measure_repository_size(
    repository,
    *,
    env: Optional[dict] = None,
    temp_key_file: Optional[str] = None,
    info_timeout: int = 60,
    use_bypass_lock: bool = False,
) -> SizeResult:
    """Best available size and `last_modified` for a server-executed
    repository. Never returns 0 bytes: unknown is `None`."""
    from app.utils.borg_env import effective_repository_remote_path

    remote_path = effective_repository_remote_path(repository)
    if (repository.borg_version or 1) != 2:
        from app.core.borg import borg
        from app.core.borg_router import BorgRouter

        cmd = BorgRouter(repository).build_repo_info_command(repository.path)
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        if use_bypass_lock:
            cmd.append("--bypass-lock")
        info_env = dict(env or {})
        info_env["TZ"] = "UTC"
        result = await borg._execute_command(cmd, timeout=info_timeout, env=info_env)
        if not result.get("success"):
            return SizeResult()
        try:
            payload = json.loads(result.get("stdout") or "{}")
        except json.JSONDecodeError:
            return SizeResult()
        raw = ((payload.get("cache") or {}).get("stats") or {}).get("unique_csize")
        # one normalized value feeds both fields: a source without bytes
        # would label a size this measurement did not produce
        size = (
            int(raw)
            if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw > 0
            else None
        )
        return SizeResult(
            bytes=size,
            source=SOURCE_BORG1_CACHE_STATS if size else None,
            last_modified=_last_modified(payload),
        )

    from app.core.borg2 import _get_borg2_binary, borg2

    last_modified = None
    rinfo = await borg2.rinfo(
        repository.path,
        passphrase=repository.passphrase,
        remote_path=remote_path,
        env=env,
    )
    if rinfo.get("success"):
        try:
            last_modified = _last_modified(json.loads(rinfo.get("stdout") or "{}"))
        except json.JSONDecodeError:
            pass

    index_env = dict(env or {})
    if repository.passphrase:
        index_env.setdefault("BORG_PASSPHRASE", repository.passphrase)
    if remote_path:
        index_env.setdefault("BORG_REMOTE_PATH", remote_path)
    indexed = await borg2_index_size(
        repository.path,
        borg2_binary=_get_borg2_binary(),
        env=index_env,
        timeout=info_timeout,
    )
    if indexed is not None:
        return SizeResult(
            bytes=indexed[0] or None,
            objects=indexed[1],
            source=SOURCE_BORG2_INDEX if indexed[0] else None,
            last_modified=last_modified,
        )

    # the whole measurement runs under the repository's metadata lock, so
    # the store-level fallback gets the same budget as the index read
    used = await storage_used(
        repository.path, key_file=temp_key_file, env=env, timeout=info_timeout
    )
    return SizeResult(
        bytes=used,
        source=SOURCE_STORAGE_USED if used else None,
        last_modified=last_modified,
    )
