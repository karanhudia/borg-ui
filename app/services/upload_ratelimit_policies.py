from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def parse_upload_policy_time(value: str) -> time:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("time must use HH:MM format")
    hour_text, minute_text = parts
    if len(hour_text) != 2 or len(minute_text) != 2:
        raise ValueError("time must use HH:MM format")
    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("time must be a valid 24-hour clock value")
    return time(hour=hour, minute=minute)


def _is_active_window(current: time, start: time, end: time) -> bool:
    if start < end:
        return start <= current < end
    return current >= start or current < end


def _coerce_run_at(run_at: datetime, timezone_name: str) -> datetime:
    try:
        schedule_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        schedule_timezone = timezone.utc
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=timezone.utc)
    return run_at.astimezone(schedule_timezone)


def resolve_scheduled_upload_ratelimit(
    *,
    base_upload_ratelimit_kib: int | None,
    policies: list[dict[str, Any]] | None,
    run_at: datetime,
    timezone_name: str,
) -> int | None:
    if not policies:
        return base_upload_ratelimit_kib

    current_time = (
        _coerce_run_at(run_at, timezone_name)
        .time()
        .replace(
            second=0,
            microsecond=0,
        )
    )
    for policy in policies:
        try:
            start = parse_upload_policy_time(str(policy["start_time"]))
            end = parse_upload_policy_time(str(policy["end_time"]))
        except (KeyError, TypeError, ValueError):
            continue
        if start == end:
            continue
        if _is_active_window(current_time, start, end):
            value = policy.get("upload_ratelimit_kib")
            return value if isinstance(value, int) and value > 0 else None
    return base_upload_ratelimit_kib
