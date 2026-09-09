"""One predicate decides both the capability and (in phase 3) the command.

Each precondition is tested failing on its own, because a partial install can
leave any one piece behind without the others, and each would otherwise fail at
a different point after the operator was told the endpoint can upgrade itself.
"""

import os
from pathlib import Path

import pytest

from agent.borg_ui_agent.runtime import get_capabilities
from agent.borg_ui_agent.self_upgrade import check_self_upgrade


@pytest.fixture
def ready(tmp_path: Path):
    """A complete, correct install. Each test breaks exactly one thing."""
    conf_path = tmp_path / "borg-ui-agent-upgrade.conf"
    helper = tmp_path / "opt" / "bin" / "borg-ui-agent-upgrade"
    helper.parent.mkdir(parents=True)
    helper.write_text("#!/bin/sh\n", encoding="utf-8")
    helper.chmod(0o755)
    conf_path.write_text(
        "\n".join(
            [
                'SERVER="https://borg.example"',
                'AGENT_ID="agent-1"',
                'BORG_INSTALL_MODE="1"',
                'SERVICE_USER="borg"',
                f'AGENT_ROOT="{helper.parent.parent}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    unit = tmp_path / "borg-ui-agent-upgrade.service"
    unit.write_text(f"[Service]\nExecStart={helper}\n", encoding="utf-8")
    path_unit = tmp_path / "borg-ui-agent-upgrade.path"
    path_unit.write_text("[Path]\nPathExists=/etc/borg-ui-agent\n", encoding="utf-8")
    trigger_dir = tmp_path / "etc"
    trigger_dir.mkdir()

    return {
        "conf_path": conf_path,
        "unit_path": unit,
        "path_unit_path": path_unit,
        "trigger_path": trigger_dir / "upgrade-requested",
    }


def test_a_complete_install_can_upgrade_itself(ready):
    readiness = check_self_upgrade(**ready)

    assert readiness.supported is True
    assert readiness.reason == ""
    assert readiness.trigger == ready["trigger_path"]


def test_a_missing_unit_is_reported_as_such(ready):
    ready["unit_path"].unlink()

    assert check_self_upgrade(**ready).reason == "unit_missing"


def test_a_missing_helper_is_reported_as_such(ready):
    helper = Path(ready["unit_path"].read_text().split("ExecStart=", 1)[1].strip())
    helper.unlink()

    assert check_self_upgrade(**ready).reason == "helper_missing"


def test_a_helper_that_is_not_executable_is_reported_as_missing(ready):
    helper = Path(ready["unit_path"].read_text().split("ExecStart=", 1)[1].strip())
    helper.chmod(0o644)

    assert check_self_upgrade(**ready).reason == "helper_missing"


def test_a_missing_upgrade_conf_is_reported_as_such(ready):
    ready["conf_path"].unlink()

    assert check_self_upgrade(**ready).reason == "conf_missing"


@pytest.mark.parametrize(
    "dropped",
    [
        "SERVER",
        "AGENT_ID",
        "BORG_INSTALL_MODE",
        "SERVICE_USER",
        "AGENT_ROOT",
    ],
)
def test_an_upgrade_conf_short_a_required_field_is_reported_as_missing(ready, dropped):
    conf = ready["conf_path"]
    kept = [
        line
        for line in conf.read_text().splitlines()
        if not line.startswith(f"{dropped}=")
    ]
    conf.write_text("\n".join(kept) + "\n", encoding="utf-8")

    assert check_self_upgrade(**ready).reason == "conf_missing"


def test_an_http_endpoint_cannot_upgrade_itself(ready):
    conf = ready["conf_path"]
    conf.write_text(
        conf.read_text().replace("https://borg.example", "http://borg.example"),
        encoding="utf-8",
    )

    # The helper refuses a non-https server, so reporting the capability here
    # would promise an upgrade that aborts as soon as it is asked for.
    assert check_self_upgrade(**ready).reason == "server_not_https"


def test_an_unwatched_trigger_reports_no_capability(ready):
    # Without the path unit nothing notices the trigger, so the helper is
    # installed but unreachable.
    ready["path_unit_path"].unlink()

    assert check_self_upgrade(**ready).reason == "path_unit_missing"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_an_agent_that_cannot_create_the_trigger_reports_no_capability(ready):
    ready["trigger_path"].parent.chmod(0o500)

    try:
        assert check_self_upgrade(**ready).reason == "trigger_not_writable"
    finally:
        ready["trigger_path"].parent.chmod(0o700)


def test_capabilities_include_self_upgrade_only_when_the_endpoint_is_ready(
    monkeypatch,
):
    monkeypatch.setattr("agent.borg_ui_agent.runtime.can_self_upgrade", lambda: False)
    assert "self_upgrade" not in get_capabilities()

    monkeypatch.setattr("agent.borg_ui_agent.runtime.can_self_upgrade", lambda: True)
    assert "self_upgrade" in get_capabilities()
