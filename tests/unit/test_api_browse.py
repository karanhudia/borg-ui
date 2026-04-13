"""
Unit tests for browse/filesystem API endpoints
"""
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.api import browse as browse_api
from app.database.models import Repository, SystemSettings


def _create_repository(test_db, name="Browse Test Repo"):
    repo = Repository(
        name=name,
        path="/tmp/test-browse-repo",
        encryption="none",
        compression="lz4",
        repository_type="local",
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


@pytest.mark.unit
class TestBrowseEndpoints:
    """Test browse API endpoints"""

    def test_browse_archive_unauthorized(self, test_client: TestClient):
        """Test browsing archive without authentication"""
        response = test_client.get("/api/browse/1/archive-name/")

        assert response.status_code == 404

    def test_browse_archive_invalid_repository(self, test_client: TestClient, admin_headers):
        """Test browsing archive with invalid repository"""
        response = test_client.get(
            "/api/browse/99999/archive-name/",
            headers=admin_headers
        )

        assert response.status_code == 404

    def test_browse_archive_root(self, test_client: TestClient, admin_headers, test_db):
        """Test browsing archive root directory"""
        repo = _create_repository(test_db)
        cached_items = [
            {"path": "docs", "type": "d", "size": None, "mtime": "2024-01-01T00:00:00"},
            {"path": "docs/readme.md", "type": "f", "size": 12, "mtime": "2024-01-01T00:00:01"},
        ]

        with patch.object(browse_api.archive_cache, "get", new=AsyncMock(return_value=cached_items)):
            response = test_client.get(
                f"/api/browse/{repo.id}/test-archive",
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json()["items"][0]["name"] == "docs"

    def test_browse_archive_subdirectory(self, test_client: TestClient, admin_headers, test_db):
        """Test browsing archive subdirectory"""
        repo = _create_repository(test_db)
        cached_items = [
            {"path": "home/user/file.txt", "type": "f", "size": 10, "mtime": "2024-01-01T00:00:01"},
            {"path": "home/user/docs", "type": "d", "size": None, "mtime": "2024-01-01T00:00:02"},
            {"path": "home/user/docs/a.txt", "type": "f", "size": 11, "mtime": "2024-01-01T00:00:03"},
        ]

        with patch.object(browse_api.archive_cache, "get", new=AsyncMock(return_value=cached_items)):
            response = test_client.get(
                f"/api/browse/{repo.id}/test-archive",
                params={"path": "home/user"},
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert [item["name"] for item in response.json()["items"]] == ["docs", "file.txt"]

    def test_get_file_content_invalid(self, test_client: TestClient, admin_headers):
        """Test getting file content from invalid archive"""
        response = test_client.get(
            "/api/browse/99999/archive-name/path/to/file.txt",
            headers=admin_headers
        )

        assert response.status_code == 404

    def test_search_archive_invalid(self, test_client: TestClient, admin_headers):
        """Test searching in invalid archive"""
        response = test_client.post(
            "/api/browse/99999/archive-name/search",
            json={"query": "test"},
            headers=admin_headers
        )

        assert response.status_code == 405


@pytest.mark.unit
class TestBrowseArchiveBehavior:
    @pytest.mark.asyncio
    async def test_browse_archive_invalid_repository_returns_contract_error(
        self,
        test_db,
        admin_user,
    ):
        with pytest.raises(browse_api.HTTPException) as exc:
            await browse_api.browse_archive_contents(
                repository_id=99999,
                archive_name="archive-name",
                path="",
                current_user=admin_user,
                db=test_db,
            )

        assert exc.value.status_code == 404
        assert exc.value.detail["key"] == "backend.errors.restore.repositoryNotFound"

    @pytest.mark.asyncio
    async def test_browse_archive_uses_cached_items_without_hitting_borg(
        self,
        test_db,
        admin_user,
    ):
        repo = _create_repository(test_db)
        cached_items = [
            {"path": "docs", "type": "d", "size": None, "mtime": "2024-01-01T00:00:00"},
            {"path": "docs/readme.md", "type": "f", "size": 12, "mtime": "2024-01-01T00:00:01"},
            {"path": "z.txt", "type": "f", "size": 3, "mtime": "2024-01-01T00:00:02"},
        ]

        with patch.object(browse_api.archive_cache, "get", new=AsyncMock(return_value=cached_items)):
            with patch.object(browse_api.BorgRouter, "list_archive_contents", new=AsyncMock()) as mock_list:
                response = await browse_api.browse_archive_contents(
                    repository_id=repo.id,
                    archive_name="test-archive",
                    path="",
                    current_user=admin_user,
                    db=test_db,
                )

        assert response["items"]
        data = response
        assert [item["name"] for item in data["items"]] == ["docs", "z.txt"]
        assert data["items"][0]["type"] == "directory"
        assert data["items"][0]["size"] == 12
        assert data["items"][1]["type"] == "file"
        mock_list.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_browse_archive_rejects_streams_that_exceed_line_limit(
        self,
        test_db,
        admin_user,
    ):
        repo = _create_repository(test_db, name="Line Limit Repo")

        with patch.object(browse_api.archive_cache, "get", new=AsyncMock(return_value=None)):
            with patch.object(
                browse_api.BorgRouter,
                "list_archive_contents",
                new=AsyncMock(return_value={"line_count_exceeded": True, "lines_read": 77}),
            ):
                with pytest.raises(HTTPException) as exc:
                    await browse_api.browse_archive_contents(
                        repository_id=repo.id,
                        archive_name="huge-archive",
                        path="",
                        current_user=admin_user,
                        db=test_db,
                    )

        assert exc.value.status_code == 413
        assert exc.value.detail["key"] == "backend.errors.browse.archiveTooLarge"

    @pytest.mark.asyncio
    async def test_browse_archive_rejects_memory_estimate_overage(
        self,
        test_db,
        admin_user,
        monkeypatch,
    ):
        repo = _create_repository(test_db, name="Memory Limit Repo")
        settings = test_db.query(SystemSettings).first()
        if settings is None:
            settings = SystemSettings()
            test_db.add(settings)
        settings.browse_max_memory_mb = 1
        test_db.commit()

        stdout = "\n".join(
            [
                json.dumps({"path": "docs", "type": "d", "mtime": "2024-01-01T00:00:00"}),
                json.dumps({"path": "docs/readme.md", "type": "f", "size": 12, "mtime": "2024-01-01T00:00:01"}),
            ]
        )

        monkeypatch.setattr(browse_api, "ITEM_SIZE_ESTIMATE", 1024 * 1024)

        with patch.object(browse_api.archive_cache, "get", new=AsyncMock(return_value=None)):
            with patch.object(
                browse_api.BorgRouter,
                "list_archive_contents",
                new=AsyncMock(return_value={"stdout": stdout}),
            ):
                with pytest.raises(HTTPException) as exc:
                    await browse_api.browse_archive_contents(
                        repository_id=repo.id,
                        archive_name="memory-archive",
                        path="",
                        current_user=admin_user,
                        db=test_db,
                    )

        assert exc.value.status_code == 413
        assert exc.value.detail["key"] == "backend.errors.browse.archiveMemoryTooHigh"

    @pytest.mark.asyncio
    async def test_browse_archive_parses_and_caches_items(
        self,
        test_db,
        admin_user,
    ):
        repo = _create_repository(test_db, name="Parse Repo")
        stdout = "\n".join(
            [
                json.dumps({"path": "docs", "type": "d", "mtime": "2024-01-01T00:00:00"}),
                "not-json",
                json.dumps({"path": "docs/readme.md", "type": "f", "size": 7, "mtime": "2024-01-01T00:00:01"}),
                json.dumps({"path": "notes.txt", "type": "f", "size": 3, "mtime": "2024-01-01T00:00:02"}),
            ]
        )

        with patch.object(browse_api.archive_cache, "get", new=AsyncMock(return_value=None)):
            with patch.object(browse_api.archive_cache, "set", new=AsyncMock(return_value=True)) as mock_set:
                with patch.object(
                    browse_api.BorgRouter,
                    "list_archive_contents",
                    new=AsyncMock(return_value={"stdout": stdout}),
                ) as mock_list:
                    response = await browse_api.browse_archive_contents(
                        repository_id=repo.id,
                        archive_name="parsed-archive",
                        path="",
                        current_user=admin_user,
                        db=test_db,
                    )

        data = response
        assert [item["name"] for item in data["items"]] == ["docs", "notes.txt"]
        assert data["items"][0]["size"] == 7
        assert data["items"][1]["size"] == 3
        mock_list.assert_awaited_once()
        mock_set.assert_awaited_once()
        cached_args = mock_set.await_args.args
        assert cached_args[0] == repo.id
        assert cached_args[1] == "parsed-archive"
        assert len(cached_args[2]) == 3

    @pytest.mark.asyncio
    async def test_browse_archive_uses_repo_ssh_environment_when_cache_misses(
        self,
        test_db,
        admin_user,
    ):
        repo = Repository(
            name="SSH Browse Repo",
            path="ssh://borgsmoke@127.0.0.1:2222/home/borgsmoke/remote-repo",
            repository_type="ssh",
            connection_id=1,
            passphrase=None,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch.object(browse_api.archive_cache, "get", new=AsyncMock(return_value=None)):
            with patch.object(browse_api.archive_cache, "set", new=AsyncMock(return_value=True)):
                with patch.object(
                    browse_api.BorgRouter,
                    "list_archive_contents",
                    new=AsyncMock(return_value={"stdout": ""}),
                ) as mock_list, patch(
                    "app.api.browse.resolve_repo_ssh_key_file",
                    return_value="/tmp/test-browse.key",
                ), patch(
                    "app.api.browse.os.path.exists",
                    side_effect=lambda path: path == "/tmp/test-browse.key",
                ), patch("app.api.browse.os.unlink") as mock_unlink:
                    await browse_api.browse_archive_contents(
                        repository_id=repo.id,
                        archive_name="parsed-archive",
                        path="",
                        current_user=admin_user,
                        db=test_db,
                    )

        _, kwargs = mock_list.await_args
        assert kwargs["env"]["BORG_RSH"].startswith("ssh -i /tmp/test-browse.key")
        mock_unlink.assert_called_once_with("/tmp/test-browse.key")

    @pytest.mark.asyncio
    async def test_browse_archive_subdirectory_only_returns_immediate_children(
        self,
        test_db,
        admin_user,
    ):
        repo = _create_repository(test_db, name="Nested Repo")
        cached_items = [
            {"path": "home/user", "type": "d", "size": None, "mtime": "2024-01-01T00:00:00"},
            {"path": "home/user/file.txt", "type": "f", "size": 10, "mtime": "2024-01-01T00:00:01"},
            {"path": "home/user/docs", "type": "d", "size": None, "mtime": "2024-01-01T00:00:02"},
            {"path": "home/user/docs/a.txt", "type": "f", "size": 11, "mtime": "2024-01-01T00:00:03"},
            {"path": "home/user/docs/b.txt", "type": "f", "size": 12, "mtime": "2024-01-01T00:00:04"},
            {"path": "home/other/skip.txt", "type": "f", "size": 99, "mtime": "2024-01-01T00:00:05"},
        ]

        with patch.object(browse_api.archive_cache, "get", new=AsyncMock(return_value=cached_items)):
            response = await browse_api.browse_archive_contents(
                repository_id=repo.id,
                archive_name="nested-archive",
                path="home/user",
                current_user=admin_user,
                db=test_db,
            )

        assert response["items"] == [
            {
                "name": "docs",
                "type": "directory",
                "size": 23,
                "mtime": "2024-01-01T00:00:02",
                "path": "home/user/docs",
            },
            {
                "name": "file.txt",
                "type": "file",
                "size": 10,
                "mtime": "2024-01-01T00:00:01",
                "path": "home/user/file.txt",
            },
        ]


@pytest.mark.unit
class TestFilesystemEndpoints:
    """Test filesystem API endpoints"""

    def test_list_directory_unauthorized(self, test_client: TestClient):
        """Test listing directory without authentication"""
        response = test_client.get("/api/filesystem/browse")

        assert response.status_code == 401

    def test_list_directory_root(self, test_client: TestClient, admin_headers):
        """Test listing root directory"""
        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": "/"},
            headers=admin_headers
        )

        assert response.status_code == 200

    def test_list_directory_invalid_path(self, test_client: TestClient, admin_headers):
        """Test listing non-existent directory"""
        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": "/nonexistent/path"},
            headers=admin_headers
        )

        assert response.status_code == 404

    def test_get_directory_info(self, test_client: TestClient, admin_headers):
        """Test getting directory information"""
        response = test_client.get(
            "/api/filesystem/info",
            params={"path": "/tmp"},
            headers=admin_headers
        )

        assert response.status_code == 404

    def test_create_directory_missing_path(self, test_client: TestClient, admin_headers):
        """Test creating directory without path"""
        response = test_client.post(
            "/api/filesystem/create-folder",
            json={},
            headers=admin_headers
        )

        assert response.status_code == 422

    def test_validate_path_empty(self, test_client: TestClient, admin_headers):
        """Test path validation with empty path"""
        response = test_client.post(
            "/api/filesystem/validate-path",
            params={"path": ""},
            headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json()["exists"] is False

    def test_validate_path_valid(self, test_client: TestClient, admin_headers):
        """Test path validation with valid path"""
        response = test_client.post(
            "/api/filesystem/validate-path",
            params={"path": "/tmp"},
            headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json()["exists"] is True

    def test_get_disk_usage(self, test_client: TestClient, admin_headers):
        """Test getting disk usage for path"""
        response = test_client.get(
            "/api/filesystem/disk-usage",
            params={"path": "/tmp"},
            headers=admin_headers
        )

        assert response.status_code == 404
