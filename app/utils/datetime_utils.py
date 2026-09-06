"""
Datetime utilities for consistent timezone handling across the application.

All datetimes in the database are stored as UTC (naive format due to SQLite limitations).
This module provides utilities to ensure consistent serialization to frontend.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    """Naive-UTC now - the canonical form for database writes.

    Datetime columns store naive UTC. A naive-UTC value round-trips
    identically on SQLite and PostgreSQL and never depends on the session
    timezone; an aware value written to `timestamp without time zone` is
    converted through the session zone first (safe only because the engine
    pins it to UTC). New "now" writes should use this helper.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_borg_archive_time(
    value: Any, *, timezone_name: Optional[str] = None
) -> Optional[datetime]:
    """Parse a Borg archive timestamp into a naive UTC database value.

    Borg stores archive timestamps as absolute values and renders them, with
    no UTC offset, in the local zone of the process that produced the listing
    - historical archives included. ``timezone_name`` names that process's
    IANA zone (the zone an agent reported, or "UTC" for a listing forced to
    TZ=UTC); without one, naive values are interpreted in this server's local
    zone. Using the zone (not a fixed offset) keeps archives created on
    either side of a DST switch correct. Numeric values are Unix epochs and
    carry no ambiguity.
    """
    if value is None:
        return None

    # bool is an int subclass; True would otherwise parse as epoch 1.
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            # Out-of-range epochs (junk input) must not escape into the
            # transport handlers; absence is handled by every caller.
            return None

    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return None

    try:
        dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None

    if dt.tzinfo is None:
        zone = None
        if timezone_name:
            try:
                zone = ZoneInfo(timezone_name)
            except Exception:
                zone = None
        if zone is not None:
            # fold=0 pins wall times repeated by a DST fall-back to their
            # EARLIER instant. Borg gives no disambiguator, so any choice is
            # off by at most the DST shift for that one hour a year - the
            # earlier reading only ever understates recency, which is the
            # safe direction for last_backup and stale monitoring. Excluding
            # ambiguous values instead could fall back to an arbitrarily
            # older archive.
            dt = dt.replace(tzinfo=zone, fold=0)
        else:
            # astimezone() on a naive datetime attaches the system zone
            # (same fold=0 semantics as above).
            dt = dt.astimezone()
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def serialize_borg_archive_time(
    value: Any, *, timezone_name: Optional[str] = None
) -> Optional[str]:
    """Re-render a borg-rendered timestamp as an ISO-8601 UTC string with offset.

    Borg's own rendering may be naive (borg1), which JavaScript's Date parses
    as browser-local time; serializing with an explicit offset makes the value
    self-describing for display. ``timezone_name`` has the same semantics as in
    parse_borg_archive_time. Unparseable strings are returned unchanged so a
    response never loses the raw value.
    """
    parsed = parse_borg_archive_time(value, timezone_name=timezone_name)
    if parsed is None:
        return value if isinstance(value, str) else None
    return serialize_datetime(parsed)


def serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
    """
    Serialize a datetime to ISO format with UTC timezone.

    This function handles both timezone-aware and naive datetimes:
    - Naive datetimes (from SQLite) are assumed to be UTC and converted
    - Timezone-aware datetimes are converted to UTC

    Args:
        dt: DateTime object to serialize (can be None)

    Returns:
        ISO format string with timezone (e.g., "2025-11-24T05:33:17.115198+00:00")
        or None if input is None

    Example:
        >>> dt = datetime(2025, 11, 24, 5, 33, 17)  # naive datetime from DB
        >>> serialize_datetime(dt)
        '2025-11-24T05:33:17+00:00'
    """
    if dt is None:
        return None

    # If datetime is naive (no timezone), assume it's UTC (from database)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        # If it has timezone info, convert to UTC
        dt = dt.astimezone(timezone.utc)

    return dt.isoformat()
