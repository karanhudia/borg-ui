from fastapi.testclient import TestClient


def test_agent_installer_script_is_public_and_token_free(test_client: TestClient):
    response = test_client.get("/agent/install.sh")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/x-shellscript")
    assert "borg-ui-agent register" in response.text
    assert "systemctl enable --now borg-ui-agent" in response.text
    assert "service-check" in response.text
    assert "borgui_enroll_" not in response.text
