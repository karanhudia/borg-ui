# Agent upgrades phase 2: privileged helper and capability

> **Superseded in part.** Tasks below describe a sudoers rule as the trigger.
> Review found that the agent unit sets `NoNewPrivileges=true`, under which
> `sudo` refuses to run, so the rule could never have worked on a non-root
> endpoint. The shipped trigger is a systemd `.path` unit watching
> `/etc/borg-ui-agent/upgrade-requested`. Read the sudoers tasks as history.

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give an enrolled endpoint the machinery to reinstall itself as root
on request, and make the agent report honestly whether that machinery is
present and usable. Nothing triggers it yet: the session command, the job type
and the UI action are phase 3.

**Architecture:** The served installer writes four root-owned artifacts: a
config file recording the reinstall parameters, a helper script that takes no
arguments and reads only that file, a `oneshot` systemd unit that runs the
helper, and a sudoers rule letting the unprivileged service user start exactly
that unit. Because every parameter comes from a root-owned file rather than
from the caller, the escalation carries no attacker-controlled input. On the
agent side one predicate decides whether the endpoint can upgrade itself, and
that predicate gates the `self_upgrade` capability the server already surfaces.

**Tech Stack:** FastAPI, bash (the served installer is a bash script embedded
in Python), systemd, sudoers, React, MUI, i18next, Storybook, pytest, vitest.

**Spec:** `docs/engineering/specs/2026-09-07-centralized-agent-upgrades.md`

## Global Constraints

- No em dashes in UI copy, i18n strings, code comments, or commit messages.
- Every new i18n key must be added to all four locales:
  `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`. The
  `frontend-locale-check` pre-push hook fails otherwise.
- No heavy left accent borders on cards, panels, alerts, or status surfaces
  (`AGENTS.md`, UI Preferences).
- New or changed UI ships a Storybook story demonstrating the changed state.
- New UI components go in `frontend/src/pages/managed-agents/`, not inline in
  `ManagedAgents.tsx`, which is over 2200 lines.
- The installer script lives inside `INSTALLER_SCRIPT`, a Python raw string in
  `app/api/agent_installer.py`. Only the delimited pinning block is rewritten
  when it is served, so everything added here is served verbatim. Two existing
  tests guard the whole script: `bash -n` parses it and `shellcheck
  --severity=warning` lints it. Both must stay green.
- Inside `INSTALLER_SCRIPT`, a `$` that bash must see literally in a nested
  heredoc body is written `\$` only when the heredoc delimiter is unquoted.
  Every heredoc added here uses a **quoted** delimiter (`<<'NAME'`), so its
  body is literal and needs no escaping.
- **Phase 2 triggers nothing.** Do not add the `agent.upgrade` session
  command, the `agent_upgrade` job type, an upgrade endpoint, or an Upgrade
  button. Those are phase 3. This phase only installs the mechanism and
  reports whether it is there.
- Do not register `managed-machines` routes in `ENDPOINT_POLICIES`
  (`app/core/authorization.py`); that router authorizes through
  `get_current_admin_user` in each route signature (spec section 11.2).

## Decisions this plan makes that the spec leaves open

Both are called out at the phase gate rather than buried here.

1. **An endpoint enrolled over `http` reports no `self_upgrade`.** The helper
   refuses a non-https server URL (spec section 6), so an endpoint whose
   `config.toml` names an `http` server can never upgrade itself. Section 6
   also insists one predicate decide both the capability and the command, so
   that the operator is never told an endpoint can upgrade and then watches it
   fail. Those two rules together mean the https requirement belongs in the
   predicate. It is added as precondition 4.
2. **Opting out is recorded by a marker file,
   `/etc/borg-ui-agent/no-remote-upgrade`.** The spec says a reinstall
   preserves the existing choice unless `--no-remote-upgrade` is given again,
   but does not say how the choice is recorded. Absence of the four artifacts
   cannot mean "opted out", because an endpoint installed before this phase
   also has none of them and must gain remote upgrade on its next reinstall.
   An explicit marker separates the two cases.

## File structure

| File | Change | Responsibility |
| --- | --- | --- |
| `app/api/agent_installer.py` | Modify | `--no-remote-upgrade` parsing, the four artifacts, the opt-out marker, and the new `install.sh.sha256` route |
| `agent/borg_ui_agent/self_upgrade.py` | Create | The single precondition predicate and the parsed `upgrade.conf` |
| `agent/borg_ui_agent/runtime.py` | Modify | `get_capabilities()` appends `self_upgrade` when the predicate holds |
| `tests/unit/test_agent_installer_api.py` | Modify | Installer packaging guards |
| `tests/unit/test_agent_upgrade_helper.py` | Create | The helper script's transport and integrity behavior, run as real bash |
| `tests/unit/test_agent_self_upgrade.py` | Create | The precondition predicate and capability detection |
| `frontend/src/pages/managed-agents/AgentManualUpgradeChip.tsx` | Create | "Manual upgrades only" chip |
| `frontend/src/pages/ManagedAgents.tsx` | Modify | Render the chip in the version cell |
| `frontend/src/pages/managed-agents/AgentManualUpgradeChip.stories.tsx` | Create | Story |
| `frontend/src/pages/__tests__/ManagedAgents.test.tsx` | Modify | Chip shows only when `self_upgrade_supported` is false |
| `frontend/src/locales/{en,de,es,it}.json` | Modify | Chip label and tooltip |
| `docs/managed-agents.md` | Modify | What the helper grants and how to decline it |

---

### Task 1: Publish a SHA256 for the served installer

The helper runs the script it downloads as root, so it verifies the download
against a checksum the server publishes (spec section 6, "Transport and
integrity"). The route is new server surface; the helper in Task 4 depends on
it existing.

**Files:**
- Modify: `app/api/agent_installer.py` (add route after `get_agent_installer`)
- Test: `tests/unit/test_agent_installer_api.py`

**Interfaces:**
- Consumes: `render_installer_script()`, already in the module.
- Produces: `GET /agent/install.sh.sha256` returning `text/plain`, body is the
  lowercase hex SHA256 of exactly the bytes `GET /agent/install.sh` returns,
  followed by a newline.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_agent_installer_api.py`:

```python
def test_the_served_installer_publishes_its_own_checksum(test_client: TestClient):
    script = test_client.get("/agent/install.sh")
    checksum = test_client.get("/agent/install.sh.sha256")

    assert checksum.status_code == 200
    assert checksum.headers["content-type"].startswith("text/plain")

    expected = hashlib.sha256(script.content).hexdigest()
    assert checksum.text.strip() == expected
    # The helper compares against this after downloading, so a checksum that
    # covered anything but the exact served bytes would abort every upgrade.
    assert checksum.text.strip() == checksum.text.strip().lower()
```

Add `import hashlib` to the imports at the top of the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_installer_api.py::test_the_served_installer_publishes_its_own_checksum -v`
Expected: FAIL with a 404 from the missing route.

- [ ] **Step 3: Write minimal implementation**

Add `import hashlib` at the top of `app/api/agent_installer.py`, then add
after `get_agent_installer`:

```python
@router.get("/agent/install.sh.sha256")
async def get_agent_installer_checksum() -> Response:
    """The SHA256 of the script this server serves at /agent/install.sh.

    The self-upgrade helper runs the downloaded script as root, so it verifies
    the download against this before executing anything. Rendered through the
    same function as the script itself, so the two cannot drift.
    """
    script = await asyncio.to_thread(render_installer_script)
    digest = hashlib.sha256(script.encode("utf-8")).hexdigest()
    return Response(content=f"{digest}\n", media_type="text/plain")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_installer_api.py -v`
Expected: PASS, and the existing installer tests stay green.

- [ ] **Step 5: Commit**

```bash
git add app/api/agent_installer.py tests/unit/test_agent_installer_api.py
git commit -m "feat(agents): publish a checksum for the installer the server serves

The self-upgrade helper runs the script it downloads as root, so it needs a
published digest to verify against before executing anything. Rendered through
render_installer_script so the checksum cannot drift from the script."
```

---

### Task 2: The `--no-remote-upgrade` opt-out and its marker

Remote upgrade is installed by default (spec D8). This task adds the flag, the
marker file that records the choice, and the reinstall preservation. It writes
none of the four artifacts yet: it establishes the variable every later task
branches on.

**Files:**
- Modify: `app/api/agent_installer.py` (`INSTALLER_SCRIPT`: defaults block,
  usage text, argument parser, and a new resolution block)
- Test: `tests/unit/test_agent_installer_api.py`

**Interfaces:**
- Produces: shell variable `REMOTE_UPGRADE` in the installer, `"1"` or `"0"`,
  resolved before any artifact is written. Marker file
  `/etc/borg-ui-agent/no-remote-upgrade`.

- [ ] **Step 1: Write the failing test**

```python
def test_agent_installer_supports_declining_remote_upgrade(test_client: TestClient):
    script = test_client.get("/agent/install.sh").text

    assert "--no-remote-upgrade" in script
    assert 'REMOTE_UPGRADE="1"' in script
    assert "/etc/borg-ui-agent/no-remote-upgrade" in script


def test_agent_installer_reinstall_preserves_a_declined_remote_upgrade(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    # The marker is what separates "this operator declined" from "this endpoint
    # was installed before remote upgrade existed". Absence must mean the
    # second, so a pre-existing endpoint gains the helper on its next
    # reinstall rather than being locked out of it forever.
    assert 'if [[ "${REMOTE_UPGRADE_SET}" == "0" && -e "${NO_REMOTE_UPGRADE_MARKER}" ]]' in (
        script
    )
    assert 'REMOTE_UPGRADE="0"' in script
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_installer_api.py -k remote_upgrade -v`
Expected: FAIL, both, on the missing strings.

- [ ] **Step 3: Write minimal implementation**

In `INSTALLER_SCRIPT`, add to the defaults block next to `SERVICE_USER_MODE_SET`:

```bash
REMOTE_UPGRADE="1"
REMOTE_UPGRADE_SET="0"
NO_REMOTE_UPGRADE_MARKER="/etc/borg-ui-agent/no-remote-upgrade"
```

Add to the `usage()` heredoc, after the `--skip-borg-install` line in the
"Borg install options" block, a new block:

```text
Remote upgrade options:
  --no-remote-upgrade   Do not install the privileged self-upgrade helper. The
                        endpoint can then only be updated by running this
                        installer on the machine with --reinstall. A reinstall
                        remembers this choice; pass --remote-upgrade to undo it.
```

Add to the argument parser, next to `--skip-borg-install`:

```bash
    --no-remote-upgrade)
      REMOTE_UPGRADE="0"
      REMOTE_UPGRADE_SET="1"
      shift
      ;;
    --remote-upgrade)
      REMOTE_UPGRADE="1"
      REMOTE_UPGRADE_SET="1"
      shift
      ;;
```

Add the resolution block immediately after the existing reinstall
service-user preservation block (the one ending
`echo "Reinstall: preserving existing service user ..."`):

```bash
# A reinstall keeps the operator's earlier answer about remote upgrade unless
# this run gives one explicitly. The marker records a decline; its absence
# means "never asked", which is also what an endpoint installed before remote
# upgrade existed looks like, and that endpoint should gain the helper here.
if [[ "${REMOTE_UPGRADE_SET}" == "0" && -e "${NO_REMOTE_UPGRADE_MARKER}" ]]; then
  REMOTE_UPGRADE="0"
  echo "Reinstall: remote upgrade stays declined (${NO_REMOTE_UPGRADE_MARKER} exists)."
fi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_installer_api.py -v`
Expected: PASS, including `..._is_valid_bash` and the shellcheck test.

- [ ] **Step 5: Commit**

```bash
git add app/api/agent_installer.py tests/unit/test_agent_installer_api.py
git commit -m "feat(agents): let an operator decline the remote upgrade helper

--no-remote-upgrade keeps an endpoint on the manual reinstall path. A marker
file records the choice so a later reinstall preserves it, while an endpoint
that predates the helper still gains it."
```

---

### Task 3: Write `upgrade.conf`

The root-owned file holding every parameter the helper needs. Written after
registration, because it records the endpoint's `agent_id`, which only exists
in `config.toml` once the machine is enrolled.

**Files:**
- Modify: `app/api/agent_installer.py` (`INSTALLER_SCRIPT`, a new
  `write_remote_upgrade_artifacts` function called after the
  `borg-ui-agent.service` heredoc and before `systemctl daemon-reload`)
- Test: `tests/unit/test_agent_installer_api.py`

**Interfaces:**
- Produces: `/etc/borg-ui-agent/upgrade.conf`, mode `0644`, owner `root:root`,
  shell `KEY="value"` lines, keys: `SERVER`, `AGENT_ID`, `BORG_INSTALL_MODE`,
  `SERVICE_USER_MODE`, `SERVICE_USER`, `SERVICE_GROUP`, `AGENT_ROOT`,
  `SYSTEMCTL`. Task 4's helper and Task 6's predicate both read these names.

- [ ] **Step 1: Write the failing test**

```python
def test_agent_installer_records_the_upgrade_parameters_as_root(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    assert "/etc/borg-ui-agent/upgrade.conf" in script
    # Root-owned and not writable by the service user: the agent must not be
    # able to repoint its own upgrade at another host (spec section 11.2).
    assert 'install -o root -g root -m 0644 ' in script
    for key in (
        "SERVER",
        "AGENT_ID",
        "BORG_INSTALL_MODE",
        "SERVICE_USER_MODE",
        "SERVICE_USER",
        "SERVICE_GROUP",
        "AGENT_ROOT",
        "SYSTEMCTL",
    ):
        assert f'{key}="' in script


def test_agent_installer_resolves_systemctl_by_absolute_path(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    # sudoers matches on the absolute path and it differs across
    # distributions, so it is resolved once and reused in both the rule and
    # upgrade.conf rather than hardcoded.
    assert 'SYSTEMCTL_PATH="$(command -v systemctl' in script
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_installer_api.py -k upgrade_parameters -v`
Expected: FAIL on the missing path.

- [ ] **Step 3: Write minimal implementation**

In `INSTALLER_SCRIPT`, immediately after the `borg-ui-agent.service` heredoc
and before the `service-check` invocation, add:

```bash
# Everything the self-upgrade helper needs, in a file only root can write.
# The helper takes no arguments and reads only this, so a compromised agent
# cannot redirect the install source, change the service user, or inject
# installer flags. That is what makes the sudoers rule in write_upgrade_sudoers
# safe to grant.
write_upgrade_conf() {
  local agent_id borg_install_mode

  agent_id="$(sed -nE 's/^agent_id[[:space:]]*=[[:space:]]*"(.*)"[[:space:]]*$/\1/p' \
    /etc/borg-ui-agent/config.toml | head -n 1)"
  if [[ -z "${agent_id}" ]]; then
    echo "Could not read agent_id from /etc/borg-ui-agent/config.toml;" >&2
    echo "skipping remote upgrade setup. This endpoint stays on the manual" >&2
    echo "reinstall path." >&2
    return 1
  fi

  if [[ "${SKIP_BORG_INSTALL}" == "1" ]]; then
    borg_install_mode="skip"
  else
    borg_install_mode="${BORG_VERSION}"
  fi

  install -o root -g root -m 0644 /dev/null "${UPGRADE_CONF}"
  cat >"${UPGRADE_CONF}" <<CONF
# Written by the Borg UI agent installer. Read by
# ${AGENT_ROOT}/bin/borg-ui-agent-upgrade, which takes no arguments.
SERVER="${SERVER%/}"
AGENT_ID="${agent_id}"
BORG_INSTALL_MODE="${borg_install_mode}"
SERVICE_USER_MODE="${SERVICE_USER_MODE}"
SERVICE_USER="${SERVICE_USER}"
SERVICE_GROUP="${SERVICE_GROUP}"
AGENT_ROOT="${AGENT_ROOT}"
SYSTEMCTL="${SYSTEMCTL_PATH}"
CONF
}
```

Add to the defaults block at the top of the script:

```bash
UPGRADE_CONF="/etc/borg-ui-agent/upgrade.conf"
SYSTEMCTL_PATH=""
```

The other three paths (`UPGRADE_UNIT`, `UPGRADE_HELPER`, `UPGRADE_SUDOERS`)
are added in the tasks that first use them. Declaring them here would trip
shellcheck's `SC2034` (assigned but never used), which the severity-warning
test treats as a failure.

And resolve `SYSTEMCTL_PATH` just before the call site, after the
distribution check that guarantees a systemd host:

```bash
SYSTEMCTL_PATH="$(command -v systemctl || true)"
```

Then call it, guarded, after the unit heredoc:

```bash
if [[ "${REMOTE_UPGRADE}" == "1" ]]; then
  write_upgrade_conf || true
fi
```

`|| true` because a missing `agent_id` must leave the endpoint on the manual
path rather than failing an otherwise good install; the function already said
so on stderr.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_installer_api.py -v`
Expected: PASS, including the `bash -n` and shellcheck tests.

- [ ] **Step 5: Commit**

```bash
git add app/api/agent_installer.py tests/unit/test_agent_installer_api.py
git commit -m "feat(agents): record the reinstall parameters in a root-owned upgrade.conf

The self-upgrade helper takes no arguments and reads every parameter from this
file, so a compromised agent cannot influence what gets installed or from
where. Written after registration because it records the endpoint's agent_id."
```

---

### Task 4: The helper script

The one thing that runs as root. It takes no arguments, refuses a server URL
it does not trust, verifies what it downloads, and only then reinstalls.

**Files:**
- Modify: `app/api/agent_installer.py` (`INSTALLER_SCRIPT`, a
  `write_upgrade_helper` function next to `write_upgrade_conf`)
- Test: `tests/unit/test_agent_upgrade_helper.py` (create)

**Interfaces:**
- Consumes: `upgrade.conf` keys from Task 3; `GET /agent/install.sh.sha256`
  from Task 1.
- Produces: `/opt/borg-ui-agent/bin/borg-ui-agent-upgrade`, mode `0755`, owner
  `root:root`, in the root-owned `${AGENT_ROOT}/bin`.

The test extracts the helper body out of the served installer and runs it as
real bash against a fake `upgrade.conf`, with `curl`, `sha256sum` and `bash`
stubbed on `PATH`. Asserting on strings alone would not catch a helper that
parses but does the wrong thing with a redirect or a bad digest.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_agent_upgrade_helper.py`:

```python
"""The self-upgrade helper runs as root, so its refusals are executed, not read.

Each test extracts the helper exactly as the installer would write it, then
runs it with a fake upgrade.conf and stub binaries on PATH.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HELPER_BEGIN = "cat >\"${UPGRADE_HELPER}\" <<'UPGRADE_HELPER'\n"
HELPER_END = "\nUPGRADE_HELPER\n"


def extract_helper(script: str) -> str:
    body = script.split(HELPER_BEGIN, 1)[1].split(HELPER_END, 1)[0]
    assert body.startswith("#!/usr/bin/env bash"), body[:80]
    return body


@pytest.fixture
def helper_env(tmp_path: Path, test_client: TestClient):
    """A helper on disk plus the knobs each test varies."""
    script = test_client.get("/agent/install.sh").text
    helper = tmp_path / "borg-ui-agent-upgrade"
    helper.write_text(extract_helper(script), encoding="utf-8")
    helper.chmod(0o755)

    etc = tmp_path / "etc"
    etc.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    def write_conf(server: str = "https://borg.example:8083") -> None:
        (etc / "upgrade.conf").write_text(
            "\n".join(
                [
                    f'SERVER="{server}"',
                    'AGENT_ID="agent-1"',
                    'BORG_INSTALL_MODE="skip"',
                    'SERVICE_USER_MODE="current"',
                    'SERVICE_USER="borg"',
                    'SERVICE_GROUP="borg"',
                    'AGENT_ROOT="/opt/borg-ui-agent"',
                    'SYSTEMCTL="/usr/bin/systemctl"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (etc / "config.toml").write_text(
            f'server_url = "{server}"\nagent_id = "agent-1"\n', encoding="utf-8"
        )

    def stub(name: str, body: str) -> None:
        path = bin_dir / name
        path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
        path.chmod(0o755)

    def run() -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        env["BORG_UI_UPGRADE_ETC"] = str(etc)
        # /bin/bash, not "bash": one test stubs bash on PATH to capture the
        # reinstall argv, and resolving the interpreter through PATH would run
        # that stub instead of the helper.
        return subprocess.run(
            ["/bin/bash", str(helper)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    write_conf()
    # A cooperative default: the script downloads, the digest matches, and the
    # reinstall records its argv. Each test overrides what it is about.
    stub("sha256sum", 'echo "deadbeef  $1"')
    stub(
        "curl",
        'out=""\n'
        'while [[ $# -gt 0 ]]; do\n'
        '  if [[ "$1" == "-o" ]]; then out="$2"; shift 2; continue; fi\n'
        '  url="$1"; shift\n'
        'done\n'
        'if [[ "${url}" == *.sha256* ]]; then echo "deadbeef" >"${out}";\n'
        'else echo "#!/bin/sh" >"${out}"; fi\n'
        f'echo "${{url}}" >>"{tmp_path}/curl.log"',
    )

    return {
        "run": run,
        "stub": stub,
        "write_conf": write_conf,
        "tmp_path": tmp_path,
        "etc": etc,
    }


def test_the_helper_refuses_a_non_https_server(helper_env):
    helper_env["write_conf"](server="http://borg.example:8083")

    result = helper_env["run"]()

    assert result.returncode != 0
    assert "https" in result.stderr
    assert not (helper_env["tmp_path"] / "curl.log").exists()


def test_the_helper_refuses_a_server_the_agent_is_not_enrolled_against(helper_env):
    (helper_env["etc"] / "config.toml").write_text(
        'server_url = "https://other.example"\nagent_id = "agent-1"\n',
        encoding="utf-8",
    )

    result = helper_env["run"]()

    assert result.returncode != 0
    assert "enrolled" in result.stderr
    assert not (helper_env["tmp_path"] / "curl.log").exists()


def test_the_helper_executes_nothing_when_the_digest_does_not_match(helper_env):
    helper_env["stub"]("sha256sum", 'echo "notthedigest  $1"')

    result = helper_env["run"]()

    assert result.returncode != 0
    assert "checksum" in result.stderr.lower()


def test_the_helper_never_follows_a_redirect_and_never_downgrades(helper_env):
    helper_env["run"]()

    recorded = (helper_env["tmp_path"] / "curl.log").read_text()
    assert "https://borg.example:8083/agent/install.sh" in recorded
    helper = (helper_env["tmp_path"] / "borg-ui-agent-upgrade").read_text()
    assert "--proto '=https'" in helper
    assert "--max-redirs 0" in helper
    assert "--insecure" not in helper
    assert "--location-trusted" not in helper


def test_the_helper_reinstalls_with_the_recorded_parameters(helper_env):
    helper_env["stub"](
        "bash",
        f'echo "$@" >>"{helper_env["tmp_path"]}/reinstall.log"',
    )

    result = helper_env["run"]()

    assert result.returncode == 0, result.stderr
    argv = (helper_env["tmp_path"] / "reinstall.log").read_text()
    assert "--reinstall" in argv
    assert "--skip-borg-install" in argv
    assert "--service-user borg" in argv


@pytest.mark.skipif(
    shutil.which("shellcheck") is None, reason="shellcheck is not installed"
)
def test_the_helper_passes_shellcheck(tmp_path: Path, test_client: TestClient):
    helper = extract_helper(test_client.get("/agent/install.sh").text)

    result = subprocess.run(
        ["shellcheck", "--shell=bash", "--severity=warning", "-"],
        input=helper,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_upgrade_helper.py -v`
Expected: FAIL in `extract_helper`, on the missing heredoc marker.

- [ ] **Step 3: Write minimal implementation**

Add to the defaults block, next to `UPGRADE_CONF`:

```bash
UPGRADE_HELPER="${AGENT_ROOT}/bin/borg-ui-agent-upgrade"
```

Add `write_upgrade_helper` next to `write_upgrade_conf` in `INSTALLER_SCRIPT`.
The heredoc delimiter is quoted, so the body is literal.

`BORG_UI_UPGRADE_ETC` exists so the tests can run the helper without root and
without touching the real `/etc`; it defaults to `/etc/borg-ui-agent`, which
is what runs in production.

```bash
write_upgrade_helper() {
  install -d -o root -g root -m 0755 "${AGENT_ROOT}/bin"
  cat >"${UPGRADE_HELPER}" <<'UPGRADE_HELPER'
#!/usr/bin/env bash
# Installed by the Borg UI agent installer. Started as root by
# borg-ui-agent-upgrade.service, which the agent may start through one narrow
# sudoers rule.
#
# It takes NO ARGUMENTS on purpose. Every parameter comes from upgrade.conf,
# which only root can write, so a compromised agent cannot change the install
# source, the service user, or the installer flags. Adding an argument here
# would undo that.
set -euo pipefail

etc="${BORG_UI_UPGRADE_ETC:-/etc/borg-ui-agent}"
conf="${etc}/upgrade.conf"
agent_config="${etc}/config.toml"

if [[ ! -r "${conf}" ]]; then
  echo "Missing ${conf}; nothing to upgrade from." >&2
  exit 1
fi

# shellcheck source=/dev/null
. "${conf}"

for required in SERVER AGENT_ID BORG_INSTALL_MODE SERVICE_USER AGENT_ROOT; do
  if [[ -z "${!required:-}" ]]; then
    echo "${conf} is missing ${required}." >&2
    exit 1
  fi
done

# This script runs what it downloads, as root. An http URL is refused rather
# than downgraded to a warning.
if [[ "${SERVER}" != https://* ]]; then
  echo "Remote upgrade requires an https server URL; ${conf} names ${SERVER}." >&2
  exit 1
fi

# A config left behind by an earlier enrollment must not be able to point a
# live agent's upgrade at a host it no longer talks to.
enrolled_server=""
if [[ -r "${agent_config}" ]]; then
  enrolled_server="$(sed -nE 's/^server_url[[:space:]]*=[[:space:]]*"(.*)"[[:space:]]*$/\1/p' \
    "${agent_config}" | head -n 1)"
fi
if [[ "${enrolled_server%/}" != "${SERVER%/}" ]]; then
  echo "${conf} names ${SERVER}, but this agent is enrolled against" >&2
  echo "'${enrolled_server}'. Refusing to upgrade." >&2
  exit 1
fi

workdir="$(mktemp -d)"
trap 'rm -rf "${workdir}"' EXIT

# --proto '=https' holds across redirects, and --max-redirs 0 means there are
# none to hold across: any redirect is an error rather than a hop to somewhere
# this script would then execute.
fetch() {
  curl -fsS --proto '=https' --max-redirs 0 -o "$2" "$1"
}

script_url="${SERVER%/}/agent/install.sh?agent_id=${AGENT_ID}"
fetch "${script_url}" "${workdir}/install.sh"
fetch "${script_url/install.sh?/install.sh.sha256?}" "${workdir}/install.sh.sha256"

expected="$(tr -d '[:space:]' <"${workdir}/install.sh.sha256")"
actual="$(sha256sum "${workdir}/install.sh" | awk '{print $1}')"
if [[ -z "${expected}" || "${expected}" != "${actual}" ]]; then
  echo "Installer checksum mismatch; expected '${expected}', got '${actual}'." >&2
  echo "Nothing was executed." >&2
  exit 1
fi

args=(--reinstall --service-user "${SERVICE_USER}")
if [[ "${BORG_INSTALL_MODE}" == "skip" ]]; then
  args+=(--skip-borg-install)
else
  args+=(--borg-version "${BORG_INSTALL_MODE}")
fi

echo "Reinstalling the Borg UI agent from ${SERVER}."
bash "${workdir}/install.sh" "${args[@]}"
UPGRADE_HELPER
  chown root:root "${UPGRADE_HELPER}"
  chmod 0755 "${UPGRADE_HELPER}"
}
```

Extend the guarded call site from Task 3:

```bash
if [[ "${REMOTE_UPGRADE}" == "1" ]] && write_upgrade_conf; then
  write_upgrade_helper
fi
```

(Replacing the `write_upgrade_conf || true` form: a missing `agent_id` should
skip the helper too, not install one that cannot work.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_upgrade_helper.py tests/unit/test_agent_installer_api.py -v`
Expected: PASS, including both shellcheck tests.

- [ ] **Step 5: Commit**

```bash
git add app/api/agent_installer.py tests/unit/test_agent_upgrade_helper.py
git commit -m "feat(agents): install the root helper that reinstalls the agent

The helper takes no arguments and reads every parameter from root-owned
upgrade.conf. It refuses a non-https server, refuses a server the agent is not
enrolled against, and verifies the downloaded installer against the checksum
the server publishes before executing anything."
```

---

### Task 5: The oneshot unit and the sudoers rule

The unit is what lets the reinstall survive the restart it performs, because
it runs outside the agent's process tree. The sudoers rule is the escalation,
and it is skipped for a root agent, which needs none (spec D10).

**Files:**
- Modify: `app/api/agent_installer.py` (`INSTALLER_SCRIPT`)
- Test: `tests/unit/test_agent_installer_api.py`

**Interfaces:**
- Produces: `/etc/systemd/system/borg-ui-agent-upgrade.service` (`Type=oneshot`,
  `ExecStart=${AGENT_ROOT}/bin/borg-ui-agent-upgrade`, not enabled) and
  `/etc/sudoers.d/borg-ui-agent-upgrade` (mode `0440`). Task 6's predicate
  reads the unit path; phase 3's session command invokes the exact argv the
  sudoers rule names.

- [ ] **Step 1: Write the failing test**

```python
def test_agent_installer_writes_a_oneshot_unit_for_the_upgrade(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    assert "/etc/systemd/system/borg-ui-agent-upgrade.service" in script
    assert "Type=oneshot" in script
    assert "ExecStart=${AGENT_ROOT}/bin/borg-ui-agent-upgrade" in script
    # Never enabled: it runs only when something starts it. And the reinstall
    # restarts borg-ui-agent, so it has to live outside that unit's process
    # tree or systemd would kill the upgrade halfway through.
    assert "systemctl enable borg-ui-agent-upgrade" not in script


def test_agent_installer_grants_one_validated_sudoers_command(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    assert (
        '${SERVICE_USER} ALL=(root) NOPASSWD: '
        '${SYSTEMCTL_PATH} start --no-block borg-ui-agent-upgrade.service'
    ) in script
    assert "visudo -cf" in script
    assert "install -o root -g root -m 0440" in script


def test_agent_installer_skips_the_sudoers_rule_for_a_root_agent(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    # A root agent can already start the unit, so it gets the unit, the helper
    # and upgrade.conf but no escalation. Skipping the whole set for root would
    # leave root endpoints with no upgrade path at all (spec D10).
    sudoers_block = script.split("write_upgrade_sudoers() {", 1)[1].split("\n}", 1)[0]
    assert 'if [[ "${SERVICE_USER}" == "root" ]]' in sudoers_block
    assert "return 0" in sudoers_block


def test_agent_installer_removes_the_upgrade_artifacts_when_declined(
    test_client: TestClient,
):
    script = test_client.get("/agent/install.sh").text

    # A reinstall with --no-remote-upgrade on an endpoint that has the helper
    # must take it away, not leave a live escalation behind.
    removal = script.split("remove_upgrade_artifacts() {", 1)[1].split("\n}", 1)[0]
    for path in ("UPGRADE_SUDOERS", "UPGRADE_UNIT", "UPGRADE_HELPER", "UPGRADE_CONF"):
        assert f'"${{{path}}}"' in removal
    assert "NO_REMOTE_UPGRADE_MARKER" in script
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_installer_api.py -k upgrade -v`
Expected: FAIL on the missing unit and sudoers strings.

- [ ] **Step 3: Write minimal implementation**

Add to the defaults block, next to `UPGRADE_CONF` and `UPGRADE_HELPER`:

```bash
UPGRADE_UNIT="/etc/systemd/system/borg-ui-agent-upgrade.service"
UPGRADE_SUDOERS="/etc/sudoers.d/borg-ui-agent-upgrade"
```

Add next to the other `write_upgrade_*` functions:

```bash
write_upgrade_unit() {
  cat >"${UPGRADE_UNIT}" <<UPGRADE_UNIT_FILE
[Unit]
Description=Borg UI agent self-upgrade
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=${AGENT_ROOT}/bin/borg-ui-agent-upgrade
UPGRADE_UNIT_FILE
  chown root:root "${UPGRADE_UNIT}"
  chmod 0644 "${UPGRADE_UNIT}"
}

# The escalation. It is one command with no caller-supplied input, which is the
# only reason it is safe to grant: the helper it starts reads its parameters
# from root-owned upgrade.conf, so the agent cannot influence what runs.
#
# A root agent already starts units, so it gets no rule at all.
write_upgrade_sudoers() {
  local staged

  if [[ "${SERVICE_USER}" == "root" ]]; then
    rm -f "${UPGRADE_SUDOERS}"
    return 0
  fi

  if [[ -z "${SYSTEMCTL_PATH}" ]]; then
    echo "Could not resolve an absolute systemctl path; skipping the sudoers" >&2
    echo "rule. This endpoint stays on the manual reinstall path." >&2
    return 1
  fi

  staged="$(mktemp)"
  cat >"${staged}" <<SUDOERS
# Installed by the Borg UI agent installer. Lets the agent ask systemd to run
# the root self-upgrade helper, and nothing else. The helper takes no
# arguments, so this grants no input surface.
${SERVICE_USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_PATH} start --no-block borg-ui-agent-upgrade.service
SUDOERS

  # Never move an unvalidated file into sudoers.d: a broken one can lock every
  # sudo user out of the machine.
  if ! visudo -cf "${staged}" >/dev/null; then
    rm -f "${staged}"
    echo "Generated sudoers rule failed validation; not installing it." >&2
    echo "This endpoint stays on the manual reinstall path." >&2
    return 1
  fi

  install -o root -g root -m 0440 "${staged}" "${UPGRADE_SUDOERS}"
  rm -f "${staged}"
}

remove_upgrade_artifacts() {
  rm -f "${UPGRADE_SUDOERS}" "${UPGRADE_UNIT}" "${UPGRADE_HELPER}" "${UPGRADE_CONF}"
}
```

Replace the guarded call site with the full block, placed after the
`borg-ui-agent.service` heredoc and before `systemctl daemon-reload` so the
reload picks up both units at once:

```bash
if [[ "${REMOTE_UPGRADE}" == "1" ]] && write_upgrade_conf; then
  write_upgrade_helper
  write_upgrade_unit
  if write_upgrade_sudoers; then
    rm -f "${NO_REMOTE_UPGRADE_MARKER}"
    echo "Remote upgrade is available on this endpoint."
  else
    remove_upgrade_artifacts
  fi
else
  remove_upgrade_artifacts
  if [[ "${REMOTE_UPGRADE}" == "0" ]]; then
    install -o root -g root -m 0644 /dev/null "${NO_REMOTE_UPGRADE_MARKER}"
    echo "Remote upgrade declined. Update this endpoint with --reinstall."
  fi
fi
```

A `visudo` failure does not abort an otherwise good install. It takes the
unit, helper and `upgrade.conf` back out instead, because without the sudoers
rule the agent cannot reach them, and the endpoint then reports no
`self_upgrade` because Task 6's predicate consults `sudo -l`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_installer_api.py tests/unit/test_agent_upgrade_helper.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/agent_installer.py tests/unit/test_agent_installer_api.py
git commit -m "feat(agents): add the oneshot upgrade unit and its narrow sudoers rule

The unit runs the helper outside the agent's process tree, so the reinstall
survives restarting the agent. The sudoers rule names one absolute command,
is validated with visudo before installation, and is skipped for a root agent,
which already starts units. Declining removes all four artifacts."
```

---

### Task 6: The precondition predicate and capability detection

One predicate decides both whether the agent advertises `self_upgrade` and
(in phase 3) whether `agent.upgrade` will run. Splitting it is what would let
the two diverge and produce an upgrade that starts and dies after the operator
was told it would work.

**Files:**
- Create: `agent/borg_ui_agent/self_upgrade.py`
- Modify: `agent/borg_ui_agent/runtime.py` (`get_capabilities`)
- Test: `tests/unit/test_agent_self_upgrade.py` (create)

**Interfaces:**
- Produces:
  ```python
  UPGRADE_UNIT_NAME = "borg-ui-agent-upgrade.service"

  @dataclass(frozen=True)
  class UpgradeReadiness:
      supported: bool
      reason: str = ""        # "" when supported, else a short machine-readable cause
      systemctl: str = ""     # absolute path from upgrade.conf
      needs_sudo: bool = True

  def check_self_upgrade(
      *,
      etc_dir: Path = Path("/etc/borg-ui-agent"),
      unit_path: Path = Path("/etc/systemd/system/borg-ui-agent-upgrade.service"),
      is_root: Callable[[], bool] = lambda: os.geteuid() == 0,
      sudo_lists: Callable[[str], bool] = _sudo_lists_upgrade_command,
  ) -> UpgradeReadiness: ...

  def can_self_upgrade() -> bool: ...
  ```
  Phase 3 calls `check_self_upgrade()` again from the `agent.upgrade` handler
  and uses `systemctl` and `needs_sudo` to build its argv. Do not add the
  handler here.
- Consumes: `upgrade.conf` keys `SERVER`, `AGENT_ID`, `SYSTEMCTL` from Task 3;
  the unit from Task 5.

Reasons, in the order checked: `unit_missing`, `helper_missing`,
`conf_missing`, `server_not_https`, `sudo_not_permitted`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_agent_self_upgrade.py`:

```python
"""One predicate decides both the capability and (in phase 3) the command.

Each precondition is tested failing on its own, because a partial install can
leave any one piece behind without the others, and each would otherwise fail at
a different point after the operator was told the endpoint can upgrade itself.
"""

from pathlib import Path

import pytest

from agent.borg_ui_agent.runtime import get_capabilities
from agent.borg_ui_agent.self_upgrade import check_self_upgrade


@pytest.fixture
def ready(tmp_path: Path):
    """A complete, correct install. Each test breaks exactly one thing."""
    etc = tmp_path / "etc"
    etc.mkdir()
    helper = tmp_path / "opt" / "bin" / "borg-ui-agent-upgrade"
    helper.parent.mkdir(parents=True)
    helper.write_text("#!/bin/sh\n", encoding="utf-8")
    helper.chmod(0o755)
    (etc / "upgrade.conf").write_text(
        "\n".join(
            [
                'SERVER="https://borg.example"',
                'AGENT_ID="agent-1"',
                f'AGENT_ROOT="{helper.parent.parent}"',
                'SYSTEMCTL="/usr/bin/systemctl"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    unit = tmp_path / "borg-ui-agent-upgrade.service"
    unit.write_text(f"[Service]\nExecStart={helper}\n", encoding="utf-8")

    return {
        "etc_dir": etc,
        "unit_path": unit,
        "is_root": lambda: False,
        "sudo_lists": lambda systemctl: True,
    }


def test_a_complete_install_can_upgrade_itself(ready):
    readiness = check_self_upgrade(**ready)

    assert readiness.supported is True
    assert readiness.reason == ""
    assert readiness.systemctl == "/usr/bin/systemctl"
    assert readiness.needs_sudo is True


def test_a_missing_unit_is_reported_as_such(ready):
    ready["unit_path"].unlink()

    assert check_self_upgrade(**ready).reason == "unit_missing"


def test_a_missing_helper_is_reported_as_such(ready):
    helper = Path(ready["unit_path"].read_text().split("ExecStart=", 1)[1].strip())
    helper.unlink()

    assert check_self_upgrade(**ready).reason == "helper_missing"


def test_a_helper_that_is_not_executable_is_reported_as_missing(ready):
    helper = Path(ready["unit_path"].read_text().split("ExecStart=", 1)[1].strip())
    helper.chmod(0o644)

    assert check_self_upgrade(**ready).reason == "helper_missing"


def test_a_missing_upgrade_conf_is_reported_as_such(ready):
    (ready["etc_dir"] / "upgrade.conf").unlink()

    assert check_self_upgrade(**ready).reason == "conf_missing"


@pytest.mark.parametrize("dropped", ["SERVER", "AGENT_ID", "SYSTEMCTL"])
def test_an_upgrade_conf_short_a_required_field_is_reported_as_missing(ready, dropped):
    conf = ready["etc_dir"] / "upgrade.conf"
    kept = [
        line
        for line in conf.read_text().splitlines()
        if not line.startswith(f"{dropped}=")
    ]
    conf.write_text("\n".join(kept) + "\n", encoding="utf-8")

    assert check_self_upgrade(**ready).reason == "conf_missing"


def test_an_http_endpoint_cannot_upgrade_itself(ready):
    conf = ready["etc_dir"] / "upgrade.conf"
    conf.write_text(
        conf.read_text().replace("https://borg.example", "http://borg.example"),
        encoding="utf-8",
    )

    # The helper refuses a non-https server, so reporting the capability here
    # would promise an upgrade that aborts as soon as it is asked for.
    assert check_self_upgrade(**ready).reason == "server_not_https"


def test_an_unprivileged_agent_without_the_sudoers_rule_reports_no_capability(ready):
    ready["sudo_lists"] = lambda systemctl: False

    assert check_self_upgrade(**ready).reason == "sudo_not_permitted"


def test_a_root_agent_needs_no_sudoers_rule(ready):
    # The installer writes no sudoers file for a root agent, and does not
    # install sudo, so consulting sudo -l would report no capability on exactly
    # the endpoints that need none.
    ready["is_root"] = lambda: True
    ready["sudo_lists"] = lambda systemctl: pytest.fail("sudo must not be consulted")

    readiness = check_self_upgrade(**ready)

    assert readiness.supported is True
    assert readiness.needs_sudo is False


def test_capabilities_include_self_upgrade_only_when_the_endpoint_is_ready(
    monkeypatch,
):
    monkeypatch.setattr(
        "agent.borg_ui_agent.runtime.can_self_upgrade", lambda: False
    )
    assert "self_upgrade" not in get_capabilities()

    monkeypatch.setattr(
        "agent.borg_ui_agent.runtime.can_self_upgrade", lambda: True
    )
    assert "self_upgrade" in get_capabilities()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_self_upgrade.py -v`
Expected: FAIL at import, `No module named agent.borg_ui_agent.self_upgrade`.

- [ ] **Step 3: Write minimal implementation**

Create `agent/borg_ui_agent/self_upgrade.py`:

```python
"""Whether this endpoint can reinstall itself when the server asks.

One predicate answers this, and both the capability report and the
`agent.upgrade` handler call it. A partial or half-removed install can leave
any one piece behind without the others, and each missing piece would
otherwise fail at a different point, after the operator has already been told
the endpoint can upgrade itself.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

UPGRADE_UNIT_NAME = "borg-ui-agent-upgrade.service"
DEFAULT_ETC_DIR = Path("/etc/borg-ui-agent")
DEFAULT_UNIT_PATH = Path("/etc/systemd/system") / UPGRADE_UNIT_NAME
REQUIRED_CONF_KEYS = ("SERVER", "AGENT_ID", "SYSTEMCTL")

_CONF_LINE = re.compile(r'^\s*([A-Z_]+)\s*=\s*"(.*)"\s*$')


@dataclass(frozen=True)
class UpgradeReadiness:
    supported: bool
    reason: str = ""
    systemctl: str = ""
    needs_sudo: bool = True


def _parse_conf(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _CONF_LINE.match(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def _exec_start(unit_path: Path) -> Optional[Path]:
    for line in unit_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("ExecStart="):
            command = line.split("=", 1)[1].strip()
            return Path(command.split()[0]) if command else None
    return None


def _sudo_lists_upgrade_command(systemctl: str) -> bool:
    """Whether sudo would let this user start the upgrade unit without a password.

    `sudo -l` on the exact command, so the answer covers the whole argv the
    handler will run rather than only the binary.
    """
    sudo = shutil.which("sudo")
    if sudo is None:
        return False
    result = subprocess.run(
        [sudo, "-n", "-l", systemctl, "start", "--no-block", UPGRADE_UNIT_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def check_self_upgrade(
    *,
    etc_dir: Path = DEFAULT_ETC_DIR,
    unit_path: Path = DEFAULT_UNIT_PATH,
    is_root: Callable[[], bool] = lambda: os.geteuid() == 0,
    sudo_lists: Callable[[str], bool] = _sudo_lists_upgrade_command,
) -> UpgradeReadiness:
    if not unit_path.is_file():
        return UpgradeReadiness(supported=False, reason="unit_missing")

    helper = _exec_start(unit_path)
    if helper is None or not helper.is_file() or not os.access(helper, os.X_OK):
        return UpgradeReadiness(supported=False, reason="helper_missing")

    conf_path = etc_dir / "upgrade.conf"
    if not conf_path.is_file():
        return UpgradeReadiness(supported=False, reason="conf_missing")

    conf = _parse_conf(conf_path)
    if any(not conf.get(key) for key in REQUIRED_CONF_KEYS):
        return UpgradeReadiness(supported=False, reason="conf_missing")

    # The helper refuses a non-https server, so an endpoint enrolled over http
    # would be told it can upgrade and then abort as soon as it was asked to.
    if not conf["SERVER"].startswith("https://"):
        return UpgradeReadiness(supported=False, reason="server_not_https")

    systemctl = conf["SYSTEMCTL"]

    # A root agent starts the unit itself. The installer writes no sudoers file
    # for it and does not install sudo, so asking sudo here would report no
    # capability on exactly the endpoints that need no escalation.
    if is_root():
        return UpgradeReadiness(supported=True, systemctl=systemctl, needs_sudo=False)

    if not sudo_lists(systemctl):
        return UpgradeReadiness(supported=False, reason="sudo_not_permitted")

    return UpgradeReadiness(supported=True, systemctl=systemctl, needs_sudo=True)


def can_self_upgrade() -> bool:
    try:
        return check_self_upgrade().supported
    except OSError:
        # An unreadable /etc or a vanished file means the endpoint cannot
        # upgrade itself. It must not mean the agent stops reporting at all.
        return False
```

In `agent/borg_ui_agent/runtime.py`, import it and gate the capability:

```python
from agent.borg_ui_agent.self_upgrade import can_self_upgrade
```

```python
def get_capabilities() -> list[str]:
    # Detected, not assumed: an agent upgraded from an install that predates
    # the helper has to report honestly so the UI routes it to the manual path.
    capabilities = list(DEFAULT_CAPABILITIES)
    if can_self_upgrade():
        capabilities.append("self_upgrade")
    return capabilities
```

Leave `self_upgrade` out of `DEFAULT_CAPABILITIES`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_self_upgrade.py tests/unit/test_agent_runtime.py -v`
Expected: PASS. `test_agent_runtime.py` asserts on `get_capabilities()`
contents in several places; those assertions are all `in` checks on other
capabilities, so they stay green.

- [ ] **Step 5: Commit**

```bash
git add agent/borg_ui_agent/self_upgrade.py agent/borg_ui_agent/runtime.py \
  tests/unit/test_agent_self_upgrade.py
git commit -m "feat(agent): report self_upgrade only when the endpoint can actually do it

One predicate decides it, and phase 3's agent.upgrade handler will call the
same one. Each precondition fails on its own with a named reason, so a partial
install reports 'cannot upgrade itself' rather than an upgrade that starts and
dies."
```

---

### Task 7: Say what the helper grants and how to decline it

**Files:**
- Modify: `docs/managed-agents.md`

- [ ] **Step 1: Add the section**

After "Reinstall or Update an Existing Agent" and before "Knowing Which Agents
Are Out of Date", add:

```markdown
## Remote Upgrade and What It Grants

New installs place four root-owned files on the endpoint so a future Borg UI
release can reinstall the agent from the server instead of you visiting the
machine:

| File | Purpose |
| --- | --- |
| `/etc/borg-ui-agent/upgrade.conf` | The reinstall parameters. Root-owned, not writable by the agent. |
| `/opt/borg-ui-agent/bin/borg-ui-agent-upgrade` | The helper. Takes no arguments and reads only `upgrade.conf`. |
| `/etc/systemd/system/borg-ui-agent-upgrade.service` | A oneshot unit that runs the helper. Never enabled. |
| `/etc/sudoers.d/borg-ui-agent-upgrade` | Lets the agent's service user start that one unit, and nothing else. Not written when the agent runs as root. |

Be clear about the trade. Before this, a compromised Borg UI server could
already run code as the agent's service user on every endpoint and read any
file on it, and it already decided which agent code the endpoint runs. With
the helper it can additionally obtain root on that endpoint: write access and
persistence. That is a real escalation, not a repackaging of existing trust.
It is bounded to the server that already controls the endpoint's agent code,
and it is what makes upgrades possible on the installer's default service user
mode rather than only on root installs.

Remote upgrade needs an `https` server URL, because the helper runs what it
downloads as root and will not fetch it over cleartext. An endpoint enrolled
against an `http` server reports no remote upgrade support and stays on the
manual path.

To decline it on a sensitive host:

```bash
curl -fsSL https://borg-ui-host:8083/agent/install.sh | sudo bash -s -- \
  --server https://borg-ui-host:8083 --token TOKEN --name NAME \
  --no-remote-upgrade
```

That endpoint keeps the manual reinstall path and reports no remote upgrade
support. A later reinstall remembers the choice; pass `--remote-upgrade` to
undo it.

Endpoints enrolled before this release have none of these files and are shown
as manual only. One reinstall with the command above gives them remote upgrade.
```

Also update the closing line of "Knowing Which Agents Are Out of Date", which
currently reads "Upgrading is still a manual reinstall on each machine in this
release.", to:

```markdown
Upgrading is still a manual reinstall on each machine in this release. New
installs now carry the machinery for server-driven upgrades, described above,
and a later release turns it on.
```

- [ ] **Step 2: Commit**

```bash
git add docs/managed-agents.md
git commit -m "docs(agents): state what the remote upgrade helper grants and how to decline"
```

---

### Task 8: Show which endpoints are manual only

The phase gate is that an endpoint installed before this phase does not report
`self_upgrade` "and the UI says so". A chip next to the version says it. No
action changes: every row's reinstall action still opens `AgentReinstallDialog`,
because there is nothing else to open until phase 3.

**Files:**
- Create: `frontend/src/pages/managed-agents/AgentManualUpgradeChip.tsx`
- Create: `frontend/src/pages/managed-agents/AgentManualUpgradeChip.stories.tsx`
- Modify: `frontend/src/pages/ManagedAgents.tsx:1724` (the version cell)
- Modify: `frontend/src/pages/__tests__/ManagedAgents.test.tsx`
- Modify: `frontend/src/locales/{en,de,es,it}.json`

**Interfaces:**
- Consumes: `AgentMachineResponse.self_upgrade_supported`, already on the type
  in `frontend/src/services/api.ts:1198`.

Run the `ui-ux-pro-max` skill before writing the component, per `AGENTS.md`.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/pages/__tests__/ManagedAgents.test.tsx`, following the
existing render helpers in that file:

```tsx
it('marks an endpoint that cannot be upgraded from the server', async () => {
  renderManagedAgents({
    agents: [
      makeAgent({ id: 1, name: 'old-box', self_upgrade_supported: false }),
      makeAgent({ id: 2, name: 'new-box', self_upgrade_supported: true }),
    ],
  })

  expect(await screen.findAllByText('Manual upgrades only')).toHaveLength(1)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/__tests__/ManagedAgents.test.tsx -t 'cannot be upgraded'`
Expected: FAIL, no matching element.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/pages/managed-agents/AgentManualUpgradeChip.tsx`:

```tsx
import { Chip, Tooltip } from '@mui/material'
import { useTranslation } from 'react-i18next'

/**
 * Shown on an endpoint that carries no self-upgrade helper, so an operator can
 * see why it is not part of server-driven upgrades. An endpoint enrolled
 * before the helper existed, one whose operator declined it, and one enrolled
 * over http all land here, and all are fixed the same way: one reinstall.
 */
export default function AgentManualUpgradeChip() {
  const { t } = useTranslation()

  return (
    <Tooltip title={t('managedAgents.page.upgrade.manualOnlyTooltip')} arrow>
      <Chip
        size="small"
        variant="outlined"
        color="default"
        label={t('managedAgents.page.upgrade.manualOnly')}
        sx={{ height: 18, fontSize: '0.58rem', fontWeight: 600, '& .MuiChip-label': { px: 0.75 } }}
      />
    </Tooltip>
  )
}
```

Add the keys to all four locales under `managedAgents.page.upgrade`:

```json
"manualOnly": "Manual upgrades only",
"manualOnlyTooltip": "This endpoint has no self-upgrade helper, so it is updated by running the reinstall command on the machine. One reinstall gives it server-driven upgrades."
```

German:

```json
"manualOnly": "Nur manuelle Updates",
"manualOnlyTooltip": "Dieser Endpunkt hat kein Self-Upgrade-Hilfsprogramm und wird daher mit dem Reinstall-Befehl auf der Maschine aktualisiert. Eine Neuinstallation aktiviert servergesteuerte Upgrades."
```

Spanish:

```json
"manualOnly": "Solo actualizaciones manuales",
"manualOnlyTooltip": "Este endpoint no tiene el asistente de autoactualizacion, asi que se actualiza ejecutando el comando de reinstalacion en la maquina. Una reinstalacion habilita las actualizaciones desde el servidor."
```

Italian:

```json
"manualOnly": "Solo aggiornamenti manuali",
"manualOnlyTooltip": "Questo endpoint non ha l'helper di autoaggiornamento, quindi si aggiorna eseguendo il comando di reinstallazione sulla macchina. Una reinstallazione abilita gli aggiornamenti dal server."
```

In `ManagedAgents.tsx`, import the component next to `AgentUpgradeChip` and
render it in the same version cell, after the existing chip:

```tsx
{agent.self_upgrade_supported === false && <AgentManualUpgradeChip />}
```

The `=== false` is deliberate: `undefined` means a server that predates the
field, and that is not a claim about the endpoint.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/__tests__/ManagedAgents.test.tsx`
Expected: PASS.

- [ ] **Step 5: Add the story**

Create `frontend/src/pages/managed-agents/AgentManualUpgradeChip.stories.tsx`,
following `AgentUpgradeChip.stories.tsx` for meta shape and the mobile
viewport parameter used there:

```tsx
import type { Meta, StoryObj } from '@storybook/react'
import AgentManualUpgradeChip from './AgentManualUpgradeChip'

const meta: Meta<typeof AgentManualUpgradeChip> = {
  title: 'Managed Agents/AgentManualUpgradeChip',
  component: AgentManualUpgradeChip,
}

export default meta
type Story = StoryObj<typeof AgentManualUpgradeChip>

export const ManualOnly: Story = {}

export const Mobile: Story = {
  parameters: { viewport: { defaultViewport: 'mobile1' } },
}
```

- [ ] **Step 6: Verify the build and lint**

Run: `cd frontend && npm run lint && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/managed-agents/AgentManualUpgradeChip.tsx \
  frontend/src/pages/managed-agents/AgentManualUpgradeChip.stories.tsx \
  frontend/src/pages/ManagedAgents.tsx \
  frontend/src/pages/__tests__/ManagedAgents.test.tsx \
  frontend/src/locales/en.json frontend/src/locales/de.json \
  frontend/src/locales/es.json frontend/src/locales/it.json
git commit -m "feat(agents): mark endpoints that can only be upgraded by hand

An endpoint enrolled before the self-upgrade helper existed, or whose operator
declined it, reports no self_upgrade. The chip says so rather than leaving the
operator to wonder why a machine never joins server-driven upgrades."
```

---

## Phase completion

- [ ] **Run the full backend suite**

Run: `pytest tests/unit -q`
Expected: PASS. `test_api_auth` failures caused by a local `.env`
`PUBLIC_BASE_URL` are pre-existing and unrelated; confirm against `main`
before treating any as a regression.

- [ ] **Run the frontend suite**

Run: `cd frontend && npx vitest run && npm run lint`
Expected: PASS.

- [ ] **Apply `superpowers:verification-before-completion`** before claiming
  the phase is done.

- [ ] **Update the spec progress table** at
  `docs/engineering/specs/2026-09-07-centralized-agent-upgrades.md:544`: set
  phase 2 to `in review`, plan file
  `docs/engineering/plans/2026-09-09-agent-upgrades-phase-2.md`, branch
  `feat/agent-upgrades-phase-2`. Change nothing else in the spec.

- [ ] **Stop at the gate.** Do not push, open a PR, or merge without the
  owner's answer. The gate for this phase: a freshly installed endpoint
  reports `self_upgrade`; an endpoint installed before this phase does not,
  and the UI says so. Raise the two open decisions at the top of this plan
  with the answer.
