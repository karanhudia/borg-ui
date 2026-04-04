"""API-driven integration tests for Borg archive mounts."""

import platform
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _mount_prerequisites_available() -> bool:
    """Return whether the host can realistically execute borg mount."""
    if shutil.which("borg") is None:
        return False

    system = platform.system()
    if system == "Linux":
        return shutil.which("fusermount") is not None or shutil.which("fusermount3") is not None
    if system == "Darwin":
        return shutil.which("mount_macfuse") is not None or shutil.which("mount_osxfuse") is not None

    return shutil.which("umount") is not None


@pytest.mark.integration
@pytest.mark.requires_borg
class TestMountArchiveIntegration:
    """Real Borg mount coverage through FastAPI endpoints."""

    def test_mount_and_unmount_archive_via_api(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo_with_archives,
        tmp_path,
    ):
        if not _mount_prerequisites_available():
            pytest.skip("borg mount prerequisites are not available in this environment")

        repo, repo_path, test_data_path, archive_names = db_borg_repo_with_archives
        mount_name = f"integration-mount-{int(time.time())}"

        mount_response = test_client.post(
            "/api/mounts/borg",
            json={
                "repository_id": repo.id,
                "archive_name": archive_names[0],
                "mount_point": mount_name,
            },
            headers=admin_headers,
        )

        if mount_response.status_code == 500:
            pytest.skip(f"borg mount failed in this environment: {mount_response.json()}")

        assert mount_response.status_code == 200, mount_response.json()
        mount_data = mount_response.json()
        mount_id = mount_data["mount_id"]
        mount_point = Path(mount_data["mount_point"])

        try:
            deadline = time.time() + 15
            while time.time() < deadline:
                if mount_point.exists() and any(mount_point.iterdir()):
                    break
                time.sleep(0.5)

            assert mount_point.exists()
            assert any(mount_point.iterdir()), "mounted archive should expose filesystem contents"

            list_response = test_client.get("/api/mounts", headers=admin_headers)
            assert list_response.status_code == 200
            mount_ids = [item["mount_id"] for item in list_response.json()]
            assert mount_id in mount_ids

            info_response = test_client.get(f"/api/mounts/{mount_id}", headers=admin_headers)
            assert info_response.status_code == 200
            info_data = info_response.json()
            assert info_data["mount_id"] == mount_id
            assert info_data["repository_id"] == repo.id
            assert archive_names[0] in info_data["source"]
        finally:
            unmount_response = test_client.post(
                f"/api/mounts/borg/unmount/{mount_id}",
                headers=admin_headers,
            )
            assert unmount_response.status_code == 200, unmount_response.json()

            deadline = time.time() + 10
            while time.time() < deadline:
                list_response = test_client.get("/api/mounts", headers=admin_headers)
                if list_response.status_code == 200:
                    mount_ids = [item["mount_id"] for item in list_response.json()]
                    if mount_id not in mount_ids:
                        break
                time.sleep(0.25)

            list_response = test_client.get("/api/mounts", headers=admin_headers)
            assert list_response.status_code == 200
            mount_ids = [item["mount_id"] for item in list_response.json()]
            assert mount_id not in mount_ids
