from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.database.models import Repository
from app.services.restore_check_service import RestoreCheckService
from app.services.operations.job_facade import resolve_maintenance_job
from tests.utils.operations import seed_job_operation


class FakeRestoreCheckProcess:
    def __init__(
        self,
        returncode: int,
        stdout: bytes = b"",
        stderr: bytes = b"",
        pid: int = 4321,
    ):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.pid = pid

    async def communicate(self):
        return self.stdout, self.stderr


class FakeBorgRouter:
    def __init__(self, repository):
        self.repository = repository

    async def list_archives(self, env=None):
        return [{"name": "archive-1", "start": "2026-01-02T00:00:00Z"}]

    def build_restore_extract_command(
        self,
        repository_path,
        archive_name,
        paths,
        remote_path=None,
        bypass_lock=False,
    ):
        return ["borg", "extract", f"{repository_path}::{archive_name}", *paths]


class FakeEmptyArchiveBorgRouter(FakeBorgRouter):
    async def list_archives(self, env=None):
        return []


@pytest.fixture
def testing_session_local(db_session):
    return sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)


@pytest.fixture
def restore_check_repository(db_session):
    repo = Repository(
        name="Restore Check Repo",
        path="/tmp/restore-check-repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
        bypass_lock=True,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


@pytest.fixture
def restore_check_job(db_session, restore_check_repository):
    job = seed_job_operation(
        db_session,
        "restore_check",
        repository_id=restore_check_repository.id,
        repository_path=restore_check_repository.path,
        status="pending",
        full_archive=True,
    )
    db_session.commit()
    db_session.refresh(job)
    return job


@pytest.mark.unit
@pytest.mark.asyncio
async def test_restore_check_success_without_borg_output_saves_summary_logs(
    testing_session_local,
    restore_check_repository,
    restore_check_job,
):
    service = RestoreCheckService()
    process = FakeRestoreCheckProcess(returncode=0)

    with (
        patch("app.services.restore_check_service.SessionLocal", testing_session_local),
        patch("app.services.restore_check_service.BorgRouter", FakeBorgRouter),
        patch(
            "app.services.restore_check_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch("app.services.restore_check_service.cleanup_temp_key_file"),
        patch(
            "app.services.restore_check_service.get_process_start_time",
            return_value=123456,
        ),
        patch(
            "app.services.restore_check_service.asyncio.create_subprocess_exec",
            return_value=process,
        ),
    ):
        await service.execute_restore_check(
            restore_check_job.id, restore_check_repository.id
        )

    verification = testing_session_local()
    refreshed_job = resolve_maintenance_job(
        verification, restore_check_job.id, "restore_check"
    )

    assert refreshed_job.status == "completed"
    assert refreshed_job.has_logs is True
    assert refreshed_job.log_file_path is not None
    log_text = Path(refreshed_job.log_file_path).read_text(encoding="utf-8")
    assert "Archive: archive-1" in log_text
    assert "Mode: Full Archive" in log_text
    assert "Restore verification completed successfully" in log_text
    verification.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_restore_check_warning_exit_completes_with_warnings(
    testing_session_local,
    restore_check_repository,
    restore_check_job,
):
    service = RestoreCheckService()
    process = FakeRestoreCheckProcess(
        returncode=1,
        stderr=(
            b'{"type":"log_message","levelname":"WARNING","message":"when setting extended '
            b'attribute com.apple.quarantine: [Errno 95] Operation not supported"}\n'
        ),
    )

    with (
        patch("app.services.restore_check_service.SessionLocal", testing_session_local),
        patch("app.services.restore_check_service.BorgRouter", FakeBorgRouter),
        patch(
            "app.services.restore_check_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch("app.services.restore_check_service.cleanup_temp_key_file"),
        patch(
            "app.services.restore_check_service.get_process_start_time",
            return_value=123456,
        ),
        patch(
            "app.services.restore_check_service.asyncio.create_subprocess_exec",
            return_value=process,
        ),
    ):
        await service.execute_restore_check(
            restore_check_job.id, restore_check_repository.id
        )

    verification = testing_session_local()
    refreshed_job = resolve_maintenance_job(
        verification, restore_check_job.id, "restore_check"
    )
    refreshed_repo = verification.get(Repository, restore_check_repository.id)

    assert refreshed_job.status == "completed_with_warnings"
    assert refreshed_job.progress == 100
    assert "completed with warnings" in refreshed_job.error_message
    assert refreshed_job.has_logs is True
    assert Path(refreshed_job.log_file_path).exists()
    assert refreshed_repo.last_restore_check is not None
    verification.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_restore_check_error_exit_still_fails(
    testing_session_local,
    restore_check_repository,
    restore_check_job,
):
    service = RestoreCheckService()
    process = FakeRestoreCheckProcess(returncode=2, stderr=b"extract failed\n")

    with (
        patch("app.services.restore_check_service.SessionLocal", testing_session_local),
        patch("app.services.restore_check_service.BorgRouter", FakeBorgRouter),
        patch(
            "app.services.restore_check_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch("app.services.restore_check_service.cleanup_temp_key_file"),
        patch(
            "app.services.restore_check_service.get_process_start_time",
            return_value=123456,
        ),
        patch(
            "app.services.restore_check_service.asyncio.create_subprocess_exec",
            return_value=process,
        ),
    ):
        await service.execute_restore_check(
            restore_check_job.id, restore_check_repository.id
        )

    verification = testing_session_local()
    refreshed_job = resolve_maintenance_job(
        verification, restore_check_job.id, "restore_check"
    )
    refreshed_repo = verification.get(Repository, restore_check_repository.id)

    assert refreshed_job.status == "failed"
    assert refreshed_job.progress == 100
    assert "exit code 2" in refreshed_job.error_message
    assert refreshed_repo.last_restore_check is None
    verification.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_restore_check_success_sends_notification(
    testing_session_local,
    restore_check_repository,
    restore_check_job,
):
    service = RestoreCheckService()
    process = FakeRestoreCheckProcess(returncode=0)

    with (
        patch("app.services.restore_check_service.SessionLocal", testing_session_local),
        patch("app.services.restore_check_service.BorgRouter", FakeBorgRouter),
        patch(
            "app.services.restore_check_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch("app.services.restore_check_service.cleanup_temp_key_file"),
        patch(
            "app.services.restore_check_service.get_process_start_time",
            return_value=123456,
        ),
        patch(
            "app.services.restore_check_service.asyncio.create_subprocess_exec",
            return_value=process,
        ),
        patch(
            "app.services.restore_check_service.NotificationService.send_restore_check_completion",
            new_callable=AsyncMock,
        ) as notify_mock,
    ):
        await service.execute_restore_check(
            restore_check_job.id, restore_check_repository.id
        )

    notify_mock.assert_awaited_once()
    call = notify_mock.await_args.kwargs
    assert call["repository_name"] == restore_check_repository.name
    assert call["status"] == "completed"
    assert call["mode"] == "full_archive"
    assert call["archive_name"] == "archive-1"
    assert call["check_type"] == "manual"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_restore_check_canary_missing_payload_needs_backup_and_saves_logs(
    testing_session_local,
    db_session,
    restore_check_repository,
):
    job = seed_job_operation(
        db_session,
        "restore_check",
        repository_id=restore_check_repository.id,
        repository_path=restore_check_repository.path,
        status="pending",
        full_archive=False,
    )
    db_session.commit()
    db_session.refresh(job)

    service = RestoreCheckService()
    process = FakeRestoreCheckProcess(returncode=0, stderr=b"extract completed\n")

    with (
        patch("app.services.restore_check_service.SessionLocal", testing_session_local),
        patch("app.services.restore_check_service.BorgRouter", FakeBorgRouter),
        patch(
            "app.services.restore_check_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch("app.services.restore_check_service.cleanup_temp_key_file"),
        patch(
            "app.services.restore_check_service.get_process_start_time",
            return_value=123456,
        ),
        patch(
            "app.services.restore_check_service.asyncio.create_subprocess_exec",
            return_value=process,
        ),
    ):
        await service.execute_restore_check(job.id, restore_check_repository.id)

    verification = testing_session_local()
    refreshed_job = resolve_maintenance_job(verification, job.id, "restore_check")
    refreshed_repo = verification.get(Repository, restore_check_repository.id)

    assert refreshed_job.status == "needs_backup"
    assert refreshed_job.progress == 100
    assert "Borg UI canary file was not found" in refreshed_job.error_message
    assert refreshed_job.has_logs is True
    assert refreshed_job.log_file_path is not None
    log_text = Path(refreshed_job.log_file_path).read_text(encoding="utf-8")
    assert "extract completed" in log_text
    assert "Borg UI canary file was not found" in log_text
    assert refreshed_repo.last_restore_check is None
    verification.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_restore_check_canary_without_archives_saves_actionable_logs(
    testing_session_local,
    db_session,
    restore_check_repository,
):
    job = seed_job_operation(
        db_session,
        "restore_check",
        repository_id=restore_check_repository.id,
        repository_path=restore_check_repository.path,
        status="pending",
        full_archive=False,
    )
    db_session.commit()
    db_session.refresh(job)

    service = RestoreCheckService()

    with (
        patch("app.services.restore_check_service.SessionLocal", testing_session_local),
        patch(
            "app.services.restore_check_service.BorgRouter",
            FakeEmptyArchiveBorgRouter,
        ),
        patch(
            "app.services.restore_check_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch("app.services.restore_check_service.cleanup_temp_key_file"),
    ):
        await service.execute_restore_check(job.id, restore_check_repository.id)

    verification = testing_session_local()
    refreshed_job = resolve_maintenance_job(verification, job.id, "restore_check")

    assert refreshed_job.status == "needs_backup"
    assert refreshed_job.progress == 100
    assert "Run a backup" in refreshed_job.error_message
    assert refreshed_job.has_logs is True
    assert refreshed_job.log_file_path is not None
    log_text = Path(refreshed_job.log_file_path).read_text(encoding="utf-8")
    assert "Mode: Canary" in log_text
    assert "Run a backup" in log_text
    verification.close()


class FakeBorg2SeriesRouter(FakeBorgRouter):
    """A Borg 2 series: every archive shares the name, ids differ."""

    captured_extract_archives: list[str] = []

    async def list_archives(self, env=None):
        return [
            {
                "name": "myplan-daily",
                "id": "ab12cd34ef56ab12",
                "start": "2026-01-01T00:00:00Z",
            },
            {
                "name": "myplan-daily",
                "id": "ef56gh78ab12cd34",
                "start": "2026-01-02T00:00:00Z",
            },
        ]

    def build_restore_extract_command(
        self,
        repository_path,
        archive_name,
        paths,
        remote_path=None,
        bypass_lock=False,
    ):
        FakeBorg2SeriesRouter.captured_extract_archives.append(archive_name)
        return ["borg2", "extract", archive_name, *paths]


class TestArchiveSelector:
    def test_borg2_series_archives_are_addressed_by_aid(self):
        from app.services.restore_check_service import _get_archive_selector

        repo = Repository(borg_version=2)
        archive = {"name": "myplan-daily", "id": "ab12cd34ef56ab12"}

        assert _get_archive_selector(archive, repo) == "aid:ab12cd34ef56ab12"

    def test_borg2_without_id_falls_back_to_the_name(self):
        from app.services.restore_check_service import _get_archive_selector

        repo = Repository(borg_version=2)

        assert _get_archive_selector({"name": "solo"}, repo) == "solo"

    def test_borg1_keeps_the_unique_name(self):
        from app.services.restore_check_service import _get_archive_selector

        repo = Repository(borg_version=1)
        archive = {"name": "backup-2026-01-01", "id": "ab12cd34ef56ab12"}

        assert _get_archive_selector(archive, repo) == "backup-2026-01-01"

    def test_string_entries_pass_through(self):
        from app.services.restore_check_service import _get_archive_selector

        assert (
            _get_archive_selector("backup-1", Repository(borg_version=2)) == "backup-1"
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_borg2_restore_check_extracts_by_aid_selector(
    db_session, testing_session_local
):
    # A series name matches every archive in the series - borg refuses the
    # extract (#863). The check must address the LATEST archive by aid:.
    repo = Repository(
        name="Borg2 Series Repo",
        path="/tmp/restore-check-b2",
        encryption="none",
        compression="lz4",
        repository_type="local",
        bypass_lock=True,
        borg_version=2,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    job = seed_job_operation(
        db_session,
        "restore_check",
        repository_id=repo.id,
        repository_path=repo.path,
        status="pending",
        full_archive=True,
    )
    db_session.commit()
    db_session.refresh(job)

    service = RestoreCheckService()
    process = FakeRestoreCheckProcess(returncode=0)
    FakeBorg2SeriesRouter.captured_extract_archives = []

    with (
        patch("app.services.restore_check_service.SessionLocal", testing_session_local),
        patch("app.services.restore_check_service.BorgRouter", FakeBorg2SeriesRouter),
        patch(
            "app.services.restore_check_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch("app.services.restore_check_service.cleanup_temp_key_file"),
        patch(
            "app.services.restore_check_service.get_process_start_time",
            return_value=123456,
        ),
        patch(
            "app.services.restore_check_service.asyncio.create_subprocess_exec",
            return_value=process,
        ),
    ):
        await service.execute_restore_check(job.id, repo.id)

    verification = testing_session_local()
    refreshed_job = resolve_maintenance_job(verification, job.id, "restore_check")

    # The newest archive of the series, addressed by id - never by the name.
    assert FakeBorg2SeriesRouter.captured_extract_archives == ["aid:ef56gh78ab12cd34"]
    assert refreshed_job.status == "completed"
    # The job row keeps the human-readable series name for display.
    assert refreshed_job.archive_name == "myplan-daily"
    verification.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancelled_canary_check_does_not_start_the_legacy_extract(
    testing_session_local,
    db_session,
    restore_check_repository,
):
    """Killing the first extract makes it fail, which would start the
    legacy-path extract after the cancel watcher has already returned."""
    job = seed_job_operation(
        db_session,
        "restore_check",
        repository_id=restore_check_repository.id,
        repository_path=restore_check_repository.path,
        status="pending",
        full_archive=False,
    )
    db_session.commit()
    db_session.refresh(job)

    service = RestoreCheckService()
    extracts = []

    async def killed_extract(*args, **kwargs):
        extracts.append(args)
        # the cancel lands while the first extract runs and kills it
        service.cancelled_jobs.add(job.id)
        return FakeRestoreCheckProcess(returncode=-15)

    with (
        patch("app.services.restore_check_service.SessionLocal", testing_session_local),
        patch("app.services.restore_check_service.BorgRouter", FakeBorgRouter),
        patch(
            "app.services.restore_check_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch("app.services.restore_check_service.cleanup_temp_key_file"),
        patch(
            "app.services.restore_check_service.get_process_start_time",
            return_value=123456,
        ),
        patch(
            "app.services.restore_check_service.asyncio.create_subprocess_exec",
            side_effect=killed_extract,
        ),
    ):
        await service.execute_restore_check(job.id, restore_check_repository.id)

    assert len(extracts) == 1
    assert job.id not in service.cancelled_jobs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancelled_check_whose_extract_warned_is_not_a_success(
    testing_session_local,
    db_session,
    restore_check_repository,
):
    """The cancel lands as the first extract ends with a warning and no
    canary: the check verified nothing, so it neither completes nor
    records a restore check on the repository."""
    job = seed_job_operation(
        db_session,
        "restore_check",
        repository_id=restore_check_repository.id,
        repository_path=restore_check_repository.path,
        status="pending",
        full_archive=False,
    )
    db_session.commit()
    db_session.refresh(job)

    service = RestoreCheckService()

    async def warned_extract(*args, **kwargs):
        service.cancelled_jobs.add(job.id)
        return FakeRestoreCheckProcess(returncode=1)

    with (
        patch("app.services.restore_check_service.SessionLocal", testing_session_local),
        patch("app.services.restore_check_service.BorgRouter", FakeBorgRouter),
        patch(
            "app.services.restore_check_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch("app.services.restore_check_service.cleanup_temp_key_file"),
        patch(
            "app.services.restore_check_service.get_process_start_time",
            return_value=123456,
        ),
        patch(
            "app.services.restore_check_service.asyncio.create_subprocess_exec",
            side_effect=warned_extract,
        ),
    ):
        await service.execute_restore_check(job.id, restore_check_repository.id)

    verification = testing_session_local()
    refreshed_job = resolve_maintenance_job(verification, job.id, "restore_check")
    refreshed_repo = verification.get(Repository, restore_check_repository.id)
    assert refreshed_job.status == "cancelled"
    assert refreshed_job.error_message == "Restore verification cancelled"
    assert refreshed_repo.last_restore_check is None
    verification.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_agent_keepalive_holds_off_the_stall_timeout(db_session, monkeypatch):
    """A silent extract reports only an empty progress (agent 0.1.7), which
    moves nothing but `updated_at`; it is not a stalled one."""
    import asyncio
    from datetime import datetime, timedelta

    from app.database.models import AgentJob
    from app.services import restore_check_service as module

    from app.core.security import get_password_hash
    from app.database.models import AgentMachine

    agent_machine = AgentMachine(
        name="keepalive-agent",
        agent_id="agt_keepalive",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=[],
    )
    db_session.add(agent_machine)
    db_session.commit()
    job = AgentJob(
        agent_machine_id=agent_machine.id,
        job_type="repository",
        status="running",
        payload={"job_kind": "repository.restore"},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()
    monkeypatch.setattr(module, "_AGENT_OP_STALL_TIMEOUT_SECONDS", 0.3)

    async def silent_agent():
        stamp = datetime.utcnow()
        for _ in range(8):
            await asyncio.sleep(0.1)
            stamp += timedelta(seconds=1)
            db_session.query(AgentJob).filter(AgentJob.id == job.id).update(
                {AgentJob.updated_at: stamp}, synchronize_session=False
            )
            db_session.commit()
        db_session.query(AgentJob).filter(AgentJob.id == job.id).update(
            {AgentJob.status: "completed", AgentJob.result: {"verified": True}},
            synchronize_session=False,
        )
        db_session.commit()

    agent = asyncio.create_task(silent_agent())
    result = await RestoreCheckService()._await_agent_operation(
        db_session, job.id, poll_interval_seconds=0.05
    )
    await agent

    assert result == {"verified": True}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_check_cancelled_before_its_first_extract_runs_none(
    testing_session_local,
    db_session,
    restore_check_repository,
):
    """The cancel may land while the check lists archives, before any
    process is tracked; no extract may start after it."""
    job = seed_job_operation(
        db_session,
        "restore_check",
        repository_id=restore_check_repository.id,
        repository_path=restore_check_repository.path,
        status="pending",
        full_archive=False,
    )
    db_session.commit()
    db_session.refresh(job)
    service = RestoreCheckService()

    class CancelWhileListing(FakeBorgRouter):
        async def list_archives(self, env=None):
            await service.cancel_restore_check(job.id)
            return await super().list_archives(env=env)

    extract = AsyncMock()
    with (
        patch("app.services.restore_check_service.SessionLocal", testing_session_local),
        patch("app.services.restore_check_service.BorgRouter", CancelWhileListing),
        patch(
            "app.services.restore_check_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch("app.services.restore_check_service.cleanup_temp_key_file"),
        patch(
            "app.services.restore_check_service.asyncio.create_subprocess_exec",
            extract,
        ),
    ):
        await service.execute_restore_check(job.id, restore_check_repository.id)

    extract.assert_not_awaited()
    assert service.cancelled_jobs == set()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_cancel_for_a_check_not_running_is_not_remembered():
    service = RestoreCheckService()

    await service.cancel_restore_check(4242)

    assert service.cancelled_jobs == set()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capabilities, status, message, expected",
    [
        # the agent stops Borg on a cancel: it is asked to, and the stop is
        # marked as the server's
        (["jobs.cancel"], "running", None, ("cancel_requested", "abandoned", 1)),
        # a user's cancel is already on its way: only sent again, its
        # provenance kept
        (
            ["jobs.cancel"],
            "cancel_requested",
            "Cancelled by user",
            ("cancel_requested", "Cancelled by user", 1),
        ),
        # an agent before `jobs.cancel` would report `canceled` at once and
        # let a silent Borg run on: its job stays live, nothing is sent
        ([], "running", None, ("running", None, 0)),
    ],
)
async def test_keepalives_alone_do_not_hold_a_job_forever(
    db_session, monkeypatch, capabilities, status, message, expected
):
    """A hung but live process keeps reporting keepalives; without progress
    the wait still ends."""
    import asyncio
    from datetime import datetime, timedelta

    from fastapi import HTTPException

    from app.core.security import get_password_hash
    from app.database.models import AgentJob, AgentMachine
    from app.services import restore_check_service as module

    agent_machine = AgentMachine(
        name="hung-agent",
        agent_id="agt_hung",
        token_hash=get_password_hash("secret"),
        token_prefix="secret",
        status="online",
        capabilities=capabilities,
    )
    db_session.add(agent_machine)
    db_session.commit()
    job = AgentJob(
        agent_machine_id=agent_machine.id,
        job_type="repository",
        status=status,
        error_message=message,
        payload={"job_kind": "repository.restore"},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()
    monkeypatch.setattr(module, "_AGENT_OP_STALL_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(module, "_AGENT_OP_NO_PROGRESS_MAX_SECONDS", 0.5)
    stop = asyncio.Event()

    async def keepalives():
        stamp = datetime.utcnow()
        while not stop.is_set():
            await asyncio.sleep(0.1)
            stamp += timedelta(seconds=1)
            db_session.query(AgentJob).filter(AgentJob.id == job.id).update(
                {AgentJob.updated_at: stamp}, synchronize_session=False
            )
            db_session.commit()

    agent = asyncio.create_task(keepalives())
    dispatch = AsyncMock(return_value=True)
    try:
        with (
            patch(
                "app.services.agent_job_dispatcher.dispatch_agent_cancel_if_connected",
                dispatch,
            ),
            pytest.raises(HTTPException) as timed_out,
        ):
            await RestoreCheckService()._await_agent_operation(
                db_session, job.id, poll_interval_seconds=0.05
            )
    finally:
        stop.set()
        await agent

    assert timed_out.value.status_code == 504
    # the agent is asked to stop rather than left running on a failed row,
    # and the stop is marked as the server's, not a user's cancel
    from app.services.operations.executors.maintenance import (
        AGENT_WAIT_ABANDONED_MESSAGE,
    )

    db_session.expire_all()
    stopped = db_session.get(AgentJob, job.id)
    want_status, want_message, dispatched = expected
    if want_message == "abandoned":
        want_message = AGENT_WAIT_ABANDONED_MESSAGE
    assert stopped.status == want_status
    assert stopped.error_message == want_message
    assert dispatch.await_count == dispatched
