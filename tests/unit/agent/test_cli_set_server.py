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


def _record(monkeypatch, recorded) -> None:
    def recorded_server():
        if isinstance(recorded, Exception):
            raise recorded
        return recorded

    monkeypatch.setattr("agent.borg_ui_agent.cli.recorded_server", recorded_server)


def test_set_server_says_when_the_move_turns_remote_upgrade_off(
    config_path: Path, monkeypatch, capsys
) -> None:
    _record(monkeypatch, "https://borg.example")

    assert (
        main(["--config", str(config_path), "set-server", "https://new.example"]) == 0
    )

    assert "--server https://new.example --reinstall" in capsys.readouterr().out


def test_set_server_names_the_reinstall_for_a_move_from_http_to_https(
    config_path: Path, monkeypatch, capsys
) -> None:
    """The endpoint had no remote upgrade on the old address, and gets it by
    the same reinstall."""
    _record(monkeypatch, "http://192.168.1.81:8083")

    main(["--config", str(config_path), "set-server", "https://borg.example.com"])

    assert "--server https://borg.example.com --reinstall" in capsys.readouterr().out


def test_set_server_quotes_the_address_in_the_command_it_suggests(
    config_path: Path, monkeypatch, capsys
) -> None:
    _record(monkeypatch, "https://borg.example")

    main(["--config", str(config_path), "set-server", "https://new.example/$(id)"])

    assert "--server 'https://new.example/$(id)' --reinstall" in capsys.readouterr().out


@pytest.mark.parametrize(
    "recorded",
    [
        "",  # no upgrade record on this endpoint
        "https://new.example",
        "https://new.example/",
        PermissionError("upgrade record not readable"),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "upgrade record is not text"),
    ],
)
def test_set_server_says_nothing_about_upgrades_otherwise(
    config_path: Path, monkeypatch, capsys, recorded
) -> None:
    _record(monkeypatch, recorded)

    assert (
        main(["--config", str(config_path), "set-server", "https://new.example"]) == 0
    )

    assert "--reinstall" not in capsys.readouterr().out
    assert load_config(config_path).server_url == "https://new.example"


def test_set_server_offers_no_reinstall_towards_a_plain_http_server(
    config_path: Path, monkeypatch, capsys
) -> None:
    _record(monkeypatch, "https://borg.example")

    main(["--config", str(config_path), "set-server", "http://192.168.1.82:8083"])

    assert "--reinstall" not in capsys.readouterr().out
