import subprocess

from fastapi.testclient import TestClient


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
    assert 'verify_borg_major "borg" "1"' in response.text
    assert 'verify_borg_major "borg2" "2"' in response.text


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


def test_agent_installer_script_allows_borg2_prereleases(test_client: TestClient):
    response = test_client.get("/agent/install.sh")

    assert (
        '"${BORG2_VENV}/bin/pip" install --pre "borgbackup>=2.0.0b1,<3"'
        in response.text
    )
    assert '"borgbackup>=2,<3"' not in response.text


def test_agent_installer_script_reuses_existing_borg2_venv(
    test_client: TestClient,
):
    response = test_client.get("/agent/install.sh")

    assert 'if [[ -x "${BORG2_VENV}/bin/borg" ]]; then' in response.text
    assert "Existing Borg 2 virtualenv detected; linking without reinstalling." in (
        response.text
    )
    assert 'ln -s "${BORG2_VENV}/bin/borg" "${BORG2_LINK}"' in response.text


def test_agent_installer_script_keeps_agent_ref_separate_from_os_release(
    test_client: TestClient,
):
    response = test_client.get("/agent/install.sh")

    assert 'AGENT_REF="main"' in response.text
    assert (
        '"git+https://github.com/karanhudia/borg-ui.git@${AGENT_REF}"' in response.text
    )
    assert "@${VERSION}" not in response.text


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
