"""
Unit tests for mount API endpoints.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from app.api import mounts
from app.services.mount_service import MountInfo, MountType
from app.database.models import Repository


@pytest.mark.unit
class TestMountArchiveEndpoints:
    def test_mount_borg_archive_success(
        self,
        test_client: TestClient,
        admin_headers,
        monkeypatch,
    ):
        mount_info = MountInfo(
            mount_id="mount-1",
            mount_type=MountType.BORG_ARCHIVE,
            mount_point="/mnt/repo",
            source="Repo::archive",
            created_at=datetime.now(timezone.utc),
            repository_id=1,
        )

        monkeypatch.setattr(
            mounts.mount_service,
            "mount_borg_archive",
            AsyncMock(return_value=("/mnt/repo", "mount-1")),
        )
        monkeypatch.setattr(
            mounts.mount_service, "get_mount", lambda mount_id: mount_info
        )

        response = test_client.post(
            "/api/mounts/borg",
            json={"repository_id": 1, "archive_name": "archive"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["mount_id"] == "mount-1"
        assert data["mount_point"] == "/mnt/repo"
        assert data["mount_type"] == MountType.BORG_ARCHIVE.value
        assert data["source"] == "Repo::archive"

    def test_mount_borg_archive_missing_mount_info_returns_500(
        self,
        test_client: TestClient,
        admin_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(
            mounts.mount_service,
            "mount_borg_archive",
            AsyncMock(return_value=("/mnt/repo", "mount-1")),
        )
        monkeypatch.setattr(mounts.mount_service, "get_mount", lambda mount_id: None)

        response = test_client.post(
            "/api/mounts/borg",
            json={"repository_id": 1},
            headers=admin_headers,
        )

        assert response.status_code == 500
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.mounts.failedMountArchive"
        )

    def test_mount_borg_archive_returns_503_when_fuse_unavailable(
        self,
        test_client: TestClient,
        admin_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(
            mounts.mount_service,
            "mount_borg_archive",
            AsyncMock(
                side_effect=mounts.MountUnavailableError(
                    "Archive mounting is unavailable in this environment: no FUSE support"
                )
            ),
        )

        response = test_client.post(
            "/api/mounts/borg",
            json={"repository_id": 1},
            headers=admin_headers,
        )

        assert response.status_code == 503
        assert (
            response.json()["detail"]["key"] == "backend.errors.mounts.mountUnavailable"
        )

    def test_unmount_borg_archive_success(
        self,
        test_client: TestClient,
        admin_headers,
        monkeypatch,
    ):
        mount_info = MountInfo(
            mount_id="mount-1",
            mount_type=MountType.BORG_ARCHIVE,
            mount_point="/mnt/repo",
            source="Repo::archive",
            created_at=datetime.now(timezone.utc),
            repository_id=1,
        )

        monkeypatch.setattr(
            mounts.mount_service, "get_mount", lambda mount_id: mount_info
        )
        monkeypatch.setattr(
            mounts.mount_service, "unmount", AsyncMock(return_value=True)
        )

        response = test_client.post(
            "/api/mounts/borg/unmount/mount-1",
            params={"force": True},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json() == {"success": True, "mount_id": "mount-1"}

    def test_unmount_borg_archive_missing_mount_returns_404(
        self,
        test_client: TestClient,
        admin_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(mounts.mount_service, "get_mount", lambda mount_id: None)

        response = test_client.post(
            "/api/mounts/borg/unmount/missing",
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.mounts.mountNotFound"

    def test_unmount_rejects_non_borg_mounts(
        self,
        test_client: TestClient,
        admin_headers,
        monkeypatch,
    ):
        mount_info = MountInfo(
            mount_id="mount-sshfs",
            mount_type=MountType.SSHFS,
            mount_point="/mnt/sshfs",
            source="sshfs",
            created_at=datetime.now(timezone.utc),
        )
        monkeypatch.setattr(
            mounts.mount_service, "get_mount", lambda mount_id: mount_info
        )

        response = test_client.post(
            "/api/mounts/borg/unmount/mount-sshfs",
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.mounts.canOnlyUnmountBorgMounts"
        )


@pytest.mark.unit
class TestMountListingAndInfo:
    def test_list_mounts_filters_non_borg_mounts_and_rewrites_sources(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        monkeypatch,
    ):
        repo = Repository(
            name="Main Repo",
            path="/backups/main",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        borg_mount = MountInfo(
            mount_id="mount-1",
            mount_type=MountType.BORG_ARCHIVE,
            mount_point="/mnt/main",
            source="/backups/main::archive-1",
            created_at=datetime.now(timezone.utc),
            repository_id=repo.id,
            job_id=11,
        )
        sshfs_mount = MountInfo(
            mount_id="mount-2",
            mount_type=MountType.SSHFS,
            mount_point="/mnt/sshfs",
            source="sshfs://remote",
            created_at=datetime.now(timezone.utc),
            repository_id=None,
            job_id=None,
        )
        monkeypatch.setattr(
            mounts.mount_service, "list_mounts", lambda: [borg_mount, sshfs_mount]
        )

        response = test_client.get("/api/mounts", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["mount_id"] == "mount-1"
        assert data[0]["source"] == "Main Repo::archive-1"
        assert data[0]["job_id"] == 11

    def test_get_mount_info_success(
        self,
        test_client: TestClient,
        admin_headers,
        monkeypatch,
    ):
        mount_info = MountInfo(
            mount_id="mount-1",
            mount_type=MountType.BORG_ARCHIVE,
            mount_point="/mnt/repo",
            source="Repo::archive",
            created_at=datetime.now(timezone.utc),
            repository_id=1,
            connection_id=2,
        )
        monkeypatch.setattr(
            mounts.mount_service, "get_mount", lambda mount_id: mount_info
        )

        response = test_client.get("/api/mounts/mount-1", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["mount_id"] == "mount-1"
        assert data["repository_id"] == 1
        assert data["connection_id"] == 2

    def test_get_mount_info_not_found(
        self,
        test_client: TestClient,
        admin_headers,
        monkeypatch,
    ):
        monkeypatch.setattr(mounts.mount_service, "get_mount", lambda mount_id: None)

        response = test_client.get("/api/mounts/missing", headers=admin_headers)

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.mounts.mountNotFound"
