from __future__ import annotations

import shlex
from typing import Any

FULL_CHECK_REQUIRED_FLAGS = ("--verify-data", "--repair", "--archives-only")


class CheckFlagConflictError(ValueError):
    def __init__(self, conflicting_flags: list[str]) -> None:
        self.conflicting_flags = conflicting_flags
        super().__init__(
            "Full-check borg check flags require max_duration to be 0: "
            + ", ".join(conflicting_flags)
        )


def find_full_check_required_flags(extra_flags: str | None) -> list[str]:
    if not extra_flags:
        return []

    try:
        tokens = shlex.split(extra_flags)
    except ValueError:
        return []

    found: list[str] = []
    for token in tokens:
        option = token.split("=", 1)[0]
        if option in FULL_CHECK_REQUIRED_FLAGS and option not in found:
            found.append(option)
    return found


def is_partial_repository_check_duration(max_duration: Any) -> bool:
    if max_duration is None:
        return False
    try:
        return int(max_duration) > 0
    except (TypeError, ValueError):
        return False


def validate_check_flags_for_max_duration(
    extra_flags: str | None, max_duration: Any
) -> None:
    if not is_partial_repository_check_duration(max_duration):
        return

    conflicting_flags = find_full_check_required_flags(extra_flags)
    if conflicting_flags:
        raise CheckFlagConflictError(conflicting_flags)
