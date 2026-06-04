"""Validation helpers for SSH connection host input."""

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
