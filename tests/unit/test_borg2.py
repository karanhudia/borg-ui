from unittest.mock import AsyncMock, patch

import pytest

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
