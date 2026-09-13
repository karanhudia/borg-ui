from pathlib import Path

import pytest

from agent.borg_ui_agent.cli import main
from agent.borg_ui_agent.config import AgentConfig, load_config, save_config


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    save_config(
        AgentConfig(
            server_url="http://192.168.1.81:8083",
            agent_id="agt_abc",
            agent_token="secret-token",
            name="db-01",
        ),
        path,
    )
    return path


def test_set_server_writes_the_new_url(config_path: Path) -> None:
    assert (
        main(["--config", str(config_path), "set-server", "http://192.168.1.82:8083"])
        == 0
    )
    assert load_config(config_path).server_url == "http://192.168.1.82:8083"


def test_set_server_preserves_identity_and_credential(config_path: Path) -> None:
    main(["--config", str(config_path), "set-server", "https://borg.example.com"])
    config = load_config(config_path)
    assert config.agent_id == "agt_abc"
    assert config.agent_token == "secret-token"
    assert config.name == "db-01"


def test_set_server_strips_a_trailing_slash(config_path: Path) -> None:
    main(["--config", str(config_path), "set-server", "https://borg.example.com/"])
    assert load_config(config_path).server_url == "https://borg.example.com"


@pytest.mark.parametrize(
    "url",
    [
        "borg.example.com",  # no scheme
        "ftp://borg.example.com",  # wrong scheme
        "http://",  # no host
        "http://user@",  # userinfo but no host
        "http://:8083",  # port but no host
        "",  # empty
    ],
)
def test_set_server_rejects_an_unusable_url(config_path: Path, url: str) -> None:
    before = config_path.read_bytes()
    with pytest.raises(SystemExit) as exit_info:
        main(["--config", str(config_path), "set-server", url])
    assert exit_info.value.code == 1
    # The file is byte-identical: a rejected URL must not leave a half-written
    # config on a machine that is already unreachable.
    assert config_path.read_bytes() == before
