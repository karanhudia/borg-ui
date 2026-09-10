"""Compare the agent version an endpoint reports against the version it should
be running.

Three inputs decide the answer, and two are not enough (see the spec at
docs/engineering/specs/2026-09-07-centralized-agent-upgrades.md section 4):

- reported:  what the endpoint last told us it runs
- desired:   what this endpoint is pinned to, or None to track the server
- available: the agent wheel this server image serves

Exact string equality is the source of truth for "current": the question is
whether the endpoint runs the wheel we serve, not whether its version number
sorts high enough. Ordering is used only to separate "behind" from "ahead of
the server", which happens when a server is rolled back. Anything that does not
parse as dotted integers is reported as unknown rather than guessed at.
"""

from __future__ import annotations

from typing import Optional

UP_TO_DATE = "up_to_date"
OUTDATED = "outdated"
AHEAD = "ahead"
PINNED = "pinned"
UNKNOWN = "unknown"

UPGRADE_STATUSES = frozenset({UP_TO_DATE, OUTDATED, AHEAD, PINNED, UNKNOWN})


def parse_agent_version(value: Optional[str]) -> Optional[tuple[int, ...]]:
    """Dotted integer components of ``value``, or None if any component is not a
    plain non-negative integer.

    Deliberately strict: a pre-release such as "0.1.3a1" returns None so the
    caller reports unknown instead of ordering it wrongly. ``str.isdigit`` also
    rejects a leading sign, so "1.-2.3" does not parse.

    The ASCII check is not redundant: ``str.isdigit`` accepts characters such as
    the superscript "\u00b2" that ``int`` then refuses, and the version string
    arrives from an agent heartbeat, so an unparseable one must return None
    rather than raise out of a list request.
    """
    if not value:
        return None
    components: list[int] = []
    for part in value.split("."):
        if not (part.isascii() and part.isdigit()):
            return None
        components.append(int(part))
    return tuple(components)


def _padded(
    left: tuple[int, ...], right: tuple[int, ...]
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    width = max(len(left), len(right))
    return (
        left + (0,) * (width - len(left)),
        right + (0,) * (width - len(right)),
    )


def compute_agent_upgrade_status(
    *,
    reported: Optional[str],
    desired: Optional[str],
    available: Optional[str],
) -> str:
    """One of UPGRADE_STATUSES for a single agent."""
    target = desired or available
    if not reported or not target:
        return UNKNOWN

    if reported == target:
        # Surface the pin so an operator can see why this endpoint will not
        # move when the server does.
        return PINNED if desired else UP_TO_DATE

    reported_parts = parse_agent_version(reported)
    target_parts = parse_agent_version(target)
    if reported_parts is None or target_parts is None:
        return UNKNOWN

    left, right = _padded(reported_parts, target_parts)
    if left > right:
        return AHEAD
    # Equal tuples with different strings (for example "0.1" against "0.1.0")
    # land here: the endpoint is not running the string we serve, so it is
    # treated as behind. Reinstalling it is harmless.
    return OUTDATED


def borg_pin_satisfied(
    *, desired: Optional[str], reported: Optional[list] = None
) -> bool:
    """Whether the Borg major an endpoint is pinned to is one it reports.

    No pin is satisfied by anything: an endpoint that tracks whatever is
    installed has nothing to wait for.

    A pin and no reported binaries is not satisfied. Silence is not success:
    the endpoint has told us nothing to compare, and clearing an upgrade on it
    would report a Borg move that may not have happened. The upgrade timeout
    (spec section 7.1) is what resolves that case, honestly, as failed.

    The reported list arrives from an agent heartbeat, so anything in it may be
    malformed and must not raise: an entry that is not a mapping with a major
    simply does not match.
    """
    if not desired:
        return True
    for entry in reported or []:
        if not isinstance(entry, dict):
            continue
        major = entry.get("major")
        if major is not None and str(major) == str(desired):
            return True
    return False
