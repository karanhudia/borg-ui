import re
import subprocess
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
    # blake3 is not a backend but Borg 2.0.0b23's id-hash dependency.
    assert '"borgstore[rclone,sftp,rest,s3,blake3]==${BORGSTORE_VERSION}"' in content
    assert re.search(r"^ARG BORGSTORE_VERSION=\S+", content, re.M)


def test_runtime_base_env_agrees_with_the_dockerfile_borgstore_version():
    """borgstore is single-sourced in runtime-base.env, like rclone, and the ARG
    default must state the same version or a local build (no build-arg) resolves
    a different one than CI. The version itself is not asserted: Borg 2 constrains
    it (2.0.0b22 requires ~=0.5.5), so the pin moves with the Borg 2 pin."""
    repo_root = Path(__file__).resolve().parents[2]
    dockerfile = (repo_root / "Dockerfile.runtime-base").read_text()
    env = _runtime_base_env(repo_root)

    arg = re.search(r"^ARG BORGSTORE_VERSION=(\S+)", dockerfile, re.M).group(1)
    assert env["BORGSTORE_VERSION"] == arg, (
        f"runtime-base.env pins borgstore {env['BORGSTORE_VERSION']}, "
        f"Dockerfile.runtime-base builds {arg}"
    )


def test_runtime_base_installs_rclone_from_official_static_binary():
    """rclone must come from the official static release (downloads.rclone.org),
    checksum-verified — not the distro package, whose years-behind "-DEV" build
    breaks OneDrive cloud-mirror sync (issue #798)."""
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile.runtime-base"
    content = dockerfile.read_text()

    assert "downloads.rclone.org" in content
    assert "sha256sum -c" in content
    assert re.search(r"^ARG RCLONE_VERSION=\S+", content, re.M)
    # The binary is delivered from the builder stage, not apt.
    assert "COPY --from=builder /out/rclone" in content
    assert not re.search(r"^\s+rclone \\", content, re.M), (
        "rclone must not be installed via the apt package list"
    )


def test_runtime_base_env_agrees_with_the_dockerfile_rclone_version():
    """rclone is single-sourced in runtime-base.env and passed to the Dockerfile
    as a build ARG; the ARG default must state the same version so a local build
    (no build-arg) matches CI."""
    repo_root = Path(__file__).resolve().parents[2]
    dockerfile = (repo_root / "Dockerfile.runtime-base").read_text()
    env = _runtime_base_env(repo_root)

    arg = re.search(r"^ARG RCLONE_VERSION=(\S+)", dockerfile, re.M).group(1)
    assert env["RCLONE_VERSION"] == arg, (
        f"runtime-base.env pins rclone {env['RCLONE_VERSION']}, "
        f"Dockerfile.runtime-base builds {arg}"
    )


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


def test_runtime_base_ci_smoke_checks_rclone_binary():
    """The smoke test must exercise the rclone binary itself, so a broken or
    missing static-binary install fails CI before the image is published."""
    workflow = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "docker-runtime-base.yml"
    )
    content = workflow.read_text()

    assert "rclone version" in content


def test_runtime_base_ci_smoke_checks_btrfs_tooling():
    workflow = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "docker-runtime-base.yml"
    )
    content = workflow.read_text()

    assert "btrfs --version" in content


def _runtime_base_env(repo_root):
    text = (repo_root / "docker" / "runtime-base.env").read_text()
    return dict(re.findall(r"^(\w+)=(\S+)", text, re.M))


def _expected_runtime_tag(env):
    return (
        f"runtime-borg1-{env['BORG1_VERSION']}"
        f"-borg2-{env['BORG2_VERSION']}"
        f"-r{env['RUNTIME_BASE_REVISION']}"
    )


def test_the_tag_script_produces_the_computed_tag():
    """`docker/runtime-base-tag.sh` is what the build scripts and workflows call, so
    exercise the script itself, not just the formula re-derived in Python -- a drift
    in the script would otherwise publish a tag no test catches."""
    repo_root = Path(__file__).resolve().parents[2]
    expected_tag = _expected_runtime_tag(_runtime_base_env(repo_root))

    result = subprocess.run(
        ["bash", str(repo_root / "docker" / "runtime-base-tag.sh")],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == expected_tag


def test_app_dockerfile_base_image_uses_the_computed_runtime_tag():
    """The app image's BASE_IMAGE default must name the runtime-base tag computed
    from the versions file. A forgotten re-tag would pull a base that was never
    built."""
    repo_root = Path(__file__).resolve().parents[2]
    dockerfile = (repo_root / "Dockerfile").read_text()
    expected_tag = _expected_runtime_tag(_runtime_base_env(repo_root))

    assert (
        f"ARG BASE_IMAGE=docker.io/ainullcode/borg-ui-runtime-base:{expected_tag}"
        in dockerfile
    ), f"BASE_IMAGE default does not name {expected_tag}"


def test_runtime_base_env_agrees_with_the_dockerfile_args():
    """The tag is computed from runtime-base.env, so it names the Borg versions by
    construction; what still has to hold is that the env file and the ARGs the
    runtime base is built with state the same versions."""
    repo_root = Path(__file__).resolve().parents[2]
    dockerfile = (repo_root / "Dockerfile.runtime-base").read_text()
    env = _runtime_base_env(repo_root)

    for major in ("1", "2"):
        arg = re.search(rf"^ARG BORG{major}_VERSION=(\S+)", dockerfile, re.M).group(1)
        assert env[f"BORG{major}_VERSION"] == arg, (
            f"runtime-base.env pins Borg {major} {env[f'BORG{major}_VERSION']}, "
            f"Dockerfile.runtime-base builds {arg}"
        )


def test_python_version_is_single_sourced():
    """runtime-base.env states the Python version once; both Dockerfiles take it
    as ARG PYTHON_VERSION and interpolate it into their FROM lines and COPY paths,
    so the 3.10-vs-3.12 split that made this image uncopyable cannot creep back."""
    repo_root = Path(__file__).resolve().parents[2]
    truth = _runtime_base_env(repo_root)["PYTHON_VERSION"]

    for name in ("Dockerfile", "Dockerfile.runtime-base"):
        text = (repo_root / name).read_text()
        assert not re.search(r"python:3\.\d+|/python3\.\d+/", text), (
            f"{name} hardcodes a Python version — use ${{PYTHON_VERSION}}"
        )
        arg = re.search(r"^ARG PYTHON_VERSION=(\S+)", text, re.M)
        assert arg and arg.group(1) == truth, (
            f"{name} ARG PYTHON_VERSION default != runtime-base.env ({truth})"
        )
