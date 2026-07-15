from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.core.borg2 import borg2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archive_contents_uses_absolute_depth_for_browse():
    with patch.object(
        borg2,
        "_run_streaming",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_run:
        await borg2.list_archive_contents(
            repository="/repo",
            archive="archive-1",
            path="docs/sub",
            browse_depth=3,
        )

    mock_run.assert_awaited_once_with(
        [
            "borg2",
            "-r",
            "/repo",
            "list",
            "--json-lines",
            "--depth",
            "3",
            "archive-1",
            "docs/sub",
        ],
        max_lines=1_000_000,
        env=None,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archive_contents_omits_depth_when_not_requested():
    with patch.object(
        borg2,
        "_run_streaming",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_run:
        await borg2.list_archive_contents(
            repository="/repo",
            archive="archive-1",
            path="",
        )

    mock_run.assert_awaited_once_with(
        ["borg2", "-r", "/repo", "list", "--json-lines", "archive-1"],
        max_lines=1_000_000,
        env=None,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_archive_uses_restore_umask():
    with patch.object(
        borg2,
        "_run",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_run:
        await borg2.extract_archive(
            repository="/repo",
            archive="archive-1",
            paths=["home/user/file.txt"],
            destination="/restore",
        )

    mock_run.assert_awaited_once_with(
        [
            "borg2",
            "-r",
            "/repo",
            "extract",
            "--umask",
            "0022",
            "archive-1",
            "home/user/file.txt",
        ],
        timeout=3600,
        cwd="/restore",
        env=None,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rcreate_injects_managed_rclone_config_into_process_env(
    monkeypatch, tmp_path
):
    rclone_root = tmp_path / "rclone"
    monkeypatch.setattr(settings, "rclone_config_root", str(rclone_root))
    captured: dict[str, object] = {}

    class Process:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        return Process()

    monkeypatch.setattr(
        "app.core.borg2.asyncio.create_subprocess_exec",
        create_subprocess_exec,
    )

    result = await borg2.rcreate(
        repository="rclone:prod-s3:borg-ui/direct",
        encryption="none",
    )

    assert result["success"] is True
    assert captured["cmd"] == (
        borg2.borg_cmd,
        "-r",
        "rclone:prod-s3:borg-ui/direct",
        "repo-create",
        "--encryption",
        "none",
    )
    assert captured["env"]["RCLONE_CONFIG"] == str(rclone_root / "rclone.conf")
