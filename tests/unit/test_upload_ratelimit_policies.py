from datetime import datetime, timezone

import pytest

from app.services.upload_ratelimit_policies import resolve_scheduled_upload_ratelimit


@pytest.mark.unit
def test_resolves_daytime_policy_over_constant_limit():
    policies = [
        {
            "label": "Daytime cap",
            "start_time": "08:00",
            "end_time": "18:00",
            "upload_ratelimit_kib": 512,
        },
        {
            "label": "Overnight unlimited",
            "start_time": "18:00",
            "end_time": "08:00",
            "upload_ratelimit_kib": None,
        },
    ]

    resolved = resolve_scheduled_upload_ratelimit(
        base_upload_ratelimit_kib=2048,
        policies=policies,
        run_at=datetime(2026, 6, 10, 12, 30, tzinfo=timezone.utc),
        timezone_name="UTC",
    )

    assert resolved == 512


@pytest.mark.unit
def test_overnight_unlimited_policy_clears_constant_limit():
    policies = [
        {
            "label": "Overnight unlimited",
            "start_time": "18:00",
            "end_time": "08:00",
            "upload_ratelimit_kib": None,
        }
    ]

    resolved = resolve_scheduled_upload_ratelimit(
        base_upload_ratelimit_kib=2048,
        policies=policies,
        run_at=datetime(2026, 6, 10, 23, 15, tzinfo=timezone.utc),
        timezone_name="UTC",
    )

    assert resolved is None


@pytest.mark.unit
def test_no_matching_policy_uses_constant_limit():
    policies = [
        {
            "label": "Daytime cap",
            "start_time": "08:00",
            "end_time": "18:00",
            "upload_ratelimit_kib": 512,
        }
    ]

    resolved = resolve_scheduled_upload_ratelimit(
        base_upload_ratelimit_kib=2048,
        policies=policies,
        run_at=datetime(2026, 6, 10, 19, 30, tzinfo=timezone.utc),
        timezone_name="UTC",
    )

    assert resolved == 2048


@pytest.mark.unit
def test_policy_matching_uses_backup_plan_timezone():
    policies = [
        {
            "label": "New York evening",
            "start_time": "19:00",
            "end_time": "23:00",
            "upload_ratelimit_kib": 1024,
        }
    ]

    resolved = resolve_scheduled_upload_ratelimit(
        base_upload_ratelimit_kib=4096,
        policies=policies,
        run_at=datetime(2026, 6, 11, 2, 30, tzinfo=timezone.utc),
        timezone_name="America/New_York",
    )

    assert resolved == 1024
