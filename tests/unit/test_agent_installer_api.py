import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import agent_installer
from app.api.borg_binaries import BORG_BINARIES, CURRENT_VERSIONS, binary_table


def test_agent_installer_script_is_public_and_token_free(test_client: TestClient):
    response = test_client.get("/agent/install.sh")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/x-shellscript")
    assert "borg-ui-agent register" in response.text
    assert "systemctl enable --now borg-ui-agent" in response.text
    assert "service-check" in response.text
    assert "borgui_enroll_" not in response.text
    assert "Raspberry Pi" not in response.text


def test_agent_installer_script_supports_borg_install_modes(test_client: TestClient):
    response = test_client.get("/agent/install.sh")

    assert "--borg-version 1" in response.text
    assert "--borg-version 2" in response.text
    assert "--borg-version both" in response.text
    assert "--skip-borg-install" in response.text
    assert 'BORG_VERSION="1"' in response.text
    # The distribution fallback still verifies by name; the pinned-binary path
    # verifies whichever name it just installed, for both majors.
    assert 'verify_borg_major "borg" "1"' in response.text
    assert 'verify_borg_major "${path_name}" "${major}"' in response.text


def test_agent_installer_script_supports_tokenless_reinstall_mode(
    test_client: TestClient,
):
    response = test_client.get("/agent/install.sh")

    assert "--reinstall" in response.text
    assert 'REINSTALL="0"' in response.text
    assert "Reinstall mode requires an existing /etc/borg-ui-agent/config.toml" in (
        response.text
    )
    assert "Preserving existing agent registration" in response.text
    assert "By default, reinstall mode skips" in response.text
    assert "Skipping Borg installation by default for reinstall mode." in response.text

    reinstall_register_branch = response.text.split(
        'if [[ "${REINSTALL}" == "1" ]]; then\n'
        '  echo "Preserving existing agent registration',
        1,
    )[1].split("else", 1)[0]
    assert " register " not in reinstall_register_branch
    assert '--token "${TOKEN}"' not in reinstall_register_branch
    assert '--name "${AGENT_NAME}"' not in reinstall_register_branch


def test_agent_installer_script_supports_service_user_modes(
    test_client: TestClient,
):
    response = test_client.get("/agent/install.sh")

    assert "[--service-user current|borg-ui-agent|root|USERNAME]" in response.text
    assert 'SERVICE_USER_MODE="current"' in response.text
    assert "--service-user" in response.text
    assert 'if [[ $# -lt 2 || -z "${2:-}" || "${2:-}" == --* ]]; then' in (
        response.text
    )
    assert "resolve_current_service_user" in response.text
    assert "resolve_service_identity" in response.text
    assert (
        "export DEBIAN_FRONTEND=noninteractive\nresolve_service_identity\n\napt-get update"
        in (response.text)
    )
    assert (
        "SUDO_USER is not set. Re-run with sudo from a non-root user" in response.text
    )
    assert "Run as the user who invoked sudo" in response.text
    assert "Run as the dedicated borg-ui-agent system user" in response.text
    assert "Run as root. Advanced; grants root-level Borg operations" in response.text


def test_agent_installer_script_uses_selected_service_identity(
    test_client: TestClient,
):
    response = test_client.get("/agent/install.sh")

    assert (
        'install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750 /etc/borg-ui-agent'
        in (response.text)
    )
    assert (
        'runuser -u "${SERVICE_USER}" -- /opt/borg-ui-agent/.venv/bin/borg-ui-agent'
        in (response.text)
    )
    assert "User=${SERVICE_USER}" in response.text
    assert "Group=${SERVICE_GROUP}" in response.text
    assert "WorkingDirectory=${SERVICE_HOME}" in response.text
    assert '--user "${SERVICE_USER}"' in response.text
    assert '--group "${SERVICE_GROUP}"' in response.text


def test_agent_installer_script_reinstall_preserves_existing_service_user(
    test_client: TestClient,
):
    response = test_client.get("/agent/install.sh")

    assert 'SERVICE_USER_MODE_SET="0"' in response.text
    assert 'SERVICE_USER_MODE_SET="1"' in response.text
    assert (
        '[[ "${REINSTALL}" == "1" && "${SERVICE_USER_MODE_SET}" == "0" ]]'
        in response.text
    )
    assert "/etc/systemd/system/borg-ui-agent.service" in response.text
    assert "awk -F= '/^User=/" in response.text
    assert "Reinstall: preserving existing service user" in response.text


def test_agent_installer_script_prepares_config_for_selected_service_user(
    test_client: TestClient,
):
    response = test_client.get("/agent/install.sh")

    assert "prepare_agent_config_path" in response.text
    assert "rm -f /etc/borg-ui-agent/config.toml" in response.text
    assert (
        'chown "${SERVICE_USER}:${SERVICE_GROUP}" /etc/borg-ui-agent/config.toml'
        in response.text
    )
    assert "chmod 0600 /etc/borg-ui-agent/config.toml" in response.text


def test_agent_installer_grants_read_capability_to_non_root_service(
    test_client: TestClient,
):
    """A non-root service cannot read files it does not own, so without this a
    complete backup requires --service-user root."""
    response = test_client.get("/agent/install.sh")

    assert "AmbientCapabilities=CAP_DAC_READ_SEARCH" in response.text
    assert "CapabilityBoundingSet=CAP_DAC_READ_SEARCH" in response.text
    # The capability is compatible with the hardened baseline, which stays.
    assert "NoNewPrivileges=true" in response.text
    assert "${SERVICE_CAPABILITIES}" in response.text


def test_agent_installer_omits_capabilities_for_a_root_service(
    test_client: TestClient,
):
    """Root already holds every capability; a bounding set would only take
    capabilities away from it."""
    response = test_client.get("/agent/install.sh")

    assert 'SERVICE_CAPABILITIES=""' in response.text
    assert 'if [[ "${SERVICE_USER}" != "root" ]]; then' in response.text


def test_agent_installer_script_installs_borg_without_a_build_toolchain(
    test_client: TestClient,
):
    """Borg publishes no wheels, so a pip install would compile on every node."""
    response = test_client.get("/agent/install.sh")

    assert "sha256sum -c -" in response.text
    assert 'install -o root -g root -m 0755 "${tmp}" "${dest}"' in response.text
    assert "borgbackup>=2.0.0b1,<3" not in response.text
    assert "build-essential" not in response.text
    assert "libxxhash-dev" not in response.text


def test_agent_installer_script_refuses_an_unverified_binary(
    test_client: TestClient,
):
    response = test_client.get("/agent/install.sh")

    assert "Checksum mismatch for Borg ${version}; refusing to install it." in (
        response.text
    )


def test_agent_installer_script_names_the_fallback_for_unsupported_platforms(
    test_client: TestClient,
):
    """32-bit ARM and musl have no published binary; say so instead of failing
    on a download that was never going to work."""
    response = test_client.get("/agent/install.sh")

    assert "Borg publishes no static binary for 32-bit ARM or musl systems." in (
        response.text
    )
    assert "Re-run with --borg-source distro" in response.text


def test_agent_installer_installs_rclone_with_borg2(test_client: TestClient):
    """No Borg release bundles rclone: it is a separate Go program, and without
    it an entire class of Borg 2 repositories fails at use time."""
    response = test_client.get("/agent/install.sh")

    install_borg2 = response.text.split("install_borg2() {", 1)[1].split("\n}", 1)[0]
    assert "install_rclone" in install_borg2
    # borgstore refuses anything older, and Debian 11 ships 1.53.
    assert '"1.57.0"' in response.text
    assert "is older than the 1.57.0 borgstore requires" in response.text


def test_agent_installer_forwarders_do_not_escalate(
    test_client: TestClient,
):
    """A forwarder in /usr/local/bin is executable by every user on the machine,
    so it must not carry elevation."""
    response = test_client.get("/agent/install.sh")

    forwarder = response.text.split("write_forwarder() {", 1)[1].split("\n}", 1)[0]
    assert "sudo" not in forwarder
    assert 'exec ${target} "\\$@"' in forwarder


def test_agent_installer_installs_the_agent_from_the_enrolling_server(
    test_client: TestClient,
):
    response = test_client.get("/agent/install.sh")

    assert 'AGENT_SOURCE="server"' in response.text
    # Air-gapped: pip resolves the agent and its dependency wheels from the served
    # wheelhouse with the index off, rather than pulling dependencies from PyPI.
    assert "--no-index" in response.text
    assert '--find-links "${SERVER%/}/agent/dist/"' in response.text
    assert '"borg-ui-agent==${PINNED_AGENT_VERSION}"' in response.text
    # Reinstall takes no --server, so the URL comes from the enrolled config.
    assert "s/^server_url[[:space:]]*=" in response.text


def test_agent_package_failure_stops_the_install(test_client: TestClient):
    """An `exit` inside a command substitution only leaves the subshell, so the
    source must be resolved into a variable or a failure would reach pip as an
    empty argument."""
    response = test_client.get("/agent/install.sh")

    assert "$(agent_package_source)" not in response.text
    assert "resolve_agent_package_source\n" in response.text
    assert '"${AGENT_PIP_ARGS[@]}"' in response.text


def test_agent_installer_distinguishes_a_server_without_a_package(
    test_client: TestClient,
):
    """The script may well have been served by a Borg UI instance whose image
    simply carries no agent wheel; saying otherwise sends people hunting in the
    wrong place."""
    response = test_client.get("/agent/install.sh")

    assert "This Borg UI server offers no agent package to install." in response.text
    assert "No server URL is known" in response.text


def test_agent_installer_script_keeps_agent_ref_separate_from_os_release(
    test_client: TestClient,
):
    response = test_client.get("/agent/install.sh")

    assert 'AGENT_REF="main"' in response.text
    assert (
        '"git+https://github.com/karanhudia/borg-ui.git@${AGENT_REF}"' in response.text
    )
    assert "@${VERSION}" not in response.text


def test_agent_installer_pins_the_versions_the_server_runs(monkeypatch):
    """The node must get the Borg the server runs, not what a distribution
    happens to ship. The server reads its own versions rather than keeping a
    second constant that can drift from the image."""
    borg1, borg2 = CURRENT_VERSIONS["1"], CURRENT_VERSIONS["2"]
    monkeypatch.setattr(
        agent_installer,
        "_installed_borg_version",
        lambda factory, label: {"borg1": borg1, "borg2": borg2}[label],
    )
    monkeypatch.setattr(
        agent_installer,
        "agent_package_path",
        lambda: Path("/opt/borg-ui/agent-dist/borg_ui_agent-0.1.2-py3-none-any.whl"),
    )

    script = agent_installer.render_installer_script()

    assert f'PINNED_BORG1_VERSION="{borg1}"' in script
    assert f'PINNED_BORG2_VERSION="{borg2}"' in script
    assert 'PINNED_AGENT_VERSION="0.1.2"' in script
    # The binary rows are exactly what the manifest renders for these versions —
    # derived, not hardcoded, so a version bump does not turn this into a chore.
    assert binary_table({"1": borg1, "2": borg2}) in script
    assert any(b.arch == "x86_64" for b in BORG_BINARIES[borg1]), (
        f"no x86_64 binary recorded for Borg {borg1}"
    )


def test_agent_installer_survives_a_server_without_borg(monkeypatch):
    """An unknown version contributes no rows, and the script then says so
    instead of installing some other version."""
    monkeypatch.setattr(
        agent_installer, "_installed_borg_version", lambda factory, label: None
    )
    monkeypatch.setattr(agent_installer, "agent_package_path", lambda: None)

    script = agent_installer.render_installer_script()

    assert 'PINNED_BORG1_VERSION=""' in script
    assert 'PINNED_BORG_BINARIES=""' in script
    assert "did not report a Borg ${major} version" in script


def test_agent_installer_rewrites_only_the_pinning_block(monkeypatch):
    """Everything outside the delimited block is served verbatim, so the script
    in the repository stays the script that runs."""
    monkeypatch.setattr(
        agent_installer,
        "_installed_borg_version",
        lambda factory, label: CURRENT_VERSIONS["1"],
    )
    monkeypatch.setattr(agent_installer, "agent_package_path", lambda: None)

    script = agent_installer.render_installer_script()
    raw = agent_installer.INSTALLER_SCRIPT

    assert script.count(agent_installer.PINNING_BEGIN) == 1
    assert script.count(agent_installer.PINNING_END) == 1
    head, _, tail = script.partition(agent_installer.PINNING_END)
    raw_tail = raw.partition(agent_installer.PINNING_END)[2]
    assert tail == raw_tail
    assert head.startswith("#!/usr/bin/env bash\nset -euo pipefail\n")


def test_the_agent_wheelhouse_is_served_as_a_find_links_index(
    test_client: TestClient, tmp_path, monkeypatch
):
    """The installer runs `pip --no-index --find-links <server>/agent/dist/`, so
    the server serves an index page linking every wheel -- the agent and its
    dependencies -- and each wheel under its own name."""
    (tmp_path / "borg_ui_agent-0.1.2-py3-none-any.whl").write_bytes(b"agent wheel")
    (tmp_path / "requests-2.32.3-py3-none-any.whl").write_bytes(b"a dependency wheel")
    monkeypatch.setenv("AGENT_PACKAGE_DIR", str(tmp_path))

    index = test_client.get("/agent/dist/")
    assert index.status_code == 200
    # Both the agent and its dependency wheel are offered, so the install is
    # air-gapped rather than reaching PyPI for the dependencies.
    assert 'href="borg_ui_agent-0.1.2-py3-none-any.whl"' in index.text
    assert 'href="requests-2.32.3-py3-none-any.whl"' in index.text

    wheel = test_client.get("/agent/dist/requests-2.32.3-py3-none-any.whl")
    assert wheel.status_code == 200
    assert wheel.content == b"a dependency wheel"


def test_the_wheelhouse_rejects_non_wheels_and_missing_files(
    test_client: TestClient, tmp_path, monkeypatch
):
    monkeypatch.setenv("AGENT_PACKAGE_DIR", str(tmp_path))

    # a wheel that is not there, and a request that is not a wheel at all
    assert test_client.get("/agent/dist/absent-0.1.0.whl").status_code == 404
    assert test_client.get("/agent/dist/notes.txt").status_code == 404

    # an empty wheelhouse still serves a valid (empty) index rather than an error
    assert test_client.get("/agent/dist/").status_code == 200


def test_agent_installer_script_is_valid_bash(test_client: TestClient):
    response = test_client.get("/agent/install.sh")

    result = subprocess.run(
        ["bash", "-n"],
        input=response.text,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(
    shutil.which("shellcheck") is None, reason="shellcheck is not installed"
)
def test_agent_installer_script_passes_shellcheck(test_client: TestClient):
    response = test_client.get("/agent/install.sh")

    result = subprocess.run(
        ["shellcheck", "--shell=bash", "--severity=warning", "-"],
        input=response.text,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout
