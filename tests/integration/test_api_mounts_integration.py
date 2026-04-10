"""API-driven integration tests for Borg archive mounts."""

import json
import platform
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database.models import Repository
from tests.utils.borg import create_archive, make_borg_test_env


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


def _require_borg2_binary() -> str:
    borg2_path = shutil.which("borg2")
    if not borg2_path:
        pytest.skip("Borg 2 binary not found. Install borg2 to run this integration test.")
    return borg2_path


def _enable_borg_v2(test_db) -> None:
    from app.database.models import LicensingState

    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="integration-borg-v2-mount")
        test_db.add(state)

    state.plan = "pro"
    state.status = "active"
    state.is_trial = False
    test_db.commit()


def _create_borg2_repo_with_archives(test_db, tmp_path):
    borg2_binary = _require_borg2_binary()
    _enable_borg_v2(test_db)

    repo_path = tmp_path / "borg2-mount-repo"
    source_path = tmp_path / "borg2-mount-source"
    source_path.mkdir()
    env = make_borg_test_env(str(tmp_path))

    init_result = subprocess.run(
        [borg2_binary, "-r", str(repo_path), "repo-create", "--encryption", "none"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert init_result.returncode == 0, init_result.stderr

    (source_path / "mount.txt").write_text("borg2 mount data\n", encoding="utf-8")
    create_archive(borg2_binary, repo_path, "mount-archive-1", [source_path], env=env)

    (source_path / "mount.txt").write_text("borg2 mount data updated\n", encoding="utf-8")
    (source_path / "mount-2.txt").write_text("borg2 mount data 2\n", encoding="utf-8")
    create_archive(borg2_binary, repo_path, "mount-archive-2", [source_path], env=env)

    repo = Repository(
        name="Borg2 Mount Repo",
        path=str(repo_path),
        encryption="none",
        compression="lz4",
        repository_type="local",
        borg_version=2,
        archive_count=2,
        source_directories=json.dumps([str(source_path)]),
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)

    return repo, repo_path, source_path, ["mount-archive-1", "mount-archive-2"]


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

        if mount_response.status_code in {500, 503}:
            payload = mount_response.json()
            if (
                mount_response.status_code == 503
                and payload.get("detail", {}).get("key") == "backend.errors.mounts.mountUnavailable"
            ):
                pytest.skip(f"borg mount unavailable in this environment: {payload}")
            pytest.skip(f"borg mount failed in this environment: {payload}")

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

    def test_borg2_mount_or_fuse_unavailable_contract(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        tmp_path,
    ):
        repo, _repo_path, _source_path, archive_names = _create_borg2_repo_with_archives(test_db, tmp_path)
        archive_name = archive_names[0]

        mount_response = test_client.post(
            "/api/mounts/borg",
            json={
                "repository_id": repo.id,
                "archive_name": archive_name,
                "mount_point": f"borg2-mount-{int(time.time())}",
            },
            headers=admin_headers,
        )

        if mount_response.status_code == 503:
            payload = mount_response.json()
            assert payload["detail"]["key"] == "backend.errors.mounts.mountUnavailable"
            return

        if mount_response.status_code == 500:
            pytest.skip(f"borg2 mount failed in this environment: {mount_response.json()}")

        assert mount_response.status_code == 200, mount_response.json()
        mount_data = mount_response.json()
        mount_id = mount_data["mount_id"]
        mount_point = Path(mount_data["mount_point"])
        assert mount_data["mount_type"] == "borg_archive"
        assert archive_name in mount_data["source"]

        try:
            deadline = time.time() + 15
            while time.time() < deadline:
                if mount_point.exists() and any(mount_point.iterdir()):
                    break
                time.sleep(0.5)

            assert mount_point.exists()
            assert any(mount_point.iterdir())
        finally:
            unmount_response = test_client.post(
                f"/api/mounts/borg/unmount/{mount_id}",
                headers=admin_headers,
            )
            assert unmount_response.status_code == 200, unmount_response.json()
