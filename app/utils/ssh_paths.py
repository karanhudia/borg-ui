import posixpath
from typing import Optional


def resolve_sshfs_source_path(path: str, default_path: Optional[str] = None) -> str:
    """
    Resolve a source path in the SFTP/SSHFS namespace.

    Relative paths like "." or "./logs" are resolved against the SSH
    connection's default_path. SSH command prefixes are intentionally not
    applied here because SSHFS mounts operate in the browsed SFTP namespace.
    """
    raw_path = (path or "").strip()
    normalized_default_path = (default_path or "/").strip() or "/"
    if not normalized_default_path.startswith("/"):
        normalized_default_path = f"/{normalized_default_path}"

    if not raw_path or raw_path in {".", "./"}:
        resolved_path = normalized_default_path
    elif raw_path.startswith("/"):
        resolved_path = posixpath.normpath(raw_path)
    else:
        resolved_path = posixpath.normpath(
            posixpath.join(normalized_default_path, raw_path)
        )

    if not resolved_path.startswith("/"):
        return f"/{resolved_path}"
    return resolved_path


def apply_ssh_command_prefix(path: str, ssh_path_prefix: Optional[str] = None) -> str:
    """
    Apply an SSH-only command path prefix.

    This is used for shell/Borg SSH commands and must not be used for SFTP or
    SSHFS source-path resolution.
    """
    normalized_path = (path or "").strip() or "/"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    normalized_path = posixpath.normpath(normalized_path)

    normalized_prefix = (ssh_path_prefix or "").strip()
    if not normalized_prefix:
        return normalized_path
    if not normalized_prefix.startswith("/"):
        normalized_prefix = f"/{normalized_prefix}"
    normalized_prefix = posixpath.normpath(normalized_prefix)

    if normalized_path == normalized_prefix or normalized_path.startswith(
        f"{normalized_prefix}/"
    ):
        return normalized_path

    return posixpath.normpath(
        posixpath.join(normalized_prefix, normalized_path.lstrip("/"))
    )
