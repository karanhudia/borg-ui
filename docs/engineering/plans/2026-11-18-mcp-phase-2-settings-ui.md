# MCP Phase 2: Settings UI and Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Pro user can create, connect, inspect and revoke MCP connections from Settings, an admin can switch MCP off or cap its level, and `docs/mcp.md` explains all of it.

**Architecture:** Phase 1 already ships the REST surface (`/api/settings/mcp/config`, `/connections`, `/connections/{id}/activity`) and the `/mcp` endpoint. This phase adds two small backend pieces (a "calls today" count, and refusing levels that have no tools yet), then a frontend feature folder `frontend/src/components/mcp/` composed from small components, a new per-user Settings tab `mcp`, one new System settings section for the admin controls, and docs.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React + MUI + TanStack Query + react-i18next + Vitest + Storybook (frontend).

**Spec:** `docs/engineering/specs/2026-11-14-mcp-server.md` (sections 5.1, 5.2, 5.11, 5.12, 6; review focus 8.3 phase 2 = 5.12).

## Global Constraints

- Branch `feat/mcp-phase-2` from `main`, worktree `../borg-ui-mcp`. Nothing committed or pushed without the gate answer (8.4).
- Phase 2 offers only `read` (spec 6: "The UI only offers levels whose tools exist").
- Tab label "AI assistants (MCP)", behind `PlanGate feature="mcp"` (5.1, 5.12).
- Create dialog uses `ResponsiveDialog`, never raw MUI `Dialog` (AGENTS.md). Levels as four rich radio cards, one line each.
- Every new string in all four locales: `en`, `de`, `es`, `it`. `npm run check:locales` must pass.
- No em dashes in copy, comments, docs or commit messages.
- No heavy left accent borders; use full outlines, tints, chips (AGENTS.md UI Preferences).
- Every new component gets a Storybook story covering its states; no PNGs committed under `frontend/storybook-snapshots/` or `frontend/argos-screenshots/`.
- Run the `ui-ux-pro-max` skill once before Task 4 (AGENTS.md: all UI work).
- No real paths, hostnames or tokens in stories or tests. Use `https://backups.example.com` and `borgui_EXAMPLE...`.
- Editing `backend.*` strings in `en.json` needs `python scripts/extract_backend_strings.py` afterwards (phase 1 note).
- Never over the UI either: the token is shown once, at creation, and never fetched again.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A user on Community opens `/settings/mcp`: they see the upgrade prompt, not a broken list or a 403 toast. (Task 5 test.)
2. An admin turns MCP off: users still reach the tab, see why it is off, and can still revoke connections; creating one is disabled. (Task 5 test.)
3. The admin cap is below a connection's chosen level: the row shows both the chosen level and what actually applies, and the dialog will not offer anything above the cap. (Task 4 tests.)
4. The Connected dialog is closed before the token was copied: a confirm step stops the token being lost, as `ApiTokensSection` does. (Task 4 test.)
5. Behind a reverse proxy under a `BASE_PATH`: the snippets use `window.location.origin + endpoint_path`, so `/borg/mcp` appears, never a bare `/mcp`. (Task 3 test.)

---

### Task 1: Backend, levels with no tools and calls today

**Files:**
- Modify: `app/mcp/registry.py` (add `top_level`)
- Modify: `app/api/mcp_connections.py` (`_check_rules`, `_config`, `_row`, `list_connections`)
- Modify: `frontend/src/locales/{en,de,es,it}.json` (`backend.errors.mcp.levelNotAvailable`), then `python scripts/extract_backend_strings.py`
- Modify: `docs/api.md` (the two new response fields)
- Test: `tests/unit/mcp/test_connections_api.py`

**Interfaces:**
- Produces: `top_level() -> Level` in `app/mcp/registry.py`, the highest level any registered tool needs (`Level.READ` when none).
- Produces: `GET /config` adds `"available_levels": list[str]`, every level name up to and including `top_level()`, in order.
- Produces: every connection row adds `"calls_today": int`, the number of `mcp_activity` rows for that connection since 00:00 UTC today.
- Produces: create or patch with a level above `top_level()` answers 422 `backend.errors.mcp.levelNotAvailable` with `params.level`.

Rule: `_check_rules` checks availability first, then the cap, then skip. Only the level being set is checked; a patch that only renames does not re-check the level. (Phase 1 already only calls `_check_rules` when the level or skip changes.)

English copy: `"levelNotAvailable": "{{level}} access is not available yet. This version of Borg UI has no {{level}} tools."`

- [ ] **Step 1: Write the failing tests**

Phase 1 tests create connections at `operate`, `manage` and `full`. Add an autouse fixture at the top of `test_connections_api.py` that monkeypatches `app.api.mcp_connections.top_level` to return `Level.FULL`, so those keep passing. The new tests override it.

```python
@pytest.mark.unit
def test_level_without_tools_is_refused(test_client, admin_headers, pro_plan, monkeypatch):
    monkeypatch.setattr("app.api.mcp_connections.top_level", lambda: Level.READ)
    response = test_client.post(
        f"{BASE}/connections", json={"name": "x", "access_level": "operate"}, headers=admin_headers
    )
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "key": "backend.errors.mcp.levelNotAvailable", "params": {"level": "operate"}
    }

@pytest.mark.unit
def test_config_lists_available_levels(test_client, auth_headers, pro_plan, monkeypatch):
    monkeypatch.setattr("app.api.mcp_connections.top_level", lambda: Level.READ)
    config = test_client.get(f"{BASE}/config", headers=auth_headers).json()
    assert config["available_levels"] == ["read"]

@pytest.mark.unit
def test_rows_count_calls_today(test_client, test_db, test_user, auth_headers, create_connection):
    row, _ = create_connection(auth_headers)
    # two rows today, one yesterday (created_at = today 00:00 UTC minus 1 s)
    ...
    listed = test_client.get(f"{BASE}/connections", headers=auth_headers).json()
    assert listed[0]["calls_today"] == 2
```

Also add `"available_levels"` to the expected dict in `test_config_read_by_anyone_written_by_admins`, and a registry unit test: `top_level()` is `Level.READ` with the phase 1 tools loaded.

- [ ] **Step 2: Run them to see them fail**

Run: `DATA_DIR=$(mktemp -d) SECRET_KEY=x .venv/bin/pytest tests/unit/mcp/test_connections_api.py tests/unit/mcp/test_registry.py -q`
Expected: the new tests fail (ImportError on `top_level`, or a missing key).

- [ ] **Step 3: Implement**

`top_level` is `max((s.level for s in REGISTRY.values()), default=Level.READ)`. `calls_today` for the list is one grouped count query (`GROUP BY connection_id`), not one query per row. `_row` takes `calls_today: int = 0`; create returns 0.

- [ ] **Step 4: Run the MCP suite and the strings check**

Run: `DATA_DIR=$(mktemp -d) SECRET_KEY=x .venv/bin/pytest tests/unit/mcp -q` and `python scripts/extract_backend_strings.py && git diff --stat app/mcp/backend_strings.json`
Expected: all pass, and the backend strings file gains the new key.

- [ ] **Step 5: Commit** (only at G2; until then, keep the work staged per task)

---

### Task 2: Frontend API client and types

**Files:**
- Modify: `frontend/src/services/api.ts` (add `mcpAPI` and types next to `tokensAPI`)
- Test: `frontend/src/services/__tests__/mcpApi.test.ts` (or the folder the existing `api.ts` tests use)

**Interfaces:**
- Produces, in `api.ts`:

```ts
export type McpLevel = 'read' | 'operate' | 'manage' | 'full'
export interface McpConfig { enabled: boolean; max_access_level: McpLevel; endpoint_path: string; available_levels: McpLevel[] }
export interface McpConnection {
  id: number; name: string; prefix: string; access_level: McpLevel; effective_level: McpLevel
  skip_routine_confirmations: boolean; last_client_name: string | null; last_client_version: string | null
  last_used_at: string | null; created_at: string; username: string | null; calls_today: number
}
export interface McpConnectionCreated extends McpConnection { token: string }
export type McpOutcome = 'ok' | 'error' | 'denied_level' | 'denied_rbac' | 'needs_confirmation' | 'confirmed'
export interface McpActivityRow { id: number; tool: string; effective_level: McpLevel; outcome: McpOutcome; error_key: string | null; target: string | null; duration_ms: number; created_at: string }
export const mcpAPI = {
  getConfig, updateConfig(body: Partial<Pick<McpConfig, 'enabled' | 'max_access_level'>>),
  list(all?: boolean), create(body: { name: string; access_level: McpLevel; skip_routine_confirmations?: boolean }),
  update(id: number, body: { name?: string; access_level?: McpLevel; skip_routine_confirmations?: boolean }),
  revoke(id: number), activity(id: number, beforeId?: number, limit = 50),
}
```

Paths are under `/settings/mcp/...`, matching phase 1. `activity` sends `before_id` only when given.

- [ ] **Step 1:** Test that `mcpAPI.list(true)` requests `/settings/mcp/connections?all=true` and `activity(4, 90)` requests `/settings/mcp/connections/4/activity?limit=50&before_id=90`, mocking the axios instance the way neighbouring service tests do. Watch it fail.
- [ ] **Step 2:** Implement. Run `cd frontend && npx vitest run src/services && npm run typecheck`. Expected: pass.

---

### Task 3: Client snippets (pure)

**Files:**
- Create: `frontend/src/components/mcp/clientSnippets.ts`
- Test: `frontend/src/components/mcp/__tests__/clientSnippets.test.ts`

**Interfaces:**
- Produces: `mcpEndpointUrl(endpointPath: string, origin = window.location.origin): string`
- Produces: `type McpClientId = 'claude-code' | 'claude-desktop' | 'cursor' | 'vscode' | 'windsurf' | 'generic'`
- Produces: `buildClientSnippets(url: string, token: string): { id: McpClientId; label: string; where: string | null; language: 'bash' | 'json' | 'text'; code: string }[]`, in that order. `label` is the product name (not translated). `where` is the config file path the user pastes into, or null.

Snippets as of 2026-11-18. **Step 3 re-checks each against the client's current docs** (spec 5.12) and records the check in the ledger:

| Client | where | code |
|---|---|---|
| Claude Code | null | `claude mcp add --transport http borg-ui <url> --header "Authorization: Bearer <token>"` |
| Claude Desktop | `claude_desktop_config.json` | `{"mcpServers":{"borg-ui":{"command":"npx","args":["-y","mcp-remote","<url>","--header","Authorization:${AUTH_HEADER}"],"env":{"AUTH_HEADER":"Bearer <token>"}}}}` (the env indirection is mcp-remote's documented workaround for spaces in args) |
| Cursor | `~/.cursor/mcp.json` | `{"mcpServers":{"borg-ui":{"url":"<url>","headers":{"Authorization":"Bearer <token>"}}}}` |
| VS Code | `.vscode/mcp.json` | `{"servers":{"borg-ui":{"type":"http","url":"<url>","headers":{"Authorization":"Bearer <token>"}}}}` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | `{"mcpServers":{"borg-ui":{"serverUrl":"<url>","headers":{"Authorization":"Bearer <token>"}}}}` |
| Generic | null | two lines: `URL: <url>` and `Header: Authorization: Bearer <token>` |

JSON snippets are `JSON.stringify(obj, null, 2)`, so they are always valid JSON.

- [ ] **Step 1: Failing tests**

```ts
it('keeps the base path', () => {
  expect(mcpEndpointUrl('/borg/mcp', 'https://backups.example.com')).toBe('https://backups.example.com/borg/mcp')
})
it('puts url and token in every snippet', () => {
  for (const s of buildClientSnippets('https://backups.example.com/mcp', 'borgui_EXAMPLE')) {
    expect(s.code).toContain('https://backups.example.com/mcp')
    expect(s.code).toContain('borgui_EXAMPLE')
  }
})
it('json snippets parse', () => {
  buildClientSnippets('https://b.example.com/mcp', 'borgui_X')
    .filter((s) => s.language === 'json')
    .forEach((s) => expect(() => JSON.parse(s.code)).not.toThrow())
})
it('claude code is one command', () => {
  expect(buildClientSnippets('https://b.example.com/mcp', 'borgui_X')[0].code)
    .toBe('claude mcp add --transport http borg-ui https://b.example.com/mcp --header "Authorization: Bearer borgui_X"')
})
```

- [ ] **Step 2:** Run `cd frontend && npx vitest run src/components/mcp`; expect a failure (module not found).
- [ ] **Step 3:** Check the six snippets against current docs (Claude Code `claude mcp add` help, the mcp-remote README, and the Cursor, VS Code and Windsurf MCP docs). Fix the table and the code if anything moved. Then implement.
- [ ] **Step 4:** Tests pass.

---

### Task 4: Connection components

Before starting this task, run the `ui-ux-pro-max` skill and apply its guidance to the layouts below, staying within the existing MUI look (`ApiTokensSection` and `TintedTile` are the closest neighbours).

**Files (each with a `.stories.tsx` and a test under `frontend/src/components/mcp/__tests__/`):**
- Create: `frontend/src/components/mcp/McpLevelCards.tsx`
- Create: `frontend/src/components/mcp/McpConnectionDialog.tsx`
- Create: `frontend/src/components/mcp/McpConnectedDialog.tsx`
- Create: `frontend/src/components/mcp/McpConnectionsList.tsx`
- Create: `frontend/src/components/mcp/McpActivityPanel.tsx`
- Create: `frontend/src/components/mcp/storyFixtures.ts` (made-up connections and activity, no real data)

**Interfaces:**
- Consumes: Task 2 types, Task 3 `buildClientSnippets` and `mcpEndpointUrl`.
- Produces:
  - `McpLevelCards({ value, onChange, available, cap }: { value: McpLevel; onChange(l: McpLevel): void; available: McpLevel[]; cap: McpLevel })`: four radio cards in level order. A card is disabled when it is not in `available` (chip "Coming soon") or is above `cap` (chip "Above your administrator's limit"). It uses `role="radiogroup"` and arrow-key navigation.
  - `McpConnectionDialog({ open, mode: 'create' | 'edit', connection?: McpConnection, config: McpConfig, onClose, onSubmit(body): Promise<void> })`: built on `ResponsiveDialog`. It has a name field and `McpLevelCards`. The "skip routine confirmations" switch shows only while `full` is picked (unreachable in phase 2, but present for phase 5). Submit stays disabled while the name is blank. Backend errors show through `translateBackendKey`.
  - `McpConnectedDialog({ open, token, endpointUrl, onClose })`: shows the token once with a copy button, a warning that it will not be shown again, and tabs, one per `buildClientSnippets` entry, each with a `where` line and a copy button. Closing before any copy asks "Close without copying the token?", as `ApiTokensSection` does.
  - `McpConnectionsList({ connections, showOwner, onEdit, onRevoke, onOpenActivity, disabledReason? })`: one row per connection. It shows the name and prefix, and a level chip that also reads "applies as Read" when `effective_level !== access_level`. It shows the client last seen ("Claude Code 1.2, 3 min ago", or "Not connected yet" when `last_client_name` is null), "N calls today", and actions to edit, revoke and open activity. Revoke asks first, using a small `ResponsiveDialog` confirm. `showOwner` adds the username. There is an empty state.
  - `McpActivityPanel({ connectionId })`: fetches through `mcpAPI.activity` with `useInfiniteQuery`, using `before_id` = the last row's id. Each row shows the tool name, an outcome chip (ok = success tone, error = error, denied_level and denied_rbac = warning, needs_confirmation and confirmed = info; tones from `components/shared/tones.ts`), the target, the duration and a relative time. A "Load more" button shows while the last page came back full. There is an empty state.

Tests (names and the assertion each one makes):
- `McpLevelCards`: `disables levels without tools` (only Read is enabled when available is `['read']`); `disables levels above the cap` (cap is `operate` and all are available, so manage and full are disabled with the cap chip).
- `McpConnectionDialog`: `submit needs a name`; `shows the skip switch only at full`.
- `McpConnectedDialog`: `shows every client tab`; `asks before closing when nothing was copied`.
- `McpConnectionsList`: `shows the effective level when the cap lowers it`; `shows not connected yet`; `asks before revoking`.
- `McpActivityPanel`: `loads older rows with before_id` (mock two pages and assert the second call's `beforeId`).

Stories: `McpLevelCards` (read only available; capped at operate; all available). `McpConnectionDialog` (create; edit; backend error). `McpConnectedDialog` (default; Generic tab selected). `McpConnectionsList` (empty; three rows including one capped and one never connected; admin view with owners; MCP turned off). `McpActivityPanel` (with every outcome; empty; with more to load).

- [ ] **Step 1:** Write all the tests above and watch them fail.
- [ ] **Step 2:** Implement the components one at a time, re-running `npx vitest run src/components/mcp` after each.
- [ ] **Step 3:** Write the stories. Run `npm run typecheck && npm run lint`.

---

### Task 5: The MCP settings tab

**Files:**
- Create: `frontend/src/components/McpTab.tsx` (composition only), with `McpTab.stories.tsx` and `__tests__/McpTab.test.tsx`
- Modify: `frontend/src/pages/Settings.tsx` (tab id `mcp` for every user, placed after `notifications` in the base tabs)
- Modify: `frontend/src/components/AppSidebar.tsx`: a Personal sub-item `{ name: 'AI assistants (MCP)', href: '/settings/mcp', icon: Bot }` after Notifications, plus `navLabel` and the Personal auto-expand match for `/mcp`
- Modify: `frontend/src/utils/analytics.ts` (`'mcp'` in `ROUTE_WORDS.settings`)

**Interfaces:**
- Consumes: everything from Tasks 2 to 4.
- `McpTab` renders `<PlanGate feature="mcp" surface="settings_mcp">`. Inside it queries `['mcp-config']` and `['mcp-connections', all]`. It has a header with a description and a "New connection" button, the list, the dialogs, and an activity drawer or inline panel for the selected connection. Admins (`user.role === 'admin'` or the existing admin check `useAuth` exposes) get an "Everyone's connections" switch that sets `all=true` and `showOwner`.
- When `config.enabled === false`, an info alert reads "MCP is turned off by your administrator. Existing connections cannot be used until it is turned back on." and "New connection" is disabled. Revoke still works.

Tests:
- `shows the upgrade prompt on community` (mock `usePlan` so `can('mcp')` is false; the upgrade prompt renders and `mcpAPI.list` is not called).
- `turned off disables create but keeps revoke`.
- `admin can switch to everyone's connections` (the toggle calls `list(true)`).
- `create then shows the token once` (submit, then the Connected dialog holds the token; after it closes, the token is nowhere in the DOM).
- The existing sidebar and route-word tests are updated: `AppSidebar.test.tsx` expects the new item, and the `ROUTE_WORDS` test (which checks `Settings.tsx`) passes.

- [ ] **Step 1:** Write the tests and watch them fail.
- [ ] **Step 2:** Implement and wire the tab.
- [ ] **Step 3:** Run `npx vitest run src/components src/pages src/utils && npm run typecheck`. Expected: pass.

---

### Task 6: Admin section in System settings

**Files:**
- Create: `frontend/src/components/system-settings/McpAccessSection.tsx`, with a story and `__tests__/McpAccessSection.test.tsx`
- Modify: `frontend/src/components/system-settings/config.ts` (seventh section tab "AI assistants (MCP)")
- Modify: `frontend/src/components/SystemSettingsTab.tsx` (`activeSection === 6` renders the section)

**Interfaces:**
- `McpAccessSection()` owns its own query (`['mcp-config']`, shared with Task 5) and its own save. It does not join the tab's big Save button, because the MCP config has its own endpoint. It has an enable switch and a max-level select listing all four levels. The cap is a ceiling, so levels with no tools yet are allowed, with helper text saying only Read has tools today. It is wrapped in `PlanGate feature="mcp"`. Saving calls `mcpAPI.updateConfig`, invalidates `['mcp-config']` and `['mcp-connections']`, and shows a toast.
- Lowering the cap shows helper text: "Connections above this level keep their setting and work at this level until you raise it again." (spec 5.2 rule 3).

Tests: `saves the switch and cap`; `shows the upgrade prompt on community`. Update `SystemSettingsTab.test.tsx` if it counts section tabs.

- [ ] **Step 1:** Write the tests and watch them fail.
- [ ] **Step 2:** Implement.
- [ ] **Step 3:** Run `npx vitest run src/components/system-settings src/components/__tests__/SystemSettingsTab.test.tsx`. Expected: pass.

---

### Task 7: Strings and docs

**Files:**
- Modify: `frontend/src/locales/{en,de,es,it}.json` (all `mcp.*`, `navigation.settings.mcp` and `systemSettings.mcp*` keys used by Tasks 4 to 6; formal "Sie" in German, matching the existing locale)
- Create: `docs/mcp.md` (front matter `title: AI assistants (MCP)`, a `nav_order` after `ssh-keys.md`, and a description)
- Modify: `docs/navigation.md` (Personal table: an "AI assistants (MCP)" row; System row mentions the MCP section)
- Modify: `docs/plan-content.json`: an entry `{ id: "mcp", plan: "pro", label: "AI assistants (MCP)", description, *_localized for es/de/it, availability: "included" }`, inserted after `archive_history`

`docs/mcp.md` sections, short:
1. What it is: talk to Borg UI from Claude Code, Claude Desktop, Cursor, VS Code, Windsurf or any MCP client, in Pro, Lite and Enterprise.
2. Access levels: the four levels table from spec 5.2. Today only Read has tools; the others arrive in later updates.
3. Creating a connection: the steps, and that the token is shown once.
4. Connecting your client: the six snippets from Task 3 with `<your-url>` and `<token>`.
5. What the AI can do at Read: a short list grouped as in spec 5.5's read tools, plus three example prompts ("What failed last night?", "Where is my space going?", "When did Photos last back up?").
6. Activity log: what is recorded (tool, outcome, target, duration), and that arguments are never stored. Kept 30 days or 20,000 rows.
7. Admin controls: the switch and cap. Lowering the cap keeps each connection's setting.
8. Security: MCP tokens only work on `/mcp`, not the REST API; RBAC still applies; secrets never pass through the AI; revoke from the list.

- [ ] **Step 1:** Fill the locale keys. Run `cd frontend && npm run check:locales`. Expected: pass.
- [ ] **Step 2:** Write the docs. Validate the JSON with `python -c "import json;json.load(open('docs/plan-content.json'))"`, plus any plan-content test (`grep -rl plan-content tests frontend/src | head`).

---

### Task 8: Verification (G2)

- [ ] Backend: `DATA_DIR=$(mktemp -d) SECRET_KEY=x .venv/bin/pytest tests/unit/mcp tests/integration/test_mcp_smoke.py tests/integration/test_mcp_real_borg.py -q`, plus the route access and string guard suites touched in phase 1. Ruff is clean.
- [ ] Frontend: `npm run typecheck && npm run lint && npx vitest run && npm run check:locales`.
- [ ] Storybook: render every new story in light and dark mode (fnm v24, copy the darwin-arm64 bindings into the worktree per memory) and screenshot each. Check there is no horizontal scroll at phone width for the dialog and the list.
- [ ] Manual pass (spec 5.14, end of phase 2): on a throwaway `DATA_DIR`, with notifications, MQTT and schedules stripped from any copied DB, run the app. Create a Read connection in the UI and paste the Claude Code snippet into a real `claude` session; `list_repositories` should answer. Then check the activity panel shows the call, turning MCP off makes the next call answer "turned off", and revoking makes the client fail authentication. Repeat the connection with Claude Desktop through `mcp-remote` if it is installed; otherwise record that it was not checked.
- [ ] Update spec 8.1: set phase 1 to `done` (merged as PR #1544) and phase 2 to `implemented`, with notes and rulings.
- [ ] Gate G2: report and wait.
