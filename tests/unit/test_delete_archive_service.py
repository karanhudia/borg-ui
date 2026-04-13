import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, mock_open, patch

import pytest

from app.database.models import DeleteArchiveJob, Repository
from app.services.delete_archive_service import (
    DeleteArchiveService,
    get_process_start_time,
)


class AsyncLineStream:
    def __init__(self, lines):
        self._lines = list(lines)

    def __aiter__(self):
        async def generator():
            for line in self._lines:
                yield line

        return generator()


class FakeProcess:
    def __init__(self, pid=1234, returncode=0, stderr_lines=None):
        self.pid = pid
        self.returncode = returncode
        self.stderr = AsyncLineStream(stderr_lines or [])

    async def wait(self):
        await asyncio.sleep(0)
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


@pytest.fixture
def delete_service(tmp_path):
    with patch("app.services.delete_archive_service.settings") as mock_settings:
        mock_settings.data_dir = str(tmp_path)
        yield DeleteArchiveService()


@pytest.mark.unit
def test_get_process_start_time_parses_proc_stat():
    proc_stat = (
        "1234 (borg delete) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 98765 20"
    )
    with patch("builtins.open", mock_open(read_data=proc_stat)):
        assert get_process_start_time(1234) == 98765


@pytest.mark.unit
def test_get_process_start_time_returns_zero_on_error():
    with patch("builtins.open", side_effect=OSError("missing")):
        assert get_process_start_time(999) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_delete_marks_missing_repository_failed(
    delete_service, db_session_commit
):
    job = DeleteArchiveJob(repository_id=999, archive_name="daily-1", status="pending")
    db_session_commit.add(job)
    db_session_commit.commit()
    db_session_commit.refresh(job)
    job_id = job.id

    with patch(
        "app.services.delete_archive_service.SessionLocal",
        return_value=db_session_commit,
    ):
        await delete_service.execute_delete(job_id, 999, "daily-1")

    refreshed = (
        db_session_commit.query(DeleteArchiveJob)
        .filter(DeleteArchiveJob.id == job_id)
        .first()
    )
    assert refreshed.status == "failed"
    assert "Repository not found" in refreshed.error_message
    assert refreshed.completed_at is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_delete_completes_and_persists_logs(
    delete_service, db_session_commit
):
    repo = Repository(
        name="Repo", path="/tmp/repo", encryption="none", repository_type="local"
    )
    db_session_commit.add(repo)
    db_session_commit.commit()
    db_session_commit.refresh(repo)

    job = DeleteArchiveJob(
        repository_id=repo.id, archive_name="daily-1", status="pending"
    )
    db_session_commit.add(job)
    db_session_commit.commit()
    db_session_commit.refresh(job)
    job_id = job.id

    process = FakeProcess(returncode=0, stderr_lines=[b"deleting archive\n", b"done\n"])

    with (
        patch(
            "app.services.delete_archive_service.SessionLocal",
            return_value=db_session_commit,
        ),
        patch(
            "app.services.delete_archive_service.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ),
        patch(
            "app.services.delete_archive_service.get_process_start_time",
            return_value=555,
        ),
    ):
        await delete_service.execute_delete(job_id, repo.id, "daily-1")

    refreshed = (
        db_session_commit.query(DeleteArchiveJob)
        .filter(DeleteArchiveJob.id == job_id)
        .first()
    )
    assert refreshed.status == "completed"
    assert refreshed.progress == 100
    assert refreshed.has_logs is True
    assert refreshed.log_file_path is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_delete_marks_warning_exit_codes(
    delete_service, db_session_commit
):
    repo = Repository(
        name="Repo", path="/tmp/repo", encryption="none", repository_type="local"
    )
    db_session_commit.add(repo)
    db_session_commit.commit()
    db_session_commit.refresh(repo)

    job = DeleteArchiveJob(
        repository_id=repo.id, archive_name="daily-1", status="pending"
    )
    db_session_commit.add(job)
    db_session_commit.commit()
    db_session_commit.refresh(job)
    job_id = job.id

    process = FakeProcess(returncode=100, stderr_lines=[b"warning line\n"])

    with (
        patch(
            "app.services.delete_archive_service.SessionLocal",
            return_value=db_session_commit,
        ),
        patch(
            "app.services.delete_archive_service.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ),
        patch(
            "app.services.delete_archive_service.get_process_start_time",
            return_value=123,
        ),
    ):
        await delete_service.execute_delete(job_id, repo.id, "daily-1")

    refreshed = (
        db_session_commit.query(DeleteArchiveJob)
        .filter(DeleteArchiveJob.id == job_id)
        .first()
    )
    assert refreshed.status == "completed_with_warnings"
    assert "exit code 100" in refreshed.error_message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_delete_marks_running_job_cancelled(delete_service, db_session):
    job = DeleteArchiveJob(
        repository_id=1,
        archive_name="daily-1",
        status="running",
        started_at=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    await delete_service.cancel_delete(job.id, db_session)

    db_session.refresh(job)
    assert job.status == "cancelled"
