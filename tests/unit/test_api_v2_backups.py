import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.database.models import BackupJob, CheckJob, CompactJob, LicensingState, Repository


def _enable_borg_v2(test_db):
    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="test-instance-v2-backups")
        test_db.add(state)
    state.plan = "pro"
    state.status = "active"
    state.is_trial = False
    test_db.commit()


def _create_v2_repo(test_db, *, name="V2 Repo", path="/tmp/v2-repo", source_directories=None):
    repo = Repository(
        name=name,
        path=path,
        encryption="repokey-aes-ocb",
        compression="lz4",
        repository_type="local",
        borg_version=2,
        source_directories=json.dumps(source_directories) if source_directories is not None else None,
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


@pytest.mark.unit
class TestV2BackupRoutes:
    def test_backup_run_is_feature_gated_by_plan(self, test_client: TestClient, admin_headers):
        response = test_client.post(
            "/api/v2/backup/run",
            json={"repository_id": 1},
            headers=admin_headers,
        )

        assert response.status_code == 403
        assert response.json()["detail"]["key"] == "backend.errors.plan.featureNotAvailable"

    def test_backup_run_success(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db, source_directories=["/data/source-a", "/data/source-b"])

        async def mark_backup_complete(job_id, repository_path, db=None, archive_name=None, skip_hooks=False):
            job = test_db.query(BackupJob).filter(BackupJob.id == job_id).first()
            job.status = "completed"
            job.original_size = 10
            job.compressed_size = 5
            job.deduplicated_size = 3
            job.nfiles = 2
            test_db.commit()

        with patch("app.api.v2.backups.backup_service.execute_backup", new=mark_backup_complete) as mock_create:
            response = test_client.post(
                "/api/v2/backup/run",
                json={"repository_id": repo.id, "archive_name": "manual-archive"},
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["status"] == "completed"
        assert response.json()["stats"] == {
            "original_size": 10,
            "compressed_size": 5,
            "deduplicated_size": 3,
            "nfiles": 2,
        }

    def test_backup_run_rejects_missing_source_directories(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)

        with patch("app.api.v2.backups.backup_service.execute_backup", new=AsyncMock()) as mock_create:
            response = test_client.post(
                "/api/v2/backup/run",
                json={"repository_id": repo.id},
                headers=admin_headers,
            )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.backup.noSourceDirectories"
        mock_create.assert_not_called()

    def test_backup_run_returns_500_when_shared_backup_execution_fails(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db, source_directories=["/data/source-a"])

        async def mark_backup_failed(job_id, repository_path, db=None, archive_name=None, skip_hooks=False):
            job = test_db.query(BackupJob).filter(BackupJob.id == job_id).first()
            job.status = "failed"
            job.error_message = "boom"
            test_db.commit()

        with patch("app.api.v2.backups.backup_service.execute_backup", new=mark_backup_failed):
            response = test_client.post(
                "/api/v2/backup/run",
                json={"repository_id": repo.id, "archive_name": "manual-archive"},
                headers=admin_headers,
            )

        assert response.status_code == 500
        assert response.json()["detail"]["key"] == "backend.errors.backup.failed"

    def test_backup_run_rejects_missing_repository(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)

        response = test_client.post(
            "/api/v2/backup/run",
            json={"repository_id": 9999},
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.repo.repositoryNotFound"

    def test_backup_prune_requires_admin(self, test_client: TestClient, auth_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db, source_directories=["/data/source"])

        response = test_client.post(
            "/api/v2/backup/prune",
            json={"repository_id": repo.id},
            headers=auth_headers,
        )

        assert response.status_code == 403
        assert response.json()["detail"]["key"] == "backend.errors.repo.adminAccessRequired"

    def test_backup_prune_success(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db, source_directories=["/data/source"])

        with patch(
            "app.api.v2.backups.prune_v2_service.run_prune",
            new=AsyncMock(return_value={"success": True, "stdout": "done", "stderr": ""}),
        ) as mock_prune:
            response = test_client.post(
                "/api/v2/backup/prune",
                json={"repository_id": repo.id, "keep_daily": 3, "dry_run": False},
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "dry_run": False,
            "prune_result": {
                "success": True,
                "stdout": "done\n\nRun compact to reclaim freed space",
                "stderr": "",
            },
        }
        mock_prune.assert_awaited_once_with(
            repo=repo,
            keep_hourly=0,
            keep_daily=3,
            keep_weekly=4,
            keep_monthly=6,
            keep_quarterly=0,
            keep_yearly=1,
            dry_run=False,
        )

    def test_backup_prune_dry_run_returns_legacy_modal_shape(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db, source_directories=["/data/source"])

        with patch(
            "app.api.v2.backups.prune_v2_service.run_prune",
            new=AsyncMock(return_value={"success": True, "stdout": "would prune", "stderr": ""}),
        ):
            response = test_client.post(
                "/api/v2/backup/prune",
                json={"repository_id": repo.id, "dry_run": True},
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "dry_run": True,
            "prune_result": {
                "success": True,
                "stdout": "would prune",
                "stderr": "",
            },
        }

    def test_backup_compact_creates_job(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db, source_directories=["/data/source"])

        with patch("app.api.v2.backups.start_background_maintenance_job") as mock_start:
            mock_start.return_value = CompactJob(id=5, repository_id=repo.id, status="running")
            response = test_client.post(
                "/api/v2/backup/compact",
                json={"repository_id": repo.id},
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json()["status"] == "running"
        assert response.json()["message"] == "backend.success.repo.compactJobStarted"
        mock_start.assert_called_once()

    def test_backup_compact_rejects_duplicate_running_job(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db, source_directories=["/data/source"])
        test_db.add(
            CompactJob(
                repository_id=repo.id,
                repository_path=repo.path,
                status="running",
            )
        )
        test_db.commit()

        response = test_client.post(
            "/api/v2/backup/compact",
            json={"repository_id": repo.id},
            headers=admin_headers,
        )

        assert response.status_code == 409
        assert response.json()["detail"]["key"] == "backend.errors.compact.alreadyRunning"

    def test_backup_check_creates_job(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db, source_directories=["/data/source"])

        with patch("app.api.v2.backups.start_background_maintenance_job") as mock_start:
            mock_start.return_value = CheckJob(id=7, repository_id=repo.id, status="running")
            response = test_client.post(
                "/api/v2/backup/check",
                json={"repository_id": repo.id},
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json()["status"] == "running"
        assert response.json()["message"] == "backend.success.repo.checkJobStarted"
        mock_start.assert_called_once()

    def test_backup_check_rejects_duplicate_running_job(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db, source_directories=["/data/source"])
        test_db.add(
            CheckJob(
                repository_id=repo.id,
                repository_path=repo.path,
                status="running",
            )
        )
        test_db.commit()

        response = test_client.post(
            "/api/v2/backup/check",
            json={"repository_id": repo.id},
            headers=admin_headers,
        )

        assert response.status_code == 409
        assert response.json()["detail"]["key"] == "backend.errors.repo.checkAlreadyRunning"
