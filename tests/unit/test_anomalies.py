from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.operations import anomalies as an


@pytest.mark.unit
def test_median():
    assert an.median([]) is None
    assert an.median([3]) == 3
    assert an.median([1, 5, 3]) == 3
    assert an.median([1, 2, 3, 4]) == 2.5


@pytest.mark.unit
def test_size_outlier_boundaries():
    prev = [100, 100, 100, 100, 100, 100, 100]
    assert an.size_outlier(prev, 59) is True
    assert an.size_outlier(prev, 60) is False
    assert an.size_outlier(prev, None) is False
    assert an.size_outlier([], 1) is False
    assert an.size_outlier([None, None], 1) is False
    # only the last seven count
    assert an.size_outlier([1] * 10 + [100] * 7, 59) is True


@pytest.mark.unit
def test_duration_outlier_boundaries():
    prev = [10.0] * 7
    assert an.duration_outlier(prev, 25.0) is False
    assert an.duration_outlier(prev, 25.1) is True
    assert an.duration_outlier(prev, None) is False


@pytest.mark.unit
def test_median_gap_uses_last_fourteen():
    starts = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(20)]
    assert an.median_gap(starts) == timedelta(days=1)
    assert an.median_gap(starts[:1]) is None
    assert an.median_gap([]) is None


@pytest.mark.unit
def test_expected_days_from_cron_and_gap():
    days = an.expected_days_from_cron(
        "0 2 * * *", datetime(2026, 9, 1), datetime(2026, 9, 4), "UTC"
    )
    assert days == {date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)}
    days = an.expected_days_from_gap(
        datetime(2026, 9, 1, 2), datetime(2026, 9, 8), timedelta(days=2)
    )
    assert days == {
        date(2026, 9, 1),
        date(2026, 9, 3),
        date(2026, 9, 5),
        date(2026, 9, 7),
    }
    # sub-daily cadence is capped at one expected day per day
    days = an.expected_days_from_gap(
        datetime(2026, 9, 1), datetime(2026, 9, 3), timedelta(hours=6)
    )
    assert days == {date(2026, 9, 1), date(2026, 9, 2)}


@pytest.mark.unit
def test_missed_run_days_from_cron_and_from_gap():
    starts = [datetime(2026, 9, d, 2) for d in (1, 2, 4, 5)]
    missed = an.missed_run_days(
        starts, until=datetime(2026, 9, 6), cron_expression="0 2 * * *"
    )
    assert missed == {date(2026, 9, 3)}
    missed = an.missed_run_days(starts, until=datetime(2026, 9, 6))
    assert missed == {date(2026, 9, 3)}
    assert (
        an.missed_run_days([datetime(2026, 9, 1)], until=datetime(2026, 9, 6)) == set()
    )
    # a day whose expected run is not yet due is not missed
    missed = an.missed_run_days(
        starts, until=datetime(2026, 9, 6, 1), cron_expression="0 2 * * *"
    )
    assert date(2026, 9, 6) not in missed


@pytest.mark.unit
def test_overdue_thresholds():
    now = datetime(2026, 9, 10)
    assert an.OVERDUE_THRESHOLD_DAYS == {
        "backup": 2,
        "check": 30,
        "prune": 14,
        "compact": 30,
        "index": 2,
        "mirror": 1,
    }
    assert an.overdue("backup", now - timedelta(days=2, seconds=1), now) is True
    assert an.overdue("backup", now - timedelta(days=2), now) is False
    assert an.overdue("check", None, now) is True
    assert an.overdue("unknown", now, now) is False


@pytest.mark.unit
def test_series_flags_per_archive():
    mk = lambda i, size, dur: SimpleNamespace(
        id=i,
        start=datetime(2026, 9, i),
        deduplicated_size=size,
        nfiles=10,
        duration_seconds=dur,
    )
    archives = [mk(i, 100, 10.0) for i in range(1, 8)] + [
        mk(8, 50, 10.0),
        mk(9, 100, 30.0),
    ]
    flags = an.series_flags(archives)
    assert flags[8] == ["size_outlier"]
    assert flags[9] == ["duration_outlier"]
    assert flags[3] == []
    # nfiles counts too
    archives = [mk(i, 100, 10.0) for i in range(1, 8)] + [
        SimpleNamespace(
            id=8,
            start=datetime(2026, 9, 8),
            deduplicated_size=100,
            nfiles=1,
            duration_seconds=10.0,
        )
    ]
    assert an.series_flags(archives)[8] == ["size_outlier"]
