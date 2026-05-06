from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.v2.restore_service import RestoreV2Service


@pytest.mark.unit
def test_build_extract_command_uses_borg2_archive_identifier():
    with patch("app.services.v2.restore_service.borg2.borg_cmd", "borg2"):
        cmd = RestoreV2Service().build_extract_command(
            repository_path="/repos/v2",
            archive_name="manual-1",
            paths=["etc/hosts"],
            remote_path="/usr/local/bin/borg2",
            bypass_lock=True,
            strip_components=1,
        )

    assert cmd == [
        "borg2",
        "-r",
        "/repos/v2",
        "extract",
        "--log-json",
        "--remote-path",
        "/usr/local/bin/borg2",
        "--bypass-lock",
        "--strip-components",
        "1",
        "manual-1",
        "etc/hosts",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preview_restore_delegates_to_borg2_extract():
    repo = SimpleNamespace(
        path="/repos/v2",
        passphrase="secret",
        remote_path=None,
        bypass_lock=True,
    )

    with patch(
        "app.services.v2.restore_service.borg2.extract_archive",
        new=AsyncMock(return_value={"success": True, "stdout": "preview"}),
    ) as mock_extract:
        result = await RestoreV2Service().preview_restore(
            repo=repo,
            archive="manual-1",
            paths=["etc/hosts"],
            destination="/restore-target",
        )

    assert result == {"success": True, "stdout": "preview"}
    mock_extract.assert_awaited_once_with(
        repository="/repos/v2",
        archive="manual-1",
        paths=["etc/hosts"],
        destination="/restore-target",
        dry_run=True,
        passphrase="secret",
        remote_path=None,
        bypass_lock=True,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archive_contents_delegates_to_borg2():
    repo = SimpleNamespace(
        path="/repos/v2",
        passphrase="secret",
        remote_path="/usr/local/bin/borg2",
        bypass_lock=False,
    )

    with patch(
        "app.services.v2.restore_service.borg2.list_archive_contents",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_list:
        result = await RestoreV2Service().list_archive_contents(
            repo=repo,
            archive="manual-1",
            path="etc",
            max_lines=123,
        )

    assert result == {"success": True, "stdout": ""}
    mock_list.assert_awaited_once_with(
        repository="/repos/v2",
        archive="manual-1",
        path="etc",
        passphrase="secret",
        remote_path="/usr/local/bin/borg2",
        max_lines=123,
        bypass_lock=False,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archive_contents_omits_empty_path_for_borg2():
    repo = SimpleNamespace(
        path="/repos/v2",
        passphrase="secret",
        remote_path=None,
        bypass_lock=False,
    )

    with patch(
        "app.services.v2.restore_service.borg2.list_archive_contents",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_list:
        await RestoreV2Service().list_archive_contents(
            repo=repo,
            archive="manual-1",
            path="",
            max_lines=99,
        )

    mock_list.assert_awaited_once_with(
        repository="/repos/v2",
        archive="manual-1",
        path="",
        passphrase="secret",
        remote_path=None,
        max_lines=99,
        bypass_lock=False,
    )
