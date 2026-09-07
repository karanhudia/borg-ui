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
    # The installer's own header documents the command too, and got missed the
    # first time precisely because this guard did not look at it.
    sources = (
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "installation.md",
        INSTALLER,
    )
    for doc in sources:
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


def test_the_unit_resolves_borg_from_the_installed_prefix_first():
    """The app runs `borg`, `borg2` and `rclone` by name.

    A pre-existing /usr/local/bin/borg is left in place on purpose, and
    systemd's default PATH would let it decide which Borg the service runs,
    which is not the one this release was built against.
    """
    path_line = re.search(r"^Environment=PATH=(.+)$", UNIT.read_text(), re.M)
    assert path_line, "the unit sets no PATH, so the service inherits systemd's default"

    entries = path_line.group(1).split(":")
    assert entries[0] == "@PREFIX@/bin", (
        f"the installed binaries must come first on PATH, got {entries[0]}"
    )
    for required in ("/usr/local/bin", "/usr/bin", "/bin"):
        assert required in entries, f"{required} dropped from the service PATH"


def test_a_failed_checksum_stops_the_install():
    """Verification only helps if it gates what follows.

    The verify and the run were separate lines in every documented block, so a
    pasted block ran `sudo bash install.sh` even after the checksum failed,
    which is the whole point of publishing the checksum.
    """
    offenders = []
    sources = (
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "installation.md",
        INSTALLER,
        REPO_ROOT / ".github" / "workflows" / "release.yml",
    )
    for doc in sources:
        lines = doc.read_text().splitlines()
        for number, line in enumerate(lines, start=1):
            if "sha256sum -c -" not in line or "install.sh.sha256" not in line:
                continue
            if not line.rstrip().endswith(("\\", '\\"')):
                offenders.append(f"{doc.name}:{number}: {line.strip()}")
                continue
            following = lines[number] if number < len(lines) else ""
            if "&&" not in following:
                offenders.append(f"{doc.name}:{number + 1}: {following.strip()}")

    assert not offenders, (
        "verifying install.sh must gate running it; chain the commands with "
        "&& so a bad checksum stops the install:\n" + "\n".join(offenders)
    )


def test_every_path_that_cannot_provide_a_borg_clears_its_forwarder():
    """@PREFIX@/bin is first on the service PATH, so a leftover forwarder there
    keeps answering for a Borg this install does not have. Every branch that
    ends without one has to take it away."""
    installer = INSTALLER.read_text()
    assert "remove_forwarder() {" in installer, "remove_forwarder is gone"

    borg2 = re.search(r"^install_borg2\(\) \{.*?^\}", installer, re.M | re.S)
    assert borg2, "install_borg2 is no longer a top-level function"
    body = borg2.group(0)

    # Each early return in install_borg2 is a path that provides no Borg 2,
    # apart from the one that has just written the forwarder.
    returns = body.count("return")
    cleanups = body.count("remove_forwarder borg2")
    assert cleanups >= returns - 1, (
        f"install_borg2 has {returns} exits but clears the forwarder on only "
        f"{cleanups} of them"
    )

    borg1 = re.search(r"^install_borg1\(\) \{.*?^\}", installer, re.M | re.S)
    assert borg1, "install_borg1 is no longer a top-level function"
    assert "write_forwarder borg /usr/bin/borg" in borg1.group(0), (
        "the distribution-package fallback must own the forwarder too, or a "
        "stale one from an earlier install shadows it"
    )


def test_an_option_without_its_value_is_a_usage_error():
    """Argument parsing runs before anything privileged, so it can be executed.

    A trailing `--version` used to read `$2` under `set -u` and die with
    "unbound variable", which tells the operator nothing about what they got
    wrong.
    """
    for option in ("--version", "--port", "--data-dir", "--service-user"):
        result = subprocess.run(
            ["bash", str(INSTALLER), option], capture_output=True, text=True
        )
        assert result.returncode == 2, (
            f"{option} without a value exited {result.returncode}, not a usage error"
        )
        assert f"{option} needs a value" in result.stderr, result.stderr
        assert "unbound variable" not in result.stderr, result.stderr


def test_help_and_unknown_options_do_not_start_an_install():
    help_result = subprocess.run(
        ["bash", str(INSTALLER), "--help"], capture_output=True, text=True
    )
    assert help_result.returncode == 0
    assert "Usage: install.sh" in help_result.stdout

    unknown = subprocess.run(
        ["bash", str(INSTALLER), "--nope"], capture_output=True, text=True
    )
    assert unknown.returncode == 2
    assert "Unknown option: --nope" in unknown.stderr


def test_the_release_workflow_expands_nothing_ref_derived_into_a_shell_body():
    """A tag name is attacker-controlled input to this job, and only the tag
    being released is validated, not the previous one picked off the tag list.
    Expansions belong in `env:`, where they cannot be read as shell source."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text()

    offenders = []
    in_run_body = False
    for number, line in enumerate(workflow.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("run: |"):
            in_run_body = True
            continue
        if in_run_body and stripped.startswith("- name:"):
            in_run_body = False
        if in_run_body and "${{" in line:
            offenders.append(f"line {number}: {stripped}")

    assert not offenders, (
        "pass these through `env:` and reference them as shell variables:\n"
        + "\n".join(offenders)
    )


def test_a_changed_service_user_takes_the_existing_data_with_it():
    """`install -d` owns directory entries, not what is already inside them.

    Switching --service-user would otherwise leave the database, the secret key
    and every deployed SSH and Borg key owned by the previous user, and the new
    service cannot open them. Rollback does not cover it either: it moves the
    `current` symlink while the unit keeps the new `User=`.
    """
    installer = INSTALLER.read_text()
    assert 'PREVIOUS_SERVICE_USER="${persisted}"' in installer, (
        "the installed unit's User= is no longer captured, so a change in it "
        "cannot be detected"
    )

    body = re.search(r"^create_directories\(\) \{.*?^\}", installer, re.M | re.S)
    assert body, "create_directories is no longer a top-level function"
    assert 'chown -R "${SERVICE_USER}:${group}" "${DATA_DIR}"' in body.group(0), (
        "a service-user change must re-own the data directory recursively"
    )


def test_the_unverified_shortcut_says_so_where_it_is_shown():
    """It sits next to the verified commands, so the label has to travel with
    the command itself, not only in prose someone may skip."""
    docs = (REPO_ROOT / "docs" / "installation.md").read_text().splitlines()

    piped = [
        number
        for number, line in enumerate(docs)
        if "install.sh | sudo bash" in line and line.strip().startswith("curl")
    ]
    assert piped, "the unverified one-liner is gone; drop this guard with it"

    for number in piped:
        window = "\n".join(docs[max(0, number - 6) : number + 1]).lower()
        assert "unverified" in window, (
            f"docs/installation.md:{number + 1} pipes the installer into a root "
            "shell without being labelled unverified nearby"
        )


def test_conflicting_source_options_are_a_usage_error():
    """--tarball carries its own version, so pairing it with --version is
    ambiguous. Checked during parsing, so it is reachable without root."""
    result = subprocess.run(
        ["bash", str(INSTALLER), "--tarball", "/nonexistent", "--version", "1.2.3"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, result.stderr
    assert "mutually exclusive" in result.stderr


def test_the_install_matrix_harness_covers_the_transitions_review_keeps_finding():
    """Most findings on this installer have been state left inconsistent by a
    second run, a run with different flags, or a run over an interrupted one.
    Those are only reachable by running it, so the harness has to keep covering
    them even as cases get added.
    """
    harness = REPO_ROOT / "scripts" / "test-native-install.sh"
    assert harness.is_file(), "the install matrix harness is gone"
    assert harness.stat().st_mode & 0o111, "the harness is not executable"

    text = harness.read_text()
    for case in (
        "fresh",
        "rerun",
        "flags",
        "nostart",
        "skipborg2",
        "partial",
        "serviceuser",
    ):
        assert f"run_case {case}" in text, f"the {case} case is no longer covered"


def _native_env_assignments() -> set[str]:
    """Keys the native install actually puts in the environment.

    Substring matching passed on a key that appeared only in a comment, which
    is how a Docker ENV regression could satisfy the parity guard while the
    native behaviour differed. These are assignments: `Environment=` in the
    unit, `export` in the launcher, and the env file the installer writes.
    """
    keys: set[str] = set()

    keys |= set(
        re.findall(r"^Environment=([A-Za-z_][A-Za-z0-9_]*)=", UNIT.read_text(), re.M)
    )
    keys |= set(
        re.findall(r"^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=", START.read_text(), re.M)
    )

    installer = INSTALLER.read_text()
    env_file = re.search(
        r'cat >"\$\{ENV_FILE\}" <<ENV\n(.*?)^ENV$', installer, re.M | re.S
    )
    assert env_file, "install.sh no longer writes the env file as an ENV heredoc"
    keys |= set(re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)=", env_file.group(1), re.M))
    return keys


def test_the_native_install_sets_what_the_image_sets():
    """Parity guard between the two ways to run Borg UI.

    The image's ENV list is the working configuration; anything it sets that
    the native path does not is a difference in behaviour between them. This
    caught OPENSSL_armcap=0, whose absence made the app die with SIGILL on
    ARM64 at first boot, long after every structural check had passed.
    """
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    production = dockerfile[dockerfile.index("AS production") :]
    keys = set(re.findall(r"^ENV ([A-Za-z_][A-Za-z0-9_]*)=", production, re.M))
    assert keys, "no ENV lines found in the Dockerfile's production stage"

    # Set from the VERSION file the tarball ships; app/config.py prefers that
    # over the environment, so the native path needs no equivalent.
    keys.discard("APP_VERSION")

    missing = sorted(keys - _native_env_assignments())
    assert not missing, (
        "the image sets these but the native install does not, so the two "
        f"behave differently: {missing}"
    )
