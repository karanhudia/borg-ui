"""Validation helpers for SSH connection host and username input."""

from __future__ import annotations

import ipaddress
import re
import unicodedata


SSH_HOST_VALIDATION_MESSAGE = (
    "Enter a bare DNS name or IP address without a scheme, path, user, spaces, "
    "brackets, or port."
)

_DNS_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_FORBIDDEN_HOST_CHARS = frozenset("/\\@[]()<>,\"'`|")

SSH_USERNAME_VALIDATION_MESSAGE = (
    "Enter a username using only letters, digits, dots, underscores, and "
    "hyphens, not starting with a hyphen."
)

# Covers POSIX login names and hosted accounts like Hetzner's u123456-sub1.
# No leading hyphen, so the value can never be read as an ssh option.
_SSH_USERNAME_RE = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._-]{0,63}$")


def normalize_ssh_host(host: str) -> str:
    """Return a trimmed bare DNS name or IP address, or raise ValueError."""
    if not isinstance(host, str):
        raise ValueError(SSH_HOST_VALIDATION_MESSAGE)

    candidate = host.strip()
    if not candidate:
        raise ValueError(SSH_HOST_VALIDATION_MESSAGE)

    if _has_hidden_or_space_character(candidate):
        raise ValueError(SSH_HOST_VALIDATION_MESSAGE)

    if any(char in candidate for char in _FORBIDDEN_HOST_CHARS):
        raise ValueError(SSH_HOST_VALIDATION_MESSAGE)

    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        pass

    if ":" in candidate:
        raise ValueError(SSH_HOST_VALIDATION_MESSAGE)

    if not _is_valid_dns_name(candidate):
        raise ValueError(SSH_HOST_VALIDATION_MESSAGE)

    return candidate


def normalize_ssh_username(username: str) -> str:
    """Return a trimmed SSH login name, or raise ValueError."""
    if not isinstance(username, str):
        raise ValueError(SSH_USERNAME_VALIDATION_MESSAGE)
    candidate = username.strip()
    if not _SSH_USERNAME_RE.fullmatch(candidate):
        raise ValueError(SSH_USERNAME_VALIDATION_MESSAGE)
    return candidate


def ssh_destination(username: str, host: str) -> str:
    """Return ``user@host`` for an ssh, sftp, sshfs or ssh-copy-id argv.

    The last line of defense for rows stored before input validation existed:
    refuses any value OpenSSH could read as an option or that would shift the
    user/host split. Deliberately looser than the input validators so a legacy
    row with an unusual but harmless value keeps working.
    """
    for value in (username, host):
        if (
            not isinstance(value, str)
            or not value
            or value.startswith("-")
            or _has_hidden_or_space_character(value)
        ):
            raise ValueError("Refusing an SSH user or host that could be an option")
    if "@" in host:
        raise ValueError("Refusing an SSH host that contains '@'")
    return f"{username}@{host}"


def _has_hidden_or_space_character(host: str) -> bool:
    for char in host:
        category = unicodedata.category(char)
        if char.isspace() or category.startswith("C"):
            return True
    return False


def _is_valid_dns_name(host: str) -> bool:
    if len(host) > 253:
        return False

    host = host.rstrip(".")
    if not host:
        return False

    labels = host.split(".")
    return all(_DNS_LABEL_RE.fullmatch(label) for label in labels)
