"""The installer's macOS flow (#1151).

The served script is one file for both platforms. These tests run its Darwin
branch on any host: the platform is overridden, and everything that would
touch the machine (uname, sw_vers, curl, launchctl, the Python runtime and
Borg it downloads, the agent it installs) is a stub under a temporary home.
"""

from __future__ import annotations

import hashlib
import io
import os
import plistlib
import re
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.borg_ui_agent.self_upgrade import check_self_upgrade

PYTHON_STUB = """#!/usr/bin/env bash
# A stand-in for the relocatable CPython: answers the version check, and
# "creates" a virtualenv whose pip and agent are stubs too.
case "${1:-}" in
  -V) echo "Python 3.12.14" ;;
  -c) exit 0 ;;
  -m)
    [[ "${2:-}" == "venv" ]] || exit 1
    shift 2
    [[ "${1:-}" == "--clear" ]] && shift
    venv="$1"
    mkdir -p "${venv}/bin"
    printf '%s\\n' "${venv}" >"${venv}/created-at"
    printf '#!/usr/bin/env bash\\n[[ -z "${STUB_PIP_FAIL:-}" ]]\\n' >"${venv}/bin/pip"
    cat >"${venv}/bin/borg-ui-agent" <<'AGENT'
#!/usr/bin/env bash
config=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) config="$2"; shift 2 ;;
    register) shift; break ;;
    *) shift ;;
  esac
done
server=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --server) server="$2"; shift 2 ;;
    *) shift ;;
  esac
done
if [[ -n "${config}" ]]; then
  printf 'server_url = "%s"\\nagent_id = "agent-1"\\nagent_token = "t"\\n' "${server}" >"${config}"
  chmod 0600 "${config}"
fi
AGENT
    chmod 0755 "${venv}/bin/pip" "${venv}/bin/borg-ui-agent"
    ;;
esac
"""

BORG_STUB = "#!/usr/bin/env bash\necho 'borg 1.4.5'\n"

# Stubs for what the flow would run on a real Mac. curl copies the fixture
# whose name ends the URL; launchctl records its calls and keeps track of
# which jobs are loaded, so a reinstall can be told from an install.
STUBS = {
    "uname": '#!/usr/bin/env bash\ncase "$1" in -s) echo Darwin ;; -m) echo arm64 ;; esac\n',
    "sw_vers": "#!/usr/bin/env bash\necho 15.6\n",
    "curl": (
        "#!/usr/bin/env bash\n"
        'out=""; url=""\n'
        'while [[ $# -gt 0 ]]; do case "$1" in -o) out="$2"; shift 2 ;; http*) url="$1"; shift ;; *) shift ;; esac; done\n'
        'cp "${STUB_FIXTURES}/${url##*/}" "${out}"\n'
    ),
    "launchctl": (
        "#!/usr/bin/env bash\n"
        'echo "$*" >>"${STUB_LOG}"\n'
        'case "$1" in\n'
        # A bare domain is the login session, there unless a test takes it away.
        '  print) if [[ "$2" != */*/* ]]; then [[ -z "${STUB_NO_LOGIN_SESSION:-}" ]];\n'
        '    else [[ -e "${STUB_STATE}/${2##*/}" ]]; fi ;;\n'
        "  bootstrap)\n"
        # STUB_BOOTSTRAP_FAILURES is how many bootstraps fail first, the way
        # launchd refuses one that follows a bootout too closely.
        '    failed="${STUB_STATE}/.bootstrap-failures"\n'
        '    count="$(cat "${failed}" 2>/dev/null || echo 0)"\n'
        '    if [[ "${count}" -lt "${STUB_BOOTSTRAP_FAILURES:-0}" ]]; then\n'
        '      echo "$((count + 1))" >"${failed}"\n'
        '      echo "Bootstrap failed: 5: Input/output error" >&2\n'
        "      exit 5\n"
        "    fi\n"
        '    touch "${STUB_STATE}/$(basename "$3" .plist)" ;;\n'
        '  bootout) rm -f "${STUB_STATE}/${2##*/}" ;;\n'
        "esac\n"
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _python_tarball(path: Path) -> None:
    """A python/ tree with one executable, the way the real archive unpacks."""
    with tarfile.open(path, "w:gz") as archive:
        data = PYTHON_STUB.encode("utf-8")
        info = tarfile.TarInfo("python/bin/python3")
        info.size = len(data)
        info.mode = 0o755
        archive.addfile(info, io.BytesIO(data))


def _pin(script: str, name: str, value: str) -> str:
    """Replace one PINNED_* assignment in the served script, table or not."""
    pattern = re.compile(rf'^{name}=".*?"$', re.M | re.S)
    assert pattern.search(script), name
    return pattern.sub(lambda _: f'{name}="{value}"', script, count=1)


@pytest.fixture
def mac(tmp_path: Path, test_client: TestClient) -> dict:
    """A fake Mac: a home, the stubs on PATH, fixtures the stub curl serves,
    and the served installer pinned to those fixtures."""
    home = tmp_path / "home"
    home.mkdir()
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, text in STUBS.items():
        _write_executable(stubs / name, text)
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    _python_tarball(fixtures / "python.tar.gz")
    _write_executable(fixtures / "borg-macos-15-arm64-gh", BORG_STUB)

    script = test_client.get("/agent/install.sh").text
    script = _pin(script, "PINNED_BORG1_VERSION", "1.4.5")
    script = _pin(
        script,
        "PINNED_BORG_BINARIES",
        "1 darwin aarch64 15 "
        f"{_sha256(fixtures / 'borg-macos-15-arm64-gh')} "
        "https://example.invalid/borg-macos-15-arm64-gh",
    )
    script = _pin(script, "PINNED_PYTHON_VERSION", "3.12.14+test")
    script = _pin(
        script,
        "PINNED_PYTHON_RUNTIMES",
        f"darwin aarch64 {_sha256(fixtures / 'python.tar.gz')} "
        "https://example.invalid/python.tar.gz",
    )
    script = _pin(script, "PINNED_AGENT_VERSION", "0.1.12")
    installer = tmp_path / "install.sh"
    installer.write_text(script, encoding="utf-8")

    state = tmp_path / "launchd"
    state.mkdir()
    log = tmp_path / "launchctl.log"
    log.touch()
    return {
        "home": home,
        "root": home / "Library" / "Application Support" / "borg-ui-agent",
        "agents": home / "Library" / "LaunchAgents",
        "installer": installer,
        "log": log,
        "env": {
            "PATH": f"{stubs}:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(home),
            "BORG_UI_AGENT_PLATFORM": "Darwin",
            "STUB_FIXTURES": str(fixtures),
            "STUB_STATE": str(state),
            "STUB_LOG": str(log),
        },
    }


def _run(mac: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(mac["installer"]), *args],
        capture_output=True,
        text=True,
        check=False,
        env=mac["env"],
        # No controlling terminal: a first install's questions must not reach
        # the developer's own terminal.
        start_new_session=True,
    )


ENROL = ("--server", "https://borg.example", "--token", "tok", "--name", "mac")


def test_linux_only_flags_are_refused_before_anything_runs(mac):
    for flag in (("--service-user", "current"), ("--borg-source", "distro")):
        result = _run(mac, *ENROL, *flag)

        assert result.returncode == 2, result.stderr
        assert "Linux only" in result.stderr
    assert not mac["root"].exists()


def test_a_mac_without_a_login_session_is_refused_before_anything_runs(mac):
    """Over ssh with nobody logged in at the Mac there is no gui/<uid> domain
    (launchctl answers 125, "Domain does not support specified action"); the
    jobs could not be loaded, so nothing is installed."""
    env = {**mac["env"], "STUB_NO_LOGIN_SESSION": "1"}

    result = subprocess.run(
        ["bash", str(mac["installer"]), *ENROL],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        start_new_session=True,
    )

    assert result.returncode == 1, result.stderr
    assert "not logged in at this Mac" in result.stderr
    assert "through Screen Sharing" in result.stderr
    assert not mac["root"].exists()
    assert "bootstrap" not in mac["log"].read_text()


def test_root_is_refused_on_macos(test_client: TestClient):
    """EUID cannot be faked from a test; the refusal is asserted in the text."""
    script = test_client.get("/agent/install.sh").text

    assert (
        'if [[ "${EUID}" -eq 0 ]]; then'
        in script.split("configure_darwin_layout\n", 1)[1]
    )
    assert "without sudo" in script


def test_an_install_lays_out_the_user_directory_and_loads_both_jobs(mac):
    result = _run(mac, *ENROL, "--borg-version", "1")

    assert result.returncode == 0, result.stderr + result.stdout
    root = mac["root"]
    assert (root / "python" / "bin" / "python3").exists()
    assert (root / "python" / ".borg-ui-runtime").read_text() == "3.12.14+test\n"
    assert (root / ".venv" / "bin" / "borg-ui-agent").exists()
    # A virtualenv works only at the path it was built at.
    assert (root / ".venv" / "created-at").read_text() == f"{root}/.venv\n"
    assert (root / "borg1" / "1.4.5" / "borg").exists()
    assert (root / "bin" / "borg1").exists()
    assert os.readlink(root / "bin" / "borg") == str(root / "bin" / "borg1")
    assert (root / "config.toml").exists()
    assert oct((root / "config.toml").stat().st_mode & 0o777) == "0o600"
    assert not (root / "upgrade-requested").exists()
    assert os.access(root / "bin" / "borg-ui-agent-upgrade", os.X_OK)
    conf = (root / "upgrade.conf").read_text()
    assert 'SERVER="https://borg.example"' in conf
    assert 'AGENT_ID="agent-1"' in conf
    assert 'server_url = "https://borg.example"' in (root / "config.toml").read_text()
    assert f'AGENT_ROOT="{root}"' in conf

    # No root-owned file and no system path: everything is under the home.
    assert not (mac["home"].parent / "etc").exists()
    assert "Remote upgrade is available on this endpoint." in result.stdout
    assert "Borg UI agent installed and started." in result.stdout


def test_both_borg_majors_get_forwarders_and_nothing_else_is_linked(mac, tmp_path):
    """Borg 2's forwarder already carries the name the agent resolves, so no
    link is made on top of it; rclone is not the installer's to install here."""
    fixtures = tmp_path / "fixtures"
    _write_executable(
        fixtures / "borg2-macos-15-arm64-gh",
        "#!/usr/bin/env bash\necho 'borg 2.0.0b24'\n",
    )
    script = mac["installer"].read_text(encoding="utf-8")
    script = _pin(script, "PINNED_BORG2_VERSION", "2.0.0b24")
    script = _pin(
        script,
        "PINNED_BORG_BINARIES",
        "1 darwin aarch64 15 "
        f"{_sha256(fixtures / 'borg-macos-15-arm64-gh')} "
        "https://example.invalid/borg-macos-15-arm64-gh\n"
        "2 darwin aarch64 15 "
        f"{_sha256(fixtures / 'borg2-macos-15-arm64-gh')} "
        "https://example.invalid/borg2-macos-15-arm64-gh",
    )
    mac["installer"].write_text(script, encoding="utf-8")

    result = _run(mac, *ENROL, "--borg-version", "both", "--no-prompt")

    assert result.returncode == 0, result.stderr + result.stdout
    root = mac["root"]
    assert os.readlink(root / "bin" / "borg") == str(root / "bin" / "borg1")
    assert (root / "bin" / "borg2").is_file() and not (
        root / "bin" / "borg2"
    ).is_symlink()
    assert "leaving it untouched" not in result.stderr
    assert "rclone is not installed" in result.stderr
    assert "could not be installed" not in result.stderr


def test_the_agent_job_resolves_borg_through_the_forwarder_directory(mac):
    _run(mac, *ENROL, "--borg-version", "1")

    with (mac["agents"] / "com.borg-ui.agent.plist").open("rb") as handle:
        job = plistlib.load(handle)

    root = str(mac["root"])
    assert job["Label"] == "com.borg-ui.agent"
    assert job["ProgramArguments"] == [
        f"{root}/.venv/bin/borg-ui-agent",
        "--config",
        f"{root}/config.toml",
        "run",
    ]
    assert job["RunAtLoad"] is True and job["KeepAlive"] is True
    assert job["EnvironmentVariables"]["PATH"].startswith(f"{root}/bin:")
    assert "BORG_PASSPHRASE" not in job["EnvironmentVariables"]
    assert job["StandardOutPath"].startswith(str(mac["home"] / "Library" / "Logs"))


def test_the_upgrade_job_watches_the_trigger_and_the_agent_is_ready_for_it(mac):
    _run(mac, *ENROL, "--borg-version", "1")
    root = mac["root"]
    job_path = mac["agents"] / "com.borg-ui.agent-upgrade.plist"

    with job_path.open("rb") as handle:
        job = plistlib.load(handle)

    assert job["ProgramArguments"] == [f"{root}/bin/borg-ui-agent-upgrade"]
    assert job["KeepAlive"] == {"PathState": {f"{root}/upgrade-requested": True}}
    env = job["EnvironmentVariables"]
    assert env["BORG_UI_UPGRADE_CONF"] == f"{root}/upgrade.conf"
    assert env["BORG_UI_UPGRADE_TRIGGER"] == f"{root}/upgrade-requested"
    assert env["BORG_UI_UPGRADE_ETC"] == str(root)
    assert env["BORG_UI_UPGRADE_JOB"] == "1"

    # The agent's own readiness check accepts what the installer wrote.
    readiness = check_self_upgrade(
        conf_path=root / "upgrade.conf",
        unit_path=job_path,
        path_unit_path=job_path,
        trigger_path=root / "upgrade-requested",
    )
    assert readiness.supported is True, readiness.reason


def test_both_jobs_are_bootstrapped_into_the_user_domain(mac):
    _run(mac, *ENROL, "--borg-version", "1")

    calls = mac["log"].read_text().splitlines()
    uid = os.getuid()
    assert (
        f"bootstrap gui/{uid} {mac['agents']}/com.borg-ui.agent-upgrade.plist" in calls
    )
    assert f"bootstrap gui/{uid} {mac['agents']}/com.borg-ui.agent.plist" in calls
    assert not any(call.startswith("bootout") for call in calls)


def test_a_reinstall_keeps_the_runtime_and_reloads_the_agent_job(mac):
    _run(mac, *ENROL, "--borg-version", "1")
    mac["log"].write_text("")

    result = _run(mac, "--reinstall")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Python 3.12.14+test already present" in result.stdout
    assert "Preserving existing agent registration" in result.stdout
    assert "Borg UI agent reinstalled and restarted." in result.stdout
    calls = mac["log"].read_text().splitlines()
    uid = os.getuid()
    agent = f"gui/{uid}/com.borg-ui.agent"
    assert calls.index(f"bootout {agent}") < calls.index(
        f"bootstrap gui/{uid} {mac['agents']}/com.borg-ui.agent.plist"
    )


def test_a_bootstrap_refused_right_after_the_bootout_is_tried_again(mac):
    """launchd can refuse a bootstrap that follows a bootout too closely and
    accept the same one moments later; the reinstall must not stop there."""
    _run(mac, *ENROL, "--borg-version", "1")
    mac["log"].write_text("")

    result = subprocess.run(
        ["bash", str(mac["installer"]), "--reinstall"],
        capture_output=True,
        text=True,
        check=False,
        env={**mac["env"], "STUB_BOOTSTRAP_FAILURES": "2"},
        start_new_session=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    calls = mac["log"].read_text().splitlines()
    assert sum(call.startswith("bootstrap ") for call in calls) == 4
    assert "Borg UI agent reinstalled and restarted." in result.stdout


def test_a_bootstrap_that_keeps_failing_stops_the_reinstall_with_the_error(mac):
    _run(mac, *ENROL, "--borg-version", "1")

    result = subprocess.run(
        ["bash", str(mac["installer"]), "--reinstall"],
        capture_output=True,
        text=True,
        check=False,
        env={**mac["env"], "STUB_BOOTSTRAP_FAILURES": "99"},
        start_new_session=True,
    )

    assert result.returncode != 0
    assert "Bootstrap failed: 5: Input/output error" in result.stderr


def test_a_reinstall_from_inside_the_upgrade_job_does_not_unload_itself(mac):
    _run(mac, *ENROL, "--borg-version", "1")
    mac["log"].write_text("")

    result = subprocess.run(
        ["bash", str(mac["installer"]), "--reinstall"],
        capture_output=True,
        text=True,
        check=False,
        env={**mac["env"], "BORG_UI_UPGRADE_JOB": "1"},
        start_new_session=True,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    calls = mac["log"].read_text().splitlines()
    uid = os.getuid()
    assert f"bootout gui/{uid}/com.borg-ui.agent-upgrade" not in calls
    assert f"bootout gui/{uid}/com.borg-ui.agent" in calls


def test_a_broken_replacement_runtime_keeps_the_one_in_use(mac, tmp_path):
    """A reinstall that pins a newer Python must not take the working
    interpreter away before the new one has answered."""
    _run(mac, *ENROL, "--borg-version", "1")
    root = mac["root"]
    script = mac["installer"].read_text(encoding="utf-8")
    script = _pin(script, "PINNED_PYTHON_VERSION", "3.13.0+test")
    broken = tmp_path / "fixtures" / "python.tar.gz"
    with tarfile.open(broken, "w:gz") as archive:
        data = b"#!/usr/bin/env bash\nexit 1\n"
        info = tarfile.TarInfo("python/bin/python3")
        info.size = len(data)
        info.mode = 0o755
        archive.addfile(info, io.BytesIO(data))
    script = _pin(
        script,
        "PINNED_PYTHON_RUNTIMES",
        f"darwin aarch64 {_sha256(broken)} https://example.invalid/python.tar.gz",
    )
    mac["installer"].write_text(script, encoding="utf-8")

    result = _run(mac, "--reinstall")

    assert result.returncode == 1
    assert "keeping the current runtime" in result.stderr
    assert (root / "python" / ".borg-ui-runtime").read_text() == "3.12.14+test\n"
    assert (root / ".venv" / "bin" / "borg-ui-agent").exists()
    assert not (root / "python.new").exists()
    assert not (root / ".venv.new").exists()


def test_a_failed_package_install_keeps_the_agent_in_use(mac):
    """pip failing mid-reinstall must not leave the endpoint without an agent."""
    _run(mac, *ENROL, "--borg-version", "1")
    root = mac["root"]
    (root / ".venv" / "marker").write_text("", encoding="utf-8")
    mac["log"].write_text("")

    result = subprocess.run(
        ["bash", str(mac["installer"]), "--reinstall"],
        capture_output=True,
        text=True,
        check=False,
        env={**mac["env"], "STUB_PIP_FAIL": "1"},
        start_new_session=True,
    )

    assert result.returncode == 1
    assert "keeping the current agent" in result.stderr
    assert (root / ".venv" / "marker").exists()
    assert (root / ".venv" / "bin" / "borg-ui-agent").exists()
    assert not (root / ".venv.old").exists()
    assert "bootout" not in mac["log"].read_text()


def test_a_failed_package_install_restores_the_previous_runtime_too(mac):
    """A reinstall that moved to a newer Python and then lost the package
    download must bring back the runtime the kept virtualenv links to."""
    _run(mac, *ENROL, "--borg-version", "1")
    root = mac["root"]
    (root / ".venv" / "marker").write_text("", encoding="utf-8")
    script = mac["installer"].read_text(encoding="utf-8")
    script = _pin(script, "PINNED_PYTHON_VERSION", "3.13.0+test")
    mac["installer"].write_text(script, encoding="utf-8")

    result = subprocess.run(
        ["bash", str(mac["installer"]), "--reinstall"],
        capture_output=True,
        text=True,
        check=False,
        env={**mac["env"], "STUB_PIP_FAIL": "1"},
        start_new_session=True,
    )

    assert result.returncode == 1
    assert "Installed Python 3.13.0+test" in result.stdout
    assert (root / "python" / ".borg-ui-runtime").read_text() == "3.12.14+test\n"
    assert (root / ".venv" / "marker").exists()
    assert not (root / "python.old").exists()
    assert not (root / ".venv.old").exists()


def test_a_replacement_runtime_that_is_too_old_gives_the_agent_back(mac, tmp_path):
    """The version check runs after the runtime swap; failing it must put
    the runtime the kept virtualenv links to back in place."""
    _run(mac, *ENROL, "--borg-version", "1")
    root = mac["root"]
    (root / ".venv" / "marker").write_text("", encoding="utf-8")
    script = mac["installer"].read_text(encoding="utf-8")
    script = _pin(script, "PINNED_PYTHON_VERSION", "3.9.6+test")
    old = tmp_path / "fixtures" / "python.tar.gz"
    with tarfile.open(old, "w:gz") as archive:
        # Runs, but answers the version check the way a 3.9 would.
        data = (
            b"#!/usr/bin/env bash\n"
            b'case "${1:-}" in\n'
            b'  -V) echo "Python 3.9.6" ;;\n'
            b'  -c) [[ "${2:-}" == "import sys" ]] ;;\n'
            b"esac\n"
        )
        info = tarfile.TarInfo("python/bin/python3")
        info.size = len(data)
        info.mode = 0o755
        archive.addfile(info, io.BytesIO(data))
    script = _pin(
        script,
        "PINNED_PYTHON_RUNTIMES",
        f"darwin aarch64 {_sha256(old)} https://example.invalid/python.tar.gz",
    )
    mac["installer"].write_text(script, encoding="utf-8")

    result = _run(mac, "--reinstall")

    assert result.returncode == 1
    assert "needs Python 3.11 or newer" in result.stderr
    assert "Keeping the current agent" in result.stderr
    assert (root / "python" / ".borg-ui-runtime").read_text() == "3.12.14+test\n"
    assert (root / ".venv" / "marker").exists()
    assert not (root / "python.old").exists()
    assert not (root / ".venv.old").exists()


def test_a_runtime_change_leaves_nothing_aside_when_it_succeeds(mac):
    _run(mac, *ENROL, "--borg-version", "1")
    root = mac["root"]
    script = mac["installer"].read_text(encoding="utf-8")
    script = _pin(script, "PINNED_PYTHON_VERSION", "3.13.0+test")
    mac["installer"].write_text(script, encoding="utf-8")

    result = _run(mac, "--reinstall")

    assert result.returncode == 0, result.stderr + result.stdout
    assert (root / "python" / ".borg-ui-runtime").read_text() == "3.13.0+test\n"
    assert (root / ".venv" / "created-at").read_text() == f"{root}/.venv\n"
    assert not (root / "python.old").exists()
    assert not (root / ".venv.old").exists()


def test_a_runtime_checksum_mismatch_installs_nothing(mac):
    script = mac["installer"].read_text(encoding="utf-8")
    script = _pin(
        script,
        "PINNED_PYTHON_RUNTIMES",
        f"darwin aarch64 {'0' * 64} https://example.invalid/python.tar.gz",
    )
    mac["installer"].write_text(script, encoding="utf-8")

    result = _run(mac, *ENROL, "--borg-version", "1")

    assert result.returncode == 1
    assert "Checksum mismatch for Python" in result.stderr
    assert not (mac["root"] / "python").exists()
    assert not (mac["agents"] / "com.borg-ui.agent.plist").exists()


def test_a_mac_below_the_floor_learns_the_macos_it_needs(mac, tmp_path):
    _write_executable(
        tmp_path / "stubs" / "sw_vers", "#!/usr/bin/env bash\necho 14.7\n"
    )

    result = _run(mac, *ENROL, "--borg-version", "1")

    assert result.returncode == 1
    assert (
        "Borg 1.4.5 for aarch64 needs macOS 15 or newer; this machine has macOS 14.7."
        in result.stderr
    )
    assert "--skip-borg-install" in result.stderr
    assert "--borg-source distro" not in result.stderr


def test_the_helper_does_nothing_without_a_request(mac):
    """launchd may start a KeepAlive job speculatively when it is loaded."""
    _run(mac, *ENROL, "--borg-version", "1")

    result = subprocess.run(
        [str(mac["root"] / "bin" / "borg-ui-agent-upgrade")],
        capture_output=True,
        text=True,
        check=False,
        env={
            **mac["env"],
            "BORG_UI_UPGRADE_TRIGGER": str(mac["root"] / "upgrade-requested"),
        },
    )

    assert result.returncode == 0, result.stderr
    assert "No upgrade requested" in result.stdout


def test_the_helper_passes_no_service_user_on_macos(test_client: TestClient):
    script = test_client.get("/agent/install.sh").text
    helper = script.split("<<'UPGRADE_HELPER'", 1)[1].split("\nUPGRADE_HELPER", 1)[0]

    assert "args=(--reinstall)" in helper
    assert 'if [[ "$(uname -s)" != "Darwin" ]]; then' in helper
    assert 'args+=(--service-user "${SERVICE_USER}")' in helper


def test_the_served_template_matches_what_the_installer_renders(mac):
    """agent/install/launchd/com.borg-ui.agent.plist is the manual-install
    copy of the rendered job, with USERNAME where the installer puts the home."""
    _run(mac, *ENROL, "--borg-version", "1")
    template = (
        Path(__file__).resolve().parents[2]
        / "agent"
        / "install"
        / "launchd"
        / "com.borg-ui.agent.plist"
    )
    with template.open("rb") as handle:
        expected = plistlib.load(handle)
    with (mac["agents"] / "com.borg-ui.agent.plist").open("rb") as handle:
        rendered = plistlib.load(handle)

    def normalise(job: dict, home: str) -> dict:
        text = plistlib.dumps(job).decode("utf-8").replace(home, "/Users/alex")
        return plistlib.loads(text.encode("utf-8"))

    assert normalise(rendered, str(mac["home"])) == expected


def test_the_uninstaller_empties_the_user_directory(mac, test_client: TestClient):
    _run(mac, *ENROL, "--borg-version", "1")
    mac["log"].write_text("")
    uninstaller = test_client.get("/agent/uninstall.sh").text

    result = subprocess.run(
        ["bash", "-s", "--", "--keep-config"],
        input=uninstaller,
        capture_output=True,
        text=True,
        check=False,
        env=mac["env"],
    )

    assert result.returncode == 0, result.stderr + result.stdout
    root = mac["root"]
    assert (root / "config.toml").exists()
    assert not (root / ".venv").exists()
    assert not (root / "python").exists()
    assert not (root / "bin").exists()
    assert not (root / "upgrade.conf").exists()
    assert not (mac["agents"] / "com.borg-ui.agent.plist").exists()
    assert not (mac["agents"] / "com.borg-ui.agent-upgrade.plist").exists()
    assert not (mac["home"] / "Library" / "Logs" / "borg-ui-agent").exists()
    calls = mac["log"].read_text().splitlines()
    uid = os.getuid()
    assert f"bootout gui/{uid}/com.borg-ui.agent" in calls
    assert f"bootout gui/{uid}/com.borg-ui.agent-upgrade" in calls
    assert "Borg UI agent removed." in result.stdout


def test_the_uninstaller_keeps_borg_on_request(mac, test_client: TestClient):
    _run(mac, *ENROL, "--borg-version", "1")
    uninstaller = test_client.get("/agent/uninstall.sh").text

    result = subprocess.run(
        ["bash", "-s", "--", "--keep-borg"],
        input=uninstaller,
        capture_output=True,
        text=True,
        check=False,
        env=mac["env"],
    )

    assert result.returncode == 0, result.stderr + result.stdout
    root = mac["root"]
    assert (root / "borg1" / "1.4.5" / "borg").exists()
    assert (root / "bin" / "borg1").exists()
    assert (root / "bin" / "borg").is_symlink()
    assert not (root / "bin" / "borg-ui-agent-upgrade").exists()
    assert not (root / ".venv").exists()
    assert not (root / "config.toml").exists()


def test_the_uninstaller_removes_the_whole_directory_by_default(mac, test_client):
    _run(mac, *ENROL, "--borg-version", "1")
    uninstaller = test_client.get("/agent/uninstall.sh").text

    result = subprocess.run(
        ["bash"],
        input=uninstaller,
        capture_output=True,
        text=True,
        check=False,
        env=mac["env"],
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert not mac["root"].exists()


def test_the_uninstaller_ignores_plain_path_variables_in_the_users_shell(
    mac, test_client
):
    """On macOS the uninstaller runs in the user's own shell, with no sudo to
    reset the environment. A LOG_DIR or AGENT_ROOT exported there for some other
    purpose must not become a path it removes."""
    _run(mac, *ENROL, "--borg-version", "1")
    uninstaller = test_client.get("/agent/uninstall.sh").text
    bystanders = {}
    for name in ("AGENT_ROOT", "CONFIG_DIR", "LOG_DIR", "STATE_DIR"):
        bystander = mac["home"] / "bystanders" / name
        bystander.mkdir(parents=True)
        (bystander / "keep").write_text("")
        bystanders[name] = str(bystander)

    result = subprocess.run(
        ["bash"],
        input=uninstaller,
        capture_output=True,
        text=True,
        check=False,
        env={**mac["env"], **bystanders},
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert not mac["root"].exists()
    for bystander in bystanders.values():
        assert (Path(bystander) / "keep").exists()


# --- the repository the agent reports -----------------------------------------


REPO_FLAGS = (
    "--borg-repo",
    "ssh://u@borg.example:23/./repo",
    "--borg-remote-path",
    "borg-1.4",
)


def test_the_repository_flags_reach_the_agent_job_and_survive_a_reinstall(mac):
    result = _run(mac, *ENROL, "--borg-version", "1", *REPO_FLAGS)

    assert result.returncode == 0, result.stderr + result.stdout
    root = mac["root"]
    env_file = root / "agent.env"
    assert oct(env_file.stat().st_mode & 0o777) == "0o600"
    assert env_file.read_text() == (
        'BORG_REPO="ssh://u@borg.example:23/./repo"\nBORG_REMOTE_PATH="borg-1.4"\n'
    )
    with (mac["agents"] / "com.borg-ui.agent.plist").open("rb") as handle:
        env = plistlib.load(handle)["EnvironmentVariables"]
    assert env["BORG_REPO"] == "ssh://u@borg.example:23/./repo"
    assert env["BORG_REMOTE_PATH"] == "borg-1.4"

    # A reinstall without the flags keeps what was recorded.
    result = _run(mac, "--reinstall")

    assert result.returncode == 0, result.stderr + result.stdout
    with (mac["agents"] / "com.borg-ui.agent.plist").open("rb") as handle:
        env = plistlib.load(handle)["EnvironmentVariables"]
    assert env["BORG_REPO"] == "ssh://u@borg.example:23/./repo"
    assert env["BORG_REMOTE_PATH"] == "borg-1.4"

    # One flag changes that one value and keeps the other.
    result = _run(mac, "--reinstall", "--borg-remote-path", "borg-1.4-rc")

    assert result.returncode == 0, result.stderr + result.stdout
    with (mac["agents"] / "com.borg-ui.agent.plist").open("rb") as handle:
        env = plistlib.load(handle)["EnvironmentVariables"]
    assert env["BORG_REPO"] == "ssh://u@borg.example:23/./repo"
    assert env["BORG_REMOTE_PATH"] == "borg-1.4-rc"
    assert env_file.read_text() == (
        'BORG_REPO="ssh://u@borg.example:23/./repo"\nBORG_REMOTE_PATH="borg-1.4-rc"\n'
    )

    # An empty value given on purpose clears that one value.
    result = _run(mac, "--reinstall", "--borg-remote-path", "")

    assert result.returncode == 0, result.stderr + result.stdout
    with (mac["agents"] / "com.borg-ui.agent.plist").open("rb") as handle:
        env = plistlib.load(handle)["EnvironmentVariables"]
    assert env["BORG_REPO"] == "ssh://u@borg.example:23/./repo"
    assert "BORG_REMOTE_PATH" not in env


def test_keep_config_keeps_what_linux_keeps_and_a_reinstall_picks_it_up(
    mac, test_client
):
    """On Linux --keep-config keeps the whole config directory. On macOS that
    directory is the agent root, so the uninstaller must spare agent.env and the
    user's own scripts.d there, not config.toml alone."""
    _run(mac, *ENROL, "--borg-version", "1", *REPO_FLAGS)
    root = mac["root"]
    (root / "scripts.d").mkdir()
    (root / "scripts.d" / "pre.sh").write_text("#!/bin/sh\n")
    (root / "upgrade-requested").write_text("")
    uninstaller = test_client.get("/agent/uninstall.sh").text

    result = subprocess.run(
        ["bash", "-s", "--", "--keep-config"],
        input=uninstaller,
        capture_output=True,
        text=True,
        check=False,
        env=mac["env"],
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert sorted(entry.name for entry in root.iterdir()) == [
        "agent.env",
        "config.toml",
        "scripts.d",
    ]
    assert (root / "scripts.d" / "pre.sh").read_text() == "#!/bin/sh\n"

    result = _run(mac, "--reinstall")

    assert result.returncode == 0, result.stderr + result.stdout
    with (mac["agents"] / "com.borg-ui.agent.plist").open("rb") as handle:
        env = plistlib.load(handle)["EnvironmentVariables"]
    assert env["BORG_REPO"] == "ssh://u@borg.example:23/./repo"
    assert env["BORG_REMOTE_PATH"] == "borg-1.4"


@pytest.mark.parametrize(
    "value", ['ssh://u@h/./re"po', "ssh://u@h/./re\\po", "ssh://u@h/./repo\nBORG_X=1"]
)
def test_a_repository_value_that_would_change_the_file_is_refused(mac, value):
    """One KEY="value" line each, and a line inside a service definition."""
    result = _run(mac, *ENROL, "--borg-version", "1", "--borg-repo", value)

    assert result.returncode == 2
    assert "must not contain quotes, backslashes or line breaks" in result.stderr
    assert not (mac["root"] / "agent.env").exists()


def test_without_a_repository_nothing_is_recorded(mac):
    result = _run(mac, *ENROL, "--borg-version", "1", "--no-prompt")

    assert result.returncode == 0, result.stderr + result.stdout
    assert not (mac["root"] / "agent.env").exists()
    with (mac["agents"] / "com.borg-ui.agent.plist").open("rb") as handle:
        env = plistlib.load(handle)["EnvironmentVariables"]
    assert set(env) == {"PATH"}


def test_an_ssh_url_is_split_into_login_host_and_port(test_client: TestClient):
    script = test_client.get("/agent/install.sh").text
    function = re.search(r"^ssh_target_of\(\) \{\n.*?^\}\n", script, re.M | re.S).group(
        0
    )
    harness = function + (
        '\nfor url in "$@"; do ssh_target_of "$url"; '
        'echo "${SSH_TARGET_HOST} ${SSH_TARGET_PORT}"; done\n'
    )

    result = subprocess.run(
        [
            "bash",
            "-c",
            harness,
            "_",
            "ssh://u@borg.example:23/./repo",
            "ssh://borg.example/srv/repo",
            "ssh://u@borg.example:2222",
            "rest://borg@store.example/series/repo",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.stdout.splitlines() == [
        "u@borg.example 23",
        "borg.example 22",
        "u@borg.example 2222",
        "borg@store.example 22",
    ]


def test_an_ssh_host_that_reads_as_an_option_is_never_passed_to_ssh(
    test_client: TestClient, tmp_path: Path
):
    """ssh://-oProxyCommand=... would make ssh run a command on this machine;
    such a host is skipped, and every other one follows "--"."""
    script = test_client.get("/agent/install.sh").text
    functions = "\n".join(
        re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", script, re.M | re.S).group(0)
        for name in ("ssh_target_of", "test_ssh_target")
    )
    calls = tmp_path / "calls"
    harness = "\n".join(
        [
            "set -euo pipefail",
            'SERVICE_USER="me"',
            f'as_service_user() {{ printf "%s\\n" "$*" >>"{calls}"; }}',
            functions,
            'for url in "$@"; do test_ssh_target "$url"; done',
        ]
    )

    result = subprocess.run(
        [
            "bash",
            "-c",
            harness,
            "_",
            "ssh://-oProxyCommand=touch${IFS}marker/repo",
            "ssh://u@borg.example:23/./repo",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Not an SSH host" in result.stderr
    assert calls.read_text().splitlines() == [
        "ssh -o ConnectTimeout=15 -p 23 -- u@borg.example exit"
    ]


def _run_on_a_terminal(mac: dict, answers: list[str], *args: str) -> tuple[int, str]:
    """Run the installer with a pseudo-terminal, answering its prompts.

    A piped install reads its answers from /dev/tty, so the test gives it one:
    every prompt ends in a space and no newline, which is what the reader
    waits for before it types the next answer.
    """
    import pty
    import select
    import time

    master, slave = pty.openpty()
    process = subprocess.Popen(
        ["bash", str(mac["installer"]), *args],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=mac["env"],
        start_new_session=True,
        preexec_fn=lambda: __import__("fcntl").ioctl(
            slave, __import__("termios").TIOCSCTTY, 0
        ),
    )
    os.close(slave)
    output = b""
    pending = list(answers)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ready, _, _ = select.select([master], [], [], 1)
        if ready:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
            if pending and (output.endswith(b": ") or output.endswith(b"] ")):
                os.write(master, (pending.pop(0) + "\n").encode())
                output += b"\n"
        elif process.poll() is not None:
            break
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        # A prompt that never matched leaves the installer waiting on the
        # terminal; it must not outlive the test.
        process.kill()
        process.wait()
    finally:
        os.close(master)
    return process.returncode, output.decode("utf-8", "replace")


def test_a_first_install_on_a_terminal_asks_for_the_repository_and_checks_the_host(
    mac, tmp_path
):
    log = tmp_path / "ssh.log"
    _write_executable(
        tmp_path / "stubs" / "ssh",
        f'#!/usr/bin/env bash\necho "$*" >>"{log}"\nexit 0\n',
    )

    rc, output = _run_on_a_terminal(
        mac,
        ["ssh://u@borg.example:23/./repo", "borg-1.4", "y"],
        *ENROL,
        "--borg-version",
        "1",
    )

    assert rc == 0, output
    assert "Borg repository this machine backs up to" in output
    assert "SSH connection to u@borg.example: OK." in output
    assert (
        log.read_text().strip() == "-o ConnectTimeout=15 -p 23 -- u@borg.example exit"
    )
    with (mac["agents"] / "com.borg-ui.agent.plist").open("rb") as handle:
        env = plistlib.load(handle)["EnvironmentVariables"]
    assert env["BORG_REPO"] == "ssh://u@borg.example:23/./repo"
    assert env["BORG_REMOTE_PATH"] == "borg-1.4"


def test_a_rest_store_gets_the_ssh_check_too(mac, tmp_path):
    """A rest:// store is reached over SSH, so its host key needs the same
    first contact."""
    log = tmp_path / "ssh.log"
    _write_executable(
        tmp_path / "stubs" / "ssh",
        f'#!/usr/bin/env bash\necho "$*" >>"{log}"\nexit 0\n',
    )

    rc, output = _run_on_a_terminal(
        mac,
        ["rest://borg@store.example/series/repo", "", "y"],
        *ENROL,
        "--borg-version",
        "1",
    )

    assert rc == 0, output
    assert (
        log.read_text().strip()
        == "-o ConnectTimeout=15 -p 22 -- borg@store.example exit"
    )


def test_a_failed_ssh_check_is_reported_and_the_install_goes_on(mac, tmp_path):
    _write_executable(tmp_path / "stubs" / "ssh", "#!/usr/bin/env bash\nexit 255\n")

    rc, output = _run_on_a_terminal(
        mac, ["ssh://u@borg.example/./repo", "", ""], *ENROL, "--borg-version", "1"
    )

    assert rc == 0, output
    assert "SSH connection to u@borg.example failed (exit 255)" in output
    assert (mac["root"] / "config.toml").exists()


def test_an_empty_answer_skips_the_repository(mac):
    rc, output = _run_on_a_terminal(mac, [""], *ENROL, "--borg-version", "1")

    assert rc == 0, output
    assert "Borg executable on that host" not in output
    assert not (mac["root"] / "agent.env").exists()
