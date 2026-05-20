from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.database.models import BackupJob, Repository, SystemSettings
from app.services.backup_monitoring_service import (
    build_backup_report,
    find_stale_repositories,
    is_monitoring_due,
    is_report_due,
    run_backup_monitoring,
    send_backup_report_now,
)


@pytest.mark.unit
def test_find_stale_repositories_includes_full_and_observe_repositories(db_session):
    now = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
    repos = [
        Repository(
            name="Fresh",
            path="/repos/fresh",
            encryption="none",
            repository_type="local",
            mode="full",
            last_backup=now - timedelta(days=1),
            archive_count=8,
        ),
        Repository(
            name="Stale Full",
            path="/repos/stale-full",
            encryption="none",
            repository_type="local",
            mode="full",
            last_backup=now - timedelta(days=5, hours=2),
            archive_count=3,
        ),
        Repository(
            name="Stale Imported",
            path="/repos/stale-imported",
            encryption="none",
            repository_type="local",
            mode="observe",
            last_backup=now - timedelta(days=8),
            archive_count=12,
        ),
        Repository(
            name="Never Backed Up",
            path="/repos/never",
            encryption="none",
            repository_type="local",
            mode="full",
            last_backup=None,
            archive_count=0,
        ),
    ]
    db_session.add_all(repos)
    db_session.commit()

    stale = find_stale_repositories(
        db_session, now, stale_after_days=3, include_observe_repos=True
    )

    assert [repo.name for repo in stale] == [
        "Stale Full",
        "Stale Imported",
        "Never Backed Up",
    ]
    assert stale[0].days_since_backup == 5
    assert stale[1].mode == "observe"
    assert stale[2].reason == "never_backed_up"


@pytest.mark.unit
def test_find_stale_repositories_can_exclude_observe_repositories(db_session):
    now = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
    db_session.add_all(
        [
            Repository(
                name="Stale Imported",
                path="/repos/stale-imported",
                encryption="none",
                repository_type="local",
                mode="observe",
                last_backup=now - timedelta(days=8),
                archive_count=12,
            ),
            Repository(
                name="Stale Managed",
                path="/repos/stale-managed",
                encryption="none",
                repository_type="local",
                mode="full",
                last_backup=now - timedelta(days=4),
                archive_count=4,
            ),
        ]
    )
    db_session.commit()

    stale = find_stale_repositories(
        db_session, now, stale_after_days=3, include_observe_repos=False
    )

    assert [repo.name for repo in stale] == ["Stale Managed"]


@pytest.mark.unit
def test_monitoring_due_respects_interval_hours():
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    settings = SystemSettings(
        backup_monitoring_enabled=True,
        backup_monitoring_interval_hours=6,
        backup_monitoring_last_checked_at=now - timedelta(hours=5, minutes=59),
    )

    assert is_monitoring_due(settings, now) is False

    settings.backup_monitoring_last_checked_at = now - timedelta(hours=6)
    assert is_monitoring_due(settings, now) is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_backup_monitoring_respects_alert_cooldown(db_session):
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    settings = SystemSettings(
        backup_monitoring_enabled=True,
        backup_monitoring_stale_after_days=3,
        backup_monitoring_interval_hours=1,
        backup_monitoring_alert_cooldown_hours=24,
        backup_monitoring_include_observe_repos=True,
        backup_monitoring_last_checked_at=now - timedelta(hours=2),
        backup_monitoring_last_alert_sent_at=now - timedelta(hours=2),
    )
    repo = Repository(
        name="Stale",
        path="/repos/stale",
        encryption="none",
        repository_type="local",
        last_backup=now - timedelta(days=10),
        archive_count=2,
    )
    db_session.add_all([settings, repo])
    db_session.commit()

    with patch(
        "app.services.backup_monitoring_service.NotificationService.send_stale_backup_alert",
        new=AsyncMock(),
    ) as mock_send:
        result = await run_backup_monitoring(db_session, now)

    assert result["stale_count"] == 1
    assert result["alert_sent"] is False
    mock_send.assert_not_awaited()
    db_session.refresh(settings)
    assert settings.backup_monitoring_last_checked_at == now.replace(tzinfo=None)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_backup_monitoring_sends_alert_when_stale_and_cooldown_elapsed(
    db_session,
):
    now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
    settings = SystemSettings(
        backup_monitoring_enabled=True,
        backup_monitoring_stale_after_days=3,
        backup_monitoring_interval_hours=1,
        backup_monitoring_alert_cooldown_hours=24,
        backup_monitoring_include_observe_repos=True,
        backup_monitoring_last_checked_at=now - timedelta(hours=2),
        backup_monitoring_last_alert_sent_at=now - timedelta(days=2),
    )
    repo = Repository(
        name="Stale",
        path="/repos/stale",
        encryption="none",
        repository_type="local",
        last_backup=now - timedelta(days=10),
        archive_count=2,
    )
    db_session.add_all([settings, repo])
    db_session.commit()

    with patch(
        "app.services.backup_monitoring_service.NotificationService.send_stale_backup_alert",
        new=AsyncMock(),
    ) as mock_send:
        result = await run_backup_monitoring(db_session, now)

    assert result["stale_count"] == 1
    assert result["alert_sent"] is True
    mock_send.assert_awaited_once()
    db_session.refresh(settings)
    assert settings.backup_monitoring_last_alert_sent_at == now.replace(tzinfo=None)


@pytest.mark.unit
def test_report_due_supports_daily_weekly_and_monthly_windows():
    now = datetime(2026, 5, 20, 8, 30, tzinfo=timezone.utc)  # Wednesday
    settings = SystemSettings(
        backup_reports_enabled=True,
        backup_reports_frequency="daily",
        backup_reports_hour_utc=8,
        backup_reports_last_sent_at=now - timedelta(days=1),
    )
    assert is_report_due(settings, now) is True

    settings.backup_reports_last_sent_at = now.replace(tzinfo=None)
    assert is_report_due(settings, now) is False

    settings.backup_reports_frequency = "weekly"
    settings.backup_reports_weekday = 2
    settings.backup_reports_last_sent_at = now - timedelta(days=8)
    assert is_report_due(settings, now) is True

    settings.backup_reports_frequency = "monthly"
    settings.backup_reports_monthday = 20
    settings.backup_reports_last_sent_at = datetime(2026, 4, 20, 9, 0)
    assert is_report_due(settings, now) is True


@pytest.mark.unit
def test_build_backup_report_respects_content_toggles(db_session):
    now = datetime(2026, 5, 20, 8, 30, tzinfo=timezone.utc)
    settings = SystemSettings(
        backup_monitoring_stale_after_days=3,
        backup_monitoring_include_observe_repos=True,
        backup_reports_include_summary=True,
        backup_reports_include_stale_repositories=True,
        backup_reports_include_recent_activity=True,
    )
    repo = Repository(
        name="Stale",
        path="/repos/stale",
        encryption="none",
        repository_type="local",
        last_backup=now - timedelta(days=10),
        archive_count=2,
    )
    job = BackupJob(
        repository="/repos/stale",
        status="completed",
        started_at=now - timedelta(hours=2),
        completed_at=now - timedelta(hours=1),
    )
    db_session.add_all([settings, repo, job])
    db_session.commit()

    report = build_backup_report(db_session, settings, now)

    assert report.repository_count == 1
    assert report.stale_count == 1
    assert "Repositories: 1" in report.body
    assert "Stale" in report.body
    assert "Recent backup activity" in report.body


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_backup_report_now_dispatches_and_updates_last_sent(db_session):
    now = datetime(2026, 5, 20, 8, 30, tzinfo=timezone.utc)
    settings = SystemSettings(
        backup_reports_enabled=False,
        backup_reports_frequency="weekly",
        backup_reports_include_summary=True,
    )
    repo = Repository(
        name="Repo",
        path="/repos/repo",
        encryption="none",
        repository_type="local",
        last_backup=now - timedelta(days=1),
        archive_count=2,
    )
    db_session.add_all([settings, repo])
    db_session.commit()

    with patch(
        "app.services.backup_monitoring_service.NotificationService.send_backup_report",
        new=AsyncMock(),
    ) as mock_send:
        result = await send_backup_report_now(db_session, now)

    assert result["sent"] is True
    assert result["repository_count"] == 1
    mock_send.assert_awaited_once()
    db_session.refresh(settings)
    assert settings.backup_reports_last_sent_at == now.replace(tzinfo=None)
