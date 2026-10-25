"""Confinement of server-local paths to the configured host mount points.

Every check resolves symlinks and ``..`` with ``os.path.realpath`` first, so a
link inside a mount that points elsewhere is judged by where it lands.
"""

import os
from typing import Iterable, List, Optional, Set

from app.config import settings

# Never a restore target, even when a mount point covers them.
_APP_DIR = "/app"


def _is_within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def local_mount_roots() -> List[str]:
    return [os.path.realpath(mp) for mp in settings.get_local_mount_points()]


def is_within_local_mount(path: str) -> bool:
    resolved = os.path.realpath(path)
    return any(_is_within(resolved, root) for root in local_mount_roots())


def mount_entries_below(path: str) -> Set[str]:
    """Names of the children of ``path`` that lead down to a mount point.

    Lets a browser start at ``/`` and walk to ``/local`` without seeing the
    rest of the container's filesystem.
    """
    resolved = os.path.realpath(path)
    entries = set()
    for root in local_mount_roots():
        if root != resolved and _is_within(root, resolved):
            relative = root[len(resolved) :].lstrip("/")
            entries.add(relative.split("/", 1)[0])
    return entries


def _restore_targets(
    destination: str, paths: Optional[Iterable[str]], restore_layout: str
) -> List[str]:
    # preserve_path recreates each archive path under the destination, so a
    # restore to "/" (original location) lands on the paths themselves.
    # contents_only strips them, so everything lands under the destination.
    paths = [p for p in (paths or []) if p]
    if restore_layout == "preserve_path" and paths:
        return [os.path.join(destination, p.lstrip("/")) for p in paths]
    return [destination]


def is_restore_destination_allowed(
    destination: str,
    paths: Optional[Iterable[str]] = None,
    restore_layout: str = "preserve_path",
    confine_to_mounts: bool = True,
) -> bool:
    """True when a server-local restore never writes into the application or
    its data directory and, when ``confine_to_mounts``, only inside a mount
    point."""
    if not destination:
        return False
    reserved = [os.path.realpath(_APP_DIR), os.path.realpath(settings.data_dir)]
    for target in _restore_targets(destination, paths, restore_layout):
        resolved = os.path.realpath(target)
        if confine_to_mounts and not is_within_local_mount(resolved):
            return False
        # Reject a target inside a reserved directory, and one that contains
        # it (restoring a whole tree over "/" would reach it too).
        if any(_is_within(resolved, r) or _is_within(r, resolved) for r in reserved):
            return False
    return True


def is_operator_metadata_path_allowed(path: str) -> bool:
    """True when a non-admin may set ``path`` as a backup location's dump,
    export or snapshot staging directory: absolute, without a ".." segment, and
    neither inside nor containing the application or its data directory. The
    app writes and, through the discovery scripts, deletes these directories,
    so a reserved-directory target is refused; the mount points do not confine
    them (the defaults live under /var/tmp/borg-ui)."""
    if not path or not os.path.isabs(path) or ".." in path.split("/"):
        return False
    try:
        resolved = os.path.realpath(path)
    except ValueError:  # an embedded NUL byte
        return False
    reserved = [os.path.realpath(_APP_DIR), os.path.realpath(settings.data_dir)]
    return not any(_is_within(resolved, r) or _is_within(r, resolved) for r in reserved)


def is_operator_source_allowed(path: str) -> bool:
    """True when a non-admin may add ``path`` as a server-local backup source:
    absolute and without a ".." segment, inside a mount point, and neither
    inside nor containing the application or its data directory (a backup of
    "/" would read them too). Borg drops ".." before the path is resolved, so a
    ".." behind a symlink would name another directory than the one checked
    here; a relative path depends on the directory Borg runs in."""
    if not path or not os.path.isabs(path) or ".." in path.split("/"):
        return False
    try:
        resolved = os.path.realpath(path)
    except ValueError:  # an embedded NUL byte
        return False
    if not is_within_local_mount(resolved):
        return False
    reserved = [os.path.realpath(_APP_DIR), os.path.realpath(settings.data_dir)]
    return not any(_is_within(resolved, r) or _is_within(r, resolved) for r in reserved)
