import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from datetime import datetime, timedelta, timezone

from app.database.models import (
    BackupJob,
    AvailabilityScheduleSkip,
    CheckJob,
    Operation,
    Repository,
    RestoreCheckJob,
    ScheduledJob,
    SystemSettings,
)
from app.services.restore_check_scheduler import RestoreCheckScheduler
from app.services.check_scheduler import run_due_scheduled_checks
from app.services.mqtt_sync_scheduler import (
    periodic_mqtt_sync,
    start_mqtt_sync_scheduler,
)
from app.services.schedule_availability import AvailabilityDecision
from app.api import schedule as schedule_api
from app.api.schedule import check_scheduled_jobs, dispatch_due_scheduled_backups


@pytest.mark.unit
def test_availability_automation_skip_is_durable_and_neutral(db_session):
    job = ScheduledJob(
        name="Availability automation",
        schedule_mode="availability",
        enabled=True,
    )
    db_session.add(job)
    db_session.commit()
    db_session.expire_all()

    now = datetime.now(timezone.utc)
    job.next_run = now + timedelta(minutes=30)
    schedule_api._record_availability_skip(
        db_session,
        job,
        now,
        reason="minimum_interval_not_elapsed",
        detail="Minimum interval after the last successful backup has not elapsed.",
    )
    db_session.commit()

    skip = db_session.query(AvailabilityScheduleSkip).one()
    assert skip.scheduled_job_id == job.id
    assert skip.reason == "minimum_interval_not_elapsed"
    assert (
        skip.detail
        == "Minimum interval after the last successful backup has not elapsed."
    )
    assert skip.next_check_at == job.next_run


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
        check_max_duration=0,
        check_extra_flags="--verify-data",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    # Phase 5: the scheduler enqueues an operation and the runner dispatches it.
    await run_due_scheduled_checks(db_session)

    db_session.refresh(repo)
    assert repo.last_scheduled_check is not None
    assert repo.next_scheduled_check is not None
    operations = db_session.query(Operation).filter(Operation.kind == "check").all()
    assert len(operations) == 1
    op = operations[0]
    assert op.status == "queued"
    assert op.trigger == "schedule"
    assert op.params["max_duration"] == 0
    assert op.params["extra_flags"] == "--verify-data"
    assert op.params["scheduled_check"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_scheduler_snapshot_preserves_agent_routing(db_session):
    # Phase 5: the scheduler enqueues and never routes. BorgRouter still
    # decides agent-vs-server on executor_type, but it does so inside the
    # check executor, which loads the live repository row rather than a
    # snapshot, so an agent repository can no longer be silently run on the
    # server by a lossy copy.
    from app.services.repository_executor import is_agent_executor

    repo = Repository(
        name="Agent Repo",
        path="rest://borg@host/repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
        executor_type="agent",
        borg_version=2,
        check_cron_expression="0 2 * * *",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    await run_due_scheduled_checks(db_session)

    op = db_session.query(Operation).filter(Operation.kind == "check").one()
    assert op.repository_id == repo.id
    assert op.trigger == "schedule"
    db_session.refresh(repo)
    assert is_agent_executor(repo) is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_availability_automation_success_advances_next_check(db_session):
    repo = Repository(
        name="Availability source",
        path="/availability-source",
        encryption="none",
        repository_type="local",
    )
    db_session.add(repo)
    db_session.commit()

    now = datetime(2026, 1, 2, 12, 0)
    job = ScheduledJob(
        name="Availability automation",
        schedule_mode="availability",
        availability_check_interval_minutes=30,
        enabled=True,
        repository_id=repo.id,
        next_run=now - timedelta(minutes=1),
    )
    db_session.add(job)
    db_session.commit()

    def close_background_task(coro):
        coro.close()
        return None

    with (
        patch(
            "app.api.schedule.asyncio.create_task",
            side_effect=close_background_task,
        ) as mock_create_task,
        patch("app.api.schedule._track_scheduled_backup_task"),
        patch(
            "app.api.schedule.repositories_available",
            new=AsyncMock(return_value=AvailabilityDecision(True)),
        ),
    ):
        await dispatch_due_scheduled_backups(db_session, now)

    db_session.refresh(job)
    mock_create_task.assert_called_once()
    assert job.next_run == now + timedelta(minutes=30)


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

    await run_due_scheduled_checks(db_session)

    db_session.refresh(repo)
    assert repo.last_scheduled_check is not None
    assert repo.next_scheduled_check is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_scheduler_uses_repository_check_timezone(db_session):
    repo = Repository(
        name="Repo",
        path="/tmp/repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
        check_cron_expression="0 2 * * *",
        check_timezone="Asia/Kolkata",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    await run_due_scheduled_checks(
        db_session, datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc)
    )

    db_session.refresh(repo)
    assert repo.next_scheduled_check == datetime(2026, 1, 1, 20, 30)


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
    """Inject one transient SQLite lock when a check operation is first marked
    running."""

    # Class level: the runner opens a fresh session per tick, and the point of
    # the test is one transient lock overall, not one per session.
    _injected_running_lock = False

    def commit(self):
        dirty_running_jobs = [
            obj
            for obj in self.dirty
            if isinstance(obj, Operation)
            and obj.kind == "check"
            and getattr(obj, "status", None) == "running"
        ]
        if dirty_running_jobs and not _LockingSession._injected_running_lock:
            _LockingSession._injected_running_lock = True
            raise OperationalError(
                "UPDATE operations SET status='running'",
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

    _LockingSession._injected_running_lock = False
    testing_session_local = sessionmaker(
        bind=db_session.get_bind(),
        autocommit=False,
        autoflush=False,
        class_=_LockingSession,
    )

    fake_processes = [
        _FakeProcess(returncode=0, pid=5000 + idx) for idx in range(len(repos))
    ]

    async def fake_exec(*args, **kwargs):
        return fake_processes.pop(0)

    with (
        patch("app.services.check_service.SessionLocal", testing_session_local),
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
        from app.services.operations.executors import load_default_executors
        from app.services.operations.runner import OperationRunner

        check_service.log_dir = Path(tmp_path)
        scheduler_session = testing_session_local()
        await run_due_scheduled_checks(scheduler_session)
        scheduler_session.close()

        # Phase 5: the runner dispatches what the scheduler enqueued.
        load_default_executors()
        runner = OperationRunner(session_factory=testing_session_local)
        # A transient lock can land on the runner's own dispatch commit.
        # `OperationRunner.start()` logs and keeps looping, so the row stays
        # queued and the next tick picks it up; that is what is reproduced
        # here, rather than letting the error escape a single tick.
        for _ in range(3):
            try:
                await runner.tick()
            except OperationalError:
                continue
        await asyncio.gather(*runner.running_tasks.values())

    verification_session = testing_session_local()
    try:
        operations = (
            verification_session.query(Operation)
            .filter(Operation.kind == "check")
            .order_by(Operation.id)
            .all()
        )
        assert len(operations) == 4
        assert [op.status for op in operations] == ["completed"] * 4
        assert all(op.started_at is not None for op in operations)
        assert all(op.completed_at is not None for op in operations)
        assert not any(op.status == "queued" for op in operations)
    finally:
        verification_session.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_restore_check_scheduler_creates_job_and_updates_next_run(db_session):
    repo = Repository(
        name="Repo",
        path="/tmp/repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
        restore_check_cron_expression="0 4 * * *",
        restore_check_timezone="Asia/Kolkata",
        restore_check_paths='["etc/hostname"]',
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    scheduler = RestoreCheckScheduler()
    testing_session_local = sessionmaker(
        bind=db_session.get_bind(), autocommit=False, autoflush=False
    )

    with patch(
        "app.services.restore_check_scheduler.SessionLocal", testing_session_local
    ):
        with patch(
            "app.services.restore_check_scheduler.start_background_maintenance_job"
        ) as mock_start:
            mock_start.side_effect = lambda db, repo, job_model, **kwargs: (
                RestoreCheckJob(
                    id=84,
                    repository_id=repo.id,
                    status="pending",
                    probe_paths=kwargs["extra_fields"]["probe_paths"],
                    scheduled_restore_check=True,
                )
            )
            await scheduler.run_scheduled_restore_checks()

    verification_session = testing_session_local()
    repo = (
        verification_session.query(Repository).filter(Repository.id == repo.id).first()
    )
    assert repo.last_scheduled_restore_check is not None
    assert repo.next_scheduled_restore_check is not None
    assert repo.next_scheduled_restore_check.hour == 22
    assert repo.next_scheduled_restore_check.minute == 30
    mock_start.assert_called_once()
    verification_session.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_restore_check_scheduler_skips_canary_for_observe_repositories(
    db_session,
):
    repo = Repository(
        name="Observe Repo",
        path="/tmp/observe",
        encryption="none",
        compression="lz4",
        repository_type="local",
        mode="observe",
        restore_check_cron_expression="0 4 * * *",
        restore_check_timezone="Asia/Kolkata",
        restore_check_paths="[]",
        restore_check_full_archive=False,
        restore_check_canary_enabled=True,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    scheduler = RestoreCheckScheduler()
    testing_session_local = sessionmaker(
        bind=db_session.get_bind(), autocommit=False, autoflush=False
    )

    with patch(
        "app.services.restore_check_scheduler.SessionLocal", testing_session_local
    ):
        with patch(
            "app.services.restore_check_scheduler.start_background_maintenance_job"
        ) as mock_start:
            await scheduler.run_scheduled_restore_checks()

    verification_session = testing_session_local()
    repo = (
        verification_session.query(Repository).filter(Repository.id == repo.id).first()
    )
    assert repo.restore_check_canary_enabled is False
    assert repo.next_scheduled_restore_check is not None
    mock_start.assert_not_called()
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
        patch(
            "app.services.backup_plan_execution_service.backup_plan_execution_service.dispatch_due_runs",
            return_value=0,
        ) as mock_plan_dispatch,
        patch(
            "app.api.schedule.run_backup_monitoring_and_reports", new=AsyncMock()
        ) as mock_monitoring,
    ):
        with pytest.raises(RuntimeError, match="stop loop"):
            await check_scheduled_jobs()

    assert mock_checks.await_count == 1
    assert mock_plan_dispatch.call_count == 1
    assert mock_monitoring.await_count == 1


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
async def test_shared_scheduler_counts_active_scheduled_backup_jobs_from_db(
    db_session,
):
    schedule_api._active_scheduled_backup_runs.clear()
    repo = Repository(
        name="Repo",
        path="/tmp/repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
    )
    db_session.add(repo)
    db_session.add(SystemSettings(max_concurrent_scheduled_backups=1))
    db_session.flush()

    active_schedule = ScheduledJob(
        name="Already Running",
        cron_expression="0 2 * * *",
        enabled=True,
        repository_id=repo.id,
        next_run=datetime.now(timezone.utc) + timedelta(days=1),
    )
    due_schedule = ScheduledJob(
        name="Due Schedule",
        cron_expression="0 3 * * *",
        enabled=True,
        repository_id=repo.id,
        next_run=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add_all([active_schedule, due_schedule])
    db_session.flush()
    db_session.add(
        BackupJob(
            repository=repo.path,
            repository_id=repo.id,
            status="pending",
            scheduled_job_id=active_schedule.id,
        )
    )
    db_session.commit()

    with patch.object(
        schedule_api,
        "_dispatch_due_scheduled_job",
        side_effect=["run-1"],
    ) as mock_dispatch:
        await dispatch_due_scheduled_backups(db_session, datetime.now(timezone.utc))

    mock_dispatch.assert_not_called()


@pytest.mark.unit
def test_dispatch_due_scheduled_borg2_job_uses_stable_archive_name(db_session):
    repo = Repository(
        name="Primary Repo",
        path="/tmp/borg2-repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
        borg_version=2,
    )
    db_session.add(repo)
    db_session.flush()
    job = ScheduledJob(
        name="Monthly Backup",
        cron_expression="0 2 * * *",
        enabled=True,
        repository_id=repo.id,
        archive_name_template="{job_name}-{repo_name}-{now}",
        next_run=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(job)
    db_session.commit()

    def discard_background_task(coro):
        coro.close()
        return MagicMock()

    with (
        patch(
            "app.api.schedule.execute_scheduled_backup_with_maintenance",
            new_callable=AsyncMock,
        ) as mock_execute,
        patch(
            "app.api.schedule.asyncio.create_task", side_effect=discard_background_task
        ),
        patch("app.api.schedule._track_scheduled_backup_task"),
    ):
        run_key = schedule_api._dispatch_due_scheduled_job(
            db_session, job, datetime.now(timezone.utc)
        )

    assert run_key is not None
    assert (
        mock_execute.call_args.kwargs["archive_name"] == "Monthly-Backup-Primary-Repo"
    )


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

    await run_due_scheduled_checks(db_session, datetime.utcnow())

    # One legacy scheduled check is already running, so a limit of two leaves
    # room for exactly one more.
    enqueued = db_session.query(Operation).filter(Operation.kind == "check").all()
    assert len(enqueued) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_scheduler_cleans_stale_pending_checks_before_capacity_check(
    db_session,
):
    db_session.add(SystemSettings(max_concurrent_scheduled_checks=1))
    repo = Repository(
        name="Repo",
        path="/tmp/repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
        check_cron_expression="0 2 * * *",
        next_scheduled_check=datetime.utcnow() - timedelta(minutes=1),
    )
    db_session.add(repo)
    db_session.flush()

    stale_job = CheckJob(
        repository_id=repo.id,
        repository_path=repo.path,
        status="pending",
        scheduled_check=True,
        created_at=datetime.utcnow() - timedelta(hours=1),
    )
    db_session.add(stale_job)
    db_session.commit()

    await run_due_scheduled_checks(db_session, datetime.utcnow())

    db_session.refresh(stale_job)
    assert stale_job.status == "failed"
    assert stale_job.completed_at is not None
    # The stale legacy row freed the only slot, so one check is enqueued.
    assert db_session.query(Operation).filter(Operation.kind == "check").count() == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_scheduler_cleans_stale_running_checks_before_capacity_check(
    db_session,
):
    db_session.add(SystemSettings(max_concurrent_scheduled_checks=1))
    repo = Repository(
        name="Repo",
        path="/tmp/repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
        check_cron_expression="0 2 * * *",
        next_scheduled_check=datetime.utcnow() - timedelta(minutes=1),
    )
    db_session.add(repo)
    db_session.flush()

    stale_job = CheckJob(
        repository_id=repo.id,
        repository_path=repo.path,
        status="running",
        scheduled_check=True,
        started_at=datetime.utcnow() - timedelta(hours=1),
        created_at=datetime.utcnow() - timedelta(hours=1),
        process_pid=999999,
        process_start_time=123,
    )
    db_session.add(stale_job)
    db_session.commit()

    await run_due_scheduled_checks(db_session, datetime.utcnow())

    db_session.refresh(stale_job)
    assert stale_job.status == "failed"
    assert stale_job.completed_at is not None
    # The stale legacy row freed the only slot, so one check is enqueued.
    assert db_session.query(Operation).filter(Operation.kind == "check").count() == 1


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
