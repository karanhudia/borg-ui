from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.database.models import CheckJob, CompactJob, PruneJob, Repository


def _create_repo(test_db) -> Repository:
    repo = Repository(
        name="Maintenance Repo",
        path="/repos/maintenance",
        encryption="none",
        repository_type="local",
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


@pytest.mark.integration
class TestMaintenanceJobApiIntegration:
    def test_repository_job_lists_use_shared_summary_shape(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        repo = _create_repo(test_db)
        test_db.add_all(
            [
                CheckJob(
                    repository_id=repo.id,
                    status="running",
                    progress=25,
                    progress_message="checking",
                    has_logs=True,
                    started_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
                ),
                CompactJob(
                    repository_id=repo.id,
                    status="completed",
                    progress=100,
                    progress_message="done",
                    started_at=datetime(2026, 1, 1, 12, 10, tzinfo=timezone.utc),
                ),
                PruneJob(
                    repository_id=repo.id,
                    status="failed",
                    error_message="prune failed",
                    has_logs=True,
                    started_at=datetime(2026, 1, 1, 12, 20, tzinfo=timezone.utc),
                ),
            ]
        )
        test_db.commit()

        check_response = test_client.get(f"/api/repositories/{repo.id}/check-jobs", headers=admin_headers)
        compact_response = test_client.get(f"/api/repositories/{repo.id}/compact-jobs", headers=admin_headers)
        prune_response = test_client.get(f"/api/repositories/{repo.id}/prune-jobs", headers=admin_headers)

        assert check_response.status_code == 200
        assert compact_response.status_code == 200
        assert prune_response.status_code == 200
        assert check_response.json()["jobs"][0]["progress"] == 25
        assert compact_response.json()["jobs"][0]["progress_message"] == "done"
        assert prune_response.json()["jobs"][0]["has_logs"] is True

    def test_repository_job_status_endpoints_read_streamed_logs(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        tmp_path,
    ):
        repo = _create_repo(test_db)
        check_log = tmp_path / "check.log"
        compact_log = tmp_path / "compact.log"
        prune_log = tmp_path / "prune.log"
        check_log.write_text("check streamed\n", encoding="utf-8")
        compact_log.write_text("compact streamed\n", encoding="utf-8")
        prune_log.write_text("prune streamed\n", encoding="utf-8")

        check_job = CheckJob(repository_id=repo.id, status="completed", log_file_path=str(check_log), has_logs=True)
        compact_job = CompactJob(repository_id=repo.id, status="completed", log_file_path=str(compact_log), has_logs=True)
        prune_job = PruneJob(repository_id=repo.id, status="completed", log_file_path=str(prune_log), has_logs=True)
        test_db.add_all([check_job, compact_job, prune_job])
        test_db.commit()
        test_db.refresh(check_job)
        test_db.refresh(compact_job)
        test_db.refresh(prune_job)

        check_response = test_client.get(f"/api/repositories/check-jobs/{check_job.id}", headers=admin_headers)
        compact_response = test_client.get(f"/api/repositories/compact-jobs/{compact_job.id}", headers=admin_headers)
        prune_response = test_client.get(f"/api/repositories/prune-jobs/{prune_job.id}", headers=admin_headers)

        assert check_response.status_code == 200
        assert compact_response.status_code == 200
        assert prune_response.status_code == 200
        assert check_response.json()["logs"] == "check streamed\n"
        assert compact_response.json()["logs"] == "compact streamed\n"
        assert prune_response.json()["logs"] == "prune streamed\n"
