import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from datetime import datetime, timedelta, timezone

from app.database.models import CheckJob, Repository, ScheduledJob, SystemSettings
from app.services.check_scheduler import run_due_scheduled_checks
from app.services.mqtt_sync_scheduler import (
    periodic_mqtt_sync,
    start_mqtt_sync_scheduler,
)
from app.services.stats_refresh_scheduler import StatsRefreshScheduler
from app.api import schedule as schedule_api
from app.api.schedule import check_scheduled_jobs, dispatch_due_scheduled_backups


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

    fake_router = MagicMock()
    fake_router.check.return_value = AsyncMock()
    with patch("app.services.check_scheduler.BorgRouter", return_value=fake_router):
        with patch(
            "app.services.check_scheduler.start_background_maintenance_job"
        ) as mock_start:
            mock_start.side_effect = lambda db, repo, job_model, **kwargs: CheckJob(
                id=42,
                repository_id=repo.id,
                status="pending",
                max_duration=kwargs["extra_fields"]["max_duration"],
                scheduled_check=True,
            )
            await run_due_scheduled_checks(db_session)

    db_session.refresh(repo)
    assert repo.last_scheduled_check is not None
    assert repo.next_scheduled_check is not None
    mock_start.assert_called_once()


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

    fake_router = MagicMock()
    fake_router.check.return_value = AsyncMock()
    with patch("app.services.check_scheduler.BorgRouter", return_value=fake_router):
        with patch(
            "app.services.check_scheduler.start_background_maintenance_job"
        ) as mock_start:
            mock_start.side_effect = lambda db, repo, job_model, **kwargs: CheckJob(
                id=43,
                repository_id=repo.id,
                status="pending",
            )
            await run_due_scheduled_checks(db_session)

    db_session.refresh(repo)
    assert repo.last_scheduled_check is not None
    assert repo.next_scheduled_check is None


class _AsyncLineStream:
    def __init__(self, lines):
        self._lines = [
            line if isinstance(line, bytes) else line.encode("utf-8") for line in lines
        ]
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._lines):
            raise StopAsyncIteration
        value = self._lines[self._index]
        self._index += 1
        return value


class _FakeProcess:
    def __init__(self, returncode=0, stderr_lines=None, pid=4321):
        self.returncode = returncode
        self.stderr = _AsyncLineStream(stderr_lines or [])
        self.stdout = _AsyncLineStream([])
        self.pid = pid

    async def wait(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


class _LockingSession(Session):
    """Inject one transient SQLite lock when a check job is first marked running."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._injected_running_lock = False

    def commit(self):
        dirty_running_jobs = [
            obj
            for obj in self.dirty
            if isinstance(obj, CheckJob) and getattr(obj, "status", None) == "running"
        ]
        if dirty_running_jobs and not self._injected_running_lock:
            self._injected_running_lock = True
            raise OperationalError(
                "UPDATE check_jobs SET status='running'",
                {},
                Exception("database is locked"),
            )
        return super().commit()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_scheduler_runs_all_due_checks_despite_transient_sqlite_locks(
    db_session, tmp_path
):
    repos = []
    for index in range(4):
        repo = Repository(
            name=f"Repo {index}",
            path=f"/tmp/repo-{index}",
            encryption="none",
            compression="lz4",
            repository_type="local",
            check_cron_expression="0 2 * * *",
            borg_version=1,
        )
        db_session.add(repo)
        repos.append(repo)

    db_session.commit()
    for repo in repos:
        db_session.refresh(repo)

    testing_session_local = sessionmaker(
        bind=db_session.get_bind(),
        autocommit=False,
        autoflush=False,
        class_=_LockingSession,
    )

    started_tasks = []
    fake_processes = [
        _FakeProcess(returncode=0, pid=5000 + idx) for idx in range(len(repos))
    ]

    def schedule_and_track(coro):
        task = asyncio.create_task(coro)
        started_tasks.append(task)
        return None

    async def fake_exec(*args, **kwargs):
        return fake_processes.pop(0)

    with (
        patch("app.services.check_service.SessionLocal", testing_session_local),
        patch(
            "app.api.maintenance_jobs.schedule_background_job",
            side_effect=schedule_and_track,
        ),
        patch(
            "app.services.check_service.asyncio.create_subprocess_exec",
            side_effect=fake_exec,
        ),
        patch("app.services.check_service.get_process_start_time", return_value=123),
        patch(
            "app.services.check_service.NotificationService.send_check_completion",
            new=AsyncMock(),
        ),
    ):
        from app.services.check_service import check_service

        check_service.log_dir = Path(tmp_path)
        scheduler_session = testing_session_local()
        await run_due_scheduled_checks(scheduler_session)
        scheduler_session.close()
        await asyncio.gather(*started_tasks)

    verification_session = testing_session_local()
    try:
        check_jobs = verification_session.query(CheckJob).order_by(CheckJob.id).all()
        assert len(check_jobs) == 4
        assert [job.status for job in check_jobs] == ["completed"] * 4
        assert all(job.started_at is not None for job in check_jobs)
        assert all(job.completed_at is not None for job in check_jobs)
        assert not any(job.status == "pending" for job in check_jobs)
    finally:
        verification_session.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_shared_scheduler_loop_runs_due_checks_each_cycle(db_session):
    repo = Repository(
        name="Repo",
        path="/tmp/repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
        check_cron_expression="0 2 * * *",
        next_scheduled_check=datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(minutes=1),
    )
    backup_schedule = ScheduledJob(
        name="Backup Schedule",
        cron_expression="0 2 * * *",
        enabled=True,
        next_run=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add_all([repo, backup_schedule])
    db_session.commit()

    testing_session_local = sessionmaker(
        bind=db_session.get_bind(), autocommit=False, autoflush=False
    )

    async def stop_after_single_tick(_seconds):
        raise RuntimeError("stop loop")

    with (
        patch("app.api.schedule.SessionLocal", testing_session_local),
        patch("app.api.schedule.asyncio.sleep", side_effect=stop_after_single_tick),
        patch(
            "app.api.schedule.run_due_scheduled_checks", new=AsyncMock()
        ) as mock_checks,
    ):
        with pytest.raises(RuntimeError, match="stop loop"):
            await check_scheduled_jobs()

    assert mock_checks.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_shared_scheduler_dispatch_limits_scheduled_backups(db_session):
    repo = Repository(
        name="Repo",
        path="/tmp/repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
    )
    db_session.add(repo)
    db_session.add(SystemSettings(max_concurrent_scheduled_backups=2))
    db_session.flush()

    for index in range(4):
        db_session.add(
            ScheduledJob(
                name=f"Schedule {index}",
                cron_expression="0 2 * * *",
                enabled=True,
                repository_id=repo.id,
                next_run=datetime.now(timezone.utc) - timedelta(minutes=1),
            )
        )
    db_session.commit()

    with patch.object(
        schedule_api,
        "_dispatch_due_scheduled_job",
        side_effect=["run-1", "run-2"],
    ) as mock_dispatch:
        await dispatch_due_scheduled_backups(db_session, datetime.now(timezone.utc))

    assert mock_dispatch.call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_shared_scheduler_dispatch_limits_scheduled_checks(db_session):
    db_session.add(SystemSettings(max_concurrent_scheduled_checks=2))
    repos = []
    for index in range(3):
        repo = Repository(
            name=f"Repo {index}",
            path=f"/tmp/repo-{index}",
            encryption="none",
            compression="lz4",
            repository_type="local",
            check_cron_expression="0 2 * * *",
            next_scheduled_check=datetime.utcnow() - timedelta(minutes=1),
        )
        repos.append(repo)
        db_session.add(repo)

    db_session.flush()
    db_session.add(
        CheckJob(
            repository_id=repos[0].id,
            status="running",
            scheduled_check=True,
        )
    )
    db_session.commit()

    with patch(
        "app.services.check_scheduler.start_background_maintenance_job",
        side_effect=lambda db, repo, job_model, **kwargs: CheckJob(
            id=100 + repo.id,
            repository_id=repo.id,
            status="pending",
            max_duration=kwargs["extra_fields"]["max_duration"],
            scheduled_check=True,
        ),
    ) as mock_start:
        await run_due_scheduled_checks(db_session, datetime.utcnow())

    assert mock_start.call_count == 1


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
    settings = SystemSettings()
    db_session.add_all([repo1, repo2, settings])
    db_session.commit()

    scheduler = StatsRefreshScheduler()
    update_results = [True, False]
    sync_state_with_db = MagicMock()
    testing_session_local = sessionmaker(
        bind=db_session.get_bind(), autocommit=False, autoflush=False
    )

    class FakeRouter:
        def __init__(self, repo):
            self.repo = repo

        async def update_stats(self, db):
            return update_results.pop(0)

    with patch(
        "app.services.stats_refresh_scheduler.SessionLocal", testing_session_local
    ):
        with patch(
            "app.services.stats_refresh_scheduler.BorgRouter", side_effect=FakeRouter
        ):
            with patch(
                "app.services.mqtt_service.mqtt_service.sync_state_with_db",
                sync_state_with_db,
            ):
                await scheduler.refresh_all_repository_stats()

    verification_session = testing_session_local()
    settings = verification_session.query(SystemSettings).first()
    assert settings.last_stats_refresh is not None
    sync_state_with_db.assert_called_once()
    verification_session.close()


@pytest.mark.unit
def test_stats_refresh_scheduler_reads_interval_from_settings(db_session):
    db_session.add(SystemSettings(stats_refresh_interval_minutes=15))
    db_session.commit()

    scheduler = StatsRefreshScheduler()
    testing_session_local = sessionmaker(
        bind=db_session.get_bind(), autocommit=False, autoflush=False
    )

    with patch(
        "app.services.stats_refresh_scheduler.SessionLocal", testing_session_local
    ):
        assert scheduler._get_refresh_interval_minutes() == 15


@pytest.mark.unit
@pytest.mark.asyncio
async def test_periodic_mqtt_sync_runs_once_before_cancellation():
    sync_state = MagicMock()

    async def stop_after_first_sleep(_seconds):
        raise asyncio.CancelledError

    with patch("app.services.mqtt_sync_scheduler.mqtt_service.sync_state", sync_state):
        with patch(
            "app.services.mqtt_sync_scheduler.asyncio.sleep",
            side_effect=stop_after_first_sleep,
        ):
            with pytest.raises(asyncio.CancelledError):
                await periodic_mqtt_sync(interval_minutes=1)

    sync_state.assert_called_once_with(reason="periodic_scheduler")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_mqtt_sync_scheduler_delegates_to_periodic_sync():
    with patch(
        "app.services.mqtt_sync_scheduler.periodic_mqtt_sync", new=AsyncMock()
    ) as mock_periodic:
        await start_mqtt_sync_scheduler()

    mock_periodic.assert_awaited_once_with(5)
