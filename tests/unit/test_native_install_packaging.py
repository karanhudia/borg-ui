"""Guards for the native (non-Docker) install path.

The native installer is shell that only ever runs on a fresh Debian or Ubuntu
host, so nothing in the normal test suite exercises it. These guards cover the
seams where it can silently drift away from the rest of the repository:

* the Borg and rclone pins it installs must keep coming from the same source of
  truth the Docker image builds from, or a native host would run a different
  Borg than the container;
* the systemd unit is a template, so every placeholder in it must actually be
  substituted by the installer;
* the paths the unit and the installer agree on must match the ones the
  application reads at runtime.
"""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "scripts" / "install.sh"
TARBALL_BUILDER = REPO_ROOT / "scripts" / "build-native-tarball.sh"
UNIT = REPO_ROOT / "packaging" / "native" / "borg-ui.service"
START = REPO_ROOT / "packaging" / "native" / "start.sh"
RUNTIME_BASE_ENV = REPO_ROOT / "docker" / "runtime-base.env"
RUNTIME_BASE_DOCKERFILE = REPO_ROOT / "Dockerfile.runtime-base"

SHELL_SCRIPTS = (INSTALLER, TARBALL_BUILDER, START)

# Written into the tarball by the builder and sourced by the installer.
VERSIONS_ENV = "packaging/native/versions.env"


def _emitted_pins() -> set[str]:
    """The keys build-native-tarball.sh writes into versions.env."""
    return set(re.findall(r'echo "([A-Z0-9_]+)=', TARBALL_BUILDER.read_text()))


def test_shell_scripts_are_executable_and_parse():
    for script in SHELL_SCRIPTS:
        assert script.stat().st_mode & 0o111, f"{script.name} is not executable"
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_installer_pins_come_from_the_runtime_base_sources():
    emitted = _emitted_pins()
    assert emitted, "build-native-tarball.sh emits no pins into versions.env"

    env_keys = {
        line.split("=", 1)[0]
        for line in RUNTIME_BASE_ENV.read_text().splitlines()
        if "=" in line and not line.startswith("#")
    }
    dockerfile_args = set(
        re.findall(r"^ARG ([A-Z0-9_]+)=", RUNTIME_BASE_DOCKERFILE.read_text(), re.M)
    )

    unsourced = emitted - env_keys - dockerfile_args
    assert not unsourced, (
        "build-native-tarball.sh invents pins that exist in neither "
        f"docker/runtime-base.env nor Dockerfile.runtime-base: {sorted(unsourced)}"
    )


def test_installer_only_uses_pins_the_tarball_provides():
    """A pin the installer reads but the builder never writes is empty at run
    time, which would install an unchecksummed or wrong-versioned binary."""
    installer = INSTALLER.read_text()
    assert VERSIONS_ENV in installer, (
        f"install.sh no longer sources {VERSIONS_ENV}; the pins would be unset"
    )

    emitted = _emitted_pins()
    used = set(
        re.findall(
            r"\$\{((?:BORG1|BORG2|BORGSTORE|RCLONE)_(?:VERSION|SHA256_[A-Z0-9]+))\}",
            installer,
        )
    )
    assert used, "install.sh reads no pinned versions at all"

    missing = used - emitted
    assert not missing, (
        f"install.sh reads pins the release tarball does not carry: {sorted(missing)}"
    )


def test_every_unit_placeholder_is_substituted_by_the_installer():
    placeholders = set(re.findall(r"@([A-Z_]+)@", UNIT.read_text()))
    assert placeholders, "the systemd unit has no placeholders left to substitute"

    installer = INSTALLER.read_text()
    unsubstituted = {name for name in placeholders if f"s|@{name}@|" not in installer}
    assert not unsubstituted, (
        "the systemd unit has placeholders install.sh never replaces, so the "
        f"installed unit would be invalid: {sorted(unsubstituted)}"
    )


def test_unit_starts_the_script_that_exists():
    exec_start = re.search(r"^ExecStart=(.+)$", UNIT.read_text(), re.M)
    assert exec_start, "the systemd unit has no ExecStart"
    # @PREFIX@/current is the unpacked release, so the tail is a repo path.
    relative = exec_start.group(1).split("/current/", 1)[1]
    assert (REPO_ROOT / relative).is_file(), (
        f"ExecStart points at {relative}, which is not in the repository"
    )


def test_native_install_serves_the_agent_wheelhouse_from_the_default_path():
    """agent_installer.py falls back to a hard-coded directory when
    AGENT_PACKAGE_DIR is unset. The installer does not set that variable, so the
    symlink it creates has to land on exactly that path or enrolling a node
    would 404."""
    from app.api.agent_installer import DEFAULT_AGENT_PACKAGE_DIR

    installer = INSTALLER.read_text()
    assert (
        f'ln -sfn "${{RELEASE_DIR}}/agent-dist" "${{PREFIX}}/agent-dist"' in installer
    )
    prefix = re.search(r'^PREFIX="([^"]+)"', installer, re.M)
    assert prefix, "install.sh no longer defines PREFIX"
    assert f"{prefix.group(1)}/agent-dist" == DEFAULT_AGENT_PACKAGE_DIR
