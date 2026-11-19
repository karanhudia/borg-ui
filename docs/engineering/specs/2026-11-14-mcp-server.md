# MCP server (Pro)

Status: designed 2026-11-14 with Karan. Not started.

## 1. Intent

A Pro user should be able to run Borg UI entirely from an AI client
(Claude Code, Claude Desktop, Cursor, VS Code, Windsurf, any MCP client):
ask questions ("what failed last night?", "where is my space going?"),
operate ("back up Photos now", "restore last Tuesday's ~/notes to /tmp"),
and set things up ("back up my Postgres container every night, keep 14
days"). Karan's words: "if it was me, i would do everything from mcp, the
whole user flow."

It must feel like Borg UI: friendly, informative, a little fun. Tool
titles read like the app's own buttons, results read like a helpful
colleague, not a JSON dump.

Why now: a Pro differentiator that no other Borg front end has, and a
natural fit for the self-hosting audience that already lives in AI
clients. Success is measured by the usage events in section 5.13.

## 2. Goals, non-goals, anti-goals

Goals

- The whole user flow over MCP: questions, operations, setup, destructive
  maintenance, under the user's own RBAC.
- User-controlled power: every MCP connection has an access level, and
  destructive actions go through preview then confirm.
- Admin control on shared installs: an on/off switch and a cap on the
  level users may grant.
- Usage visible in the borg-ui-analytics dashboard.
- Pro, Lite and Enterprise get it; feature trials work.

Non-goals (this round)

- OAuth sign-in for claude.ai web/mobile and ChatGPT connectors (phase 8,
  later, see section 7).
- MCP Apps interactive cards (phase 7, later).
- MCP resources and sampling. Tools and prompts only.
- A separate MCP process, package, or port.
- Licensing actions, API token management and MCP settings over MCP.

Anti-goals (a failure even if it works)

- An AI wiping a repository from one misread sentence.
- An MCP connection doing more than its level allows, by any path,
  including using its token against the REST API directly.
- An AI raising its own level, minting tokens, or changing MCP settings.
- Secrets (repository passphrases, private keys, remote passwords,
  notification URLs with tokens, user passwords) passing through the AI
  vendor. See 5.9.
- 339 auto-generated tools with route-shaped names.
- Tool output that floods the client's context (a million-file listing,
  a full log).
- Duplicated business logic that drifts from what the web UI does.

## 3. Constraints found in the code

- Business logic lives in fat routers (`app/api/repositories.py` 8k
  lines, `ssh_keys.py` 3.4k, `schedule.py` 3k), not services. RBAC, plan
  gates and validation are enforced at route level.
- Borg 2 repositories are served by `/api/v2/...` for about ten
  operations (archives list/info/delete, run, prune, compact, check,
  repository create/import/info/stats). The frontend routes these in
  `frontend/src/services/borgApi/client.ts`. Rule: no Borg 2 branching
  inside existing v1 files.
- Personal access tokens exist (`api_tokens`, `borgui_` prefix, bcrypt
  hash, resolved in `app/core/security.py:_resolve_api_token_user`). They
  carry the user's full power and no scope.
- Plan gating: `FEATURES` in `app/core/features.py`. Lite is gated as Pro
  (`licensing_service.py`, `license_plan` vs `access_level`), so a single
  `"mcp": Plan.PRO` covers Pro, Lite, Enterprise and trials.
- Two gunicorn workers by default (`app/config.py: workers = 2`). Any MCP
  state shared between calls (confirmation codes, rate limits) lives in
  the database, not memory.
- `BASE_PATH` deployments: the MCP endpoint lives under it.
- Backend error responses carry `detail.key` (`backend.errors.*`); English
  strings live in `frontend/src/locales/en.json` under `backend`.
- Backend analytics: `app/services/error_reporter.py` already posts to
  `t.borgui.com/e` with consent caching, a queue on one daemon thread,
  rate caps and the per-user `analytics_enabled` opt-out.
- Ingest allowlist: new event names must be added to `src/catalog.ts` in
  borg-ui-analytics and deployed before the release that sends them.

## 4. Approaches

A. Generate tools from the OpenAPI schema (`fastapi-mcp` and similar).
Fast, but 339 route-shaped tools, no preview and confirm, destructive
routes exposed raw. Rejected: contradicts every goal in section 2.

B. Hand-written tools calling the service layer directly. Clean in
theory, but the logic sits in routers, so every tool would re-implement
validation, RBAC and Borg 1/2 handling. Rejected: thousands of lines of
drift-prone duplication.

C. Hand-written, task-shaped tools that call the existing REST routes
in-process. Chosen by Karan 2026-11-14. Every rule the web UI follows
applies for free; the MCP layer adds only naming, copy, level checks,
preview and confirm, output shaping and redaction. Trade-off: tools
depend on API response shapes; one contract test per tool catches drift
in CI.

## 5. Design

### 5.1 Feature key and gating

- `FEATURES["mcp"] = Plan.PRO`. Add `mcp` to the `feature` list in the
  analytics journey catalog (`Plan - FeatureBlocked` / `FeatureUsed`).
- The `/mcp` endpoint checks `has_feature(db, "mcp")` on every request.
  When refused it answers with an MCP error whose message is friendly and
  names the upgrade path ("MCP access is part of Borg UI Pro. Your
  install is on Community. See Settings > Plan."), not a bare 403.
- The settings tab (5.12) sits behind `PlanGate` with `feature="mcp"`.

### 5.2 Connections and access levels

An MCP connection is a row in `api_tokens` with new columns (one alembic
migration; recompute heads against fetched `origin/main` first):

| Column | Type | Meaning |
|---|---|---|
| `kind` | `api` \| `mcp`, default `api` | Existing rows stay `api`. |
| `access_level` | `read` \| `operate` \| `manage` \| `full`, null for `api` | Chosen at creation, editable. |
| `skip_routine_confirmations` | bool, default false | Only meaningful at `full`. See 5.6. |
| `last_client_name`, `last_client_version` | string, null | From the MCP `initialize` handshake, shown in the UI. |

Levels, cumulative:

| Level | Adds |
|---|---|
| `read` | Everything that only looks: status, problems, repositories, archives, file browsing and search, jobs, logs, plans, schedules, connections, settings. |
| `operate` | Running what exists: start, cancel and retry backups and plans, check, compact, restore checks, restore to a new location, mount and unmount, run a schedule now, tests (SSH, notification, script), index resync, pause and resume background work. |
| `manage` | Creating and editing configuration: repositories, SSH keys and connections, backup plans, schedules, scripts, notification channels, rclone remotes, agents, system settings, users (admins only, via RBAC). |
| `full` | Destructive actions, always through preview and confirm (5.6). |

Rules

1. Token isolation. REST authentication rejects `kind = mcp` tokens with
   401 (`backend.errors.auth.mcpTokenNotForApi`). `/mcp` rejects
   `kind = api` tokens and JWTs, cookies and proxy-auth headers. One
   choke point each: `_resolve_api_token_user` for REST, the MCP auth
   dependency for `/mcp`.
2. RBAC still applies. A connection never exceeds its user. A viewer's
   `full` connection still only reads, because the routes refuse.
3. Admin controls, in System settings: `mcp_enabled` (default true) and
   `mcp_max_access_level` (default `full`). Effective level per call is
   `min(connection.access_level, mcp_max_access_level)`. Lowering the cap
   never rewrites rows; raising it restores them. When disabled, `/mcp`
   answers every call with a friendly "turned off by your administrator".
4. A connection's tools list is filtered to its effective level, so the
   AI never sees tools it cannot call. A call to a hidden tool still
   fails with a clear message (clients cache lists).
5. Never over MCP: token management, MCP settings, the admin switch,
   licensing, password changes. No tool exists for them.

Deleting a connection revokes it (existing token delete). Existing
personal API tokens are untouched.

### 5.3 Transport and server

- Official Python `mcp` SDK (FastMCP), Streamable HTTP, stateless mode,
  mounted in the FastAPI app at `{BASE_PATH}/mcp`. Pin the exact version
  in `requirements.txt`. No legacy SSE transport.
- Stateless so either gunicorn worker answers any call. Progress
  notifications ride on the response stream of the call that asked for
  them (5.8); nothing depends on a session living on one worker.
- Auth: `Authorization: Bearer borgui_...` only. Validate the `Origin`
  header per the MCP spec (reject browser origins that are not the
  install's own) to block DNS rebinding.
- Rate limit per connection, stored in the database: builder's call on
  numbers (proposal: 120 calls per minute, friendly "slow down" message).
- Server identity: name `borg-ui`, title `Borg UI`, version = app
  version, the Borg UI icon (MCP `icons`), and an `instructions` string
  that teaches the model Borg UI's concepts in about 300 words: a
  repository holds archives; a backup plan says what to back up, where,
  when and how long to keep it; schedules run plans; checks verify; prune
  applies retention, compact frees space; restores never overwrite unless
  asked; prefer plans over one-off backups for anything recurring; for
  anything with secrets, hand off to the web UI (5.9).

### 5.4 Tool execution (in-process)

Package: `app/mcp/` (new). Layout is the builder's call within these
parts: `server.py` (FastMCP app, auth, level filter), `client.py`
(in-process REST client), `borg_routes.py` (Borg 1/2 routing),
`resolve.py` (names to ids), `render.py` (copy and shaping),
`confirm.py` (5.6), `activity.py` (5.11), `tools/<domain>.py`,
`prompts.py`.

- `client.py` calls the app through `httpx.ASGITransport` against the
  same FastAPI instance. It authenticates as the connection's user with a
  short-lived internal credential minted per tool call (proposal: a JWT
  with a 60 s lifetime and an `mcp_connection_id` claim), never the
  user's MCP token. The builder must verify the credential is accepted in
  every auth mode the app supports (local, OIDC, proxy auth) and that it
  respects disabled users.
- `borg_routes.py` mirrors `borgApi/client.ts`: for a repository with
  `borg_version == 2` the split operations go to `/api/v2/...`. Lives
  only in `app/mcp/`; no edits to v1 files.
- Each tool declares its level and the routes it may call. A contract
  test asserts that no tool below `full` declares a `DELETE` route or any
  route in the destructive list (5.6), and that every declared route
  exists in the app.
- `resolve.py`: tools accept names or ids for repositories, archives,
  plans, schedules, connections, scripts, channels. Match by id, then
  exact name, then case-insensitive unique prefix. Ambiguity returns the
  candidates as a friendly question ("I found two: *Photos* and *Photos
  old*. Which one?"), never a guess.
- Errors: a REST error with `detail.key` renders through the English
  strings in `en.json` `backend` subtree. The builder decides how that
  subtree reaches the runtime image (proposal: a build step extracts it
  to `app/mcp/backend_strings.json`). Unknown keys fall back to a generic
  sentence plus the key. Plan refusals render the upgrade sentence.
- Redaction at one choke point: every tool result passes through
  `app.utils.redaction` plus a field denylist (`passphrase`,
  `private_key`, `password`, `token`, `secret`, notification URLs) before
  it leaves `render.py`. A test scans every tool's output on fixture data
  for those fields.

### 5.5 Tool catalog

Names are snake_case verbs; each has a `title` (shown by Claude Desktop),
a description written in Borg UI's voice, MCP annotations (`readOnlyHint`,
`destructiveHint`, `idempotentHint`, `openWorldHint` false), an input
schema with examples, and both text content and `structuredContent`.
Final wording is the builder's within 5.7. Level codes: R read, O
operate, M manage, F full. Confirm codes: C always, c skippable (5.6).

Overview and health

| Tool | Title | Level |
|---|---|---|
| `get_overview` | See how my backups are doing | R |
| `list_problems` | Find what needs attention | R |
| `get_upcoming_runs` | See what runs next | R |
| `get_system_info` | About this Borg UI | R |

Repositories and space

| Tool | Title | Level |
|---|---|---|
| `list_repositories` | List repositories | R |
| `get_repository` | Look at a repository | R |
| `get_repository_space` | See where the space goes | R |
| `preview_prune` | Preview a prune | O |
| `compare_retention` | Compare retention policies | R |

Archives and files

| Tool | Title | Level |
|---|---|---|
| `list_archives` | List archives | R |
| `get_archive` | Look at an archive | R |
| `browse_archive` | Browse files in an archive | R |
| `search_files` | Search backed-up files | R |
| `get_file_history` | Trace a file's history | R |
| `compare_archives` | See what changed between archives | R |

Jobs and activity

| Tool | Title | Level |
|---|---|---|
| `list_activity` | Show recent activity | R |
| `list_running_jobs` | See what's running | R |
| `get_job` | Check on a job | R |
| `get_job_log` | Read a job's log | R |
| `wait_for_job` | Wait for a job to finish | R |
| `explain_failure` | Explain why a job failed | R |

`explain_failure` gathers the job, the tail of its log, the backend error
key and recent similar failures, and returns them shaped for the model
to reason over. It does not guess the cause itself.

Plans, schedules, sources

| Tool | Title | Level |
|---|---|---|
| `list_backup_plans` / `get_backup_plan` | List / Look at backup plans | R |
| `list_plan_runs` | Show a plan's runs | R |
| `list_schedules` / `get_schedule` | List / Look at schedules | R |
| `check_cron` | Check a schedule expression | R |
| `browse_server_folders` | Browse folders on the server | R |
| `browse_agent_folders` | Browse folders on an agent machine | R |
| `discover_sources` | Find databases and containers | O |

Connections and settings (read)

| Tool | Title | Level |
|---|---|---|
| `list_ssh_connections` / `list_ssh_keys` | List SSH connections / keys | R |
| `list_agents` | List agent machines | R |
| `list_rclone_remotes` | List cloud remotes | R |
| `list_scripts` | List scripts | R |
| `list_notification_channels` | List notification channels | R |
| `get_settings` | Look at settings | R |
| `list_users` | List users (admins) | R |

Operate

| Tool | Title | Level |
|---|---|---|
| `start_backup` | Back up now | O |
| `run_backup_plan` | Run a backup plan | O |
| `run_schedule_now` | Run a schedule now | O |
| `cancel_job` | Cancel a job | O |
| `retry_job` | Retry a job | O |
| `check_repository` | Check a repository | O |
| `compact_repository` | Compact a repository | O |
| `run_restore_check` | Run a restore check | O |
| `preview_restore` | Preview a restore | O |
| `restore_files` | Restore files (new location) | O |
| `mount_archive` / `unmount_archive` | Mount / Unmount an archive | O |
| `refresh_repository` | Refresh repository info | O |
| `test_ssh_connection` | Test an SSH connection | O |
| `test_notification` | Send a test notification | O |
| `test_script` | Test a script | O |
| `pause_background_work` / `resume_background_work` | Pause / Resume background work | O |

`restore_files` at O refuses any destination that already contains the
paths being restored; overwriting is the F path below.

Manage

| Tool | Title | Level |
|---|---|---|
| `create_repository` | Create a repository | M |
| `import_repository` | Connect an existing repository | M |
| `update_repository` | Change repository settings | M |
| `set_check_schedule` / `set_restore_check_schedule` | Schedule checks / restore checks | M |
| `generate_ssh_key` | Create an SSH key | M |
| `add_ssh_connection` | Add an SSH connection | M |
| `update_ssh_connection` | Change an SSH connection | M |
| `trust_host_key` | Trust a server's host key | M |
| `create_backup_plan` | Create a backup plan | M |
| `update_backup_plan` | Change a backup plan | M |
| `set_backup_plan_enabled` | Turn a backup plan on or off | M |
| `create_schedule` / `update_schedule` | Create / Change a schedule | M |
| `set_schedule_enabled` / `duplicate_schedule` | Turn on or off / Copy a schedule | M |
| `create_script` / `update_script` | Create / Change a script | M |
| `assign_script` | Attach a script to a repository | M |
| `update_notification_channel` | Change a notification channel's events | M |
| `update_rclone_remote` | Change a cloud remote | M |
| `upgrade_agents` | Upgrade agent machines | M |
| `update_settings` | Change settings | M |
| `create_user` / `update_user` | Add / Change a user (admins) | M |

`create_backup_plan` is the centrepiece: one call takes sources (local
paths, SSH connection paths, agent paths, discovered databases or
containers), one or more repositories, a schedule (validated like
`SchedulePicker` does, with timezone), retention, compression,
exclusions and scripts, and answers with a readable summary of the plan
it made plus the next run time. When something is missing it says what,
instead of inventing defaults the user never heard; defaults it does
apply are listed in the answer.

Full (destructive)

| Tool | Title | Level | Confirm |
|---|---|---|---|
| `prune_repository` | Prune old archives | F | c |
| `delete_archives` | Delete archives | F | c |
| `delete_backup_plan` | Delete a backup plan | F | c |
| `delete_schedule` | Delete a schedule | F | c |
| `delete_script` | Delete a script | F | c |
| `delete_notification_channel` | Delete a notification channel | F | c |
| `delete_ssh_connection` / `delete_ssh_key` | Delete an SSH connection / key | F | c |
| `forget_host_key` | Forget a host key | F | c |
| `remove_agent` | Remove an agent machine | F | c |
| `clean_up_logs` | Clean up old logs | F | c |
| `restore_files_overwrite` | Restore files over existing ones | F | C |
| `break_repository_lock` | Break a repository lock | F | C |
| `remove_repository` | Remove a repository from Borg UI | F | C |
| `delete_repository_permanently` | Delete a repository and its data | F | C |
| `wipe_repository` | Wipe all archives | F | C |
| `delete_user` | Delete a user (admins) | F | C |

About 95 tools in all. The builder may merge or split where a cleaner
shape emerges, keeping levels and confirm codes.

### 5.6 Preview and confirm

Every F tool runs in two calls.

1. Call without `confirmation_code`: nothing changes. The tool computes
   a preview, reusing the app's existing previews where they exist (prune
   preview, wipe preview, restore preview, archive info for deletes), and
   answers with a plain summary ("Pruning *Photos* with 7d 4w 6m would
   delete 14 archives, oldest 2025-03-01, and free at least 38 GB.") plus
   a code (`confirm-7KQ2`) valid for 5 minutes. The text tells the model
   to show the summary to the user and ask before confirming.
2. Call again with the same arguments plus `confirmation_code`: it runs.

Stored in a new table `mcp_confirmations` (`code` hashed, `connection_id`,
`tool`, `args_hash` of the canonicalised arguments without the code,
`summary`, `expires_at`, `used_at`). A code is single-use, bound to the
connection, tool and exact arguments. A mismatch fails with a friendly
message and a fresh preview. Expired codes are pruned daily.

`skip_routine_confirmations` (connection setting, only at `full`): the
`c` tools run on the first call and the result says so ("Done. You've
turned off confirmations for routine deletes on this connection."). `C`
tools always confirm. Default off.

### 5.7 Voice and copy

- English only for tool titles, descriptions and results. The model
  answers the user in their language; translating tool copy adds cost
  without reaching the user. This is not partial localization: the web
  UI side (5.12) is fully localized.
- Results lead with the outcome in one line, then the useful details,
  then a next step the user might want ("Want me to wait for it?").
  Markdown, short. Status glyphs allowed (✓ ✗ ⏳ ⚠). No em dashes.
- Sizes humanized with raw bytes in `structuredContent`; times relative
  plus absolute in the user's timezone preference; durations from the
  previous comparable run as an estimate ("usually ~6 min").
- Names in italics, ids only in `structuredContent` unless needed to
  disambiguate.
- One style guide file in `app/mcp/` with examples, reviewed with Karan
  in phase 1's plan, so every later phase writes in the same voice.

### 5.8 Long-running work and output limits

- Starting anything returns at once with the job id, what it is doing,
  and the estimate. `wait_for_job` blocks up to 45 s, sends MCP progress
  notifications when the client passed a `progressToken`, and returns
  either the result or "still running, x% done, ask me again".
- Lists default to 25 items, max 200, with an opaque cursor. File
  browsing pages by directory. Logs return the last 200 lines, max 1000,
  with a `before` cursor. Every truncated answer says what was left out
  and how to get more.
- Hard cap per result (proposal: 60 kB of text), enforced in `render.py`.

### 5.9 Secrets: never through the AI

Secrets never go through the AI vendor. Karan chose "generate, reveal
once" for repository passphrases, 2026-11-14.

Repository passphrase (generate, reveal once)

- `create_repository` over MCP generates a strong passphrase server side
  (same generator strength the wizard uses, or `secrets` with at least
  128 bits if the wizard has none), stores it the way the app already
  stores passphrases (encrypted at rest), and never returns it. Default
  encryption is the app's own default for that Borg version.
- The repository gets a new flag `passphrase_unsaved` (bool, default
  false; set only by this path). While it is set:
  - the repository page shows a "Save your passphrase" banner (not a
    left accent border; see AGENTS.md UI preferences) with a Reveal
    button and, for keyfile modes, the keyfile download;
  - `list_problems` and the dashboard's attention list include it, so
    the AI reminds the user and the web UI does too ("*Photos* has a
    passphrase you haven't saved yet. Without it the backups cannot be
    restored if Borg UI's database is lost.");
  - the MCP answer to `create_repository` says the passphrase was
    generated, why saving it matters, and links to the repository page.
- Reveal: a new REST route `POST /api/repositories/{id}/passphrase/reveal`
  that works only while `passphrase_unsaved` is set, only for a user who
  may edit the repository, and only after re-authentication: the current
  password for local accounts; for OIDC or proxy-auth accounts (no local
  password), typing the repository name. It must refuse the MCP internal
  credential (5.4, `mcp_connection_id` claim) and every token: browser
  session only. Each reveal is logged.
- "I've saved it" (`POST .../passphrase/acknowledge`) clears the flag.
  After that the passphrase is never shown again, matching today's rule
  that no response returns a passphrase. Revealing alone does not clear
  the flag, so a user who closes the dialog is still reminded.
- No MCP tool reveals or acknowledges. The reveal is a web UI action.
- These two routes are the only change to existing repository code;
  they are not Borg 2 specific, so they live in the v1 router as shared
  repository routes.

Other secrets (hand off to the web UI)

- Importing an existing encrypted repository needs the user's
  passphrase, so `import_repository` returns a link to the import dialog
  prefilled with everything else.
- SSH key deploy needing a remote password, notification channels whose
  URL holds a token, rclone remotes needing OAuth or keys, user
  passwords: the tool prepares everything it can and returns a deep link
  to the exact web UI dialog, prefilled, plus one line of what to enter
  there.
- Deep links use `PUBLIC_BASE_URL` when set, else the request's host.
  The builder adds the query parameters the target dialogs need to open
  prefilled; that is the only change to existing pages.

### 5.10 Prompts

Shown as slash commands by Claude Code and as prompt pickers elsewhere.
Each is a short guided flow that uses the tools above.

| Prompt | Does |
|---|---|
| `health-check` | Overview, problems, stale repositories, failing checks, a short verdict. |
| `set-up-backup` | Asks what to protect, where, how often, how long; builds a plan. |
| `restore-a-file` | Finds the file across archives, previews, restores to a safe place. |
| `free-up-space` | Space breakdown, retention comparison, prune preview, compact. |
| `why-did-it-fail` | Picks the latest failure and walks through `explain_failure`. |
| `weekly-report` | What ran, what failed, growth, what to look at. |

### 5.11 Activity log

New table `mcp_activity`: `connection_id`, `user_id`, `tool`,
`effective_level`, `outcome` (`ok`, `error`, `denied_level`,
`denied_rbac`, `needs_confirmation`, `confirmed`), `error_key`,
`target` (a short redacted label such as "repository Photos"),
`duration_ms`, `created_at`. No arguments are stored. Retention: 30 days
or 20,000 rows, pruned by the existing daily cleanup. Read through a new
REST route for the settings UI (user sees their own connections; admins
see all).

### 5.12 Web UI

- New Settings tab "MCP" (label "AI assistants (MCP)"), behind
  `PlanGate feature="mcp"`. Update `docs/navigation.md` in the same
  change.
- Connections list: name, level chip, client last seen ("Claude Code
  1.2, 3 min ago"), calls today, actions (edit level, revoke).
- Create dialog (`ResponsiveDialog`): name, level as four rich radio
  cards with one line each of what the AI can do, the routine
  confirmation switch when `full` is picked, the admin cap shown and
  enforced.
- Created dialog: token shown once, plus a tabbed "Connect your client"
  block with copy buttons: Claude Code (`claude mcp add --transport http
  borg-ui <url> --header "Authorization: Bearer ..."`), Claude Desktop
  (JSON using `mcp-remote` with the header), Cursor, VS Code, Windsurf,
  generic. The builder verifies each snippet against the client's current
  docs at implementation time.
- Activity panel per connection (5.11), with outcome chips.
- Admin card in System settings: enable switch and max level.
- Every string in all four locales. Storybook stories for every new
  component and state. Follows AGENTS.md shared components and UI
  preferences.
- User docs: new `docs/mcp.md` (what it is, levels, confirm, clients,
  examples, security), plus a plan-content feature entry in
  `docs/plan-content.json` (all locales).

### 5.13 Analytics events

Generalize the queue, consent and rate-limit parts of
`error_reporter.py` into one backend sender both use (one choke point,
not a copy). Events, all respecting the per-user opt-out, never carrying
arguments, names or paths:

| Event | Props |
|---|---|
| `MCP - ConnectionCreated` / `ConnectionRevoked` / `LevelChanged` | `level`, `skip_routine_confirmations` |
| `MCP - ClientConnected` | `client` (normalized to a known list: `claude-code`, `claude-desktop`, `cursor`, `vscode`, `windsurf`, `other`), `level` |
| `MCP - ToolCall` | `tool`, `level`, `outcome`, `error_class`, `duration_bucket` |
| `MCP - Confirmation` | `tool`, `step` (`previewed`, `confirmed`, `expired`, `mismatched`, `skipped_by_setting`) |
| `MCP - PromptUsed` | `prompt` |

`ClientConnected` once per connection per day per client, not per
handshake (stateless mode handshakes often). `ToolCall` sampled at 1.0
but capped per install per hour like `Error - Report`.

Cross-repo (borg-ui-analytics): add the names to `src/catalog.ts`,
deploy ingest before the release, add an MCP panel to the dashboard
(installs using MCP, clients, tools by calls and failure rate, level mix,
confirmation funnel, Community installs blocked on `mcp`). Document the
events in `docs/engineering/specs/2026-10-21-analytics-journey-events.md`.

### 5.14 Testing

- Contract test per tool against the real app with the API fixture setup
  (`2026-11-06-api-fixture-setup.md`), Borg 1 and Borg 2 where the tool
  touches split routes.
- Level matrix: every tool at every level, plus the admin cap, plus RBAC
  viewer and operator users.
- Token isolation: MCP token on REST is 401, API token and JWT on `/mcp`
  are refused.
- Confirmation: single use, expiry, argument mismatch, wrong connection,
  skip setting honoured for `c` and ignored for `C`.
- Redaction scan over every tool's output on fixture data.
- Passphrase reveal: refused without re-auth, refused for tokens and the MCP internal credential, refused once acknowledged, logged; `create_repository` output never contains the passphrase.
- End-to-end smoke: official MCP Python client over HTTP against a
  running app, initialize, list tools per level, one call per domain.
- Manual pass at the end of phases 2, 4 and 5 with Claude Code and Claude
  Desktop on a throwaway data dir (strip notifications, MQTT, schedules
  from any copied DB first).

## 6. Phases

Each phase merges to main on its own and is usable. The UI only offers
levels whose tools exist (phase 2 offers `read`; phase 3 adds `operate`;
phase 4 `manage`; phase 5 `full`).

| Phase | Scope | Plan | Implement | Review |
|---|---|---|---|---|
| 1 Foundation and read tools | 5.1 to 5.4, 5.7, 5.8, 5.11 backend, read tools of 5.5, migration, redaction, contract test harness, smoke | Fable 5.2 | Opus 5.5 | Fable 5.2 |
| 2 Settings UI and docs | 5.12 (read level), 5.2 admin controls, `docs/mcp.md` | Fable 5.2 | Sonnet 5.5 | Fable 5.2 |
| 3 Operate | operate tools, `wait_for_job` progress, `restore_files` | Fable 5.2 | Sonnet 5.5 | Fable 5.2 |
| 4 Manage | manage tools, 5.9 reveal-once passphrase (migration, routes, banner, story) and hand-off links, `create_backup_plan` | Fable 5.2 | Opus 5.5 | Fable 5.2 |
| 5 Full | 5.6, destructive tools | Fable 5.2 | Opus 5.5 | Fable 5.2 |
| 6 Prompts, analytics, polish | 5.10, 5.13 in both repos, copy pass over every tool | Fable 5.2 | Sonnet 5.5 | Fable 5.2 |

Model choices are Claude's call; Karan may change them.

## 7. Not in this round

- Phase 7: MCP Apps cards (backup timeline, space chart, restore picker)
  rendered inline in clients that support them, in Borg UI's look.
- Phase 8: OAuth 2.1 with dynamic client registration so claude.ai web
  and mobile and ChatGPT can connect; the consent screen picks the level
  and reuses 5.2 and 5.11. Only useful for installs reachable over public
  HTTPS.
- MCP resources, sampling, elicitation.

## 8. Working this spec

### 8.1 Progress

| Phase | Status | Plan file | Branch | Notes |
| --- | --- | --- | --- | --- |
| 1 Foundation and read tools | done | `docs/engineering/plans/2026-11-14-mcp-phase-1-foundation.md` | `feat/mcp-phase-1` | Plan drafted 2026-11-14 on Fable 5.2 (the model section 6 names). SDK checked by prototype: `mcp==2.3.0` lowlevel `Server` with stateless Streamable HTTP as one route on the FastAPI app; GET must answer 405 (a stateless GET stream never ends). 36 read tools. Refinements to raise at G1: activity rows survive revocation, pruning on write instead of a daily job, gated installs answer tool calls with a friendly error instead of refusing the connection. Approved at G1 on 2026-11-14 as drafted; all four open questions settled as the plan proposes (voice guide, activity survives revocation, friendly tool error when gated, no script bodies at Read). Implemented 2026-11-14 on Opus 5.5 (G0 matched) in worktree `../borg-ui-mcp`, all twelve tasks; ledger rulings: one commit at G2; new `mcp.nameRequired` key (the `tokens.*` keys have no strings); a session manager per startup; icon from the built logo.svg; `get_repository` reuses the detail route's Borg stats and `get_archive` reads the index, calling Borg only for live rows; explicit field allowlists in every tool; keyed 5xx errors show their message; `get_settings` omits MCP state; activity pruned on write. Bugs found by tests and fixed: Borg 1 archive info sent the id instead of the name (caught only by the new real-Borg integration test), `path` query collided with the client's URL argument, crashing routes raised through the in-process transport, generic errors were not logged. Guards updated: route access registry (MCP routes, `update_config` behind `get_current_admin_user`), timestamp-parse allowlist (`app/mcp/render.py`, `app/mcp/resolve.py`). Verification: full `tests/unit` 8555 passed before the two guard fixes, then MCP, guard, token and feature suites plus both MCP integration tests 225 passed; ruff clean on changed files; frontend typecheck, `vitest src/core` and `check:locales` green. Not verified: Borg 2 live (no borg2 binary locally); a session in the owner's Claude Code. Final review was a self-review; the 8.2 review step (`/code-review high` on Fable 5.2) is still to run. Process lapse: Tasks 4 and 9 wrote code before watching the tests fail, mitigated by mutation checks. Note for later PRs: editing `backend.*` strings in `en.json` needs `scripts/extract_backend_strings.py`. Committed at G2 on 2026-11-15 as 9f17a8a9d. Review 2026-11-15 on Opus 5.5 (owner chose it over Fable 5.2 at G0; CodeRabbit could not authenticate, so a manual pass against 8.3 and Appendix A). Findings: Important, PATCH lowering a Full connection that skips confirmations returns 422 skipNeedsFull instead of dropping the skip (probe confirmed); Minor, `pick` also matches substrings where 5.4 says unique prefix (revisit before phase 5 destructive tools); Minor, Origin equals Host does not stop DNS rebinding (bearer auth still blocks it); Minor, validation failures and rate-limit refusals are not recorded in activity; Minor, no contract test that tools never declare token, licensing or password routes (5.2 rule 5). G3 2026-11-15: owner chose to fix the Important finding only; fixed with `test_lowering_full_drops_the_skip` RED to GREEN, MCP suite 194 passed. The four minors stay open. CodeRabbit rounds on PR #1544 fixed in follow-up commits (rate limit now counts running calls; holds while gunicorn runs one worker, which `entrypoint.sh` does, though `app/config.py` and section 3 still say two). Merged to main as PR #1544 (b7114f7da). |
| 2 Settings UI and docs | done | `docs/engineering/plans/2026-11-18-mcp-phase-2-settings-ui.md` | `feat/mcp-phase-2` | Plan drafted 2026-11-18 on Opus 5.5 (owner chose it over Fable 5.2 at G0). Two backend additions the UI needs: `calls_today` per row, and refusing levels with no tools yet (`top_level()`, `available_levels` in config) so a connection cannot be created at a level that silently gains power when a later phase ships. Tab sits in Settings > Personal; admin controls are a new System settings section with its own save. Approved at G1 on 2026-11-18 as drafted. Implemented 2026-11-18 on Opus 5.5 (section 6 names Sonnet 5.5; owner asked to implement in this session), all eight tasks. Rulings: one commit at G2; snippets checked against client docs on 2026-11-18, VS Code uses `.mcp.json` (`.vscode/mcp.json` is deprecated) and Windsurf has no tab because its docs now redirect to Devin and the format could not be confirmed (Other clients covers it); clients shown by their raw MCP name; activity opens in a dialog; `calls_today` counts the UTC day. Verification: full `tests/unit` plus both MCP integration tests 8754 passed, 154 skipped; full frontend vitest 3500 passed; typecheck, oxlint and `check:locales` clean; all 22 MCP stories screenshotted in light and dark at 1280 and 375 px with no page errors and no horizontal scroll (fixed on the way: dialog footers lacked the usual padding, story auth mocks never resolved a user). Not verified: a live session in the owner's Claude Code or Claude Desktop (spec 5.14 manual pass; it changes the owner's own client config). Committed at G2 on 2026-11-18. Merged to main as PR #1562 (e2a403a64) on 2026-11-19. |
| 3 Operate | committed | `docs/engineering/plans/2026-11-19-mcp-phase-3-operate.md` | `feat/mcp-phase-3` | Plan drafted 2026-11-19 on Opus 5.5 (owner chose it over Fable 5.2 at G0), worktree `../borg-ui-mcp-3`. 21 operate tools in nine tasks. Found while planning: the endpoint answers in JSON mode, where the SDK drops notifications, so progress needs streamed (SSE) answers (Task 1). Raised at G1: SSE for every call, a stricter restore destination rule (refuse any non-empty destination), the notification test reading the stored URL in-process, folding in phase 1's rule 5 contract test, no mount point argument. Approved at G1 on 2026-11-19 as drafted; all five open questions settled as the plan proposes. Implemented 2026-11-19 on Opus 5.5 (section 6 names Sonnet 5.5; owner chose Opus at G0), all nine tasks, 20 operate tools (the plan said 21, a miscount). Rulings: one commit at G2; the redaction scan runs at operate and skips tools that launch real work (their own stubbed tests cover them); restore destination listed once before starting (a folder filled in between is not caught for Borg 1; Borg 2 still refuses via existing_files); discover_sources scans the wizard's four default database paths; pause and resume do not count the queue. Also folded in: the 5.2 rule 5 contract test from phase 1's review. Verification: full `tests/unit` 8850 passed, 154 skipped; MCP unit plus both MCP integration tests 314 passed, the real-Borg one now backs up, waits, checks, refuses a restore into a full folder and restores into an empty one; ruff clean; personal-paths guard OK. Not verified: Borg 2 live (no borg2 locally); progress in a real client session; a session in the owner's Claude Code. Deferred minor: the Borg dry-run previews and source scans can outlast the in-process client's 120 s timeout on big repositories. Final review was a self-review. Committed at G2 on 2026-11-19; the 8.2 review step is next. Review 2026-11-19 on Opus 5.5 (owner chose it over Fable 5.2 at G0): CodeRabbit (second run; the first dropped its connection) plus a manual pass against 8.3 and Appendix A, each finding checked in code. Important: the agent folder listing hides dotfiles unless asked (`include_hidden`), so an agent destination holding only hidden files passes the empty-folder check; a failed estimate lookup after a start succeeded reports an error for a job that did start, inviting a second run; `test_script` runs with the server's whole environment and its output reaches the AI, where pattern redaction missed `API_TOKEN=` in a probe (route behaviour, admins only, against 5.9). Minor: progress repeats the same value on every poll (MCP says it must increase); an agent repository with `destination_connection` writes on the agent, which the check covers, but the answer reads as an SSH restore; the 120 s client timeout (deferred). Rejected: unmount picking non-Borg mounts (the list route returns Borg mounts only). Restated, not new: the Borg 1 list-then-start race (implementation ruling). G3 2026-11-19: owner chose to fix all six; each fixed RED to GREEN: agent listing asks for hidden files (`test_agent_listing_includes_hidden_files`); `estimate` returns None on a failed lookup (`test_failed_estimate_still_reports_the_started_job`); `test_script` output blanks every server environment value of 8+ characters outside a short benign list (`test_script_output_hides_the_server_environment`); progress sent only when it rises (`test_wait_for_job_progress_only_increases`); an agent repository with `destination_connection` is refused (`test_agent_repository_refuses_an_ssh_destination`); dry runs and scans wait 600 s and any timeout answers with a clear sentence (`test_timeout_is_a_clear_sentence` and four timeout tests). MCP suites 324 passed, source-scanning guards 214 passed, ruff clean. Fixes committed 2026-11-19. Pre-PR CodeRabbit run: 4 major; fixed 3 RED to GREEN: `check_repository` sent nothing for a full check, which the v1 route reads as a 3600 s partial check, and passed minutes where the route takes seconds; the in-process client's timeouts never fired (httpx's ASGI transport ignores them), now an anyio deadline (`test_slow_route_times_out`). Dismissed 1: blanking short environment values in `test_script` output would mangle ordinary output such as 0, 1 or true. |
| 4 Manage | not started | | | |
| 5 Full | not started | | | |
| 6 Prompts, analytics, polish | not started | | | |

### 8.2 Continuation protocol

Same as section 19.2 of
`docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`,
with these substitutions: the model table is section 6; plan files are
`docs/engineering/plans/<date>-mcp-phase-<n>-<slug>.md`; branches are
`feat/mcp-phase-<n>` from `main`, always in a worktree; the review step
checks against 8.3 and Appendix A.

### 8.3 Review focus per phase

Every phase: 5.2 rules 1, 2 and 5, 5.4 redaction, Appendix A. Phase 1:
5.3, 5.4, 5.8, 5.11. Phase 2: 5.12. Phase 3: 5.8, `restore_files`
destination rule. Phase 4: 5.9, `create_backup_plan`. Phase 5: 5.6.
Phase 6: 5.13 privacy.

### 8.4 Gates

Same as 19.4 of the operations spec: G0 model, G1 plan review, G2
verification and commit, G3 review findings, G4 blocked, G5 spec
conflict. Nothing is committed or pushed without the gate answer.

## Appendix A. Decisions and rejected alternatives

- Approach C (in-process REST) over OpenAPI generation and over direct
  service calls. Karan, 2026-11-14.
- Preview and confirm for destructive tools, with access levels chosen
  per connection, admin switch and cap. Karan, 2026-11-14.
- Confirmation always for whole-repository deletes, wipes, overwriting
  restores, lock breaks, user deletes; skippable per connection for
  routine deletes. Karan agreed to Claude's proposal, 2026-11-14.
- Token clients first; OAuth (claude.ai, ChatGPT) later. Karan,
  2026-11-14.
- Lite gets MCP, through the existing Pro gate. Karan, 2026-11-14.
- Secrets never pass through the AI. Repository passphrases are
  generated server side and revealed once in the web UI behind
  re-authentication (5.9); rejected: handing passphrase entry off to the
  wizard (breaks the in-chat setup) and accepting passphrases in chat
  (sends them to the AI vendor). Karan, 2026-11-14.
- Phase 4 includes the reveal-once routes, banner and attention entry.
  Claude's call.
- MCP connections live in `api_tokens` with a `kind` column, not a new
  table; existing personal tokens keep full power. Claude's call.
- English-only tool copy. Claude's call, 5.7.
