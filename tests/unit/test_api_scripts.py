import pytest
from unittest.mock import AsyncMock, patch

from app.database.models import Repository, SSHConnection


@pytest.mark.unit
class TestScriptTestingEndpoint:
    @pytest.mark.asyncio
    async def test_non_admin_cannot_test_scripts(self, test_client, auth_headers):
        response = test_client.post(
            "/api/scripts/test", headers=auth_headers, json={"script": "echo hi"}
        )

        assert response.status_code == 403
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.scripts.adminAccessRequired"
        )

    def test_empty_script_is_rejected(self, test_client, admin_headers):
        response = test_client.post(
            "/api/scripts/test", headers=admin_headers, json={"script": "   "}
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.scripts.scriptCannotBeEmpty"
        )

    def test_executes_script_with_base_sandbox_environment(
        self, test_client, admin_headers
    ):
        result = {
            "success": True,
            "stdout": "ok",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 0.12,
        }

        with patch(
            "app.api.scripts.execute_script", new=AsyncMock(return_value=result)
        ) as mock_execute:
            response = test_client.post(
                "/api/scripts/test",
                headers=admin_headers,
                json={"script": "echo hello"},
            )

        assert response.status_code == 200
        assert response.json() == result
        mock_execute.assert_awaited_once()
        call = mock_execute.await_args
        assert call.kwargs["script"] == "echo hello"
        assert call.kwargs["timeout"] == 30.0
        assert call.kwargs["context"] == "test"
        assert call.kwargs["env"] == {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/tmp",
            "TMPDIR": "/tmp",
        }

    def test_injects_repository_context_and_source_connection(
        self, test_client, admin_headers, test_db
    ):
        connection = SSHConnection(
            host="backup.example.com",
            username="borg",
            port=2222,
            ssh_key_id=None,
        )
        test_db.add(connection)
        test_db.commit()
        test_db.refresh(connection)

        repo = Repository(
            name="Repo",
            path="/backups/repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
            source_ssh_connection_id=connection.id,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.scripts.execute_script",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "stdout": "",
                    "stderr": "",
                    "exit_code": 0,
                    "execution_time": 0.01,
                }
            ),
        ) as mock_execute:
            response = test_client.post(
                "/api/scripts/test",
                headers=admin_headers,
                json={"script": "env", "repository_id": repo.id},
            )

        assert response.status_code == 200
        env = mock_execute.await_args.kwargs["env"]
        assert env["BORG_UI_REPOSITORY_ID"] == str(repo.id)
        assert env["BORG_UI_REPOSITORY_NAME"] == repo.name
        assert env["BORG_UI_REPOSITORY_PATH"] == repo.path
        assert env["BORG_UI_HOOK_TYPE"] == "pre-backup"
        assert env["BORG_UI_REMOTE_HOST"] == connection.host
        assert env["BORG_UI_REMOTE_PORT"] == str(connection.port)
        assert env["BORG_UI_REMOTE_USERNAME"] == connection.username

    def test_timeout_result_is_returned_as_http_error(self, test_client, admin_headers):
        with patch(
            "app.api.scripts.execute_script",
            new=AsyncMock(
                return_value={
                    "success": False,
                    "stdout": "",
                    "stderr": "script timed out after 30s",
                    "exit_code": -1,
                    "execution_time": 30.0,
                }
            ),
        ):
            response = test_client.post(
                "/api/scripts/test",
                headers=admin_headers,
                json={"script": "sleep 999"},
            )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.scripts.scriptExecutionTimedOut"
        )
