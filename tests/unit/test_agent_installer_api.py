import hashlib
import re
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


_INSTALLER_FUNCTIONS = (
    "glibc_at_least",
    "select_borg_binary",
    "lowest_glibc_offered",
    "borg_fallback_advice",
    "install_borg_from_server",
)


def _run_install_borg_from_server(
    script: str, *, major: str, version: str, glibc: str, binaries: str
) -> subprocess.CompletedProcess:
    """Run the installer's server-source path in isolation: only the functions
    it needs, with the machine facts and the pinned manifest table injected."""
    functions = "\n".join(
        re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", script, re.M | re.S).group(0)
        for name in _INSTALLER_FUNCTIONS
    )
    link = "/usr/local/bin/borg2" if major == "2" else "/usr/local/bin/borg"
    harness = "\n".join(
        [
            functions,
            'MACHINE_ARCH="x86_64"',
            f'MACHINE_GLIBC="{glibc}"',
            f'PINNED_BORG_BINARIES="{binaries}"',
            f'install_borg_from_server "{major}" "{version}" {link}',
        ]
    )
    return subprocess.run(
        ["bash", "-c", harness], capture_output=True, text=True, check=False
    )


_MANIFEST_TABLE = "\n".join(
    [
        "1 x86_64 2.31 aa https://example.invalid/borg1-glibc231",
        "1 x86_64 2.35 bb https://example.invalid/borg1-glibc235",
        "2 x86_64 2.43 cc https://example.invalid/borg2-glibc243",
    ]
)


def test_agent_installer_names_the_glibc_floor_for_borg2(test_client: TestClient):
    """A machine below the floor learns the number it misses, and is not sent to
    --borg-source distro, which install_borg2 rejects: Borg 2 has no
    distribution package, so the only way past is a self-managed install."""
    script = test_client.get("/agent/install.sh").text

    result = _run_install_borg_from_server(
        script, major="2", version="2.0.0b24", glibc="2.39", binaries=_MANIFEST_TABLE
    )

    assert result.returncode == 1
    assert (
        "Borg 2.0.0b24 for x86_64 needs glibc 2.43 or newer; "
        "this machine has glibc 2.39."
    ) in result.stderr
    # The agent resolves Borg 2 as `borg2`; a bare pip install provides only
    # `borg`, so the suggested commands pin the server's version and expose it
    # under the name the installer's own forwarder would have used.
    assert "expose it as 'borg2' on PATH" in result.stderr
    # The pip route builds from source: say what the build needs.
    assert "OpenSSL 3.2 or newer" in result.stderr
    assert (
        '/opt/borg2/bin/pip install --pre "borgbackup==2.0.0b24" '
        '"borgstore[rclone,sftp,rest,s3,blake3]"'
    ) in result.stderr
    assert "ln -sfn /opt/borg2/bin/borg /usr/local/bin/borg2" in result.stderr
    assert "--skip-borg-install" in result.stderr
    assert "--borg-source distro" not in result.stderr
    assert "32-bit ARM" not in result.stderr


def test_agent_installer_prints_no_unpinned_borg2_install(test_client: TestClient):
    """Without a version reported by the server there is nothing to pin, and an
    unpinned `pip install borgbackup` would install whatever is newest — a
    different Borg than the server. Say what to do, print no command."""
    script = test_client.get("/agent/install.sh").text

    result = _run_install_borg_from_server(
        script, major="2", version="", glibc="2.39", binaries=_MANIFEST_TABLE
    )

    assert result.returncode == 1
    assert "This Borg UI server did not report a Borg 2 version." in result.stderr
    assert "expose it as 'borg2' on PATH" in result.stderr
    assert "--skip-borg-install" in result.stderr
    assert "pip install" not in result.stderr
    assert "--borg-source distro" not in result.stderr


def test_agent_installer_keeps_the_distro_fallback_for_borg1(
    test_client: TestClient,
):
    """Borg 1 below its floor is pointed at the distribution package."""
    script = test_client.get("/agent/install.sh").text

    result = _run_install_borg_from_server(
        script, major="1", version="1.4.5", glibc="2.28", binaries=_MANIFEST_TABLE
    )

    assert result.returncode == 1
    assert "needs glibc 2.31 or newer; this machine has glibc 2.28." in result.stderr
    assert "Re-run with --borg-source distro" in result.stderr
    assert "pip install" not in result.stderr


def test_agent_installer_explains_an_architecture_without_binaries(
    test_client: TestClient,
):
    """No row for the architecture at all: the reason is the platform, not the
    glibc version, so no floor is quoted."""
    script = test_client.get("/agent/install.sh").text

    result = _run_install_borg_from_server(
        script,
        major="2",
        version="2.0.0b24",
        glibc="2.43",
        binaries="2 aarch64 2.43 cc https://example.invalid/borg2-arm64",
    )

    assert result.returncode == 1
    assert "No published Borg 2.0.0b24 binary for x86_64." in result.stderr
    assert "Borg publishes no static binary for 32-bit ARM or musl systems." in (
        result.stderr
    )
    assert "needs glibc" not in result.stderr
    assert "--skip-borg-install" in result.stderr


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


def test_agent_installer_script_runs_far_enough_to_print_usage(
    test_client: TestClient, tmp_path: Path
):
    # bash -n only parses. Actually running --help catches the runtime aborts
    # set -u produces when a variable is used before it is assigned.
    script = tmp_path / "install.sh"
    script.write_text(test_client.get("/agent/install.sh").text)

    result = subprocess.run(
        ["bash", str(script), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Usage:" in result.stdout


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


def test_the_served_installer_publishes_its_own_checksum(test_client: TestClient):
    script = test_client.get("/agent/install.sh")
    checksum = test_client.get("/agent/install.sh.sha256")

    assert checksum.status_code == 200
    assert checksum.headers["content-type"].startswith("text/plain")

    expected = hashlib.sha256(script.content).hexdigest()
    assert checksum.text.strip() == expected
    # The helper compares against this after downloading, so a checksum that
    # covered anything but the exact served bytes would abort every upgrade.
    assert checksum.text.strip() == checksum.text.strip().lower()


def test_agent_installer_supports_declining_remote_upgrade(test_client: TestClient):
    script = test_client.get("/agent/install.sh").text

    assert "--no-remote-upgrade" in script
    assert 'REMOTE_UPGRADE="1"' in script
    # Outside the agent-owned config directory: a compromised agent must not
    # be able to pin itself onto the manual path and block its own remediation.
    assert 'NO_REMOTE_UPGRADE_MARKER="/etc/borg-ui-agent-no-remote-upgrade"' in (script)


def test_agent_installer_reinstall_preserves_a_declined_remote_upgrade(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    # The marker is what separates "this operator declined" from "this endpoint
    # was installed before remote upgrade existed". Absence must mean the
    # second, so a pre-existing endpoint gains the helper on its next
    # reinstall rather than being locked out of it forever.
    assert (
        'if [[ "${REMOTE_UPGRADE_SET}" == "0" && -e "${NO_REMOTE_UPGRADE_MARKER}" ]]'
        in script
    )
    assert 'REMOTE_UPGRADE="0"' in script


def test_agent_installer_records_the_upgrade_parameters_as_root(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    # Not under /etc/borg-ui-agent: that directory is owned by the service
    # user, which could then replace a file root sources. Root-owned and out of
    # the agent's reach, so the agent cannot repoint its own upgrade at another
    # host (spec section 11.2).
    assert 'UPGRADE_CONF="/etc/borg-ui-agent-upgrade.conf"' in script
    assert "/etc/borg-ui-agent/upgrade.conf" not in script
    assert "install -o root -g root -m 0644 " in script
    for key in (
        "SERVER",
        "AGENT_ID",
        "BORG_INSTALL_MODE",
        "SERVICE_USER_MODE",
        "SERVICE_USER",
        "SERVICE_GROUP",
        "AGENT_ROOT",
    ):
        assert f'{key}="' in script


def test_agent_installer_rejects_an_agent_id_that_is_not_an_identifier(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    # agent_id is read from the service-user-owned config.toml and written into
    # a file root sources, so anything but a plain identifier has to be refused.
    assert '[[ ! "${agent_id}" =~ ^[A-Za-z0-9._-]+$ ]]' in script


def test_agent_installer_writes_a_oneshot_unit_for_the_upgrade(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    assert "/etc/systemd/system/borg-ui-agent-upgrade.service" in script
    assert "Type=oneshot" in script
    assert "ExecStart=${AGENT_ROOT}/bin/borg-ui-agent-upgrade" in script
    # Never enabled: it runs only when something starts it. And the reinstall
    # restarts borg-ui-agent, so it has to live outside that unit's process
    # tree or systemd would kill the upgrade halfway through.
    assert "systemctl enable borg-ui-agent-upgrade" not in script


def test_agent_installer_triggers_the_upgrade_through_a_path_unit(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    # The agent unit runs with NoNewPrivileges=true, which makes sudo refuse to
    # run at all, so the trigger cannot go through sudo. Creating one file the
    # agent already has write access to is the whole escalation.
    assert "/etc/systemd/system/borg-ui-agent-upgrade.path" in script
    assert "PathExists=/etc/borg-ui-agent/upgrade-requested" in script
    assert "Unit=borg-ui-agent-upgrade.service" in script
    assert "systemctl enable --now borg-ui-agent-upgrade.path" in script
    assert 'sudoers.d/borg-ui-agent-upgrade"' not in script
    assert "visudo" not in script


def test_agent_installer_reinstall_prefers_the_root_owned_server(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    # config.toml belongs to the service user. An agent that rewrote its own
    # server_url must not get a bare --reinstall to fetch and run code from
    # wherever it named, nor have that server recorded for later upgrades.
    reinstall = script.split('if [[ "${REINSTALL}" == "1" ]]; then', 1)[1]
    from_conf = reinstall.index('sed -nE \'s/^SERVER="(.*)"$/\\1/p\' "${UPGRADE_CONF}"')
    from_toml = reinstall.index("/etc/borg-ui-agent/config.toml | head -n 1")
    assert from_conf < from_toml


def test_agent_installer_clears_the_trigger_before_arming_the_path_unit(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    # Enabling the unit with a trigger already there starts the helper at once,
    # running a second installer as root on top of the one still going.
    block = script.split("write_upgrade_path_unit() {", 1)[1].split("\n}", 1)[0]
    assert block.index('rm -f "${UPGRADE_TRIGGER}"') < block.index(
        "systemctl enable --now borg-ui-agent-upgrade.path"
    )


def test_agent_installer_helper_clears_its_own_trigger(test_client: TestClient):
    script = test_client.get("/agent/install.sh").text

    # A .path unit re-runs for as long as the trigger exists, so the helper has
    # to remove it before anything that can fail.
    helper = script.split("<<'UPGRADE_HELPER'", 1)[1]
    body = helper.split('if [[ ! -r "${conf}" ]]', 1)[0]
    assert (
        'rm -f "${BORG_UI_UPGRADE_TRIGGER:-/etc/borg-ui-agent/upgrade-requested}"'
        in (body)
    )


def test_agent_installer_takes_away_a_sudoers_rule_from_an_older_install(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    # Endpoints installed before the path unit carry a live sudoers rule. A
    # reinstall must remove it rather than leave both paths open.
    assert script.count("rm -f /etc/sudoers.d/borg-ui-agent-upgrade") == 2


def test_agent_installer_removes_the_upgrade_artifacts_when_declined(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    # A reinstall with --no-remote-upgrade on an endpoint that has the helper
    # must take it away, not leave a live escalation behind.
    removal = script.split("remove_upgrade_artifacts() {", 1)[1].split("\n}", 1)[0]
    assert "systemctl disable --now borg-ui-agent-upgrade.path" in removal
    for path in (
        "UPGRADE_PATH_UNIT",
        "UPGRADE_UNIT",
        "UPGRADE_HELPER",
        "UPGRADE_CONF",
        "UPGRADE_TRIGGER",
    ):
        assert f'"${{{path}}}"' in removal
    assert "NO_REMOTE_UPGRADE_MARKER" in script
