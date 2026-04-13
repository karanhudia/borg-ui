from unittest.mock import AsyncMock, patch

import pytest

from app.services.repository_service import RepositoryService


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_repository_uses_borg_info_json_command():
    with patch(
        "app.services.repository_service.borg._execute_command",
        new=AsyncMock(
            return_value={"success": True, "stdout": '{"archives":[]}', "stderr": ""}
        ),
    ) as mock_execute:
        result = await RepositoryService().verify_repository(
            path="/tmp/repo",
            passphrase="secret",
            remote_path="/usr/bin/borg",
            bypass_lock=True,
            timeout=12,
        )

    assert result == {"success": True, "info": {"archives": []}}
    mock_execute.assert_awaited_once_with(
        [
            "borg",
            "info",
            "--remote-path",
            "/usr/bin/borg",
            "--bypass-lock",
            "/tmp/repo",
            "--json",
        ],
        timeout=12,
        env=mock_execute.await_args.kwargs["env"],
    )
    env = mock_execute.await_args.kwargs["env"]
    assert env["BORG_PASSPHRASE"] == "secret"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_keyfile_uses_borg_key_export_shape():
    repository = type("Repo", (), {"path": "/tmp/repo", "passphrase": "secret"})()

    process = type(
        "Proc",
        (),
        {
            "returncode": 0,
            "communicate": AsyncMock(return_value=(b"", b"")),
        },
    )()

    with patch(
        "app.services.repository_service.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ) as mock_exec:
        result = await RepositoryService().export_keyfile(repository, "/tmp/repo.key")

    assert result["success"] is True
    args = mock_exec.await_args.args
    assert args[:5] == ("borg", "key", "export", "/tmp/repo", "/tmp/repo.key")
