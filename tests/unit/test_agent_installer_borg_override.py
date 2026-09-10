"""The pinned Borg version has to beat how the endpoint was installed.

The upgrade helper passes --borg-version (or --skip-borg-install) from
upgrade.conf, which records the install, and a bare --reinstall skips Borg by
default. A pin is what an operator asked for afterwards, so it outranks both.
The function is extracted from the served script and run, not read.
"""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import agent_installer

FUNCTION_NAME = "apply_pinned_borg_version"


def extract_function(script: str, name: str) -> str:
    """The function body, from its opening line to the closing brace in
    column 0. Bash has no other way to say where a function ends, and the
    installer writes every function this way."""
    begin = script.index(f"{name}() {{")
    end = script.index("\n}\n", begin) + len("\n}\n")
    body = script[begin:end]
    assert body.rstrip().endswith("}"), body[-80:]
    return body


def run_override(
    tmp_path: Path,
    *,
    pinned: str,
    borg_version: str = "1",
    borg_version_set: str = "0",
    skip_borg_install: str = "0",
    borg_source: str = "server",
) -> dict[str, str]:
    """Run the function with the variables the installer would hold, and
    report what it left them as."""
    body = extract_function(agent_installer.render_installer_script(), FUNCTION_NAME)
    harness = tmp_path / "harness.sh"
    harness.write_text(
        "\n".join(
            [
                "set -euo pipefail",
                f'PINNED_DESIRED_BORG_VERSION="{pinned}"',
                f'BORG_VERSION="{borg_version}"',
                f'BORG_VERSION_SET="{borg_version_set}"',
                f'SKIP_BORG_INSTALL="{skip_borg_install}"',
                f'BORG_SOURCE="{borg_source}"',
                body,
                FUNCTION_NAME,
                'echo "RESULT BORG_VERSION=${BORG_VERSION}"',
                'echo "RESULT BORG_VERSION_SET=${BORG_VERSION_SET}"',
                'echo "RESULT SKIP_BORG_INSTALL=${SKIP_BORG_INSTALL}"',
                'echo "RESULT BORG_SOURCE=${BORG_SOURCE}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["bash", str(harness)], capture_output=True, text=True, timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    return dict(
        line.removeprefix("RESULT ").split("=", 1)
        for line in completed.stdout.splitlines()
        if line.startswith("RESULT ")
    )


def test_no_pin_leaves_every_choice_alone(tmp_path):
    """The unpinned case is every first-time install and every endpoint
    without a pin, so it must not change behaviour at all."""
    result = run_override(tmp_path, pinned="", borg_version="1", skip_borg_install="1")

    assert result["BORG_VERSION"] == "1"
    assert result["BORG_VERSION_SET"] == "0"
    assert result["SKIP_BORG_INSTALL"] == "1"


def test_a_pin_overrides_the_borg_version_the_helper_passed(tmp_path):
    """The helper passes --borg-version 1 from upgrade.conf; the operator
    pinned 2."""
    result = run_override(tmp_path, pinned="2", borg_version="1", borg_version_set="1")

    assert result["BORG_VERSION"] == "2"
    assert result["BORG_VERSION_SET"] == "1"
    assert result["SKIP_BORG_INSTALL"] == "0"


def test_a_pin_overrides_skip_borg_install(tmp_path):
    """An endpoint recorded as BORG_INSTALL_MODE=skip, and a bare --reinstall,
    both arrive here with SKIP_BORG_INSTALL=1. A pin has to win or such an
    endpoint could never be moved from the UI."""
    result = run_override(tmp_path, pinned="2", skip_borg_install="1")

    assert result["BORG_VERSION"] == "2"
    assert result["SKIP_BORG_INSTALL"] == "0"


def test_pinning_borg_2_on_a_distro_endpoint_falls_back_to_server_binaries(tmp_path):
    """No distribution ships Borg 2 and install_borg2 exits on distro, which
    would fail the whole reinstall and lose the agent upgrade with it."""
    result = run_override(tmp_path, pinned="2", borg_source="distro")

    assert result["BORG_VERSION"] == "2"
    assert result["BORG_SOURCE"] == "server"


def test_pinning_borg_1_leaves_a_distro_endpoint_on_distro(tmp_path):
    """Distributions do ship Borg 1, so an endpoint installed from packages
    must not be repointed at the server's binaries by a pin it already
    satisfies."""
    result = run_override(tmp_path, pinned="1", borg_source="distro")

    assert result["BORG_VERSION"] == "1"
    assert result["BORG_SOURCE"] == "distro"


@pytest.mark.parametrize("pinned", ["3", "both", "1.2"])
def test_an_unusable_pin_changes_nothing(tmp_path, pinned):
    """The server drops these before they are served (Task 1). The script
    still refuses them: it is also runnable straight from the repository, and
    a pin it cannot map to install_borg1 or install_borg2 must not silently
    become one of them."""
    result = run_override(
        tmp_path, pinned=pinned, borg_version="1", skip_borg_install="1"
    )

    assert result["BORG_VERSION"] == "1"
    assert result["SKIP_BORG_INSTALL"] == "1"


def test_the_override_runs_after_the_reinstall_defaults_and_before_the_install(
    test_client: TestClient,
):
    """Placement is the property under test. Called before the reinstall block
    it would be undone by the skip-by-default; called after the install case
    or after write_upgrade_conf it would decide nothing."""
    script = test_client.get("/agent/install.sh").text
    call_site = script.index(f"\n{FUNCTION_NAME}\n")

    assert call_site > script.index("Skipping Borg installation by default")
    # rindex, not index: the first `case "${BORG_VERSION}" in` is the
    # --borg-version argument parser near the top. The last one is the install
    # dispatch that acts on the value this function may have changed.
    assert call_site < script.rindex('case "${BORG_VERSION}" in')
    assert call_site < script.index("write_upgrade_conf()")
