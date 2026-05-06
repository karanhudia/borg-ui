from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.database.models import Repository, RestoreCheckJob
from app.services.restore_check_service import RestoreCheckService


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
    job = RestoreCheckJob(
        repository_id=restore_check_repository.id,
        repository_path=restore_check_repository.path,
        status="pending",
        full_archive=True,
    )
    db_session.add(job)
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
    refreshed_job = verification.get(RestoreCheckJob, restore_check_job.id)

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
    refreshed_job = verification.get(RestoreCheckJob, restore_check_job.id)
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
    refreshed_job = verification.get(RestoreCheckJob, restore_check_job.id)
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
    job = RestoreCheckJob(
        repository_id=restore_check_repository.id,
        repository_path=restore_check_repository.path,
        status="pending",
        full_archive=False,
    )
    db_session.add(job)
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
    refreshed_job = verification.get(RestoreCheckJob, job.id)
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
    job = RestoreCheckJob(
        repository_id=restore_check_repository.id,
        repository_path=restore_check_repository.path,
        status="pending",
        full_archive=False,
    )
    db_session.add(job)
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
    refreshed_job = verification.get(RestoreCheckJob, job.id)

    assert refreshed_job.status == "needs_backup"
    assert refreshed_job.progress == 100
    assert "Run a backup" in refreshed_job.error_message
    assert refreshed_job.has_logs is True
    assert refreshed_job.log_file_path is not None
    log_text = Path(refreshed_job.log_file_path).read_text(encoding="utf-8")
    assert "Mode: Canary" in log_text
    assert "Run a backup" in log_text
    verification.close()
