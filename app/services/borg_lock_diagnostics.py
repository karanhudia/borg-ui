"""Bounded, read-only context for server-side Borg cache lock contention.

Owner entries identify what Borg recorded, not whether that owner is alive.
Never inspect a repository/remote path or break a lock from these diagnostics.
"""

import os
import re
import socket
from itertools import islice
from pathlib import Path

from app.core.borg import BorgInterface
from app.utils.redaction import redact_secrets

_LOCK_PATH = re.compile(
    r"Failed to (?:create/)?acquire the lock (.+?)(?: \(timeout\)\.?$|\.$)",
    re.MULTILINE,
)


def _bounded(value: str, limit: int = 160) -> str:
    return redact_secrets(value)[:limit]


def cache_lock_diagnostics(message: str, env: dict) -> dict:
    """List up to five owner names only for a local cache's exclusive lock.

    The configured cache root may itself be a volume/symlink, but repository
    or lock symlinks beneath it must not redirect inspection elsewhere.
    Files inside the lock directory are never opened, changed, or removed.
    """
    context = {
        "current_hostname": _bounded(socket.gethostname()),
        "borg_host_id": _bounded(
            env.get("BORG_HOST_ID")
            or os.environ.get("BORG_HOST_ID")
            or "not configured"
        ),
        "owner_liveness": "unknown",
        "cache_lock_status": "not_inspected",
        "owners": [],
    }
    match = _LOCK_PATH.search(message)
    if not match:
        return context
    context["lock_path"] = _bounded(match[1], 320)
    try:
        path = Path(match[1])
        root = Path(BorgInterface._get_borg_cache_root(env)).resolve()
        # Only Borg's per-repository cache layout, not an arbitrary path
        # printed by a remote Borg process or an error containing '..'.
        if not path.is_absolute() or path.name != "lock.exclusive":
            return context
        if not re.fullmatch(r"[0-9a-f]{64}", path.parent.name):
            return context
        if path.parent.is_symlink() or path.is_symlink():
            return context
        if path.parent.parent.resolve() != root:
            return context
        with os.scandir(path) as entries:
            names = [entry.name for entry in islice(entries, 6)]
        context["owners"] = [_bounded(name) for name in names[:5]]
        context["owners_truncated"] = len(names) > 5
        context["cache_lock_status"] = "present"
    except (OSError, RuntimeError, ValueError) as exc:
        context["cache_lock_status"] = type(exc).__name__
    return context
