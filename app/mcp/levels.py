"""MCP access levels (spec 2026-11-14-mcp-server, 5.2)."""

from __future__ import annotations

from enum import IntEnum


class Level(IntEnum):
    READ = 0
    OPERATE = 1
    MANAGE = 2
    FULL = 3

    @classmethod
    def parse(cls, value: str) -> "Level":
        try:
            return cls[value.upper()]
        except (KeyError, AttributeError):
            raise ValueError(f"Unknown access level: {value!r}") from None

    @property
    def label(self) -> str:
        return self.name.lower()


LEVEL_NAMES = tuple(level.label for level in Level)


def effective_level(connection_level: str, cap: str) -> Level:
    """The lower of what the connection was given and what the admin allows."""
    return min(Level.parse(connection_level), Level.parse(cap))
