from pathlib import Path


def test_borg2_venv_installs_pyfuse3():
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile.runtime-base"
    content = dockerfile.read_text()

    assert "/opt/borg2-venv/bin/pip install --no-cache-dir pyfuse3" in content
    assert "ln -sf /opt/borg2-venv/bin/borg /usr/local/bin/borg2" in content


def test_borg2_venv_installs_all_backend_dependencies():
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile.runtime-base"
    content = dockerfile.read_text()

    # borgstore version is parameterized as a build ARG, consistent with the
    # borg1/borg2 pins, so CI can override it without editing the install line.
    assert '"borgstore[rclone,sftp,rest,s3]==${BORGSTORE_VERSION}"' in content
    assert "ARG BORGSTORE_VERSION=0.4.1" in content


def test_runtime_base_env_pins_borgstore_version():
    runtime_env = (
        Path(__file__).resolve().parents[2] / "docker" / "runtime-base.env"
    ).read_text()

    assert "BORGSTORE_VERSION=0.4.1" in runtime_env


def test_runtime_base_installs_rclone():
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile.runtime-base"
    content = dockerfile.read_text()

    assert "rclone" in content


def test_runtime_base_installs_btrfs_snapshot_tooling():
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile.runtime-base"
    content = dockerfile.read_text()

    assert "btrfs-progs" in content


def test_runtime_base_ci_smoke_checks_rclone_and_rest_backend_dependency():
    workflow = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "docker-runtime-base.yml"
    )
    content = workflow.read_text()

    assert "/opt/borg2-venv/bin/python" in content
    assert "import requests" in content
    assert "borgstore rclone/rest dependencies ok" in content


def test_runtime_base_ci_smoke_checks_sftp_backend_dependency():
    workflow = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "docker-runtime-base.yml"
    )
    content = workflow.read_text()

    assert "import paramiko" in content
    assert "borgstore sftp dependencies ok" in content


def test_runtime_base_ci_smoke_checks_s3_backend_dependency():
    workflow = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "docker-runtime-base.yml"
    )
    content = workflow.read_text()

    assert "import boto3" in content
    assert "borgstore s3 dependencies ok" in content


def test_runtime_base_ci_smoke_checks_btrfs_tooling():
    workflow = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "docker-runtime-base.yml"
    )
    content = workflow.read_text()

    assert "btrfs --version" in content


def test_app_dockerfile_uses_rclone_runtime_base_tag():
    repo_root = Path(__file__).resolve().parents[2]
    dockerfile = (repo_root / "Dockerfile").read_text()
    runtime_env = (repo_root / "docker" / "runtime-base.env").read_text()

    expected_tag = "runtime-borg1-1.4.4-borg2-2.0.0b21-r5"

    assert f"BORG_RUNTIME_BASE_TAG={expected_tag}" in runtime_env
    assert (
        f"ARG BASE_IMAGE=docker.io/ainullcode/borg-ui-runtime-base:{expected_tag}"
        in dockerfile
    )
