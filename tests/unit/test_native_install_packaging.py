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


def _run_load_persisted_settings(
    tmp_path, env_file_text=None, unit_text=None, data_dir_explicit="false"
):
    """Exercise install.sh's load_persisted_settings in isolation.

    Extracting the one function is worth the awkwardness: an upgrade that
    misreads the installed DATA_DIR provisions and chowns the wrong tree, and
    two rounds of review found real bugs in exactly this parsing.
    """
    env_file = tmp_path / "borg-ui.env"
    unit_file = tmp_path / "borg-ui.service"
    if env_file_text is not None:
        env_file.write_text(env_file_text)
    if unit_text is not None:
        unit_file.write_text(unit_text)

    body = re.search(
        r"^load_persisted_settings\(\) \{.*?^\}", INSTALLER.read_text(), re.M | re.S
    )
    assert body, "load_persisted_settings is no longer a top-level function"

    script = "\n".join(
        [
            "set -euo pipefail",
            f'ENV_FILE="{env_file}"',
            f'UNIT_FILE="{unit_file}"',
            'DATA_DIR="/var/lib/borg-ui"',
            'PORT="8081"',
            'SERVICE_USER="root"',
            f'DATA_DIR_EXPLICIT="{data_dir_explicit}"',
            'PORT_EXPLICIT="false"',
            'SERVICE_USER_EXPLICIT="false"',
            "log() { :; }",
            'warn() { echo "WARN:$*"; }',
            'die() { echo "DIE:$*"; exit 1; }',
            body.group(0),
            "load_persisted_settings",
            'echo "RESULT ${DATA_DIR} ${PORT} ${SERVICE_USER}"',
        ]
    )
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True)


def test_upgrade_reads_back_the_settings_the_install_actually_uses(tmp_path):
    result = _run_load_persisted_settings(
        tmp_path,
        # A later assignment wins and one layer of quotes is stripped, the way
        # systemd reads an EnvironmentFile.
        env_file_text='DATA_DIR=/tmp/first\nPORT=9000\nDATA_DIR="/srv/borg-ui"\n',
        # The service user lives in the unit, not the env file.
        unit_text="[Service]\nUser=borgui\n",
    )
    assert result.returncode == 0, result.stderr
    assert "RESULT /srv/borg-ui 9000 borgui" in result.stdout


def test_fresh_install_keeps_the_defaults(tmp_path):
    result = _run_load_persisted_settings(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "RESULT /var/lib/borg-ui 8081 root" in result.stdout


def test_a_flag_contradicting_the_installed_value_warns_and_keeps_it(tmp_path):
    result = _run_load_persisted_settings(
        tmp_path, env_file_text="DATA_DIR=/srv/plain\n", data_dir_explicit="true"
    )
    assert result.returncode == 0, result.stderr
    assert "WARN:" in result.stdout
    assert "RESULT /srv/plain " in result.stdout


def test_syntax_the_parser_cannot_honour_is_refused_not_guessed_at(tmp_path):
    result = _run_load_persisted_settings(
        tmp_path, env_file_text="DATA_DIR=/srv/a\\ b\n"
    )
    assert result.returncode != 0
    assert "DIE:" in result.stdout


def test_no_documented_install_command_fetches_from_a_mutable_branch():
    """The bootstrap script runs as root, so what it is fetched from matters.

    A raw.githubusercontent.com URL on a branch resolves to whatever that
    branch holds at the moment the command is run, and it can move after a
    release. Release assets are fixed per release and have a published
    checksum beside them, so every documented command names one of those.
    """
    offenders = []
    for doc in (REPO_ROOT / "README.md", REPO_ROOT / "docs" / "installation.md"):
        for number, line in enumerate(doc.read_text().splitlines(), start=1):
            if "install.sh" not in line or "curl" not in line:
                continue
            if "raw.githubusercontent.com" in line:
                offenders.append(f"{doc.name}:{number}: {line.strip()}")

    assert not offenders, (
        "install commands must come from a release asset, not a branch:\n"
        + "\n".join(offenders)
    )


def test_the_release_publishes_the_installer_and_its_checksum():
    builder = TARBALL_BUILDER.read_text()
    assert 'cp scripts/install.sh "${OUT_DIR}/install.sh"' in builder
    assert "sha256sum install.sh >install.sh.sha256" in builder

    release = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text()
    for asset in ("dist/install.sh", "dist/install.sh.sha256"):
        assert asset in release, f"{asset} is never attached to the release"


def test_every_step_main_calls_actually_exists():
    """The composition layer, checked by bash itself.

    A review round found `main` still calling a function that a refactor had
    deleted. Under `set -e` that aborts every install at that line, and no
    other test noticed because none of them run `main`. Sourcing the script
    with its invocation stripped and asking bash to resolve each step is the
    cheapest way to keep that from recurring.
    """
    installer = INSTALLER.read_text()
    assert installer.rstrip().endswith('main "$@"'), (
        "install.sh no longer ends with its main invocation; this guard "
        "strips that line to source the script safely"
    )
    definitions = installer.rstrip()[: -len('main "$@"')]

    body = re.search(r"^main\(\) \{\n(.*?)^\}", installer, re.M | re.S)
    assert body, "install.sh has no top-level main()"

    steps = []
    for line in body.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        steps.append(line.split()[0])
    assert len(steps) > 5, f"main() looks unparsed, found only {steps}"

    probe = "\n".join(
        [definitions]
        + [
            f"declare -F {step} >/dev/null || type -t {step} >/dev/null || "
            f'echo "MISSING {step}"'
            for step in steps
        ]
    )
    result = subprocess.run(["bash", "-c", probe], capture_output=True, text=True)
    missing = [
        line.split()[1]
        for line in result.stdout.splitlines()
        if line.startswith("MISSING")
    ]
    assert not missing, f"main() calls steps that do not exist: {missing}"


def test_the_installer_never_brings_the_service_up_with_a_bare_start():
    """`systemctl start` does nothing to an already-active unit.

    The rollback path has to replace a process that may still be running: a
    release can be active yet never answer on its port, which is exactly the
    case `wait_until_serving` catches. `start` there would leave the hung new
    release running behind a symlink pointing at the old one.
    """
    offenders = [
        f"line {number}: {line.strip()}"
        for number, line in enumerate(INSTALLER.read_text().splitlines(), start=1)
        if re.search(r"^\s*(if\s+)?systemctl start borg-ui", line)
    ]
    assert not offenders, (
        "use `systemctl restart borg-ui`; `start` is a no-op on an active unit:\n"
        + "\n".join(offenders)
    )
