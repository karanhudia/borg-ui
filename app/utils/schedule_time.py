"""Helpers for recurring schedule timezone intent."""

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

DEFAULT_SCHEDULE_TIMEZONE = "UTC"


class InvalidScheduleTimezone(ValueError):
    """Raised when a schedule timezone is not a valid IANA timezone."""


def normalize_schedule_timezone(value: Optional[str]) -> str:
    schedule_timezone = (value or DEFAULT_SCHEDULE_TIMEZONE).strip()
    if not schedule_timezone:
        schedule_timezone = DEFAULT_SCHEDULE_TIMEZONE

    try:
        ZoneInfo(schedule_timezone)
    except ZoneInfoNotFoundError as exc:
        raise InvalidScheduleTimezone(
            f"Invalid schedule timezone: {schedule_timezone}"
        ) from exc

    return schedule_timezone


def to_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_utc_naive(value: datetime) -> datetime:
    return to_utc_aware(value).replace(tzinfo=None)


def _ensure_localized(value: datetime, schedule_timezone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=schedule_timezone)
    return value


def calculate_next_cron_run(
    cron_expression: str,
    base_time: Optional[datetime] = None,
    schedule_timezone: Optional[str] = None,
) -> datetime:
    """
    Calculate the next run for a cron expression interpreted in schedule_timezone.

    The returned datetime is naive UTC, matching the database convention used by
    SQLite-backed DateTime columns in the application.
    """
    timezone_name = normalize_schedule_timezone(schedule_timezone)
    schedule_tz = ZoneInfo(timezone_name)
    base_utc = to_utc_aware(base_time or datetime.now(timezone.utc))
    base_local = base_utc.astimezone(schedule_tz)

    cron = croniter(cron_expression, base_local)
    next_local = _ensure_localized(cron.get_next(datetime), schedule_tz)
    return to_utc_naive(next_local)


def calculate_next_cron_runs(
    cron_expression: str,
    count: int,
    base_time: Optional[datetime] = None,
    schedule_timezone: Optional[str] = None,
) -> list[datetime]:
    timezone_name = normalize_schedule_timezone(schedule_timezone)
    schedule_tz = ZoneInfo(timezone_name)
    base_utc = to_utc_aware(base_time or datetime.now(timezone.utc))
    base_local = base_utc.astimezone(schedule_tz)

    cron = croniter(cron_expression, base_local)
    runs: list[datetime] = []
    for _ in range(count):
        next_local = _ensure_localized(cron.get_next(datetime), schedule_tz)
        runs.append(to_utc_naive(next_local))

    return runs
