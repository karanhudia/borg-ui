"""
Unit tests for get_repository_stats passphrase handling

Verifies that the get_repository_stats function and its calling endpoints
correctly pass the repository passphrase and remote_path to borg commands.

Without the passphrase, borg info/list fail on encrypted repositories with
"BORG_PASSPHRASE is not set", causing the stats and archive browser
endpoints to return error payloads that the frontend cannot render.
"""
import subprocess
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

# Mock borg binary check before any app module instantiates BorgInterface
_orig_run = subprocess.run

def _fake_subprocess_run(cmd, *args, **kwargs):
    if cmd and cmd[0] == "borg" and "--version" in cmd:
        result = MagicMock()
        result.returncode = 0
        result.stdout = "borg 1.4.0"
        result.stderr = ""
        return result
    return _orig_run(cmd, *args, **kwargs)

with patch("subprocess.run", side_effect=_fake_subprocess_run):
    from fastapi.testclient import TestClient
    from app.database.models import Repository
    from app.api.repositories import get_repository_stats


@pytest.mark.unit
class TestGetRepositoryStatsEndpoint:
    """Test that the /stats endpoint passes passphrase to borg commands"""

    def test_stats_endpoint_passes_passphrase_to_borg_info(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Stats endpoint must set BORG_PASSPHRASE when calling borg info"""
        repo = Repository(
            name="Encrypted Repo",
            path="/tmp/encrypted-repo",
            encryption="repokey",
            passphrase="my-secret-passphrase",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.repositories.borg._execute_command", new_callable=AsyncMock
        ) as mock_exec, patch(
            "app.api.repositories.borg.list_archives", new_callable=AsyncMock
        ) as mock_list:
            mock_exec.return_value = {
                "success": True,
                "stdout": "Repository ID: abc123\nEncrypted: Yes",
                "stderr": "",
                "return_code": 0,
            }
            mock_list.return_value = {
                "success": True,
                "stdout": '{"archives": []}',
            }

            response = test_client.get(
                f"/api/repositories/{repo.id}/stats", headers=admin_headers
            )

            assert response.status_code == 200

            # Verify borg._execute_command was called with env containing passphrase
            mock_exec.assert_called_once()
            _, kwargs = mock_exec.call_args
            env = kwargs.get("env", {})
            assert env.get("BORG_PASSPHRASE") == "my-secret-passphrase"

    def test_stats_endpoint_passes_passphrase_to_list_archives(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Stats endpoint must pass passphrase kwarg to borg.list_archives"""
        repo = Repository(
            name="Encrypted Repo 2",
            path="/tmp/encrypted-repo-2",
            encryption="repokey",
            passphrase="my-secret-passphrase",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.repositories.borg._execute_command", new_callable=AsyncMock
        ) as mock_exec, patch(
            "app.api.repositories.borg.list_archives", new_callable=AsyncMock
        ) as mock_list:
            mock_exec.return_value = {
                "success": True,
                "stdout": "Repository ID: abc123",
                "stderr": "",
                "return_code": 0,
            }
            mock_list.return_value = {
                "success": True,
                "stdout": '{"archives": [{"name": "archive1"}]}',
            }

            response = test_client.get(
                f"/api/repositories/{repo.id}/stats", headers=admin_headers
            )

            assert response.status_code == 200
            mock_list.assert_called_once()
            _, kwargs = mock_list.call_args
            assert kwargs.get("passphrase") == "my-secret-passphrase"

    def test_stats_endpoint_passes_remote_path(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Stats endpoint must pass remote_path to borg commands"""
        repo = Repository(
            name="Remote Repo",
            path="ssh://user@host/repo",
            encryption="repokey",
            passphrase="secret",
            compression="lz4",
            repository_type="ssh",
            remote_path="/usr/local/bin/borg1",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.repositories.borg._execute_command", new_callable=AsyncMock
        ) as mock_exec, patch(
            "app.api.repositories.borg.list_archives", new_callable=AsyncMock
        ) as mock_list:
            mock_exec.return_value = {
                "success": True,
                "stdout": "Repository ID: abc123",
                "stderr": "",
                "return_code": 0,
            }
            mock_list.return_value = {
                "success": True,
                "stdout": '{"archives": []}',
            }

            response = test_client.get(
                f"/api/repositories/{repo.id}/stats", headers=admin_headers
            )

            assert response.status_code == 200

            # Verify --remote-path in borg info command
            cmd_args = mock_exec.call_args[0][0]
            assert "--remote-path" in cmd_args
            assert "/usr/local/bin/borg1" in cmd_args

            # Verify remote_path was passed to list_archives
            _, kwargs = mock_list.call_args
            assert kwargs.get("remote_path") == "/usr/local/bin/borg1"

    def test_stats_endpoint_no_passphrase_for_unencrypted(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """BORG_PASSPHRASE should not be set for unencrypted repos"""
        repo = Repository(
            name="Unencrypted Repo",
            path="/tmp/unencrypted-repo",
            encryption="none",
            passphrase=None,
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.repositories.borg._execute_command", new_callable=AsyncMock
        ) as mock_exec, patch(
            "app.api.repositories.borg.list_archives", new_callable=AsyncMock
        ) as mock_list:
            mock_exec.return_value = {
                "success": True,
                "stdout": "Repository ID: abc123",
                "stderr": "",
                "return_code": 0,
            }
            mock_list.return_value = {
                "success": True,
                "stdout": '{"archives": []}',
            }

            response = test_client.get(
                f"/api/repositories/{repo.id}/stats", headers=admin_headers
            )

            assert response.status_code == 200
            _, kwargs = mock_exec.call_args
            env = kwargs.get("env", {})
            assert "BORG_PASSPHRASE" not in env

    def test_stats_endpoint_handles_borg_info_failure(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Stats endpoint should return error details when borg info fails"""
        repo = Repository(
            name="Failing Repo",
            path="/tmp/failing-repo",
            encryption="repokey",
            passphrase="secret",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.repositories.borg._execute_command", new_callable=AsyncMock
        ) as mock_exec:
            mock_exec.return_value = {
                "success": False,
                "stdout": "",
                "stderr": "Repository does not exist",
                "return_code": 2,
            }

            response = test_client.get(
                f"/api/repositories/{repo.id}/stats", headers=admin_headers
            )

            assert response.status_code == 200
            data = response.json()
            stats = data.get("stats", data)
            assert "error" in stats

    def test_stats_endpoint_passes_bypass_lock(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Stats endpoint should pass bypass_lock to borg commands"""
        repo = Repository(
            name="Locked Repo",
            path="/tmp/locked-repo",
            encryption="repokey",
            passphrase="secret",
            compression="lz4",
            repository_type="local",
            bypass_lock=True,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.repositories.borg._execute_command", new_callable=AsyncMock
        ) as mock_exec, patch(
            "app.api.repositories.borg.list_archives", new_callable=AsyncMock
        ) as mock_list:
            mock_exec.return_value = {
                "success": True,
                "stdout": "Repository ID: abc123",
                "stderr": "",
                "return_code": 0,
            }
            mock_list.return_value = {
                "success": True,
                "stdout": '{"archives": []}',
            }

            response = test_client.get(
                f"/api/repositories/{repo.id}/stats", headers=admin_headers
            )

            assert response.status_code == 200

            # Verify --bypass-lock in borg info command
            cmd_args = mock_exec.call_args[0][0]
            assert "--bypass-lock" in cmd_args

            # Verify bypass_lock passed to list_archives
            _, kwargs = mock_list.call_args
            assert kwargs.get("bypass_lock") is True

    def test_stats_endpoint_not_found(self, test_client: TestClient, admin_headers):
        """Stats endpoint returns 404 for nonexistent repository"""
        response = test_client.get(
            "/api/repositories/99999/stats", headers=admin_headers
        )
        assert response.status_code == 404

    def test_stats_endpoint_no_auth(self, test_client: TestClient):
        """Stats endpoint rejects unauthenticated requests"""
        response = test_client.get("/api/repositories/1/stats")
        assert response.status_code == 401


@pytest.mark.unit
class TestGetRepositoryStatsFunction:
    """Test the get_repository_stats function directly"""

    @pytest.mark.asyncio
    async def test_passphrase_forwarded_to_borg_info(self):
        """get_repository_stats must set BORG_PASSPHRASE in env for borg info"""
        with patch(
            "app.api.repositories.borg._execute_command", new_callable=AsyncMock
        ) as mock_exec, patch(
            "app.api.repositories.borg.list_archives", new_callable=AsyncMock
        ) as mock_list:
            mock_exec.return_value = {
                "success": True,
                "stdout": "Repository ID: abc",
                "stderr": "",
                "return_code": 0,
            }
            mock_list.return_value = {
                "success": True,
                "stdout": '{"archives": []}',
            }

            from app.api.repositories import get_repository_stats

            result = await get_repository_stats("/tmp/repo", passphrase="test-pass")

            assert "error" not in result
            _, kwargs = mock_exec.call_args
            env = kwargs.get("env", {})
            assert env.get("BORG_PASSPHRASE") == "test-pass"

    @pytest.mark.asyncio
    async def test_passphrase_forwarded_to_list_archives(self):
        """get_repository_stats must forward passphrase to list_archives"""
        with patch(
            "app.api.repositories.borg._execute_command", new_callable=AsyncMock
        ) as mock_exec, patch(
            "app.api.repositories.borg.list_archives", new_callable=AsyncMock
        ) as mock_list:
            mock_exec.return_value = {
                "success": True,
                "stdout": "OK",
                "stderr": "",
                "return_code": 0,
            }
            mock_list.return_value = {
                "success": True,
                "stdout": '{"archives": []}',
            }

            from app.api.repositories import get_repository_stats

            await get_repository_stats("/tmp/repo", passphrase="test-pass")

            mock_list.assert_called_once_with(
                "/tmp/repo",
                passphrase="test-pass",
                remote_path=None,
                bypass_lock=False,
            )

    @pytest.mark.asyncio
    async def test_remote_path_included_in_borg_info_cmd(self):
        """get_repository_stats must add --remote-path to borg info command"""
        with patch(
            "app.api.repositories.borg._execute_command", new_callable=AsyncMock
        ) as mock_exec, patch(
            "app.api.repositories.borg.list_archives", new_callable=AsyncMock
        ) as mock_list:
            mock_exec.return_value = {
                "success": True,
                "stdout": "OK",
                "stderr": "",
                "return_code": 0,
            }
            mock_list.return_value = {
                "success": True,
                "stdout": '{"archives": []}',
            }

            from app.api.repositories import get_repository_stats

            await get_repository_stats(
                "ssh://user@host/repo",
                passphrase="pass",
                remote_path="/usr/local/bin/borg1",
            )

            cmd_args = mock_exec.call_args[0][0]
            assert "--remote-path" in cmd_args
            idx = cmd_args.index("--remote-path")
            assert cmd_args[idx + 1] == "/usr/local/bin/borg1"

    @pytest.mark.asyncio
    async def test_remote_path_forwarded_to_list_archives(self):
        """get_repository_stats must forward remote_path to list_archives"""
        with patch(
            "app.api.repositories.borg._execute_command", new_callable=AsyncMock
        ) as mock_exec, patch(
            "app.api.repositories.borg.list_archives", new_callable=AsyncMock
        ) as mock_list:
            mock_exec.return_value = {
                "success": True,
                "stdout": "OK",
                "stderr": "",
                "return_code": 0,
            }
            mock_list.return_value = {
                "success": True,
                "stdout": '{"archives": []}',
            }

            from app.api.repositories import get_repository_stats

            await get_repository_stats(
                "ssh://user@host/repo",
                passphrase="pass",
                remote_path="/usr/local/bin/borg1",
            )

            _, kwargs = mock_list.call_args
            assert kwargs["remote_path"] == "/usr/local/bin/borg1"

    @pytest.mark.asyncio
    async def test_bypass_lock_in_borg_info_cmd(self):
        """get_repository_stats must add --bypass-lock when requested"""
        with patch(
            "app.api.repositories.borg._execute_command", new_callable=AsyncMock
        ) as mock_exec, patch(
            "app.api.repositories.borg.list_archives", new_callable=AsyncMock
        ) as mock_list:
            mock_exec.return_value = {
                "success": True,
                "stdout": "OK",
                "stderr": "",
                "return_code": 0,
            }
            mock_list.return_value = {
                "success": True,
                "stdout": '{"archives": []}',
            }

            from app.api.repositories import get_repository_stats

            await get_repository_stats("/tmp/repo", bypass_lock=True)

            cmd_args = mock_exec.call_args[0][0]
            assert "--bypass-lock" in cmd_args

    @pytest.mark.asyncio
    async def test_no_passphrase_omits_env_key(self):
        """BORG_PASSPHRASE must not be set when passphrase is None"""
        with patch(
            "app.api.repositories.borg._execute_command", new_callable=AsyncMock
        ) as mock_exec, patch(
            "app.api.repositories.borg.list_archives", new_callable=AsyncMock
        ) as mock_list:
            mock_exec.return_value = {
                "success": True,
                "stdout": "OK",
                "stderr": "",
                "return_code": 0,
            }
            mock_list.return_value = {
                "success": True,
                "stdout": '{"archives": []}',
            }

            from app.api.repositories import get_repository_stats

            await get_repository_stats("/tmp/repo", passphrase=None)

            _, kwargs = mock_exec.call_args
            env = kwargs.get("env", {})
            assert "BORG_PASSPHRASE" not in env

    @pytest.mark.asyncio
    async def test_borg_info_failure_returns_error(self):
        """get_repository_stats should return error when borg info fails"""
        with patch(
            "app.api.repositories.borg._execute_command", new_callable=AsyncMock
        ) as mock_exec:
            mock_exec.return_value = {
                "success": False,
                "stdout": "",
                "stderr": "BORG_PASSPHRASE is not set",
                "return_code": 2,
            }

            from app.api.repositories import get_repository_stats

            result = await get_repository_stats("/tmp/repo")

            assert "error" in result
            assert "BORG_PASSPHRASE" in result["details"]

    @pytest.mark.asyncio
    async def test_no_remote_path_omits_flag(self):
        """--remote-path must not be added when remote_path is None"""
        with patch(
            "app.api.repositories.borg._execute_command", new_callable=AsyncMock
        ) as mock_exec, patch(
            "app.api.repositories.borg.list_archives", new_callable=AsyncMock
        ) as mock_list:
            mock_exec.return_value = {
                "success": True,
                "stdout": "OK",
                "stderr": "",
                "return_code": 0,
            }
            mock_list.return_value = {
                "success": True,
                "stdout": '{"archives": []}',
            }

            from app.api.repositories import get_repository_stats

            await get_repository_stats("/tmp/repo", passphrase="pass")

            cmd_args = mock_exec.call_args[0][0]
            assert "--remote-path" not in cmd_args
