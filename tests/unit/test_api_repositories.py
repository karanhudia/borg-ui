"""
Comprehensive unit tests for repositories API endpoints

These tests focus on:
- Authentication and authorization
- CRUD operations (database only)
- Input validation
- Error handling

Integration tests (test_api_repositories_integration.py) handle:
- Real borg repository operations
- Repository initialization
- Stats and info retrieval
- Import existing repositories
"""

import pytest
import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.core.security import get_password_hash
from app.database.models import (
    AgentMachine,
    CheckJob,
    LicensingState,
    Repository,
    RestoreCheckJob,
    ScheduledJob,
    SSHConnection,
    SystemSettings,
)


def _discard_background_coro(coro):
    coro.close()


def _enable_borg_v2(test_db):
    settings_row = test_db.query(SystemSettings).first()
    if settings_row is None:
        settings_row = SystemSettings()
        test_db.add(settings_row)

    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="test-instance-v2-repository-api")
        test_db.add(state)

    state.plan = "pro"
    state.status = "active"
    state.is_trial = False
    test_db.commit()


def _base_repository_payload(**overrides):
    payload = {
        "name": "Test Repo",
        "path": "/tmp/test-repo",
        "encryption": "none",
        "compression": "lz4",
        "repository_type": "local",
    }
    payload.update(overrides)
    return payload


@pytest.mark.unit
class TestRepositoriesListAndGet:
    """Test repository listing and retrieval"""

    def test_list_repositories_empty(self, test_client: TestClient, admin_headers):
        """Test listing repositories when none exist"""
        response = test_client.get("/api/repositories/", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "repositories" in data or isinstance(data, list)

    def test_list_repositories_with_data(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test listing repositories with data"""
        # Create a repository in the test database
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()

        response = test_client.get("/api/repositories/", headers=admin_headers)

        assert response.status_code == 200
        # Response format might be {"success": true, "repositories": [...]} or just [...]
        data = response.json()
        if isinstance(data, dict):
            assert "repositories" in data
            repos = data["repositories"]
        else:
            repos = data

        assert len(repos) >= 1

    def test_list_repositories_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test listing repositories returns 200 and correct structure"""
        # Create test repositories
        repo1 = Repository(
            name="Repo 1", path="/repo1", encryption="none", repository_type="local"
        )
        repo2 = Repository(
            name="Repo 2", path="/repo2", encryption="repokey", repository_type="ssh"
        )
        test_db.add_all([repo1, repo2])
        test_db.commit()

        response = test_client.get("/api/repositories/", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "repositories" in data
        assert len(data["repositories"]) >= 2

    def test_list_repositories_includes_inline_script_parameters(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Repo With Params",
            path="/repo-with-params",
            encryption="none",
            repository_type="local",
            pre_backup_script_parameters={"TARGET_DIR": "/srv/data"},
            post_backup_script_parameters={"STATUS_FILE": "/tmp/status"},
        )
        test_db.add(repo)
        test_db.commit()

        response = test_client.get("/api/repositories/", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        repos = data["repositories"] if isinstance(data, dict) else data
        matching = next(item for item in repos if item["path"] == "/repo-with-params")
        assert matching["pre_backup_script_parameters"] == {"TARGET_DIR": "/srv/data"}
        assert matching["post_backup_script_parameters"] == {
            "STATUS_FILE": "/tmp/status"
        }

    def test_list_repositories_includes_schedule_summary(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Repo With Schedule",
            path="/repo-scheduled",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        schedule = ScheduledJob(
            name="Daily Backup",
            cron_expression="0 2 * * *",
            repository_id=repo.id,
            enabled=True,
            next_run=datetime(2099, 4, 14, 2, 0, 0),
        )
        test_db.add(schedule)
        test_db.commit()

        response = test_client.get("/api/repositories/", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        repo_data = next(r for r in data["repositories"] if r["id"] == repo.id)
        assert repo_data["has_schedule"] is True
        assert repo_data["schedule_enabled"] is True
        assert repo_data["schedule_name"] == "Daily Backup"
        assert repo_data["next_run"] is not None

    def test_list_repositories_unauthorized(self, test_client: TestClient):
        """Test listing repositories without authentication"""
        response = test_client.get("/api/repositories/")

        assert response.status_code == 401

    def test_list_repositories_no_auth(self, test_client: TestClient):
        """Test listing repositories without authentication returns 403"""
        response = test_client.get("/api/repositories/")

        assert response.status_code == 401

    def test_list_repositories_pagination(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test listing repositories with pagination"""
        # Create multiple repositories
        for i in range(5):
            repo = Repository(
                name=f"Pagination Repo {i}",
                path=f"/tmp/page-repo-{i}",
                encryption="none",
                compression="lz4",
                repository_type="local",
            )
            test_db.add(repo)
        test_db.commit()

        response = test_client.get(
            "/api/repositories/",
            params={"limit": 2, "offset": 0},
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_search_repositories_by_name(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test searching repositories by name"""
        repo = Repository(
            name="Searchable Repository",
            path="/tmp/search-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()

        response = test_client.get(
            "/api/repositories/", params={"search": "Searchable"}, headers=admin_headers
        )

        assert response.status_code == 200

    def test_get_repository_by_id(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test getting a specific repository"""
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/repositories/{repo.id}", headers=admin_headers
        )

        assert response.status_code == 200

    # NOTE: Repository retrieval with stats is tested in integration tests
    # (test_api_repositories_integration.py) with real borg repositories

    def test_get_nonexistent_repository(self, test_client: TestClient, admin_headers):
        """Test getting a repository that doesn't exist"""
        response = test_client.get("/api/repositories/99999", headers=admin_headers)

        assert response.status_code == 404

    def test_get_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test getting non-existent repository returns 404"""
        response = test_client.get("/api/repositories/99999", headers=admin_headers)

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"] == "backend.errors.repo.repositoryNotFound"
        )

    def test_get_repository_by_id_negative_id(
        self, test_client: TestClient, admin_headers
    ):
        """Test getting repository with negative ID"""
        response = test_client.get("/api/repositories/-1", headers=admin_headers)

        assert response.status_code == 404

    def test_get_repository_details(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test getting repository details"""
        repo = Repository(
            name="Detail Test Repo",
            path="/tmp/detail-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
            source_directories=json.dumps(["/home/user"]),
            exclude_patterns=json.dumps(["*.tmp"]),
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/repositories/{repo.id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        repository = data.get("repository", data)
        assert repository["name"] == "Detail Test Repo"


@pytest.mark.unit
class TestRepositoriesCreate:
    """Test repository creation"""

    def test_create_local_repository(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test creating local repository"""
        with (
            patch(
                "app.api.repositories.initialize_borg_repository",
                new=AsyncMock(return_value={"success": True}),
            ),
            patch("app.api.repositories.mqtt_service.sync_state_with_db"),
        ):
            response = test_client.post(
                "/api/repositories/",
                json={
                    "name": "Local Backup Repo",
                    "path": "/tmp/local-repo",
                    "encryption": "none",
                    "compression": "lz4",
                    "repository_type": "local",
                    "source_directories": ["/tmp/source"],
                },
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_create_ssh_repository(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test creating SSH repository"""
        connection = SSHConnection(host="server", username="user", port=22)
        test_db.add(connection)
        test_db.commit()
        test_db.refresh(connection)

        with (
            patch(
                "app.api.repositories.initialize_borg_repository",
                new=AsyncMock(return_value={"success": True}),
            ),
            patch("app.api.repositories.mqtt_service.sync_state_with_db"),
        ):
            response = test_client.post(
                "/api/repositories/",
                json={
                    "name": "Remote SSH Repo",
                    "path": "/path/to/repo",
                    "encryption": "repokey",
                    "passphrase": "test-passphrase",
                    "compression": "zstd",
                    "repository_type": "ssh",
                    "connection_id": connection.id,
                    "source_directories": ["/tmp/source"],
                },
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_create_agent_repository_records_target_without_server_init(
        self, test_client: TestClient, admin_headers, test_db
    ):
        agent = AgentMachine(
            name="Laptop",
            agent_id="agt_laptop",
            token_hash=get_password_hash("borgui_agent_secret"),
            token_prefix="borgui_agent_secret"[:20],
            status="online",
        )
        test_db.add(agent)
        test_db.commit()
        test_db.refresh(agent)

        with (
            patch(
                "app.api.repositories.initialize_borg_repository",
                new=AsyncMock(return_value={"success": True}),
            ) as initialize,
            patch("app.api.repositories.mqtt_service.sync_state_with_db"),
        ):
            response = test_client.post(
                "/api/repositories/",
                json={
                    "name": "Agent Repo",
                    "path": "/agent/repo",
                    "encryption": "none",
                    "compression": "lz4",
                    "source_directories": ["/home/user/docs"],
                    "execution_target": "agent",
                    "agent_machine_id": agent.id,
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        initialize.assert_not_awaited()
        repo = test_db.query(Repository).filter_by(name="Agent Repo").first()
        assert repo.execution_target == "agent"
        assert repo.agent_machine_id == agent.id
        assert repo.path == "/agent/repo"

    def test_create_repository_missing_name(
        self, test_client: TestClient, admin_headers
    ):
        """Test creating repository without name"""
        response = test_client.post(
            "/api/repositories/",
            json={"path": "/tmp/test-repo", "encryption": "none", "compression": "lz4"},
            headers=admin_headers,
        )

        assert response.status_code == 422  # Validation error

    def test_create_repository_missing_path(
        self, test_client: TestClient, admin_headers
    ):
        """Test creating repository without path"""
        response = test_client.post(
            "/api/repositories/",
            json={"name": "No Path Repo", "encryption": "none", "compression": "lz4"},
            headers=admin_headers,
        )

        assert response.status_code == 422

    def test_create_repository_invalid_encryption(
        self, test_client: TestClient, admin_headers
    ):
        """Test creating repository with invalid encryption type"""
        response = test_client.post(
            "/api/repositories/",
            json={
                "name": "Invalid Encryption",
                "path": "/tmp/test-repo",
                "encryption": "invalid-encryption-type",
                "compression": "lz4",
                "repository_type": "local",
            },
            headers=admin_headers,
        )

        assert response.status_code == 400

    def test_create_repository_with_source_directories(
        self, test_client: TestClient, admin_headers
    ):
        """Test creating repository with source directories"""
        with (
            patch(
                "app.api.repositories.initialize_borg_repository",
                new=AsyncMock(return_value={"success": True}),
            ),
            patch("app.api.repositories.mqtt_service.sync_state_with_db"),
        ):
            response = test_client.post(
                "/api/repositories/",
                json={
                    "name": "Multi Source Repo",
                    "path": "/tmp/multi-source",
                    "encryption": "none",
                    "compression": "lz4",
                    "repository_type": "local",
                    "source_directories": ["/home/user/docs", "/home/user/photos"],
                },
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_create_repository_with_exclude_patterns(
        self, test_client: TestClient, admin_headers
    ):
        """Test creating repository with exclude patterns"""
        with (
            patch(
                "app.api.repositories.initialize_borg_repository",
                new=AsyncMock(return_value={"success": True}),
            ),
            patch("app.api.repositories.mqtt_service.sync_state_with_db"),
        ):
            response = test_client.post(
                "/api/repositories/",
                json={
                    "name": "Exclude Patterns Repo",
                    "path": "/tmp/exclude-repo",
                    "encryption": "none",
                    "compression": "lz4",
                    "repository_type": "local",
                    "exclude_patterns": ["*.tmp", "*.cache", "node_modules/"],
                },
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_create_repository_without_source_fields_stays_storage_only(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test basic repository creation does not persist legacy backup source fields"""
        with (
            patch(
                "app.api.repositories.initialize_borg_repository",
                new=AsyncMock(return_value={"success": True}),
            ),
            patch("app.api.repositories.mqtt_service.sync_state_with_db"),
        ):
            response = test_client.post(
                "/api/repositories/",
                json={
                    "name": "Storage Only Repo",
                    "path": "/tmp/storage-only-repo",
                    "encryption": "none",
                    "compression": "lz4",
                    "repository_type": "local",
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        repo = (
            test_db.query(Repository)
            .filter(Repository.name == "Storage Only Repo")
            .one()
        )
        assert repo.source_directories is None
        assert repo.exclude_patterns is None
        assert repo.source_ssh_connection_id is None

    def test_create_repository_validation_error(
        self, test_client: TestClient, admin_headers
    ):
        """Test repository creation with missing required fields returns 422"""
        response = test_client.post(
            "/api/repositories/",
            json={"name": "Incomplete Repo"},  # Missing path, encryption, etc.
            headers=admin_headers,
        )

        assert response.status_code == 422  # Validation error

    def test_create_repository_no_auth(self, test_client: TestClient):
        """Test creating repository without authentication returns 403"""
        response = test_client.post(
            "/api/repositories/",
            json={"name": "Test", "path": "/test", "encryption": "none"},
        )

        assert response.status_code == 401

    def test_create_repository_delegates_borg2_payloads_to_v2_api(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _enable_borg_v2(test_db)

        with patch(
            "app.api.v2.repositories._rcreate",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "already_existed": False,
                    "stdout": "",
                    "stderr": "",
                }
            ),
        ):
            response = test_client.post(
                "/api/repositories/",
                json={
                    "name": "Delegated Borg2 Repo",
                    "path": "/tmp/delegated-borg2-repo",
                    "borg_version": 2,
                    "encryption": "repokey-aes-ocb",
                    "compression": "lz4",
                    "source_directories": ["/data/source"],
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        repo = (
            test_db.query(Repository)
            .filter(Repository.name == "Delegated Borg2 Repo")
            .first()
        )
        assert repo is not None
        assert repo.borg_version == 2
        assert repo.encryption == "repokey-aes-ocb"

    def test_legacy_prune_route_dispatches_v2_repo_via_router(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _enable_borg_v2(test_db)
        repo = Repository(
            **_base_repository_payload(name="Legacy Prune V2", borg_version=2)
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.repositories.BorgRouter.prune", new_callable=AsyncMock
        ) as mock_prune:
            response = test_client.post(
                f"/api/repositories/{repo.id}/prune",
                json={"keep_daily": 7},
                headers=admin_headers,
            )

        assert response.status_code == 200
        mock_prune.assert_awaited_once()

    def test_create_repository_duplicate_path(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test creating repository with duplicate path"""
        # Create first repository
        repo = Repository(
            name="Existing",
            path="/duplicate/path",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()

        # Try to create second repository with same path
        response = test_client.post(
            "/api/repositories/",
            json={
                "name": "Duplicate",
                "path": "/duplicate/path",
                "encryption": "none",
                "repository_type": "local",
                "source_directories": ["/tmp/source"],
            },
            headers=admin_headers,
        )

        assert response.status_code == 400


@pytest.mark.unit
class TestRepositoriesUpdate:
    """Test repository update operations"""

    def test_update_repository_name(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test updating repository name"""
        repo = Repository(
            name="Old Name",
            path="/tmp/update-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.put(
            f"/api/repositories/{repo.id}",
            json={"name": "New Name"},
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_update_repository_compression(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test updating repository compression"""
        repo = Repository(
            name="Compression Test",
            path="/tmp/compression-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.put(
            f"/api/repositories/{repo.id}",
            json={"compression": "zstd"},
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_update_nonexistent_repository(
        self, test_client: TestClient, admin_headers
    ):
        """Test updating non-existent repository"""
        response = test_client.put(
            "/api/repositories/99999",
            json={"name": "Updated Name"},
            headers=admin_headers,
        )

        assert response.status_code == 404

    def test_update_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test updating non-existent repository returns 404 or 403"""
        response = test_client.put(
            "/api/repositories/99999", json={"name": "Updated"}, headers=admin_headers
        )

        assert response.status_code == 404

    def test_update_repository_empty_name(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test updating repository with empty name"""
        repo = Repository(
            name="Original",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.put(
            f"/api/repositories/{repo.id}",
            json={"name": ""},  # Empty name
            headers=admin_headers,
        )

        assert response.status_code == 200

    def test_update_repository_clear_source_connection_id(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test clearing source_connection_id when switching from remote to local source"""
        # Create repository with a remote source
        repo = Repository(
            name="Remote Source Repo",
            path="/tmp/remote-source-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
            source_ssh_connection_id=1,  # Initially has remote source
            source_directories=json.dumps(["/remote/data"]),
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        # Verify initial state
        assert repo.source_ssh_connection_id == 1

        # Update to clear source_connection_id (switch to local source)
        response = test_client.put(
            f"/api/repositories/{repo.id}",
            json={
                "source_connection_id": None,  # Explicitly clear it
                "source_directories": ["/local/data"],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(repo)
        assert repo.source_ssh_connection_id is None
        assert json.loads(repo.source_directories) == ["/local/data"]

    def test_update_repository_empty_source_lists_clear_legacy_source_settings(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test empty source and exclude lists remove legacy source settings"""
        repo = Repository(
            name="Legacy Source Repo",
            path="/tmp/legacy-source-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
            source_ssh_connection_id=1,
            source_directories=json.dumps(["/remote/data"]),
            exclude_patterns=json.dumps(["*.tmp"]),
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.put(
            f"/api/repositories/{repo.id}",
            json={
                "source_connection_id": None,
                "source_directories": [],
                "exclude_patterns": [],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(repo)
        assert repo.source_ssh_connection_id is None
        assert repo.source_directories is None
        assert repo.exclude_patterns is None

    def test_update_repository_type_local_to_ssh(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test updating repository type from local to SSH"""
        # Create local repository
        repo = Repository(
            name="Local Repo",
            path="/tmp/local-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        # Verify initial state
        assert repo.repository_type == "local"
        assert repo.host is None
        assert repo.username is None

        ssh_conn = SSHConnection(
            host="backup.example.com", username="backupuser", port=22
        )
        test_db.add(ssh_conn)
        test_db.commit()
        test_db.refresh(ssh_conn)

        with (
            patch(
                "app.api.repositories.BorgRouter.verify_repository",
                new=AsyncMock(return_value={"success": False}),
            ),
            patch(
                "app.api.repositories.BorgRouter.initialize_repository",
                new=AsyncMock(return_value={"success": True}),
            ),
            patch("app.api.repositories.mqtt_service.sync_state_with_db"),
        ):
            response = test_client.put(
                f"/api/repositories/{repo.id}",
                json={"connection_id": ssh_conn.id, "path": "/home/borg-backup"},
                headers=admin_headers,
            )

        assert response.status_code == 200
        test_db.refresh(repo)
        assert repo.repository_type == "ssh"
        assert repo.connection_id == ssh_conn.id
        assert repo.path == "ssh://backupuser@backup.example.com:22/home/borg-backup"

    def test_update_ssh_repository_path_reconstruction(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test that updating an SSH repository path properly reconstructs the SSH URL"""
        from app.database.models import SSHConnection, SSHKey

        # Create SSH key
        ssh_key = SSHKey(
            name="Test Key",
            private_key="encrypted_key_data",
            public_key="ssh-rsa AAAA...",
        )
        test_db.add(ssh_key)
        test_db.commit()

        # Create SSH connection
        ssh_conn = SSHConnection(
            host="host.local", username="user", port=22, ssh_key_id=ssh_key.id
        )
        test_db.add(ssh_conn)
        test_db.commit()

        # Create SSH repository with connection_id
        repo = Repository(
            name="SSH Repo",
            path="ssh://user@host.local:22/home/borg-backup",
            encryption="none",
            compression="lz4",
            connection_id=ssh_conn.id,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        # Verify initial state
        assert repo.path == "ssh://user@host.local:22/home/borg-backup"

        # Update with plain path (like wizard sends) - path should be reconstructed
        response = test_client.put(
            f"/api/repositories/{repo.id}",
            json={
                "path": "/home/borg-backup",  # Plain path without SSH URL
                "source_directories": ["/data", "/config"],  # Adding source dirs
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(repo)
        assert repo.path == "ssh://user@host.local:22/home/borg-backup"
        assert json.loads(repo.source_directories) == ["/data", "/config"]

    def test_update_repository_path_change_initializes_new_repo(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test that changing repository path to a non-existent location initializes a new borg repository"""
        import tempfile
        import shutil

        # Create a temporary directory for the test repositories
        temp_dir = tempfile.mkdtemp()

        try:
            # Create initial repository
            initial_path = f"{temp_dir}/initial-repo"
            os.makedirs(initial_path, exist_ok=True)

            # Create a minimal borg repository structure at initial path
            os.makedirs(f"{initial_path}/data", exist_ok=True)
            with open(f"{initial_path}/config", "w") as f:
                f.write("[repository]\nversion = 1\n")

            repo = Repository(
                name="Path Change Repo",
                path=initial_path,
                encryption="none",
                compression="lz4",
                repository_type="local",
            )
            test_db.add(repo)
            test_db.commit()
            test_db.refresh(repo)

            # Verify initial state
            assert repo.path == initial_path

            # Update to a NEW path that doesn't exist yet
            new_path = f"{temp_dir}/new-repo"
            with (
                patch(
                    "app.api.repositories.BorgRouter.verify_repository",
                    new=AsyncMock(side_effect=RuntimeError("missing repo")),
                ),
                patch(
                    "app.api.repositories.BorgRouter.initialize_repository",
                    new=AsyncMock(return_value={"success": True}),
                ),
                patch("app.api.repositories.mqtt_service.sync_state_with_db"),
            ):
                response = test_client.put(
                    f"/api/repositories/{repo.id}",
                    json={"path": new_path},
                    headers=admin_headers,
                )

            assert response.status_code == 200
            test_db.refresh(repo)
            assert repo.path == new_path
        finally:
            # Clean up temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_update_repository_path_to_existing_repo_does_not_reinit(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test that changing path to an existing borg repository doesn't reinitialize it"""
        import tempfile
        import shutil

        temp_dir = tempfile.mkdtemp()

        try:
            # Create two borg repositories
            initial_path = f"{temp_dir}/initial-repo"
            existing_repo_path = f"{temp_dir}/existing-repo"

            for path in [initial_path, existing_repo_path]:
                os.makedirs(path, exist_ok=True)
                os.makedirs(f"{path}/data", exist_ok=True)
                with open(f"{path}/config", "w") as f:
                    f.write("[repository]\nversion = 1\n")

            repo = Repository(
                name="Relocate Repo",
                path=initial_path,
                encryption="none",
                compression="lz4",
                repository_type="local",
            )
            test_db.add(repo)
            test_db.commit()
            test_db.refresh(repo)

            # Update to point to the existing borg repository
            with (
                patch(
                    "app.api.repositories.BorgRouter.verify_repository",
                    new=AsyncMock(return_value={"success": True}),
                ),
                patch("app.api.repositories.mqtt_service.sync_state_with_db"),
            ):
                response = test_client.put(
                    f"/api/repositories/{repo.id}",
                    json={"path": existing_repo_path},
                    headers=admin_headers,
                )

            assert response.status_code == 200
            test_db.refresh(repo)
            assert repo.path == existing_repo_path
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_update_repository_path_strips_whitespace(
        self, test_client: TestClient, admin_headers, test_db
    ):
        import tempfile
        import shutil

        temp_dir = tempfile.mkdtemp()

        try:
            initial_path = f"{temp_dir}/initial-repo"
            existing_repo_path = f"{temp_dir}/existing-repo"

            for path in [initial_path, existing_repo_path]:
                os.makedirs(path, exist_ok=True)
                os.makedirs(f"{path}/data", exist_ok=True)
                with open(f"{path}/config", "w") as f:
                    f.write("[repository]\nversion = 1\n")

            repo = Repository(
                name="Whitespace Repo",
                path=initial_path,
                encryption="none",
                compression="lz4",
                repository_type="local",
            )
            test_db.add(repo)
            test_db.commit()
            test_db.refresh(repo)

            with (
                patch(
                    "app.api.repositories.BorgRouter.verify_repository",
                    new=AsyncMock(return_value={"success": True}),
                ),
                patch("app.api.repositories.mqtt_service.sync_state_with_db"),
            ):
                response = test_client.put(
                    f"/api/repositories/{repo.id}",
                    json={"path": f"  {existing_repo_path}  "},
                    headers=admin_headers,
                )

            assert response.status_code == 200
            test_db.refresh(repo)
            assert repo.path == existing_repo_path
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_update_v2_repository_path_uses_borg2_reinit(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="V2 Path Change Repo",
            path="/tmp/v2-initial",
            encryption="repokey-aes-ocb",
            compression="lz4",
            repository_type="local",
            borg_version=2,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with (
            patch(
                "app.api.repositories.BorgRouter.verify_repository",
                new=AsyncMock(return_value={"success": False, "stderr": "missing"}),
            ) as mock_verify,
            patch(
                "app.api.repositories.BorgRouter.initialize_repository",
                new=AsyncMock(return_value={"success": True, "stderr": ""}),
            ) as mock_init,
            patch(
                "app.api.repositories.initialize_borg_repository",
                new=AsyncMock(return_value={"success": True}),
            ) as mock_v1_init,
            patch("app.api.repositories.mqtt_service.sync_state_with_db"),
        ):
            response = test_client.put(
                f"/api/repositories/{repo.id}",
                json={"path": "/tmp/v2-new-path"},
                headers=admin_headers,
            )

        assert response.status_code == 200
        mock_verify.assert_awaited_once()
        mock_init.assert_awaited_once()
        mock_v1_init.assert_not_awaited()

    def test_download_keyfile_uses_router_export_for_borg2_repository(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="V2 Keyfile Repo",
            path="/tmp/v2-keyfile",
            encryption="keyfile-aes-ocb",
            compression="lz4",
            repository_type="local",
            borg_version=2,
            has_keyfile=True,
            passphrase="secret",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        async def fake_export_keyfile(output_path):
            with open(output_path, "wb") as handle:
                handle.write(b"KEYDATA")
            return {"success": True}

        with patch(
            "app.api.repositories.BorgRouter.export_keyfile",
            new=AsyncMock(side_effect=fake_export_keyfile),
        ) as mock_export:
            response = test_client.get(
                f"/api/repositories/{repo.id}/keyfile", headers=admin_headers
            )

        assert response.status_code == 200
        assert response.content == b"KEYDATA"
        mock_export.assert_awaited_once()


@pytest.mark.unit
class TestRepositoriesDelete:
    """Test repository deletion"""

    def test_delete_repository(self, test_client: TestClient, admin_headers, test_db):
        """Test deleting repository"""
        repo = Repository(
            name="Delete Me",
            path="/tmp/delete-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.delete(
            f"/api/repositories/{repo.id}", headers=admin_headers
        )

        assert response.status_code == 200

    def test_delete_nonexistent_repository(
        self, test_client: TestClient, admin_headers
    ):
        """Test deleting non-existent repository"""
        response = test_client.delete("/api/repositories/99999", headers=admin_headers)

        assert response.status_code == 404

    def test_delete_repository_not_found(self, test_client: TestClient, admin_headers):
        """Test deleting non-existent repository returns 404 or 403"""
        response = test_client.delete("/api/repositories/99999", headers=admin_headers)

        assert response.status_code == 404

    def test_delete_repository_no_auth(self, test_client: TestClient):
        """Test deleting repository without authentication returns 403"""
        response = test_client.delete("/api/repositories/1")

        assert response.status_code == 401

    def test_delete_repository_twice(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test deleting repository twice returns 404 on second attempt"""
        repo = Repository(
            name="To Delete",
            path="/delete/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        repo_id = repo.id

        # First delete - may succeed or be forbidden
        first_response = test_client.delete(
            f"/api/repositories/{repo_id}", headers=admin_headers
        )

        # If first delete succeeded, second should return 404
        if first_response.status_code == 200:
            second_response = test_client.delete(
                f"/api/repositories/{repo_id}", headers=admin_headers
            )
            assert second_response.status_code == 404


@pytest.mark.unit
class TestRepositoriesStatistics:
    """Test repository statistics and info"""

    def test_get_repository_stats(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test getting repository statistics"""
        repo = Repository(
            name="Stats Repo",
            path="/tmp/stats-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.repositories.get_repository_stats",
            new=AsyncMock(return_value={"total_size": "1.00 GB"}),
        ):
            response = test_client.get(
                f"/api/repositories/{repo.id}/stats", headers=admin_headers
            )

        assert response.status_code == 200

    def test_get_repository_info(self, test_client: TestClient, admin_headers, test_db):
        """Test getting repository info"""
        repo = Repository(
            name="Info Repo",
            path="/tmp/info-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.repositories._run_repository_command",
            new=AsyncMock(return_value=(0, b'{"repository":{"id":"abc"}}', b"")),
        ):
            response = test_client.get(
                f"/api/repositories/{repo.id}/info", headers=admin_headers
            )

        assert response.status_code == 200

    def test_get_repository_info_uses_v2_command_shape_for_borg2_repo(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="V2 Info Repo",
            path="/tmp/v2-info-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
            borg_version=2,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with (
            patch("app.core.borg2.borg2.borg_cmd", "borg2"),
            patch(
                "app.api.repositories._run_repository_command",
                new=AsyncMock(return_value=(0, b'{"repository":{"id":"abc"}}', b"")),
            ) as mock_run,
        ):
            response = test_client.get(
                f"/api/repositories/{repo.id}/info",
                headers=admin_headers,
            )

        assert response.status_code == 200
        cmd = mock_run.await_args.args[2]
        assert cmd[0] == "borg2"
        assert "-r" in cmd
        assert "info" in cmd

    def test_get_repository_stats_not_found(
        self, test_client: TestClient, admin_headers
    ):
        """Test getting stats for non-existent repository returns 404"""
        response = test_client.get(
            "/api/repositories/99999/stats", headers=admin_headers
        )

        assert response.status_code == 404

    def test_get_repository_info_not_found(
        self, test_client: TestClient, admin_headers
    ):
        """Test getting info for non-existent repository returns 404"""
        response = test_client.get(
            "/api/repositories/99999/info", headers=admin_headers
        )

        assert response.status_code == 404

    def test_get_stats_no_auth(self, test_client: TestClient):
        """Test getting repository stats without authentication returns 403"""
        response = test_client.get("/api/repositories/1/stats")

        assert response.status_code == 401

    def test_get_info_no_auth(self, test_client: TestClient):
        """Test getting repository info without authentication returns 403"""
        response = test_client.get("/api/repositories/1/info")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_repository_stats_forwards_passphrase_for_encrypted_local_repo(
        self, test_db
    ):
        repo = Repository(
            name="Encrypted Stats Repo",
            path="/tmp/encrypted-stats-repo",
            encryption="repokey",
            passphrase="secret-passphrase",
            compression="lz4",
            repository_type="local",
        )

        with (
            patch("app.api.repositories.resolve_repo_ssh_key_file", return_value=None),
            patch(
                "app.api.repositories.borg._execute_command",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "stdout": "ok",
                        "stderr": "",
                        "return_code": 0,
                    }
                ),
            ) as mock_exec,
            patch(
                "app.api.repositories.BorgRouter.list_archives",
                new=AsyncMock(return_value=[]),
            ) as mock_list,
        ):
            from app.api.repositories import get_repository_stats

            stats = await get_repository_stats(repo, test_db)

        assert "error" not in stats
        _, kwargs = mock_exec.call_args
        assert kwargs["env"]["BORG_PASSPHRASE"] == "secret-passphrase"
        mock_list.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_repository_stats_omits_passphrase_for_unencrypted_local_repo(
        self, test_db
    ):
        repo = Repository(
            name="Unencrypted Stats Repo",
            path="/tmp/unencrypted-stats-repo",
            encryption="none",
            passphrase=None,
            compression="lz4",
            repository_type="local",
        )

        with (
            patch("app.api.repositories.resolve_repo_ssh_key_file", return_value=None),
            patch(
                "app.api.repositories.borg._execute_command",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "stdout": "ok",
                        "stderr": "",
                        "return_code": 0,
                    }
                ),
            ) as mock_exec,
            patch(
                "app.api.repositories.BorgRouter.list_archives",
                new=AsyncMock(return_value=[]),
            ),
        ):
            from app.api.repositories import get_repository_stats

            await get_repository_stats(repo, test_db)

        _, kwargs = mock_exec.call_args
        assert "BORG_PASSPHRASE" not in kwargs["env"]

    @pytest.mark.asyncio
    async def test_get_repository_stats_includes_remote_path_and_ssh_key_for_remote_repo(
        self, test_db
    ):
        repo = Repository(
            name="Remote Stats Repo",
            path="ssh://backup@example.com:22/backups/repo",
            encryption="repokey",
            passphrase="remote-passphrase",
            compression="lz4",
            repository_type="ssh",
            remote_path="/usr/local/bin/borg1",
            connection_id=7,
        )

        with (
            patch(
                "app.api.repositories.resolve_repo_ssh_key_file",
                return_value="/tmp/test.key",
            ),
            patch(
                "app.api.repositories.borg._execute_command",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "stdout": "ok",
                        "stderr": "",
                        "return_code": 0,
                    }
                ),
            ) as mock_exec,
            patch(
                "app.api.repositories.BorgRouter.list_archives",
                new=AsyncMock(return_value=[]),
            ) as mock_list,
            patch("app.api.repositories.os.path.exists", return_value=False),
        ):
            from app.api.repositories import get_repository_stats

            await get_repository_stats(repo, test_db)

        (cmd,) = mock_exec.call_args[0]
        assert "--remote-path" in cmd
        assert "/usr/local/bin/borg1" in cmd
        _, kwargs = mock_exec.call_args
        assert "BORG_RSH" in kwargs["env"]
        mock_list.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_repository_stats_supports_bypass_lock_and_borg_info_failure(
        self, test_db
    ):
        repo = Repository(
            name="Locked Stats Repo",
            path="/tmp/locked-stats-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )

        with (
            patch("app.api.repositories.resolve_repo_ssh_key_file", return_value=None),
            patch(
                "app.api.repositories.borg._execute_command",
                new=AsyncMock(
                    return_value={
                        "success": False,
                        "stdout": "",
                        "stderr": "stats failed",
                        "return_code": 2,
                    }
                ),
            ) as mock_exec,
        ):
            from app.api.repositories import get_repository_stats

            stats = await get_repository_stats(repo, test_db, bypass_lock=True)

        (cmd,) = mock_exec.call_args[0]
        assert "--bypass-lock" in cmd
        assert stats == {
            "error": "Failed to get repository info",
            "details": "stats failed",
        }

    @pytest.mark.asyncio
    async def test_get_repository_stats_tolerates_archive_list_failure(self, test_db):
        repo = Repository(
            name="Archive List Failure Repo",
            path="/tmp/archive-list-failure-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )

        with (
            patch("app.api.repositories.resolve_repo_ssh_key_file", return_value=None),
            patch(
                "app.api.repositories.borg._execute_command",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "stdout": "ok",
                        "stderr": "",
                        "return_code": 0,
                    }
                ),
            ),
            patch(
                "app.api.repositories.BorgRouter.list_archives",
                new=AsyncMock(return_value=[]),
            ),
        ):
            from app.api.repositories import get_repository_stats

            stats = await get_repository_stats(repo, test_db)

        assert stats["archive_count"] == 0


@pytest.mark.unit
class TestRepositoriesImport:
    """Test repository import functionality"""

    def test_import_repository_validation_error(
        self, test_client: TestClient, admin_headers
    ):
        """Test importing repository with missing fields returns 422"""
        response = test_client.post(
            "/api/repositories/import",
            json={"name": "Incomplete"},
            headers=admin_headers,
        )

        assert response.status_code == 422

    def test_import_repository_no_auth(self, test_client: TestClient):
        """Test importing repository without authentication returns 403"""
        response = test_client.post(
            "/api/repositories/import",
            json={"name": "Test", "path": "/test", "encryption": "none"},
        )

        assert response.status_code == 401

    def test_import_repository_allows_unencrypted_repo_without_passphrase(
        self, test_client: TestClient, admin_headers, test_db, tmp_path
    ):
        """Test importing an unencrypted repository does not require a passphrase."""
        repo_path = tmp_path / "unencrypted-import"
        repo_path.mkdir()
        (repo_path / "config").write_text("[repository]\n", encoding="utf-8")

        verify_result = {
            "success": True,
            "info": {"encryption": {"mode": "none"}},
        }

        with (
            patch(
                "app.api.repositories.verify_existing_repository",
                new=AsyncMock(return_value=verify_result),
            ) as mock_verify,
            patch(
                "app.core.borg_router.BorgRouter.update_stats",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.api.repositories.mqtt_service.sync_state_with_db",
                return_value=None,
            ),
        ):
            response = test_client.post(
                "/api/repositories/import",
                json={
                    "name": "Imported Unencrypted Repo",
                    "path": str(repo_path),
                    "compression": "lz4",
                    "mode": "observe",
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["repository"]["encryption"] == "none"
        assert mock_verify.await_args.args[1] is None

    def test_import_repository_rejects_directory_named_config(
        self, test_client: TestClient, admin_headers, tmp_path
    ):
        repo_path = tmp_path / "invalid-import"
        repo_path.mkdir()
        (repo_path / "config").mkdir()

        response = test_client.post(
            "/api/repositories/import",
            json={
                "name": "Invalid Imported Repo",
                "path": str(repo_path),
                "compression": "lz4",
                "mode": "observe",
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.repo.notValidBorgRepository"
        )

    def test_import_repository_delegates_borg2_payloads_to_v2_api(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _enable_borg_v2(test_db)

        with patch(
            "app.api.v2.repositories._rinfo",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "stdout": json.dumps({"repository": {"id": 1}}),
                    "stderr": "",
                }
            ),
        ):
            response = test_client.post(
                "/api/repositories/import",
                json={
                    "name": "Delegated Borg2 Import",
                    "path": "/tmp/delegated-borg2-import",
                    "borg_version": 2,
                    "encryption": "none",
                    "source_directories": ["/data/source"],
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        repo = (
            test_db.query(Repository)
            .filter(Repository.name == "Delegated Borg2 Import")
            .first()
        )
        assert repo is not None
        assert repo.borg_version == 2


@pytest.mark.unit
class TestRepositoriesArchives:
    """Test repository archives listing"""

    def test_list_repository_archives_not_found(
        self, test_client: TestClient, admin_headers
    ):
        """Test listing archives for non-existent repository returns 404"""
        response = test_client.get(
            "/api/repositories/99999/archives", headers=admin_headers
        )

        assert response.status_code == 404


@pytest.mark.unit
class TestRepositoriesJobStatus:
    """Test repository job status endpoints"""

    def test_get_repository_check_jobs(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test getting repository check jobs returns 200"""
        repo = Repository(
            name="Job Repo",
            path="/job/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/repositories/{repo.id}/check-jobs", headers=admin_headers
        )

        assert response.status_code == 200

    def test_get_repository_check_jobs_scheduled_only(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Scheduled Check Repo",
            path="/job/scheduled-check-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        test_db.add_all(
            [
                CheckJob(
                    repository_id=repo.id,
                    status="completed",
                    scheduled_check=True,
                ),
                CheckJob(
                    repository_id=repo.id,
                    status="completed",
                    scheduled_check=False,
                ),
            ]
        )
        test_db.commit()

        response = test_client.get(
            f"/api/repositories/{repo.id}/check-jobs?scheduled_only=true",
            headers=admin_headers,
        )

        assert response.status_code == 200
        jobs = response.json()["jobs"]
        assert len(jobs) == 1
        assert jobs[0]["scheduled_check"] is True

    def test_get_repository_compact_jobs(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test getting repository compact jobs returns 200"""
        repo = Repository(
            name="Job Repo",
            path="/job/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/repositories/{repo.id}/compact-jobs", headers=admin_headers
        )

        assert response.status_code == 200

    def test_get_repository_prune_jobs(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test getting repository prune jobs returns 200"""
        repo = Repository(
            name="Job Repo",
            path="/job/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/repositories/{repo.id}/prune-jobs", headers=admin_headers
        )

        assert response.status_code == 200

    def test_get_repository_running_jobs(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test getting repository running jobs returns 200"""
        repo = Repository(
            name="Job Repo",
            path="/job/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/repositories/{repo.id}/running-jobs", headers=admin_headers
        )

        assert response.status_code == 200

    def test_get_check_jobs_repository_not_found(
        self, test_client: TestClient, admin_headers
    ):
        """Test getting check jobs for non-existent repository returns 200 with empty list"""
        response = test_client.get(
            "/api/repositories/99999/check-jobs", headers=admin_headers
        )

        # Returns 200 with empty list, not 404
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data or isinstance(data, list)

    def test_get_compact_jobs_repository_not_found(
        self, test_client: TestClient, admin_headers
    ):
        """Test getting compact jobs for non-existent repository returns 200 with empty list"""
        response = test_client.get(
            "/api/repositories/99999/compact-jobs", headers=admin_headers
        )

        # Returns 200 with empty list, not 404
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data or isinstance(data, list)

    def test_get_prune_jobs_repository_not_found(
        self, test_client: TestClient, admin_headers
    ):
        """Test getting prune jobs for non-existent repository returns 200 with empty list"""
        response = test_client.get(
            "/api/repositories/99999/prune-jobs", headers=admin_headers
        )

        # Returns 200 with empty list, not 404
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data or isinstance(data, list)

    def test_get_running_jobs_repository_not_found(
        self, test_client: TestClient, admin_headers
    ):
        """Test getting running jobs for non-existent repository returns 200 with status"""
        response = test_client.get(
            "/api/repositories/99999/running-jobs", headers=admin_headers
        )

        # Returns 200 with status structure, not 404
        assert response.status_code == 200
        data = response.json()
        assert "has_running_jobs" in data or "jobs" in data or isinstance(data, list)


@pytest.mark.unit
class TestRepositoryCheckSchedule:
    """Test repository check schedule endpoints"""

    def test_get_check_schedule(self, test_client: TestClient, admin_headers, test_db):
        """Test getting check schedule for a repository"""
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            repository_type="local",
            check_cron_expression="0 2 * * 0",  # Weekly on Sunday at 2 AM
            check_max_duration=3600,
            notify_on_check_success=False,
            notify_on_check_failure=True,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/repositories/{repo.id}/check-schedule", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["repository_id"] == repo.id
        assert data["check_cron_expression"] == "0 2 * * 0"
        assert data["check_max_duration"] == 3600
        assert data["notify_on_check_success"] == False
        assert data["notify_on_check_failure"] == True
        assert data["enabled"] == True

    def test_get_check_schedule_disabled(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test getting check schedule for repository with no schedule"""
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            repository_type="local",
            check_cron_expression=None,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/repositories/{repo.id}/check-schedule", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["repository_id"] == repo.id
        assert data["check_cron_expression"] is None
        assert data["enabled"] == False

    def test_update_check_schedule(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test updating check schedule for a repository"""
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        # Update check schedule
        payload = {
            "cron_expression": "0 3 * * *",  # Daily at 3 AM
            "max_duration": 7200,
            "notify_on_success": True,
            "notify_on_failure": False,
        }
        response = test_client.put(
            f"/api/repositories/{repo.id}/check-schedule",
            headers=admin_headers,
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["repository"]["check_cron_expression"] == "0 3 * * *"
        assert data["repository"]["check_max_duration"] == 7200
        assert data["repository"]["notify_on_check_success"] == True
        assert data["repository"]["notify_on_check_failure"] == False
        assert data["repository"]["next_scheduled_check"] is not None

    def test_update_check_schedule_disable(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test disabling check schedule for a repository"""
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            repository_type="local",
            check_cron_expression="0 2 * * 0",  # Weekly on Sunday at 2 AM
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        # Disable check schedule
        payload = {"cron_expression": ""}
        response = test_client.put(
            f"/api/repositories/{repo.id}/check-schedule",
            headers=admin_headers,
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["repository"]["check_cron_expression"] is None
        assert data["repository"]["next_scheduled_check"] is None

    def test_get_check_schedule_not_found(self, test_client: TestClient, admin_headers):
        """Test getting check schedule for non-existent repository"""
        response = test_client.get(
            "/api/repositories/99999/check-schedule", headers=admin_headers
        )

        assert response.status_code == 404

    def test_update_check_schedule_not_found(
        self, test_client: TestClient, admin_headers
    ):
        """Test updating check schedule for non-existent repository"""
        payload = {"cron_expression": "0 2 * * 0"}
        response = test_client.put(
            "/api/repositories/99999/check-schedule",
            headers=admin_headers,
            json=payload,
        )

        assert response.status_code == 404


@pytest.mark.unit
class TestRepositoryRestoreCheckSchedule:
    def test_get_restore_check_schedule(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            repository_type="local",
            restore_check_cron_expression="0 5 * * 1",
            restore_check_timezone="Europe/Berlin",
            restore_check_paths='["etc/hostname"]',
            notify_on_restore_check_success=False,
            notify_on_restore_check_failure=True,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/repositories/{repo.id}/restore-check-schedule", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["repository_id"] == repo.id
        assert data["restore_check_cron_expression"] == "0 5 * * 1"
        assert data["restore_check_timezone"] == "Europe/Berlin"
        assert data["timezone"] == "Europe/Berlin"
        assert data["restore_check_paths"] == ["etc/hostname"]
        assert data["notify_on_restore_check_failure"] == True
        assert data["restore_check_mode"] == "probe_paths"
        assert data["restore_check_canary_enabled"] == False
        assert data["enabled"] == True

    def test_update_restore_check_schedule(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        payload = {
            "cron_expression": "0 6 * * *",
            "timezone": "Asia/Kolkata",
            "paths": ["etc/hostname", "var/log"],
            "notify_on_success": True,
            "notify_on_failure": False,
        }
        response = test_client.put(
            f"/api/repositories/{repo.id}/restore-check-schedule",
            headers=admin_headers,
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["repository"]["restore_check_cron_expression"] == "0 6 * * *"
        assert data["repository"]["restore_check_timezone"] == "Asia/Kolkata"
        assert data["repository"]["timezone"] == "Asia/Kolkata"
        assert data["repository"]["restore_check_paths"] == [
            "etc/hostname",
            "var/log",
        ]
        assert data["repository"]["restore_check_mode"] == "probe_paths"
        assert data["repository"]["restore_check_canary_enabled"] == False
        assert data["repository"]["notify_on_restore_check_success"] == True
        assert data["repository"]["notify_on_restore_check_failure"] == False
        assert data["repository"]["next_scheduled_restore_check"] is not None

    def test_update_restore_check_schedule_defaults_to_canary_mode(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Canary Repo",
            path="/tmp/canary",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.put(
            f"/api/repositories/{repo.id}/restore-check-schedule",
            headers=admin_headers,
            json={"cron_expression": "0 7 * * *", "paths": [], "full_archive": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["repository"]["restore_check_mode"] == "canary"
        assert data["repository"]["restore_check_canary_enabled"] == True

        test_db.refresh(repo)
        assert repo.restore_check_canary_enabled is True

        disable_response = test_client.put(
            f"/api/repositories/{repo.id}/restore-check-schedule",
            headers=admin_headers,
            json={"cron_expression": ""},
        )

        assert disable_response.status_code == 200
        assert (
            disable_response.json()["repository"]["restore_check_canary_enabled"]
            == False
        )
        test_db.refresh(repo)
        assert repo.restore_check_canary_enabled is False

    def test_update_restore_check_schedule_rejects_canary_for_observe_repo(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Observe Repo",
            path="/tmp/observe",
            encryption="none",
            repository_type="local",
            mode="observe",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.put(
            f"/api/repositories/{repo.id}/restore-check-schedule",
            headers=admin_headers,
            json={"cron_expression": "0 7 * * *", "paths": [], "full_archive": False},
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.repo.restoreCheckCanaryUnsupportedObserve"
        )

    def test_update_restore_check_schedule_allows_probe_paths_for_observe_repo(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Observe Repo",
            path="/tmp/observe",
            encryption="none",
            repository_type="local",
            mode="observe",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.put(
            f"/api/repositories/{repo.id}/restore-check-schedule",
            headers=admin_headers,
            json={
                "cron_expression": "0 7 * * *",
                "paths": ["etc/hostname"],
                "full_archive": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["repository"]["restore_check_mode"] == "probe_paths"
        assert data["repository"]["restore_check_canary_enabled"] == False

    def test_start_restore_check_job(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Test Repo",
            path="/tmp/test",
            encryption="none",
            repository_type="local",
            restore_check_paths='["etc/hostname"]',
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.repositories.start_background_maintenance_job"
        ) as mock_start:
            mock_start.return_value = RestoreCheckJob(
                id=501,
                repository_id=repo.id,
                status="pending",
                probe_paths='["etc/hostname"]',
            )
            response = test_client.post(
                f"/api/repositories/{repo.id}/restore-check",
                headers=admin_headers,
                json={},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == 501
        assert data["message"] == "backend.success.repo.restoreCheckJobStarted"

    def test_manual_canary_restore_check_marks_canary_for_future_backups(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Canary Repo",
            path="/tmp/canary",
            encryption="none",
            repository_type="local",
            restore_check_canary_enabled=False,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.maintenance_jobs.schedule_background_job",
            side_effect=_discard_background_coro,
        ):
            response = test_client.post(
                f"/api/repositories/{repo.id}/restore-check",
                headers=admin_headers,
                json={"paths": [], "full_archive": False},
            )

        assert response.status_code == 200
        test_db.refresh(repo)
        assert repo.restore_check_canary_enabled is True
        assert repo.restore_check_paths == "[]"
        assert repo.restore_check_full_archive is False

    def test_manual_canary_restore_check_rejects_observe_repo(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Observe Repo",
            path="/tmp/observe",
            encryption="none",
            repository_type="local",
            mode="observe",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.post(
            f"/api/repositories/{repo.id}/restore-check",
            headers=admin_headers,
            json={"paths": [], "full_archive": False},
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.repo.restoreCheckCanaryUnsupportedObserve"
        )

    def test_manual_probe_restore_check_allows_observe_repo(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Observe Repo",
            path="/tmp/observe",
            encryption="none",
            repository_type="local",
            mode="observe",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.maintenance_jobs.schedule_background_job",
            side_effect=_discard_background_coro,
        ):
            response = test_client.post(
                f"/api/repositories/{repo.id}/restore-check",
                headers=admin_headers,
                json={"paths": ["etc/hostname"], "full_archive": False},
            )

        assert response.status_code == 200


@pytest.mark.unit
class TestBorgEnvironmentSetup:
    """Test borg environment setup functions"""

    def test_setup_borg_env_sets_relocated_repo_access(self):
        """Test that setup_borg_env sets BORG_RELOCATED_REPO_ACCESS_IS_OK"""
        from app.api.repositories import setup_borg_env

        env = setup_borg_env()

        assert "BORG_RELOCATED_REPO_ACCESS_IS_OK" in env
        assert env["BORG_RELOCATED_REPO_ACCESS_IS_OK"] == "yes"

    def test_setup_borg_env_sets_unencrypted_repo_access(self):
        """Test that setup_borg_env sets BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"""
        from app.api.repositories import setup_borg_env

        env = setup_borg_env()

        assert "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK" in env
        assert env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] == "yes"

    def test_setup_borg_env_sets_passphrase(self):
        """Test that setup_borg_env sets passphrase when provided"""
        from app.api.repositories import setup_borg_env

        env = setup_borg_env(passphrase="test-passphrase")

        assert "BORG_PASSPHRASE" in env
        assert env["BORG_PASSPHRASE"] == "test-passphrase"

    def test_setup_borg_env_no_passphrase_when_not_provided(self):
        """Test that setup_borg_env doesn't set passphrase when not provided"""
        from app.api.repositories import setup_borg_env

        env = setup_borg_env()

        assert "BORG_PASSPHRASE" not in env

    def test_setup_borg_env_sets_lock_wait(self):
        """Test that setup_borg_env sets BORG_LOCK_WAIT"""
        from app.api.repositories import setup_borg_env

        env = setup_borg_env()

        assert "BORG_LOCK_WAIT" in env
        assert env["BORG_LOCK_WAIT"] == "180"

    def test_setup_borg_env_sets_hostname_unique(self):
        """Test that setup_borg_env sets BORG_HOSTNAME_IS_UNIQUE"""
        from app.api.repositories import setup_borg_env

        env = setup_borg_env()

        assert "BORG_HOSTNAME_IS_UNIQUE" in env
        assert env["BORG_HOSTNAME_IS_UNIQUE"] == "yes"

    def test_setup_borg_env_sets_ssh_opts(self):
        """Test that setup_borg_env sets BORG_RSH when ssh_opts provided"""
        from app.api.repositories import setup_borg_env

        ssh_opts = ["-o", "StrictHostKeyChecking=no"]
        env = setup_borg_env(ssh_opts=ssh_opts)

        assert "BORG_RSH" in env
        assert "StrictHostKeyChecking=no" in env["BORG_RSH"]
