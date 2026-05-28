import importlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.core.security import get_password_hash
from app.database.models import (
    AgentMachine,
    Repository,
    RepositoryStorage,
    RcloneSyncJob,
    RcloneRemote,
    SSHConnection,
)
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
    assert created["config_path"].endswith("/rclone.conf")
    config_file = tmp_path / "rclone" / "rclone.conf"
    config_body = config_file.read_text(encoding="utf-8")
    assert "[prod-s3]" in config_body
    assert "type = s3" in config_body
    assert "provider = AWS" in config_body

    response = test_client.get("/api/rclone/remotes", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["remotes"][0]["name"] == "prod-s3"

    duplicate = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": " prod-s3 ",
            "provider": "s3",
            "config_source": "managed",
            "redacted_config": {"type": "s3", "provider": "AWS"},
        },
    )

    assert duplicate.status_code == 409
    response = test_client.get("/api/rclone/remotes", headers=admin_headers)
    assert response.status_code == 200
    assert [remote["name"] for remote in response.json()["remotes"]] == ["prod-s3"]

    traversal = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "../../escape",
            "provider": "s3",
            "config_source": "managed",
            "redacted_config": {"type": "s3", "provider": "AWS"},
        },
    )

    assert traversal.status_code == 400
    assert (
        traversal.json()["detail"]["key"] == "backend.errors.rclone.invalidRemoteName"
    )


@pytest.mark.unit
def test_list_rclone_remotes_includes_repository_usage_count(
    test_client: TestClient, admin_headers, test_db
):
    used_remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    unused_remote = RcloneRemote(
        name="archive-b2", provider="b2", config_source="managed"
    )
    repositories = [
        Repository(name="Photos", path="/cache/repositories/1", encryption="none"),
        Repository(name="Documents", path="/cache/repositories/2", encryption="none"),
    ]
    test_db.add_all([used_remote, unused_remote, *repositories])
    test_db.commit()
    test_db.refresh(used_remote)
    test_db.refresh(unused_remote)
    for repository in repositories:
        test_db.refresh(repository)

    test_db.add_all(
        [
            RepositoryStorage(
                repository_id=repositories[0].id,
                backend="rclone",
                rclone_remote_id=used_remote.id,
                rclone_remote_path="borg-ui/repositories/photos",
                cache_path="/cache/repositories/1",
                sync_policy="after_success",
                sync_status="current",
            ),
            RepositoryStorage(
                repository_id=repositories[1].id,
                backend="rclone",
                rclone_remote_id=used_remote.id,
                rclone_remote_path="borg-ui/repositories/documents",
                cache_path="/cache/repositories/2",
                sync_policy="after_success",
                sync_status="pending",
            ),
        ]
    )
    test_db.commit()

    response = test_client.get("/api/rclone/remotes", headers=admin_headers)

    assert response.status_code == 200
    remotes = {remote["name"]: remote for remote in response.json()["remotes"]}
    assert remotes["prod-s3"]["usage_count"] == 2
    assert remotes["archive-b2"]["usage_count"] == 0


@pytest.mark.unit
def test_create_rclone_remote_rejects_blank_provider(
    test_client: TestClient, admin_headers
):
    response = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "prod-s3",
            "provider": "   ",
            "config_source": "managed",
            "redacted_config": {"type": "s3", "provider": "AWS"},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {"key": "backend.errors.rclone.invalidProvider"}


@pytest.mark.unit
def test_create_managed_rclone_remote_removes_config_file_on_commit_failure(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    config_root = tmp_path / "rclone"
    monkeypatch.setattr("app.api.rclone.settings.rclone_config_root", str(config_root))
    original_commit = test_db.commit
    state = {"failed": False}

    def fail_once():
        if not state["failed"]:
            state["failed"] = True
            raise RuntimeError("database unavailable")
        return original_commit()

    monkeypatch.setattr(test_db, "commit", fail_once)

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

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "key": "backend.errors.rclone.failedToCreateRemote"
    }
    assert not (config_root / "rclone.conf").exists()


@pytest.mark.unit
def test_update_rclone_remote_renames_managed_config_section(
    test_client: TestClient, admin_headers, tmp_path, monkeypatch
):
    config_root = tmp_path / "rclone"
    monkeypatch.setattr("app.api.rclone.settings.rclone_config_root", str(config_root))

    create_response = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "prod-s3",
            "provider": "s3",
            "config_source": "managed",
            "redacted_config": {"type": "s3", "provider": "AWS"},
        },
    )
    remote_id = create_response.json()["id"]

    response = test_client.put(
        f"/api/rclone/remotes/{remote_id}",
        headers=admin_headers,
        json={
            "name": "archive-b2",
            "provider": "b2",
            "redacted_config": {"type": "b2", "account": "redacted"},
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "archive-b2"
    assert updated["provider"] == "b2"
    config_body = (config_root / "rclone.conf").read_text(encoding="utf-8")
    assert "[prod-s3]" not in config_body
    assert "[archive-b2]" in config_body
    assert "type = b2" in config_body
    assert "account = redacted" in config_body


@pytest.mark.unit
def test_update_rclone_remote_rejects_duplicate_name(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    other = RcloneRemote(name="archive-b2", provider="b2", config_source="managed")
    test_db.add_all([remote, other])
    test_db.commit()
    test_db.refresh(remote)

    response = test_client.put(
        f"/api/rclone/remotes/{remote.id}",
        headers=admin_headers,
        json={"name": " archive-b2 "},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"key": "backend.errors.rclone.remoteExists"}


@pytest.mark.unit
def test_delete_rclone_remote_removes_managed_config_section(
    test_client: TestClient, admin_headers, tmp_path, monkeypatch
):
    config_root = tmp_path / "rclone"
    monkeypatch.setattr("app.api.rclone.settings.rclone_config_root", str(config_root))
    create_response = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "prod-s3",
            "provider": "s3",
            "config_source": "managed",
            "redacted_config": {"type": "s3", "provider": "AWS"},
        },
    )
    remote_id = create_response.json()["id"]

    response = test_client.delete(
        f"/api/rclone/remotes/{remote_id}", headers=admin_headers
    )

    assert response.status_code == 204
    response = test_client.get("/api/rclone/remotes", headers=admin_headers)
    assert response.json()["remotes"] == []
    assert not (config_root / "rclone.conf").exists()


@pytest.mark.unit
def test_delete_rclone_remote_rejects_used_remote(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(
        name="Photos", path="/cache/repositories/1", encryption="none"
    )
    test_db.add_all([remote, repository])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(repository)
    test_db.add(
        RepositoryStorage(
            repository_id=repository.id,
            backend="rclone",
            rclone_remote_id=remote.id,
            rclone_remote_path="borg-ui/photos",
            cache_path="/cache/repositories/1",
            sync_policy="after_success",
            sync_status="current",
        )
    )
    test_db.commit()

    response = test_client.delete(
        f"/api/rclone/remotes/{remote.id}", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"key": "backend.errors.rclone.remoteInUse"}
    assert test_db.query(RcloneRemote).filter(RcloneRemote.id == remote.id).one()


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
def test_browse_remote_returns_paths_relative_to_remote_root(
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
                {"Name": "snapshots", "Path": "snapshots", "IsDir": True, "Size": -1},
                {"Name": "manifest.json", "Path": "manifest.json", "IsDir": False},
            ]
        ),
    )

    response = test_client.get(
        f"/api/rclone/remotes/{remote.id}/browse",
        headers=admin_headers,
        params={"path": "borg-ui"},
    )

    assert response.status_code == 200
    assert response.json()["path"] == "borg-ui"
    assert response.json()["entries"] == [
        {
            "name": "snapshots",
            "path": "borg-ui/snapshots",
            "is_dir": True,
            "size": None,
            "modified": None,
        },
        {
            "name": "manifest.json",
            "path": "borg-ui/manifest.json",
            "is_dir": False,
            "size": None,
            "modified": None,
        },
    ]


@pytest.mark.unit
def test_repository_rclone_status_endpoint(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(
        name="App",
        path="/cache/repositories/1",
        encryption="none",
        repository_type="rclone",
    )
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
def test_create_local_repository_with_cloud_mirror_preserves_primary_path_and_syncs(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    repo_path = tmp_path / "repositories" / "app"
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )
    sync = AsyncMock(
        return_value=RcloneCommandResult(
            success=True,
            return_code=0,
            stdout="",
            stderr="",
            command=["rclone", "sync"],
            redacted_command="rclone sync <path> <path>",
        )
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.sync", sync
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Local App",
            "path": str(repo_path),
            "encryption": "none",
            "storage_backend": "local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "after_success",
            "rclone_extra_flags": ["--fast-list"],
        },
    )

    assert response.status_code == 200
    repository = test_db.query(Repository).filter(Repository.name == "Local App").one()
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == str(repo_path)
    assert repository.repository_type == "local"
    assert storage.cache_path == str(repo_path)
    assert storage.sync_direction == "primary_to_remote"
    assert storage.sync_status == "current"
    assert response.json()["repository"]["storage_backend"] == "local"
    assert response.json()["repository"]["rclone_storage"]["rclone_target"] == (
        "prod-s3:borg-ui/repositories/app"
    )
    assert "rclone_cache_path" not in response.json()["repository"]


@pytest.mark.unit
def test_create_local_repository_cloud_mirror_rejects_client_cache_path(
    test_client: TestClient, admin_headers, test_db, tmp_path
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Local App",
            "path": str(tmp_path / "repositories" / "app"),
            "encryption": "none",
            "cloud_mirror_enabled": True,
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
def test_create_ssh_repository_with_cloud_mirror_uses_server_owned_mount_strategy(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    connection = SSHConnection(host="storage.example", username="borg", port=22)
    test_db.add_all([remote, connection])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(connection)
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
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
    mount_service = AsyncMock()
    mount_service.active_mounts = {
        "mount-ssh-repo": type(
            "MountInfo", (), {"mount_point": "/tmp/sshfs_mount_9/backups/app"}
        )()
    }
    mount_service.mount_ssh_directory.return_value = (
        "/tmp/sshfs_mount_9",
        "mount-ssh-repo",
    )
    mount_service.unmount.return_value = True
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_repository_service.ssh_mount_service",
        mount_service,
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "SSH App",
            "path": "/backups/app",
            "encryption": "none",
            "storage_backend": "ssh",
            "repository_type": "ssh",
            "connection_id": connection.id,
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "after_success",
        },
    )

    assert response.status_code == 200
    repository = test_db.query(Repository).filter(Repository.name == "SSH App").one()
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == "ssh://borg@storage.example:22/backups/app"
    assert repository.connection_id == connection.id
    assert storage.cache_path is None
    assert storage.sync_direction == "sshfs_mount_to_remote"
    assert storage.sync_status == "current"
    assert response.json()["repository"]["rclone_storage"]["sync_direction"] == (
        "sshfs_mount_to_remote"
    )
    assert "rclone_cache_path" not in response.json()["repository"]


@pytest.mark.unit
def test_create_ssh_repository_cloud_mirror_rejects_client_cache_path(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    connection = SSHConnection(host="storage.example", username="borg", port=22)
    test_db.add_all([remote, connection])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(connection)

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "SSH App",
            "path": "/backups/app",
            "encryption": "none",
            "storage_backend": "ssh",
            "repository_type": "ssh",
            "connection_id": connection.id,
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_cache_path": "/tmp/client-owned-stage",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"] == "backend.errors.rclone.cachePathServerOwned"
    )


@pytest.mark.unit
def test_create_ssh_repository_cloud_mirror_requires_stored_connection(
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
            "name": "SSH App",
            "path": "/backups/app",
            "encryption": "none",
            "storage_backend": "ssh",
            "repository_type": "ssh",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.rclone.mirrorUnsupportedPrimary"
    )


@pytest.mark.unit
def test_create_ssh_repository_cloud_mirror_first_sync_failure_preserves_repository(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    connection = SSHConnection(host="storage.example", username="borg", port=22)
    test_db.add_all([remote, connection])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(connection)
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )
    mount_service = AsyncMock()
    mount_service.active_mounts = {
        "mount-ssh-repo": type(
            "MountInfo", (), {"mount_point": "/tmp/sshfs_mount_9/backups/app"}
        )()
    }
    mount_service.mount_ssh_directory.return_value = (
        "/tmp/sshfs_mount_9",
        "mount-ssh-repo",
    )
    mount_service.unmount.return_value = True
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_repository_service.ssh_mount_service",
        mount_service,
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
            "name": "SSH App",
            "path": "/backups/app",
            "encryption": "none",
            "storage_backend": "ssh",
            "repository_type": "ssh",
            "connection_id": connection.id,
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "after_success",
        },
    )

    assert response.status_code == 200
    repository = test_db.query(Repository).filter(Repository.name == "SSH App").one()
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == "ssh://borg@storage.example:22/backups/app"
    assert storage.sync_status == "failed"
    assert storage.last_sync_error == "remote unavailable"
    assert response.json()["repository"]["rclone_storage"]["sync_status"] == "failed"


@pytest.mark.unit
def test_create_agent_repository_with_cloud_mirror_records_agent_owned_strategy(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    agent = AgentMachine(
        name="Laptop",
        agent_id="agt_laptop_mirror",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.rclone_sync"],
    )
    test_db.add_all([remote, agent])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(agent)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Agent Mirror App",
            "path": "/agent/repositories/app",
            "encryption": "none",
            "execution_target": "agent",
            "executor_type": "agent",
            "agent_machine_id": agent.id,
            "storage_backend": "agent_local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "manual",
        },
    )

    assert response.status_code == 200
    repository = (
        test_db.query(Repository).filter(Repository.name == "Agent Mirror App").one()
    )
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.executor_type == "agent"
    assert repository.agent_machine_id == agent.id
    assert repository.path == "/agent/repositories/app"
    assert storage.cache_path is None
    assert storage.sync_direction == "agent_to_remote"
    assert response.json()["repository"]["rclone_storage"]["sync_direction"] == (
        "agent_to_remote"
    )
    assert response.json()["repository"]["rclone_storage"]["cache_path"] is None
    assert response.json()["repository"]["agent_machine_name"] == "Laptop"
    assert response.json()["repository"]["agent_machine_status"] == "online"
    assert (
        response.json()["repository"]["rclone_storage"]["agent_machine_name"]
        == "Laptop"
    )
    assert (
        response.json()["repository"]["rclone_storage"]["agent_machine_status"]
        == "online"
    )
    assert "rclone_cache_path" not in response.json()["repository"]


@pytest.mark.unit
def test_create_agent_repository_cloud_mirror_rejects_client_cache_path(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    agent = AgentMachine(
        name="Laptop",
        agent_id="agt_laptop_cache_reject",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.rclone_sync"],
    )
    test_db.add_all([remote, agent])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(agent)

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Agent Mirror App",
            "path": "/agent/repositories/app",
            "encryption": "none",
            "execution_target": "agent",
            "executor_type": "agent",
            "agent_machine_id": agent.id,
            "storage_backend": "agent_local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_cache_path": "/tmp/client-owned-agent-stage",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"] == "backend.errors.rclone.cachePathServerOwned"
    )
    assert test_db.query(RepositoryStorage).count() == 0


@pytest.mark.unit
def test_create_agent_repository_cloud_mirror_requires_agent_sync_capability(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    agent = AgentMachine(
        name="Laptop",
        agent_id="agt_laptop_missing_capability",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.info"],
    )
    test_db.add_all([remote, agent])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(agent)

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Agent Mirror App",
            "path": "/agent/repositories/app",
            "encryption": "none",
            "execution_target": "agent",
            "executor_type": "agent",
            "agent_machine_id": agent.id,
            "storage_backend": "agent_local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["key"] == "backend.errors.agents.capabilityMissing"
    assert (
        test_db.query(Repository).filter(Repository.name == "Agent Mirror App").first()
        is None
    )
    assert test_db.query(RepositoryStorage).count() == 0


@pytest.mark.unit
def test_create_agent_repository_cloud_mirror_rejects_soft_deleted_agent(test_db):
    from app.api.repositories import _require_agent_rclone_sync_capability

    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    agent = AgentMachine(
        name="Deleted Laptop",
        agent_id="agt_deleted_laptop_mirror",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        deleted_at=datetime.utcnow(),
        capabilities=["repository.rclone_sync"],
    )
    test_db.add_all([remote, agent])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(agent)

    with pytest.raises(HTTPException) as exc_info:
        _require_agent_rclone_sync_capability(agent.id, test_db)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["key"] == "backend.errors.agents.agentNotQueueable"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_agent_repository_borg2_requires_plan_feature(
    admin_user, test_db, monkeypatch
):
    from app.api.repositories import RepositoryCreate, create_repository

    agent = AgentMachine(
        name="Laptop",
        agent_id="agt_laptop_borg2_plan",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.info"],
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)

    async def unexpected_agent_create(*_args, **_kwargs):
        return {"success": True}

    monkeypatch.setattr(
        "app.api.repositories._create_agent_repository_record",
        unexpected_agent_create,
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_repository(
            RepositoryCreate(
                name="Agent Borg2 App",
                path="/agent/repositories/borg2-app",
                borg_version=2,
                encryption="none",
                execution_target="agent",
                executor_type="agent",
                agent_machine_id=agent.id,
                storage_backend="agent_local",
            ),
            admin_user,
            test_db,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["key"] == "backend.errors.plan.featureNotAvailable"
    assert (
        test_db.query(Repository).filter(Repository.name == "Agent Borg2 App").first()
        is None
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_mirrored_agent_repository_requires_new_agent_sync_capability(
    admin_user, test_db, monkeypatch
):
    from app.api.repositories import RepositoryUpdate, update_repository

    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    original_agent = AgentMachine(
        name="Mirror Agent",
        agent_id="agt_mirror_capable",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.rclone_sync"],
    )
    replacement_agent = AgentMachine(
        name="Info Agent",
        agent_id="agt_info_only",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.info"],
    )
    test_db.add_all([remote, original_agent, replacement_agent])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(original_agent)
    test_db.refresh(replacement_agent)
    repository = Repository(
        name="Agent Mirror App",
        path="/agent/repositories/app",
        encryption="none",
        compression="lz4",
        execution_target="agent",
        executor_type="agent",
        agent_machine_id=original_agent.id,
    )
    test_db.add(repository)
    test_db.commit()
    test_db.refresh(repository)
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        rclone_remote_id=remote.id,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path=None,
        sync_policy="manual",
        sync_status="current",
        sync_direction="agent_to_remote",
    )
    test_db.add(storage)
    test_db.commit()
    monkeypatch.setattr(
        "app.api.repositories.mqtt_service.sync_state_with_db",
        lambda *args, **kwargs: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await update_repository(
            repository.id,
            RepositoryUpdate(agent_machine_id=replacement_agent.id),
            admin_user,
            test_db,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["key"] == "backend.errors.agents.capabilityMissing"
    test_db.refresh(repository)
    assert repository.agent_machine_id == original_agent.id


@pytest.mark.unit
def test_create_agent_repository_cloud_mirror_first_sync_failure_preserves_repository(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(
        name="prod-s3",
        provider="s3",
        config_source="managed",
        redacted_config={"type": "s3", "provider": "AWS"},
    )
    agent = AgentMachine(
        name="Laptop",
        agent_id="agt_laptop_sync_failure",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.rclone_sync"],
    )
    test_db.add_all([remote, agent])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(agent)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )

    def fake_queue(db, repository, *, job_kind, operation=None, **_kwargs):
        return SimpleNamespace(id=77)

    async def fake_wait(db, agent_job_id, **_kwargs):
        raise HTTPException(
            status_code=502,
            detail={
                "key": "backend.errors.agents.repositoryOperationFailed",
                "message": "agent rclone failed",
            },
        )

    monkeypatch.setattr(
        "app.services.rclone_repository_service.queue_agent_repository_operation_job",
        fake_queue,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.wait_for_agent_repository_operation_job",
        fake_wait,
        raising=False,
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Agent Mirror App",
            "path": "/agent/repositories/app",
            "encryption": "none",
            "execution_target": "agent",
            "executor_type": "agent",
            "agent_machine_id": agent.id,
            "storage_backend": "agent_local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "after_success",
        },
    )

    assert response.status_code == 200
    repository = (
        test_db.query(Repository).filter(Repository.name == "Agent Mirror App").one()
    )
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == "/agent/repositories/app"
    assert storage.sync_status == "failed"
    assert storage.last_sync_error == "agent rclone failed"
    assert response.json()["repository"]["rclone_storage"]["sync_status"] == "failed"


@pytest.mark.unit
def test_update_agent_repository_cloud_mirror_preflight_failure_rolls_back_storage(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    agent = AgentMachine(
        name="Laptop",
        agent_id="agt_laptop_update_rollback",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.rclone_sync"],
    )
    test_db.add_all([remote, agent])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(agent)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )

    create_response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Agent Mirror App",
            "path": "/agent/repositories/app",
            "encryption": "none",
            "execution_target": "agent",
            "executor_type": "agent",
            "agent_machine_id": agent.id,
            "storage_backend": "agent_local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/old",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "manual",
            "rclone_extra_flags": ["--fast-list"],
        },
    )

    assert create_response.status_code == 200
    repository = (
        test_db.query(Repository).filter(Repository.name == "Agent Mirror App").one()
    )
    test_db.refresh(repository)
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    storage.sync_status = "current"
    test_db.commit()
    test_db.refresh(storage)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(side_effect=TimeoutError("remote timed out")),
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={
            "name": "Agent Mirror App",
            "path": "/agent/repositories/app",
            "encryption": "none",
            "compression": "lz4",
            "execution_target": "agent",
            "executor_type": "agent",
            "agent_machine_id": agent.id,
            "storage_backend": "agent_local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/new",
            "rclone_remote_path_verified": False,
            "rclone_sync_policy": "after_success",
            "rclone_extra_flags": [],
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.rclone.remotePathPreflightFailed"
    )
    test_db.refresh(repository)
    test_db.refresh(storage)
    assert repository.path == "/agent/repositories/app"
    assert repository.agent_machine_id == agent.id
    assert storage.rclone_remote_path == "borg-ui/repositories/old"
    assert storage.cache_path is None
    assert storage.sync_direction == "agent_to_remote"
    assert storage.sync_policy == "manual"
    assert storage.sync_status == "current"
    assert storage.extra_flags == ["--fast-list"]


@pytest.mark.unit
def test_create_local_repository_cloud_mirror_blocks_unverified_non_empty_target(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[{"Name": "existing", "IsDir": True}]),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Local App",
            "path": str(tmp_path / "repositories" / "app"),
            "encryption": "none",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_sync_policy": "manual",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.rclone.remotePathNotVerified"
    )
    assert (
        test_db.query(Repository).filter(Repository.name == "Local App").first() is None
    )


@pytest.mark.unit
def test_create_local_repository_cloud_mirror_first_sync_failure_preserves_repository(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    repo_path = tmp_path / "repositories" / "app"
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
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
            "name": "Local App",
            "path": str(repo_path),
            "encryption": "none",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "after_success",
        },
    )

    assert response.status_code == 200
    repository = test_db.query(Repository).filter(Repository.name == "Local App").one()
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == str(repo_path)
    assert storage.sync_status == "failed"
    assert storage.last_sync_error == "remote unavailable"
    assert response.json()["repository"]["rclone_storage"]["sync_status"] == "failed"


@pytest.mark.unit
def test_create_local_repository_cloud_mirror_scheduled_policy_returns_next_run(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    repo_path = tmp_path / "repositories" / "scheduled-app"
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Scheduled Mirror App",
            "path": str(repo_path),
            "encryption": "none",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/scheduled-app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "scheduled",
            "rclone_sync_cron_expression": "0 */6 * * *",
            "rclone_sync_timezone": "UTC",
        },
    )

    assert response.status_code == 200
    repository = (
        test_db.query(Repository)
        .filter(Repository.name == "Scheduled Mirror App")
        .one()
    )
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    payload = response.json()["repository"]["rclone_storage"]
    assert storage.sync_policy == "scheduled"
    assert storage.sync_cron_expression == "0 */6 * * *"
    assert storage.sync_timezone == "UTC"
    assert storage.next_scheduled_sync_at is not None
    assert payload["sync_cron_expression"] == "0 */6 * * *"
    assert payload["sync_timezone"] == "UTC"
    assert payload["next_scheduled_sync_at"] is not None


@pytest.mark.unit
def test_create_scheduled_cloud_mirror_requires_cron_expression(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Missing Cron Mirror",
            "path": str(tmp_path / "repositories" / "missing-cron"),
            "encryption": "none",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/missing-cron",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "scheduled",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"] == "backend.errors.rclone.scheduleCronRequired"
    )
    assert (
        test_db.query(Repository)
        .filter(Repository.name == "Missing Cron Mirror")
        .first()
        is None
    )


@pytest.mark.unit
def test_import_local_repository_with_cloud_mirror_preserves_primary_path_and_syncs(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    repo_path = tmp_path / "repositories" / "imported"
    repo_path.mkdir(parents=True)
    (repo_path / "config").write_text("[repository]\nversion = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.api.repositories.verify_existing_repository",
        AsyncMock(
            return_value={
                "success": True,
                "info": {"encryption": {"mode": "none"}},
            }
        ),
    )
    monkeypatch.setattr(
        "app.api.repositories.BorgRouter.update_stats",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
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
        "/api/repositories/import",
        headers=admin_headers,
        json={
            "name": "Imported Local App",
            "path": str(repo_path),
            "encryption": "none",
            "storage_backend": "local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/imported",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "after_success",
            "rclone_extra_flags": ["--fast-list"],
        },
    )

    assert response.status_code == 200
    repository = (
        test_db.query(Repository).filter(Repository.name == "Imported Local App").one()
    )
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == str(repo_path)
    assert repository.repository_type == "local"
    assert storage.cache_path == str(repo_path)
    assert storage.sync_direction == "primary_to_remote"
    assert storage.sync_status == "current"
    assert response.json()["repository"]["storage_backend"] == "local"
    assert response.json()["repository"]["rclone_storage"]["rclone_target"] == (
        "prod-s3:borg-ui/repositories/imported"
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


@pytest.mark.unit
def test_create_rclone_repository_unexpected_init_failure_does_not_persist_record(
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
        AsyncMock(side_effect=RuntimeError("borg init crashed")),
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
            "rclone_sync_policy": "manual",
        },
    )

    assert response.status_code == 500
    assert test_db.query(Repository).filter(Repository.name == "App").first() is None


@pytest.mark.unit
@pytest.mark.parametrize("endpoint", ["/api/repositories/", "/api/repositories/import"])
def test_rclone_repository_rejects_borg2_payload(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch, endpoint
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
        "app.api.repositories.rclone_repository_service.hydrate_repository",
        AsyncMock(return_value={"sync_status": "current"}),
    )
    monkeypatch.setattr(
        "app.api.repositories.verify_existing_repository",
        AsyncMock(
            return_value={
                "success": True,
                "info": {"encryption": {"mode": "none"}},
            }
        ),
    )

    response = test_client.post(
        endpoint,
        headers=admin_headers,
        json={
            "name": "Borg2 Cloud Repo",
            "path": "/client/ignored",
            "borg_version": 2,
            "encryption": "none",
            "storage_backend": "rclone",
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_sync_policy": "manual",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["key"] == "backend.errors.rclone.borgV2Unsupported"


@pytest.mark.unit
def test_import_rclone_repository_verify_failure_removes_repository_record(
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
        "app.api.repositories.rclone_repository_service.hydrate_repository",
        AsyncMock(return_value={"sync_status": "current"}),
    )
    monkeypatch.setattr(
        "app.api.repositories.verify_existing_repository",
        AsyncMock(return_value={"success": False, "error": "not a borg repo"}),
    )

    response = test_client.post(
        "/api/repositories/import",
        headers=admin_headers,
        json={
            "name": "Imported Cloud Repo",
            "path": "/client/ignored",
            "encryption": "none",
            "storage_backend": "rclone",
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/imported",
            "rclone_sync_policy": "manual",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.repo.failedToVerifyRepository"
    )
    assert (
        test_db.query(Repository)
        .filter(Repository.name == "Imported Cloud Repo")
        .first()
        is None
    )
    assert test_db.query(RepositoryStorage).count() == 0


@pytest.mark.unit
def test_import_rclone_repository_flushes_storage_before_hydrate(
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

    async def hydrate_with_storage_lookup(db, repository):
        storage = (
            db.query(RepositoryStorage)
            .filter(RepositoryStorage.repository_id == repository.id)
            .first()
        )
        assert storage is not None
        return {"sync_status": "current"}

    monkeypatch.setattr(
        "app.api.repositories.rclone_repository_service.hydrate_repository",
        hydrate_with_storage_lookup,
    )
    monkeypatch.setattr(
        "app.api.repositories.verify_existing_repository",
        AsyncMock(
            return_value={
                "success": True,
                "info": {"encryption": {"mode": "none"}},
            }
        ),
    )

    response = test_client.post(
        "/api/repositories/import",
        headers=admin_headers,
        json={
            "name": "Imported Cloud Repo",
            "path": "/client/ignored",
            "encryption": "none",
            "storage_backend": "rclone",
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/imported",
            "rclone_sync_policy": "manual",
        },
    )

    assert response.status_code == 200
    repository = (
        test_db.query(Repository).filter(Repository.name == "Imported Cloud Repo").one()
    )
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert storage.cache_path == str(
        tmp_path / "cache" / "repositories" / str(repository.id)
    )


@pytest.mark.unit
def test_update_rclone_repository_storage_fields(
    test_client: TestClient, admin_headers, test_db
):
    old_remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    new_remote = RcloneRemote(name="archive-s3", provider="s3", config_source="managed")
    repository = Repository(name="App", path="/cache/repositories/1", encryption="none")
    test_db.add_all([old_remote, new_remote, repository])
    test_db.commit()
    test_db.refresh(old_remote)
    test_db.refresh(new_remote)
    test_db.refresh(repository)
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        rclone_remote_id=old_remote.id,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path="/cache/repositories/1",
        sync_policy="after_success",
        sync_status="current",
        extra_flags=[],
    )
    test_db.add(storage)
    test_db.commit()

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={
            "rclone_remote_id": new_remote.id,
            "rclone_remote_path": "borg-ui/repositories/archive",
            "rclone_sync_policy": "manual",
            "rclone_extra_flags": ["--fast-list"],
        },
    )

    assert response.status_code == 200
    test_db.refresh(storage)
    assert storage.rclone_remote_id == new_remote.id
    assert storage.rclone_remote_path == "borg-ui/repositories/archive"
    assert storage.sync_policy == "manual"
    assert storage.extra_flags == ["--fast-list"]


@pytest.mark.unit
def test_update_local_repository_enables_cloud_mirror(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(name="App", path="/repositories/app", encryption="none")
    test_db.add_all([remote, repository])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(repository)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={
            "storage_backend": "local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "manual",
            "rclone_extra_flags": ["--fast-list"],
        },
    )

    assert response.status_code == 200
    test_db.refresh(repository)
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == "/repositories/app"
    assert repository.repository_type == "local"
    assert storage.cache_path == "/repositories/app"
    assert storage.sync_direction == "primary_to_remote"
    assert storage.rclone_remote_id == remote.id
    assert storage.rclone_remote_path == "borg-ui/repositories/app"
    assert storage.sync_policy == "manual"
    assert storage.extra_flags == ["--fast-list"]


@pytest.mark.unit
def test_update_local_repository_cloud_mirror_adds_scheduled_policy(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(name="App", path="/repositories/app", encryption="none")
    test_db.add_all([remote, repository])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(repository)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={
            "storage_backend": "local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "scheduled",
            "rclone_sync_cron_expression": "*/30 * * * *",
            "rclone_sync_timezone": "UTC",
        },
    )

    assert response.status_code == 200
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert storage.sync_policy == "scheduled"
    assert storage.sync_cron_expression == "*/30 * * * *"
    assert storage.sync_timezone == "UTC"
    assert storage.next_scheduled_sync_at is not None


@pytest.mark.unit
def test_manual_rclone_sync_records_job_without_clearing_schedule(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(name="App", path="/repositories/app", encryption="none")
    test_db.add_all([remote, repository])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(repository)
    next_run = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2)
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        rclone_remote_id=remote.id,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path="/repositories/app",
        sync_policy="scheduled",
        sync_status="pending",
        sync_direction="primary_to_remote",
        sync_cron_expression="0 */6 * * *",
        sync_timezone="UTC",
        next_scheduled_sync_at=next_run,
    )
    test_db.add(storage)
    test_db.commit()
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.sync",
        AsyncMock(
            return_value=RcloneCommandResult(
                success=True,
                return_code=0,
                stdout="manual sync completed",
                stderr="",
                command=["rclone", "sync"],
                redacted_command="rclone sync <path> <path>",
            )
        ),
    )

    response = test_client.post(
        f"/api/repositories/{repository.id}/rclone/sync",
        headers=admin_headers,
    )

    assert response.status_code == 200
    test_db.refresh(storage)
    sync_job = test_db.query(RcloneSyncJob).one()
    assert response.json()["sync_status"] == "current"
    assert storage.next_scheduled_sync_at == next_run
    assert sync_job.triggered_by == "manual"
    assert sync_job.status == "completed"
    assert sync_job.log_text == "manual sync completed"


@pytest.mark.unit
def test_update_local_repository_cloud_mirror_preflight_failure_uses_error_key(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(name="App", path="/repositories/app", encryption="none")
    test_db.add_all([remote, repository])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(repository)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(side_effect=TimeoutError("rclone timed out")),
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={
            "storage_backend": "local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "manual",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.rclone.remotePathPreflightFailed"
    )
    assert test_db.query(RepositoryStorage).count() == 0


@pytest.mark.unit
def test_update_mirrored_local_repository_path_updates_cloud_mirror_source(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(
        name="App",
        path="/repositories/app",
        encryption="none",
        repository_type="local",
    )
    test_db.add_all([remote, repository])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(repository)
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        rclone_remote_id=remote.id,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path="/repositories/app",
        sync_policy="manual",
        sync_status="current",
        sync_direction="primary_to_remote",
    )
    test_db.add(storage)
    test_db.commit()
    monkeypatch.setattr(
        "app.api.repositories.BorgRouter.verify_repository",
        AsyncMock(return_value={"success": True}),
    )
    monkeypatch.setattr(
        "app.api.repositories.mqtt_service.sync_state_with_db",
        lambda *args, **kwargs: None,
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={"path": "/repositories/app-new"},
    )

    assert response.status_code == 200
    test_db.refresh(repository)
    test_db.refresh(storage)
    assert repository.path == "/repositories/app-new"
    assert storage.cache_path == "/repositories/app-new"


@pytest.mark.unit
def test_update_cloud_mirror_remote_change_blocks_unverified_non_empty_target(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    old_remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    new_remote = RcloneRemote(name="archive-s3", provider="s3", config_source="managed")
    repository = Repository(
        name="App",
        path="/repositories/app",
        encryption="none",
        repository_type="local",
    )
    test_db.add_all([old_remote, new_remote, repository])
    test_db.commit()
    test_db.refresh(old_remote)
    test_db.refresh(new_remote)
    test_db.refresh(repository)
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        rclone_remote_id=old_remote.id,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path="/repositories/app",
        sync_policy="manual",
        sync_status="current",
        sync_direction="primary_to_remote",
    )
    test_db.add(storage)
    test_db.commit()
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[{"Name": "existing", "IsDir": True}]),
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={"rclone_remote_id": new_remote.id},
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.rclone.remotePathNotVerified"
    )
    test_db.refresh(storage)
    assert storage.rclone_remote_id == old_remote.id


@pytest.mark.unit
def test_update_ssh_cloud_mirror_remote_change_rolls_back_on_preflight_failure(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    old_remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    new_remote = RcloneRemote(name="archive-s3", provider="s3", config_source="managed")
    connection = SSHConnection(host="storage.example", username="borg", port=22)
    repository = Repository(
        name="SSH App",
        path="ssh://borg@storage.example:22/backups/app",
        encryption="none",
        repository_type="ssh",
        connection_id=1,
        execution_target="ssh",
        executor_type="server",
    )
    test_db.add_all([old_remote, new_remote, connection, repository])
    test_db.commit()
    test_db.refresh(old_remote)
    test_db.refresh(new_remote)
    test_db.refresh(connection)
    repository.connection_id = connection.id
    test_db.commit()
    test_db.refresh(repository)
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        rclone_remote_id=old_remote.id,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path=None,
        sync_policy="manual",
        sync_status="current",
        sync_direction="sshfs_mount_to_remote",
    )
    test_db.add(storage)
    test_db.commit()
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[{"Name": "existing", "IsDir": True}]),
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={"rclone_remote_id": new_remote.id},
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.rclone.remotePathNotVerified"
    )
    test_db.refresh(storage)
    assert storage.rclone_remote_id == old_remote.id
    assert storage.rclone_remote_path == "borg-ui/repositories/app"
    assert storage.cache_path is None
    assert storage.sync_direction == "sshfs_mount_to_remote"


@pytest.mark.unit
def test_rclone_storage_migration_downgrade_drops_created_tables():
    migration = importlib.import_module(
        "app.database.migrations.113_add_rclone_storage"
    )
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        migration.upgrade(db)
        inspector = inspect(engine)
        assert inspector.has_table("rclone_remotes")
        assert inspector.has_table("repository_storage")
        assert inspector.has_table("rclone_sync_jobs")

        migration.downgrade(db)
        inspector = inspect(engine)
        assert not inspector.has_table("rclone_sync_jobs")
        assert not inspector.has_table("repository_storage")
        assert not inspector.has_table("rclone_remotes")
    finally:
        db.close()


@pytest.mark.unit
def test_rclone_storage_migration_runs_with_connection():
    migration = importlib.import_module(
        "app.database.migrations.113_add_rclone_storage"
    )
    engine = create_engine("sqlite:///:memory:")

    with engine.connect() as connection:
        migration.upgrade(connection)
        inspector = inspect(engine)
        assert inspector.has_table("rclone_remotes")
        assert inspector.has_table("repository_storage")
        assert inspector.has_table("rclone_sync_jobs")


@pytest.mark.unit
def test_rclone_storage_migration_uses_postgresql_identity_columns():
    migration = importlib.import_module(
        "app.database.migrations.113_add_rclone_storage"
    )

    class FakeDialect:
        name = "postgresql"

    class FakeBind:
        dialect = FakeDialect()

    class FakeDb:
        def get_bind(self):
            return FakeBind()

    assert migration._id_primary_key(FakeDb()) == (
        "id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"
    )
    assert migration._timestamp_type(FakeDb()) == "TIMESTAMP"
