import subprocess

from fastapi.testclient import TestClient


def test_uninstaller_is_served_as_a_shell_script(test_client: TestClient):
    response = test_client.get("/agent/uninstall.sh")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/x-shellscript")
    assert response.text.startswith("#!/usr/bin/env bash\n")


def test_uninstaller_is_identical_for_every_caller(test_client: TestClient):
    """Pins the "static, no per-agent data" property in spec section 8, which is
    what makes serving this unauthenticated acceptable: the script carries no
    credential, no pins and nothing that identifies one endpoint from another."""
    first = test_client.get("/agent/uninstall.sh?agent_id=agt_one").text
    second = test_client.get("/agent/uninstall.sh?agent_id=agt_two").text
    bare = test_client.get("/agent/uninstall.sh").text

    assert first == second == bare


def test_uninstaller_is_valid_bash(test_client: TestClient):
    script = test_client.get("/agent/uninstall.sh").text

    result = subprocess.run(
        ["bash", "-n"], input=script, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr


def test_uninstaller_help_exits_zero_without_touching_anything(
    test_client: TestClient,
):
    """--help must not reach a removal. A script that piped into sudo bash and
    started deleting before printing its usage would be the worst possible
    way to learn the flags."""
    script = test_client.get("/agent/uninstall.sh").text

    result = subprocess.run(
        ["bash", "-s", "--", "--help"],
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--keep-borg" in result.stdout
    assert "--keep-user" in result.stdout
    assert "--keep-config" in result.stdout


def test_uninstaller_rejects_an_unknown_flag(test_client: TestClient):
    script = test_client.get("/agent/uninstall.sh").text

    result = subprocess.run(
        ["bash", "-s", "--", "--purge-everything"],
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--purge-everything" in result.stderr
