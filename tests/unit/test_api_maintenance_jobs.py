from datetime import datetime

import pytest
from fastapi import HTTPException

from app.api.maintenance_jobs import (
    create_maintenance_job,
    create_running_maintenance_job,
    create_started_maintenance_job,
    ensure_no_running_job,
    get_job_with_repository,
    get_repository_jobs,
    read_job_logs,
    start_background_maintenance_job,
    serialize_job_status,
    serialize_job_summary,
)
from app.database.models import CheckJob, Repository


def _create_repo(test_db, name="Repo", path="/repos/main"):
    repo = Repository(name=name, path=path, encryption="none", repository_type="local")
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


@pytest.mark.unit
class TestMaintenanceJobsHelpers:
    def test_ensure_no_running_job_raises_conflict(self, test_db):
        repo = _create_repo(test_db)
        test_db.add(CheckJob(repository_id=repo.id, status="running"))
        test_db.commit()

        with pytest.raises(HTTPException) as exc:
            ensure_no_running_job(
                test_db,
                CheckJob,
                repo.id,
                error_key="backend.errors.repo.checkAlreadyRunning",
            )

        assert exc.value.status_code == 409
        assert exc.value.detail["key"] == "backend.errors.repo.checkAlreadyRunning"

    def test_create_running_maintenance_job_sets_running_fields(self, test_db):
        repo = _create_repo(test_db)

        job = create_running_maintenance_job(test_db, CheckJob, repo)

        assert job.repository_id == repo.id
        assert job.repository_path == repo.path
        assert job.status == "running"
        assert job.progress == 0
        assert job.started_at is not None

    def test_create_started_maintenance_job_sets_running_defaults(self, test_db):
        repo = _create_repo(test_db)

        job = create_started_maintenance_job(test_db, CheckJob, repo, status="running")

        assert job.status == "running"
        assert job.progress == 0
        assert job.started_at is not None

    def test_start_background_maintenance_job_creates_job_and_dispatches(self, test_db):
        repo = _create_repo(test_db)
        dispatched = []

        async def fake_dispatch(job):
            dispatched.append(job.id)

        with pytest.MonkeyPatch.context() as mp:
            scheduled = []
            mp.setattr(
                "app.api.maintenance_jobs.schedule_background_job",
                lambda coro: scheduled.append(coro),
            )

            job = start_background_maintenance_job(
                test_db,
                repo,
                CheckJob,
                error_key="backend.errors.repo.checkAlreadyRunning",
                dispatcher=fake_dispatch,
                extra_fields={"max_duration": 90},
            )

        assert job.status == "pending"
        assert job.max_duration == 90
        assert len(scheduled) == 1
        scheduled[0].close()

    def test_get_job_with_repository_checks_access(self, test_db, admin_user):
        repo = _create_repo(test_db)
        job = create_maintenance_job(
            test_db, CheckJob, repo, extra_fields={"max_duration": 60}
        )

        loaded_job, loaded_repo = get_job_with_repository(
            test_db,
            admin_user,
            CheckJob,
            job.id,
            not_found_key="backend.errors.repo.checkJobNotFound",
        )

        assert loaded_job.id == job.id
        assert loaded_repo.id == repo.id

    def test_get_repository_jobs_returns_empty_for_missing_repo(
        self, test_db, admin_user
    ):
        jobs = get_repository_jobs(test_db, admin_user, 9999, CheckJob, limit=5)

        assert jobs == []

    def test_read_job_logs_prefers_file_and_falls_back_to_legacy_logs(
        self, test_db, tmp_path
    ):
        repo = _create_repo(test_db)
        log_path = tmp_path / "check.log"
        log_path.write_text("from file\n", encoding="utf-8")

        file_job = CheckJob(
            repository_id=repo.id, log_file_path=str(log_path), logs="legacy"
        )
        legacy_job = CheckJob(repository_id=repo.id, logs="legacy only")

        assert read_job_logs(file_job) == "from file\n"
        assert read_job_logs(legacy_job) == "legacy only"

    def test_serialize_job_helpers_include_requested_fields(self, test_db):
        repo = _create_repo(test_db)
        job = CheckJob(
            repository_id=repo.id,
            status="completed",
            started_at=datetime(2026, 1, 1, 12, 0, 0),
            completed_at=datetime(2026, 1, 1, 12, 5, 0),
            progress=100,
            progress_message="done",
            error_message=None,
            logs="line 1",
            has_logs=True,
        )

        status_payload = serialize_job_status(
            job,
            include_progress=True,
            include_logs=True,
            include_has_logs=True,
        )
        summary_payload = serialize_job_summary(
            job,
            include_progress=True,
            include_has_logs=True,
        )

        assert status_payload["progress"] == 100
        assert status_payload["progress_message"] == "done"
        assert status_payload["logs"] == "line 1"
        assert status_payload["has_logs"] is True
        assert summary_payload["progress"] == 100
        assert summary_payload["has_logs"] is True
