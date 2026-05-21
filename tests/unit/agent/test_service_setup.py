import getpass
import grp
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.borg_ui_agent.cli import main
from agent.borg_ui_agent.service_setup import (
    DEFAULT_SERVICE_GROUP,
    DEFAULT_SERVICE_USER,
    ServiceSetupError,
    validate_service_identity,
    validate_service_paths,
    validate_service_setup,
)


def test_validate_service_identity_reports_missing_user(monkeypatch):
    def missing_user(name):
        raise KeyError(name)

    monkeypatch.setattr("agent.borg_ui_agent.service_setup.pwd.getpwnam", missing_user)

    with pytest.raises(ServiceSetupError) as exc:
        validate_service_identity(DEFAULT_SERVICE_USER, DEFAULT_SERVICE_GROUP)

    message = str(exc.value)
    assert "Service user 'borg-ui-agent' does not exist" in message
    assert "sudo useradd --system --user-group" in message
    assert "borg-ui-agent" in message


def test_validate_service_identity_reports_missing_group(monkeypatch):
    monkeypatch.setattr(
        "agent.borg_ui_agent.service_setup.pwd.getpwnam",
        lambda name: SimpleNamespace(pw_name=name),
    )

    def missing_group(name):
        raise KeyError(name)

    monkeypatch.setattr("agent.borg_ui_agent.service_setup.grp.getgrnam", missing_group)

    with pytest.raises(ServiceSetupError) as exc:
        validate_service_identity(DEFAULT_SERVICE_USER, DEFAULT_SERVICE_GROUP)

    message = str(exc.value)
    assert "Service group 'borg-ui-agent' does not exist" in message
    assert "sudo groupadd --system borg-ui-agent" in message


def test_validate_service_identity_accepts_existing_user_and_group(monkeypatch):
    monkeypatch.setattr(
        "agent.borg_ui_agent.service_setup.pwd.getpwnam",
        lambda name: SimpleNamespace(pw_name=name),
    )
    monkeypatch.setattr(
        "agent.borg_ui_agent.service_setup.grp.getgrnam",
        lambda name: SimpleNamespace(gr_name=name),
    )

    validate_service_identity(DEFAULT_SERVICE_USER, DEFAULT_SERVICE_GROUP)


def test_validate_service_paths_reports_missing_executable(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")

    with pytest.raises(ServiceSetupError) as exc:
        validate_service_paths(
            executable_path=tmp_path / "missing-borg-ui-agent",
            config_path=config_path,
        )

    message = str(exc.value)
    assert "Agent executable" in message
    assert "does not exist" in message
    assert (
        "Install the agent virtual environment before enabling the service" in message
    )


def test_validate_service_paths_reports_non_executable_binary(tmp_path: Path):
    executable_path = tmp_path / "borg-ui-agent"
    executable_path.write_text("#!/bin/sh\n", encoding="utf-8")
    executable_path.chmod(0o644)
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")

    with pytest.raises(ServiceSetupError) as exc:
        validate_service_paths(
            executable_path=executable_path,
            config_path=config_path,
        )

    assert f"Agent executable '{executable_path}' is not executable" in str(exc.value)


def test_validate_service_paths_reports_missing_config(tmp_path: Path):
    executable_path = tmp_path / "borg-ui-agent"
    executable_path.write_text("#!/bin/sh\n", encoding="utf-8")
    executable_path.chmod(0o755)

    with pytest.raises(ServiceSetupError) as exc:
        validate_service_paths(
            executable_path=executable_path,
            config_path=tmp_path / "config.toml",
        )

    message = str(exc.value)
    assert "Agent config" in message
    assert "does not exist" in message
    assert "Register the agent with --config" in message


def test_validate_service_setup_accepts_existing_identity_and_paths(
    monkeypatch, tmp_path: Path
):
    executable_path = tmp_path / "borg-ui-agent"
    executable_path.write_text("#!/bin/sh\n", encoding="utf-8")
    executable_path.chmod(0o755)
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "agent.borg_ui_agent.service_setup.pwd.getpwnam",
        lambda name: SimpleNamespace(pw_name=name),
    )
    monkeypatch.setattr(
        "agent.borg_ui_agent.service_setup.grp.getgrnam",
        lambda name: SimpleNamespace(gr_name=name),
    )

    validate_service_setup(
        user=DEFAULT_SERVICE_USER,
        group=DEFAULT_SERVICE_GROUP,
        executable_path=executable_path,
        config_path=config_path,
    )


def test_service_check_cli_reports_success_for_valid_setup(capsys, tmp_path: Path):
    executable_path = tmp_path / "borg-ui-agent"
    executable_path.write_text("#!/bin/sh\n", encoding="utf-8")
    executable_path.chmod(0o755)
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    current_group = grp.getgrgid(os.getgid()).gr_name

    result = main(
        [
            "service-check",
            "--user",
            getpass.getuser(),
            "--group",
            current_group,
            "--exec",
            str(executable_path),
            "--config",
            str(config_path),
        ]
    )

    output = capsys.readouterr()
    assert result == 0
    assert "borg-ui-agent service setup OK" in output.out
    assert f"user={getpass.getuser()}" in output.out
    assert f"group={current_group}" in output.out


def test_service_check_cli_exits_with_clear_missing_user_error(capsys, tmp_path: Path):
    executable_path = tmp_path / "borg-ui-agent"
    executable_path.write_text("#!/bin/sh\n", encoding="utf-8")
    executable_path.chmod(0o755)
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "service-check",
                "--user",
                "__borg_ui_missing_user__",
                "--group",
                grp.getgrgid(os.getgid()).gr_name,
                "--exec",
                str(executable_path),
                "--config",
                str(config_path),
            ]
        )

    output = capsys.readouterr()
    assert exc.value.code == 1
    assert "borg-ui-agent: Service user '__borg_ui_missing_user__' does not exist" in (
        output.err
    )
