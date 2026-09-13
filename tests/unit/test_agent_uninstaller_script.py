import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_STUBS = """
run_systemctl() { echo "systemctl $*" >>"${CALL_LOG}"; }
run_userdel() { echo "userdel $1" >>"${CALL_LOG}"; }
"""


def _extract(script: str, *names: str) -> str:
    return "\n".join(
        re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", script, re.M | re.S).group(0)
        for name in names
    )


def _run(
    script: str, *, functions: tuple[str, ...], body: str, env: dict[str, str]
) -> subprocess.CompletedProcess:
    harness = "\n".join(
        [
            "set -uo pipefail",
            "FAILURES=()",
            'note_failure() { FAILURES+=("$1"); }',
            _STUBS,
            _extract(script, *functions),
            body,
        ]
    )
    return subprocess.run(
        ["bash", "-c", harness],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", **env},
    )


@pytest.fixture
def script(test_client: TestClient) -> str:
    return test_client.get("/agent/uninstall.sh").text


@pytest.fixture
def call_log(tmp_path: Path) -> Path:
    path = tmp_path / "calls.log"
    path.touch()
    return path


def test_removes_a_symlink_into_the_agent_root(
    script: str, tmp_path: Path, call_log: Path
):
    agent_root = tmp_path / "opt" / "borg-ui-agent"
    (agent_root / "bin").mkdir(parents=True)
    forwarder = agent_root / "bin" / "borg"
    forwarder.write_text("#!/bin/sh\n")
    link = tmp_path / "usr" / "local" / "bin" / "borg"
    link.parent.mkdir(parents=True)
    link.symlink_to(forwarder)

    result = _run(
        script,
        functions=("remove_borg_links",),
        body="remove_borg_links",
        env={
            "CALL_LOG": str(call_log),
            "AGENT_ROOT": str(agent_root),
            "BORG1_LINK": str(link),
            "BORG2_LINK": str(tmp_path / "usr" / "local" / "bin" / "borg2"),
            "KEEP_BORG": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert not link.exists() and not link.is_symlink()


def test_leaves_a_distro_borg_symlink_alone(
    script: str, tmp_path: Path, call_log: Path
):
    """SAFETY RULE 1. If this ever inverts, an uninstall breaks Borg for
    everything else on the machine, including backups run outside Borg UI."""
    agent_root = tmp_path / "opt" / "borg-ui-agent"
    agent_root.mkdir(parents=True)
    distro_borg = tmp_path / "usr" / "bin" / "borg"
    distro_borg.parent.mkdir(parents=True)
    distro_borg.write_text("#!/bin/sh\n")
    link = tmp_path / "usr" / "local" / "bin" / "borg"
    link.parent.mkdir(parents=True)
    link.symlink_to(distro_borg)

    result = _run(
        script,
        functions=("remove_borg_links",),
        body="remove_borg_links",
        env={
            "CALL_LOG": str(call_log),
            "AGENT_ROOT": str(agent_root),
            "BORG1_LINK": str(link),
            "BORG2_LINK": str(tmp_path / "usr" / "local" / "bin" / "borg2"),
            "KEEP_BORG": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert link.is_symlink()
    assert distro_borg.exists()


def test_leaves_a_real_file_at_the_link_path_alone(
    script: str, tmp_path: Path, call_log: Path
):
    """Not a symlink at all: an operator's own binary sitting at the same path
    is not ours to remove."""
    agent_root = tmp_path / "opt" / "borg-ui-agent"
    agent_root.mkdir(parents=True)
    real = tmp_path / "usr" / "local" / "bin" / "borg"
    real.parent.mkdir(parents=True)
    real.write_text("#!/bin/sh\n")

    result = _run(
        script,
        functions=("remove_borg_links",),
        body="remove_borg_links",
        env={
            "CALL_LOG": str(call_log),
            "AGENT_ROOT": str(agent_root),
            "BORG1_LINK": str(real),
            "BORG2_LINK": str(tmp_path / "nope"),
            "KEEP_BORG": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert real.exists()


def test_keep_borg_leaves_an_owned_symlink_alone(
    script: str, tmp_path: Path, call_log: Path
):
    agent_root = tmp_path / "opt" / "borg-ui-agent"
    (agent_root / "bin").mkdir(parents=True)
    forwarder = agent_root / "bin" / "borg"
    forwarder.write_text("#!/bin/sh\n")
    link = tmp_path / "usr" / "local" / "bin" / "borg"
    link.parent.mkdir(parents=True)
    link.symlink_to(forwarder)

    result = _run(
        script,
        functions=("remove_borg_links",),
        body="remove_borg_links",
        env={
            "CALL_LOG": str(call_log),
            "AGENT_ROOT": str(agent_root),
            "BORG1_LINK": str(link),
            "BORG2_LINK": str(tmp_path / "nope"),
            "KEEP_BORG": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    assert link.is_symlink()


def test_deletes_only_the_dedicated_service_user(
    script: str, tmp_path: Path, call_log: Path
):
    """SAFETY RULE 2, the half that acts."""
    unit = tmp_path / "borg-ui-agent.service"
    unit.write_text("[Service]\nUser=borg-ui-agent\nGroup=borg-ui-agent\n")

    result = _run(
        script,
        functions=("remove_service_user",),
        body="remove_service_user",
        env={
            "CALL_LOG": str(call_log),
            "SERVICE_UNIT": str(unit),
            "STATE_DIR": str(tmp_path / "var" / "lib" / "borg-ui-agent"),
            "DEDICATED_USER": "borg-ui-agent",
            "KEEP_USER": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "userdel borg-ui-agent" in call_log.read_text()


def test_never_deletes_an_operator_login_account(
    script: str, tmp_path: Path, call_log: Path
):
    """SAFETY RULE 2, the half that matters. An install run with
    --service-user current binds the unit to the operator's own login account.
    If this ever inverts, an uninstall deletes that account and its home
    directory."""
    unit = tmp_path / "borg-ui-agent.service"
    unit.write_text("[Service]\nUser=someoperator\nGroup=someoperator\n")

    result = _run(
        script,
        functions=("remove_service_user",),
        body="remove_service_user",
        env={
            "CALL_LOG": str(call_log),
            "SERVICE_UNIT": str(unit),
            "STATE_DIR": str(tmp_path / "var" / "lib" / "borg-ui-agent"),
            "DEDICATED_USER": "borg-ui-agent",
            "KEEP_USER": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "userdel" not in call_log.read_text()


def test_never_deletes_root_as_a_service_user(
    script: str, tmp_path: Path, call_log: Path
):
    """--service-user root is a supported install mode."""
    unit = tmp_path / "borg-ui-agent.service"
    unit.write_text("[Service]\nUser=root\n")

    result = _run(
        script,
        functions=("remove_service_user",),
        body="remove_service_user",
        env={
            "CALL_LOG": str(call_log),
            "SERVICE_UNIT": str(unit),
            "STATE_DIR": str(tmp_path / "state"),
            "DEDICATED_USER": "borg-ui-agent",
            "KEEP_USER": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "userdel" not in call_log.read_text()


def test_deletes_nothing_when_the_unit_is_already_gone(
    script: str, tmp_path: Path, call_log: Path
):
    """Silence is not consent. A machine whose unit was removed by hand tells
    us nothing about which account ran the service, so the account stays."""
    result = _run(
        script,
        functions=("remove_service_user",),
        body="remove_service_user",
        env={
            "CALL_LOG": str(call_log),
            "SERVICE_UNIT": str(tmp_path / "absent.service"),
            "STATE_DIR": str(tmp_path / "state"),
            "DEDICATED_USER": "borg-ui-agent",
            "KEEP_USER": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "userdel" not in call_log.read_text()


def test_keep_user_leaves_the_dedicated_account_alone(
    script: str, tmp_path: Path, call_log: Path
):
    unit = tmp_path / "borg-ui-agent.service"
    unit.write_text("[Service]\nUser=borg-ui-agent\n")
    state = tmp_path / "var" / "lib" / "borg-ui-agent"
    state.mkdir(parents=True)

    result = _run(
        script,
        functions=("remove_service_user",),
        body="remove_service_user",
        env={
            "CALL_LOG": str(call_log),
            "SERVICE_UNIT": str(unit),
            "STATE_DIR": str(state),
            "DEDICATED_USER": "borg-ui-agent",
            "KEEP_USER": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "userdel" not in call_log.read_text()
    assert state.exists()


def test_a_failed_userdel_is_reported_rather_than_swallowed(
    script: str, tmp_path: Path, call_log: Path
):
    """Otherwise an account that could not be deleted still ends the run with
    "Borg UI agent removed." """
    unit = tmp_path / "borg-ui-agent.service"
    unit.write_text("[Service]\nUser=borg-ui-agent\n")

    harness = "\n".join(
        [
            "set -uo pipefail",
            "FAILURES=()",
            'note_failure() { FAILURES+=("$1"); }',
            'run_systemctl() { echo "systemctl $*" >>"${CALL_LOG}"; }',
            'run_userdel() { echo "userdel $1" >>"${CALL_LOG}"; return 8; }',
            _extract(script, "remove_service_user", "report"),
            "remove_service_user",
            "report",
        ]
    )
    result = subprocess.run(
        ["bash", "-c", harness],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "CALL_LOG": str(call_log),
            "SERVICE_UNIT": str(unit),
            "STATE_DIR": str(tmp_path / "state"),
            "DEDICATED_USER": "borg-ui-agent",
            "KEEP_USER": "0",
        },
    )

    assert result.returncode != 0
    assert "could not delete the borg-ui-agent account" in result.stderr
    assert "Borg UI agent removed." not in result.stdout


def test_keep_config_keeps_the_config_but_not_the_upgrade_trigger(
    script: str, tmp_path: Path, call_log: Path
):
    config_dir = tmp_path / "etc" / "borg-ui-agent"
    config_dir.mkdir(parents=True)
    config = config_dir / "config.toml"
    config.write_text('server_url = "http://x"\n')
    trigger = config_dir / "upgrade-requested"
    trigger.touch()

    result = _run(
        script,
        functions=("remove_agent_files",),
        body="remove_agent_files",
        env={
            "CALL_LOG": str(call_log),
            "AGENT_ROOT": str(tmp_path / "opt" / "borg-ui-agent"),
            "CONFIG_DIR": str(config_dir),
            "CONFIG_FILE": str(config),
            "UPGRADE_TRIGGER": str(trigger),
            "NO_REMOTE_UPGRADE_MARKER": str(tmp_path / "marker"),
            "KEEP_CONFIG": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    assert config.exists()
    assert not trigger.exists()


def test_removes_the_whole_config_directory_by_default(
    script: str, tmp_path: Path, call_log: Path
):
    config_dir = tmp_path / "etc" / "borg-ui-agent"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text('server_url = "http://x"\n')
    agent_root = tmp_path / "opt" / "borg-ui-agent"
    agent_root.mkdir(parents=True)
    (agent_root / "marker").touch()

    result = _run(
        script,
        functions=("remove_agent_files",),
        body="remove_agent_files",
        env={
            "CALL_LOG": str(call_log),
            "AGENT_ROOT": str(agent_root),
            "CONFIG_DIR": str(config_dir),
            "CONFIG_FILE": str(config_dir / "config.toml"),
            "UPGRADE_TRIGGER": str(config_dir / "upgrade-requested"),
            "NO_REMOTE_UPGRADE_MARKER": str(tmp_path / "marker"),
            "KEEP_CONFIG": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert not config_dir.exists()
    assert not agent_root.exists()


def test_every_removal_tolerates_a_missing_target(
    script: str, tmp_path: Path, call_log: Path
):
    """Spec section 6.5: running the script twice, or on a machine that was
    never fully installed, exits zero."""
    absent = tmp_path / "absent"

    result = _run(
        script,
        functions=("remove_agent_files", "remove_borg_links", "remove_service_user"),
        body="remove_agent_files; remove_borg_links; remove_service_user",
        env={
            "CALL_LOG": str(call_log),
            "AGENT_ROOT": str(absent / "opt"),
            "CONFIG_DIR": str(absent / "etc"),
            "CONFIG_FILE": str(absent / "etc" / "config.toml"),
            "UPGRADE_TRIGGER": str(absent / "etc" / "upgrade-requested"),
            "NO_REMOTE_UPGRADE_MARKER": str(absent / "marker"),
            "SERVICE_UNIT": str(absent / "unit.service"),
            "STATE_DIR": str(absent / "state"),
            "BORG1_LINK": str(absent / "borg"),
            "BORG2_LINK": str(absent / "borg2"),
            "DEDICATED_USER": "borg-ui-agent",
            "KEEP_BORG": "0",
            "KEEP_USER": "0",
            "KEEP_CONFIG": "0",
        },
    )

    assert result.returncode == 0, result.stderr


_CURL_STUB = """
curl() {
  echo "curl $*" >>"${CALL_LOG}"
  cat >>"${STDIN_LOG:-/dev/null}"
  return "${CURL_RC:-0}"
}
"""


def _run_unregister(
    script: str,
    *,
    call_log: Path,
    config: Path,
    curl_rc: str = "0",
    stdin_log: Path | None = None,
) -> subprocess.CompletedProcess:
    harness = "\n".join(
        [
            "set -uo pipefail",
            "FAILURES=()",
            'note_failure() { FAILURES+=("$1"); }',
            _CURL_STUB,
            _extract(script, "unregister"),
            "unregister",
        ]
    )
    return subprocess.run(
        ["bash", "-c", harness],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "CALL_LOG": str(call_log),
            "CONFIG_FILE": str(config),
            "UNREGISTER_TIMEOUT": "5",
            "CURL_RC": curl_rc,
            "STDIN_LOG": str(stdin_log) if stdin_log else "/dev/null",
        },
    )


def _write_config(tmp_path: Path) -> Path:
    config = tmp_path / "config.toml"
    config.write_text(
        'server_url = "https://borg.example.com"\n'
        'agent_id = "agt_abc"\n'
        'agent_token = "secret-token"\n'
        'name = "db-01"\n'
    )
    return config


def test_unregister_calls_the_server_recorded_in_the_config(
    script: str, tmp_path: Path, call_log: Path
):
    stdin_log = tmp_path / "stdin.log"
    result = _run_unregister(
        script, call_log=call_log, config=_write_config(tmp_path), stdin_log=stdin_log
    )

    calls = call_log.read_text()
    assert result.returncode == 0, result.stderr
    assert "https://borg.example.com/api/agents/unregister" in calls
    assert "X-Borg-Agent-Authorization: Bearer secret-token" in stdin_log.read_text()


def test_unregister_keeps_the_token_out_of_the_command_line(
    script: str, tmp_path: Path, call_log: Path
):
    """A command line is world-readable through ps, and this runs as root, so a
    local user on the endpoint could read the credential out of the process
    table while the uninstall runs. The header goes in on stdin instead."""
    stdin_log = tmp_path / "stdin.log"
    _run_unregister(
        script, call_log=call_log, config=_write_config(tmp_path), stdin_log=stdin_log
    )

    assert "secret-token" not in call_log.read_text()
    assert "secret-token" in stdin_log.read_text()


def test_unregister_never_echoes_the_token(script: str, tmp_path: Path, call_log: Path):
    """Spec section 8. The token reaches curl and nothing else."""
    result = _run_unregister(script, call_log=call_log, config=_write_config(tmp_path))

    assert "secret-token" not in result.stdout
    assert "secret-token" not in result.stderr


def test_unregister_continues_when_the_server_is_unreachable(
    script: str, tmp_path: Path, call_log: Path
):
    """Spec section 6.4. A stranded agent is a likely reason to be
    uninstalling, and it must not block local cleanup."""
    result = _run_unregister(
        script, call_log=call_log, config=_write_config(tmp_path), curl_rc="7"
    )

    assert result.returncode == 0, result.stderr
    assert (
        "could not" in result.stdout.lower() or "not notified" in result.stdout.lower()
    )


def test_unregister_skips_a_missing_config(script: str, tmp_path: Path, call_log: Path):
    """Safe on a partially installed or already-unregistered machine."""
    result = _run_unregister(script, call_log=call_log, config=tmp_path / "absent.toml")

    assert result.returncode == 0, result.stderr
    assert call_log.read_text() == ""


_FULL_RUN_STUBS = """
systemctl() { echo "systemctl $*" >>"${CALL_LOG}"; }
userdel() { echo "userdel $*" >>"${CALL_LOG}"; }
curl() { echo "curl $*" >>"${CALL_LOG}"; return "${CURL_RC:-0}"; }
id() { echo 0; }
"""


def _run_whole_script(
    script: str, *, env: dict[str, str], args: tuple[str, ...] = ()
) -> subprocess.CompletedProcess:
    """Runs the script's own main sequence, not a sequence the test invented.

    The ordering of that sequence is itself load-bearing: remove_service_user
    reads User= from the unit, so anything that removes the unit before it runs
    silently turns the dedicated-account removal into a no-op. A test that
    calls the functions in an order of its own choosing cannot see that.
    """
    return subprocess.run(
        ["bash", "-s", "--", *args],
        input=_FULL_RUN_STUBS + script,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", **env},
    )


def _installed_machine(tmp_path: Path, *, unit_user: str) -> dict[str, str]:
    agent_root = tmp_path / "opt" / "borg-ui-agent"
    (agent_root / "bin").mkdir(parents=True)
    config_dir = tmp_path / "etc" / "borg-ui-agent"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text('server_url = "http://x"\n')
    unit = tmp_path / "borg-ui-agent.service"
    unit.write_text(f"[Service]\nUser={unit_user}\n")
    state = tmp_path / "var" / "lib" / "borg-ui-agent"
    state.mkdir(parents=True)

    return {
        "AGENT_ROOT": str(agent_root),
        "CONFIG_DIR": str(config_dir),
        "CONFIG_FILE": str(config_dir / "config.toml"),
        "UPGRADE_TRIGGER": str(config_dir / "upgrade-requested"),
        "SERVICE_UNIT": str(unit),
        "UPGRADE_UNIT": str(tmp_path / "upgrade.service"),
        "UPGRADE_PATH_UNIT": str(tmp_path / "upgrade.path"),
        "UPGRADE_CONF": str(tmp_path / "upgrade.conf"),
        "UPGRADE_HELPER": str(agent_root / "bin" / "borg-ui-agent-upgrade"),
        "LEGACY_SUDOERS": str(tmp_path / "sudoers"),
        "NO_REMOTE_UPGRADE_MARKER": str(tmp_path / "marker"),
        "STATE_DIR": str(state),
        "BORG1_LINK": str(tmp_path / "borg"),
        "BORG2_LINK": str(tmp_path / "borg2"),
        "DEDICATED_USER": "borg-ui-agent",
    }


def test_the_main_sequence_deletes_the_dedicated_user(
    script: str, tmp_path: Path, call_log: Path
):
    """The whole point of the dedicated-account branch, run in the order the
    script actually runs it. remove_service_user reads User= from the unit, so
    a sequence that removes the unit first leaves the account behind forever
    while every isolated test still passes."""
    env = _installed_machine(tmp_path, unit_user="borg-ui-agent")

    result = _run_whole_script(script, env={"CALL_LOG": str(call_log), **env})

    assert result.returncode == 0, result.stderr + result.stdout
    assert "userdel" in call_log.read_text()
    assert not Path(env["AGENT_ROOT"]).exists()
    assert not Path(env["CONFIG_DIR"]).exists()
    assert not Path(env["STATE_DIR"]).exists()


def test_the_main_sequence_removes_the_state_dir_for_any_service_user(
    script: str, tmp_path: Path, call_log: Path
):
    """Spec section 6.2 lists /var/lib/borg-ui-agent under what is always
    removed. Only the account deletion is conditional on which user it is."""
    env = _installed_machine(tmp_path, unit_user="someoperator")

    result = _run_whole_script(script, env={"CALL_LOG": str(call_log), **env})

    assert result.returncode == 0, result.stderr + result.stdout
    assert "userdel" not in call_log.read_text()
    assert not Path(env["STATE_DIR"]).exists()


def test_keep_user_still_keeps_the_state_dir(
    script: str, tmp_path: Path, call_log: Path
):
    env = _installed_machine(tmp_path, unit_user="borg-ui-agent")

    result = _run_whole_script(
        script, env={"CALL_LOG": str(call_log), **env}, args=("--keep-user",)
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "userdel" not in call_log.read_text()
    assert Path(env["STATE_DIR"]).exists()


def test_the_main_sequence_is_idempotent(script: str, tmp_path: Path, call_log: Path):
    """Spec section 6.5: a second run exits zero."""
    env = _installed_machine(tmp_path, unit_user="borg-ui-agent")

    _run_whole_script(script, env={"CALL_LOG": str(call_log), **env})
    second = _run_whole_script(script, env={"CALL_LOG": str(call_log), **env})

    assert second.returncode == 0, second.stderr + second.stdout
