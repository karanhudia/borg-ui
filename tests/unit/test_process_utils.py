from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.utils.process_utils import break_repository_lock


@pytest.mark.unit
def test_break_repository_lock_uses_v1_command_shape():
    repository = SimpleNamespace(
        id=1,
        borg_version=1,
        path="/repo/path",
        passphrase="secret",
        connection_id=None,
        remote_path="/usr/bin/borg",
    )

    with patch("app.utils.process_utils.subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0, stderr="")

        result = break_repository_lock(repository)

    assert result is True
    cmd = mock_run.call_args.args[0]
    env = mock_run.call_args.kwargs["env"]
    assert cmd == ["borg", "break-lock", "--remote-path", "/usr/bin/borg", "/repo/path"]
    assert env["BORG_PASSPHRASE"] == "secret"


@pytest.mark.unit
def test_break_repository_lock_uses_v2_command_shape():
    repository = SimpleNamespace(
        id=2,
        borg_version=2,
        path="/repo/path",
        passphrase="secret",
        connection_id=None,
        remote_path="/usr/bin/borg2",
    )

    with (
        patch("app.core.borg2.borg2.borg_cmd", "borg2"),
        patch("app.utils.process_utils.subprocess.run") as mock_run,
    ):
        mock_run.return_value = SimpleNamespace(returncode=0, stderr="")

        result = break_repository_lock(repository)

    assert result is True
    cmd = mock_run.call_args.args[0]
    env = mock_run.call_args.kwargs["env"]
    assert cmd == [
        "borg2",
        "-r",
        "/repo/path",
        "break-lock",
        "--remote-path",
        "/usr/bin/borg2",
    ]
    assert env["BORG_PASSPHRASE"] == "secret"


@pytest.mark.unit
def test_break_repository_lock_uses_resolved_legacy_ssh_key():
    repository = SimpleNamespace(
        id=3,
        borg_version=1,
        path="ssh://backup@example.com:2222/repo/path",
        passphrase=None,
        connection_id=None,
        remote_path="/usr/bin/borg",
    )
    connection = SimpleNamespace(id=9)
    db = MagicMock()

    with (
        patch("app.utils.process_utils.object_session", return_value=db),
        patch(
            "app.utils.process_utils.resolve_repository_ssh_connection",
            return_value=connection,
        ),
        patch(
            "app.utils.process_utils.resolve_repo_ssh_key_file",
            return_value="/tmp/repository.key",
        ) as resolve_key,
        patch("app.utils.process_utils.cleanup_temp_key_file") as cleanup_key,
        patch("app.utils.process_utils.subprocess.run") as mock_run,
    ):
        mock_run.return_value = SimpleNamespace(returncode=0, stderr="")

        result = break_repository_lock(repository)

    assert result is True
    assert "-i /tmp/repository.key" in mock_run.call_args.kwargs["env"]["BORG_RSH"]
    resolve_key.assert_called_once_with(repository, db)
    cleanup_key.assert_called_once_with("/tmp/repository.key")
