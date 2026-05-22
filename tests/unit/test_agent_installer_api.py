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


def test_agent_installer_script_supports_borg_install_modes(test_client: TestClient):
    response = test_client.get("/agent/install.sh")

    assert "--borg-version 1" in response.text
    assert "--borg-version 2" in response.text
    assert "--borg-version both" in response.text
    assert "--skip-borg-install" in response.text
    assert 'BORG_VERSION="1"' in response.text
    assert 'verify_borg_major "borg" "1"' in response.text
    assert 'verify_borg_major "borg2" "2"' in response.text


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
