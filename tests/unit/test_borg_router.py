from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.borg_router import BorgRouter


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_stats_is_noop_for_v2_repo(db_session):
    repo = SimpleNamespace(borg_version=2)

    result = await BorgRouter(repo).update_stats(db_session)

    assert result is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_stats_delegates_to_v1_repository_helper(db_session):
    repo = SimpleNamespace(borg_version=1)

    with patch(
        "app.api.repositories.update_repository_stats",
        new=AsyncMock(return_value=False),
    ) as mock_update:
        result = await BorgRouter(repo).update_stats(db_session)

    assert result is False
    mock_update.assert_awaited_once_with(repo, db_session)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_delegates_to_v2_service():
    repo = SimpleNamespace(borg_version=2, id=41)

    with patch(
        "app.services.v2.check_service.check_v2_service.execute_check",
        new=AsyncMock(),
    ) as mock_check:
        await BorgRouter(repo).check(7)

    mock_check.assert_awaited_once_with(7, 41)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_delegates_to_v1_service():
    repo = SimpleNamespace(borg_version=1, id=19)

    with patch(
        "app.services.check_service.check_service.execute_check",
        new=AsyncMock(),
    ) as mock_check:
        await BorgRouter(repo).check(5)

    mock_check.assert_awaited_once_with(5, 19)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archives_for_v2_returns_parsed_archives():
    repo = SimpleNamespace(
        borg_version=2,
        path="/tmp/repo",
        passphrase="secret",
        remote_path=None,
        bypass_lock=True,
    )

    with patch(
        "app.core.borg2.borg2.list_archives",
        new=AsyncMock(return_value={"success": True, "stdout": '{"archives":[{"name":"a1"}]}'}),
    ):
        archives = await BorgRouter(repo).list_archives()

    assert archives == [{"name": "a1"}]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archives_for_v2_returns_empty_on_failure():
    repo = SimpleNamespace(
        borg_version=2,
        path="/tmp/repo",
        passphrase=None,
        remote_path=None,
        bypass_lock=False,
    )

    with patch(
        "app.core.borg2.borg2.list_archives",
        new=AsyncMock(return_value={"success": False, "stderr": "boom"}),
    ):
        archives = await BorgRouter(repo).list_archives()

    assert archives == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archives_for_v2_returns_empty_on_invalid_json():
    repo = SimpleNamespace(
        borg_version=2,
        path="/tmp/repo",
        passphrase=None,
        remote_path=None,
        bypass_lock=False,
    )

    with patch(
        "app.core.borg2.borg2.list_archives",
        new=AsyncMock(return_value={"success": True, "stdout": "not-json"}),
    ):
        archives = await BorgRouter(repo).list_archives()

    assert archives == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archives_for_v1_returns_stdout_payload():
    repo = SimpleNamespace(
        borg_version=1,
        path="/tmp/repo",
        passphrase="secret",
        remote_path="/usr/bin/borg",
        bypass_lock=True,
    )

    with patch(
        "app.core.borg.borg.list_archives",
        new=AsyncMock(return_value={"success": True, "stdout": [{"archive": "a1"}]}),
    ) as mock_list:
        archives = await BorgRouter(repo).list_archives()

    assert archives == [{"archive": "a1"}]
    mock_list.assert_awaited_once_with(
        "/tmp/repo",
        remote_path="/usr/bin/borg",
        passphrase="secret",
        bypass_lock=True,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archives_for_v1_returns_empty_on_failure():
    repo = SimpleNamespace(
        borg_version=1,
        path="/tmp/repo",
        passphrase=None,
        remote_path=None,
        bypass_lock=False,
    )

    with patch(
        "app.core.borg.borg.list_archives",
        new=AsyncMock(return_value={"success": False, "stderr": "boom"}),
    ):
        archives = await BorgRouter(repo).list_archives()

    assert archives == []
