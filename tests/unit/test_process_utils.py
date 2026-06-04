from types import SimpleNamespace
from unittest.mock import patch

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
