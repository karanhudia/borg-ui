"""The one place the server reads a repository's Borg major (#1315).

Anything but 1 or 2 is refused, so no caller can take an unknown major for
Borg 1. Kept free of app imports so any module can use it without an import
cycle.
"""

from typing import Any


def borg_major(obj: Any) -> int:
    """The Borg major of a repository row or request model, 1 when unset."""
    value = getattr(obj, "borg_version", None)
    if value is None:
        return 1
    try:
        major = int(value)
    except (TypeError, ValueError):
        major = None
    # int() would also take 2.5 for 2 and True for 1
    if major not in (1, 2) or str(value).strip() != str(major):
        raise ValueError(f"Unsupported Borg major: {value!r}")
    return major


def is_borg2(obj: Any) -> bool:
    return borg_major(obj) == 2
