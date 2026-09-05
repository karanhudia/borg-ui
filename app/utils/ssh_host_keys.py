"""Host-key pinning for SSH connections (trust on first use).

Every SSH invocation used to pass ``StrictHostKeyChecking=no`` together with
``UserKnownHostsFile=/dev/null``, which means the remote host was never
authenticated: anything that could answer on the address was trusted, on every
connection, forever. This module replaces that bypass for every invocation that
is bound to a stored :class:`~app.database.models.SSHConnection`.

The model is OpenSSH's own: the first time we talk to a host we record its
public key, and from then on the key must match or the connection fails. The
recorded key lives on the connection row (``known_host_key``), so it survives
container restarts and is visible in the UI.

Two ways a key gets pinned:

* **Explicitly**, from the UI: the user is shown the fingerprint and confirms
  it before it is stored. That is the path every newly created connection
  takes, and it is the moment the verification is actually worth something.
* **Silently**, on first use of a connection that predates this feature. Those
  connections were already being used with no verification at all, so pinning
  whatever answers now is strictly better than the status quo, and it avoids
  breaking every existing install on upgrade. See the design spec.

Once a key is pinned, a change is never absorbed silently in either case: the
connection fails and the user has to re-verify.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import structlog

from app.config import settings

logger = structlog.get_logger()

# Key types we ask for, best first. Restricting the scan keeps the stored value
# small and avoids pinning a type OpenSSH would not have negotiated anyway.
SCAN_KEY_TYPES = "ed25519,rsa,ecdsa"

SCAN_TIMEOUT_SECONDS = 10

# How long to leave a connection unscanned after its host key could not be read.
SCAN_RETRY_COOLDOWN_SECONDS = 60

HOST_KEY_STATUS_TRUSTED = "trusted"
HOST_KEY_STATUS_UNKNOWN = "unknown"
HOST_KEY_STATUS_CHANGED = "changed"
HOST_KEY_STATUS_UNREACHABLE = "unreachable"


class HostKeyScanError(Exception):
    """Raised when the remote host's key could not be read."""


def known_hosts_dir() -> Path:
    """Directory holding the per-connection known_hosts files."""
    return Path(settings.ssh_home_dir or settings.ssh_keys_dir) / "known_hosts.d"


def known_hosts_path(connection) -> Path:
    """Path of the known_hosts file materialised for one connection.

    A connection that has not been saved yet has no id, so it is addressed by
    the host and port it points at instead. Both are stable for the lifetime of
    such an object, and a saved row always wins on id.
    """
    connection_id = getattr(connection, "id", None)
    if connection_id is not None:
        return known_hosts_dir() / f"connection_{connection_id}"

    host = getattr(connection, "host", "") or ""
    port = getattr(connection, "port", 22) or 22
    digest = hashlib.sha256(f"{host}:{port}".encode()).hexdigest()[:16]
    return known_hosts_dir() / f"host_{digest}"


def scan_host_key(host: str, port: int = 22) -> str:
    """Return the known_hosts lines ``ssh-keyscan`` reports for a host.

    Raises HostKeyScanError when the host cannot be reached or offers no key.
    """
    if not host:
        raise HostKeyScanError("No host to scan")

    try:
        result = subprocess.run(
            [
                "ssh-keyscan",
                "-T",
                str(SCAN_TIMEOUT_SECONDS),
                "-t",
                SCAN_KEY_TYPES,
                "-p",
                str(port or 22),
                host,
            ],
            capture_output=True,
            text=True,
            timeout=SCAN_TIMEOUT_SECONDS + 5,
        )
    except FileNotFoundError as exc:
        raise HostKeyScanError("ssh-keyscan is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise HostKeyScanError(f"Timed out reading the host key of {host}") from exc

    lines = [
        line.strip()
        for line in (result.stdout or "").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not lines:
        detail = (result.stderr or "").strip().splitlines()
        raise HostKeyScanError(
            detail[-1] if detail else f"No host key returned by {host}"
        )

    return "\n".join(lines)


async def scan_host_key_async(host: str, port: int = 22) -> str:
    """Async wrapper around :func:`scan_host_key`, for use in request handlers."""
    return await asyncio.to_thread(scan_host_key, host, port)


def key_fingerprint(host_key: Optional[str]) -> Optional[str]:
    """Return the ``SHA256:`` fingerprint of the first key in a known_hosts blob.

    Computed here rather than shelled out to ``ssh-keygen``: the connection
    list renders one of these per row. The format matches what OpenSSH prints,
    so a user can compare it against ``ssh-keygen -lf`` on the host itself.
    ``ssh-keyscan`` lists key types in SCAN_KEY_TYPES order, so the first line
    is the strongest key the host offered.
    """
    if not host_key or not host_key.strip():
        return None

    for line in host_key.splitlines():
        fields = line.strip().split()
        if len(fields) < 3:
            continue
        try:
            blob = base64.b64decode(fields[2], validate=True)
        except (ValueError, binascii.Error):
            continue
        digest = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
        return f"SHA256:{digest}"

    return None


def host_keys_match(stored: Optional[str], observed: Optional[str]) -> bool:
    """Whether an observed scan still contains the key we pinned.

    A host can legitimately gain a key type between scans, so a match means
    "every key we pinned is still offered", not "the scans are identical".
    """
    if not stored or not observed:
        return False

    observed_lines = {line.strip() for line in observed.splitlines() if line.strip()}
    stored_lines = [line.strip() for line in stored.splitlines() if line.strip()]
    if not stored_lines:
        return False

    return all(line in observed_lines for line in stored_lines)


def pinned_host_key(connection) -> Optional[str]:
    """The key a connection has pinned, or None when it has none.

    Anything that is not a non-empty string counts as unpinned, so a partially
    built or mocked connection object cannot smuggle a non-key into the
    known_hosts file.
    """
    host_key = getattr(connection, "known_host_key", None)
    if not isinstance(host_key, str) or not host_key.strip():
        return None
    return host_key


def trusts_on_first_use(connection) -> bool:
    """Whether this connection may pin whatever key answers, without asking.

    True only for connections that existed before host-key verification did.
    Those were already running with no verification at all, so recording the
    current key is strictly better than the status quo and does not break an
    install on upgrade. A connection created since gets the confirm dialog
    instead, which is the moment verification is actually worth something.
    """
    return getattr(connection, "host_key_trust_on_first_use", False) is True


def write_known_hosts_file(connection) -> Optional[str]:
    """Materialise a connection's pinned key as a known_hosts file.

    Returns the file path, or None when nothing is pinned yet.
    """
    host_key = pinned_host_key(connection)
    if not host_key:
        return None

    directory = known_hosts_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = known_hosts_path(connection)
        # Write via a temporary file in the same directory so a concurrent
        # command never reads a half-written known_hosts file.
        fd, temp_path = tempfile.mkstemp(dir=str(directory), prefix=".known_hosts.")
        with os.fdopen(fd, "w") as handle:
            handle.write(host_key.rstrip("\n") + "\n")
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
        return str(path)
    except OSError as exc:
        logger.warning(
            "Could not write the known_hosts file for an SSH connection",
            connection_id=getattr(connection, "id", None),
            error=str(exc),
        )
        return None


def forget_known_hosts_file(connection) -> None:
    """Remove a connection's materialised known_hosts file, if any."""
    try:
        known_hosts_path(connection).unlink(missing_ok=True)
    except OSError:  # pragma: no cover - best effort cleanup
        pass


def _session_for(connection, db):
    """The session that owns a connection row, when the caller passed none."""
    if db is not None:
        return db
    try:
        from sqlalchemy.orm import object_session

        return object_session(connection)
    except Exception:  # pragma: no cover - detached or non-ORM object
        return None


def pin_host_key(connection, db, host_key: str) -> None:
    """Store a host key on a connection and materialise its known_hosts file.

    Raises whatever the commit raised if the key could not be persisted: a
    caller that told the user their host is now verified must not say so when
    the row still has no key.
    """
    connection.known_host_key = host_key.strip()
    session = _session_for(connection, db)
    if session is not None:
        try:
            session.commit()
        except Exception as exc:
            logger.warning(
                "Could not persist a pinned host key",
                connection_id=getattr(connection, "id", None),
                error=str(exc),
            )
            session.rollback()
            raise
    write_known_hosts_file(connection)


_FAILED_SCANS: dict[object, float] = {}


def _scan_recently_failed(connection) -> bool:
    """Whether this connection's key was scanned, and failed, a moment ago.

    A scan against an unreachable host costs the full ssh-keyscan timeout. That
    is fine once, but an unpinned connection is retried on every SSH invocation,
    and a backup plan makes many. The cooldown keeps a host that is simply down
    from adding that timeout to every command.
    """
    key = getattr(connection, "id", None) or id(connection)
    failed_at = _FAILED_SCANS.get(key)
    if failed_at is None:
        return False
    if time.monotonic() - failed_at < SCAN_RETRY_COOLDOWN_SECONDS:
        return True
    _FAILED_SCANS.pop(key, None)
    return False


def _auto_pin(connection, db) -> bool:
    """Silently pin the key of a connection that has never had one.

    Returns True when a key was pinned. Only for connections created before
    host-key verification existed: they were used with no verification at all,
    so recording the current key can only improve on that.
    """
    if _scan_recently_failed(connection):
        return False

    host = getattr(connection, "host", None)
    try:
        host_key = scan_host_key(host, getattr(connection, "port", 22) or 22)
    except HostKeyScanError as exc:
        logger.warning(
            "Could not pin the host key of an SSH connection",
            connection_id=getattr(connection, "id", None),
            host=host,
            error=str(exc),
        )
        _FAILED_SCANS[getattr(connection, "id", None) or id(connection)] = (
            time.monotonic()
        )
        return False

    _FAILED_SCANS.pop(getattr(connection, "id", None) or id(connection), None)
    try:
        pin_host_key(connection, db, host_key)
    except Exception as exc:  # a failed pin must not fail the SSH command
        logger.warning(
            "Could not store the host key pinned on first use",
            connection_id=getattr(connection, "id", None),
            host=host,
            error=str(exc),
        )
        return False
    logger.info(
        "Pinned the host key of an existing SSH connection on first use",
        connection_id=getattr(connection, "id", None),
        host=host,
        fingerprint=key_fingerprint(host_key),
    )
    return True


def host_key_ssh_opts(connection, db=None) -> list[str]:
    """Return the OpenSSH options that verify one connection's host key.

    Pins the key first when the connection has none. Falls back to
    ``accept-new`` only when the host key cannot be read at all, which is still
    stricter than the ``StrictHostKeyChecking=no`` this replaced: a key change
    on a host we have already talked to is refused either way.
    """
    if connection is None:
        return [
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={_shared_known_hosts_path()}",
        ]

    if not pinned_host_key(connection) and trusts_on_first_use(connection):
        _auto_pin(connection, db)

    if pinned_host_key(connection):
        # A pinned connection always verifies strictly. If the file could not
        # be written, OpenSSH finds no key for the host and refuses to connect,
        # which is the right way to fail: never downgrade a connection the user
        # has verified because of a full or read-only disk.
        path = write_known_hosts_file(connection) or str(known_hosts_path(connection))
        return [
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={path}",
        ]

    # Nothing pinned: either a connection awaiting the user's confirmation, or
    # one whose host could not be scanned. Let OpenSSH record the key it sees
    # in the per-connection file so a later change is still refused, rather
    # than reverting to trusting anything.
    directory = known_hosts_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        return [
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={_shared_known_hosts_path()}",
        ]
    return [
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"UserKnownHostsFile={known_hosts_path(connection)}",
    ]


def host_key_ssh_opts_for_host(
    host: str, port: int = 22, username: Optional[str] = None
) -> list[str]:
    """Verify a bare host/port against the pinned key of its stored connection.

    For the helpers that are handed connection details as loose strings rather
    than a row. An endpoint that matches no single stored connection, or one
    that matches several, records the key on first use instead: there is no
    single pin to enforce, and refusing outright would break paths that run
    before a connection exists at all, such as key deployment.
    """
    if not host:
        return host_key_ssh_opts(None)

    from app.database.database import SessionLocal
    from app.database.models import SSHConnection

    session = SessionLocal()
    try:
        query = session.query(SSHConnection).filter(
            SSHConnection.host == host, SSHConnection.port == (port or 22)
        )
        if username:
            query = query.filter(SSHConnection.username == username)
        matches = query.all()
        connection = matches[0] if len(matches) == 1 else None
        return host_key_ssh_opts(connection, session)
    except Exception as exc:  # pragma: no cover - a lookup failure is not fatal
        logger.warning(
            "Could not resolve the SSH connection for a host",
            host=host,
            error=str(exc),
        )
        return host_key_ssh_opts(None)
    finally:
        session.close()


def host_key_ssh_opts_for_path(path: str) -> list[str]:
    """Verify a bare ``ssh://`` URL against the pinned key of its connection.

    For the few helpers that are handed a URL rather than a connection row.
    Falls back to recording the key on first use when the URL matches no stored
    connection, which is still stricter than trusting whatever answers.
    """
    if not path or not path.startswith("ssh://"):
        return host_key_ssh_opts(None)

    from app.database.database import SessionLocal
    from app.utils.ssh_utils import find_ssh_connection_for_path

    session = SessionLocal()
    try:
        return host_key_ssh_opts(find_ssh_connection_for_path(path, session), session)
    except Exception as exc:  # pragma: no cover - a lookup failure is not fatal
        logger.warning(
            "Could not resolve the SSH connection for a path",
            path=path,
            error=str(exc),
        )
        return host_key_ssh_opts(None)
    finally:
        session.close()


def _shared_known_hosts_path() -> Path:
    """Fallback known_hosts file for invocations with no connection row.

    Creates the directory as a side effect: OpenSSH will not record a key in a
    file whose directory does not exist, and an invocation with no connection
    row has nothing else to verify against.
    """
    directory = known_hosts_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover - unwritable data dir
        logger.warning("Could not create the known_hosts directory", error=str(exc))
    return directory / "shared"


def host_key_verification_failed(output: Optional[str]) -> bool:
    """Whether SSH output shows the pinned key no longer matches."""
    if not output:
        return False
    lowered = output.lower()
    return (
        "host key verification failed" in lowered
        or "remote host identification has changed" in lowered
    )


def describe_host_key_status(connection, observed: Optional[str]) -> str:
    """Classify a fresh scan against what the connection has pinned."""
    stored = pinned_host_key(connection)
    if not observed:
        return HOST_KEY_STATUS_UNREACHABLE
    if not stored:
        return HOST_KEY_STATUS_UNKNOWN
    if host_keys_match(stored, observed):
        return HOST_KEY_STATUS_TRUSTED
    return HOST_KEY_STATUS_CHANGED


def ssh_keyscan_available() -> bool:
    """Whether ``ssh-keyscan`` exists in this image."""
    return shutil.which("ssh-keyscan") is not None
