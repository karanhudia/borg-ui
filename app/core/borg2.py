"""Borg 2 command wrapper.

This module is the exclusive home for all borg2 binary interactions.
It is intentionally separate from borg.py — no cross-imports between the two.

Key command differences from Borg 1:
  Repository lifecycle:
    borg  init  REPO            → borg2 rcreate REPO
    borg  info  REPO            → borg2 rinfo   REPO
    borg  delete REPO           → borg2 rdelete REPO

  Archive operations (same CLI shape, different binary):
    borg2 create   REPO::ARCHIVE  ...
    borg2 list     REPO            (list archives)
    borg2 list     REPO::ARCHIVE  (list archive contents)
    borg2 info     REPO::ARCHIVE
    borg2 extract  REPO::ARCHIVE  ...
    borg2 delete   REPO::ARCHIVE
    borg2 prune    REPO
    borg2 compact  REPO           (mandatory after delete/prune — space not freed automatically)
    borg2 check    REPO
    borg2 mount    REPO::ARCHIVE  MOUNTPOINT

  --remote-path is Borg 1 only: Borg 2 has no such option, the remote Borg
  command travels in BORG_REMOTE_PATH (`borg2_remote_path_env`).

  --bypass-lock is Borg 1 only. Borg 2 has no such option either, so the
  bypass_lock arguments below are accepted (callers and the repository
  settings speak for both majors) and ignored. A Borg 2 command that carried
  it would fail at argument parsing, which reads as an unreachable repository
  rather than as a flag this Borg does not know.

  Encryption modes (borg 2 only), translated to repo-create's
  --encryption/--key-location split by BORG2_ENCRYPTION_FLAGS:
    repokey-aes-ocb            (default — recommended)
    repokey-chacha20-poly1305
    keyfile-aes-ocb
    keyfile-chacha20-poly1305
    authenticated
  Borg 2.0.0b25 removed the unencrypted modes; `none` is refused by name.
"""

import asyncio
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional
from urllib.parse import urlsplit

import structlog

from app.config import settings
from app.core.borg_stream import CommandByteStream, CommandLineStream
from app.utils.repository_paths import (  # noqa: F401  (URL rules re-exported)
    BORG2_ONLY_URL_PREFIXES,
    borg1_ssh_address_host,
    borg2_only_url_prefix,
    strip_ssh_url_path,
)
from app.utils.ssh_host_keys import host_key_ssh_opts
from app.utils.ssh_paths import apply_ssh_command_prefix
from app.utils.ssh_utils import public_key_only_ssh_args

logger = structlog.get_logger()

# The encryption modes Borg 2 repositories are offered in, keyed by the combined
# name the API, the UI and the repository row all speak, mapped to the flags
# repo-create wants.
#
# Borg 2's repo-create takes three orthogonal options where the combined name
# is one value: the cipher (--encryption), where the key is stored
# (--key-location) and the id hash (--id-hash, sha256 by default). Translating
# here keeps that split where it belongs — one command builder — instead of
# pushing a schema and vocabulary change through every caller and stored row.
#
# --key-location is omitted where borg's default is what the combined name
# means: `authenticated` keeps its key in the repository. Borg 2 has no
# BLAKE2b modes; the BLAKE3 ones are not offered.
#
# Without encryption the id hash is part of the mode name
# (`authenticated-sha256`/`-blake3`); `authenticated` is the sha256 variant.
#
# Borg 2 has no unencrypted modes: every repository has a key. `none` is not
# mapped to another mode — a repository created under that name would be
# something else than asked for — but refused by name
# (BORG2_REMOVED_ENCRYPTION_MODES).
BORG2_ENCRYPTION_FLAGS: Dict[str, List[str]] = {
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
}

BORG2_ENCRYPTION_MODES = list(BORG2_ENCRYPTION_FLAGS)

# The stored modes only Borg 2 has (`authenticated` is a Borg 1 mode too).
V2_ONLY_ENCRYPTION_MODES = {
    "repokey-aes-ocb",
    "repokey-chacha20-poly1305",
    "keyfile-aes-ocb",
    "keyfile-chacha20-poly1305",
}

# Modes an earlier Borg 2 had, with what to say to a caller that still asks.
BORG2_REMOVED_ENCRYPTION_MODES: Dict[str, str] = {
    "none": (
        "Borg 2 has no unencrypted repositories since 2.0.0b25; use "
        "'authenticated' (data is not encrypted, but protected by a key and "
        "its passphrase) or an encrypted mode"
    ),
}

# Borg 2 betas change the repository format and the command line at short
# intervals, and a repository written by one beta is unreadable to the one
# before it. An endpoint therefore runs at least the Borg 2 this server ships
# (its pin, `CURRENT_VERSIONS` in app/api/borg_binaries.json), and nothing
# older; the minimum moves with the pin.
_VERSION_KEY = re.compile(
    r"\b(\d{1,6})\.(\d{1,6})\.(\d{1,6})(?:(a|b|rc)(\d{1,6}))?(\.dev\d{0,6})?"
)
# An alpha sorts before a beta, a beta before a release candidate, and that
# before the release; a development build before the version it leads to,
# and one of a release (`2.0.0.dev1`) before that release's alphas.
_STAGE_ORDER = {"a": 0, "b": 1, "rc": 2, None: 3}


def _borg2_version_key(version: Optional[str]) -> Optional[tuple]:
    """A sortable key for the first version in a string ("2.0.0b25",
    "borg2 2.0.0rc1", "2.0.0b26.dev3"), or None where there is none. A
    `.devN` build sorts before the version it leads to; what follows it (a
    local `+g...` part) is not compared."""
    match = _VERSION_KEY.search(version or "")
    if not match:
        return None
    major, minor, patch, stage, number, dev = match.groups()
    return (
        int(major),
        int(minor),
        int(patch),
        -1 if dev and stage is None else _STAGE_ORDER[stage],
        int(number or 0),
        0 if dev else 1,
    )


def borg2_minimum_version() -> Optional[str]:
    """The oldest Borg 2 an endpoint may run: the one this server ships."""
    from app.api.borg_binaries import CURRENT_VERSIONS

    return CURRENT_VERSIONS.get("2") or None


def borg2_below_minimum(version: Optional[str]) -> bool:
    """Whether a reported Borg 2 version is older than the server's.

    Only a version that reads as an older Borg 2 is below. An absent or
    unreadable one is not: it is not evidence of an old binary, and an
    endpoint that reports a Borg major never omits the version
    (`detect_borg_binaries` keeps the two together or drops the binary), so
    this covers a hand-made heartbeat only.
    """
    reported = _borg2_version_key(version)
    minimum = _borg2_version_key(borg2_minimum_version())
    if reported is None or minimum is None:
        return False
    return reported < minimum


def borg2_removed_encryption_refusal(mode: str) -> Optional[Dict]:
    """A failed repo-create result for a mode Borg 2 no longer has, or None.
    Shaped like a command result, so callers show it the way they show any
    repo-create that failed."""
    message = BORG2_REMOVED_ENCRYPTION_MODES.get(mode)
    if message is None:
        return None
    return {"return_code": 2, "stdout": "", "stderr": message, "success": False}


def borg2_encryption_flags(mode: str) -> List[str]:
    """The repo-create flags for a combined encryption mode name."""
    if mode in BORG2_REMOVED_ENCRYPTION_MODES:
        raise ValueError(BORG2_REMOVED_ENCRYPTION_MODES[mode])
    try:
        return list(BORG2_ENCRYPTION_FLAGS[mode])
    except KeyError:
        raise ValueError(
            f"unsupported Borg 2 encryption mode {mode!r}; expected one of "
            + ", ".join(BORG2_ENCRYPTION_MODES)
        ) from None


# Borg 2.0.0b25 replaced rest:// by ssh:// (REST over ssh, same path rules)
# and does not reject the old scheme: a URL it does not know is read as a
# local path, so `rest://user@host/repo` names the directory
# `./rest:/user@host/repo` under the working directory. repo-create and
# create succeed there, and the backup never leaves the machine.
REMOVED_REPOSITORY_URL_MESSAGE = (
    "rest:// repository URLs were removed in Borg 2.0.0b25, which reads one as "
    "a local directory. Use ssh://[user@]host[:port]/path instead (the path "
    "rules are the same), and create the repository anew: 2.0.0b25 cannot "
    "read a repository written by an earlier Borg 2 beta."
)


def borg2_repository_url_refusal(repository: Optional[str]) -> Optional[str]:
    """Why Borg 2 must not be run on this repository URL, or None."""
    if (repository or "").strip().lower().startswith("rest://"):
        return REMOVED_REPOSITORY_URL_MESSAGE
    return None


def ensure_borg2_repository_url(repository: Optional[str]) -> None:
    """Raise ValueError for a repository URL Borg 2 would misread."""
    refusal = borg2_repository_url_refusal(repository)
    if refusal:
        raise ValueError(refusal)


def _command_repository(cmd: List[str]) -> Optional[str]:
    """The value of -r on a Borg 2 command line."""
    for index, token in enumerate(cmd[:-1]):
        if token == "-r":
            return cmd[index + 1]
    return None


def borg2_extract_existing_files_flags(existing_files: Optional[str]) -> List[str]:
    """The extract options for what a restore does with a destination that
    already holds files (#1261). "refuse", the default, is the exact restore
    into an empty directory and needs none. "continue" is chosen in the
    restore dialog, next to its caveat: Borg's --continue writes into such a
    directory and skips a file that already has the archived type, mode,
    size and modification time, so a file damaged in place stays damaged."""
    return ["--continue"] if existing_files == "continue" else []


def borg2_restore_target_refusal(
    destination: Optional[str],
    existing_files: Optional[str] = "refuse",
) -> Optional[Dict]:
    """The translatable reason a Borg 2 restore will not go into
    `destination`, or None.

    Borg 2.0.0b25 refuses to extract into a directory that is not empty
    ("Extraction directory ... is not empty", exit 33), the original location
    and a fresh filesystem with its lost+found included. Its way around,
    --continue, skips a file that already has the archived type, mode, size
    and modification time, so a file damaged in place would stay damaged
    behind a restore that reports success. Borg UI passes the option only
    for a restore that asks for it (`existing_files="continue"`); any other
    is refused before Borg runs, with what to do.

    Nothing for a directory that is empty, missing or unreadable: Borg then
    does, or says, what it would without this.
    """
    if not destination or existing_files == "continue":
        return None
    try:
        with os.scandir(destination) as entries:
            occupied = next(entries, None) is not None
    except OSError:
        return None
    if not occupied:
        return None
    return {
        "key": "backend.errors.restore.borg2DestinationNotEmpty",
        "params": {"path": destination},
    }


def borg2_remote_path_env(remote_path: Optional[str]) -> Dict[str, str]:
    """The environment that names the Borg command on the remote side.

    Borg 2 has no --remote-path, only BORG_REMOTE_PATH; a command line that
    carries the option fails at argument parsing.
    """
    return {"BORG_REMOTE_PATH": remote_path} if remote_path else {}


def borg2_rsh_with_repository_port(rsh: str, repository_path: Optional[str]) -> str:
    """The remote shell command with the port of an ssh:// repository URL.

    Borg 2 hands a remote shell it was given (BORG_RSH) to the store as it
    is and adds the URL's port only to the ssh command it builds itself, so
    with BORG_RSH set `ssh://host:2222/path` connects to port 22. A remote
    shell that names a port keeps it.
    """
    if not rsh or not (repository_path or "").startswith("ssh://"):
        return rsh
    try:
        port = urlsplit(repository_path).port
        words = shlex.split(rsh)
    except ValueError:
        return rsh
    if port is None or any(
        word == "-p" or (word.startswith("-p") and word[2:].isdigit()) for word in words
    ):
        return rsh
    return f"{rsh} -p {port}"


def borg2_env_with_repository_port(env: dict, repository_path: Optional[str]) -> dict:
    """`env` with the repository's port in the remote shell it names, in
    place (BORG_RSH, and BORGSTORE_RSH where one is set)."""
    for name in ("BORG_RSH", "BORGSTORE_RSH"):
        if env.get(name):
            env[name] = borg2_rsh_with_repository_port(env[name], repository_path)
    return env


def _borg2_path(tail: str, *, from_url: bool) -> tuple[bool, str]:
    """(absolute, path) of what follows the host in a Borg 2 URL, or of a
    plain path.

    Borg 2 reads `ssh://host/rel` as relative to the login directory and
    `ssh://host//abs` as absolute. A URL tail carries the separator: `//abs`
    is absolute, `/rel` relative. A plain path is absolute with a leading
    slash, except Borg 1's spelling of the login directory, `/./rel`.
    """
    if from_url:
        if tail.startswith("//"):
            return True, "/" + tail.lstrip("/")
        return False, tail[1:] if tail.startswith("/") else tail
    if tail in (".", "/.") or tail.startswith("/./"):
        return False, tail.lstrip("/")
    if tail.startswith("/"):
        return True, "/" + tail.lstrip("/")
    return False, tail


def borg2_ssh_repository_directory(path: str) -> str:
    """The directory on the host that a Borg 2 ssh:// repository URL names,
    for what reaches the files without Borg (a mount, a copy).

    Borg 2 reads `ssh://host//abs` as absolute and `ssh://host/rel` as
    relative to the login directory of the SSH user, which nothing here
    knows: such a URL names no directory that can be handed on, and taking
    its text for an absolute path would name another one. Raises ValueError
    for it.
    """
    tail = strip_ssh_url_path(path)
    if not path.startswith("ssh://"):
        return tail or "/"
    absolute, directory = _borg2_path(tail, from_url=True)
    if not absolute:
        raise ValueError(
            "this Borg 2 repository is addressed relative to the login "
            "directory of the SSH user (ssh://host/path); its directory on "
            "the host is only known for the absolute form, ssh://host//path"
        )
    return directory


def borg2_ssh_repository_url(
    raw_path: str,
    connection_details: Mapping[str, Any],
    *,
    stored_path: Optional[str] = None,
) -> str:
    """The ssh:// URL of a Borg 2 repository on a connection.

    Borg 2 reads the path after the host as relative to the login directory
    and takes a second slash for an absolute path, where Borg 1 reads it as
    absolute. The same text therefore names two places, and an absolute
    path written the Borg 1 way lands under the login directory.

    `raw_path` is a URL, which keeps the form it came in, or a plain path,
    where a leading slash means absolute. `stored_path` is the URL the
    repository has now: the repository form sends the tail of that URL back
    as the path, so a path equal to it is the stored URL unchanged, not a
    plain path.
    """
    base = (
        f"ssh://{connection_details['username']}@"
        f"{connection_details['host']}:{connection_details['port']}/"
    )
    repo_path = strip_ssh_url_path(raw_path)
    from_url = raw_path.startswith("ssh://") or (
        stored_path is not None
        and stored_path.startswith("ssh://")
        and strip_ssh_url_path(stored_path) == raw_path
    )
    absolute, path = _borg2_path(repo_path, from_url=from_url)
    ssh_path_prefix = connection_details.get("ssh_path_prefix")
    if ssh_path_prefix and absolute:
        # the prefix belongs to paths on the host, not to the login directory
        path = apply_ssh_command_prefix(path, str(ssh_path_prefix))
        absolute, path = _borg2_path(path, from_url=False)
    return base + ("/" + path.lstrip("/") if absolute else path)


_NOT_A_REPOSITORY = "is not a valid repository"


def borg2_unreadable_repository_detail(stderr: Optional[str]) -> Optional[Dict]:
    """The translatable detail for a repository this Borg 2 cannot read, or
    None for any other failure.

    Borg 2 is in beta and its repository format has changed between betas.
    2.0.0b25 cannot tell a repository written by an earlier beta from a
    directory that holds none and answers both with "is not a valid
    repository", so that answer gets a text that names the format change
    first and the wrong path second.
    """
    if _NOT_A_REPOSITORY in (stderr or "").lower():
        return {"key": "backend.errors.repo.borg2RepositoryNotReadable"}
    return None


def normalize_repo_info_encryption(info: Dict) -> Dict:
    """Give repo-info's encryption block a `mode` again, in place.

    Borg 2's repo-info reports ``{"encryption": "aes256-ocb", "id_hash":
    "sha256"}`` where Borg 1 reports ``{"mode": "repokey-aes-ocb"}`` (#9168),
    the same split repo-create makes. Everything downstream — the stored
    repository row, the API response, the info dialog — reads ``mode``, and got
    nothing, so the UI showed "N/A" for a repository that is in fact encrypted.

    The cipher is what `mode` is filled from. The key location is deliberately
    NOT reconstructed: Borg 2 does not report it here, so `repokey-` or
    `keyfile-` would be a guess, and a guess about where the key lives is
    worse than a field that names only what borg actually said. `id_hash` is left in place
    for callers that want it.
    """
    encryption = info.get("encryption")
    if isinstance(encryption, dict) and not encryption.get("mode"):
        cipher = encryption.get("encryption")
        if cipher:
            encryption["mode"] = cipher
    return info


DEFAULT_BORG2_BINARY = "borg2"


def _get_borg2_binary() -> str:
    """Resolve the borg2 binary path from system settings (falls back to 'borg2')."""
    try:
        from app.database.database import SessionLocal
        from app.database.models import SystemSettings

        db = SessionLocal()
        try:
            sys_settings = db.query(SystemSettings).first()
            if sys_settings and sys_settings.borg2_binary_path:
                return sys_settings.borg2_binary_path
        finally:
            db.close()
    except Exception:
        pass
    return DEFAULT_BORG2_BINARY


class Borg2Interface:
    """Interface for interacting with the Borg 2 CLI.

    One global instance is created at module level (`borg2`).
    The binary path is resolved once from system settings at startup.
    """

    _validated = False
    _cached_version: Optional[str] = None
    _cached_system_info: Optional[Dict] = None

    def __init__(self):
        self.borg_cmd = _get_borg2_binary()
        if not Borg2Interface._validated:
            self._validate_installation()
            Borg2Interface._validated = True

    def _validate_installation(self):
        """Validate that the borg2 binary is accessible."""
        try:
            result = subprocess.run(
                [self.borg_cmd, "--version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                logger.info("Borg2 found", version=result.stdout.strip())
            else:
                logger.warning(
                    "Borg2 binary returned non-zero on --version", cmd=self.borg_cmd
                )
        except (FileNotFoundError, OSError):
            logger.warning(
                "Borg2 not available — v2 repositories will not be usable",
                cmd=self.borg_cmd,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Borg2 --version timed out", cmd=self.borg_cmd)

    # ── Internal execution helpers ─────────────────────────────────────────────

    def _base_env(self, extra: Optional[Dict] = None) -> Dict:
        """Build the base environment variables shared by all borg2 commands."""
        env = os.environ.copy()
        env["BORG_LOCK_WAIT"] = "20"
        env["BORG_HOSTNAME_IS_UNIQUE"] = "yes"
        # Borg 2's pack cache — same defaults and override semantics as
        # setup_borg_env (app/utils/borg_env.py), see the comment there.
        env.setdefault("BORG_STORE_CACHE", "1")
        env.setdefault("BORG_PACK_CACHE_SIZE", str(2 * 1024**3))
        env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
        env["BORG_RELOCATED_REPO_ACCESS_IS_OK"] = "yes"
        ssh_opts = [
            *public_key_only_ssh_args(),
            *host_key_ssh_opts(None),
            "-o",
            "LogLevel=ERROR",
        ]
        env["BORG_RSH"] = f"ssh {' '.join(ssh_opts)}"
        env["RCLONE_CONFIG"] = str(Path(settings.rclone_config_root) / "rclone.conf")
        if extra:
            env.update(extra)
        return env

    def _command_env(self, cmd: List[str], extra: Optional[Dict] = None) -> Dict:
        """The environment of one command: the base environment, with the
        port of the command's repository URL in the remote shell (Borg 2 does
        not add it to a remote shell it was given)."""
        return borg2_env_with_repository_port(
            self._base_env(extra), _command_repository(cmd)
        )

    async def _run(
        self,
        cmd: List[str],
        timeout: int = 3600,
        cwd: Optional[str] = None,
        env: Optional[Dict] = None,
        on_process: Optional[Callable[[asyncio.subprocess.Process], None]] = None,
    ) -> Dict:
        """Execute a borg2 command and capture output.

        `on_process` receives the spawned process so a caller that needs to
        cancel the command (the maintenance services) can track and terminate
        it. A terminated process comes back as an ordinary failure with the
        signal's return code.
        """
        refusal = borg2_repository_url_refusal(_command_repository(cmd))
        if refusal:
            logger.error("Refused borg2 command", command=" ".join(cmd))
            return {"return_code": 2, "stdout": "", "stderr": refusal, "success": False}
        logger.info("Executing borg2 command", command=" ".join(cmd), cwd=cwd)
        exec_env = self._command_env(cmd, env)
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=exec_env,
            )
            if on_process is not None:
                on_process(process)
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            result = {
                "return_code": process.returncode,
                "stdout": stdout.decode() if stdout else "",
                "stderr": stderr.decode() if stderr else "",
                "success": process.returncode == 0,
            }
            if result["success"]:
                logger.info("Borg2 command succeeded", command=" ".join(cmd))
            else:
                logger.error(
                    "Borg2 command failed",
                    command=" ".join(cmd),
                    return_code=process.returncode,
                    stderr=result["stderr"],
                )
            return result
        except asyncio.TimeoutError:
            logger.error(
                "Borg2 command timed out", command=" ".join(cmd), timeout=timeout
            )
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": f"Timed out after {timeout}s",
                "success": False,
            }
        except Exception as e:
            logger.error(
                "Borg2 command execution failed", command=" ".join(cmd), error=str(e)
            )
            return {"return_code": -1, "stdout": "", "stderr": str(e), "success": False}

    async def _run_streaming(
        self,
        cmd: List[str],
        max_lines: int = 1_000_000,
        timeout: int = 3600,
        cwd: Optional[str] = None,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Execute a borg2 command with line-by-line streaming (prevents OOM on large outputs)."""
        refusal = borg2_repository_url_refusal(_command_repository(cmd))
        if refusal:
            logger.error("Refused borg2 command", command=" ".join(cmd))
            return {
                "return_code": 2,
                "stdout": "",
                "stderr": refusal,
                "success": False,
                "line_count_exceeded": False,
                "lines_read": 0,
            }
        logger.info(
            "Executing borg2 command (streaming)",
            command=" ".join(cmd),
            max_lines=max_lines,
        )
        exec_env = self._command_env(cmd, env)
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=exec_env,
            )
            stdout_lines = []
            line_count = 0
            line_count_exceeded = False
            start_time = asyncio.get_event_loop().time()

            async for line in process.stdout:
                if asyncio.get_event_loop().time() - start_time > timeout:
                    process.kill()
                    await process.wait()
                    return {
                        "return_code": -1,
                        "stdout": "\n".join(stdout_lines),
                        "stderr": f"Timed out after {timeout}s (read {line_count:,} lines)",
                        "success": False,
                        "line_count_exceeded": False,
                        "lines_read": line_count,
                    }
                line_count += 1
                if line_count > max_lines:
                    line_count_exceeded = True
                    process.kill()
                    await process.wait()
                    break
                stdout_lines.append(line.decode("utf-8", errors="replace").rstrip("\n"))

            stderr_data = await process.stderr.read()
            stderr = (
                stderr_data.decode("utf-8", errors="replace") if stderr_data else ""
            )
            if process.returncode is None:
                await process.wait()

            return {
                "return_code": process.returncode,
                "stdout": "\n".join(stdout_lines),
                "stderr": stderr,
                "success": process.returncode == 0 and not line_count_exceeded,
                "line_count_exceeded": line_count_exceeded,
                "lines_read": line_count,
            }
        except Exception as e:
            logger.error(
                "Borg2 streaming command failed", command=" ".join(cmd), error=str(e)
            )
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False,
                "line_count_exceeded": False,
                "lines_read": 0,
            }

    # ── Repository lifecycle ───────────────────────────────────────────────────

    async def rcreate(
        self,
        repository: str,
        encryption: str = "repokey-aes-ocb",
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
    ) -> Dict:
        """Create (initialise) a new Borg 2 repository.

        Replaces `borg init` — borg2 uses `rcreate` for this.
        """
        refusal = borg2_removed_encryption_refusal(encryption)
        if refusal:
            return refusal
        cmd = [
            self.borg_cmd,
            "-r",
            repository,
            "repo-create",
            *borg2_encryption_flags(encryption),
        ]
        # Repo creation must not touch the shared pack cache: with the cache
        # enabled, Store.create() also creates the cache backend, which rejects
        # an already-populated cache directory — and borg misreports that as
        # "repository already exists".
        env = {"BORG_STORE_CACHE": ""}
        env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase
        return await self._run(cmd, timeout=300, env=env)

    async def rinfo(
        self,
        repository: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        bypass_lock: bool = False,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Get repository-level metadata only (no archive stats).

        Returns encryption, repository ID/location — but no per-archive stats.
        Prefer info_repo() when you need storage statistics.
        Note: borg2 repo-info does not support --bypass-lock.
        """
        cmd = [self.borg_cmd, "-r", repository, "repo-info", "--json"]
        exec_env = env.copy() if env else {}
        exec_env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        # Machine-parsed output: render timestamps in UTC (borg2 timestamps
        # carry an offset either way; pinned for uniformity with borg1).
        exec_env["TZ"] = "UTC"
        return await self._run(cmd, timeout=60, env=exec_env)

    async def info_repo(
        self,
        repository: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        bypass_lock: bool = False,
        timeout: int = 600,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Get info for all archives in a repository (per-archive stats).

        Unlike rinfo (repo-info), this returns an 'archives' array where each entry
        has stats.original_size and stats.nfiles. This is the borg2 equivalent of
        `borg info REPO --json` in borg1.
        """
        cmd = [self.borg_cmd, "-r", repository, "info", "--json"]
        exec_env = env.copy() if env else {}
        exec_env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        # Machine-parsed output: render timestamps in UTC (see rinfo).
        exec_env["TZ"] = "UTC"
        return await self._run(cmd, timeout=timeout, env=exec_env)

    async def rdelete(
        self,
        repository: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
    ) -> Dict:
        """Delete an entire repository.

        Replaces `borg delete REPO` — borg2 uses `rdelete` for repo-level deletion.
        """
        cmd = [self.borg_cmd, "-r", repository, "repo-delete", "--force"]
        # Repo deletion must not touch the shared pack cache: with the cache
        # enabled, Store.destroy() removes the whole cache directory, evicting
        # every other repository's cached packs.
        env = {"BORG_STORE_CACHE": ""}
        env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase
        return await self._run(cmd, timeout=300, env=env)

    # ── Archive listing & info ─────────────────────────────────────────────────

    async def list_archives(
        self,
        repository: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        bypass_lock: bool = False,
        env: Optional[Dict] = None,
    ) -> Dict:
        """List archives in a repository (same CLI as borg1 but different binary).
        Note: borg2 repo-list does not support --bypass-lock.
        """
        cmd = [self.borg_cmd, "-r", repository, "repo-list", "--json"]
        exec_env = env.copy() if env else {}
        exec_env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        # Machine-parsed output: render timestamps in UTC (see rinfo).
        exec_env["TZ"] = "UTC"
        return await self._run(cmd, env=exec_env)

    async def info_archive(
        self,
        repository: str,
        archive: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        bypass_lock: bool = False,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Get information about a specific archive."""
        cmd = [self.borg_cmd, "-r", repository, "info", "--json", archive]
        exec_env = env.copy() if env else {}
        exec_env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        # Machine-parsed output: render timestamps in UTC (see rinfo).
        exec_env["TZ"] = "UTC"
        return await self._run(cmd, env=exec_env)

    async def list_archive_contents(
        self,
        repository: str,
        archive: str,
        path: str = "",
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        max_lines: int = 1_000_000,
        bypass_lock: bool = False,
        browse_depth: Optional[int] = None,
        env: Optional[Dict] = None,
    ) -> Dict:
        """List contents of an archive with streaming to prevent OOM."""
        cmd = [self.borg_cmd, "-r", repository, "list", "--json-lines"]
        if browse_depth is not None:
            cmd.extend(["--depth", str(browse_depth)])
        cmd.append(archive)
        if path:
            cmd.append(path.strip("/"))
        exec_env = env.copy() if env else {}
        exec_env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        # Machine-parsed output: render file mtimes in UTC (see list_archives).
        exec_env["TZ"] = "UTC"
        return await self._run_streaming(cmd, max_lines=max_lines, env=exec_env)

    def diff_archives(
        self,
        repository: str,
        archive_a: str,
        archive_b: str,
        *,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        env: Optional[Dict] = None,
        timeout: int = 3600,
    ) -> "CommandLineStream":
        ensure_borg2_repository_url(repository)
        cmd = [self.borg_cmd, "-r", repository, "diff", "--json-lines"]
        cmd.extend([archive_a, archive_b])
        exec_env = self._command_env(cmd, env)
        exec_env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        # Machine-parsed output: render timestamps in UTC (see list_archives).
        exec_env["TZ"] = "UTC"
        return CommandLineStream(cmd, env=exec_env, timeout=timeout)

    def list_archive_lines(
        self,
        repository: str,
        archive: str,
        *,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        env: Optional[Dict] = None,
        timeout: int = 3600,
    ) -> "CommandLineStream":
        ensure_borg2_repository_url(repository)
        cmd = [self.borg_cmd, "-r", repository, "list", "--json-lines"]
        cmd.append(archive)
        exec_env = self._command_env(cmd, env)
        exec_env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        # Machine-parsed output: render timestamps in UTC (see list_archives).
        exec_env["TZ"] = "UTC"
        return CommandLineStream(cmd, env=exec_env, timeout=timeout)

    # ── Backup operations ──────────────────────────────────────────────────────

    async def create(
        self,
        repository: str,
        source_paths: List[str],
        compression: str = "lz4",
        archive_name: Optional[str] = None,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
    ) -> Dict:
        """Create a new archive (backup)."""
        if not repository:
            return {
                "success": False,
                "error": "Repository is required",
                "stdout": "",
                "stderr": "",
            }
        if not source_paths:
            return {
                "success": False,
                "error": "Source paths are required",
                "stdout": "",
                "stderr": "",
            }

        if not archive_name:
            archive_name = "{hostname}-{now}"
        cmd = [
            self.borg_cmd,
            "-r",
            repository,
            "create",
            "--compression",
            compression,
            "--stats",
            "--json",
            archive_name,
        ]
        cmd.extend(source_paths)
        env = {"BORG_PASSPHRASE": passphrase} if passphrase else {}
        env.update(borg2_remote_path_env(remote_path))
        return await self._run(cmd, timeout=settings.backup_timeout, env=env or None)

    async def extract_archive(
        self,
        repository: str,
        archive: str,
        paths: List[str],
        destination: str,
        dry_run: bool = False,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        bypass_lock: bool = False,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Extract files from an archive."""
        cmd = [self.borg_cmd, "-r", repository, "extract", "--umask", "0022"]
        if dry_run:
            cmd.append("--dry-run")
        cmd.append(archive)
        if paths:
            cmd.extend(paths)
        exec_env = env.copy() if env else {}
        exec_env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run(
            cmd, timeout=settings.backup_timeout, cwd=destination, env=exec_env or None
        )

    def export_archive_tar(
        self,
        repository: str,
        archive: str,
        directory_path: str,
        *,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        env: Optional[Dict] = None,
        timeout: int = 3600,
        strip_components: int = 0,
    ) -> "CommandByteStream":
        """Stream one archived directory as an uncompressed tar to stdout."""
        ensure_borg2_repository_url(repository)
        cmd = [self.borg_cmd, "-r", repository, "export-tar"]
        if strip_components:
            cmd.extend(["--strip-components", str(strip_components)])
        cmd.extend([archive, "-", "--", directory_path.strip("/")])
        exec_env = env.copy() if env else {}
        exec_env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return CommandByteStream(
            cmd, env=self._command_env(cmd, exec_env), timeout=timeout
        )

    async def delete_archive(
        self,
        repository: str,
        archive: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        env: Optional[Dict] = None,
        on_process: Optional[Callable[[asyncio.subprocess.Process], None]] = None,
    ) -> Dict:
        """Delete a single archive.

        Note: in Borg 2, space is NOT freed automatically after delete.
        Call compact() afterwards to reclaim disk space.
        """
        cmd = [self.borg_cmd, "-r", repository, "delete", archive]
        exec_env = env.copy() if env else {}
        exec_env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run(cmd, env=exec_env or None, on_process=on_process)

    async def prune_archives(
        self,
        repository: str,
        keep_hourly: int = 0,
        keep_daily: int = 7,
        keep_weekly: int = 4,
        keep_monthly: int = 6,
        keep_quarterly: int = 0,
        keep_yearly: int = 1,
        dry_run: bool = False,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        keep_within: Optional[str] = None,
    ) -> Dict:
        """Prune old archives.

        Note: in Borg 2, space is NOT freed automatically after prune.
        Call compact() afterwards to reclaim disk space.
        """
        cmd = [self.borg_cmd, "-r", repository, "prune"]
        if keep_hourly > 0:
            cmd.extend(["--keep-hourly", str(keep_hourly)])
        if keep_daily > 0:
            cmd.extend(["--keep-daily", str(keep_daily)])
        if keep_weekly > 0:
            cmd.extend(["--keep-weekly", str(keep_weekly)])
        if keep_monthly > 0:
            cmd.extend(["--keep-monthly", str(keep_monthly)])
        if keep_quarterly > 0:
            cmd.extend(["--keep-3monthly", str(keep_quarterly)])
        if keep_yearly > 0:
            cmd.extend(["--keep-yearly", str(keep_yearly)])
        if keep_within and keep_within.strip():
            # Borg 2 has no --keep-within (nor --keep-last): --keep takes
            # either form, a count or an interval like "1d".
            cmd.extend(["--keep", keep_within.strip()])
        cmd.append("--list")
        if dry_run:
            cmd.append("--dry-run")
        env = {"BORG_PASSPHRASE": passphrase} if passphrase else {}
        env.update(borg2_remote_path_env(remote_path))
        return await self._run(cmd, env=env or None)

    async def compact(
        self,
        repository: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        env: Optional[Dict] = None,
        on_process: Optional[Callable[[asyncio.subprocess.Process], None]] = None,
    ) -> Dict:
        """Compact repository to free space.

        In Borg 2 this step is REQUIRED after delete/prune — space is not freed
        automatically unlike Borg 1. This is by design to allow faster deletes.
        """
        cmd = [self.borg_cmd, "-r", repository, "compact"]
        exec_env = env.copy() if env else {}
        exec_env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run(cmd, env=exec_env or None, on_process=on_process)

    async def check_repository(
        self,
        repository: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Check repository integrity."""
        cmd = [self.borg_cmd, "-r", repository, "check"]
        exec_env = env.copy() if env else {}
        exec_env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run(cmd, env=exec_env or None)

    async def break_lock(
        self,
        repository: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Break a stale lock on a repository."""
        logger.warning("Breaking stale borg2 lock", repository=repository)
        cmd = [self.borg_cmd, "-r", repository, "break-lock"]
        exec_env = env.copy() if env else {}
        exec_env.update(borg2_remote_path_env(remote_path))
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run(cmd, timeout=30, env=exec_env or None)

    # ── Version & system info ──────────────────────────────────────────────────

    def get_version(self) -> str:
        """Return the borg2 version string (synchronous, for startup checks)."""
        try:
            result = subprocess.run(
                [self.borg_cmd, "--version"], capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip() if result.returncode == 0 else "Unknown"
        except Exception as e:
            logger.error("Failed to get borg2 version", error=str(e))
            return "Unknown"

    async def get_system_info(self) -> Dict:
        """Get borg2 system information (cached after first call)."""
        try:
            if Borg2Interface._cached_system_info is not None:
                return Borg2Interface._cached_system_info

            version_result = await self._run([self.borg_cmd, "--version"])
            if not version_result["success"]:
                Borg2Interface._cached_system_info = None  # don't cache failures
                return {
                    "success": False,
                    "error": version_result.get("stderr", "binary not found"),
                }

            version = version_result["stdout"].strip()
            Borg2Interface._cached_system_info = {
                "success": True,
                "borg_version": version,
                "binary": self.borg_cmd,
            }
            logger.info("Cached borg2 system info", version=version)
            return Borg2Interface._cached_system_info
        except Exception as e:
            logger.error("Failed to get borg2 system info", error=str(e))
            return {"success": False, "error": str(e)}


# Global instance — mirrors the `borg` singleton in borg.py
borg2 = Borg2Interface()
