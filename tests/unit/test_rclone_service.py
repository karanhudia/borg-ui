import asyncio

import pytest

from app.config import settings
from app.services.rclone_service import RcloneCommandResult, RcloneService
from app.services.rclone_service import rclone_service


@pytest.mark.unit
def test_rclone_command_builders_use_argv_lists():
    service = RcloneService(
        binary="rclone",
        config_path="/data/rclone/prod.conf",
        default_transfers=4,
        default_checkers=8,
    )

    assert service.version_command() == ["rclone", "version"]
    assert service.listremotes_command() == [
        "rclone",
        "--config",
        "/data/rclone/prod.conf",
        "listremotes",
    ]
    assert service.lsjson_command("prod-s3:borg-ui/repositories/app") == [
        "rclone",
        "--config",
        "/data/rclone/prod.conf",
        "lsjson",
        "prod-s3:borg-ui/repositories/app",
    ]
    assert service.sync_command(
        "/cache/repositories/app",
        "prod-s3:borg-ui/repositories/app",
        extra_flags=["--s3-no-check-bucket", "--fast-list"],
    ) == [
        "rclone",
        "--config",
        "/data/rclone/prod.conf",
        "sync",
        "/cache/repositories/app",
        "prod-s3:borg-ui/repositories/app",
        "--transfers",
        "4",
        "--checkers",
        "8",
        "--s3-no-check-bucket",
        "--fast-list",
    ]


@pytest.mark.unit
def test_default_rclone_service_uses_managed_config_file():
    assert rclone_service.config_path == f"{settings.rclone_config_root}/rclone.conf"


@pytest.mark.unit
def test_rclone_redacts_sensitive_command_values():
    service = RcloneService(binary="rclone", config_path="/data/rclone/prod.conf")

    redacted = service.redact_command(
        [
            "rclone",
            "--config",
            "/data/rclone/prod.conf",
            "sync",
            "/cache/repositories/app",
            "prod-s3:borg-ui/repositories/app",
            "--s3-access-key-id",
            "AKIA_TEST",
            "--s3-secret-access-key=secret-value",
            "--password",
            "plain-password",
        ]
    )

    assert "/data/rclone/prod.conf" not in redacted
    assert "/cache/repositories/app" not in redacted
    assert "prod-s3:borg-ui/repositories/app" not in redacted
    assert "AKIA_TEST" not in redacted
    assert "secret-value" not in redacted
    assert "plain-password" not in redacted
    assert "<rclone-config>" in redacted
    assert "<path>" in redacted
    assert "<redacted>" in redacted


@pytest.mark.unit
def test_rclone_parse_json_result():
    result = RcloneCommandResult(
        success=True,
        return_code=0,
        stdout='[{"Name":"config","IsDir":false}]',
        stderr="",
        command=["rclone", "lsjson", "remote:path"],
        redacted_command="rclone lsjson <path>",
    )

    assert result.json() == [{"Name": "config", "IsDir": False}]


@pytest.mark.unit
def test_rclone_execute_uses_create_subprocess_exec(monkeypatch):
    service = RcloneService(binary="rclone")
    captured = {}

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"ok", b""

    async def fake_create_subprocess_exec(*argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = asyncio.run(service.execute(["rclone", "version"], timeout=5))

    assert result.success is True
    assert captured["argv"] == ("rclone", "version")
    assert "shell" not in captured["kwargs"]
