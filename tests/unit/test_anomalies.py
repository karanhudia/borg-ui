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
def test_expected_days_from_cron():
    days = an.expected_days_from_cron(
        "0 2 * * *", datetime(2026, 9, 1), datetime(2026, 9, 4), "UTC"
    )
    assert days == {date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)}


@pytest.mark.unit
def test_missed_run_days_needs_a_cron():
    """Without a cron from a schedule or plan the cadence is a guess, and a
    guess flagged pruned days as missed runs (issue #943)."""
    starts = [datetime(2026, 9, d, 2) for d in (1, 2, 4, 5)]
    missed = an.missed_run_days(
        starts, until=datetime(2026, 9, 6), cron_expression="0 2 * * *"
    )
    assert missed == {date(2026, 9, 3)}
    assert an.missed_run_days(starts, until=datetime(2026, 9, 6)) == set()
    assert (
        an.missed_run_days(
            [datetime(2026, 9, 1)], until=datetime(2026, 9, 6), cron_expression=None
        )
        == set()
    )
    # a day whose expected run is not yet due is not missed
    missed = an.missed_run_days(
        starts, until=datetime(2026, 9, 6, 1), cron_expression="0 2 * * *"
    )
    assert date(2026, 9, 6) not in missed


@pytest.mark.unit
def test_a_completed_run_is_not_a_missed_day():
    """The archive of a run that happened may have been pruned since; the run
    record is the evidence that keeps the day out of the red (issue #943)."""
    starts = [datetime(2026, 9, d, 2) for d in (1, 2, 4, 5)]
    assert (
        an.missed_run_days(
            starts,
            until=datetime(2026, 9, 6),
            cron_expression="0 2 * * *",
            run_days=[date(2026, 9, 3)],
        )
        == set()
    )


@pytest.mark.unit
def test_days_outside_the_retention_window_are_not_missed():
    """Beyond the daily keeps the repository is expected to have no archive,
    so an absent day there says nothing about whether a run happened."""
    starts = [datetime(2026, 9, d, 2) for d in (1, 5)]
    assert an.missed_run_days(
        starts, until=datetime(2026, 9, 6), cron_expression="0 2 * * *"
    ) == {date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4)}
    assert an.missed_run_days(
        starts,
        until=datetime(2026, 9, 6),
        cron_expression="0 2 * * *",
        retention_since=date(2026, 9, 4),
    ) == {date(2026, 9, 4)}


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
    # the fixed thresholds feed the heatmap and the default cadence; the
    # strip judges against overdue_after with a schedule-aware threshold
    assert an.overdue_after(now - timedelta(days=2, seconds=1), now, timedelta(days=2))
    assert not an.overdue_after(now - timedelta(days=2), now, timedelta(days=2))
    assert an.overdue_after(None, now, timedelta(days=30))


@pytest.mark.unit
def test_series_flags_per_archive():
    mk = lambda i, size, dur: SimpleNamespace(
        id=i,
        start=datetime(2026, 9, i),
        original_size=size,
        deduplicated_size=1,
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
            original_size=100,
            deduplicated_size=1,
            nfiles=1,
            duration_seconds=10.0,
        )
    ]
    assert an.series_flags(archives)[8] == ["size_outlier"]


@pytest.mark.unit
def test_size_outlier_ignores_deduplicated_size():
    """A retention keep absorbs the unique data of the archives pruned around
    it, so its deduplicated size dwarfs a normal archive's and flagged every
    healthy daily archive next to it (issue #943)."""
    keeps = [
        SimpleNamespace(
            id=i,
            start=datetime(2026, 9, i),
            original_size=100,
            deduplicated_size=20_000,
            nfiles=10,
            duration_seconds=10.0,
        )
        for i in range(1, 8)
    ]
    daily = SimpleNamespace(
        id=8,
        start=datetime(2026, 9, 8),
        original_size=100,
        deduplicated_size=700,
        nfiles=10,
        duration_seconds=10.0,
    )
    assert an.series_flags([*keeps, daily])[8] == []


@pytest.mark.unit
def test_cron_days_stay_in_utc_for_a_non_utc_schedule():
    """Archive starts are naive UTC, so the expected days must be UTC days too.
    A Europe/Berlin 01:00 schedule fires at 23:00 UTC the day before, and every
    one of those runs has to line up with the archive it produced, or the
    heatmap flags almost every day as a missed run."""
    # 2026-09-02 01:00 Berlin (CEST, UTC+2) is 2026-09-01 23:00 UTC.
    days = an.expected_days_from_cron(
        "0 1 * * *",
        datetime(2026, 9, 1, 12),
        datetime(2026, 9, 4),
        "Europe/Berlin",
    )
    assert days == {date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)}

    starts = [datetime(2026, 9, d, 23) for d in (1, 2, 4)]
    missed = an.missed_run_days(
        starts,
        until=datetime(2026, 9, 6),
        cron_expression="0 1 * * *",
        timezone_name="Europe/Berlin",
    )
    assert missed == {date(2026, 9, 3), date(2026, 9, 5)}
