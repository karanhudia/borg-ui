"""
Unit tests for archives API endpoints

These tests focus on:
- Authentication and authorization
- Input validation
- Error handling
- Resource existence validation

Integration tests (test_api_archives_integration.py) handle:
- Real borg operations
- Archive listing, info, contents
- File downloads
- Encryption
"""

import asyncio
import base64
import os
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from app.core.security import get_password_hash
from app.database.models import (
    AgentMachine,
    DeleteArchiveJob,
    Repository,
    SystemSettings,
)


def _create_agent(test_db, *capabilities: str) -> AgentMachine:
    agent = AgentMachine(
        name="Archive Download Agent",
        agent_id="agt_archive_download",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=list(capabilities),
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)
    return agent


@pytest.mark.unit
class TestArchivesAuthentication:
    """Test authentication and authorization for archives endpoints"""

    def test_list_archives_no_auth_returns_403(self, test_client: TestClient):
        """
        Verify unauthenticated requests are rejected.
        NOTE: FastAPI's HTTPBearer returns 403 for missing credentials.
        """
        response = test_client.get("/api/archives/list?repository=/tmp/repo")
        assert response.status_code == 401

    def test_get_archive_info_no_auth_returns_403(self, test_client: TestClient):
        """Verify unauthenticated archive info requests are rejected"""
        response = test_client.get("/api/archives/myarchive/info?repository=/tmp/repo")
        assert response.status_code == 401

    def test_get_archive_contents_no_auth_returns_403(self, test_client: TestClient):
        """Verify unauthenticated archive contents requests are rejected"""
        response = test_client.get(
            "/api/archives/myarchive/contents?repository=/tmp/repo"
        )
        assert response.status_code == 401

    def test_delete_archive_no_auth_returns_403(self, test_client: TestClient):
        """Verify unauthenticated archive deletion is rejected"""
        response = test_client.delete("/api/archives/myarchive?repository=/tmp/repo")
        assert response.status_code == 401


@pytest.mark.unit
class TestArchivesResourceValidation:
    """Test resource existence validation"""

    def test_list_archives_nonexistent_repository_returns_404(
        self, test_client: TestClient, admin_headers
    ):
        """Should return 404 when repository doesn't exist in database"""
        response = test_client.get(
            "/api/archives/list?repository=/nonexistent/path", headers=admin_headers
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.restore.repositoryNotFound"
        )

    def test_delete_archive_legacy_route_dispatches_v2_repo_via_router(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        repo = Repository(
            name="V2 Repo",
            path="/tmp/v2-repo",
            encryption="none",
            repository_type="local",
            borg_version=2,
        )
        test_db.add(repo)
        test_db.commit()

        with patch(
            "app.api.archives.BorgRouter.delete_archive", new_callable=AsyncMock
        ) as mock_delete:
            response = test_client.delete(
                "/api/archives/archive-1",
                params={"repository": repo.path},
                headers=admin_headers,
            )

        assert response.status_code == 200
        mock_delete.assert_awaited_once()

    def test_delete_archive_route_constructs_router_with_stable_repo_identity(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        repo = Repository(
            name="Repo",
            path="/tmp/repo",
            encryption="none",
            repository_type="local",
            borg_version=2,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        fake_router = Mock(delete_archive=AsyncMock())
        created = {}

        def fake_create_task(coro):
            created["coro"] = coro
            return object()

        with (
            patch(
                "app.api.archives.BorgRouter", return_value=fake_router
            ) as mock_router,
            patch("app.api.archives.asyncio.create_task", side_effect=fake_create_task),
        ):
            response = test_client.delete(
                "/api/archives/archive-1",
                params={"repository": repo.path},
                headers=admin_headers,
            )

        assert response.status_code == 200
        routed_repo = mock_router.call_args.args[0]
        assert not isinstance(routed_repo, Repository)
        assert routed_repo.id == repo.id
        assert routed_repo.borg_version == repo.borg_version

        asyncio.run(created["coro"])
        fake_router.delete_archive.assert_awaited_once()

    def test_delete_job_status_applies_log_save_policy(
        self, test_client: TestClient, admin_headers, test_db, tmp_path
    ):
        settings = test_db.query(SystemSettings).first()
        if settings is None:
            settings = SystemSettings()
            test_db.add(settings)
        settings.log_save_policy = "failed_only"
        repo = Repository(
            name="Archive Repo",
            path="/tmp/archive-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.flush()
        log_file = tmp_path / "delete.log"
        log_file.write_text("archive deleted", encoding="utf-8")
        job = DeleteArchiveJob(
            repository_id=repo.id,
            repository_path=repo.path,
            archive_name="archive-1",
            status="completed",
            started_at=datetime(2026, 4, 27, 3, 0, 6),
            completed_at=datetime(2026, 4, 27, 3, 5, 6),
            log_file_path=str(log_file),
            has_logs=True,
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get(
            f"/api/archives/delete-jobs/{job.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["logs"] is None
        assert body["has_logs"] is False


@pytest.mark.unit
class TestArchivesSshEnvironment:
    def test_list_archives_uses_repo_ssh_environment(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        repo = Repository(
            name="SSH Repo",
            path="ssh://borgsmoke@127.0.0.1:2222/home/borgsmoke/remote-repo",
            repository_type="ssh",
            connection_id=1,
            passphrase=None,
        )
        test_db.add(repo)
        test_db.commit()

        fake_key_path = "/tmp/test-ssh.key"
        with (
            patch(
                "app.api.archives.resolve_repo_ssh_key_file", return_value=fake_key_path
            ),
            patch(
                "app.api.archives.os.path.exists",
                side_effect=lambda path: path == fake_key_path,
            ),
            patch("app.api.archives.os.unlink") as mock_unlink,
            patch(
                "app.api.archives.borg.list_archives",
                new=AsyncMock(
                    return_value={"success": True, "stdout": {"archives": []}}
                ),
            ) as mock_list_archives,
        ):
            response = test_client.get(
                f"/api/archives/list?repository={repo.path}",
                headers=admin_headers,
            )

        assert response.status_code == 200
        _, kwargs = mock_list_archives.await_args
        assert kwargs["env"]["BORG_RSH"].startswith("ssh -i /tmp/test-ssh.key")
        mock_unlink.assert_called_once_with(fake_key_path)

    def test_archive_info_uses_repo_ssh_environment_for_contents(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        repo = Repository(
            name="SSH Repo",
            path="ssh://borgsmoke@127.0.0.1:2222/home/borgsmoke/remote-repo",
            repository_type="ssh",
            connection_id=1,
            passphrase=None,
        )
        test_db.add(repo)
        test_db.commit()

        with (
            patch("app.api.archives.resolve_repo_ssh_key_file", return_value=None),
            patch(
                "app.api.archives.borg.info_archive",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "stdout": '{"archives":[{"name":"arch1"}]}',
                    }
                ),
            ) as mock_info_archive,
            patch(
                "app.api.archives.borg.list_archive_contents",
                new=AsyncMock(return_value={"success": True, "stdout": ""}),
            ) as mock_list_contents,
        ):
            response = test_client.get(
                f"/api/archives/arch1/info?repository={repo.path}&include_files=true",
                headers=admin_headers,
            )

        assert response.status_code == 200
        _, info_kwargs = mock_info_archive.await_args
        _, contents_kwargs = mock_list_contents.await_args
        assert "BORG_RSH" in info_kwargs["env"]
        assert "BORG_RSH" in contents_kwargs["env"]

    def test_get_archive_info_nonexistent_repository_returns_404(
        self, test_client: TestClient, admin_headers
    ):
        """Should return 404 when repository doesn't exist in database"""
        response = test_client.get(
            "/api/archives/myarchive/info?repository=/nonexistent/path",
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.restore.repositoryNotFound"
        )

    def test_get_archive_contents_nonexistent_repository_returns_404(
        self, test_client: TestClient, admin_headers
    ):
        """Should return 404 when repository doesn't exist in database"""
        response = test_client.get(
            "/api/archives/myarchive/contents?repository=/nonexistent/path",
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.restore.repositoryNotFound"
        )

    def test_delete_archive_nonexistent_repository_returns_404(
        self, test_client: TestClient, admin_headers
    ):
        """Should return 404 when repository doesn't exist in database"""
        response = test_client.delete(
            "/api/archives/myarchive?repository=/nonexistent/path",
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.restore.repositoryNotFound"
        )


@pytest.mark.unit
class TestDownloadFileEndpoint:
    """Test GET /archives/download endpoint validation"""

    def test_download_file_missing_token(self, test_client: TestClient):
        """Test download without authentication token"""
        response = test_client.get(
            "/api/archives/download?repository=/test/repo&archive=test-archive&file_path=/test.txt"
        )

        assert response.status_code == 401

    def test_download_file_invalid_token(self, test_client: TestClient):
        """Test download with invalid/expired token"""
        response = test_client.get(
            "/api/archives/download?repository=/test/repo&archive=test-archive&file_path=/test.txt&token=invalid-token"
        )

        # Should fail with invalid token
        assert response.status_code == 401

    def test_download_file_authorized_with_bearer_header(
        self, test_client: TestClient, admin_headers
    ):
        """Download endpoint should accept standard bearer auth without query token."""
        response = test_client.get(
            "/api/archives/download?repository=/nonexistent&archive=test-archive&file_path=/test.txt",
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.archives.repositoryNotFound"
        )

    def test_download_file_proxy_auth_without_token(
        self, test_client: TestClient, monkeypatch
    ):
        """Proxy-auth mode should not require a JWT query token for downloads."""
        from app import config

        monkeypatch.setattr(config.settings, "disable_authentication", True)

        response = test_client.get(
            "/api/archives/download?repository=/nonexistent&archive=test-archive&file_path=/test.txt",
            headers={"X-Forwarded-User": "proxyuser"},
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.archives.repositoryNotFound"
        )

    def test_download_file_repository_not_found(
        self, test_client: TestClient, test_db, admin_headers
    ):
        """Test download from non-existent repository"""
        response = test_client.get(
            "/api/archives/download?repository=/nonexistent&archive=test-archive&file_path=/test.txt",
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.archives.repositoryNotFound"
        )

    def test_download_file_uses_repo_ssh_environment(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        repo = Repository(
            name="SSH Repo",
            path="ssh://borgsmoke@127.0.0.1:2222/home/borgsmoke/remote-repo",
            repository_type="ssh",
            connection_id=1,
            passphrase=None,
        )
        test_db.add(repo)
        test_db.commit()

        fake_key_path = "/tmp/test-ssh.key"
        temp_dir = "/tmp/archive-download"
        extracted_path = os.path.realpath(os.path.join(temp_dir, "extracted.txt"))
        with (
            patch(
                "app.api.archives.resolve_repo_ssh_key_file", return_value=fake_key_path
            ),
            patch(
                "app.api.archives.os.path.exists",
                side_effect=lambda path: path in {fake_key_path, extracted_path},
            ),
            patch("app.api.archives.os.unlink") as mock_unlink,
            patch(
                "app.api.archives.tempfile.mkdtemp",
                return_value=temp_dir,
            ),
            patch(
                "app.api.archives.FileResponse",
                side_effect=lambda **kwargs: {"path": kwargs["path"]},
            ) as mock_file_response,
            patch(
                "app.api.archives.borg.extract_archive",
                new=AsyncMock(return_value={"success": True, "stdout": ""}),
            ) as mock_extract,
        ):
            response = test_client.get(
                f"/api/archives/download?repository={repo.path}&archive=test-archive&file_path=/extracted.txt",
                headers=admin_headers,
            )

        assert response.status_code == 200
        _, kwargs = mock_extract.await_args
        assert kwargs["env"]["BORG_RSH"].startswith("ssh -i /tmp/test-ssh.key")
        mock_file_response.assert_called_once()
        mock_unlink.assert_called_once_with(fake_key_path)

    def test_download_file_accepts_repository_id(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        repo = Repository(
            name="Local Repo",
            path="/tmp/local-repo",
            repository_type="local",
            passphrase=None,
        )
        test_db.add(repo)
        test_db.commit()

        temp_dir = "/tmp/archive-download"
        extracted_path = os.path.realpath(os.path.join(temp_dir, "extracted.txt"))
        with (
            patch("app.api.archives.resolve_repo_ssh_key_file", return_value=None),
            patch(
                "app.api.archives.os.path.exists",
                side_effect=lambda path: path == extracted_path,
            ),
            patch(
                "app.api.archives.tempfile.mkdtemp",
                return_value=temp_dir,
            ),
            patch(
                "app.api.archives.FileResponse",
                side_effect=lambda **kwargs: {"path": kwargs["path"]},
            ) as mock_file_response,
            patch(
                "app.api.archives.borg.extract_archive",
                new=AsyncMock(return_value={"success": True, "stdout": ""}),
            ) as mock_extract,
        ):
            response = test_client.get(
                f"/api/archives/download?repository={repo.id}&archive=test-archive&file_path=/extracted.txt",
                headers=admin_headers,
            )

        assert response.status_code == 200
        args, kwargs = mock_extract.await_args
        assert args == (
            repo.path,
            "test-archive",
            ["/extracted.txt"],
            "/tmp/archive-download",
        )
        assert kwargs["dry_run"] is False
        assert kwargs["remote_path"] == repo.remote_path
        assert kwargs["passphrase"] == repo.passphrase
        assert kwargs["bypass_lock"] == repo.bypass_lock
        mock_file_response.assert_called_once()

    def test_download_file_for_agent_repository_queues_extract_job(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        tmp_path,
    ):
        agent = _create_agent(test_db, "repository.extract_archive_file")
        repo = Repository(
            name="Agent Download Repo",
            path="/agent/repositories/app",
            encryption="none",
            repository_type="local",
            executor_type="agent",
            execution_target="agent",
            agent_machine_id=agent.id,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        archive_path = tmp_path / "extract"
        content = b"hello from the managed agent\n"
        queued_jobs = []

        def fake_queue(db, repository, *, job_kind, operation=None, **_kwargs):
            queued_jobs.append(
                {
                    "repository": repository,
                    "job_kind": job_kind,
                    "operation": operation,
                }
            )
            return Mock(id=42)

        with (
            patch(
                "app.api.archives.tempfile.mkdtemp",
                return_value=str(archive_path),
            ),
            patch(
                "app.api.archives.queue_agent_repository_operation_job",
                side_effect=fake_queue,
                create=True,
            ),
            patch(
                "app.api.archives.dispatch_agent_job_best_effort",
                new=AsyncMock(return_value=True),
                create=True,
            ) as dispatch_agent,
            patch(
                "app.api.archives.wait_for_agent_repository_operation_job",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "content_base64": base64.b64encode(content).decode("ascii"),
                        "stderr": "",
                    }
                ),
                create=True,
            ) as wait_for_agent,
            patch(
                "app.api.archives.borg.extract_archive",
                new=AsyncMock(return_value={"success": True, "stderr": ""}),
            ) as local_extract,
        ):
            response = test_client.get(
                f"/api/archives/download?repository={repo.id}&archive=test-archive&file_path=/extracted.txt",
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.content == content
        assert queued_jobs == [
            {
                "repository": repo,
                "job_kind": "repository.extract_archive_file",
                "operation": {
                    "archive": "test-archive",
                    "file_path": "/extracted.txt",
                },
            }
        ]
        dispatch_agent.assert_awaited_once()
        wait_for_agent.assert_awaited_once_with(test_db, 42)
        local_extract.assert_not_awaited()

    def test_download_file_for_agent_repository_preserves_extract_failure(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        tmp_path,
    ):
        agent = _create_agent(test_db, "repository.extract_archive_file")
        repo = Repository(
            name="Agent Missing Repo",
            path="/agent/repositories/missing",
            encryption="none",
            repository_type="local",
            executor_type="agent",
            execution_target="agent",
            agent_machine_id=agent.id,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        stderr = "Repository /agent/repositories/missing does not exist.\n"
        with (
            patch(
                "app.api.archives.tempfile.mkdtemp",
                return_value=str(tmp_path / "extract"),
            ),
            patch(
                "app.api.archives.queue_agent_repository_operation_job",
                return_value=Mock(id=43),
            ),
            patch(
                "app.api.archives.dispatch_agent_job_best_effort",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.api.archives.wait_for_agent_repository_operation_job",
                new=AsyncMock(return_value={"success": False, "stderr": stderr}),
            ),
            patch(
                "app.api.archives.borg.extract_archive",
                new=AsyncMock(return_value={"success": True, "stderr": ""}),
            ) as local_extract,
        ):
            response = test_client.get(
                f"/api/archives/download?repository={repo.id}&archive=test-archive&file_path=/extracted.txt",
                headers=admin_headers,
            )

        assert response.status_code == 500
        assert response.json()["detail"] == {
            "key": "backend.errors.archives.failedExtractFile",
            "params": {"error": stderr},
        }
        local_extract.assert_not_awaited()


@pytest.mark.unit
def test_archive_extract_selector_addresses_borg2_id_via_aid():
    from types import SimpleNamespace
    from app.api.archives import _archive_extract_selector

    borg2 = SimpleNamespace(borg_version=2)
    borg1 = SimpleNamespace(borg_version=1)
    hex_id = "deadbeefdeadbeef"

    # Borg 2 hex id -> aid: selector
    assert _archive_extract_selector(hex_id, borg2) == f"aid:{hex_id}"
    # already-prefixed selector is left alone
    assert _archive_extract_selector(f"aid:{hex_id}", borg2) == f"aid:{hex_id}"
    # a non-hex name (not an id) is passed through even for Borg 2
    assert _archive_extract_selector("m3s01", borg2) == "m3s01"
    # Borg 1 never uses aid: (unique names)
    assert _archive_extract_selector(hex_id, borg1) == hex_id
