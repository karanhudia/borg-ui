from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database.models import Repository, RepositoryStorage, RcloneRemote
from app.services.rclone_service import RcloneCommandResult
from app.services.rclone_service import RcloneUnavailable
from tests.unit.helpers import assert_auth_required


@pytest.mark.unit
def test_rclone_status_requires_authentication(test_client: TestClient):
    response = test_client.get("/api/rclone/status")

    assert_auth_required(response)


@pytest.mark.unit
def test_rclone_status_reports_unavailable_binary(
    test_client: TestClient, admin_headers, monkeypatch
):
    async def fake_status():
        raise RcloneUnavailable("rclone binary not found")

    monkeypatch.setattr("app.api.rclone.rclone_service.status", fake_status)

    response = test_client.get("/api/rclone/status", headers=admin_headers)

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "version": None,
        "error": "rclone binary not found",
    }


@pytest.mark.unit
def test_create_and_list_rclone_remote(
    test_client: TestClient, admin_headers, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.api.rclone.settings.rclone_config_root", str(tmp_path / "rclone")
    )

    response = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "prod-s3",
            "provider": "s3",
            "config_source": "managed",
            "redacted_config": {"type": "s3", "provider": "AWS"},
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "prod-s3"
    assert created["provider"] == "s3"
    assert created["config_path"].endswith("/prod-s3.conf")

    response = test_client.get("/api/rclone/remotes", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["remotes"][0]["name"] == "prod-s3"


@pytest.mark.unit
def test_test_remote_updates_status(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)

    monkeypatch.setattr(
        "app.api.rclone.rclone_service.about",
        AsyncMock(return_value={"success": True, "stdout": "ok", "stderr": ""}),
    )

    response = test_client.post(
        f"/api/rclone/remotes/{remote.id}/test", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "connected"
    test_db.refresh(remote)
    assert remote.last_test_status == "connected"


@pytest.mark.unit
def test_browse_remote_returns_redacted_entries(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)

    monkeypatch.setattr(
        "app.api.rclone.rclone_service.lsjson",
        AsyncMock(
            return_value=[
                {
                    "Name": "config",
                    "Path": "borg-ui/repositories/app/config",
                    "IsDir": False,
                }
            ]
        ),
    )

    response = test_client.get(
        f"/api/rclone/remotes/{remote.id}/browse",
        headers=admin_headers,
        params={"path": "borg-ui/repositories/app"},
    )

    assert response.status_code == 200
    assert response.json()["entries"][0]["name"] == "config"


@pytest.mark.unit
def test_repository_rclone_status_endpoint(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(name="App", path="/cache/repositories/1", encryption="none")
    test_db.add_all([remote, repository])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(repository)
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        rclone_remote_id=remote.id,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path="/cache/repositories/1",
        sync_policy="after_success",
        sync_status="pending",
    )
    test_db.add(storage)
    test_db.commit()

    response = test_client.get(
        f"/api/repositories/{repository.id}/rclone/status", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["rclone_target"] == "prod-s3:borg-ui/repositories/app"
    assert response.json()["sync_status"] == "pending"


@pytest.mark.unit
def test_create_rclone_repository_rejects_client_cache_path(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "App",
            "path": "/client/ignored",
            "encryption": "none",
            "storage_backend": "rclone",
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_cache_path": "/tmp/client-owned-cache",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"] == "backend.errors.rclone.cachePathServerOwned"
    )


@pytest.mark.unit
def test_create_rclone_repository_derives_cache_path_and_syncs(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(
        "app.api.repositories.rclone_repository_service.cache_root", str(cache_root)
    )
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.sync",
        AsyncMock(
            return_value=RcloneCommandResult(
                success=True,
                return_code=0,
                stdout="",
                stderr="",
                command=["rclone", "sync"],
                redacted_command="rclone sync <path> <path>",
            )
        ),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "App",
            "path": "/client/ignored",
            "encryption": "none",
            "storage_backend": "rclone",
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_sync_policy": "after_success",
        },
    )

    assert response.status_code == 200
    repository = test_db.query(Repository).filter(Repository.name == "App").one()
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == str(cache_root / "repositories" / str(repository.id))
    assert storage.cache_path == repository.path
    assert storage.rclone_remote_path == "borg-ui/repositories/app"
    assert storage.sync_status == "current"
    assert response.json()["repository"]["rclone_storage"]["rclone_target"] == (
        "prod-s3:borg-ui/repositories/app"
    )


@pytest.mark.unit
def test_create_rclone_repository_persists_sync_failure_state(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    monkeypatch.setattr(
        "app.api.repositories.rclone_repository_service.cache_root",
        str(tmp_path / "cache"),
    )
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.sync",
        AsyncMock(
            return_value=RcloneCommandResult(
                success=False,
                return_code=1,
                stdout="",
                stderr="remote unavailable",
                command=["rclone", "sync"],
                redacted_command="rclone sync <path> <path>",
            )
        ),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "App",
            "path": "/client/ignored",
            "encryption": "none",
            "storage_backend": "rclone",
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_sync_policy": "after_success",
        },
    )

    assert response.status_code == 200
    repository = test_db.query(Repository).filter(Repository.name == "App").one()
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert storage.sync_status == "failed"
    assert storage.last_sync_error == "remote unavailable"
