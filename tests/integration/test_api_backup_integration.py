import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_helpers import parse_archives_payload, wait_for_job_terminal_status


def _prepare_repository_for_backup(repo, test_db, source_paths):
    repo.source_directories = json.dumps([str(path) for path in source_paths])
    repo.compression = "lz4"
    test_db.commit()


@pytest.mark.integration
@pytest.mark.requires_borg
class TestBackupCreationIntegration:
    """Integration tests for backup creation and job tracking."""

    def test_create_backup_success(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        test_db,
    ):
        repo, repo_path, test_data_path = db_borg_repo
        _prepare_repository_for_backup(repo, test_db, [test_data_path])

        response = test_client.post(
            "/api/backup/start",
            json={"repository": str(repo_path)},
            headers=admin_headers,
        )

        assert response.status_code in [200, 201, 202]
        job_id = response.json()["job_id"]

        job_data = wait_for_job_terminal_status(
            test_client,
            "/api/backup/status",
            job_id,
            admin_headers,
            timeout=45,
        )
        assert job_data["status"] in ["completed", "completed_with_warnings"]

        list_response = test_client.get(
            f"/api/archives/list?repository={repo_path}",
            headers=admin_headers,
        )
        assert list_response.status_code == 200

        archive_names = [archive["name"] for archive in parse_archives_payload(list_response.json())]
        assert any(name.startswith("manual-backup-") for name in archive_names)

    def test_backup_status_and_job_filters_include_manual_backup(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        test_db,
    ):
        repo, repo_path, test_data_path = db_borg_repo
        _prepare_repository_for_backup(repo, test_db, [test_data_path])

        response = test_client.post(
            "/api/backup/start",
            json={"repository": str(repo_path)},
            headers=admin_headers,
        )

        assert response.status_code in [200, 201, 202]
        job_id = response.json()["job_id"]

        status_payload = wait_for_job_terminal_status(
            test_client,
            "/api/backup/status",
            job_id,
            admin_headers,
            timeout=45,
        )

        progress = status_payload["progress_details"]
        assert set(
            [
                "original_size",
                "compressed_size",
                "deduplicated_size",
                "nfiles",
                "current_file",
                "progress_percent",
                "backup_speed",
                "total_expected_size",
                "estimated_time_remaining",
            ]
        ).issubset(progress.keys())

        manual_jobs = test_client.get(
            "/api/backup/jobs?manual_only=true",
            headers=admin_headers,
        )
        assert manual_jobs.status_code == 200
        manual_job_ids = [job["id"] for job in manual_jobs.json()["jobs"]]
        assert job_id in manual_job_ids

        scheduled_jobs = test_client.get(
            "/api/backup/jobs?scheduled_only=true",
            headers=admin_headers,
        )
        assert scheduled_jobs.status_code == 200
        scheduled_job_ids = [job["id"] for job in scheduled_jobs.json()["jobs"]]
        assert job_id not in scheduled_job_ids

    def test_create_backup_for_unknown_repository_path_fails_in_background(
        self,
        test_client: TestClient,
        admin_headers,
        tmp_path,
    ):
        missing_repo_path = tmp_path / "missing-repo"

        response = test_client.post(
            "/api/backup/start",
            json={"repository": str(missing_repo_path)},
            headers=admin_headers,
        )

        assert response.status_code in [200, 201, 202]
        job_id = response.json()["job_id"]

        job_data = wait_for_job_terminal_status(
            test_client,
            "/api/backup/status",
            job_id,
            admin_headers,
            timeout=20,
        )

        assert job_data["status"] == "failed"
        assert job_data["error_message"]

    def test_download_backup_logs_for_failed_backup_job(
        self,
        test_client: TestClient,
        admin_headers,
        db_encrypted_borg_repo,
        test_db,
    ):
        repo, repo_path, test_data_path, _passphrase = db_encrypted_borg_repo
        _prepare_repository_for_backup(repo, test_db, [test_data_path])
        repo.passphrase = "definitely-wrong-passphrase"
        test_db.commit()

        response = test_client.post(
            "/api/backup/start",
            json={"repository": str(repo_path)},
            headers=admin_headers,
        )

        assert response.status_code in [200, 201, 202]
        job_id = response.json()["job_id"]

        job_data = wait_for_job_terminal_status(
            test_client,
            "/api/backup/status",
            job_id,
            admin_headers,
            timeout=45,
        )

        assert job_data["status"] == "failed"
        assert job_data["error_message"]

        logs_response = test_client.get(
            f"/api/backup/logs/{job_id}/download",
            headers=admin_headers,
        )

        assert logs_response.status_code == 200
        assert logs_response.headers["content-type"].startswith("text/plain")
        assert f'backup_job_{job_id}_logs.txt' in logs_response.headers["content-disposition"]
        assert "passphrase" in logs_response.text.lower() or "passphrase supplied in" in logs_response.text.lower()

    def test_create_backup_success_for_encrypted_repository(
        self,
        test_client: TestClient,
        admin_headers,
        db_encrypted_borg_repo,
        test_db,
    ):
        repo, repo_path, test_data_path, _passphrase = db_encrypted_borg_repo
        _prepare_repository_for_backup(repo, test_db, [test_data_path])

        response = test_client.post(
            "/api/backup/start",
            json={"repository": str(repo_path)},
            headers=admin_headers,
        )

        assert response.status_code in [200, 201, 202]
        job_id = response.json()["job_id"]

        job_data = wait_for_job_terminal_status(
            test_client,
            "/api/backup/status",
            job_id,
            admin_headers,
            timeout=45,
        )
        assert job_data["status"] in ["completed", "completed_with_warnings"]

        list_response = test_client.get(
            f"/api/archives/list?repository={repo_path}",
            headers=admin_headers,
        )
        assert list_response.status_code == 200
        archive_names = [archive["name"] for archive in parse_archives_payload(list_response.json())]
        assert "encrypted-archive" in archive_names
        assert any(name.startswith("manual-backup-") for name in archive_names)
