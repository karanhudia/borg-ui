"""
Datetime utilities for consistent timezone handling across the application.

All datetimes in the database are stored as UTC (naive format due to SQLite limitations).
This module provides utilities to ensure consistent serialization to frontend.
"""
from datetime import datetime, timezone
from typing import Optional


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
