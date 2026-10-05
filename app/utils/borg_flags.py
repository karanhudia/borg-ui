"""Allowlist for user supplied borg flags.

Repository and backup plan ``custom_flags`` and ``check_extra_flags`` are free
text that end up in a borg argv (or, for remote-direct backups, in a shell
command on the source host). Only options that cannot run commands, change
the repository or read arbitrary files are accepted. Keep this module in sync
with ``agent/borg_ui_agent/borg_flags.py``; a unit test compares them.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence

from pydantic import field_validator, model_validator

# Option name -> True when it takes a value. Borg 1 and Borg 2 spellings;
# BORG_MAJOR_ONLY_FLAGS names the ones only one major accepts.
_COMMON_FLAGS: dict[str, bool] = {
    "--progress": False,
    "-p": False,
    "--verbose": False,
    "-v": False,
    "--info": False,
    "--debug": False,
    "--log-json": False,
    "--show-rc": False,
    "--lock-wait": True,
}

ALLOWED_BORG_FLAGS: dict[str, dict[str, bool]] = {
    "create": {
        **_COMMON_FLAGS,
        "--stats": False,
        "-s": False,
        "--list": False,
        "--filter": True,
        "--one-file-system": False,
        "-x": False,
        "--numeric-ids": False,
        "--numeric-owner": False,
        "--atime": False,
        "--noatime": False,
        "--noctime": False,
        "--nobirthtime": False,
        "--noflags": False,
        "--nobsdflags": False,
        "--noacls": False,
        "--noxattrs": False,
        "--sparse": False,
        "--read-special": False,
        "--exclude-caches": False,
        "--exclude-nodump": False,
        "--exclude-if-present": True,
        "--keep-exclude-tags": False,
        "--exclude": True,
        "-e": True,
        "--pattern": True,
        "--files-cache": True,
        "--files-changed": True,
        "--checkpoint-interval": True,
        "--chunker-params": True,
        "--comment": True,
        "--compression": True,
        "--upload-ratelimit": True,
        "--upload-buffer": True,
        "--timestamp": True,
        "--dry-run": False,
        "-n": False,
    },
    "check": {
        **_COMMON_FLAGS,
        "--repository-only": False,
        "--archives-only": False,
        "--verify-data": False,
        "--repair": False,
        "--save-space": False,
        "--find-lost-archives": False,
        "--max-duration": True,
        "--first": True,
        "--last": True,
        "--oldest": True,
        "--newest": True,
        "--older": True,
        "--newer": True,
        "--sort-by": True,
        "--prefix": True,
        "--glob-archives": True,
        "--match-archives": True,
        "-a": True,
    },
}


# Options of ALLOWED_BORG_FLAGS that only one Borg major accepts; the other
# fails at argument parsing ("unrecognized arguments", exit 2). Measured on
# Borg 1.4.5 and 2.0.0b25. Borg 2.0.0b22 removed --upload-ratelimit and
# --upload-buffer with the Borg 1 remote protocol they throttled.
BORG_MAJOR_ONLY_FLAGS: dict[str, dict[int, frozenset[str]]] = {
    "create": {
        1: frozenset(
            {
                "--numeric-owner",
                "--noatime",
                "--nobsdflags",
                "--exclude-nodump",
                "--checkpoint-interval",
                "--upload-ratelimit",
                "--upload-buffer",
            }
        ),
        2: frozenset(),
    },
    "check": {
        1: frozenset({"--save-space", "--prefix", "--glob-archives"}),
        2: frozenset(
            {
                "--find-lost-archives",
                "--match-archives",
                "--oldest",
                "--newest",
                "--older",
                "--newer",
            }
        ),
    },
}


def _has_control_chars(token: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in token)


def _expand_short_flags(token: str, allowed: dict[str, bool]) -> list[str]:
    """Split ``-xs`` into ``-x -s`` when every letter is an allowed boolean."""
    if not token.startswith("-") or token.startswith("--") or len(token) <= 2:
        return [token]
    flags = [f"-{letter}" for letter in token[1:]]
    if all(allowed.get(flag) is False for flag in flags):
        return flags
    return [token]


def parse_borg_flags(
    value: str | Sequence[str] | None,
    command: str,
    borg_version: int | None = None,
) -> list[str]:
    """Split and validate user supplied flags for ``borg <command>``.

    Accepts the stored text (or an already split list) and returns argv
    tokens. Value options come back as ``--name=value`` (short ones as two
    tokens), so a value can never be read as a separate option or path.
    Raises ValueError for anything not on the allowlist, and with
    ``borg_version`` for an option that Borg major does not have.
    """
    allowed = ALLOWED_BORG_FLAGS.get(command)
    if allowed is None:
        raise ValueError(f"Unsupported borg command for custom flags: {command}")
    other_only: frozenset[str] = frozenset()
    if borg_version is not None:
        other_only = BORG_MAJOR_ONLY_FLAGS[command][1 if borg_version == 2 else 2]
    if value is None:
        return []
    if isinstance(value, str):
        try:
            tokens = shlex.split(value)
        except ValueError as exc:
            raise ValueError(f"Invalid borg {command} flags: {exc}") from exc
    else:
        tokens = list(value)
    tokens = [
        flag
        for token in tokens
        for flag in (
            _expand_short_flags(token, allowed) if isinstance(token, str) else [token]
        )
    ]

    result: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not isinstance(token, str) or _has_control_chars(token):
            raise ValueError(f"Invalid borg {command} flag: {token!r}")
        if not token.startswith("-"):
            raise ValueError(
                f"Positional arguments are not allowed in borg {command} flags: "
                f"{token!r}"
            )
        name, sep, flag_value = token.partition("=")
        if name not in allowed:
            raise ValueError(f"Borg {command} flag is not allowed: {name}")
        if name in other_only:
            raise ValueError(
                f"Borg {borg_version} {command} has no option {name}; "
                f"it is a Borg {1 if borg_version == 2 else 2} option"
            )
        takes_value = allowed[name]
        if not takes_value:
            if sep:
                raise ValueError(f"Borg {command} flag {name} does not take a value")
            result.append(name)
            continue
        if not sep:
            if index >= len(tokens) or tokens[index].startswith("-"):
                raise ValueError(f"Borg {command} flag {name} requires a value")
            flag_value = tokens[index]
            index += 1
            if _has_control_chars(flag_value):
                raise ValueError(f"Invalid value for borg {command} flag {name}")
        if not flag_value:
            raise ValueError(f"Borg {command} flag {name} requires a value")
        if not name.startswith("--") and flag_value.startswith("-"):
            raise ValueError(f"Invalid value for borg {command} flag {name}")
        if name.startswith("--"):
            result.append(f"{name}={flag_value}")
        else:
            result.extend([name, flag_value])
    return result


def borg_flags_validator(field: str, command: str, borg_version: int | None = None):
    """Pydantic field validator that rejects what parse_borg_flags rejects."""

    def _validate(cls, value):
        parse_borg_flags(value, command, borg_version)
        return value

    return field_validator(field)(_validate)


def borg_flags_major_validator(field: str, command: str, major=None):
    """Pydantic model validator that checks ``field`` against the Borg major
    the request runs on: ``major(model)`` when given, else the model's own
    ``borg_version`` field (1 when unset)."""

    def _validate(self):
        borg_version = (
            major(self) if major else (getattr(self, "borg_version", None) or 1)
        )
        parse_borg_flags(getattr(self, field), command, borg_version)
        return self

    return model_validator(mode="after")(_validate)
