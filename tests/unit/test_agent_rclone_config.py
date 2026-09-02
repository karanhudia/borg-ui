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
