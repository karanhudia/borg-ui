"""Anomaly rules (spec section 9.5). Pure functions; the heatmap and
status-strip routes call them and decide which flags the plan may show."""

from datetime import date, datetime, timedelta, timezone
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from croniter import croniter

OVERDUE_THRESHOLD_DAYS: dict[str, int] = {
    "backup": 2,
    "check": 30,
    "prune": 14,
    "compact": 30,
    "index": 2,
    "mirror": 1,
}
SIZE_OUTLIER_RATIO = 0.6
DURATION_OUTLIER_RATIO = 2.5
OUTLIER_WINDOW = 7
CADENCE_SAMPLE = 14
MAX_EXPECTED_DAYS = 5000


def median(values: Sequence[float]) -> Optional[float]:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def _window(previous: Sequence) -> list:
    return [v for v in list(previous)[-OUTLIER_WINDOW:] if v is not None]


def size_outlier(previous: Sequence[Optional[int]], value: Optional[int]) -> bool:
    base = median(_window(previous))
    if value is None or base is None:
        return False
    return value < SIZE_OUTLIER_RATIO * base


def duration_outlier(
    previous: Sequence[Optional[float]], value: Optional[float]
) -> bool:
    base = median(_window(previous))
    if value is None or base is None:
        return False
    return value > DURATION_OUTLIER_RATIO * base


def median_gap(starts: Sequence[datetime]) -> Optional[timedelta]:
    sample = sorted(starts)[-CADENCE_SAMPLE:]
    if len(sample) < 2:
        return None
    gaps = [(b - a).total_seconds() for a, b in zip(sample, sample[1:])]
    return timedelta(seconds=median(gaps))


def expected_days_from_cron(
    cron_expression: str,
    start: datetime,
    until: datetime,
    timezone_name: Optional[str] = None,
) -> set[date]:
    tz = ZoneInfo(timezone_name) if timezone_name else None
    # `start` and `until` are naive UTC, matching Archive.start. A cron fires in
    # its own zone, so the base is converted into that zone and every firing is
    # converted back, keeping the returned days in UTC like the archive days
    # they are compared against.
    base = start.replace(tzinfo=timezone.utc).astimezone(tz) if tz else start
    it = croniter(cron_expression, base)
    days: set[date] = set()
    while len(days) < MAX_EXPECTED_DAYS:
        nxt = it.get_next(datetime)
        naive = nxt.astimezone(timezone.utc).replace(tzinfo=None) if nxt.tzinfo else nxt
        if naive > until:
            break
        days.add(naive.date())
    return days


def expected_days_from_gap(
    first: datetime, last: datetime, until: datetime, gap: timedelta
) -> set[date]:
    """Expected days at cadence `gap`, phased on `last` rather than `first`.

    The newest archive is the best evidence of when the backup currently runs;
    anchoring on the oldest lets a schedule that moved drift out of phase and
    report a missed day for the offset between the old time and the new one.
    """
    step = max(gap, timedelta(days=1))
    days: set[date] = set()
    current = last
    while current >= first and len(days) < MAX_EXPECTED_DAYS:
        days.add(current.date())
        current -= step
    current = last + step
    while current < until and len(days) < MAX_EXPECTED_DAYS:
        days.add(current.date())
        current += step
    return days


def missed_run_days(
    starts: Sequence[datetime],
    *,
    until: datetime,
    cron_expression: Optional[str] = None,
    timezone_name: Optional[str] = None,
) -> set[date]:
    """Days inside the series cadence with no archive. Cadence is the cron
    when known, else the median gap of the last 14 archives. A day is only
    counted once its expected run time has passed."""
    if not starts:
        return set()
    first = min(starts)
    present = {s.date() for s in starts}
    if cron_expression:
        # Start the iteration just before the first archive so its own day
        # counts as expected. Days after `until` are excluded by the helper.
        expected = expected_days_from_cron(
            cron_expression, first - timedelta(seconds=1), until, timezone_name
        )
    else:
        gap = median_gap(starts)
        if gap is None:
            return set()
        # `until` directly: the helper already stops at the last expected time
        # before it, so subtracting a gap would hide a run that is already due.
        expected = expected_days_from_gap(first, max(starts), until, gap)
    return {d for d in expected if d not in present and d >= first.date()}


def overdue(cell: str, last_completed_at: Optional[datetime], now: datetime) -> bool:
    threshold = OVERDUE_THRESHOLD_DAYS.get(cell)
    if threshold is None:
        return False
    if last_completed_at is None:
        return True
    return now - last_completed_at > timedelta(days=threshold)


def series_flags(archives: Sequence) -> dict[int, list[str]]:
    """Outlier flags per archive id, comparing each archive with the seven
    before it in start order."""
    ordered = sorted(archives, key=lambda a: (a.start, a.id))
    flags: dict[int, list[str]] = {}
    for i, archive in enumerate(ordered):
        previous = ordered[max(0, i - OUTLIER_WINDOW) : i]
        found: list[str] = []
        if size_outlier(
            [p.deduplicated_size for p in previous], archive.deduplicated_size
        ) or size_outlier([p.nfiles for p in previous], archive.nfiles):
            found.append("size_outlier")
        if duration_outlier(
            [p.duration_seconds for p in previous], archive.duration_seconds
        ):
            found.append("duration_outlier")
        flags[archive.id] = found
    return flags
