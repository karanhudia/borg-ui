from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.borg2 import borg2
from app.services.v2.repository_service import RepositoryV2Service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_repository_uses_borg2_info_shape_without_ssh_key():
    with patch(
        "app.services.v2.repository_service.borg2.info_repo",
        new=AsyncMock(return_value={"success": True}),
    ) as mock_info:
        result = await RepositoryV2Service().verify_repository(
            path="/tmp/repo",
            passphrase="secret",
            remote_path="/usr/bin/borg2",
            timeout=23,
            bypass_lock=True,
        )

    assert result == {"success": True}
    mock_info.assert_awaited_once_with(
        repository="/tmp/repo",
        passphrase="secret",
        remote_path="/usr/bin/borg2",
        bypass_lock=True,
        timeout=23,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_repository_uses_borg2_rcreate_without_ssh_key():
    with patch(
        "app.services.v2.repository_service.borg2.rcreate",
        new=AsyncMock(return_value={"success": True}),
    ) as mock_create:
        result = await RepositoryV2Service().initialize_repository(
            path="/tmp/repo",
            encryption="repokey-aes-ocb",
            passphrase="secret",
            remote_path="/usr/bin/borg2",
            init_timeout=50,
        )

    assert result == {"success": True}
    mock_create.assert_awaited_once_with(
        repository="/tmp/repo",
        encryption="repokey-aes-ocb",
        passphrase="secret",
        remote_path="/usr/bin/borg2",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_repository_with_ssh_key_disables_the_store_cache():
    """The SSH-key create runs with the key's environment, which carries the
    pack cache default; repo-create must still run with the cache off, or
    every create after the first one fails on the populated cache."""

    @contextmanager
    def fake_ssh_key_borg_env(**kwargs):
        yield {
            "BORG_STORE_CACHE": "1",
            "BORG_PASSPHRASE": "secret",
            "BORG_RSH": "ssh -i /tmp/key",
        }

    with (
        patch(
            "app.services.v2.repository_service.ssh_key_borg_env",
            fake_ssh_key_borg_env,
        ),
        patch.object(
            borg2, "_run", new=AsyncMock(return_value={"success": True})
        ) as mock_run,
        patch.object(borg2, "borg_cmd", "borg2"),
    ):
        result = await RepositoryV2Service().initialize_repository(
            path="ssh://borg@host:22/./repo",
            encryption="repokey-aes-ocb",
            passphrase="secret",
            ssh_key_id=7,
            remote_path="/usr/bin/borg2",
            init_timeout=50,
        )

    assert result == {"success": True}
    cmd = mock_run.await_args.args[0]
    assert cmd[:4] == ["borg2", "-r", "ssh://borg@host:22/./repo", "repo-create"]
    assert mock_run.await_args.kwargs["timeout"] == 50
    env = borg2._command_env(cmd, mock_run.await_args.kwargs["env"])
    assert env["BORG_STORE_CACHE"] == ""
    assert env["BORG_RSH"].startswith("ssh -i /tmp/key")
    assert env["BORG_PASSPHRASE"] == "secret"
    assert env["BORG_REMOTE_PATH"] == "/usr/bin/borg2"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_keyfile_uses_borg2_key_export_shape():
    repository = SimpleNamespace(
        path="/tmp/repo", passphrase="secret", remote_path="/usr/bin/borg2"
    )

    with (
        patch(
            "app.services.v2.repository_service.borg2._run",
            new=AsyncMock(return_value={"success": True}),
        ) as mock_run,
        patch("app.services.v2.repository_service.borg2.borg_cmd", "borg2"),
    ):
        result = await RepositoryV2Service().export_keyfile(repository, "/tmp/repo.key")

    assert result == {"success": True}
    mock_run.assert_awaited_once_with(
        [
            "borg2",
            "-r",
            "/tmp/repo",
            "key",
            "export",
            "/tmp/repo.key",
        ],
        timeout=30,
        env={"BORG_REMOTE_PATH": "/usr/bin/borg2", "BORG_PASSPHRASE": "secret"},
    )
