import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.database.models import CheckJob, Repository, SystemSettings
from app.services.check_scheduler import CheckScheduler
from app.services.mqtt_sync_scheduler import periodic_mqtt_sync, start_mqtt_sync_scheduler
from app.services.stats_refresh_scheduler import StatsRefreshScheduler


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_scheduler_creates_job_and_updates_next_run(db_session):
    repo = Repository(
        name="Repo",
        path="/tmp/repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
        check_cron_expression="0 2 * * *",
        check_max_duration=123,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    scheduler = CheckScheduler()
    fake_router = MagicMock()
    fake_router.check.return_value = AsyncMock()
    testing_session_local = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)

    with patch("app.services.check_scheduler.SessionLocal", testing_session_local):
        with patch("app.services.check_scheduler.BorgRouter", return_value=fake_router):
            with patch("app.services.check_scheduler.asyncio.create_task") as mock_create_task:
                await scheduler.run_scheduled_checks()

    verification_session = testing_session_local()
    jobs = verification_session.query(CheckJob).filter(CheckJob.repository_id == repo.id).all()
    assert len(jobs) == 1
    assert jobs[0].status == "pending"
    assert jobs[0].scheduled_check is True
    assert jobs[0].max_duration == 123

    repo = verification_session.query(Repository).filter(Repository.id == repo.id).first()
    assert repo.last_scheduled_check is not None
    assert repo.next_scheduled_check is not None
    mock_create_task.assert_called_once()
    verification_session.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_scheduler_ignores_invalid_cron_expression(db_session):
    repo = Repository(
        name="Broken Cron Repo",
        path="/tmp/repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
        check_cron_expression="not a cron",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    scheduler = CheckScheduler()
    fake_router = MagicMock()
    fake_router.check.return_value = AsyncMock()
    testing_session_local = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)

    with patch("app.services.check_scheduler.SessionLocal", testing_session_local):
        with patch("app.services.check_scheduler.BorgRouter", return_value=fake_router):
            with patch("app.services.check_scheduler.asyncio.create_task"):
                await scheduler.run_scheduled_checks()

    verification_session = testing_session_local()
    repo = verification_session.query(Repository).filter(Repository.id == repo.id).first()
    assert repo.last_scheduled_check is not None
    assert repo.next_scheduled_check is None
    verification_session.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stats_refresh_scheduler_updates_repositories_and_settings(db_session):
    repo1 = Repository(
        name="Repo 1",
        path="/tmp/repo1",
        encryption="none",
        compression="lz4",
        repository_type="local",
    )
    repo2 = Repository(
        name="Repo 2",
        path="/tmp/repo2",
        encryption="none",
        compression="lz4",
        repository_type="local",
    )
    settings = SystemSettings(plan="community")
    db_session.add_all([repo1, repo2, settings])
    db_session.commit()

    scheduler = StatsRefreshScheduler()
    update_results = [True, False]
    sync_state_with_db = MagicMock()
    testing_session_local = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)

    class FakeRouter:
        def __init__(self, repo):
            self.repo = repo

        async def update_stats(self, db):
            return update_results.pop(0)

    with patch("app.services.stats_refresh_scheduler.SessionLocal", testing_session_local):
        with patch("app.services.stats_refresh_scheduler.BorgRouter", side_effect=FakeRouter):
            with patch("app.services.mqtt_service.mqtt_service.sync_state_with_db", sync_state_with_db):
                await scheduler.refresh_all_repository_stats()

    verification_session = testing_session_local()
    settings = verification_session.query(SystemSettings).first()
    assert settings.last_stats_refresh is not None
    sync_state_with_db.assert_called_once()
    verification_session.close()


@pytest.mark.unit
def test_stats_refresh_scheduler_reads_interval_from_settings(db_session):
    db_session.add(SystemSettings(plan="community", stats_refresh_interval_minutes=15))
    db_session.commit()

    scheduler = StatsRefreshScheduler()
    testing_session_local = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)

    with patch("app.services.stats_refresh_scheduler.SessionLocal", testing_session_local):
        assert scheduler._get_refresh_interval_minutes() == 15


@pytest.mark.unit
@pytest.mark.asyncio
async def test_periodic_mqtt_sync_runs_once_before_cancellation():
    sync_state = MagicMock()

    async def stop_after_first_sleep(_seconds):
        raise asyncio.CancelledError

    with patch("app.services.mqtt_sync_scheduler.mqtt_service.sync_state", sync_state):
        with patch("app.services.mqtt_sync_scheduler.asyncio.sleep", side_effect=stop_after_first_sleep):
            with pytest.raises(asyncio.CancelledError):
                await periodic_mqtt_sync(interval_minutes=1)

    sync_state.assert_called_once_with(reason="periodic_scheduler")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_mqtt_sync_scheduler_delegates_to_periodic_sync():
    with patch("app.services.mqtt_sync_scheduler.periodic_mqtt_sync", new=AsyncMock()) as mock_periodic:
        await start_mqtt_sync_scheduler()

    mock_periodic.assert_awaited_once_with(5)
