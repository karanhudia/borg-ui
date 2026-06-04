from __future__ import annotations

import grp
import os
import pwd
from pathlib import Path

DEFAULT_SERVICE_USER = "borg-ui-agent"
DEFAULT_SERVICE_GROUP = "borg-ui-agent"
DEFAULT_SERVICE_EXECUTABLE = Path("/opt/borg-ui-agent/.venv/bin/borg-ui-agent")
DEFAULT_SERVICE_CONFIG = Path("/etc/borg-ui-agent/config.toml")


class ServiceSetupError(RuntimeError):
    """Raised when the Linux service setup is not ready for systemd."""


def _user_creation_hint(user: str, group: str) -> str:
    if user == group:
        return (
            "sudo useradd --system --user-group --home-dir "
            f"/var/lib/borg-ui-agent --create-home --shell /usr/sbin/nologin {user}"
        )
    return (
        "sudo useradd --system --gid "
        f"{group} --home-dir /var/lib/borg-ui-agent --create-home "
        f"--shell /usr/sbin/nologin {user}"
    )


def validate_service_identity(user: str, group: str) -> None:
    service_user = user.strip()
    service_group = group.strip()
    if not service_user:
        raise ServiceSetupError("Service user must not be empty.")
    if not service_group:
        raise ServiceSetupError("Service group must not be empty.")

    try:
        pwd.getpwnam(service_user)
    except KeyError as exc:
        raise ServiceSetupError(
            f"Service user '{service_user}' does not exist. Create it with: "
            f"{_user_creation_hint(service_user, service_group)}"
        ) from exc

    try:
        grp.getgrnam(service_group)
    except KeyError as exc:
        raise ServiceSetupError(
            f"Service group '{service_group}' does not exist. Create it with: "
            f"sudo groupadd --system {service_group}"
        ) from exc


def validate_service_paths(executable_path: Path, config_path: Path) -> None:
    if not executable_path.exists():
        raise ServiceSetupError(
            f"Agent executable '{executable_path}' does not exist. "
            "Install the agent virtual environment before enabling the service, "
            "then pass the matching path with --exec."
        )
    if not executable_path.is_file():
        raise ServiceSetupError(
            f"Agent executable '{executable_path}' is not a file. "
            "Pass the installed borg-ui-agent executable path with --exec."
        )
    if not os.access(executable_path, os.X_OK):
        raise ServiceSetupError(
            f"Agent executable '{executable_path}' is not executable. "
            "Fix permissions before enabling the service."
        )
    if not config_path.exists():
        raise ServiceSetupError(
            f"Agent config '{config_path}' does not exist. "
            f"Register the agent with --config {config_path} before enabling "
            "the service."
        )
    if not config_path.is_file():
        raise ServiceSetupError(
            f"Agent config '{config_path}' is not a file. "
            "Pass the registered agent config path with --config."
        )


def validate_service_setup(
    *,
    user: str,
    group: str,
    executable_path: Path,
    config_path: Path,
) -> None:
    validate_service_identity(user, group)
    validate_service_paths(executable_path, config_path)
