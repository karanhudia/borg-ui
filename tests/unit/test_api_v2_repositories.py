import base64
import json
from unittest.mock import AsyncMock, patch

from cryptography.fernet import Fernet

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.borg2 import BORG2_ENCRYPTION_MODES
from app.config import settings
from app.database.models import LicensingState, Repository, SystemSettings
from app.database.models import SSHConnection, SSHKey


def _enable_borg_v2(test_db, **settings):
    system_settings = test_db.query(SystemSettings).first()
    if system_settings is None:
        system_settings = SystemSettings(**settings)
        test_db.add(system_settings)
    else:
        for key, value in settings.items():
            setattr(system_settings, key, value)

    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="test-instance-v2-repositories")
        test_db.add(state)
    state.plan = "pro"
    state.status = "active"
    state.is_trial = False
    test_db.commit()


def _create_v2_repo(
    test_db,
    *,
    name="V2 Repo",
    path="/tmp/v2-repo",
    repository_type="local",
    source_directories=None,
    bypass_lock=False,
):
    repo = Repository(
        name=name,
        path=path,
        encryption="repokey-aes-ocb",
        compression="lz4",
        repository_type=repository_type,
        borg_version=2,
        source_directories=json.dumps(source_directories) if source_directories is not None else None,
        bypass_lock=bypass_lock,
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


@pytest.mark.unit
class TestV2RepositoryRoutes:
    def test_encryption_modes_are_feature_gated(self, test_client: TestClient, admin_headers):
        response = test_client.get("/api/v2/repositories/encryption-modes", headers=admin_headers)

        assert response.status_code == 403
        assert response.json()["detail"]["key"] == "backend.errors.plan.featureNotAvailable"

    def test_encryption_modes_success(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)

        response = test_client.get("/api/v2/repositories/encryption-modes", headers=admin_headers)

        assert response.status_code == 200
        assert response.json()["encryption_modes"] == BORG2_ENCRYPTION_MODES

    def test_create_repository_success(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        payload = {
            "name": "Borg 2 Repo",
            "path": "/tmp/v2-create-repo",
            "encryption": "repokey-aes-ocb",
            "compression": "lz4",
            "source_directories": ["/data/source-a", "/data/source-b"],
            "source_connection_id": 44,
        }

        with patch(
            "app.api.v2.repositories._rcreate",
            new=AsyncMock(return_value={"success": True, "already_existed": False, "stdout": "", "stderr": ""}),
        ) as mock_rcreate:
            response = test_client.post("/api/v2/repositories/", json=payload, headers=admin_headers)

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == payload["name"]
        assert body["path"] == payload["path"]
        assert body["borg_version"] == 2
        assert body["already_existed"] is False
        assert body["message"] == "backend.success.repo.created"

        repo = test_db.query(Repository).filter(Repository.name == payload["name"]).first()
        assert repo is not None
        assert repo.borg_version == 2
        assert json.loads(repo.source_directories) == payload["source_directories"]
        assert repo.source_ssh_connection_id == 44
        mock_rcreate.assert_awaited_once()

    def test_create_repository_rejects_invalid_encryption(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)

        response = test_client.post(
            "/api/v2/repositories/",
            json={
                "name": "Bad Repo",
                "path": "/tmp/v2-bad-repo",
                "encryption": "totally-invalid",
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.repo.invalidEncryption"

    def test_create_repository_requires_admin(self, test_client: TestClient, auth_headers, test_db):
        _enable_borg_v2(test_db)

        response = test_client.post(
            "/api/v2/repositories/",
            json={
                "name": "Viewer Repo",
                "path": "/tmp/v2-viewer-repo",
                "encryption": "none",
            },
            headers=auth_headers,
        )

        assert response.status_code == 403
        assert response.json()["detail"]["key"] == "backend.errors.repo.adminAccessRequired"

    def test_create_repository_rejects_missing_ssh_connection(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)

        response = test_client.post(
            "/api/v2/repositories/",
            json={
                "name": "SSH Repo",
                "path": "ssh://example.com/backups/repo",
                "connection_id": 999,
            },
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.repo.sshConnectionNotFound"

    def test_create_repository_with_ssh_connection_uses_ssh_key_rsh(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)

        cipher = Fernet(base64.urlsafe_b64encode(settings.secret_key.encode()[:32]))
        ssh_key = SSHKey(
            name="repo-key",
            public_key="ssh-rsa AAAA",
            private_key=cipher.encrypt(b"private-key").decode(),
            key_type="rsa",
        )
        test_db.add(ssh_key)
        test_db.commit()
        test_db.refresh(ssh_key)

        connection = SSHConnection(
            ssh_key_id=ssh_key.id,
            host="example.com",
            username="borg",
            port=22,
        )
        test_db.add(connection)
        test_db.commit()
        test_db.refresh(connection)

        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (b"", b"")

        session_factory = sessionmaker(bind=test_db.get_bind(), autocommit=False, autoflush=False)
        with patch("app.services.v2.repository_service.SessionLocal", session_factory):
            with patch("app.services.v2.repository_service.borg2._run", return_value={"success": True, "stdout": "", "stderr": ""}) as mock_run:
                response = test_client.post(
                    "/api/v2/repositories/",
                    json={
                        "name": "SSH Borg 2 Repo",
                        "path": "ssh://example.com/backups/repo",
                        "encryption": "none",
                        "connection_id": connection.id,
                    },
                    headers=admin_headers,
                )

        assert response.status_code == 201
        env = mock_run.call_args.kwargs["env"]
        assert env["BORG_RSH"].startswith("ssh ")
        assert "-i" in env["BORG_RSH"]

    def test_create_repository_reports_init_failure(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)

        with patch(
            "app.api.v2.repositories._rcreate",
            new=AsyncMock(return_value={"success": False, "already_existed": False, "stdout": "", "stderr": "boom"}),
        ):
            response = test_client.post(
                "/api/v2/repositories/",
                json={
                    "name": "Init Fail Repo",
                    "path": "/tmp/v2-init-fail",
                    "encryption": "none",
                },
                headers=admin_headers,
            )

        assert response.status_code == 500
        assert response.json()["detail"]["key"] == "backend.errors.repo.initFailed"

    def test_create_repository_rejects_duplicate_name(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        _create_v2_repo(test_db, name="Existing Repo", path="/tmp/existing-repo")

        response = test_client.post(
            "/api/v2/repositories/",
            json={
                "name": "Existing Repo",
                "path": "/tmp/new-repo",
                "encryption": "none",
            },
            headers=admin_headers,
        )

        assert response.status_code == 409
        assert response.json()["detail"]["key"] == "backend.errors.repo.nameExists"

    def test_import_repository_rejects_verification_failure(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)

        with patch(
            "app.api.v2.repositories._rinfo",
            new=AsyncMock(return_value={"success": False, "stderr": "repo missing"}),
        ):
            response = test_client.post(
                "/api/v2/repositories/import",
                json={
                    "name": "Import Repo",
                    "path": "/tmp/v2-import-repo",
                    "encryption": "none",
                },
                headers=admin_headers,
            )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.repo.verificationFailed"

    def test_import_repository_success(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)

        with patch(
            "app.api.v2.repositories._rinfo",
            new=AsyncMock(return_value={"success": True, "stdout": json.dumps({"repository": {"id": 1}}), "stderr": ""}),
        ):
            response = test_client.post(
                "/api/v2/repositories/import",
                json={
                    "name": "Imported Repo",
                    "path": "/tmp/v2-import-success",
                    "encryption": "none",
                    "source_directories": ["/data/source"],
                    "source_connection_id": 55,
                    "custom_flags": "--stats",
                    "pre_backup_script": "echo pre",
                    "post_backup_script": "echo post",
                },
                headers=admin_headers,
            )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Imported Repo"
        assert body["borg_version"] == 2
        repo = test_db.query(Repository).filter(Repository.name == "Imported Repo").first()
        assert repo is not None
        assert repo.source_ssh_connection_id == 55
        assert repo.custom_flags == "--stats"
        assert repo.pre_backup_script == "echo pre"
        assert repo.post_backup_script == "echo post"

    def test_import_repository_writes_keyfile_content_for_verification(
        self, test_client: TestClient, admin_headers, test_db, tmp_path
    ):
        _enable_borg_v2(test_db)

        fake_home = tmp_path / "home"
        fake_home.mkdir()

        with patch("app.api.v2.repositories.os.path.expanduser", return_value=str(fake_home)), patch(
            "app.api.v2.repositories._rinfo",
            new=AsyncMock(return_value={"success": True, "stdout": json.dumps({"repository": {"id": 1}}), "stderr": ""}),
        ):
            response = test_client.post(
                "/api/v2/repositories/import",
                json={
                    "name": "Imported Keyfile Repo",
                    "path": "/tmp/v2-import-keyfile",
                    "encryption": "keyfile-aes-ocb",
                    "keyfile_content": "BORG_KEY sample-key",
                    "source_directories": ["/data/source"],
                },
                headers=admin_headers,
            )

        assert response.status_code == 201
        repo = test_db.query(Repository).filter(Repository.name == "Imported Keyfile Repo").first()
        assert repo is not None
        assert repo.has_keyfile is True
        keyfile_name = "tmp_v2_import_keyfile"
        assert (fake_home / ".config" / "borg" / "keys" / keyfile_name).exists()

    def test_import_repository_rejects_duplicate_path(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        _create_v2_repo(test_db, name="Existing Import", path="/tmp/existing-import")

        response = test_client.post(
            "/api/v2/repositories/import",
            json={
                "name": "Another Import",
                "path": "/tmp/existing-import",
                "encryption": "none",
            },
            headers=admin_headers,
        )

        assert response.status_code == 409
        assert response.json()["detail"]["key"] == "backend.errors.repo.pathExists"

    def test_get_repository_info_merges_rinfo_and_disk_usage(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db, path="/tmp/v2-info-repo")

        with patch(
            "app.api.v2.repositories.borg2.info_repo",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "stdout": json.dumps({"archives": [{"name": "archive-1"}]}),
                    "stderr": "",
                }
            ),
        ) as mock_info:
            with patch(
                "app.api.v2.repositories.borg2.rinfo",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "stdout": json.dumps(
                            {
                                "repository": {"id": 9},
                                "encryption": {"mode": "repokey-aes-ocb"},
                            }
                        ),
                        "stderr": "",
                    }
                ),
            ) as mock_rinfo:
                with patch("app.api.v2.repositories.calculate_path_size_bytes", new=AsyncMock(return_value=12345)) as mock_size:
                    response = test_client.get(f"/api/v2/repositories/{repo.id}/info", headers=admin_headers)

        assert response.status_code == 200
        info = response.json()["info"]
        assert info["repository"] == {"id": 9}
        assert info["encryption"] == {"mode": "repokey-aes-ocb"}
        assert info["rinfo_stats"] == {"unique_csize": 12345, "unique_size": 12345}
        mock_info.assert_awaited_once()
        mock_rinfo.assert_awaited_once()
        mock_size.assert_awaited_once_with([repo.path], timeout=30)

    def test_get_repository_info_returns_500_on_info_failure(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db, path="/tmp/v2-info-fail")

        with patch(
            "app.api.v2.repositories.borg2.info_repo",
            new=AsyncMock(return_value={"success": False, "stdout": "", "stderr": "info failed"}),
        ):
            response = test_client.get(f"/api/v2/repositories/{repo.id}/info", headers=admin_headers)

        assert response.status_code == 500
        assert response.json()["detail"]["key"] == "backend.errors.repo.infoFailed"

    def test_get_repository_info_returns_404_for_missing_repo(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)

        response = test_client.get("/api/v2/repositories/999/info", headers=admin_headers)

        assert response.status_code == 404
        assert response.json()["detail"]["key"] == "backend.errors.repo.notFound"

    def test_list_archives_respects_system_bypass_lock(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db, bypass_lock_on_list=True)
        repo = _create_v2_repo(test_db, path="/tmp/v2-list-repo")

        with patch(
            "app.api.v2.repositories.borg2.list_archives",
            new=AsyncMock(return_value={"success": True, "stdout": json.dumps({"archives": [{"name": "one"}]}), "stderr": ""}),
        ) as mock_list:
            response = test_client.get(f"/api/v2/repositories/{repo.id}/archives", headers=admin_headers)

        assert response.status_code == 200
        assert response.json() == {"archives": [{"name": "one"}], "borg_version": 2}
        mock_list.assert_awaited_once()
        assert mock_list.call_args.kwargs["bypass_lock"] is True

    def test_list_archives_returns_500_on_borg_failure(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)

        with patch(
            "app.api.v2.repositories.borg2.list_archives",
            new=AsyncMock(return_value={"success": False, "stdout": "", "stderr": "list failed"}),
        ):
            response = test_client.get(f"/api/v2/repositories/{repo.id}/archives", headers=admin_headers)

        assert response.status_code == 500
        assert response.json()["detail"]["key"] == "backend.errors.repo.listFailed"

    def test_list_archives_returns_500_on_borg_failure(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)

        with patch(
            "app.api.v2.repositories.borg2.list_archives",
            new=AsyncMock(return_value={"success": False, "stdout": "", "stderr": "boom"}),
        ):
            response = test_client.get(f"/api/v2/repositories/{repo.id}/archives", headers=admin_headers)

        assert response.status_code == 500
        assert response.json()["detail"]["key"] == "backend.errors.repo.listFailed"

    def test_get_repository_stats_success(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)

        with patch(
            "app.api.v2.repositories.borg2.rinfo",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "stdout": json.dumps({"repository": {"id": 7}, "encryption": {"mode": "none"}}),
                    "stderr": "",
                }
            ),
        ) as mock_rinfo:
            response = test_client.get(f"/api/v2/repositories/{repo.id}/stats", headers=admin_headers)

        assert response.status_code == 200
        assert response.json()["stats"] == {"repository": {"id": 7}, "encryption": {"mode": "none"}}
        assert response.json()["borg_version"] == 2
        mock_rinfo.assert_awaited_once()

    def test_get_repository_stats_returns_500_on_borg_failure(self, test_client: TestClient, admin_headers, test_db):
        _enable_borg_v2(test_db)
        repo = _create_v2_repo(test_db)

        with patch(
            "app.api.v2.repositories.borg2.rinfo",
            new=AsyncMock(return_value={"success": False, "stdout": "", "stderr": "stats failed"}),
        ):
            response = test_client.get(f"/api/v2/repositories/{repo.id}/stats", headers=admin_headers)

        assert response.status_code == 500
        assert response.json()["detail"]["key"] == "backend.errors.repo.infoFailed"
