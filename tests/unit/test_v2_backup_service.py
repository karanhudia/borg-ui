from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.v2.backup_service import BackupV2Service


@pytest.mark.unit
def test_validate_local_repository_access_requires_directory(tmp_path):
    repo = SimpleNamespace(path=str(tmp_path / "missing"))

    with pytest.raises(ValueError):
        BackupV2Service().validate_local_repository_access(repo)


@pytest.mark.unit
def test_build_backup_create_command_uses_borg2_shape():
    with patch("app.services.v2.backup_service.borg2.borg_cmd", "borg2"):
        cmd = BackupV2Service().build_backup_create_command(
            repository_path="/repos/v2",
            archive_name="manual-1",
            compression="zstd",
            exclude_patterns=["*.tmp"],
            custom_flags=["--one-file-system"],
        )

    assert cmd == [
        "borg2",
        "--progress",
        "--show-rc",
        "--log-json",
        "-r",
        "/repos/v2",
        "create",
        "--stats",
        "--compression",
        "zstd",
        "--exclude",
        "*.tmp",
        "--one-file-system",
        "manual-1",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_backup_delegates_to_borg2_create():
    repo = SimpleNamespace(
        path="/repos/v2",
        compression="lz4",
        passphrase="secret",
        remote_path="/usr/local/bin/borg2",
    )

    with patch(
        "app.services.v2.backup_service.borg2.create",
        new=AsyncMock(return_value={"success": True}),
    ) as mock_create:
        result = await BackupV2Service().run_backup(
            repo=repo,
            source_paths=["/data/a", "/data/b"],
            archive_name="manual-1",
        )

    assert result == {"success": True}
    mock_create.assert_awaited_once_with(
        repository="/repos/v2",
        source_paths=["/data/a", "/data/b"],
        compression="lz4",
        archive_name="manual-1",
        passphrase="secret",
        remote_path="/usr/local/bin/borg2",
    )
