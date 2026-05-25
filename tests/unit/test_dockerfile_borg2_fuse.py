from pathlib import Path


def test_borg2_venv_installs_pyfuse3():
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile.runtime-base"
    content = dockerfile.read_text()

    assert "/opt/borg2-venv/bin/pip install --no-cache-dir pyfuse3" in content
    assert "ln -sf /opt/borg2-venv/bin/borg /usr/local/bin/borg2" in content


def test_runtime_base_installs_rclone():
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile.runtime-base"
    content = dockerfile.read_text()

    assert "rclone" in content


def test_app_dockerfile_uses_rclone_runtime_base_tag():
    repo_root = Path(__file__).resolve().parents[2]
    dockerfile = (repo_root / "Dockerfile").read_text()
    runtime_env = (repo_root / "docker" / "runtime-base.env").read_text()

    expected_tag = "runtime-borg1-1.4.4-borg2-2.0.0b21-r2"

    assert f"BORG_RUNTIME_BASE_TAG={expected_tag}" in runtime_env
    assert (
        f"ARG BASE_IMAGE=docker.io/ainullcode/borg-ui-runtime-base:{expected_tag}"
        in dockerfile
    )
