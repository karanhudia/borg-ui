from datetime import datetime

import pytest

from app.api.maintenance_jobs import (
    read_job_logs,
    serialize_job_status,
    serialize_job_summary,
)
from app.database.models import Operation, Repository
from app.services.operations.job_facade import MaintenanceJobFacade
from tests.utils.operations import seed_job_operation


def _create_repo(test_db, name="Repo", path="/repos/main"):
    repo = Repository(name=name, path=path, encryption="none", repository_type="local")
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


@pytest.mark.unit
class TestMaintenanceJobsHelpers:
    def test_read_job_logs_prefers_file_and_falls_back_to_legacy_logs(
        self, test_db, tmp_path
    ):
        repo = _create_repo(test_db)
        log_path = tmp_path / "check.log"
        log_path.write_text("from file\n", encoding="utf-8")

        file_job = seed_job_operation(
            test_db,
            "check",
            repository_id=repo.id,
            log_file_path=str(log_path),
            logs="legacy",
        )
        legacy_job = seed_job_operation(
            test_db, "check", repository_id=repo.id, logs="legacy only"
        )

        assert read_job_logs(file_job, log_save_policy="all_jobs") == "from file\n"
        assert read_job_logs(legacy_job, log_save_policy="all_jobs") == "legacy only"

    def test_serialize_job_helpers_include_requested_fields(self, test_db):
        repo = _create_repo(test_db)
        job = MaintenanceJobFacade(
            test_db,
            seed_job_operation(
                test_db,
                "check",
                repository_id=repo.id,
                status="completed",
                started_at=datetime(2026, 1, 1, 12, 0, 0),
                completed_at=datetime(2026, 1, 1, 12, 5, 0),
                progress=100,
                progress_message="done",
                error_message=None,
                logs="line 1",
            ),
        )

        status_payload = serialize_job_status(
            job,
            include_progress=True,
            include_logs=True,
            include_has_logs=True,
            log_save_policy="all_jobs",
        )
        summary_payload = serialize_job_summary(
            job,
            include_progress=True,
            include_has_logs=True,
            log_save_policy="all_jobs",
        )

        assert status_payload["progress"] == 100
        assert status_payload["progress_message"] == "done"
        assert status_payload["logs"] == "line 1"
        assert status_payload["has_logs"] is True
        assert summary_payload["progress"] == 100
        assert summary_payload["has_logs"] is True

    def test_serialize_job_helpers_apply_log_save_policy(self, test_db):
        repo = _create_repo(test_db)
        job = seed_job_operation(
            test_db,
            "check",
            repository_id=repo.id,
            status="completed",
            started_at=datetime(2026, 1, 1, 12, 0, 0),
            completed_at=datetime(2026, 1, 1, 12, 5, 0),
            logs="successful check output",
            has_logs=True,
        )

        status_payload = serialize_job_status(
            job,
            include_logs=True,
            include_has_logs=True,
            log_save_policy="failed_only",
        )
        summary_payload = serialize_job_summary(
            job,
            include_has_logs=True,
            log_save_policy="failed_only",
        )

        assert status_payload["logs"] == ""
        assert status_payload["has_logs"] is False
        assert summary_payload["has_logs"] is False

    def test_serialize_job_helpers_keep_running_logs_visible(self, test_db):
        repo = _create_repo(test_db)
        job = seed_job_operation(
            test_db,
            "check",
            repository_id=repo.id,
            status="running",
            started_at=datetime(2026, 1, 1, 12, 0, 0),
            logs="live check output",
            has_logs=True,
        )

        status_payload = serialize_job_status(
            job,
            include_logs=True,
            include_has_logs=True,
            log_save_policy="failed_only",
        )

        assert status_payload["logs"] == "live check output"
        assert status_payload["has_logs"] is True


@pytest.mark.unit
def test_status_serializes_stats_for_compact_only(test_db):
    """`result["stats"]` is a compact's `--stats` output; the facade would
    hand back a `stats` key of any kind's result, the payload does not."""
    repo = _create_repo(test_db)
    payloads = {}
    for kind in ("compact", "check"):
        operation = Operation(
            repository_id=repo.id,
            kind=kind,
            category="maintenance",
            status="completed",
            trigger="manual",
            priority=10,
            run_id=f"run-{kind}",
            result={"stats": {"repository_size": 5}},
        )
        test_db.add(operation)
        test_db.commit()
        payloads[kind] = serialize_job_status(
            MaintenanceJobFacade(test_db, operation),
            include_progress=True,
            include_logs=False,
            include_has_logs=False,
            log_save_policy="all_jobs",
        )
    assert payloads["compact"]["stats"] == {"repository_size": 5}
    assert "stats" not in payloads["check"]
