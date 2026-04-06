import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.database.models import CheckJob, CompactJob, LicensingState, Repository


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

        borg_response = {
            "success": True,
            "stdout": json.dumps({"archives": 1, "size": 2}),
            "stderr": "",
        }
        with patch("app.api.v2.backups.borg2.create", new=AsyncMock(return_value=borg_response)) as mock_create:
            response = test_client.post(
                "/api/v2/backup/run",
                json={"repository_id": repo.id, "archive_name": "manual-archive"},
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json() == {"success": True, "stats": {"archives": 1, "size": 2}}
        mock_create.assert_awaited_once_with(
            repository=repo.path,
            source_paths=["/data/source-a", "/data/source-b"],
            compression="lz4",
            archive_name="manual-archive",
            passphrase=None,
            remote_path=None,
        )

    def test_backup_run_rejects_missing_source_directories(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)

        with patch("app.api.v2.backups.borg2.create", new=AsyncMock()) as mock_create:
            response = test_client.post(
                "/api/v2/backup/run",
                json={"repository_id": repo.id},
                headers=admin_headers,
            )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.backup.noSourceDirectories"
        mock_create.assert_not_called()

    def test_backup_run_rejects_missing_repository(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)

        response = test_client.post(
            "/api/v2/backup/run",
            json={"repository_id": 9999},
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.restore.repositoryNotFound"

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

        with patch("app.api.v2.backups.borg2.prune_archives", new=AsyncMock(return_value={"success": True, "stdout": "done", "stderr": ""})) as mock_prune:
            response = test_client.post(
                "/api/v2/backup/prune",
                json={"repository_id": repo.id, "keep_daily": 3, "dry_run": False},
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "output": "done",
            "note": "Run compact to reclaim freed space",
        }
        mock_prune.assert_awaited_once_with(
            repository=repo.path,
            keep_hourly=0,
            keep_daily=3,
            keep_weekly=4,
            keep_monthly=6,
            keep_quarterly=0,
            keep_yearly=1,
            dry_run=False,
            passphrase=None,
            remote_path=None,
        )

    def test_backup_compact_creates_job(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db, source_directories=["/data/source"])

        with patch("app.api.v2.backups.asyncio.create_task", return_value=object()) as mock_create_task:
            response = test_client.post(
                "/api/v2/backup/compact",
                json={"repository_id": repo.id},
                headers=admin_headers,
            )

            scheduled = mock_create_task.call_args.args[0]
            scheduled.close()

        assert response.status_code == 200
        assert response.json()["status"] == "running"
        assert response.json()["message"] == "backend.success.repo.compactJobStarted"
        job = test_db.query(CompactJob).first()
        assert job is not None
        assert job.repository_id == repo.id
        assert job.status == "running"

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

        with patch("app.api.v2.backups.asyncio.create_task", return_value=object()) as mock_create_task:
            response = test_client.post(
                "/api/v2/backup/check",
                json={"repository_id": repo.id},
                headers=admin_headers,
            )

            scheduled = mock_create_task.call_args.args[0]
            scheduled.close()

        assert response.status_code == 200
        assert response.json()["status"] == "running"
        assert response.json()["message"] == "backend.success.repo.checkJobStarted"
        job = test_db.query(CheckJob).first()
        assert job is not None
        assert job.repository_id == repo.id
        assert job.status == "running"

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
