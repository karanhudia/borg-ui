import re
from typing import Any, Mapping, Optional

from app.utils.ssh_paths import apply_ssh_command_prefix


def strip_ssh_url_path(path: str) -> str:
    if not path.startswith("ssh://"):
        return path

    match = re.match(r"ssh://[^/]+(/.*)", path)
    if match:
        return match.group(1)
    return path.split("/", 3)[-1] if "/" in path else path


def build_ssh_repository_path(
    raw_path: str, connection_details: Mapping[str, Any]
) -> str:
    repo_path = strip_ssh_url_path(raw_path)
    ssh_path_prefix = connection_details.get("ssh_path_prefix")
    if ssh_path_prefix:
        repo_path = apply_ssh_command_prefix(repo_path, str(ssh_path_prefix))

    return (
        f"ssh://{connection_details['username']}@"
        f"{connection_details['host']}:{connection_details['port']}/"
        f"{repo_path.lstrip('/')}"
    )


# Repository URLs only Borg 2 can open.
BORG2_ONLY_URL_PREFIXES = (
    "rest://",
    "sftp://",
    "http://",
    "https://",
    "s3:",
    "b2:",
    "rclone:",
)


def borg1_ssh_address_host(path: Optional[str]) -> Optional[str]:
    """The `[user@]host` of Borg 1's short SSH form `[user@]host:path`, or
    None. Borg 2 has no such form: it reads the text as a local directory."""
    text = (path or "").strip()
    if "://" in text or borg2_only_url_prefix(text):
        return None
    host, separator, _ = text.partition(":")
    if not separator or not host or "/" in host:
        return None
    return host


def borg2_only_url_prefix(path: Optional[str]) -> Optional[str]:
    """The scheme of a repository URL only Borg 2 can open, or None.
    Case-insensitive, and only at the start of the path."""
    lowered = (path or "").strip().lower()
    for prefix in BORG2_ONLY_URL_PREFIXES:
        if lowered.startswith(prefix):
            return prefix
    return None
