"""Shared Borg environment helpers for repository and SSH-key backed operations."""

from contextlib import contextmanager
import os
from typing import Iterator, Optional

from app.utils.ssh_utils import resolve_repo_ssh_key_file, resolve_ssh_key_file_by_id


def get_standard_ssh_opts(
    include_key_path: Optional[str] = None,
    *,
    keepalive: bool = False,
) -> list[str]:
    """Return standard SSH options for Borg operations."""
    opts: list[str] = []

    if include_key_path:
        opts.extend(["-i", include_key_path])

    opts.extend(
        [
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "LogLevel=ERROR",
        ]
    )

    if keepalive:
        opts.extend(
            [
                "-o",
                "ServerAliveInterval=15",
                "-o",
                "ServerAliveCountMax=3",
                "-o",
                "TCPKeepAlive=yes",
            ]
        )

    opts.extend(
        [
            "-o",
            "RequestTTY=no",
            "-o",
            "PermitLocalCommand=no",
        ]
    )

    return opts


def setup_borg_env(
    *,
    base_env=None,
    passphrase: Optional[str] = None,
    ssh_opts: Optional[list[str]] = None,
    lock_wait: str = "180",
    show_progress: bool = False,
):
    """Build a Borg execution environment with consistent defaults."""
    env = base_env.copy() if base_env else os.environ.copy()

    if passphrase:
        env["BORG_PASSPHRASE"] = passphrase

    env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
    env["BORG_RELOCATED_REPO_ACCESS_IS_OK"] = "yes"
    env["BORG_LOCK_WAIT"] = lock_wait
    env["BORG_HOSTNAME_IS_UNIQUE"] = "yes"

    if show_progress:
        env["BORG_SHOW_PROGRESS"] = "1"

    if ssh_opts:
        env["BORG_RSH"] = f"ssh {' '.join(ssh_opts)}"

    return env


def cleanup_temp_key_file(temp_key_file: Optional[str]) -> None:
    if temp_key_file and os.path.exists(temp_key_file):
        os.unlink(temp_key_file)


def build_repository_borg_env(
    repository,
    db,
    *,
    keepalive: bool = False,
    show_progress: bool = False,
    lock_wait: str = "180",
    base_env=None,
):
    """Build Borg env for a stored repository and return env + temp key path."""
    temp_key_file = resolve_repo_ssh_key_file(repository, db)
    ssh_opts = get_standard_ssh_opts(include_key_path=temp_key_file, keepalive=keepalive)
    env = setup_borg_env(
        base_env=base_env,
        passphrase=getattr(repository, "passphrase", None),
        ssh_opts=ssh_opts,
        lock_wait=lock_wait,
        show_progress=show_progress,
    )
    return env, temp_key_file


def build_ssh_key_borg_env(
    *,
    path: str,
    passphrase: Optional[str] = None,
    ssh_key_id: Optional[int] = None,
    db=None,
    keepalive: bool = False,
    show_progress: bool = False,
    lock_wait: str = "180",
    base_env=None,
):
    """Build Borg env for an arbitrary Borg path plus optional SSH key ID."""
    temp_key_file = None
    if ssh_key_id and path.startswith("ssh://"):
        temp_key_file = resolve_ssh_key_file_by_id(ssh_key_id, db=db)

    ssh_opts = get_standard_ssh_opts(include_key_path=temp_key_file, keepalive=keepalive)
    env = setup_borg_env(
        base_env=base_env,
        passphrase=passphrase,
        ssh_opts=ssh_opts,
        lock_wait=lock_wait,
        show_progress=show_progress,
    )
    return env, temp_key_file


@contextmanager
def repository_borg_env(
    repository,
    db,
    *,
    keepalive: bool = False,
    show_progress: bool = False,
    lock_wait: str = "180",
    base_env=None,
) -> Iterator[dict]:
    env, temp_key_file = build_repository_borg_env(
        repository,
        db,
        keepalive=keepalive,
        show_progress=show_progress,
        lock_wait=lock_wait,
        base_env=base_env,
    )
    try:
        yield env
    finally:
        cleanup_temp_key_file(temp_key_file)


@contextmanager
def ssh_key_borg_env(
    *,
    path: str,
    passphrase: Optional[str] = None,
    ssh_key_id: Optional[int] = None,
    db=None,
    keepalive: bool = False,
    show_progress: bool = False,
    lock_wait: str = "180",
    base_env=None,
) -> Iterator[dict]:
    env, temp_key_file = build_ssh_key_borg_env(
        path=path,
        passphrase=passphrase,
        ssh_key_id=ssh_key_id,
        db=db,
        keepalive=keepalive,
        show_progress=show_progress,
        lock_wait=lock_wait,
        base_env=base_env,
    )
    try:
        yield env
    finally:
        cleanup_temp_key_file(temp_key_file)
