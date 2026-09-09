"""One predicate decides both the capability and (in phase 3) the command.

Each precondition is tested failing on its own, because a partial install can
leave any one piece behind without the others, and each would otherwise fail at
a different point after the operator was told the endpoint can upgrade itself.
"""

from pathlib import Path

import pytest

from agent.borg_ui_agent.runtime import get_capabilities
from agent.borg_ui_agent.self_upgrade import check_self_upgrade


@pytest.fixture
def ready(tmp_path: Path):
    """A complete, correct install. Each test breaks exactly one thing."""
    etc = tmp_path / "etc"
    etc.mkdir()
    helper = tmp_path / "opt" / "bin" / "borg-ui-agent-upgrade"
    helper.parent.mkdir(parents=True)
    helper.write_text("#!/bin/sh\n", encoding="utf-8")
    helper.chmod(0o755)
    (etc / "upgrade.conf").write_text(
        "\n".join(
            [
                'SERVER="https://borg.example"',
                'AGENT_ID="agent-1"',
                f'AGENT_ROOT="{helper.parent.parent}"',
                'SYSTEMCTL="/usr/bin/systemctl"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    unit = tmp_path / "borg-ui-agent-upgrade.service"
    unit.write_text(f"[Service]\nExecStart={helper}\n", encoding="utf-8")

    return {
        "etc_dir": etc,
        "unit_path": unit,
        "is_root": lambda: False,
        "sudo_lists": lambda systemctl: True,
    }


def test_a_complete_install_can_upgrade_itself(ready):
    readiness = check_self_upgrade(**ready)

    assert readiness.supported is True
    assert readiness.reason == ""
    assert readiness.systemctl == "/usr/bin/systemctl"
    assert readiness.needs_sudo is True


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
    (ready["etc_dir"] / "upgrade.conf").unlink()

    assert check_self_upgrade(**ready).reason == "conf_missing"


@pytest.mark.parametrize("dropped", ["SERVER", "AGENT_ID", "SYSTEMCTL"])
def test_an_upgrade_conf_short_a_required_field_is_reported_as_missing(ready, dropped):
    conf = ready["etc_dir"] / "upgrade.conf"
    kept = [
        line
        for line in conf.read_text().splitlines()
        if not line.startswith(f"{dropped}=")
    ]
    conf.write_text("\n".join(kept) + "\n", encoding="utf-8")

    assert check_self_upgrade(**ready).reason == "conf_missing"


def test_an_http_endpoint_cannot_upgrade_itself(ready):
    conf = ready["etc_dir"] / "upgrade.conf"
    conf.write_text(
        conf.read_text().replace("https://borg.example", "http://borg.example"),
        encoding="utf-8",
    )

    # The helper refuses a non-https server, so reporting the capability here
    # would promise an upgrade that aborts as soon as it is asked for.
    assert check_self_upgrade(**ready).reason == "server_not_https"


def test_an_unprivileged_agent_without_the_sudoers_rule_reports_no_capability(ready):
    ready["sudo_lists"] = lambda systemctl: False

    assert check_self_upgrade(**ready).reason == "sudo_not_permitted"


def test_a_root_agent_needs_no_sudoers_rule(ready):
    # The installer writes no sudoers file for a root agent, and does not
    # install sudo, so consulting sudo -l would report no capability on exactly
    # the endpoints that need none.
    ready["is_root"] = lambda: True
    ready["sudo_lists"] = lambda systemctl: pytest.fail("sudo must not be consulted")

    readiness = check_self_upgrade(**ready)

    assert readiness.supported is True
    assert readiness.needs_sudo is False


def test_capabilities_include_self_upgrade_only_when_the_endpoint_is_ready(
    monkeypatch,
):
    monkeypatch.setattr("agent.borg_ui_agent.runtime.can_self_upgrade", lambda: False)
    assert "self_upgrade" not in get_capabilities()

    monkeypatch.setattr("agent.borg_ui_agent.runtime.can_self_upgrade", lambda: True)
    assert "self_upgrade" in get_capabilities()
