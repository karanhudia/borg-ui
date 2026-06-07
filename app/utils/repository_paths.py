import re
from typing import Any, Mapping

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
