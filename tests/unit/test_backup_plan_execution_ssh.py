from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.models import SSHConnection, SSHKey
from app.services.backup_plan_execution_service import backup_plan_execution_service


@pytest.mark.asyncio
async def test_remote_source_script_uses_public_key_only_authentication_options(
    monkeypatch,
):
    source_connection = SSHConnection(
        id=7,
        host="truenas.example",
        username="backup",
        port=2222,
        ssh_key_id=42,
    )
    ssh_key = MagicMock(spec=SSHKey)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = ssh_key
    captured_cmd: list[str] = []

    process = AsyncMock()
    process.communicate = AsyncMock(return_value=(b"ok\n", b""))
    process.returncode = 0

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured_cmd.extend(cmd)
        return process

    monkeypatch.setattr(
        "app.services.backup_plan_execution_service.write_ssh_key_to_tempfile",
        lambda key: "/tmp/source.key",
    )
    monkeypatch.setattr(
        "app.services.backup_plan_execution_service.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    monkeypatch.setattr(
        "app.services.backup_plan_execution_service.os.path.exists",
        lambda path: True,
    )
    monkeypatch.setattr(
        "app.services.backup_plan_execution_service.os.unlink",
        lambda path: None,
    )

    result = await backup_plan_execution_service._execute_remote_source_script(
        source_connection=source_connection,
        script="echo ok",
        timeout=10,
        env={},
        context="source-pre-backup",
        run_id=99,
        db=db,
    )

    assert result["success"] is True
    assert captured_cmd[:3] == ["ssh", "-i", "/tmp/source.key"]
    assert "BatchMode=yes" in captured_cmd
    assert "IdentitiesOnly=yes" in captured_cmd
    assert "PreferredAuthentications=publickey" in captured_cmd
    assert "PasswordAuthentication=no" in captured_cmd
    assert "NumberOfPasswordPrompts=0" in captured_cmd
