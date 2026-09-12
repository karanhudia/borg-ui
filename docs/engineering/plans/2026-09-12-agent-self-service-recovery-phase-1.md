# Agent self-service recovery phase 1: change the server URL

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. The owner has ruled out subagents on
> cost, so `superpowers:subagent-driven-development` is not an option here.

**Goal:** An operator whose Borg UI server moved to a new address opens Managed
Agents, clicks **Change server URL** on the stranded card, types the new URL,
and is handed one command that points that endpoint at the new address without
re-enrolling it.

**Architecture:** Nothing in the agent to server protocol changes and no new
server route is added. The agent gains one subcommand, `set-server`, that
rewrites `server_url` in `config.toml` through the existing `save_config` and
leaves `agent_id`, `agent_token` and `name` alone. The page gains one dialog
that renders exactly one command, chosen from the `agent_version` already
present on `AgentMachineResponse`: the subcommand for an agent new enough to
have it, an anchored `sed` against the exact line `save_config` writes for
anything older or unknown. The operator never sees the fork. The offline card
gains one line naming `borg-ui-agent status` as the way to read what the
endpoint currently believes, which is the diagnostic that already exists and
that nothing points at.

**Tech Stack:** Python (argparse, pytest), React, TypeScript, MUI, i18next,
Vitest, Storybook.

**Spec:** `docs/engineering/specs/2026-09-12-agent-self-service-recovery.md`
(sections 4, 5, 7, 8, 9; phase 10.2). Appendix A lists every file touched.

## Global Constraints

- No em dashes in UI copy, i18n strings, code comments, docs, or commit
  messages. Check added lines only, with
  `git diff -U0 origin/main | grep -nP '\xe2\x80\x94'`.
- Every new i18n key must be added to all four locales:
  `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`. The
  `frontend-locale-check` pre-push hook fails otherwise.
- New UI components go in `frontend/src/pages/managed-agents/`, not inline in
  `ManagedAgents.tsx`, which is over 2400 lines.
- New or changed UI ships a Storybook story for the changed state, in default
  and mobile viewports, matching `ManagedAgents.stories.tsx` conventions.
- No heavy left accent borders on cards, panels, alerts, or status surfaces
  (`AGENTS.md`, UI Preferences).
- No new server route in this phase. Spec section 4 lists the whole feature,
  and the only new endpoint it names, `GET /agent/uninstall.sh`, is phase 2.
- `set-server` writes only through `save_config`. It never touches
  `agent_token`, `agent_id`, or any unit file (spec section 8).
- Do not re-open a decision in the spec's Appendix B.

## Decisions this plan makes that the spec leaves open

Called out here rather than buried in a task, and repeated as Open questions at
the end for the phase gate.

1. **The command form is selected in the frontend, not by a server route.**
   Spec section 5.2 says "the server chooses which form based on the
   `agent_version` already stored on the machine record, compared using the
   existing `parse_agent_version`", and Appendix B.2 calls this "selecting the
   form server-side". Spec section 4 is explicit that the entire phase 1 shape
   is a subcommand, dialogs and docs, with no new endpoint. Those reconcile
   one way: the selection is made from the record rather than by the operator,
   and `agent_version` is already on `AgentMachineResponse` and already
   rendered on the card (`ManagedAgents.tsx:1827`). Every other agent command
   on this page is built in TypeScript from the same record
   (`agentInstallCommandText.ts`), so this one is too. Adding a route to
   return a string the page already has the inputs for would be a route with
   no reason to exist.
2. **The TypeScript version check mirrors `parse_agent_version`'s strictness
   rather than reusing `compareVersions`.** `frontend/src/utils/announcements.ts`
   exports a `compareVersions` that understands prereleases and is used for
   announcement gating. `parse_agent_version`
   (`app/core/agent_versions.py:31`) deliberately refuses anything that is not
   plain dotted ASCII integers and returns None so the caller reports unknown.
   Spec section 5.2 routes unknown to the `sed` fallback, which is the safe
   branch. Reusing `compareVersions` would rank a prerelease instead of
   refusing it, which is the opposite of what the cited function does. The
   mirror is eight lines and lives beside the command it gates.
3. **`CopyableCodeBlock` moves out of `ManagedAgents.tsx` into
   `managed-agents/`.** It is module-private at `ManagedAgents.tsx:976` and the
   new dialog needs it. Exporting it in place would make
   `managed-agents/AgentSetServerDialog.tsx` import from `ManagedAgents.tsx`
   while `ManagedAgents.tsx` imports the dialog, which is an import cycle.
   Moving the component is the smaller and non-cyclic change, and it removes
   about 60 lines from a file the constraints already call too long.
4. **The version floor is `0.1.5`, and this phase bumps the agent to it.**
   `set-server` does not exist in any released agent, so the floor is the
   release that first carries it. Today `agent/borg_ui_agent/__init__.py` and
   `pyproject.toml` both read `0.1.4`; Task 1 moves both to `0.1.5` in the same
   commit that adds the subcommand, so the constant the dialog compares against
   is never ahead of the code.

---

### Task 1: `set-server` subcommand

**Files:**
- Modify: `agent/borg_ui_agent/cli.py:27` (`build_parser`), and the dispatch in
  `main` at `agent/borg_ui_agent/cli.py:161`
- Modify: `agent/borg_ui_agent/__init__.py:1` (`0.1.4` to `0.1.5`)
- Modify: `pyproject.toml:7` (`0.1.4` to `0.1.5`)
- Test: `tests/unit/agent/test_cli_set_server.py` (new)

**Interfaces:**
- Consumes: `load_config`, `save_config`, `AgentConfig` from
  `agent/borg_ui_agent/config.py`, all unchanged.
- Produces: CLI surface `borg-ui-agent set-server URL`, exit 0 on success and
  exit 1 with a message on an invalid URL. Task 2 hard-codes this spelling into
  the rendered command.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/agent/test_cli_set_server.py`:

```python
from pathlib import Path

import pytest

from agent.borg_ui_agent.cli import main
from agent.borg_ui_agent.config import AgentConfig, load_config, save_config


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    save_config(
        AgentConfig(
            server_url="http://192.168.1.81:8083",
            agent_id="agt_abc",
            agent_token="secret-token",
            name="db-01",
        ),
        path,
    )
    return path


def test_set_server_writes_the_new_url(config_path: Path) -> None:
    assert main(["--config", str(config_path), "set-server", "http://192.168.1.82:8083"]) == 0
    assert load_config(config_path).server_url == "http://192.168.1.82:8083"


def test_set_server_preserves_identity_and_credential(config_path: Path) -> None:
    main(["--config", str(config_path), "set-server", "https://borg.example.com"])
    config = load_config(config_path)
    assert config.agent_id == "agt_abc"
    assert config.agent_token == "secret-token"
    assert config.name == "db-01"


def test_set_server_strips_a_trailing_slash(config_path: Path) -> None:
    main(["--config", str(config_path), "set-server", "https://borg.example.com/"])
    assert load_config(config_path).server_url == "https://borg.example.com"


@pytest.mark.parametrize(
    "url",
    [
        "borg.example.com",           # no scheme
        "ftp://borg.example.com",     # wrong scheme
        "http://",                    # no host
        "",                           # empty
    ],
)
def test_set_server_rejects_an_unusable_url(config_path: Path, url: str) -> None:
    before = config_path.read_bytes()
    with pytest.raises(SystemExit) as exit_info:
        main(["--config", str(config_path), "set-server", url])
    assert exit_info.value.code == 1
    # The file is byte-identical: a rejected URL must not leave a half-written
    # config on a machine that is already unreachable.
    assert config_path.read_bytes() == before
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/agent/test_cli_set_server.py -v`
Expected: FAIL, argparse rejecting `set-server` as an invalid choice.

- [ ] **Step 3: Add the subparser**

In `agent/borg_ui_agent/cli.py`, inside `build_parser`, after the
`subparsers.add_parser("unregister")` line:

```python
    set_server = subparsers.add_parser("set-server")
    set_server.add_argument("url")
```

- [ ] **Step 4: Add the handler**

Add to `agent/borg_ui_agent/cli.py`, after `_unregister`, and add
`from urllib.parse import urlparse` to the imports at the top of the file:

```python
def _set_server(args: argparse.Namespace) -> int:
    """Point this endpoint at a different Borg UI server.

    Only `server_url` moves. The agent id, its credential and its name are
    rewritten unchanged, so the endpoint keeps its identity and its history on
    the new address instead of enrolling a second time.
    """
    parsed = urlparse(args.url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            f"invalid server URL: {args.url!r} (expected http:// or https:// and a host)"
        )
    config = load_config(args.config)
    config_path = save_config(
        AgentConfig(
            server_url=args.url.rstrip("/"),
            agent_id=config.agent_id,
            agent_token=config.agent_token,
            name=config.name,
        ),
        args.config,
    )
    print(f"Server: {args.url.rstrip('/')}")
    print(f"Config: {config_path}")
    print("Restart the service for this to take effect.")
    return 0
```

- [ ] **Step 5: Wire the dispatch**

In `main`, after the `unregister` branch:

```python
        if args.command == "set-server":
            return _set_server(args)
```

And widen the except clause so a rejected URL exits 1 with the message rather
than tracing back. Change:

```python
    except (AgentClientError, OSError, KeyError, ServiceSetupError) as exc:
```

to:

```python
    except (AgentClientError, OSError, KeyError, ServiceSetupError, ValueError) as exc:
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/unit/agent/test_cli_set_server.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 7: Bump the agent version**

`agent/borg_ui_agent/__init__.py`:

```python
__version__ = "0.1.5"
```

`pyproject.toml` line 7:

```toml
version = "0.1.5"
```

- [ ] **Step 8: Run the agent suite for regressions**

Run: `pytest tests/unit/agent tests/unit/test_agent_runtime.py -q`
Expected: PASS. If a test asserts the literal `0.1.4`, update it to `0.1.5`;
`tests/unit/test_agent_installer_pins.py` monkeypatches the version and is not
affected.

- [ ] **Step 9: Commit**

```bash
git add agent/borg_ui_agent/cli.py agent/borg_ui_agent/__init__.py pyproject.toml tests/unit/agent/test_cli_set_server.py
git commit -m "feat(agent): add a set-server subcommand for redirecting an endpoint"
```

---

### Task 2: version-selected command rendering

**Files:**
- Create: `frontend/src/pages/managed-agents/agentSetServerCommandText.ts`
- Test: `frontend/src/pages/managed-agents/__tests__/agentSetServerCommandText.test.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks. Deliberately does **not** reuse
  `shellQuote` from `agentInstallCommandText.ts`: that helper returns a value
  bare when it matches its safe-character class, and every ordinary server URL
  does, so it would render `set-server http://host:8083` where spec section 5.2
  shows `set-server "URL"`. The `sed` half needs unconditional double quotes
  for a different reason again: that half is TOML, not shell, and
  `save_config` always writes the value quoted.
- Produces:
  `buildSetServerCommand(newServerUrl: string, agentVersion: string | null | undefined): string`
  and `SET_SERVER_MIN_AGENT_VERSION: string`. Task 3 calls
  `buildSetServerCommand` and nothing else from this module.

- [ ] **Step 1: Write the failing tests**

Create
`frontend/src/pages/managed-agents/__tests__/agentSetServerCommandText.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { buildSetServerCommand, isSafeServerUrlForCommand } from '../agentSetServerCommandText'

const URL = 'http://192.168.1.82:8083'

describe('buildSetServerCommand', () => {
  it('uses the subcommand on an agent that has it', () => {
    expect(buildSetServerCommand(URL, '0.1.5')).toBe(
      `sudo borg-ui-agent set-server "${URL}" && sudo systemctl restart borg-ui-agent`
    )
  })

  it('uses the subcommand on an agent newer than the floor', () => {
    expect(buildSetServerCommand(URL, '0.2.0')).toContain('borg-ui-agent set-server')
  })

  it('falls back to sed on an older agent', () => {
    expect(buildSetServerCommand(URL, '0.1.4')).toBe(
      `sudo sed -i 's|^server_url = .*|server_url = "${URL}"|' ` +
        '/etc/borg-ui-agent/config.toml && sudo systemctl restart borg-ui-agent'
    )
  })

  it('falls back to sed when the version is unknown', () => {
    expect(buildSetServerCommand(URL, null)).toContain('sed -i')
    expect(buildSetServerCommand(URL, undefined)).toContain('sed -i')
    expect(buildSetServerCommand(URL, '')).toContain('sed -i')
  })

  it('falls back to sed on a version that is not plain dotted integers', () => {
    // Mirrors parse_agent_version in app/core/agent_versions.py, which returns
    // None for a prerelease rather than ordering it.
    expect(buildSetServerCommand(URL, '0.1.5a1')).toContain('sed -i')
    expect(buildSetServerCommand(URL, 'nightly')).toContain('sed -i')
  })

  it('always double-quotes the URL, including an ordinary one', () => {
    // The sed half is TOML, not shell: save_config always writes the value
    // quoted, so the replacement line has to reproduce the quotes exactly.
    expect(buildSetServerCommand(URL, '0.1.4')).toContain(`server_url = "${URL}"`)
  })

  it('escapes a shell metacharacter in the subcommand form', () => {
    const command = buildSetServerCommand('http://example.com/$(touch pwned)', '0.1.5')
    expect(command).toContain('\\$(touch pwned)')
    expect(command).not.toMatch(/[^\\]\$\(/)
  })

  it('escapes a double quote and a backslash', () => {
    const command = buildSetServerCommand('http://example.com/a"b\\c', '0.1.5')
    expect(command).toContain('a\\"b\\\\c')
  })

  it('does not let a URL containing an equals sign break the sed replacement', () => {
    const command = buildSetServerCommand('http://example.com/?a=b', '0.1.4')
    // The pattern is anchored at line start and replaces the whole line, so
    // the URL's own "=" is only ever in the replacement half.
    expect(command).toContain('s|^server_url = .*|server_url = "http://example.com/?a=b"|')
  })
})

describe('isSafeServerUrlForCommand', () => {
  it('accepts ordinary http and https URLs', () => {
    expect(isSafeServerUrlForCommand(URL)).toBe(true)
    expect(isSafeServerUrlForCommand('https://borg.example.com/borg')).toBe(true)
  })

  it('rejects anything that is not http or https with a host', () => {
    expect(isSafeServerUrlForCommand('borg.example.com')).toBe(false)
    expect(isSafeServerUrlForCommand('ftp://borg.example.com')).toBe(false)
    expect(isSafeServerUrlForCommand('')).toBe(false)
  })

  it("rejects a single quote and a pipe", () => {
    // The sed expression is wrapped in single quotes and delimited by "|".
    // Neither character appears in a real server URL, and escaping them inside
    // a single-quoted sed expression is not worth the rendering it would need.
    expect(isSafeServerUrlForCommand("http://example.com/a'b")).toBe(false)
    expect(isSafeServerUrlForCommand('http://example.com/a|b')).toBe(false)
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/agent/test_cli_set_server.py -v`
Expected: FAIL, argparse rejecting `set-server` as an invalid choice.

- [ ] **Step 3: Add the subparser**

In `agent/borg_ui_agent/cli.py`, inside `build_parser`, after the
`subparsers.add_parser("unregister")` line:

```python
    set_server = subparsers.add_parser("set-server")
    set_server.add_argument("url")
```

- [ ] **Step 4: Add the handler**

Add to `agent/borg_ui_agent/cli.py`, after `_unregister`, and add
`from urllib.parse import urlparse` to the imports at the top of the file:

```python
def _set_server(args: argparse.Namespace) -> int:
    """Point this endpoint at a different Borg UI server.

    Only `server_url` moves. The agent id, its credential and its name are
    rewritten unchanged, so the endpoint keeps its identity and its history on
    the new address instead of enrolling a second time.
    """
    parsed = urlparse(args.url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            f"invalid server URL: {args.url!r} (expected http:// or https:// and a host)"
        )
    config = load_config(args.config)
    config_path = save_config(
        AgentConfig(
            server_url=args.url.rstrip("/"),
            agent_id=config.agent_id,
            agent_token=config.agent_token,
            name=config.name,
        ),
        args.config,
    )
    print(f"Server: {args.url.rstrip('/')}")
    print(f"Config: {config_path}")
    print("Restart the service for this to take effect.")
    return 0
```

- [ ] **Step 5: Wire the dispatch**

In `main`, after the `unregister` branch:

```python
        if args.command == "set-server":
            return _set_server(args)
```

And widen the except clause so a rejected URL exits 1 with the message rather
than tracing back. Change:

```python
    except (AgentClientError, OSError, KeyError, ServiceSetupError) as exc:
```

to:

```python
    except (AgentClientError, OSError, KeyError, ServiceSetupError, ValueError) as exc:
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/unit/agent/test_cli_set_server.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 7: Bump the agent version**

`agent/borg_ui_agent/__init__.py`:

```python
__version__ = "0.1.5"
```

`pyproject.toml` line 7:

```toml
version = "0.1.5"
```

- [ ] **Step 8: Run the agent suite for regressions**

Run: `pytest tests/unit/agent tests/unit/test_agent_runtime.py -q`
Expected: PASS. If a test asserts the literal `0.1.4`, update it to `0.1.5`;
`tests/unit/test_agent_installer_pins.py` monkeypatches the version and is not
affected.

- [ ] **Step 9: Commit**

```bash
git add agent/borg_ui_agent/cli.py agent/borg_ui_agent/__init__.py pyproject.toml tests/unit/agent/test_cli_set_server.py
git commit -m "feat(agent): add a set-server subcommand for redirecting an endpoint"
```

---

### Task 2: version-selected command rendering

**Files:**
- Create: `frontend/src/pages/managed-agents/agentSetServerCommandText.ts`
- Test: `frontend/src/pages/managed-agents/__tests__/agentSetServerCommandText.test.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks. Deliberately does **not** reuse
  `shellQuote` from `agentInstallCommandText.ts`: that helper returns a value
  bare when it matches its safe-character class, and every ordinary server URL
  does, so it would render `set-server http://host:8083` where spec section 5.2
  shows `set-server "URL"`. The `sed` half needs unconditional double quotes
  for a different reason again: that half is TOML, not shell, and
  `save_config` always writes the value quoted.
- Produces:
  `buildSetServerCommand(newServerUrl: string, agentVersion: string | null | undefined): string`
  and `SET_SERVER_MIN_AGENT_VERSION: string`. Task 3 calls
  `buildSetServerCommand` and nothing else from this module.

- [ ] **Step 1: Write the failing tests**

Create
`frontend/src/pages/managed-agents/__tests__/agentSetServerCommandText.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { buildSetServerCommand } from '../agentSetServerCommandText'

const URL = 'http://192.168.1.82:8083'

describe('buildSetServerCommand', () => {
  it('uses the subcommand on an agent that has it', () => {
    expect(buildSetServerCommand(URL, '0.1.5')).toBe(
      `sudo borg-ui-agent set-server "${URL}" && sudo systemctl restart borg-ui-agent`
    )
  })

  it('uses the subcommand on an agent newer than the floor', () => {
    expect(buildSetServerCommand(URL, '0.2.0')).toContain('borg-ui-agent set-server')
  })

  it('falls back to sed on an older agent', () => {
    expect(buildSetServerCommand(URL, '0.1.4')).toBe(
      `sudo sed -i 's|^server_url = .*|server_url = "${URL}"|' ` +
        '/etc/borg-ui-agent/config.toml && sudo systemctl restart borg-ui-agent'
    )
  })

  it('falls back to sed when the version is unknown', () => {
    expect(buildSetServerCommand(URL, null)).toContain('sed -i')
    expect(buildSetServerCommand(URL, undefined)).toContain('sed -i')
    expect(buildSetServerCommand(URL, '')).toContain('sed -i')
  })

  it('falls back to sed on a version that is not plain dotted integers', () => {
    // Mirrors parse_agent_version in app/core/agent_versions.py, which returns
    // None for a prerelease rather than ordering it.
    expect(buildSetServerCommand(URL, '0.1.5a1')).toContain('sed -i')
    expect(buildSetServerCommand(URL, 'nightly')).toContain('sed -i')
  })

  it('shell-quotes a URL carrying a metacharacter', () => {
    const hostile = 'http://example.com/$(touch pwned)'
    const command = buildSetServerCommand(hostile, '0.1.5')
    expect(command).toContain('\\$')
    expect(command).not.toContain('$(touch pwned)')
  })

  it('does not let a URL containing an equals sign break the sed replacement', () => {
    const command = buildSetServerCommand('http://example.com/?a=b', '0.1.4')
    // The pattern is anchored at line start and replaces the whole line, so
    // the URL's own "=" is only ever in the replacement half.
    expect(command).toContain("s|^server_url = .*|server_url = \"http://example.com/?a=b\"|")
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && yarn vitest run src/pages/managed-agents/__tests__/agentSetServerCommandText.test.ts`
Expected: FAIL, module not found.

- [ ] **Step 3: Write the module**

Create `frontend/src/pages/managed-agents/agentSetServerCommandText.ts`:

```ts
/**
 * The first agent release carrying `borg-ui-agent set-server`. Anything older,
 * or anything whose version does not parse, gets the sed fallback instead.
 */
export const SET_SERVER_MIN_AGENT_VERSION = '0.1.5'

const AGENT_CONFIG_PATH = '/etc/borg-ui-agent/config.toml'
const RESTART = 'sudo systemctl restart borg-ui-agent'

/**
 * Dotted integer components, or null when any component is not a plain
 * non-negative ASCII integer.
 *
 * A deliberate mirror of `parse_agent_version` in
 * `app/core/agent_versions.py`: a prerelease such as "0.1.5a1" returns null so
 * the caller takes the fallback rather than guessing at an ordering. The
 * frontend's own `compareVersions` in `utils/announcements.ts` ranks
 * prereleases, which is right for announcement gating and wrong here.
 */
function parseAgentVersion(value: string | null | undefined): number[] | null {
  if (!value) return null
  const components: number[] = []
  for (const part of value.split('.')) {
    if (!/^[0-9]+$/.test(part)) return null
    components.push(Number.parseInt(part, 10))
  }
  return components
}

function atLeast(reported: number[], floor: number[]): boolean {
  const width = Math.max(reported.length, floor.length)
  for (let i = 0; i < width; i += 1) {
    const left = reported[i] ?? 0
    const right = floor[i] ?? 0
    if (left !== right) return left > right
  }
  return true
}

function hasSetServerSubcommand(agentVersion: string | null | undefined): boolean {
  const reported = parseAgentVersion(agentVersion)
  if (reported === null) return false
  return atLeast(reported, parseAgentVersion(SET_SERVER_MIN_AGENT_VERSION) as number[])
}

/**
 * Whether a URL can be rendered into either command form safely.
 *
 * Beyond being an http or https URL with a host, it must carry no single quote
 * and no "|". The sed expression is wrapped in single quotes and delimited by
 * "|", so either character would break out of the expression. Neither appears
 * in a real server URL, so refusing is honest and cheaper than the escaping
 * that carrying them would need. The dialog renders no command until this
 * passes.
 */
export function isSafeServerUrlForCommand(value: string): boolean {
  let parsed: URL
  try {
    parsed = new URL(value)
  } catch {
    return false
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) return false
  if (parsed.hostname === '') return false
  return !/['|]/.test(value)
}

/**
 * Always double-quoted, with the characters the shell would still read inside
 * double quotes escaped.
 *
 * Unconditional, not conditional like `shellQuote` in
 * `agentInstallCommandText.ts`: the sed half of the command is TOML rather than
 * shell, and `save_config` (`agent/borg_ui_agent/config.py`) always writes
 * `server_url = "..."`, so the replacement line has to reproduce those quotes
 * whatever the URL looks like.
 */
function quote(value: string): string {
  return `"${value.replace(/(["\\$`])/g, '\\$1')}"`
}

/**
 * The one command shown for moving an endpoint to a new server address.
 *
 * The form is picked from the version the endpoint last reported, never by the
 * operator: an agent new enough runs the subcommand, and anything older or
 * unknown gets a sed anchored on the exact line `save_config` writes. The
 * pattern replaces the whole line, so a URL containing "=" is safe.
 */
export function buildSetServerCommand(
  newServerUrl: string,
  agentVersion: string | null | undefined
): string {
  const url = newServerUrl.replace(/\/+$/, '')
  if (hasSetServerSubcommand(agentVersion)) {
    return `sudo borg-ui-agent set-server ${quote(url)} && ${RESTART}`
  }
  return (
    `sudo sed -i 's|^server_url = .*|server_url = ${quote(url)}|' ` +
    `${AGENT_CONFIG_PATH} && ${RESTART}`
  )
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && yarn vitest run src/pages/managed-agents/__tests__/agentSetServerCommandText.test.ts`
Expected: PASS, 12 tests.

- [ ] **Step 5: Confirm the install command is untouched**

This task deliberately does not modify `agentInstallCommandText.ts`. Confirm:

Run: `cd frontend && yarn vitest run src/pages/managed-agents && git diff --stat -- src/pages/managed-agents/agentInstallCommandText.ts`
Expected: tests PASS and the diff is empty.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/managed-agents/agentSetServerCommandText.ts frontend/src/pages/managed-agents/__tests__/agentSetServerCommandText.test.ts
git commit -m "feat(managed-agents): render the set-server command by agent version"
```

---

### Task 3: the Change server URL dialog

**Files:**
- Create: `frontend/src/pages/managed-agents/CopyableCodeBlock.tsx` (moved from
  `ManagedAgents.tsx:976`)
- Create: `frontend/src/pages/managed-agents/AgentSetServerDialog.tsx`
- Create: `frontend/src/pages/managed-agents/AgentSetServerDialog.stories.tsx`
- Modify: `frontend/src/pages/ManagedAgents.tsx` (delete the local
  `CopyableCodeBlock`, import the moved one)
- Modify: `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`
- Test: `frontend/src/pages/managed-agents/__tests__/AgentSetServerDialog.test.tsx`

**Interfaces:**
- Consumes: `buildSetServerCommand` and `isSafeServerUrlForCommand` from
  Task 2, and `ResponsiveDialog` from
  `../../components/shared/ResponsiveDialog`.
- Produces: default export `AgentSetServerDialog` with props
  `{ agent: AgentMachineResponse | null; open: boolean; defaultServerUrl: string; onCopy: (value: string) => void; onCancel: () => void }`.
  Task 4 mounts it with exactly these props.

- [ ] **Step 1: Move `CopyableCodeBlock`**

Cut the whole `function CopyableCodeBlock({ ... })` body from
`frontend/src/pages/ManagedAgents.tsx` (it starts at line 976) into a new file
`frontend/src/pages/managed-agents/CopyableCodeBlock.tsx`, adding
`export default` and the imports it uses (`Box`, `IconButton`, `Tooltip` from
`@mui/material`, `alpha` from `@mui/material/styles`, `Copy` from
`lucide-react`). In `ManagedAgents.tsx`, replace it with:

```tsx
import CopyableCodeBlock from './managed-agents/CopyableCodeBlock'
```

- [ ] **Step 2: Verify the move changed nothing**

Run: `cd frontend && yarn vitest run src/pages/__tests__/ManagedAgents.test.tsx && yarn tsc --noEmit`
Expected: PASS, and no type errors. Commit this move on its own:

```bash
git add frontend/src/pages/managed-agents/CopyableCodeBlock.tsx frontend/src/pages/ManagedAgents.tsx
git commit -m "refactor(managed-agents): move CopyableCodeBlock into its own file"
```

- [ ] **Step 3: Write the failing test**

Create
`frontend/src/pages/managed-agents/__tests__/AgentSetServerDialog.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import AgentSetServerDialog from '../AgentSetServerDialog'
import type { AgentMachineResponse } from '../../../services/api'

const agent = (agentVersion: string | null) =>
  ({
    id: 1,
    agent_id: 'agt_1',
    name: 'db-01',
    hostname: 'db-01.internal',
    status: 'offline',
    agent_version: agentVersion,
  }) as AgentMachineResponse

const renderDialog = (agentVersion: string | null) => {
  const onCopy = vi.fn()
  render(
    <AgentSetServerDialog
      agent={agent(agentVersion)}
      open
      defaultServerUrl="http://192.168.1.82:8083"
      onCopy={onCopy}
      onCancel={vi.fn()}
    />
  )
  return { onCopy }
}

describe('AgentSetServerDialog', () => {
  it('prefills the field with this server own URL', () => {
    renderDialog('0.1.5')
    expect(screen.getByRole('textbox')).toHaveValue('http://192.168.1.82:8083')
  })

  it('shows the subcommand form for a current agent', () => {
    renderDialog('0.1.5')
    expect(screen.getByText(/borg-ui-agent set-server/)).toBeInTheDocument()
    expect(screen.queryByText(/sed -i/)).not.toBeInTheDocument()
  })

  it('shows the sed form for an older agent, without explaining a fork', () => {
    renderDialog('0.1.4')
    expect(screen.getByText(/sed -i/)).toBeInTheDocument()
    expect(screen.queryByText(/borg-ui-agent set-server/)).not.toBeInTheDocument()
  })

  it('rerenders the command as the URL is edited', async () => {
    renderDialog('0.1.5')
    const field = screen.getByRole('textbox')
    await userEvent.clear(field)
    await userEvent.type(field, 'https://borg.example.com')
    expect(screen.getByText(/https:\/\/borg\.example\.com/)).toBeInTheDocument()
  })

  it('copies the rendered command', async () => {
    const { onCopy } = renderDialog('0.1.5')
    await userEvent.click(screen.getByRole('button', { name: /copy/i }))
    expect(onCopy).toHaveBeenCalledWith(expect.stringContaining('set-server'))
  })

  it('names borg-ui-agent status as the way to read the current URL', () => {
    renderDialog('0.1.5')
    expect(screen.getByText(/borg-ui-agent status/)).toBeInTheDocument()
  })

  it('renders no command while the URL is unusable', async () => {
    renderDialog('0.1.5')
    const field = screen.getByRole('textbox')
    await userEvent.clear(field)
    await userEvent.type(field, 'borg.example.com')
    expect(screen.queryByText(/set-server|sed -i/)).not.toBeInTheDocument()
    expect(screen.getByText(/http:\/\/ or https:\/\//)).toBeInTheDocument()
  })
})
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd frontend && yarn vitest run src/pages/managed-agents/__tests__/AgentSetServerDialog.test.tsx`
Expected: FAIL, module not found.

- [ ] **Step 5: Add the i18n keys**

Add to `frontend/src/locales/en.json` under `managedAgents.page`, and the
translated equivalents to `de.json`, `es.json` and `it.json`:

```json
"setServerDialog": {
  "title": "Change server URL",
  "description": "Point this endpoint at a different Borg UI address. It keeps its identity, its credential and its history, so no new enrollment token is needed.",
  "fieldLabel": "New server URL",
  "fieldHelper": "Prefilled with this server's own address. Edit it if the endpoint should reach Borg UI somewhere else, for example through a reverse proxy.",
  "invalidUrl": "Enter a full URL starting with http:// or https://",
  "copyCommand": "Copy command",
  "runHint": "Run this on the endpoint, as a user who can sudo.",
  "statusHint": "Not sure what address the endpoint holds right now? Run borg-ui-agent status on it."
}
```

- [ ] **Step 6: Write the dialog**

Create `frontend/src/pages/managed-agents/AgentSetServerDialog.tsx`:

```tsx
import {
  Alert,
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import ResponsiveDialog from '../../components/shared/ResponsiveDialog'
import type { AgentMachineResponse } from '../../services/api'
import CopyableCodeBlock from './CopyableCodeBlock'
import { buildSetServerCommand, isSafeServerUrlForCommand } from './agentSetServerCommandText'

/**
 * Hands the operator one command that moves an endpoint to a new server
 * address.
 *
 * The endpoint's current `server_url` is not stored on the server, so the
 * field cannot be prefilled from the record. It prefills with this server's
 * own base URL, which is the value the operator almost always wants and the
 * same one the enrollment command uses, and points at `borg-ui-agent status`
 * for reading what the endpoint actually holds.
 */
export default function AgentSetServerDialog({
  agent,
  open,
  defaultServerUrl,
  onCopy,
  onCancel,
}: {
  agent: AgentMachineResponse | null
  open: boolean
  defaultServerUrl: string
  onCopy: (value: string) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const [serverUrl, setServerUrl] = useState(defaultServerUrl)
  // Reset per target so an edit made for one endpoint is not carried to the
  // next card the operator opens.
  useEffect(() => {
    setServerUrl(defaultServerUrl)
  }, [agent, defaultServerUrl])

  const valid = isSafeServerUrlForCommand(serverUrl)
  const command = buildSetServerCommand(serverUrl, agent?.agent_version)

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
      <DialogTitle>{t('managedAgents.page.setServerDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          <Stack spacing={0.5}>
            <Typography sx={{ fontWeight: 700 }}>
              {[agent?.name, agent?.hostname].filter(Boolean).join(' · ')}
            </Typography>
            <Typography sx={{ color: 'text.secondary' }}>
              {t('managedAgents.page.setServerDialog.description')}
            </Typography>
          </Stack>
          <TextField
            fullWidth
            size="small"
            value={serverUrl}
            onChange={(event) => setServerUrl(event.target.value)}
            label={t('managedAgents.page.setServerDialog.fieldLabel')}
            error={serverUrl.length > 0 && !valid}
            helperText={
              serverUrl.length > 0 && !valid
                ? t('managedAgents.page.setServerDialog.invalidUrl')
                : t('managedAgents.page.setServerDialog.fieldHelper')
            }
          />
          {valid ? (
            <>
              <CopyableCodeBlock
                value={command}
                copyLabel={t('managedAgents.page.setServerDialog.copyCommand')}
                onCopy={() => onCopy(command)}
              />
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {t('managedAgents.page.setServerDialog.runHint')}
              </Typography>
            </>
          ) : null}
          <Alert severity="info" sx={{ borderRadius: 1.5 }}>
            {t('managedAgents.page.setServerDialog.statusHint')}
          </Alert>
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd frontend && yarn vitest run src/pages/managed-agents/__tests__/AgentSetServerDialog.test.tsx`
Expected: PASS, 7 tests.

- [ ] **Step 8: Write the Storybook stories**

Create `frontend/src/pages/managed-agents/AgentSetServerDialog.stories.tsx`:

```tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import AgentSetServerDialog from './AgentSetServerDialog'
import type { AgentMachineResponse } from '../../services/api'

const agent = {
  id: 1,
  agent_id: 'agt_1',
  name: 'db-01',
  hostname: 'db-01.internal',
  status: 'offline',
  agent_version: '0.1.5',
  created_at: '2026-05-10T08:00:00.000Z',
  updated_at: '2026-09-12T08:00:00.000Z',
} as AgentMachineResponse

const meta: Meta<typeof AgentSetServerDialog> = {
  title: 'Managed Agents/AgentSetServerDialog',
  component: AgentSetServerDialog,
  parameters: { layout: 'fullscreen' },
  args: {
    open: true,
    defaultServerUrl: 'http://192.168.1.82:8083',
    onCopy: () => {},
    onCancel: () => {},
  },
}
export default meta

type Story = StoryObj<typeof AgentSetServerDialog>

export const CurrentAgent: Story = { args: { agent } }

export const OlderAgent: Story = {
  args: { agent: { ...agent, agent_version: '0.1.4' } as AgentMachineResponse },
}

export const UnknownVersion: Story = {
  args: { agent: { ...agent, agent_version: null } as AgentMachineResponse },
}

export const Mobile: Story = {
  args: { agent },
  parameters: { viewport: { defaultViewport: 'mobile1' } },
}
```

- [ ] **Step 9: Render the stories and check both themes**

Storybook needs Node 20.19 or newer; select it with `fnm use v24` first.

Run: `cd frontend && yarn storybook`
Open `Managed Agents/AgentSetServerDialog`, check `CurrentAgent`, `OlderAgent`
and `Mobile` in light and dark, and confirm the command box wraps rather than
overflowing at mobile width.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/pages/managed-agents/AgentSetServerDialog.tsx frontend/src/pages/managed-agents/AgentSetServerDialog.stories.tsx frontend/src/pages/managed-agents/__tests__/AgentSetServerDialog.test.tsx frontend/src/locales
git commit -m "feat(managed-agents): add the change server URL dialog"
```

---

### Task 4: card action and the offline status hint

**Files:**
- Modify: `frontend/src/pages/ManagedAgents.tsx` (import and state near
  `reinstallTarget` at line 1645, an action button in the row that starts at
  line 1991, the dialog mount beside `AgentReinstallDialog` at line 2222, and
  the hint near the `last_error` block at line 1934)
- Modify: `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`
- Modify: `frontend/src/pages/ManagedAgents.stories.tsx`
- Test: `frontend/src/pages/__tests__/ManagedAgents.test.tsx`

**Interfaces:**
- Consumes: `AgentSetServerDialog` from Task 3, with the prop shape that task
  produced.
- Produces: nothing further tasks depend on.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/pages/__tests__/ManagedAgents.test.tsx`, following the
render helper already in that file:

```tsx
it('opens the change server URL dialog from the card', async () => {
  renderManagedAgents()
  await userEvent.click(await screen.findByLabelText(/change server url/i))
  expect(await screen.findByRole('textbox')).toBeInTheDocument()
  expect(screen.getByText(/borg-ui-agent set-server|sed -i/)).toBeInTheDocument()
})

it('points an offline card at borg-ui-agent status', async () => {
  renderManagedAgents()
  expect(await screen.findByText(/borg-ui-agent status/)).toBeInTheDocument()
})
```

If the fixture in that file has no offline agent, add one with
`status: 'offline'` rather than changing an existing fixture, so the online
assertions already in the file keep their subject.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && yarn vitest run src/pages/__tests__/ManagedAgents.test.tsx`
Expected: FAIL, no element with that label.

- [ ] **Step 3: Add the i18n keys**

Add to `managedAgents.page.actions` in all four locales:

```json
"changeServerUrl": "Change server URL"
```

And to `managedAgents.page` in all four locales:

```json
"offlineStatusHint": "Run borg-ui-agent status on the endpoint to see the server address it currently holds."
```

- [ ] **Step 4: Add the state and the import**

In `frontend/src/pages/ManagedAgents.tsx`, beside the existing import block for
`managed-agents/` components:

```tsx
import AgentSetServerDialog from './managed-agents/AgentSetServerDialog'
```

And beside `reinstallTarget` at line 1645, inside `AgentList`:

```tsx
const [setServerTarget, setSetServerTarget] = useState<AgentMachineResponse | null>(null)
```

- [ ] **Step 5: Add the action button**

In the card action row, between the reinstall button and the revoke button, add
a button using the same `IconButton` shape as its neighbours. Import `Link2`
from `lucide-react` beside the existing icon imports. Available in every state,
because offline is the state where it matters most (spec section 7):

```tsx
<Tooltip title={t('managedAgents.page.actions.changeServerUrl')} arrow>
  <IconButton
    size="small"
    aria-label={t('managedAgents.page.actions.changeServerUrl')}
    onClick={() => {
      trackSystem(EventAction.VIEW, {
        section: MANAGED_AGENTS_ANALYTICS_SECTION,
        operation: 'open_set_server_dialog',
        status: agent.status,
      })
      setSetServerTarget(agent)
    }}
    sx={{
      width: { xs: 40, sm: 34 },
      height: { xs: 40, sm: 34 },
      borderRadius: 1.5,
      color: alpha(theme.palette.primary.main, 0.75),
      '&:hover': {
        color: theme.palette.primary.main,
        bgcolor: alpha(theme.palette.primary.main, isDark ? 0.15 : 0.1),
      },
    }}
  >
    <Link2 size={16} />
  </IconButton>
</Tooltip>
```

- [ ] **Step 6: Mount the dialog**

Beside `<AgentReinstallDialog ... />` at line 2222:

```tsx
<AgentSetServerDialog
  open={!!setServerTarget}
  agent={setServerTarget}
  defaultServerUrl={serverUrl}
  onCopy={onCopy}
  onCancel={() => setSetServerTarget(null)}
/>
```

- [ ] **Step 7: Add the offline hint**

Directly after the `{agent.last_error && (...)}` block at line 1934, add a line
shown only when the endpoint is not online. The server cannot receive a
`last_error` from an agent that cannot reach it, so this is the only thing the
card can say about that state:

```tsx
{agent.status !== 'online' && (
  <Typography
    variant="caption"
    sx={{ display: 'block', mb: 1.5, color: 'text.secondary', lineHeight: 1.4 }}
  >
    {t('managedAgents.page.offlineStatusHint')}
  </Typography>
)}
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd frontend && yarn vitest run src/pages/__tests__/ManagedAgents.test.tsx && yarn tsc --noEmit`
Expected: PASS, and no type errors.

- [ ] **Step 9: Add a story for the offline card**

In `frontend/src/pages/ManagedAgents.stories.tsx`, beside
`AgentFleetVersionStates` (line 644), which is the file's convention for an
agent-state story:

```tsx
const offlineAgents = [
  {
    ...agents[0],
    id: 93,
    agent_id: 'agt_offline_93',
    name: 'Stranded NAS',
    status: 'offline',
    agent_version: '0.1.4',
    available_agent_version: '0.1.5',
  },
  {
    ...agents[1],
    id: 94,
    agent_id: 'agt_offline_94',
    name: 'Relocated Server',
    status: 'offline',
    agent_version: '0.1.5',
    available_agent_version: '0.1.5',
  },
]

export const AgentFleetOfflineRecovery: Story = {
  name: 'Agent list with offline endpoints and the server URL hint',
  render: () => (
    <AgentList
      agents={offlineAgents}
      serverUrl="https://borg-ui.example.com"
      onCopy={() => {}}
      onRevoke={() => {}}
      onDelete={() => {}}
      onViewLogs={() => {}}
      isRevoking={false}
      isDeleting={false}
    />
  ),
}

export const AgentFleetOfflineRecoveryMobile: Story = {
  ...AgentFleetOfflineRecovery,
  name: 'Agent list with offline endpoints, mobile',
  parameters: { viewport: { defaultViewport: 'mobile1' } },
}
```

If the fixture array in that file is typed such that a literal `status` string
is rejected, cast each entry `as AgentMachineResponse`, matching how
`AgentUpgradeDialog.stories.tsx` builds its fixture.

- [ ] **Step 10: Render and screenshot**

Run: `fnm use v24 && cd frontend && yarn storybook`
Check `AgentFleetOfflineRecovery` and `AgentFleetOfflineRecoveryMobile` in
light and dark. Confirm the action row does not wrap awkwardly now that it carries
one more button at `sm`.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/pages/ManagedAgents.tsx frontend/src/pages/ManagedAgents.stories.tsx frontend/src/pages/__tests__/ManagedAgents.test.tsx frontend/src/locales
git commit -m "feat(managed-agents): add the change server URL action and an offline status hint"
```

---

### Task 5: documentation

**Files:**
- Modify: `docs/managed-agents.md` (the "Server URL and Localhost" section at
  line 244)

**Interfaces:**
- Consumes: the command spellings from Task 2.
- Produces: nothing.

- [ ] **Step 1: Add the recovery section**

In `docs/managed-agents.md`, immediately after the "Server URL and Localhost"
section, add:

```markdown
### Moving an endpoint to a new server address

If the Borg UI server moves, for example because its IP address changed or it
went behind a reverse proxy, every enrolled agent still holds the old address
and goes offline. Reinstalling does not fix this: `--reinstall` deliberately
preserves `/etc/borg-ui-agent/config.toml`, which is where the old address
lives.

To see what address an endpoint currently holds, run this on that machine:

```bash
borg-ui-agent status
```

To move it, open **Managed Agents**, click **Change server URL** on that
endpoint's card, enter the new address, and run the command it gives you on
that machine. The endpoint keeps its identity, its credential and its history,
so you do not need a new enrollment token and you do not get a second card in
the fleet list.

The command Borg UI shows depends on the agent version that endpoint last
reported. From agent 0.1.5 onward it uses the subcommand:

```bash
sudo borg-ui-agent set-server "https://borg.example.com" && sudo systemctl restart borg-ui-agent
```

Older agents do not have that subcommand, so Borg UI shows an equivalent edit
of the config file instead. Either way it is one command, and you do not have
to choose between them.
```

- [ ] **Step 2: Check for em dashes**

Run: `git diff -U0 origin/main -- docs/managed-agents.md | grep -nP '\xe2\x80\x94'`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add docs/managed-agents.md
git commit -m "docs(managed-agents): document recovering an endpoint after the server moves"
```

---

## Verification before claiming the phase done

Use `superpowers:verification-before-completion`. Run each of these and paste
the output rather than asserting the result.

- [ ] `pytest tests/unit/agent tests/unit/test_agent_runtime.py tests/unit/test_agent_installer_pins.py -q`
- [ ] `cd frontend && yarn vitest run src/pages/managed-agents src/pages/__tests__/ManagedAgents.test.tsx`
- [ ] `cd frontend && yarn tsc --noEmit && yarn lint`
- [ ] `git diff -U0 origin/main | grep -nP '\xe2\x80\x94'` returns nothing
- [ ] All four locales carry every new key (the `frontend-locale-check`
      pre-push hook is the backstop, but check before pushing)
- [ ] Storybook rendered, light and dark, default and mobile, for
      `AgentSetServerDialog` and the offline `ManagedAgents` card

## The phase gate

Spec section 10.2: an operator can move a real endpoint to a new URL from the
card, on both a current agent and one old enough to need the `sed` fallback,
and it reconnects with the same identity.

This needs a live endpoint and is the owner's to run. Suggested check, on the
Raspberry Pi agent:

1. Note `agent_id` on the card.
2. Run `borg-ui-agent status` on the endpoint and record the server URL.
3. Use the dialog to move it to the tunnel URL, run the command, confirm the
   card goes online with the same `agent_id` and no second card appears.
4. Downgrade the reported version, or test against an endpoint still on 0.1.4,
   to exercise the `sed` form, and confirm it reconnects the same way.

## Open questions for the gate

1. Command rendering is in TypeScript, not a server route (decision 1 above).
   Spec section 5.2 says "the server chooses", section 4 says no new endpoint.
   Confirm the reading.
2. The agent version floor is `0.1.5` and this phase bumps `pyproject.toml` and
   `agent/borg_ui_agent/__init__.py` to it (decision 4). Confirm that is how
   agent releases are cut here, rather than the bump belonging to a release
   commit of its own.
3. `CopyableCodeBlock` moves out of `ManagedAgents.tsx` (decision 3). Confirm
   that refactor is welcome in this branch rather than deferred.
