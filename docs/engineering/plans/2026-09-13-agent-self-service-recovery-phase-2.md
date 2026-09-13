# Agent self-service recovery phase 2: uninstall

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. The owner has ruled out subagents on
> cost, so `superpowers:subagent-driven-development` is not an option here.

**Goal:** An operator retiring a machine clicks **Uninstall** on its card, runs
the one command it hands them, and the machine is left with no trace of Borg
UI: no service, no venv, no config, no dedicated user. Their own Borg
installation and their backup repositories are untouched.

**Architecture:** One new route, `GET /agent/uninstall.sh`, beside the
`install.sh` route, serving a static string constant. Unlike `install.sh` it
takes no query parameters and renders no per-agent pins, so it needs no
database access and is byte-identical for every caller. The script unregisters
first, best effort, using the credential already in `config.toml`, then removes
the inventory in spec section 6.2, collecting failures rather than aborting
halfway. Two removals are conditional and those conditions are the point of the
change: a Borg symlink is removed only when it resolves under
`/opt/borg-ui-agent`, and the service account is deleted only when it is
literally `borg-ui-agent`. On the page, one more card action and one more
dialog.

**Tech Stack:** FastAPI, bash (the served script is tested by running it),
pytest, React, TypeScript, MUI, i18next, Vitest, Storybook.

**Spec:** `docs/engineering/specs/2026-09-12-agent-self-service-recovery.md`
(sections 4, 6, 7, 8, 9; phase 10.3). Appendix A lists every file touched.

## Global Constraints

- No em dashes in UI copy, i18n strings, code comments, docs, or commit
  messages. Check added lines only, with
  `git diff -U0 origin/main | grep -n $'—'` (BSD grep has no `-P`).
- Every new i18n key must be added to all four locales:
  `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`. The
  `frontend-locale-check` pre-push hook fails otherwise.
- New UI components go in `frontend/src/pages/managed-agents/`, not inline in
  `ManagedAgents.tsx`.
- New or changed UI ships a Storybook story for the changed state, in default
  and mobile viewports. Storybook here hardcodes the light theme
  (`.storybook/preview.tsx:43`), so dark cannot be checked there; say so rather
  than claiming it was.
- No heavy left accent borders on cards, panels, alerts, or status surfaces
  (`AGENTS.md`, UI Preferences).
- **Backup repositories are never touched, under any flag.** Nothing in this
  script may remove, move, or write to a repository path.
- The upgrade helper and its `.path` trigger are not used to perform the
  uninstall. The script removes them; it never triggers them (spec section 8).
- Do not re-open a decision in the spec's Appendix B. In particular B.3, full
  removal by default, and B.4, no checksum on the pasted command.

## The two safety rules

Spec section 6.2 calls these load-bearing, and section 9 says they are the
tests that matter most in this change. They are stated here once, in full,
because every task below depends on them.

1. **A Borg symlink is removed only when it resolves to a path under
   `/opt/borg-ui-agent`.** The installer creates `/usr/local/bin/borg` and
   `/usr/local/bin/borg2` as symlinks to forwarder scripts in
   `/opt/borg-ui-agent/bin` (`app/api/agent_installer.py:605`), so a link this
   installer owns always resolves under `AGENT_ROOT`. This is the same test
   `_classify_install_source` uses to label a binary `borg-ui-installer` in the
   UI (`agent/borg_ui_agent/borg.py:49`), so the uninstaller and the card agree
   by construction. A distro Borg at `/usr/bin/borg` is never touched, and
   neither is a symlink an operator pointed elsewhere. Removing a
   system-package Borg would break Borg for everything else on that machine,
   including backups run outside Borg UI.
2. **The service account is deleted only when it is literally
   `borg-ui-agent`.** That is the dedicated account the installer creates
   (`app/api/agent_installer.py:352`). An install run with
   `--service-user current` binds the service to the operator's own login
   account (`resolve_current_service_user`, line 336), and deleting that would
   be catastrophic. The script reads `User=` from the unit before removing the
   unit, and deletes the account only on an exact match.

Both rules hold under every flag. Neither is a preference to be simplified
away.

## Decisions this plan makes that the spec leaves open

Called out here rather than buried in a task, and repeated as Open questions at
the end for the phase gate.

1. **The script's paths are overridable for testing, through environment
   variables defaulting to the real paths.** The spec says the script is tested
   by running it, matching `install.sh`. `install.sh` is tested by extracting
   individual functions with a regex and running them in a harness with the
   machine facts injected (`tests/unit/test_agent_installer_api.py:209`). The
   uninstaller's removals take paths rather than machine facts, so the same
   technique needs the paths to be injectable. Each is declared
   `VAR="${VAR:-/real/path}"`, which changes nothing for a real run piped into
   `sudo bash` with no environment set, and lets a test point the whole
   inventory at a tmpdir. The alternative, asserting on the script text rather
   than its behavior, would not test the safety rules at all.
2. **`systemctl` and `userdel` are called through one-line wrappers.** Same
   reason: a test harness stubs the wrapper and records the call, so the
   service-user rule can be tested without creating and deleting real accounts
   on the machine running the suite. The wrappers add no logic.
3. **A failure to unregister is reported but never fails the script.** Spec
   section 6.4 makes this best effort with a short timeout, because a stranded
   agent is a likely reason to be uninstalling. This plan puts the timeout at 5
   seconds and says so in the output either way.

---

### Task 1: the route and the script skeleton

**Files:**
- Modify: `app/api/agent_installer.py` (add `UNINSTALLER_SCRIPT` beside
  `INSTALLER_SCRIPT` at line 35, and the route beside `install.sh` at line
  1242)
- Test: `tests/unit/test_agent_uninstaller_api.py` (new)

**Interfaces:**
- Consumes: `router` from `app/api/agent_installer.py`, unchanged.
- Produces: `UNINSTALLER_SCRIPT: str` and `GET /agent/uninstall.sh`. Task 2 and
  Task 3 add functions to that same constant.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_agent_uninstaller_api.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_agent_uninstaller_api.py -v`
Expected: FAIL, 404 on the route.

- [ ] **Step 3: Add the script constant**

In `app/api/agent_installer.py`, after `INSTALLER_SCRIPT`'s closing `"""`, add:

```python
UNINSTALLER_SCRIPT = r"""#!/usr/bin/env bash
# Removes the Borg UI agent from this machine.
#
# Deliberately not `set -e`: every removal tolerates a missing target, and a
# half-removed machine is worse than a fully reported one. Failures are
# collected and printed at the end (spec section 6.5).
set -uo pipefail

# Overridable so the test harness can point the whole inventory at a tmpdir.
# A real run is piped into `sudo bash` with none of these set, so each takes
# its real path.
AGENT_ROOT="${AGENT_ROOT:-/opt/borg-ui-agent}"
CONFIG_DIR="${CONFIG_DIR:-/etc/borg-ui-agent}"
CONFIG_FILE="${CONFIG_FILE:-${CONFIG_DIR}/config.toml}"
UPGRADE_TRIGGER="${UPGRADE_TRIGGER:-${CONFIG_DIR}/upgrade-requested}"
SERVICE_UNIT="${SERVICE_UNIT:-/etc/systemd/system/borg-ui-agent.service}"
UPGRADE_UNIT="${UPGRADE_UNIT:-/etc/systemd/system/borg-ui-agent-upgrade.service}"
UPGRADE_PATH_UNIT="${UPGRADE_PATH_UNIT:-/etc/systemd/system/borg-ui-agent-upgrade.path}"
UPGRADE_CONF="${UPGRADE_CONF:-/etc/borg-ui-agent-upgrade.conf}"
UPGRADE_HELPER="${UPGRADE_HELPER:-${AGENT_ROOT}/bin/borg-ui-agent-upgrade}"
LEGACY_SUDOERS="${LEGACY_SUDOERS:-/etc/sudoers.d/borg-ui-agent-upgrade}"
NO_REMOTE_UPGRADE_MARKER="${NO_REMOTE_UPGRADE_MARKER:-/etc/borg-ui-agent-no-remote-upgrade}"
STATE_DIR="${STATE_DIR:-/var/lib/borg-ui-agent}"
BORG1_LINK="${BORG1_LINK:-/usr/local/bin/borg}"
BORG2_LINK="${BORG2_LINK:-/usr/local/bin/borg2}"
DEDICATED_USER="${DEDICATED_USER:-borg-ui-agent}"
UNREGISTER_TIMEOUT="${UNREGISTER_TIMEOUT:-5}"

KEEP_BORG="0"
KEEP_USER="0"
KEEP_CONFIG="0"

FAILURES=()

note_failure() {
  FAILURES+=("$1")
}

# Wrapped so the test harness can stub them. No logic of their own.
run_systemctl() {
  systemctl "$@" >/dev/null 2>&1
}

run_userdel() {
  userdel --remove "$1" >/dev/null 2>&1
}

usage() {
  cat <<'USAGE'
Usage:
  curl -fsSL http://SERVER:PORT/agent/uninstall.sh | sudo bash

Removes the Borg UI agent from this machine: the service, the upgrade helper,
the virtualenv, the configuration, and the dedicated service user.

Your own Borg installation and your backup repositories are never touched.

Options:
  --keep-borg     Leave the Borg binaries this installer placed, and their
                  symlinks, in place
  --keep-user     Leave the dedicated borg-ui-agent user and its state
                  directory in place
  --keep-config   Leave /etc/borg-ui-agent/config.toml in place, for a
                  reinstall against the same registration
  --help          Print this message

A Borg installed by your distribution is never removed, with or without
--keep-borg. A service user that is not the dedicated borg-ui-agent account is
never deleted, with or without --keep-user.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-borg) KEEP_BORG="1"; shift ;;
    --keep-user) KEEP_USER="1"; shift ;;
    --keep-config) KEEP_CONFIG="1"; shift ;;
    --help|-h) usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Run with --help for usage." >&2
      exit 2
      ;;
  esac
done
"""
```

The rest of the script arrives in Tasks 2 and 3. Leave it here for now so this
task's tests can pass on their own.

- [ ] **Step 4: Add the route**

In `app/api/agent_installer.py`, directly after the `install.sh.sha256` route:

```python
@router.get("/agent/uninstall.sh")
async def get_agent_uninstaller() -> Response:
    """The uninstaller this server serves, identical for every caller.

    Unauthenticated, matching install.sh beside it. Acceptable because the
    script is static: it carries no credential, no pins and no per-agent data,
    and does nothing unless an operator with root on a machine chooses to run
    it there. It reveals only that a Borg UI server is present, which
    install.sh already reveals (spec section 8).

    Takes no query parameters and touches no database, so unlike the installer
    it needs neither a session nor a worker thread.
    """
    return Response(content=UNINSTALLER_SCRIPT, media_type="text/x-shellscript")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_agent_uninstaller_api.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 6: Commit**

```bash
git add app/api/agent_installer.py tests/unit/test_agent_uninstaller_api.py
git commit -m "feat(agent-installer): serve a static uninstall script"
```

---

### Task 2: the removals, and the two safety rules

**Files:**
- Modify: `app/api/agent_installer.py` (`UNINSTALLER_SCRIPT`)
- Test: `tests/unit/test_agent_uninstaller_script.py` (new)

**Interfaces:**
- Consumes: the variables and `note_failure` / `run_systemctl` / `run_userdel`
  from Task 1.
- Produces: shell functions `remove_service`, `remove_upgrade_artifacts`,
  `remove_borg_links`, `remove_service_user`, `remove_agent_files`, and
  `report`. Task 3 adds `unregister` and the main sequence that calls all of
  them.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_agent_uninstaller_script.py`. The harness mirrors
`_run_install_borg_from_server` in `tests/unit/test_agent_installer_api.py:209`:
pull the functions out of the served script, inject state, run one.

```python
import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_STUBS = """
run_systemctl() { echo "systemctl $*" >>"${CALL_LOG}"; }
run_userdel() { echo "userdel $1" >>"${CALL_LOG}"; }
"""


def _extract(script: str, *names: str) -> str:
    return "\n".join(
        re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", script, re.M | re.S).group(0)
        for name in names
    )


def _run(
    script: str, *, functions: tuple[str, ...], body: str, env: dict[str, str]
) -> subprocess.CompletedProcess:
    harness = "\n".join(
        [
            "set -uo pipefail",
            "FAILURES=()",
            'note_failure() { FAILURES+=("$1"); }',
            _STUBS,
            _extract(script, *functions),
            body,
        ]
    )
    return subprocess.run(
        ["bash", "-c", harness],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", **env},
    )


@pytest.fixture
def script(test_client: TestClient) -> str:
    return test_client.get("/agent/uninstall.sh").text


@pytest.fixture
def call_log(tmp_path: Path) -> Path:
    path = tmp_path / "calls.log"
    path.touch()
    return path


def test_removes_a_symlink_into_the_agent_root(
    script: str, tmp_path: Path, call_log: Path
):
    agent_root = tmp_path / "opt" / "borg-ui-agent"
    (agent_root / "bin").mkdir(parents=True)
    forwarder = agent_root / "bin" / "borg"
    forwarder.write_text("#!/bin/sh\n")
    link = tmp_path / "usr" / "local" / "bin" / "borg"
    link.parent.mkdir(parents=True)
    link.symlink_to(forwarder)

    result = _run(
        script,
        functions=("remove_borg_links",),
        body="remove_borg_links",
        env={
            "CALL_LOG": str(call_log),
            "AGENT_ROOT": str(agent_root),
            "BORG1_LINK": str(link),
            "BORG2_LINK": str(tmp_path / "usr" / "local" / "bin" / "borg2"),
            "KEEP_BORG": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert not link.exists() and not link.is_symlink()


def test_leaves_a_distro_borg_symlink_alone(
    script: str, tmp_path: Path, call_log: Path
):
    """SAFETY RULE 1. If this ever inverts, an uninstall breaks Borg for
    everything else on the machine, including backups run outside Borg UI."""
    agent_root = tmp_path / "opt" / "borg-ui-agent"
    agent_root.mkdir(parents=True)
    distro_borg = tmp_path / "usr" / "bin" / "borg"
    distro_borg.parent.mkdir(parents=True)
    distro_borg.write_text("#!/bin/sh\n")
    link = tmp_path / "usr" / "local" / "bin" / "borg"
    link.parent.mkdir(parents=True)
    link.symlink_to(distro_borg)

    result = _run(
        script,
        functions=("remove_borg_links",),
        body="remove_borg_links",
        env={
            "CALL_LOG": str(call_log),
            "AGENT_ROOT": str(agent_root),
            "BORG1_LINK": str(link),
            "BORG2_LINK": str(tmp_path / "usr" / "local" / "bin" / "borg2"),
            "KEEP_BORG": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert link.is_symlink()
    assert distro_borg.exists()


def test_leaves_a_real_file_at_the_link_path_alone(
    script: str, tmp_path: Path, call_log: Path
):
    """Not a symlink at all: an operator's own binary sitting at the same path
    is not ours to remove."""
    agent_root = tmp_path / "opt" / "borg-ui-agent"
    agent_root.mkdir(parents=True)
    real = tmp_path / "usr" / "local" / "bin" / "borg"
    real.parent.mkdir(parents=True)
    real.write_text("#!/bin/sh\n")

    result = _run(
        script,
        functions=("remove_borg_links",),
        body="remove_borg_links",
        env={
            "CALL_LOG": str(call_log),
            "AGENT_ROOT": str(agent_root),
            "BORG1_LINK": str(real),
            "BORG2_LINK": str(tmp_path / "nope"),
            "KEEP_BORG": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert real.exists()


def test_keep_borg_leaves_an_owned_symlink_alone(
    script: str, tmp_path: Path, call_log: Path
):
    agent_root = tmp_path / "opt" / "borg-ui-agent"
    (agent_root / "bin").mkdir(parents=True)
    forwarder = agent_root / "bin" / "borg"
    forwarder.write_text("#!/bin/sh\n")
    link = tmp_path / "usr" / "local" / "bin" / "borg"
    link.parent.mkdir(parents=True)
    link.symlink_to(forwarder)

    result = _run(
        script,
        functions=("remove_borg_links",),
        body="remove_borg_links",
        env={
            "CALL_LOG": str(call_log),
            "AGENT_ROOT": str(agent_root),
            "BORG1_LINK": str(link),
            "BORG2_LINK": str(tmp_path / "nope"),
            "KEEP_BORG": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    assert link.is_symlink()


def test_deletes_only_the_dedicated_service_user(
    script: str, tmp_path: Path, call_log: Path
):
    """SAFETY RULE 2, the half that acts."""
    unit = tmp_path / "borg-ui-agent.service"
    unit.write_text("[Service]\nUser=borg-ui-agent\nGroup=borg-ui-agent\n")

    result = _run(
        script,
        functions=("remove_service_user",),
        body="remove_service_user",
        env={
            "CALL_LOG": str(call_log),
            "SERVICE_UNIT": str(unit),
            "STATE_DIR": str(tmp_path / "var" / "lib" / "borg-ui-agent"),
            "DEDICATED_USER": "borg-ui-agent",
            "KEEP_USER": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "userdel borg-ui-agent" in call_log.read_text()


def test_never_deletes_an_operator_login_account(
    script: str, tmp_path: Path, call_log: Path
):
    """SAFETY RULE 2, the half that matters. An install run with
    --service-user current binds the unit to the operator's own login account.
    If this ever inverts, an uninstall deletes that account and its home
    directory."""
    unit = tmp_path / "borg-ui-agent.service"
    unit.write_text("[Service]\nUser=someoperator\nGroup=someoperator\n")

    result = _run(
        script,
        functions=("remove_service_user",),
        body="remove_service_user",
        env={
            "CALL_LOG": str(call_log),
            "SERVICE_UNIT": str(unit),
            "STATE_DIR": str(tmp_path / "var" / "lib" / "borg-ui-agent"),
            "DEDICATED_USER": "borg-ui-agent",
            "KEEP_USER": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "userdel" not in call_log.read_text()


def test_never_deletes_root_as_a_service_user(
    script: str, tmp_path: Path, call_log: Path
):
    """--service-user root is a supported install mode."""
    unit = tmp_path / "borg-ui-agent.service"
    unit.write_text("[Service]\nUser=root\n")

    result = _run(
        script,
        functions=("remove_service_user",),
        body="remove_service_user",
        env={
            "CALL_LOG": str(call_log),
            "SERVICE_UNIT": str(unit),
            "STATE_DIR": str(tmp_path / "state"),
            "DEDICATED_USER": "borg-ui-agent",
            "KEEP_USER": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "userdel" not in call_log.read_text()


def test_deletes_nothing_when_the_unit_is_already_gone(
    script: str, tmp_path: Path, call_log: Path
):
    """Silence is not consent. A machine whose unit was removed by hand tells
    us nothing about which account ran the service, so the account stays."""
    result = _run(
        script,
        functions=("remove_service_user",),
        body="remove_service_user",
        env={
            "CALL_LOG": str(call_log),
            "SERVICE_UNIT": str(tmp_path / "absent.service"),
            "STATE_DIR": str(tmp_path / "state"),
            "DEDICATED_USER": "borg-ui-agent",
            "KEEP_USER": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "userdel" not in call_log.read_text()


def test_keep_user_leaves_the_dedicated_account_alone(
    script: str, tmp_path: Path, call_log: Path
):
    unit = tmp_path / "borg-ui-agent.service"
    unit.write_text("[Service]\nUser=borg-ui-agent\n")
    state = tmp_path / "var" / "lib" / "borg-ui-agent"
    state.mkdir(parents=True)

    result = _run(
        script,
        functions=("remove_service_user",),
        body="remove_service_user",
        env={
            "CALL_LOG": str(call_log),
            "SERVICE_UNIT": str(unit),
            "STATE_DIR": str(state),
            "DEDICATED_USER": "borg-ui-agent",
            "KEEP_USER": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "userdel" not in call_log.read_text()
    assert state.exists()


def test_keep_config_keeps_the_config_but_not_the_upgrade_trigger(
    script: str, tmp_path: Path, call_log: Path
):
    config_dir = tmp_path / "etc" / "borg-ui-agent"
    config_dir.mkdir(parents=True)
    config = config_dir / "config.toml"
    config.write_text('server_url = "http://x"\n')
    trigger = config_dir / "upgrade-requested"
    trigger.touch()

    result = _run(
        script,
        functions=("remove_agent_files",),
        body="remove_agent_files",
        env={
            "CALL_LOG": str(call_log),
            "AGENT_ROOT": str(tmp_path / "opt" / "borg-ui-agent"),
            "CONFIG_DIR": str(config_dir),
            "CONFIG_FILE": str(config),
            "UPGRADE_TRIGGER": str(trigger),
            "NO_REMOTE_UPGRADE_MARKER": str(tmp_path / "marker"),
            "KEEP_CONFIG": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    assert config.exists()
    assert not trigger.exists()


def test_removes_the_whole_config_directory_by_default(
    script: str, tmp_path: Path, call_log: Path
):
    config_dir = tmp_path / "etc" / "borg-ui-agent"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text('server_url = "http://x"\n')
    agent_root = tmp_path / "opt" / "borg-ui-agent"
    agent_root.mkdir(parents=True)
    (agent_root / "marker").touch()

    result = _run(
        script,
        functions=("remove_agent_files",),
        body="remove_agent_files",
        env={
            "CALL_LOG": str(call_log),
            "AGENT_ROOT": str(agent_root),
            "CONFIG_DIR": str(config_dir),
            "CONFIG_FILE": str(config_dir / "config.toml"),
            "UPGRADE_TRIGGER": str(config_dir / "upgrade-requested"),
            "NO_REMOTE_UPGRADE_MARKER": str(tmp_path / "marker"),
            "KEEP_CONFIG": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert not config_dir.exists()
    assert not agent_root.exists()


def test_every_removal_tolerates_a_missing_target(
    script: str, tmp_path: Path, call_log: Path
):
    """Spec section 6.5: running the script twice, or on a machine that was
    never fully installed, exits zero."""
    absent = tmp_path / "absent"

    result = _run(
        script,
        functions=("remove_agent_files", "remove_borg_links", "remove_service_user"),
        body="remove_agent_files; remove_borg_links; remove_service_user",
        env={
            "CALL_LOG": str(call_log),
            "AGENT_ROOT": str(absent / "opt"),
            "CONFIG_DIR": str(absent / "etc"),
            "CONFIG_FILE": str(absent / "etc" / "config.toml"),
            "UPGRADE_TRIGGER": str(absent / "etc" / "upgrade-requested"),
            "NO_REMOTE_UPGRADE_MARKER": str(absent / "marker"),
            "SERVICE_UNIT": str(absent / "unit.service"),
            "STATE_DIR": str(absent / "state"),
            "BORG1_LINK": str(absent / "borg"),
            "BORG2_LINK": str(absent / "borg2"),
            "DEDICATED_USER": "borg-ui-agent",
            "KEEP_BORG": "0",
            "KEEP_USER": "0",
            "KEEP_CONFIG": "0",
        },
    )

    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_agent_uninstaller_script.py -v`
Expected: FAIL. `_extract` raises `AttributeError` because none of the
functions exist in the script yet.

- [ ] **Step 3: Add the removal functions**

Append to `UNINSTALLER_SCRIPT` in `app/api/agent_installer.py`, after the
argument loop:

```bash
remove_service() {
  run_systemctl disable --now borg-ui-agent
  rm -f "${SERVICE_UNIT}" || note_failure "could not remove ${SERVICE_UNIT}"
}

# Spec section 6.2 says to reuse the installer's remove_upgrade_artifacts
# (app/api/agent_installer.py:1050). The installer and the uninstaller are two
# separate bash strings served to different machines, so there is no runtime to
# share: what is reused is the inventory, item for item. If the installer's
# list ever grows, this one has to grow with it, and a stale copy here leaves
# an escalation path behind on a machine that is meant to be clean.
remove_upgrade_artifacts() {
  run_systemctl disable --now borg-ui-agent-upgrade.path
  rm -f "${UPGRADE_PATH_UNIT}" "${UPGRADE_UNIT}" "${UPGRADE_HELPER}" \
    "${UPGRADE_CONF}" "${UPGRADE_TRIGGER}" \
    || note_failure "could not remove the upgrade artifacts"
  # An install that predates the path unit granted the agent a sudoers rule.
  # Take it away rather than leaving a live escalation behind on a machine
  # that is supposed to have no Borg UI on it.
  rm -f "${LEGACY_SUDOERS}" || note_failure "could not remove ${LEGACY_SUDOERS}"
}

# SAFETY RULE 1 (spec section 6.2). A link is ours only when it resolves to a
# path under AGENT_ROOT, which is where the installer's forwarder scripts live.
# The same test _classify_install_source uses to label a binary
# "borg-ui-installer" in the UI, so the card and this script agree by
# construction. A distro Borg at /usr/bin/borg, or a link an operator pointed
# somewhere else, is left exactly as it is: removing a system-package Borg
# would break Borg for everything else on the machine.
remove_borg_links() {
  if [[ "${KEEP_BORG}" == "1" ]]; then
    echo "Leaving the Borg binaries and their symlinks in place."
    return 0
  fi

  local link resolved root
  root="$(cd "${AGENT_ROOT}" 2>/dev/null && pwd -P)" || root=""
  for link in "${BORG1_LINK}" "${BORG2_LINK}"; do
    [[ -L "${link}" ]] || continue
    resolved="$(readlink -f "${link}" 2>/dev/null || true)"
    if [[ -n "${root}" && "${resolved}" == "${root}"/* ]]; then
      rm -f "${link}" || note_failure "could not remove ${link}"
    else
      echo "Leaving ${link} alone: it does not point into ${AGENT_ROOT}."
    fi
  done
}

# SAFETY RULE 2 (spec section 6.2). The account is deleted only when the unit
# says the service ran as the dedicated account this installer creates. An
# install run with --service-user current binds the unit to the operator's own
# login account, and deleting that would take their home directory with it.
# A missing unit tells us nothing, so it deletes nothing.
remove_service_user() {
  if [[ "${KEEP_USER}" == "1" ]]; then
    echo "Leaving the service user and its state directory in place."
    return 0
  fi

  local unit_user=""
  if [[ -r "${SERVICE_UNIT}" ]]; then
    unit_user="$(awk -F= '/^User=/ {print $2; exit}' "${SERVICE_UNIT}" 2>/dev/null || true)"
  fi

  if [[ "${unit_user}" != "${DEDICATED_USER}" ]]; then
    if [[ -n "${unit_user}" ]]; then
      echo "Leaving the '${unit_user}' account alone: only the dedicated ${DEDICATED_USER} account is removed."
    fi
    return 0
  fi

  rm -rf "${STATE_DIR}" || note_failure "could not remove ${STATE_DIR}"
  run_userdel "${DEDICATED_USER}"
}

remove_agent_files() {
  rm -rf "${AGENT_ROOT}" || note_failure "could not remove ${AGENT_ROOT}"
  rm -f "${NO_REMOTE_UPGRADE_MARKER}" \
    || note_failure "could not remove ${NO_REMOTE_UPGRADE_MARKER}"

  if [[ "${KEEP_CONFIG}" == "1" ]]; then
    # The operator asked to keep the file, not to keep the upgrade trigger:
    # an unwatched trigger left behind is a request nothing will ever serve.
    rm -f "${UPGRADE_TRIGGER}" || note_failure "could not remove ${UPGRADE_TRIGGER}"
    echo "Keeping ${CONFIG_FILE}."
    return 0
  fi

  rm -rf "${CONFIG_DIR}" || note_failure "could not remove ${CONFIG_DIR}"
}

report() {
  # The early return is load-bearing, not just tidy: under `set -u`, bash 3.2
  # (which macOS ships, and which runs these tests locally) aborts on
  # "${FAILURES[@]}" when the array is empty. Expanding it only after the count
  # check is what keeps the happy path working there. If you restructure this,
  # check it on bash 3.2, not only on CI's bash 5.
  if [[ ${#FAILURES[@]} -eq 0 ]]; then
    echo "Borg UI agent removed."
    return 0
  fi
  echo "Borg UI agent removed, with problems:" >&2
  local failure
  for failure in "${FAILURES[@]}"; do
    echo "  - ${failure}" >&2
  done
  return 1
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_agent_uninstaller_script.py -v`
Expected: PASS, 12 tests.

- [ ] **Step 5: Prove the safety rules fail loudly when inverted**

Spec section 9 asks that each safety rule get a test that fails if the
condition is inverted. Verify by hand, then revert:

1. In `remove_borg_links`, change `"${resolved}" == "${root}"/*` to
   `"${resolved}" != "${root}"/*`. Run
   `pytest tests/unit/test_agent_uninstaller_script.py -v`. Expected:
   `test_leaves_a_distro_borg_symlink_alone` FAILS. Revert.
2. In `remove_service_user`, change `!=` to `==` in the
   `"${unit_user}" != "${DEDICATED_USER}"` test. Run the suite. Expected:
   `test_never_deletes_an_operator_login_account` and
   `test_never_deletes_root_as_a_service_user` FAIL. Revert.

Confirm `git diff` is empty before moving on. Do not commit either inversion.

- [ ] **Step 6: Commit**

```bash
git add app/api/agent_installer.py tests/unit/test_agent_uninstaller_script.py
git commit -m "feat(agent-installer): remove the agent, with the two safety rules"
```

---

### Task 3: unregister first, then the main sequence

**Files:**
- Modify: `app/api/agent_installer.py` (`UNINSTALLER_SCRIPT`)
- Test: `tests/unit/test_agent_uninstaller_script.py`

**Interfaces:**
- Consumes: the functions from Task 2.
- Produces: shell function `unregister`, and the main sequence. Nothing later
  depends on these.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_agent_uninstaller_script.py`:

```python
_CURL_STUB = """
curl() { echo "curl $*" >>"${CALL_LOG}"; return "${CURL_RC:-0}"; }
"""


def _run_unregister(
    script: str, *, call_log: Path, config: Path, curl_rc: str = "0"
) -> subprocess.CompletedProcess:
    harness = "\n".join(
        [
            "set -uo pipefail",
            "FAILURES=()",
            'note_failure() { FAILURES+=("$1"); }',
            _CURL_STUB,
            _extract(script, "unregister"),
            "unregister",
        ]
    )
    return subprocess.run(
        ["bash", "-c", harness],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "CALL_LOG": str(call_log),
            "CONFIG_FILE": str(config),
            "UNREGISTER_TIMEOUT": "5",
            "CURL_RC": curl_rc,
        },
    )


def _write_config(tmp_path: Path) -> Path:
    config = tmp_path / "config.toml"
    config.write_text(
        'server_url = "https://borg.example.com"\n'
        'agent_id = "agt_abc"\n'
        'agent_token = "secret-token"\n'
        'name = "db-01"\n'
    )
    return config


def test_unregister_calls_the_server_recorded_in_the_config(
    script: str, tmp_path: Path, call_log: Path
):
    result = _run_unregister(
        script, call_log=call_log, config=_write_config(tmp_path)
    )

    calls = call_log.read_text()
    assert result.returncode == 0, result.stderr
    assert "https://borg.example.com/api/agents/unregister" in calls
    assert "X-Borg-Agent-Authorization: Bearer secret-token" in calls


def test_unregister_never_echoes_the_token(
    script: str, tmp_path: Path, call_log: Path
):
    """Spec section 8. The token reaches curl and nothing else."""
    result = _run_unregister(
        script, call_log=call_log, config=_write_config(tmp_path)
    )

    assert "secret-token" not in result.stdout
    assert "secret-token" not in result.stderr


def test_unregister_continues_when_the_server_is_unreachable(
    script: str, tmp_path: Path, call_log: Path
):
    """Spec section 6.4. A stranded agent is a likely reason to be
    uninstalling, and it must not block local cleanup."""
    result = _run_unregister(
        script, call_log=call_log, config=_write_config(tmp_path), curl_rc="7"
    )

    assert result.returncode == 0, result.stderr
    assert "could not" in result.stdout.lower() or "not notified" in result.stdout.lower()


def test_unregister_skips_a_missing_config(
    script: str, tmp_path: Path, call_log: Path
):
    """Safe on a partially installed or already-unregistered machine."""
    result = _run_unregister(
        script, call_log=call_log, config=tmp_path / "absent.toml"
    )

    assert result.returncode == 0, result.stderr
    assert call_log.read_text() == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_agent_uninstaller_script.py -k unregister -v`
Expected: FAIL, `unregister` not found in the script.

- [ ] **Step 3: Add the unregister function**

Append to `UNINSTALLER_SCRIPT`, after `report`:

```bash
# Best effort, and deliberately so (spec section 6.4). The server marks the
# machine revoked, so the card reflects reality without the operator clicking
# Delete. A stranded agent cannot reach its server, which is a likely reason to
# be uninstalling in the first place, so a failure here reports and continues.
#
# The token is read from the config and sent only to the server_url recorded in
# that same file, never to a URL passed on the command line, so a pasted script
# cannot be steered into exfiltrating the credential. It is never echoed.
unregister() {
  if [[ ! -r "${CONFIG_FILE}" ]]; then
    echo "No readable config at ${CONFIG_FILE}; skipping the unregister call."
    return 0
  fi

  local server token
  server="$(awk -F'"' '/^server_url[[:space:]]*=/ {print $2; exit}' "${CONFIG_FILE}")"
  token="$(awk -F'"' '/^agent_token[[:space:]]*=/ {print $2; exit}' "${CONFIG_FILE}")"

  if [[ -z "${server}" || -z "${token}" ]]; then
    echo "The config carries no server URL and token; skipping the unregister call."
    return 0
  fi

  if curl -fsS --max-time "${UNREGISTER_TIMEOUT}" -X POST \
    -H "X-Borg-Agent-Authorization: Bearer ${token}" \
    "${server%/}/api/agents/unregister" >/dev/null 2>&1; then
    echo "Server notified: this endpoint is now revoked."
  else
    echo "Could not reach ${server} to unregister. Removing locally anyway."
  fi
  return 0
}
```

- [ ] **Step 4: Add the main sequence**

Append to `UNINSTALLER_SCRIPT`, at the very end:

```bash
if [[ "${EUID:-$(id -u)}" != "0" ]]; then
  echo "This must run as root. Pipe it into 'sudo bash'." >&2
  exit 1
fi

unregister
remove_service
remove_upgrade_artifacts
remove_borg_links
remove_service_user
remove_agent_files
run_systemctl daemon-reload
report
```

- [ ] **Step 5: Run the whole suite to verify it passes**

Run: `pytest tests/unit/test_agent_uninstaller_script.py tests/unit/test_agent_uninstaller_api.py -v`
Expected: PASS, 16 tests.

Note the root guard is added after the Task 1 `--help` test, which must still
pass: `--help` exits before the guard is reached. If it now fails, the guard is
in the wrong place. Move it below the argument loop, not above.

- [ ] **Step 6: Commit**

```bash
git add app/api/agent_installer.py tests/unit/test_agent_uninstaller_script.py
git commit -m "feat(agent-installer): unregister before removing the agent"
```

---

### Task 4: the uninstall dialog and the card action

**Files:**
- Create: `frontend/src/pages/managed-agents/AgentUninstallDialog.tsx`
- Create: `frontend/src/pages/managed-agents/AgentUninstallDialog.stories.tsx`
- Modify: `frontend/src/pages/ManagedAgents.tsx`
- Modify: `frontend/src/pages/ManagedAgents.stories.tsx`
- Modify: `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`
- Test: `frontend/src/pages/managed-agents/__tests__/AgentUninstallDialog.test.tsx`

**Interfaces:**
- Consumes: `CopyableCodeBlock` and `ResponsiveDialog`, both already used by
  `AgentSetServerDialog` (phase 1).
- Produces: default export `AgentUninstallDialog` with props
  `{ agent: AgentMachineResponse | null; open: boolean; serverUrl: string; onCopy: (value: string) => void; onCancel: () => void }`.

- [ ] **Step 1: Write the failing test**

Create
`frontend/src/pages/managed-agents/__tests__/AgentUninstallDialog.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import AgentUninstallDialog from '../AgentUninstallDialog'
import type { AgentMachineResponse } from '../../../services/api'

const agent = {
  id: 1,
  agent_id: 'agt_1',
  name: 'db-01',
  hostname: 'db-01.internal',
  status: 'offline',
} as AgentMachineResponse

const renderDialog = () => {
  const onCopy = vi.fn()
  render(
    <AgentUninstallDialog
      agent={agent}
      open
      serverUrl="https://borg-ui.example.com"
      onCopy={onCopy}
      onCancel={vi.fn()}
    />
  )
  return { onCopy }
}

describe('AgentUninstallDialog', () => {
  it('renders the uninstall command', () => {
    renderDialog()
    expect(
      screen.getByText('curl -fsSL https://borg-ui.example.com/agent/uninstall.sh | sudo bash')
    ).toBeInTheDocument()
  })

  it('copies the command', async () => {
    const { onCopy } = renderDialog()
    await userEvent.click(screen.getByRole('button', { name: /copy/i }))
    expect(onCopy).toHaveBeenCalledWith(expect.stringContaining('uninstall.sh'))
  })

  it('says plainly that Borg and the repositories are not touched', () => {
    renderDialog()
    expect(screen.getByText(/your own Borg installation/i)).toBeInTheDocument()
    expect(screen.getByText(/backup repositories/i)).toBeInTheDocument()
  })

  it('lists what the script removes', () => {
    renderDialog()
    expect(screen.getByText(/service/i)).toBeInTheDocument()
    expect(screen.getByText(/\/opt\/borg-ui-agent/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && yarn vitest run src/pages/managed-agents/__tests__/AgentUninstallDialog.test.tsx`
Expected: FAIL, module not found.

- [ ] **Step 3: Add the i18n keys**

Add to `managedAgents.page` in `en.json`, and translated equivalents in
`de.json`, `es.json` and `it.json`:

```json
"uninstallDialog": {
  "title": "Uninstall the agent",
  "description": "Run this on the endpoint to remove Borg UI from it completely. It unregisters itself first, so this card updates on its own.",
  "removesTitle": "What this removes",
  "removesService": "The borg-ui-agent service and its upgrade helper",
  "removesVenv": "The virtualenv at /opt/borg-ui-agent",
  "removesConfig": "The configuration at /etc/borg-ui-agent, including the credential",
  "removesUser": "The dedicated borg-ui-agent service user, if the install created one",
  "keepsBorg": "Your own Borg installation is not touched. Only binaries this installer placed are removed.",
  "keepsRepositories": "Your backup repositories are not touched.",
  "copyCommand": "Copy command"
}
```

And to `managedAgents.page.actions` in all four locales:

```json
"uninstallAgent": "Uninstall the agent"
```

- [ ] **Step 4: Write the dialog**

Create `frontend/src/pages/managed-agents/AgentUninstallDialog.tsx`:

```tsx
import {
  Alert,
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material'
import { useTranslation } from 'react-i18next'
import ResponsiveDialog from '../../components/shared/ResponsiveDialog'
import type { AgentMachineResponse } from '../../services/api'
import CopyableCodeBlock from './CopyableCodeBlock'

/**
 * Hands the operator the one command that removes Borg UI from an endpoint.
 *
 * No typed confirmation: the command still has to be pasted into a root shell
 * on the target machine, which is confirmation enough (spec section 7). What
 * the dialog owes the operator instead is an honest inventory, and the two
 * lines saying what is not touched.
 */
export default function AgentUninstallDialog({
  agent,
  open,
  serverUrl,
  onCopy,
  onCancel,
}: {
  agent: AgentMachineResponse | null
  open: boolean
  serverUrl: string
  onCopy: (value: string) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const command = `curl -fsSL ${serverUrl}/agent/uninstall.sh | sudo bash`

  const removals = [
    t('managedAgents.page.uninstallDialog.removesService'),
    t('managedAgents.page.uninstallDialog.removesVenv'),
    t('managedAgents.page.uninstallDialog.removesConfig'),
    t('managedAgents.page.uninstallDialog.removesUser'),
  ]

  return (
    <ResponsiveDialog
      open={open}
      onClose={onCancel}
      fullWidth
      maxWidth="md"
      footer={
        <DialogActions>
          <Button onClick={onCancel}>{t('common.buttons.close')}</Button>
        </DialogActions>
      }
    >
      <DialogTitle>{t('managedAgents.page.uninstallDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          <Stack spacing={0.5}>
            <Typography sx={{ fontWeight: 700 }}>
              {[agent?.name, agent?.hostname].filter(Boolean).join(' · ')}
            </Typography>
            <Typography sx={{ color: 'text.secondary' }}>
              {t('managedAgents.page.uninstallDialog.description')}
            </Typography>
          </Stack>
          <CopyableCodeBlock
            value={command}
            copyLabel={t('managedAgents.page.uninstallDialog.copyCommand')}
            onCopy={() => onCopy(command)}
          />
          <Stack spacing={0.5}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              {t('managedAgents.page.uninstallDialog.removesTitle')}
            </Typography>
            <List dense disablePadding>
              {removals.map((line) => (
                <ListItem key={line} disableGutters sx={{ py: 0 }}>
                  <ListItemText
                    primary={line}
                    primaryTypographyProps={{ variant: 'body2', color: 'text.secondary' }}
                  />
                </ListItem>
              ))}
            </List>
          </Stack>
          <Alert severity="info" sx={{ borderRadius: 1.5 }}>
            {t('managedAgents.page.uninstallDialog.keepsBorg')}{' '}
            {t('managedAgents.page.uninstallDialog.keepsRepositories')}
          </Alert>
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && yarn vitest run src/pages/managed-agents/__tests__/AgentUninstallDialog.test.tsx`
Expected: PASS, 4 tests.

- [ ] **Step 6: Wire it into the card**

In `frontend/src/pages/ManagedAgents.tsx`:

Import beside the phase 1 dialog import:

```tsx
import AgentUninstallDialog from './managed-agents/AgentUninstallDialog'
```

Import `Eraser` from `lucide-react` beside the existing icon imports. State,
beside `setServerTarget`:

```tsx
const [uninstallTarget, setUninstallTarget] = useState<AgentMachineResponse | null>(null)
```

Action button, immediately before the delete button so the two destructive
actions sit together, styled as destructive to match it:

```tsx
<Tooltip title={t('managedAgents.page.actions.uninstallAgent')} arrow>
  <IconButton
    size="small"
    aria-label={t('managedAgents.page.actions.uninstallAgent')}
    onClick={() => {
      trackSystem(EventAction.VIEW, {
        section: MANAGED_AGENTS_ANALYTICS_SECTION,
        operation: 'open_uninstall_dialog',
        status: agent.status,
      })
      setUninstallTarget(agent)
    }}
    sx={{
      width: { xs: 40, sm: 34 },
      height: { xs: 40, sm: 34 },
      borderRadius: 1.5,
      color: alpha(theme.palette.error.main, 0.6),
      '&:hover': {
        color: theme.palette.error.main,
        bgcolor: alpha(theme.palette.error.main, isDark ? 0.15 : 0.1),
      },
    }}
  >
    <Eraser size={16} />
  </IconButton>
</Tooltip>
```

Mount it beside `AgentSetServerDialog`:

```tsx
<AgentUninstallDialog
  open={!!uninstallTarget}
  agent={uninstallTarget}
  serverUrl={serverUrl}
  onCopy={onCopy}
  onCancel={() => setUninstallTarget(null)}
/>
```

- [ ] **Step 7: Add a card test**

Append to the `ManagedAgents server URL recovery` describe block in
`frontend/src/pages/__tests__/ManagedAgents.test.tsx`, or add a sibling block:

```tsx
it('opens the uninstall dialog from the card', async () => {
  renderOffline()

  await userEvent.click(screen.getByRole('button', { name: /uninstall the agent/i }))

  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText(/uninstall\.sh \| sudo bash/)).toBeInTheDocument()
})
```

- [ ] **Step 8: Run the page tests and typecheck**

Run: `cd frontend && yarn vitest run src/pages/managed-agents src/pages/__tests__/ManagedAgents.test.tsx && yarn tsc --noEmit && yarn lint`
Expected: PASS, no type errors, no lint errors.

- [ ] **Step 9: Write the Storybook stories**

Create `frontend/src/pages/managed-agents/AgentUninstallDialog.stories.tsx`:

```tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import AgentUninstallDialog from './AgentUninstallDialog'
import type { AgentMachineResponse } from '../../services/api'

const agent = {
  id: 1,
  agent_id: 'agt_1',
  name: 'db-01',
  hostname: 'db-01.internal',
  status: 'offline',
  agent_version: '0.1.5',
  created_at: '2026-05-10T08:00:00.000Z',
  updated_at: '2026-09-13T08:00:00.000Z',
} as AgentMachineResponse

const meta: Meta<typeof AgentUninstallDialog> = {
  title: 'Managed Agents/AgentUninstallDialog',
  component: AgentUninstallDialog,
  parameters: { layout: 'fullscreen' },
  args: {
    agent,
    open: true,
    serverUrl: 'https://borg-ui.example.com',
    onCopy: () => {},
    onCancel: () => {},
  },
}
export default meta

type Story = StoryObj<typeof AgentUninstallDialog>

export const Default: Story = {}

export const Mobile: Story = {
  parameters: { viewport: { defaultViewport: 'mobile1' } },
}
```

- [ ] **Step 10: Render and check**

Run: `fnm use v24 && cd frontend && yarn storybook --ci --quiet`

Story ids come from the title, lowercased and hyphenated: check
`managed-agents-agentuninstalldialog--default` and `--mobile`. Confirm the
action row still fits on one line at mobile width now that it carries seven
buttons. If it does not, that is a real finding: report it rather than
shrinking the icons.

Storybook here hardcodes the light theme, so dark cannot be verified this way.
Say so rather than claiming it was checked.

- [ ] **Step 11: Commit**

```bash
git add frontend/src
git commit -m "feat(managed-agents): add the uninstall dialog and card action"
```

---

### Task 5: documentation

**Files:**
- Modify: `docs/managed-agents.md`

**Interfaces:**
- Consumes: the command from Task 4 and the flags from Task 1.
- Produces: nothing.

- [ ] **Step 1: Add the removal section**

In `docs/managed-agents.md`, after the "Moving an endpoint to a new server
address" section added in phase 1, add:

```markdown
### Removing an endpoint

`borg-ui-agent unregister` tells the server the endpoint is gone and deletes
its config, but it leaves the service, the virtualenv and the rest on the
machine. To remove everything, open **Managed Agents**, click **Uninstall** on
that endpoint's card, and run the command it gives you:

```bash
curl -fsSL https://borg-ui.example.com/agent/uninstall.sh | sudo bash
```

The script unregisters with the server first, so the card shows the endpoint as
revoked without you clicking Delete. If the server cannot be reached, which is
likely if you are removing an endpoint that has been stranded, it says so and
removes everything locally anyway.

It removes the service and its upgrade helper, the virtualenv at
`/opt/borg-ui-agent`, the configuration at `/etc/borg-ui-agent`, and the
dedicated `borg-ui-agent` service user if the install created one.

Two things it never removes, with or without flags:

- **A Borg your distribution installed.** Only binaries this installer placed
  under `/opt/borg-ui-agent` are removed, along with the `/usr/local/bin`
  symlinks pointing at them. A Borg at `/usr/bin/borg` is left alone, because
  removing it would break Borg for everything else on that machine.
- **A service user that is not the dedicated account.** If the agent was
  installed with `--service-user current`, it runs as your own login account,
  and that account is never deleted.

Your backup repositories are never touched.

Flags, if you want to keep something:

- `--keep-borg` leaves the Borg binaries this installer placed, and their
  symlinks, in place
- `--keep-user` leaves the dedicated service user and `/var/lib/borg-ui-agent`
  in place
- `--keep-config` leaves `/etc/borg-ui-agent/config.toml` in place, for a
  reinstall against the same registration

Running the script twice, or on a machine that was never fully installed, is
safe: every removal tolerates a missing target.
```

- [ ] **Step 2: Check for em dashes**

Run: `git diff -U0 origin/main -- docs/managed-agents.md | grep -n $'—'`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add docs/managed-agents.md
git commit -m "docs(managed-agents): document removing an endpoint"
```

---

## Verification before claiming the phase done

Use `superpowers:verification-before-completion`. Run each and paste the
output rather than asserting the result.

- [ ] `pytest tests/unit/test_agent_uninstaller_api.py tests/unit/test_agent_uninstaller_script.py -v`
- [ ] `pytest tests/unit/test_agent_installer_api.py tests/unit/test_agent_installer_pins.py -q`
      (the uninstaller shares a module with the installer; prove it moved
      nothing)
- [ ] `cd frontend && yarn vitest run src/pages/managed-agents src/pages/__tests__/ManagedAgents.test.tsx`
- [ ] `cd frontend && yarn tsc --noEmit && yarn lint`
- [ ] `git diff -U0 origin/main | grep -n $'—'` returns nothing
- [ ] All four locales carry every new key
- [ ] Storybook rendered for `AgentUninstallDialog` at default and mobile
      width, and the card action row still fits at mobile
- [ ] Both safety-rule inversions from Task 2 Step 5 were performed, failed the
      right tests, and were reverted

## The phase gate

Spec section 10.3: a real endpoint is removed with no trace, verified against
the section 6.2 inventory, with a system-package Borg and the operator's own
login account both demonstrably intact afterwards.

This needs a real machine and is the owner's to run. Suggested check:

1. On the endpoint, before: `ls -la /usr/local/bin/borg /usr/bin/borg`,
   `awk -F= '/^User=/ {print $2}' /etc/systemd/system/borg-ui-agent.service`,
   `id "$(whoami)"`.
2. Run the command from the card.
3. After, confirm gone: `/opt/borg-ui-agent`, `/etc/borg-ui-agent`,
   `/var/lib/borg-ui-agent`, both systemd units, the upgrade helper and conf,
   `/etc/borg-ui-agent-no-remote-upgrade`, `/etc/sudoers.d/borg-ui-agent-upgrade`.
4. Confirm intact: `/usr/bin/borg` still runs, the operator's own account still
   exists with its home directory, and a backup repository is still readable
   with `borg list`.
5. Run the script a second time and confirm it exits zero.
6. Confirm the card shows the endpoint as revoked without clicking Delete.

Test on a machine installed with `--service-user current` specifically. That is
the case safety rule 2 exists for, and the one a dedicated-user test would not
catch.

## Open questions for the gate

**Answered by the owner 2026-09-13:** 1 and 2 accepted as planned, both
seams in. 3 confirmed at 5 seconds.

1. Script paths are overridable through environment variables so the tests can
   run the real functions against a tmpdir (decision 1). Confirm that is
   acceptable in a script piped into `sudo bash`, given every variable takes
   its real path when unset.
2. `systemctl` and `userdel` go through one-line wrappers so the harness can
   stub them (decision 2). Same question.
3. The unregister timeout is 5 seconds (decision 3). Spec section 6.4 says
   short without naming a number.
