"""The self-upgrade helper runs as root, so its refusals are executed, not read.

Each test extracts the helper exactly as the installer would write it, then
runs it with a fake upgrade.conf and stub binaries on PATH.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HELPER_BEGIN = "cat >\"${UPGRADE_HELPER}\" <<'UPGRADE_HELPER'\n"
HELPER_END = "\nUPGRADE_HELPER\n"


def extract_helper(script: str) -> str:
    body = script.split(HELPER_BEGIN, 1)[1].split(HELPER_END, 1)[0]
    assert body.startswith("#!/usr/bin/env bash"), body[:80]
    return body


@pytest.fixture
def helper_env(tmp_path: Path, test_client: TestClient):
    """A helper on disk plus the knobs each test varies."""
    script = test_client.get("/agent/install.sh").text
    helper = tmp_path / "borg-ui-agent-upgrade"
    helper.write_text(extract_helper(script), encoding="utf-8")
    helper.chmod(0o755)

    etc = tmp_path / "etc"
    etc.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    def write_conf(server: str = "https://borg.example:8083") -> None:
        (tmp_path / "upgrade.conf").write_text(
            "\n".join(
                [
                    f'SERVER="{server}"',
                    'AGENT_ID="agent-1"',
                    'BORG_INSTALL_MODE="skip"',
                    'SERVICE_USER_MODE="current"',
                    'SERVICE_USER="borg"',
                    'SERVICE_GROUP="borg"',
                    'AGENT_ROOT="/opt/borg-ui-agent"',
                    'SYSTEMCTL="/usr/bin/systemctl"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (etc / "config.toml").write_text(
            f'server_url = "{server}"\nagent_id = "agent-1"\n', encoding="utf-8"
        )

    def stub(name: str, body: str) -> None:
        # An absolute interpreter, not /usr/bin/env: one test stubs bash
        # itself, and `env bash` would resolve back through the stub PATH into
        # the stub, recursively.
        path = bin_dir / name
        path.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
        path.chmod(0o755)

    def run() -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env["BORG_UI_UPGRADE_ETC"] = str(etc)
        env["BORG_UI_UPGRADE_CONF"] = str(tmp_path / "upgrade.conf")
        env["BORG_UI_UPGRADE_TRIGGER"] = str(tmp_path / "upgrade-requested")
        # /bin/bash, not "bash": one test stubs bash on PATH to capture the
        # reinstall argv, and resolving the interpreter through PATH would run
        # that stub instead of the helper.
        return subprocess.run(
            ["/bin/bash", str(helper)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    write_conf()
    # A cooperative default: the script downloads, the digest matches, and the
    # reinstall is a no-op. Each test overrides what it is about.
    stub("sha256sum", 'echo "deadbeef  $1"')
    stub(
        "curl",
        'out=""\n'
        'url=""\n'
        "while [[ $# -gt 0 ]]; do\n"
        '  if [[ "$1" == "-o" ]]; then out="$2"; shift 2; continue; fi\n'
        '  url="$1"; shift\n'
        "done\n"
        'if [[ "${url}" == *.sha256* ]]; then echo "deadbeef" >"${out}";\n'
        'else echo "#!/bin/sh" >"${out}"; fi\n'
        f'echo "${{url}}" >>"{tmp_path}/curl.log"',
    )

    return {
        "run": run,
        "stub": stub,
        "write_conf": write_conf,
        "tmp_path": tmp_path,
        "etc": etc,
    }


def test_the_helper_refuses_a_non_https_server(helper_env):
    helper_env["write_conf"](server="http://borg.example:8083")

    result = helper_env["run"]()

    assert result.returncode != 0
    assert "https" in result.stderr
    assert not (helper_env["tmp_path"] / "curl.log").exists()


def test_the_helper_refuses_a_server_the_agent_is_not_enrolled_against(helper_env):
    (helper_env["etc"] / "config.toml").write_text(
        'server_url = "https://other.example"\nagent_id = "agent-1"\n',
        encoding="utf-8",
    )

    result = helper_env["run"]()

    assert result.returncode != 0
    assert "enrolled" in result.stderr
    assert not (helper_env["tmp_path"] / "curl.log").exists()


def test_the_helper_executes_nothing_when_the_digest_does_not_match(helper_env):
    helper_env["stub"]("sha256sum", 'echo "notthedigest  $1"')
    helper_env["stub"]("bash", f'echo "$@" >>"{helper_env["tmp_path"]}/reinstall.log"')

    result = helper_env["run"]()

    assert result.returncode != 0
    assert "checksum" in result.stderr.lower()
    assert not (helper_env["tmp_path"] / "reinstall.log").exists()


def test_the_helper_never_follows_a_redirect_and_never_downgrades(helper_env):
    helper_env["run"]()

    recorded = (helper_env["tmp_path"] / "curl.log").read_text()
    assert "https://borg.example:8083/agent/install.sh" in recorded
    helper = (helper_env["tmp_path"] / "borg-ui-agent-upgrade").read_text()
    assert "--proto '=https'" in helper
    assert "--max-redirs 0" in helper
    assert "--insecure" not in helper
    assert "--location-trusted" not in helper


def test_the_helper_reinstalls_with_the_recorded_parameters(helper_env):
    helper_env["stub"]("bash", f'echo "$@" >>"{helper_env["tmp_path"]}/reinstall.log"')

    result = helper_env["run"]()

    assert result.returncode == 0, result.stderr
    argv = (helper_env["tmp_path"] / "reinstall.log").read_text()
    assert "--reinstall" in argv
    assert "--skip-borg-install" in argv
    assert "--service-user borg" in argv


def test_the_helper_clears_the_trigger_before_it_can_fail(helper_env):
    trigger = helper_env["tmp_path"] / "upgrade-requested"
    trigger.write_text("", encoding="utf-8")
    helper_env["write_conf"](server="http://borg.example:8083")

    # The run below aborts on the http server. The trigger still has to be
    # gone, or the path unit would restart the helper forever.
    assert helper_env["run"]().returncode == 1
    assert not trigger.exists()


def test_the_helper_keeps_the_recorded_borg_source(helper_env):
    conf = helper_env["tmp_path"] / "upgrade.conf"
    conf.write_text(
        conf.read_text().replace('BORG_INSTALL_MODE="skip"', 'BORG_INSTALL_MODE="1"')
        + 'BORG_SOURCE="distro"\n',
        encoding="utf-8",
    )
    helper_env["stub"]("bash", f'echo "$@" >>"{helper_env["tmp_path"]}/reinstall.log"')

    result = helper_env["run"]()

    assert result.returncode == 0, result.stderr
    # An endpoint on distribution packages must not be repointed at the
    # server's static binaries by its own upgrade.
    argv = (helper_env["tmp_path"] / "reinstall.log").read_text()
    assert "--borg-version 1" in argv
    assert "--borg-source distro" in argv


@pytest.mark.skipif(
    shutil.which("shellcheck") is None, reason="shellcheck is not installed"
)
def test_the_helper_passes_shellcheck(test_client: TestClient):
    helper = extract_helper(test_client.get("/agent/install.sh").text)

    result = subprocess.run(
        ["shellcheck", "--shell=bash", "--severity=warning", "-"],
        input=helper,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout
