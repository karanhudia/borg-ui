from datetime import datetime, timezone

import pytest

from app.utils.schedule_time import (
    InvalidScheduleTimezone,
    calculate_next_cron_run,
    normalize_schedule_timezone,
)


@pytest.mark.unit
def test_calculate_next_cron_run_interprets_cron_in_schedule_timezone():
    base_time = datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc)

    next_run = calculate_next_cron_run(
        "0 2 * * *",
        base_time=base_time,
        schedule_timezone="Asia/Kolkata",
    )

    assert next_run == datetime(2026, 1, 1, 20, 30)


@pytest.mark.unit
def test_calculate_next_cron_run_defaults_to_utc_for_existing_schedules():
    base_time = datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc)

    next_run = calculate_next_cron_run("0 2 * * *", base_time=base_time)

    assert next_run == datetime(2026, 1, 2, 2, 0)


@pytest.mark.unit
def test_normalize_schedule_timezone_rejects_invalid_timezone():
    with pytest.raises(InvalidScheduleTimezone):
        normalize_schedule_timezone("not/a-zone")
