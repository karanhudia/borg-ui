import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.database.models import CheckJob, CompactJob, DeleteArchiveJob, Repository
from app.services.v2.check_service import CheckV2Service
from app.services.v2.compact_service import CompactV2Service
from app.services.v2.delete_archive_service import DeleteArchiveV2Service


class AsyncLineStream:
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


class FakeProcess:
    def __init__(self, returncode=0, stderr_lines=None, stdout_lines=None, pid=4321):
        self.returncode = returncode
        self.stderr = AsyncLineStream(stderr_lines or [])
        self.stdout = AsyncLineStream(stdout_lines or [])
        self.pid = pid
        self.terminated = False
        self.killed = False

    async def wait(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


@pytest.fixture
def testing_session_local(db_session):
    return sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)


@pytest.fixture
def borg_v2_repo_for_services(db_session):
    repo = Repository(
        name="Service Repo",
        path="/tmp/service-repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
        borg_version=2,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


class TestCheckV2Service:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_check_marks_missing_repository_failed(
        self, db_session, testing_session_local, tmp_path
    ):
        job = CheckJob(repository_id=999, status="running")
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        service = CheckV2Service()
        service.log_dir = tmp_path

        with patch("app.services.v2.check_service.SessionLocal", testing_session_local):
            await service.execute_check(job.id, 999)

        verification = testing_session_local()
        refreshed = verification.query(CheckJob).filter(CheckJob.id == job.id).first()
        assert refreshed.status == "failed"
        assert "Repository not found" in refreshed.error_message
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_check_skips_terminal_jobs(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = CheckJob(repository_id=borg_v2_repo_for_services.id, status="completed")
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        service = CheckV2Service()
        service.log_dir = tmp_path

        with (
            patch("app.services.v2.check_service.SessionLocal", testing_session_local),
            patch(
                "app.services.v2.check_service.asyncio.create_subprocess_exec"
            ) as mock_exec,
        ):
            await service.execute_check(job.id, borg_v2_repo_for_services.id)

        mock_exec.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_check_completes_and_persists_logs(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = CheckJob(repository_id=borg_v2_repo_for_services.id, status="running")
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        progress_line = json.dumps(
            {
                "type": "progress_percent",
                "message": "Checking segments",
                "operation": 1,
                "current": 3,
                "total": 6,
                "finished": False,
            }
        )
        process = FakeProcess(returncode=0, stderr_lines=[progress_line])

        service = CheckV2Service()
        service.log_dir = tmp_path

        with (
            patch("app.services.v2.check_service.SessionLocal", testing_session_local),
            patch(
                "app.services.v2.check_service.resolve_repo_ssh_key_file",
                return_value=None,
            ),
            patch(
                "app.services.v2.check_service._get_borg2_binary", return_value="borg2"
            ),
            patch(
                "app.services.v2.check_service._get_process_start_time",
                return_value=123,
            ),
            patch(
                "app.services.v2.check_service.asyncio.create_subprocess_exec",
                return_value=process,
            ),
        ):
            await service.execute_check(job.id, borg_v2_repo_for_services.id)

        verification = testing_session_local()
        refreshed_job = (
            verification.query(CheckJob).filter(CheckJob.id == job.id).first()
        )
        refreshed_repo = (
            verification.query(Repository)
            .filter(Repository.id == borg_v2_repo_for_services.id)
            .first()
        )
        assert refreshed_job.status == "completed"
        assert refreshed_job.progress == 100
        assert refreshed_job.has_logs is True
        assert refreshed_job.log_file_path is not None
        assert Path(refreshed_job.log_file_path).exists()
        assert refreshed_repo.last_check is not None
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_check_uses_partial_check_flags_when_max_duration_is_set(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = CheckJob(
            repository_id=borg_v2_repo_for_services.id,
            status="running",
            max_duration=3600,
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        process = FakeProcess(
            returncode=0,
            stderr_lines=[
                json.dumps(
                    {
                        "type": "log_message",
                        "message": "Starting partial repository check",
                    }
                )
            ],
        )

        service = CheckV2Service()
        service.log_dir = tmp_path

        with (
            patch("app.services.v2.check_service.SessionLocal", testing_session_local),
            patch(
                "app.services.v2.check_service.resolve_repo_ssh_key_file",
                return_value=None,
            ),
            patch(
                "app.services.v2.check_service._get_borg2_binary", return_value="borg2"
            ),
            patch(
                "app.services.v2.check_service._get_process_start_time",
                return_value=123,
            ),
            patch(
                "app.services.v2.check_service.asyncio.create_subprocess_exec",
                return_value=process,
            ) as mock_exec,
        ):
            await service.execute_check(job.id, borg_v2_repo_for_services.id)

        cmd = mock_exec.call_args.args
        assert "--repository-only" in cmd
        assert "--max-duration" in cmd
        assert "3600" in cmd

        verification = testing_session_local()
        refreshed_job = (
            verification.query(CheckJob).filter(CheckJob.id == job.id).first()
        )
        assert (
            refreshed_job.progress_message
            == "Partial repository check completed successfully"
        )
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_check_sets_warning_state(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = CheckJob(repository_id=borg_v2_repo_for_services.id, status="running")
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        service = CheckV2Service()
        service.log_dir = tmp_path

        with (
            patch("app.services.v2.check_service.SessionLocal", testing_session_local),
            patch(
                "app.services.v2.check_service.resolve_repo_ssh_key_file",
                return_value=None,
            ),
            patch(
                "app.services.v2.check_service._get_borg2_binary", return_value="borg2"
            ),
            patch(
                "app.services.v2.check_service._get_process_start_time",
                return_value=123,
            ),
            patch(
                "app.services.v2.check_service.asyncio.create_subprocess_exec",
                return_value=FakeProcess(returncode=1, stderr_lines=["warning"]),
            ),
        ):
            await service.execute_check(job.id, borg_v2_repo_for_services.id)

        verification = testing_session_local()
        refreshed = verification.query(CheckJob).filter(CheckJob.id == job.id).first()
        assert refreshed.status == "completed_with_warnings"
        assert "warnings" in refreshed.error_message
        verification.close()


class TestCompactV2Service:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_compact_marks_missing_repository_failed(
        self, db_session, testing_session_local, tmp_path
    ):
        job = CompactJob(repository_id=999, status="running")
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        service = CompactV2Service()
        service.log_dir = tmp_path

        with patch(
            "app.services.v2.compact_service.SessionLocal", testing_session_local
        ):
            await service.execute_compact(job.id, 999)

        verification = testing_session_local()
        refreshed = (
            verification.query(CompactJob).filter(CompactJob.id == job.id).first()
        )
        assert refreshed.status == "failed"
        assert "Repository not found" in refreshed.error_message
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_compact_completes_with_two_phase_progress(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = CompactJob(repository_id=borg_v2_repo_for_services.id, status="running")
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        lines = [
            json.dumps(
                {
                    "type": "progress_percent",
                    "message": "Computing used chunks",
                    "operation": 1,
                    "current": 5,
                    "total": 10,
                    "finished": False,
                }
            ),
            json.dumps(
                {
                    "type": "progress_percent",
                    "message": "Deleting unused objects",
                    "operation": 2,
                    "current": 10,
                    "total": 10,
                    "finished": False,
                }
            ),
        ]

        service = CompactV2Service()
        service.log_dir = tmp_path

        with (
            patch(
                "app.services.v2.compact_service.SessionLocal", testing_session_local
            ),
            patch(
                "app.services.v2.compact_service.resolve_repo_ssh_key_file",
                return_value=None,
            ),
            patch(
                "app.services.v2.compact_service._get_borg2_binary",
                return_value="borg2",
            ),
            patch(
                "app.services.v2.compact_service._get_process_start_time",
                return_value=123,
            ),
            patch(
                "app.services.v2.compact_service.asyncio.create_subprocess_exec",
                return_value=FakeProcess(returncode=0, stderr_lines=lines),
            ),
        ):
            await service.execute_compact(job.id, borg_v2_repo_for_services.id)

        verification = testing_session_local()
        refreshed = (
            verification.query(CompactJob).filter(CompactJob.id == job.id).first()
        )
        refreshed_repo = (
            verification.query(Repository)
            .filter(Repository.id == borg_v2_repo_for_services.id)
            .first()
        )
        assert refreshed.status == "completed"
        assert refreshed.progress == 100
        assert refreshed.has_logs is True
        assert refreshed_repo.last_compact is not None
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_compact_sets_warning_state(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = CompactJob(repository_id=borg_v2_repo_for_services.id, status="running")
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        service = CompactV2Service()
        service.log_dir = tmp_path

        with (
            patch(
                "app.services.v2.compact_service.SessionLocal", testing_session_local
            ),
            patch(
                "app.services.v2.compact_service.resolve_repo_ssh_key_file",
                return_value=None,
            ),
            patch(
                "app.services.v2.compact_service._get_borg2_binary",
                return_value="borg2",
            ),
            patch(
                "app.services.v2.compact_service._get_process_start_time",
                return_value=123,
            ),
            patch(
                "app.services.v2.compact_service.asyncio.create_subprocess_exec",
                return_value=FakeProcess(returncode=100, stderr_lines=["warn"]),
            ),
        ):
            await service.execute_compact(job.id, borg_v2_repo_for_services.id)

        verification = testing_session_local()
        refreshed = (
            verification.query(CompactJob).filter(CompactJob.id == job.id).first()
        )
        refreshed_repo = (
            verification.query(Repository)
            .filter(Repository.id == borg_v2_repo_for_services.id)
            .first()
        )
        assert refreshed.status == "completed_with_warnings"
        assert "warnings" in refreshed.error_message
        assert refreshed_repo.last_compact is not None
        verification.close()


class TestDeleteArchiveV2Service:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_delete_marks_missing_repository_failed(
        self, db_session, testing_session_local, tmp_path
    ):
        job = DeleteArchiveJob(repository_id=999, archive_name="old", status="pending")
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        service = DeleteArchiveV2Service()
        service.log_dir = tmp_path

        with patch(
            "app.services.v2.delete_archive_service.SessionLocal", testing_session_local
        ):
            await service.execute_delete(job.id, 999, "old")

        verification = testing_session_local()
        refreshed = (
            verification.query(DeleteArchiveJob)
            .filter(DeleteArchiveJob.id == job.id)
            .first()
        )
        assert refreshed.status == "failed"
        assert refreshed.error_message == "Repository not found"
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_delete_fails_when_archive_delete_fails(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = DeleteArchiveJob(
            repository_id=borg_v2_repo_for_services.id,
            repository_path=borg_v2_repo_for_services.path,
            archive_name="old",
            status="pending",
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        service = DeleteArchiveV2Service()
        service.log_dir = tmp_path

        with (
            patch(
                "app.services.v2.delete_archive_service.SessionLocal",
                testing_session_local,
            ),
            patch(
                "app.services.v2.delete_archive_service.borg2.delete_archive",
                return_value={"success": False, "stderr": "cannot delete"},
            ),
        ):
            await service.execute_delete(job.id, borg_v2_repo_for_services.id, "old")

        verification = testing_session_local()
        refreshed = (
            verification.query(DeleteArchiveJob)
            .filter(DeleteArchiveJob.id == job.id)
            .first()
        )
        assert refreshed.status == "failed"
        assert refreshed.error_message == "cannot delete"
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_delete_completes_even_if_compact_warns(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = DeleteArchiveJob(
            repository_id=borg_v2_repo_for_services.id,
            repository_path=borg_v2_repo_for_services.path,
            archive_name="old",
            status="pending",
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        service = DeleteArchiveV2Service()
        service.log_dir = tmp_path

        with (
            patch(
                "app.services.v2.delete_archive_service.SessionLocal",
                testing_session_local,
            ),
            patch(
                "app.services.v2.delete_archive_service.borg2.delete_archive",
                return_value={"success": True, "stderr": ""},
            ),
            patch(
                "app.services.v2.delete_archive_service.borg2.compact",
                return_value={"success": False, "stderr": "compact warning"},
            ),
        ):
            await service.execute_delete(job.id, borg_v2_repo_for_services.id, "old")

        verification = testing_session_local()
        refreshed = (
            verification.query(DeleteArchiveJob)
            .filter(DeleteArchiveJob.id == job.id)
            .first()
        )
        assert refreshed.status == "completed"
        assert refreshed.progress == 100
        verification.close()
