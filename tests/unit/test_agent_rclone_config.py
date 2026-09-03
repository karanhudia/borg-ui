import pytest

from app.database.models import RcloneRemote
from app.services.rclone_repository_service import rclone_repository_service

CONFIG = """[gdrive]
type = drive
scope = drive
token = {"access_token":"real-token"}
client_id = real-client-id
client_secret = real-client-secret
"""


def _remote(config_path):
    return RcloneRemote(
        name="gdrive",
        provider="drive",
        config_path=str(config_path),
        redacted_config={
            "type": "drive",
            "scope": "drive",
            "token": "***",
            "client_id": "***",
            "client_secret": "***",
        },
    )


@pytest.mark.unit
def test_agent_config_sends_real_credentials(tmp_path):
    # The agent writes these into its own rclone.conf and runs rclone against
    # it. Built from redacted_config the secrets arrive as the literal "***",
    # and rclone dies before any network call with
    # "invalid character '*' looking for beginning of value".
    config_path = tmp_path / "rclone.conf"
    config_path.write_text(CONFIG, encoding="utf-8")

    values = rclone_repository_service._agent_rclone_config(_remote(config_path))

    assert values["token"] == '{"access_token":"real-token"}'
    assert values["client_id"] == "real-client-id"
    assert values["client_secret"] == "real-client-secret"
    assert "***" not in values.values()


@pytest.mark.unit
def test_agent_config_keeps_the_remote_type(tmp_path):
    # type is what tells rclone which backend to use; without it the remote is
    # unusable even when the credentials are right.
    config_path = tmp_path / "rclone.conf"
    config_path.write_text(CONFIG, encoding="utf-8")

    values = rclone_repository_service._agent_rclone_config(_remote(config_path))

    assert values["type"] == "drive"


@pytest.mark.unit
def test_agent_config_falls_back_when_the_file_is_unreadable(tmp_path):
    # A missing or unreadable config should not send an empty section: the
    # provider is still known, so rclone can report a useful error about the
    # remote rather than a missing type.
    remote = _remote(tmp_path / "does-not-exist.conf")

    values = rclone_repository_service._agent_rclone_config(remote)

    assert values["type"] == "drive"
    # The whole stored section is carried over, not just the type: an
    # implementation that dropped redacted_config and set only the provider
    # would still produce a "type" and would pass on that assertion alone.
    assert values["scope"] == "drive"
    assert values["token"] == "***"
    assert values["client_id"] == "***"
    assert values["client_secret"] == "***"


@pytest.mark.unit
def test_agent_config_falls_back_when_the_file_cannot_be_read(tmp_path, monkeypatch):
    # The more likely failure in practice: the file exists but the process
    # cannot read it. rclone.conf holds credentials and is normally 0600, so a
    # server running as another user hits PermissionError rather than a
    # missing path. It is an OSError like any other and must not escape.
    config_path = tmp_path / "rclone.conf"
    config_path.write_text(CONFIG, encoding="utf-8")

    real_open = open

    def _deny(path, *args, **kwargs):
        if str(path) == str(config_path):
            raise PermissionError(13, "Permission denied")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", _deny)

    values = rclone_repository_service._agent_rclone_config(_remote(config_path))

    assert values["type"] == "drive"
    assert values["scope"] == "drive"
    assert values["token"] == "***"


@pytest.mark.unit
def test_agent_config_falls_back_when_the_file_is_malformed(tmp_path):
    # A truncated or hand-edited rclone.conf raises configparser.Error rather
    # than OSError, and must fall back the same way instead of propagating.
    config_path = tmp_path / "rclone.conf"
    config_path.write_text("this is not an ini file\n= broken\n", encoding="utf-8")

    values = rclone_repository_service._agent_rclone_config(_remote(config_path))

    assert values["type"] == "drive"
    assert values["token"] == "***"
