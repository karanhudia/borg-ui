"""
Unit tests for filesystem API endpoints and helpers.
"""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.api import filesystem
from app.database.models import SSHConnection, SSHKey


def _encrypt_private_key(secret_key: str, private_key: str) -> str:
    key = base64.urlsafe_b64encode(secret_key.encode()[:32])
    return Fernet(key).encrypt(private_key.encode()).decode()


def _create_ssh_key_record(test_db, secret_key: str) -> SSHKey:
    ssh_key = SSHKey(
        name="ssh-key",
        public_key="ssh-rsa AAA",
        private_key=_encrypt_private_key(secret_key, "PRIVATE KEY"),
    )
    test_db.add(ssh_key)
    test_db.commit()
    test_db.refresh(ssh_key)
    return ssh_key


@pytest.mark.unit
class TestFilesystemBrowseLocal:
    def test_browse_local_filesystem_detects_borg_repo_and_mounts(
        self,
        test_client: TestClient,
        admin_headers,
        monkeypatch,
        tmp_path,
    ):
        root = tmp_path / "browse-root"
        root.mkdir()

        local_mount = root / "mount-point"
        local_mount.mkdir()
        (local_mount / "config").write_text("[repository]\n")
        (local_mount / "data").mkdir()

        plain_dir = root / "plain-dir"
        plain_dir.mkdir()
        (root / "note.txt").write_text("hello")

        monkeypatch.setattr(
            filesystem.settings.__class__,
            "get_local_mount_points",
            lambda self: [str(local_mount)],
        )

        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": str(root), "connection_type": "local"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["current_path"] == str(root)
        assert data["is_inside_local_mount"] is False

        items = data["items"]
        assert [item["name"] for item in items][:2] == ["mount-point", "plain-dir"]
        mount_item = next(item for item in items if item["name"] == "mount-point")
        assert mount_item["is_local_mount"] is True
        assert mount_item["is_borg_repo"] is True

    def test_browse_local_filesystem_rejects_missing_path(
        self,
        test_client: TestClient,
        admin_headers,
    ):
        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": "/definitely/missing", "connection_type": "local"},
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.filesystem.pathNotFound"

    def test_browse_local_filesystem_rejects_non_directory(
        self,
        test_client: TestClient,
        admin_headers,
        tmp_path,
    ):
        file_path = tmp_path / "not-a-dir.txt"
        file_path.write_text("content")

        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": str(file_path), "connection_type": "local"},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.filesystem.pathNotDirectory"

    def test_browse_filesystem_rejects_invalid_connection_type(
        self,
        test_client: TestClient,
        admin_headers,
    ):
        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": "/tmp", "connection_type": "bogus"},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.filesystem.invalidConnectionType"

    @pytest.mark.asyncio
    async def test_browse_local_filesystem_permission_denied_raises_403(self, tmp_path):
        with patch.object(filesystem.os, "listdir", side_effect=PermissionError):
            with pytest.raises(filesystem.HTTPException) as exc:
                await filesystem.browse_local_filesystem(str(tmp_path))

        assert exc.value.status_code == 403
        assert exc.value.detail["key"] == "backend.errors.filesystem.permissionDenied"


@pytest.mark.unit
class TestFilesystemBrowseSSH:
    def test_browse_filesystem_ssh_uses_saved_default_path(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        ssh_connection = SSHConnection(
            ssh_key_id=123,
            host="example.com",
            username="borg",
            port=22,
            default_path="/srv/backups",
        )
        test_db.add(ssh_connection)
        test_db.commit()

        with patch.object(
            filesystem,
            "browse_ssh_filesystem",
            new=AsyncMock(
                return_value=filesystem.BrowseResponse(
                    current_path="/srv/backups",
                    items=[],
                    parent_path="/srv",
                    is_inside_local_mount=False,
                )
            ),
        ) as mock_browse:
            response = test_client.get(
                "/api/filesystem/browse",
                params={
                    "path": "/",
                    "connection_type": "ssh",
                    "ssh_key_id": 123,
                    "host": "example.com",
                    "username": "borg",
                    "port": 22,
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        mock_browse.assert_awaited_once()
        assert mock_browse.await_args.args[0] == "/srv/backups"

    @pytest.mark.asyncio
    async def test_browse_ssh_filesystem_parses_listing_and_borg_repo(
        self,
        test_db,
        monkeypatch,
    ):
        secret_key = "a" * 32
        monkeypatch.setattr(filesystem.settings, "secret_key", secret_key, raising=False)
        monkeypatch.setattr(filesystem.settings.__class__, "get_local_mount_points", lambda self: [])

        ssh_key = SSHKey(
            name="ssh-key",
            public_key="ssh-rsa AAA",
            private_key=_encrypt_private_key(secret_key, "PRIVATE KEY"),
        )
        test_db.add(ssh_key)
        test_db.commit()
        test_db.refresh(ssh_key)

        def run_side_effect(cmd, *args, **kwargs):
            if cmd[0] == "sftp":
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        "total 8\n"
                        "drwxr-xr-x 2 user group 4096 Nov 26 10:30 archives\n"
                        "-rw-r--r-- 1 user group 12 Nov 26 10:31 notes.txt\n"
                    ),
                    stderr="",
                )
            return SimpleNamespace(returncode=0, stdout="config\ndata\n", stderr="")

        monkeypatch.setattr(filesystem.subprocess, "run", run_side_effect)
        monkeypatch.setattr(filesystem, "is_borg_repository_ssh", lambda *args, **kwargs: True)

        response = await filesystem.browse_ssh_filesystem(
            path="/remote",
            ssh_key_id=ssh_key.id,
            host="example.com",
            username="borg",
            port=22,
            db=test_db,
        )

        assert response.current_path == "/remote"
        assert response.parent_path == "/"
        assert response.is_inside_local_mount is False
        assert [item.name for item in response.items] == ["archives", "notes.txt"]
        assert response.items[0].is_directory is True
        assert response.items[0].is_borg_repo is True
        assert response.items[1].is_directory is False

    @pytest.mark.asyncio
    async def test_browse_ssh_filesystem_missing_key_returns_404(self, test_db):
        with pytest.raises(filesystem.HTTPException) as exc:
            await filesystem.browse_ssh_filesystem(
                path="/remote",
                ssh_key_id=9999,
                host="example.com",
                username="borg",
                port=22,
                db=test_db,
            )

        assert exc.value.status_code == 404
        assert exc.value.detail["key"] == "backend.errors.ssh.sshKeyNotFound"

    def test_browse_filesystem_missing_ssh_params_returns_400(
        self,
        test_client: TestClient,
        admin_headers,
    ):
        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": "/remote", "connection_type": "ssh"},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.filesystem.sshParamsRequired"


@pytest.mark.unit
class TestFilesystemValidationAndCreateFolder:
    def test_validate_path_local_detects_borg_repo(
        self,
        test_client: TestClient,
        admin_headers,
        monkeypatch,
        tmp_path,
    ):
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "config").write_text("[repository]\n")
        (repo_path / "data").mkdir()

        monkeypatch.setattr(
            filesystem.settings.__class__,
            "get_local_mount_points",
            lambda self: [],
        )

        response = test_client.post(
            "/api/filesystem/validate-path",
            params={"path": str(repo_path), "connection_type": "local"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data == {
            "exists": True,
            "is_directory": True,
            "is_borg_repo": True,
            "path": str(repo_path),
        }

    def test_validate_path_ssh_missing_params_returns_400(
        self,
        test_client: TestClient,
        admin_headers,
    ):
        response = test_client.post(
            "/api/filesystem/validate-path",
            params={"path": "/remote", "connection_type": "ssh"},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.filesystem.sshParamsRequired"

    def test_validate_path_rejects_invalid_connection_type(
        self,
        test_client: TestClient,
        admin_headers,
    ):
        response = test_client.post(
            "/api/filesystem/validate-path",
            params={"path": "/tmp", "connection_type": "bogus"},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.filesystem.invalidConnectionType"

    @pytest.mark.asyncio
    async def test_validate_path_ssh_success(
        self,
        test_db,
        monkeypatch,
    ):
        secret_key = "a" * 32
        monkeypatch.setattr(filesystem.settings, "secret_key", secret_key, raising=False)

        ssh_key = SSHKey(
            name="validate-ssh",
            public_key="ssh-rsa AAA",
            private_key=_encrypt_private_key(secret_key, "PRIVATE KEY"),
        )
        test_db.add(ssh_key)
        test_db.commit()
        test_db.refresh(ssh_key)

        monkeypatch.setattr(
            filesystem.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="File: /remote\nType: directory\n", stderr=""),
        )
        monkeypatch.setattr(filesystem, "is_borg_repository_ssh", lambda *args, **kwargs: True)

        payload = await filesystem.validate_path(
            path="/remote",
            connection_type="ssh",
            ssh_key_id=ssh_key.id,
            host="example.com",
            username="borg",
            port=22,
            current_user=SimpleNamespace(username="admin"),
            db=test_db,
        )

        assert payload == {
            "exists": True,
            "is_directory": True,
            "is_borg_repo": True,
            "path": "/remote",
        }

    def test_create_folder_local_success(
        self,
        test_client: TestClient,
        admin_headers,
        tmp_path,
    ):
        response = test_client.post(
            "/api/filesystem/create-folder",
            json={
                "path": str(tmp_path),
                "folder_name": "new-folder",
                "connection_type": "local",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert Path(data["path"]).exists()

    def test_create_folder_rejects_invalid_folder_name(
        self,
        test_client: TestClient,
        admin_headers,
        tmp_path,
    ):
        response = test_client.post(
            "/api/filesystem/create-folder",
            json={
                "path": str(tmp_path),
                "folder_name": "../",
                "connection_type": "local",
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.filesystem.invalidFolderName"

    def test_create_folder_local_existing_directory_returns_400(
        self,
        test_client: TestClient,
        admin_headers,
        tmp_path,
    ):
        existing = tmp_path / "existing-folder"
        existing.mkdir()

        response = test_client.post(
            "/api/filesystem/create-folder",
            json={
                "path": str(tmp_path),
                "folder_name": "existing-folder",
                "connection_type": "local",
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.filesystem.folderAlreadyExists"

    def test_create_folder_local_permission_error_returns_403(
        self,
        test_client: TestClient,
        admin_headers,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(filesystem.os, "makedirs", lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError()))

        response = test_client.post(
            "/api/filesystem/create-folder",
            json={
                "path": str(tmp_path),
                "folder_name": "new-folder",
                "connection_type": "local",
            },
            headers=admin_headers,
        )

        assert response.status_code == 403
        assert response.json()["detail"]["key"] == "backend.errors.filesystem.permissionDeniedCreateFolder"

    def test_create_folder_ssh_missing_connection_details_returns_400(
        self,
        test_client: TestClient,
        admin_headers,
        tmp_path,
    ):
        response = test_client.post(
            "/api/filesystem/create-folder",
            json={
                "path": str(tmp_path),
                "folder_name": "remote-folder",
                "connection_type": "ssh",
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.filesystem.sshConnectionDetailsRequired"

    def test_validate_path_ssh_missing_key_returns_404(
        self,
        test_client: TestClient,
        admin_headers,
    ):
        response = test_client.post(
            "/api/filesystem/validate-path",
            params={
                "path": "/remote",
                "connection_type": "ssh",
                "ssh_key_id": 9999,
                "host": "example.com",
                "username": "borg",
                "port": 22,
            },
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.ssh.sshKeyNotFound"

    def test_create_folder_ssh_success(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        monkeypatch,
    ):
        secret_key = filesystem.settings.secret_key
        ssh_key = _create_ssh_key_record(test_db, secret_key)

        monkeypatch.setattr(
            filesystem.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
        )

        response = test_client.post(
            "/api/filesystem/create-folder",
            json={
                "path": "/remote",
                "folder_name": "new-folder",
                "connection_type": "ssh",
                "ssh_key_id": ssh_key.id,
                "host": "example.com",
                "username": "borg",
                "port": 22,
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["path"] == "/remote/new-folder"

    def test_create_folder_ssh_existing_directory_returns_400(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        monkeypatch,
    ):
        secret_key = filesystem.settings.secret_key
        ssh_key = _create_ssh_key_record(test_db, secret_key)

        monkeypatch.setattr(
            filesystem.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="File exists"),
        )

        response = test_client.post(
            "/api/filesystem/create-folder",
            json={
                "path": "/remote",
                "folder_name": "existing-folder",
                "connection_type": "ssh",
                "ssh_key_id": ssh_key.id,
                "host": "example.com",
                "username": "borg",
                "port": 22,
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.filesystem.folderAlreadyExists"
