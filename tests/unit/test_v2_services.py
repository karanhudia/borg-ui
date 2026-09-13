import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Operation,
    Repository,
)
from app.services.v2.check_service import CheckV2Service
from app.services.v2.compact_service import CompactV2Service
from app.services.v2.delete_archive_service import DeleteArchiveV2Service
from app.services.operations.job_facade import resolve_maintenance_job
from tests.utils.operations import seed_job_operation


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
        job = seed_job_operation(
            db_session, "check", repository_id=999, status="running"
        )
        db_session.commit()
        db_session.refresh(job)

        service = CheckV2Service()
        service.log_dir = tmp_path

        with patch("app.services.v2.check_service.SessionLocal", testing_session_local):
            await service.execute_check(job.id, 999)

        verification = testing_session_local()
        refreshed = resolve_maintenance_job(verification, job.id, "check")
        assert refreshed.status == "failed"
        assert "Repository not found" in refreshed.error_message
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_check_skips_terminal_jobs(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = seed_job_operation(
            db_session,
            "check",
            repository_id=borg_v2_repo_for_services.id,
            status="completed",
        )
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
        job = seed_job_operation(
            db_session,
            "check",
            repository_id=borg_v2_repo_for_services.id,
            status="running",
        )
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
        refreshed_job = resolve_maintenance_job(verification, job.id, "check")
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
        assert refreshed_job.started_at is not None
        assert refreshed_repo.last_check is not None
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_check_sets_started_at_on_pending_scheduler_job(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        # The check scheduler creates jobs as pending without started_at; the
        # service must record the execution start itself or the job stays
        # invisible to every started_at-based view (dashboard activity feed).
        job = seed_job_operation(
            db_session,
            "check",
            repository_id=borg_v2_repo_for_services.id,
            status="pending",
        )
        db_session.commit()
        db_session.refresh(job)

        process = FakeProcess(returncode=0, stderr_lines=[])

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
        refreshed_job = resolve_maintenance_job(verification, job.id, "check")
        assert refreshed_job.status == "completed"
        assert refreshed_job.started_at is not None
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_check_does_not_resurrect_a_concurrently_cancelled_job(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        # A cancellation can land between the service's status guard and its
        # start claim; the claim's status predicate must lose that race and
        # never start borg on the cancelled job.
        job = seed_job_operation(
            db_session,
            "check",
            repository_id=borg_v2_repo_for_services.id,
            status="pending",
        )
        db_session.commit()
        db_session.refresh(job)

        from app.services.v2 import check_service as check_service_module

        real_commit_with_retry = check_service_module.commit_with_retry

        async def cancel_then_commit(db, **kwargs):
            if kwargs.get("action") == "borg2_check_start":
                other = testing_session_local()
                other.query(Operation).filter(Operation.id == job.id).update(
                    {"status": "cancelled"}
                )
                other.commit()
                other.close()
            return await real_commit_with_retry(db, **kwargs)

        spawn = MagicMock()
        service = CheckV2Service()
        service.log_dir = tmp_path

        with (
            patch("app.services.v2.check_service.SessionLocal", testing_session_local),
            patch(
                "app.services.v2.check_service.commit_with_retry",
                new=cancel_then_commit,
            ),
            patch(
                "app.services.v2.check_service.asyncio.create_subprocess_exec",
                new=spawn,
            ),
        ):
            await service.execute_check(job.id, borg_v2_repo_for_services.id)

        spawn.assert_not_called()
        verification = testing_session_local()
        refreshed_job = resolve_maintenance_job(verification, job.id, "check")
        assert refreshed_job.status == "cancelled"
        assert refreshed_job.started_at is None
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_check_uses_partial_check_flags_when_max_duration_is_set(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = seed_job_operation(
            db_session,
            "check",
            repository_id=borg_v2_repo_for_services.id,
            status="running",
            max_duration=3600,
        )
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
        refreshed_job = resolve_maintenance_job(verification, job.id, "check")
        assert (
            refreshed_job.progress_message
            == "Partial repository check completed successfully"
        )
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_check_appends_extra_flags(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = seed_job_operation(
            db_session,
            "check",
            repository_id=borg_v2_repo_for_services.id,
            status="running",
            max_duration=0,
            extra_flags="--verify-data --save-space",
        )
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
                return_value=FakeProcess(returncode=0, stderr_lines=[]),
            ) as mock_exec,
        ):
            await service.execute_check(job.id, borg_v2_repo_for_services.id)

        cmd = mock_exec.call_args.args
        assert "--verify-data" in cmd
        assert "--save-space" in cmd

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_check_sets_warning_state(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = seed_job_operation(
            db_session,
            "check",
            repository_id=borg_v2_repo_for_services.id,
            status="running",
        )
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
        refreshed = resolve_maintenance_job(verification, job.id, "check")
        assert refreshed.status == "completed_with_warnings"
        assert "warnings" in refreshed.error_message
        verification.close()


class TestCompactV2Service:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_compact_marks_missing_repository_failed(
        self, db_session, testing_session_local, tmp_path
    ):
        job = seed_job_operation(
            db_session, "compact", repository_id=999, status="running"
        )
        db_session.commit()
        db_session.refresh(job)

        service = CompactV2Service()
        service.log_dir = tmp_path

        with patch(
            "app.services.v2.compact_service.SessionLocal", testing_session_local
        ):
            await service.execute_compact(job.id, 999)

        verification = testing_session_local()
        refreshed = resolve_maintenance_job(verification, job.id, "compact")
        assert refreshed.status == "failed"
        assert "Repository not found" in refreshed.error_message
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_compact_completes_with_two_phase_progress(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = seed_job_operation(
            db_session,
            "compact",
            repository_id=borg_v2_repo_for_services.id,
            status="running",
        )
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
        refreshed = resolve_maintenance_job(verification, job.id, "compact")
        refreshed_repo = (
            verification.query(Repository)
            .filter(Repository.id == borg_v2_repo_for_services.id)
            .first()
        )
        assert refreshed.status == "completed"
        assert refreshed.progress == 100
        assert refreshed.has_logs is True
        assert refreshed.started_at is not None
        assert refreshed_repo.last_compact is not None
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_compact_persists_stats_from_log_json(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        """The compact runs with --stats --info; the INFO statistics lines
        are parsed from the --log-json stream and persisted on the operation
        row the service drives through the facade (#931)."""
        job = Operation(
            repository_id=borg_v2_repo_for_services.id,
            kind="compact",
            category="maintenance",
            status="running",
            trigger="manual",
            priority=10,
            run_id="run-compact",
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)
        # what `BORG_UNITS=raw` prints: exact byte counts
        messages = [
            "Overall statistics, considering all 2 archives in this repository:",
            "Source data size was 1000000 B in 6 files.",
            "Deduplicated size is 500000 B.",
            "Repository size is 502000 B in 6 objects.",
            "Compression factor is 1.00.",
            "Compaction saved 0 B.",
        ]
        lines = [
            json.dumps(
                {
                    "type": "log_message",
                    "levelname": "INFO",
                    "name": "borg.archiver.compact_cmd",
                    "message": m,
                }
            )
            for m in messages
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
                "app.services.v2.compact_service.compact_stats_supported",
                return_value=True,
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
            ) as spawn,
        ):
            await service.execute_compact(job.id, borg_v2_repo_for_services.id)

        cmd = list(spawn.call_args.args)
        assert cmd[cmd.index("compact") + 1 :][:2] == ["--stats", "--info"]
        assert spawn.call_args.kwargs["env"]["BORG_UNITS"] == "raw"
        verification = testing_session_local()
        refreshed = verification.get(Operation, job.id)
        refreshed_repo = (
            verification.query(Repository)
            .filter(Repository.id == borg_v2_repo_for_services.id)
            .first()
        )
        assert refreshed.status == "completed"
        assert refreshed.result["stats"]["repository_size"] == 502_000
        assert refreshed.result["stats"]["source_files"] == 6
        assert refreshed.result["stats"]["size_precision"] == "exact"
        assert refreshed_repo.total_size == "490.23 KB"
        assert refreshed_repo.total_size_source == "compact_stats"
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_compact_keeps_stats_when_finalize_commit_retries(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        """commit_with_retry rolls the session back before it reruns
        prepare(); the finalize closure must restore stats and total_size
        too, or a retried commit drops them (review finding on #931)."""
        job = Operation(
            repository_id=borg_v2_repo_for_services.id,
            kind="compact",
            category="maintenance",
            status="running",
            trigger="manual",
            priority=10,
            run_id="run-compact",
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)
        lines = [
            json.dumps(
                {
                    "type": "log_message",
                    "levelname": "INFO",
                    "name": "borg.archiver.compact_cmd",
                    "message": "Repository size is 502000 B in 6 objects.",
                }
            )
        ]

        from app.services.v2 import compact_service as compact_service_module

        real_commit_with_retry = compact_service_module.commit_with_retry

        async def rollback_then_commit(db, **kwargs):
            if kwargs.get("action") == "borg2_compact_finalize":
                db.rollback()  # what a SQLite lock error does before the retry
            return await real_commit_with_retry(db, **kwargs)

        service = CompactV2Service()
        service.log_dir = tmp_path
        with (
            patch(
                "app.services.v2.compact_service.SessionLocal", testing_session_local
            ),
            patch(
                "app.services.v2.compact_service.commit_with_retry",
                new=rollback_then_commit,
            ),
            patch(
                "app.services.v2.compact_service.resolve_repo_ssh_key_file",
                return_value=None,
            ),
            patch(
                "app.services.v2.compact_service.compact_stats_supported",
                return_value=True,
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
        refreshed = verification.get(Operation, job.id)
        refreshed_repo = (
            verification.query(Repository)
            .filter(Repository.id == borg_v2_repo_for_services.id)
            .first()
        )
        assert refreshed.status == "completed"
        assert refreshed.result["stats"]["repository_size"] == 502_000
        assert refreshed_repo.total_size == "490.23 KB"
        assert refreshed_repo.total_size_source == "compact_stats"
        # the four size columns are restored together after the retry
        assert refreshed_repo.total_size_bytes == 502_000
        assert refreshed_repo.total_size_measured_at is not None
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_compact_sets_started_at_on_pending_scheduler_job(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        # Same contract as the check service: jobs dispatched as pending must
        # get started_at from the service itself.
        job = seed_job_operation(
            db_session,
            "compact",
            repository_id=borg_v2_repo_for_services.id,
            status="pending",
        )
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
                return_value=FakeProcess(returncode=0, stderr_lines=[]),
            ),
        ):
            await service.execute_compact(job.id, borg_v2_repo_for_services.id)

        verification = testing_session_local()
        refreshed = resolve_maintenance_job(verification, job.id, "compact")
        assert refreshed.status == "completed"
        assert refreshed.started_at is not None
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_compact_does_not_resurrect_a_concurrently_cancelled_job(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        # Same race as the check service: a cancellation landing between the
        # status guard and the start claim must win.
        job = seed_job_operation(
            db_session,
            "compact",
            repository_id=borg_v2_repo_for_services.id,
            status="pending",
        )
        db_session.commit()
        db_session.refresh(job)

        from app.services.v2 import compact_service as compact_service_module

        real_commit_with_retry = compact_service_module.commit_with_retry

        async def cancel_then_commit(db, **kwargs):
            if kwargs.get("action") == "borg2_compact_start":
                other = testing_session_local()
                other.query(Operation).filter(Operation.id == job.id).update(
                    {"status": "cancelled"}
                )
                other.commit()
                other.close()
            return await real_commit_with_retry(db, **kwargs)

        spawn = MagicMock()
        service = CompactV2Service()
        service.log_dir = tmp_path

        with (
            patch(
                "app.services.v2.compact_service.SessionLocal", testing_session_local
            ),
            patch(
                "app.services.v2.compact_service.commit_with_retry",
                new=cancel_then_commit,
            ),
            patch(
                "app.services.v2.compact_service.asyncio.create_subprocess_exec",
                new=spawn,
            ),
        ):
            await service.execute_compact(job.id, borg_v2_repo_for_services.id)

        spawn.assert_not_called()
        verification = testing_session_local()
        refreshed = resolve_maintenance_job(verification, job.id, "compact")
        assert refreshed.status == "cancelled"
        assert refreshed.started_at is None
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_compact_sets_warning_state(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = seed_job_operation(
            db_session,
            "compact",
            repository_id=borg_v2_repo_for_services.id,
            status="running",
        )
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
        refreshed = resolve_maintenance_job(verification, job.id, "compact")
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
        job = seed_job_operation(
            db_session,
            "delete_archive",
            repository_id=999,
            archive_name="old",
            status="pending",
        )
        db_session.commit()
        db_session.refresh(job)

        service = DeleteArchiveV2Service()
        service.log_dir = tmp_path

        with patch(
            "app.services.v2.delete_archive_service.SessionLocal", testing_session_local
        ):
            await service.execute_delete(job.id, 999, "old")

        verification = testing_session_local()
        refreshed = resolve_maintenance_job(verification, job.id, "delete_archive")
        assert refreshed.status == "failed"
        assert refreshed.error_message == "Repository not found"
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_delete_fails_when_archive_delete_fails(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = seed_job_operation(
            db_session,
            "delete_archive",
            repository_id=borg_v2_repo_for_services.id,
            repository_path=borg_v2_repo_for_services.path,
            archive_name="old",
            status="pending",
        )
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
        refreshed = resolve_maintenance_job(verification, job.id, "delete_archive")
        assert refreshed.status == "failed"
        assert refreshed.error_message == "cannot delete"
        verification.close()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_delete_completes_even_if_compact_warns(
        self, db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
    ):
        job = seed_job_operation(
            db_session,
            "delete_archive",
            repository_id=borg_v2_repo_for_services.id,
            repository_path=borg_v2_repo_for_services.path,
            archive_name="old",
            status="pending",
        )
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
        refreshed = resolve_maintenance_job(verification, job.id, "delete_archive")
        assert refreshed.status == "completed"
        assert refreshed.progress == 100
        verification.close()


@pytest.mark.unit
def test_compact_log_window_keeps_head_and_tail():
    from app.services.v2.compact_service import _LogWindow

    window = _LogWindow()
    for i in range(_LogWindow.HEAD + _LogWindow.TAIL + 7):
        window.append(f"line {i}")
    lines = window.lines()
    assert lines[0] == "line 0"
    assert lines[_LogWindow.HEAD - 1] == f"line {_LogWindow.HEAD - 1}"
    assert lines[_LogWindow.HEAD] == "... 7 lines omitted ..."
    assert lines[_LogWindow.HEAD + 1] == f"line {_LogWindow.HEAD + 7}"
    assert lines[-1] == f"line {_LogWindow.HEAD + _LogWindow.TAIL + 6}"
    assert len(window) == _LogWindow.HEAD + _LogWindow.TAIL
    # the statistics come last, wherever the newest lines sit
    assert window.last(2) == lines[-2:]

    short = _LogWindow()
    short.append("only")
    assert short.lines() == ["only"] and len(short) == 1
    assert short.last(64) == ["only"]
    assert short.last(0) == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_compact_without_stats_on_a_borg_before_b15(
    db_session, testing_session_local, borg_v2_repo_for_services, tmp_path, monkeypatch
):
    """A configured Borg 2 binary may be any build; before 2.0.0b15 the
    flag fails the whole compact, so it is left out with `--info` and
    `BORG_UNITS=raw`, and no statistics are expected."""
    monkeypatch.delenv("BORG_UNITS", raising=False)
    job = Operation(
        repository_id=borg_v2_repo_for_services.id,
        kind="compact",
        category="maintenance",
        status="running",
        trigger="manual",
        priority=10,
        run_id="run-compact-old",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    service = CompactV2Service()
    service.log_dir = tmp_path
    with (
        patch("app.services.v2.compact_service.SessionLocal", testing_session_local),
        patch(
            "app.services.v2.compact_service.resolve_repo_ssh_key_file",
            return_value=None,
        ),
        patch(
            "app.services.v2.compact_service._get_borg2_binary", return_value="borg2"
        ),
        patch(
            "app.services.v2.compact_service.compact_stats_supported",
            return_value=False,
        ),
        patch(
            "app.services.v2.compact_service._get_process_start_time", return_value=1
        ),
        patch(
            "app.services.v2.compact_service.asyncio.create_subprocess_exec",
            return_value=FakeProcess(returncode=0, stderr_lines=[]),
        ) as spawn,
    ):
        await service.execute_compact(job.id, borg_v2_repo_for_services.id)

    cmd = list(spawn.call_args.args)
    assert "--stats" not in cmd and "--info" not in cmd
    assert "BORG_UNITS" not in spawn.call_args.kwargs["env"]
    verification = testing_session_local()
    refreshed = verification.get(Operation, job.id)
    assert refreshed.status == "completed"
    assert (refreshed.result or {}).get("stats") is None
    verification.close()


@pytest.mark.unit
def test_server_compact_stats_support_is_probed_per_binary_file(monkeypatch):
    from app.core import borg2 as borg2_core

    calls = []

    class _Probe:
        stdout = "borg2 2.0.0b14\n"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _Probe()

    monkeypatch.setattr(borg2_core.subprocess, "run", fake_run)
    monkeypatch.setattr(borg2_core, "_COMPACT_STATS_SUPPORT", {})
    assert borg2_core.compact_stats_supported("/opt/borg2") is False
    assert borg2_core.compact_stats_supported("/opt/borg2") is False
    assert calls == [["/opt/borg2", "--version"]]

    _Probe.stdout = "borg2 2.0.0b24\n"
    monkeypatch.setattr(borg2_core, "_binary_key", lambda binary: (binary, 2, 2))
    assert borg2_core.compact_stats_supported("/opt/borg2") is True

    def failing_run(cmd, **kwargs):
        raise OSError("no such binary")

    monkeypatch.setattr(borg2_core.subprocess, "run", failing_run)
    # unreadable: no flag this time (a wrong flag fails the whole compact)
    assert borg2_core.compact_stats_supported("/opt/other") is False

    # output without a version token: nothing known, no flag, and nothing
    # is remembered, so the next probe decides afresh
    _Probe.stdout = "some wrapper banner\n"
    monkeypatch.setattr(borg2_core.subprocess, "run", fake_run)
    monkeypatch.setattr(borg2_core, "_binary_key", lambda binary: (binary, 3, 3))
    assert borg2_core.compact_stats_supported("/opt/borg2") is False
    _Probe.stdout = "borg2 2.0.0b24\n"
    assert borg2_core.compact_stats_supported("/opt/borg2") is True


class _RunnerContext:
    """The slice of OperationContext the maintenance executor uses, for a row
    the runner has already claimed."""

    def __init__(self, db, operation):
        self.db = db
        self.operation = operation
        self.operation_id = operation.id
        self.repository_id = operation.repository_id
        self.kind = operation.kind
        self.params = dict(operation.params or {})

    def cancelled(self):
        return False

    def log(self, line):
        return None

    async def progress(self, **kwargs):
        return None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_claimed_compact_runs_the_borg2_service(
    db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
):
    """Regression for #1005: a compact the runner claimed (`running` with a
    `started_at`) reaches the Borg 2 service through the maintenance
    executor and runs, instead of the service skipping it as already
    started and the executor reporting `service returned no result`."""
    from app.services.operations.executors import maintenance

    job = _runner_claimed_operation(db_session, borg_v2_repo_for_services, "compact")
    runner_started_at = job.started_at

    service = CompactV2Service()
    service.log_dir = tmp_path
    with (
        patch("app.services.v2.compact_service.compact_v2_service", service),
        patch("app.services.v2.compact_service.SessionLocal", testing_session_local),
        patch(
            "app.services.v2.compact_service.resolve_repo_ssh_key_file",
            return_value=None,
        ),
        patch(
            "app.services.v2.compact_service._get_borg2_binary", return_value="borg2"
        ),
        patch(
            "app.services.v2.compact_service.compact_stats_supported",
            return_value=False,
        ),
        patch(
            "app.services.v2.compact_service._get_process_start_time", return_value=1
        ),
        patch(
            "app.services.v2.compact_service.asyncio.create_subprocess_exec",
            return_value=FakeProcess(returncode=0, stderr_lines=[]),
        ) as spawn,
    ):
        outcome = await maintenance.run_compact(_RunnerContext(db_session, job))

    assert spawn.called, "the service never ran borg"
    assert outcome.status == "completed"
    verification = testing_session_local()
    refreshed = verification.get(Operation, job.id)
    assert refreshed.status == "completed"
    # the start is the service's own, recorded when it claimed the row
    assert refreshed.started_at is not None
    assert refreshed.started_at != runner_started_at
    assert refreshed.completed_at is not None
    verification.close()


class _CommunicatingProcess:
    """The process shape the prune service drives (`communicate`)."""

    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.pid = 4321
        self._out = (stdout, stderr)

    async def communicate(self):
        return self._out

    async def wait(self):
        return self.returncode

    def terminate(self):
        return None

    def kill(self):
        return None


# a fixed past instant: the service's own stamp must differ from it on any
# clock resolution
_RUNNER_CLAIMED_AT = datetime(2026, 1, 1, 12, 0, 0)


def _runner_claimed_operation(db_session, repository, kind, params=None):
    job = Operation(
        repository_id=repository.id,
        kind=kind,
        category="maintenance",
        status="queued",
        trigger="manual",
        priority=10,
        run_id=f"run-claimed-{kind}",
        params=params or {},
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    db_session.query(Operation).filter(
        Operation.id == job.id, Operation.status == "queued"
    ).update(
        {"status": "running", "started_at": _RUNNER_CLAIMED_AT},
        synchronize_session=False,
    )
    db_session.commit()
    db_session.refresh(job)
    assert job.started_at == _RUNNER_CLAIMED_AT
    return job


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_claimed_check_runs_the_borg2_service(
    db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
):
    """Regression for #1005, check: the real Borg 2 check service claims
    and runs a row the runner claimed."""
    from app.services.operations.executors import maintenance

    job = _runner_claimed_operation(db_session, borg_v2_repo_for_services, "check")
    runner_started_at = job.started_at
    service = CheckV2Service()
    service.log_dir = tmp_path
    with (
        patch("app.services.v2.check_service.check_v2_service", service),
        patch("app.services.v2.check_service.SessionLocal", testing_session_local),
        patch(
            "app.services.v2.check_service.resolve_repo_ssh_key_file",
            return_value=None,
        ),
        patch("app.services.v2.check_service._get_borg2_binary", return_value="borg2"),
        patch("app.services.v2.check_service._get_process_start_time", return_value=1),
        patch(
            "app.services.v2.check_service.asyncio.create_subprocess_exec",
            return_value=FakeProcess(returncode=0, stderr_lines=[]),
        ) as spawn,
    ):
        outcome = await maintenance.run_check(_RunnerContext(db_session, job))

    assert spawn.called, "the service never ran borg"
    assert outcome.status == "completed"
    verification = testing_session_local()
    refreshed = verification.get(Operation, job.id)
    assert refreshed.status == "completed"
    assert refreshed.started_at is not None
    assert refreshed.started_at != runner_started_at
    verification.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_claimed_prune_runs_the_borg2_service(
    db_session, testing_session_local, borg_v2_repo_for_services, tmp_path
):
    """Regression for #1005, prune: the real Borg 2 prune service claims and
    runs a row the runner claimed."""
    from unittest.mock import AsyncMock

    from app.services.operations.executors import maintenance
    from app.services.v2.prune_service import PruneV2Service

    job = _runner_claimed_operation(
        db_session, borg_v2_repo_for_services, "prune", params={"keep_daily": 7}
    )
    runner_started_at = job.started_at
    service = PruneV2Service()
    service.log_dir = tmp_path
    spawn = AsyncMock(return_value=_CommunicatingProcess(0, stdout=b"pruned"))
    with (
        patch("app.services.v2.prune_service.prune_v2_service", service),
        patch("app.services.v2.prune_service.SessionLocal", testing_session_local),
        patch("app.services.v2.prune_service._get_borg2_binary", return_value="borg2"),
        patch(
            "app.services.v2.prune_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch(
            "app.services.v2.prune_service.asyncio.create_subprocess_exec", new=spawn
        ),
    ):
        outcome = await maintenance.run_prune(_RunnerContext(db_session, job))

    assert spawn.called, "the service never ran borg"
    assert outcome.status == "completed"
    verification = testing_session_local()
    refreshed = verification.get(Operation, job.id)
    assert refreshed.status == "completed"
    assert refreshed.started_at is not None
    assert refreshed.started_at != runner_started_at
    verification.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runner_claimed_delete_archive_runs_the_borg2_service(
    db_session, testing_session_local, borg_v2_repo_for_services
):
    """Regression for #1005, delete_archive: the real Borg 2 delete service
    claims and runs a row the runner claimed (it is the one claiming
    service without a cancellation poll)."""
    from unittest.mock import AsyncMock

    from app.services.operations.executors import maintenance
    from app.services.v2.delete_archive_service import DeleteArchiveV2Service

    job = _runner_claimed_operation(
        db_session,
        borg_v2_repo_for_services,
        "delete_archive",
        params={"archive_name": "aid:deadbeef"},
    )
    runner_started_at = job.started_at
    service = DeleteArchiveV2Service()
    delete = AsyncMock(return_value={"success": True, "stdout": "", "stderr": ""})
    compact = AsyncMock(return_value={"success": True, "stdout": "", "stderr": ""})
    with (
        patch(
            "app.services.v2.delete_archive_service.delete_archive_v2_service", service
        ),
        patch(
            "app.services.v2.delete_archive_service.SessionLocal", testing_session_local
        ),
        patch(
            "app.services.v2.delete_archive_service.build_repository_borg_env",
            return_value=({}, None),
        ),
        patch("app.services.v2.delete_archive_service.borg2.delete_archive", delete),
        patch("app.services.v2.delete_archive_service.borg2.compact", compact),
    ):
        outcome = await maintenance.run_delete_archive(_RunnerContext(db_session, job))

    assert delete.await_count == 1, "the service never ran borg"
    assert outcome.status == "completed"
    verification = testing_session_local()
    refreshed = verification.get(Operation, job.id)
    assert refreshed.status == "completed"
    assert refreshed.started_at is not None
    assert refreshed.started_at != runner_started_at
    verification.close()
