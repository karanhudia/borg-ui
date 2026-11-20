# MCP Phase 4: Manage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, with superpowers:test-driven-development for every task. UI tasks also use `ui-ux-pro-max`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A connection at `manage` can set Borg UI up: create and change repositories, SSH keys and connections, backup plans, schedules, scripts, notification events, cloud remotes, agents, settings and users. No secret passes through the AI. A repository created over MCP gets a passphrase generated on the server, which the user reveals once in the web UI.

**Architecture:** Same shape as phases 1 and 3. Each tool is a handler in `app/mcp/tools/<domain>.py` that resolves names, calls the app's own REST routes through `InternalClient`, and shapes a `ToolResult`. Three things are new. (1) The reveal-once passphrase: a `passphrase_unsaved` column, two browser-only routes, a dashboard warning and a web UI banner. (2) Hand-off links: `app/mcp/links.py` builds deep links into web UI dialogs, which learn to open prefilled from query parameters. (3) Field allowlists on every update tool, so a tool can never send a field the spec keeps away from the AI. Registering the first `manage` tool raises `top_level()`, so the phase 2 settings UI offers Manage with no change.

**Tech Stack:** FastAPI, SQLAlchemy and alembic, `mcp==2.3.0` (lowlevel `Server`, stateless Streamable HTTP, SSE answers), httpx ASGITransport, pytest. React with MUI, Storybook and vitest for Tasks 3 and 9.

**Spec:** `docs/engineering/specs/2026-11-14-mcp-server.md`. Relevant sections: 5.2, 5.4, the Manage table and the `create_backup_plan` paragraph in 5.5, 5.7, 5.9 and 5.14. Review focus (8.3) for phase 4 is 5.9 and `create_backup_plan`.

## Global Constraints

- Branch `feat/mcp-phase-4` from `main`, worktree `../borg-ui-mcp-4`. Nothing is committed or pushed without the gate answer (8.4).
- Tools call REST routes only. No service-layer calls, no Borg calls. There is one exception: `create_repository` sets `passphrase_unsaved` through `app/mcp/passphrase.py` (Open question 1). Borg 1/2 branching lives only in `app/mcp/borg_routes.py`, mirroring `frontend/src/services/borgApi/client.ts`.
- Existing route files change only in these places:
  - the two passphrase routes and the dashboard warning (5.9);
  - the dialogs' query parameters (5.9, "the only change to existing pages").
- Every manage tool declares `level=Level.MANAGE`, `read_only=False`, and `idempotent` honestly. Updates and toggles to a given state are idempotent; creates, duplicates and upgrades are not.
- No manage tool declares a `DELETE` route or a destructive route. The phase 3 contract test enforces this.
- Every update tool sends only fields from its own allowlist, declared as a module constant and tested. Unknown arguments are rejected by the input model (`model_config = ConfigDict(extra="forbid")`).
- Secrets never reach a result, the activity row or a log. Secrets here means passphrases, private keys, remote passwords, notification URLs, rclone secret keys and user passwords. A tool that needs one answers with a hand-off link and one line saying what to enter there (5.9).
- Copy follows `app/mcp/STYLE.md`: outcome first, names in italics, one next-step offer, no em dashes, no exclamation marks, no "successfully".
- Every result leaves through `render.finish` (redaction and the 60 kB cap).
- No real paths, hosts, tokens or URLs in tests. Use `/data/example`, `backups.example.com` and `json://example.invalid`. The personal-paths guard runs in pre-commit.
- Frontend strings in all four locales (en, de, es, it), checked by `npm run check:locales`. Storybook stories for every new component and changed state. Render light and dark at 1280 and 375 px before G2 (fnm Node 24).
- The migration's `down_revision` is computed against freshly fetched `origin/main` heads on the day it is written.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **No passphrase escapes.** `create_repository` output never contains the generated passphrase: not the text, not `structuredContent`, not the `mcp_activity` row, not a log line. The redaction scan cannot catch this by field name, because the value is random. (Task 4 test.)
2. **Reveal is browser-only.** The reveal route refuses:
   - the MCP internal credential and any `borgui_` token, even with the right password;
   - a wrong password, or a wrong repository name for an account with no local password;
   - a repository whose flag is already cleared.

   (Task 2 tests.)
3. **Settings stay off limits.** `update_settings` cannot touch `mcp_beta_enabled`, `metrics_token`, `rotate_metrics_token`, `mqtt_password`, the MQTT TLS keys, `webhook_url` or `lock_breaking_enabled`, even when the model sends them. (Task 8 test.)
4. **Missing answers are asked for.** `create_backup_plan` without sources, repositories or a schedule posts nothing and names what is missing. Every default it applies is listed in the answer. (Task 6 tests.)
5. **Updates hit the named target.** An update by name only ever resolves the named object. With *Photos* and *Old Photos*, `update_repository("photos")` resolves *Photos* and never *Old Photos* through a substring match. (Task 1 test, closing the phase 1 review minor.)
6. **Host keys are confirmed by the user.** `trust_host_key` never trusts a key the user has not seen. The first call shows the fingerprint and trusts nothing. The second call must carry the same fingerprint, and a server that changed its key in between is refused. (Task 5 test.)

---

### Task 1: Client writes, exact prefixes, links, forbidden routes

**Files:**
- Modify: `app/mcp/client.py` (`put`, `patch`)
- Modify: `app/mcp/resolve.py` (`pick`: id, exact name, case-insensitive unique *prefix*; no substrings)
- Modify: `app/mcp/context.py`, `app/mcp/server.py` (`ToolContext.base_url`)
- Create: `app/mcp/links.py`
- Modify: `tests/unit/mcp/test_contract.py` (forbidden routes), `tests/unit/mcp/test_tools_stubbed.py` (`StubApi.put`, `StubApi.patch`)
- Test: `tests/unit/mcp/test_resolve.py`, `tests/unit/mcp/test_links.py`, `tests/unit/mcp/test_contract.py`

**Interfaces:**
- Produces: `InternalClient.put(path, /, json=None, **params)` and `InternalClient.patch(...)`, same shape as `post`.
- Produces: `ToolContext.base_url: str`. It is built in `on_call_tool` from `app.core.oidc.build_external_base_url(request)` plus `BASE_PATH`, so `PUBLIC_BASE_URL` wins when set (5.9).
- Produces: `links.web(ctx, page: str, **params) -> str`. It returns `{base_url}/{page}?{urlencoded params}`, dropping `None` values. Callers never pass a secret, and the test asserts a denylisted key raises `ValueError`. The pages and params Task 9 implements:

| Link | Page and params |
|---|---|
| `links.repository(ctx, repo_id)` | `repositories?reveal={id}` |
| `links.import_repository(ctx, **fields)` | `repositories?import=1&name=&path=&borg_version=&connection_id=&encryption=` |
| `links.ssh_deploy(ctx, host, username, port)` | `ssh-connections?deploy=1&host=&username=&port=` |
| `links.rclone_remote(ctx, remote_id)` | `cloud-storage?edit={id}` |
| `links.new_user(ctx, **fields)` | `settings/users?new=1&username=&email=&full_name=&role=` |

- Produces: `FORBIDDEN_ROUTES` gains three routes, so no tool at any level declares them (5.9 "No MCP tool reveals or acknowledges"):
  - `GET /api/repositories/{repo_id}/keyfile`
  - `POST /api/repositories/{repo_id}/passphrase/reveal`
  - `POST /api/repositories/{repo_id}/passphrase/acknowledge`

  The reveal and acknowledge routes appear in Task 2, so the check matches on the path string, not on the app's route table.

- [ ] **Step 1: Failing tests:**
  - `test_pick_prefers_prefix_over_substring`: items *Photos* and *Old Photos*, ref `photos`, picks *Photos*.
  - `test_pick_substring_only_is_not_found`: ref `hotos` raises the not-found sentence.
  - `test_web_link_uses_public_base_url` (monkeypatch `settings.public_base_url`).
  - `test_web_link_keeps_base_path`.
  - `test_web_link_refuses_secret_params` (`passphrase=`, `password=`, `private_key=`).
  - Extend `test_destructive_and_forbidden_checks_match` with the three routes.
- [ ] **Step 2: Implement.** Run the whole MCP unit suite: every existing name lookup must still pass with prefix-only matching. Any test that relied on a substring gets its ref fixed, not the rule loosened.
- [ ] **Step 3:** MCP suite green.

### Task 2: Reveal-once passphrase, backend

**Files:**
- Create: `app/database/alembic/versions/<rev>_repository_passphrase_unsaved.py` (`repositories.passphrase_unsaved` Boolean, `server_default=false`, not null)
- Modify: `app/database/models.py` (`Repository.passphrase_unsaved`)
- Modify: `app/core/security.py` (`require_browser_session` dependency)
- Modify: `app/api/repositories.py` (two routes at the end of the file, plus `passphrase_unsaved` in the repository list and detail responses)
- Modify: `app/api/dashboard.py` (`build_full_repository_health`: warning, at least `warning` health)
- Modify: `frontend/src/locales/*.json` `backend.errors.repo.*` keys, then run `scripts/extract_backend_strings.py`
- Test: `tests/unit/test_repository_passphrase_reveal.py`, `tests/unit/test_dashboard_health.py` (or the existing health test file), `tests/unit/mcp/test_migration_downgrade.py`

**Interfaces:**
- Produces: `require_browser_session(request, user=Depends(get_current_user)) -> User`. It refuses with 403 `backend.errors.auth.browserSessionRequired` when `request.state.mcp_connection_id` is set or when the credential was a `borgui_` token. Have `_get_active_user_from_token` set `request.state.api_token_auth = True`; that is the one choke point.
- Produces: `POST /api/repositories/{repo_id}/passphrase/reveal`, body `{"password": str | None, "repository_name": str | None}`, answers `{"passphrase": str, "encryption": str, "has_keyfile": bool}`. It checks in this order:
  1. browser session;
  2. `check_repo_access(..., "operator")`, the role that may edit a repository; confirm the name against `repositories.py` update;
  3. the flag is set, else 409 `backend.errors.repo.passphraseAlreadySaved`;
  4. re-authentication: `verify_password` when the user has a local password hash, else an exact `repository_name` match; on failure 403 `backend.errors.repo.reauthFailed`.

  Each reveal is logged with `logger.warning("passphrase revealed", repository_id=, user_id=)`, never the value. The flag stays set.
- Produces: `POST /api/repositories/{repo_id}/passphrase/acknowledge`. It requires a browser session and edit access, clears the flag and answers 204. Repeating it is a 204 no-op.
- Produces: dashboard warning text `"Passphrase not saved yet"`. `list_problems` then shows it with no change, because it lists repository warnings.

- [ ] **Step 1: Failing tests:**
  - reveal with the right password answers the passphrase;
  - reveal with a wrong password is 403 and nothing is revealed;
  - an OIDC user (no password hash) reveals with the exact repository name and is refused with a near miss;
  - a `borgui_` API token is refused;
  - the MCP internal credential is refused (mint it with `create_mcp_internal_token`);
  - a viewer is refused;
  - reveal after acknowledge is 409;
  - reveal does not clear the flag;
  - the reveal log line holds no passphrase (`caplog`);
  - health of a flagged repository is at least `warning` with the warning text;
  - migration downgrade drops the column.
- [ ] **Step 2: Implement.** Recompute alembic heads against fetched `origin/main` before writing `down_revision`.
- [ ] **Step 3:** Run the new tests, the route access registry guard (add both routes there) and `tests/unit/mcp`. All green.

### Task 3: Reveal-once passphrase, web UI

Use `ui-ux-pro-max` first.

**Files:**
- Create: `frontend/src/components/repositories/PassphraseUnsavedBanner.tsx` (+ `.stories.tsx`, test)
- Create: `frontend/src/components/repositories/RevealPassphraseDialog.tsx` (+ `.stories.tsx`, test). It is a `ResponsiveDialog`.
- Modify: `frontend/src/pages/Repositories.tsx` (render the banner above the list; `?reveal={id}` opens the dialog for that repository)
- Modify: `frontend/src/services/api.ts` (or the repositories service): `revealPassphrase`, `acknowledgePassphrase`
- Modify: `frontend/src/types/index.ts` (`passphrase_unsaved?: boolean`)
- Modify: `frontend/src/locales/{en,de,es,it}.json`

**Behaviour (5.9):**
- **Banner.** One banner lists every flagged repository the user can see: "*Photos* has a passphrase you haven't saved yet. Without it the backups cannot be restored if Borg UI's database is lost." It has a Reveal button per repository. Use a tinted, full-outline surface with an icon, and no left accent border (AGENTS.md).
- **Dialog, step 1.** Re-authentication: a password field for local accounts, or "Type the repository name" when the user has no local password. The current user's `auth_source` tells the dialog which one to show.
- **Dialog, step 2.** The passphrase in a monospace field with a copy button. For keyfile modes it also offers the keyfile download through the existing `GET /api/repositories/{id}/keyfile`. There is an "I've saved it" button, which calls acknowledge, closes the dialog and refreshes the list. Closing without it keeps the banner.

- [ ] **Step 1: Failing vitest tests:**
  - the banner lists only flagged repositories;
  - the dialog asks for the password for a local user and for the name for an OIDC user;
  - a wrong password shows the error and no passphrase;
  - "I've saved it" calls acknowledge;
  - closing without it does not call acknowledge;
  - `?reveal=7` opens the dialog for repository 7.
- [ ] **Step 2: Implement** the components, page wiring and strings in four locales.
- [ ] **Step 3: Stories:**
  - banner with one repository and with three;
  - dialog states: password re-auth, name re-auth, error, revealed repokey, revealed keyfile.
- [ ] **Step 4:** `npm run typecheck`, `npx vitest run` on the new and changed files, `npm run check:locales`, oxlint. Render the stories light and dark at 1280 and 375 px and screenshot them.

### Task 4: Repository tools

**Files:**
- Create: `app/mcp/tools/manage_repositories.py`
- Create: `app/mcp/passphrase.py` (`generate() -> str`, `mark_unsaved(repo_id: int) -> None`)
- Modify: `app/mcp/borg_routes.py` (`repository_create(payload) -> (path, body)`, `repository_import(payload)`)
- Modify: `app/mcp/tools/__init__.py`
- Test: `tests/unit/mcp/test_tools_manage_repositories.py`, `tests/unit/mcp/test_borg_routes.py`

**Interfaces:**
- `borg_routes.repository_create` and `borg_routes.repository_import` follow `client.ts`:
  - `/api/v2/repositories/` (or `/import`) when `borg_version == 2` and the target is neither an agent nor rclone;
  - `/api/repositories/` (or `/import`) otherwise.
- `passphrase.generate()` returns `secrets.token_urlsafe(24)`: 192 bits on one line, so the route's single-line validator accepts it. The wizard has no generator (5.9).
- `passphrase.mark_unsaved(repo_id)` sets the column in its own session from `app/mcp/db.py`. It is the only direct write in `app/mcp/`.

| Tool | Routes | Rule |
|---|---|---|
| `create_repository` | `POST /api/repositories/`, `POST /api/v2/repositories/`, `GET /api/ssh-keys/connections` | See the notes below the table. |
| `import_repository` | `POST /api/repositories/import`, `POST /api/v2/repositories/import` | `encrypted` (bool, default true). True: no POST; answer with `links.import_repository` and "Enter the passphrase there." False: POST with `encryption="none"` and answer as a create. |
| `update_repository` | `GET /api/repositories/{repo_id}`, `PUT /api/repositories/{repo_id}` | Allowlist `UPDATE_REPOSITORY_FIELDS`: `name`, `compression`, `source_directories`, `exclude_patterns`, `custom_flags`, `upload_ratelimit_kib`, `pre_hook_timeout`, `post_hook_timeout`, `continue_on_hook_failure`, `skip_on_hook_failure`. Never `passphrase`, `path` or `encryption`. The answer lists what changed, before and after. |
| `set_check_schedule` | `PUT /api/repositories/{repo_id}/check-schedule`, `POST /api/schedule/validate-cron` | Cron plus timezone, checked by `validate_schedule` (Task 6) before the PUT. `off` clears it. Optional `max_duration` minutes. |
| `set_restore_check_schedule` | `PUT /api/repositories/{repo_id}/restore-check-schedule`, `POST /api/schedule/validate-cron` | Same; the body fields are taken from the route's model. |

`create_repository` details:
- **Input.** `name`, `path`, optional `ssh_connection` (name or `user@host`), `borg_version` (default 1), `encryption` (default: the app's own, `repokey` or `repokey-aes-ocb`), `compression` (default `lz4`).
- **Passphrase.** When the encryption is not `none`, it is generated and put in the body in-process.
- **After the POST.** `mark_unsaved(id)` runs. If it raises, the tool answers an error telling the user to open the repository in the web UI. The passphrase stays stored, so nothing is lost.
- **Answer.** The repository was created. A passphrase was generated and stored. Why saving it matters (5.9 copy). Then `links.repository`.
- **Scope.** Agent and rclone repositories answer with a link to the web UI wizard (Open question 3).

- [ ] **Step 1: Failing tests** (stubbed routes for route choice; seeded app for the flag):
  - `test_create_repository_borg2_posts_v2`;
  - `test_create_repository_generates_and_never_returns_the_passphrase`: capture the POST body. Then assert the body's passphrase is absent from the result text, `structuredContent`, every `mcp_activity` column and `caplog`.
  - `test_create_repository_marks_unsaved`;
  - `test_create_unencrypted_does_not_mark`;
  - `test_import_encrypted_hands_off_without_posting`: the link has no `passphrase` param;
  - `test_update_repository_sends_only_allowlisted_fields`: an extra field is rejected by the model; the PUT body keys are a subset of the allowlist;
  - `test_set_check_schedule_rejects_bad_cron_without_put`.
- [ ] **Step 2: Implement.**
- [ ] **Step 3:** Suite green, including `test_redaction_scan.py`.

### Task 5: SSH keys, connections, host keys

**Files:**
- Create: `app/mcp/tools/manage_connections.py`
- Test: `tests/unit/mcp/test_tools_manage_connections.py`

| Tool | Routes | Rule |
|---|---|---|
| `generate_ssh_key` | `POST /api/ssh-keys/generate` | `name`, `key_type` (default `ed25519`), `system_key` (default false when a system key exists). The answer shows the *public* key and where to add it. The private key never appears; the route does not return it, and a test asserts that. |
| `add_ssh_connection` | `GET /api/ssh-keys`, `POST /api/ssh-keys/{key_id}/test-connection` | `host`, `username`, `port`, optional `ssh_key` (default: the system key). The route creates the connection and tests it with the key. When the key is not on the server yet, the answer has the public key to add to `authorized_keys`, plus `links.ssh_deploy` for deploying with the server's password in the web UI. The tool never takes a password. |
| `update_ssh_connection` | `PUT /api/ssh-keys/connections/{connection_id}` | Allowlist `UPDATE_SSH_FIELDS`: `default_path`, `ssh_path_prefix`, `mount_point`, `use_sftp_mode`, `use_sudo`, `port`. Host and username stay out: changing them is a different server. |
| `trust_host_key` | `GET /api/ssh-keys/connections/{connection_id}/host-key`, `POST /api/ssh-keys/connections/{connection_id}/host-key/trust` | See the notes below the table. |

`trust_host_key` runs in two calls:
1. Without `fingerprint`: scan, show the fingerprint and key type, trust nothing, and tell the model to ask the user to compare it with the server's own.
2. With `fingerprint`: scan again. If the scanned fingerprint differs from the argument, refuse ("The server now shows a different key"). If it matches, POST the scanned key.

- [ ] **Step 1: Failing tests:**
  - generate answers a public key and no `PRIVATE KEY` text;
  - `add_ssh_connection` auth failure answers the public key and the deploy link;
  - the update allowlist;
  - `trust_host_key` first call makes no POST;
  - a mismatched fingerprint makes no POST;
  - a matching fingerprint POSTs the scanned key.
- [ ] **Step 2: Implement.**
- [ ] **Step 3:** Suite green.

### Task 6: Backup plans and schedules

**Files:**
- Create: `app/mcp/tools/manage_plans.py`
- Modify: `app/mcp/tools/plans.py` (move the cron check into `validate_schedule`; `check_cron` calls it)
- Test: `tests/unit/mcp/test_tools_manage_plans.py`, `tests/unit/mcp/test_tools_plans.py`

**Interfaces:**
- Produces: `validate_schedule(ctx, expression: str, timezone: str | None) -> dict`. It returns the route's answer (`cron_expression`, `timezone`, `next_runs`) or raises `ScheduleInvalid(text)`, which tools render as their error. The validator is the one `SchedulePicker` uses.

**`create_backup_plan` (5.5 centrepiece, review focus).**

Input model, all optional so the tool can answer "missing" instead of a schema error:

| Field | Shape |
|---|---|
| `name` | string |
| `sources` | list of `{path, ssh_connection?, agent?}` |
| `repositories` | list of names or ids |
| `schedule` | cron string or `manual` |
| `timezone` | string |
| `retention` | `{daily, weekly, monthly, yearly, within}` |
| `compression` | string |
| `exclude_patterns` | list |
| `pre_backup_script`, `post_backup_script` | name or id |
| `after` | list of `prune`, `compact`, `check` |

1. **Missing answers.** If `name`, `sources`, `repositories` or `schedule` is missing, answer one line per missing item and post nothing. Example: "To make the plan I still need: what to back up, which repository, how often (or `manual`)."
2. **Resolving.** Repositories, SSH connections, agents and scripts go through `resolve.py`. `source_type` is:
   - `local` when every source is plain;
   - `remote` when all sources share one SSH connection;
   - `agent` when all share one agent;
   - otherwise `mixed`, with per-source `source_locations` as `backup_plans.py` reads them.

   Sources on two different SSH connections are refused; `source_ssh_connection_id` is single.
3. **Schedule.** A cron `schedule` goes through `validate_schedule` and sets `schedule_enabled=True`. `manual` sets it false.
4. **Defaults.** Applied defaults are named in a "Defaults I used" list:
   - retention 7 daily, 4 weekly, 6 monthly, 1 yearly (`BackupPlanPayload`'s own);
   - compression `lz4`;
   - archive names `{plan_name}-{now}`;
   - repositories run one after another.
5. **POST.** `POST /api/backup-plans/` with `repositories` as `[{repository_id, execution_order}]`.
6. **Answer.** The plan summary, then the next run from `validate_schedule`'s `next_runs[0]`, then "Want me to run it now?".

Databases and containers are not a source type here (Open question 2).

**Other tools:**

| Tool | Routes | Rule |
|---|---|---|
| `update_backup_plan` | `GET /api/backup-plans/{plan_id}`, `PUT /api/backup-plans/{plan_id}` | The PUT takes the whole plan, so: GET, merge the allowlisted changes, PUT. Allowlist: `name`, `description`, `sources`, `exclude_patterns`, `schedule`/`timezone` (validated), `retention`, `compression`, `after`, scripts, `repositories`. The answer lists before and after for what changed. |
| `set_backup_plan_enabled` | `POST /api/backup-plans/{plan_id}/toggle`, `GET /api/backup-plans/{plan_id}` | Takes `enabled: bool`. Toggles only when the state differs, so it is idempotent. |
| `create_schedule` / `update_schedule` | `POST /api/schedule/`, `PUT /api/schedule/{job_id}`, `GET /api/schedule/{job_id}` | Same missing-answer rule as the plan (name, repositories, cron). Validated cron. Retention and prune/compact as in `ScheduledJobCreate`. Descriptions point recurring backups to plans first (5.3 instructions). |
| `set_schedule_enabled` | `POST /api/schedule/{job_id}/toggle` | As for plans. |
| `duplicate_schedule` | `POST /api/schedule/{job_id}/duplicate` | Optional new name; when given, a follow-up PUT renames the copy. |

- [ ] **Step 1: Failing tests:**
  - `test_create_plan_missing_answers_posts_nothing` (parametrized over the four missing fields);
  - `test_create_plan_lists_defaults_used`;
  - `test_create_plan_bad_cron_posts_nothing`;
  - `test_create_plan_two_ssh_connections_refused`;
  - `test_create_plan_answer_has_next_run` (seeded app, real POST);
  - `test_update_plan_keeps_unchanged_fields` (GET, merge, PUT; the body equals the GET plus the change);
  - `test_set_plan_enabled_is_idempotent` (no toggle when already in that state);
  - one happy path per schedule tool;
  - `check_cron` still passes its phase 1 tests.
- [ ] **Step 2: Implement.**
- [ ] **Step 3:** Suite green.

### Task 7: Scripts, notification events, cloud remotes, agents

**Files:**
- Create: `app/mcp/tools/manage_misc.py`. Rename it if a clearer split shows up; keep it under about 500 lines.
- Test: `tests/unit/mcp/test_tools_manage_misc.py`

| Tool | Routes | Rule |
|---|---|---|
| `create_script` / `update_script` | `POST /api/scripts`, `PUT /api/scripts/{script_id}` | Admin-only by route. Fields `name`, `description`, `content`, `timeout`, `run_on`. `parameters` are left out (they can hold password-type parameters). The answer shows the first 20 lines of the content back. |
| `assign_script` | `POST /api/repositories/{repository_id}/scripts`, `GET /api/scripts` | Repository and script by name. `hook_type` is `pre-backup` or `post-backup`. Agent repositories take `agent_script_name`, following the route's rule. |
| `update_notification_channel` | `GET /api/notifications`, `PUT /api/notifications/{setting_id}` | Allowlist: every `notify_on_*` field, `enabled`, `title_prefix`, `include_job_name_in_title`, `monitor_all_repositories`, `repository_ids` (from names). Never `service_url`: the answer to a URL request is a link to Settings > Notifications. |
| `update_rclone_remote` | `GET /api/rclone/remotes`, `PUT /api/rclone/remotes/{remote_id}` | `name` and `settings` (dict). Any `settings` key that `app.api.rclone._is_sensitive_config_key` flags is refused before calling, with `links.rclone_remote`. Unchanged secret values are preserved by the route's redacted-value merge; the tool sends only the keys it was given. |
| `upgrade_agents` | `GET /api/managed-machines/agents`, `POST /api/managed-machines/agents/upgrade` | `agents`: names, or `outdated` (every agent whose upgrade status says one is available). The answer lists which upgrades were requested and which were already current. |

- [ ] **Step 1: Failing tests:**
  - `test_update_notification_never_sends_or_shows_the_url`: seeded channel with `json://secret.example.invalid/abc`; assert the PUT body has no `service_url` and the result and activity row hold no URL;
  - `test_rclone_sensitive_key_hands_off_without_put`;
  - `test_upgrade_outdated_picks_only_outdated`;
  - `test_assign_script_by_names`;
  - a non-admin refusal for `create_script`.
- [ ] **Step 2: Implement.**
- [ ] **Step 3:** Suite green, including the redaction scan.

### Task 8: Settings and users

**Files:**
- Create: `app/mcp/tools/manage_settings.py`
- Test: `tests/unit/mcp/test_tools_manage_settings.py`

| Tool | Routes | Rule |
|---|---|---|
| `update_settings` | `GET /api/settings/system`, `PUT /api/settings/system` | See the notes below the table. |
| `update_user` | `GET /api/settings/users`, `PUT /api/settings/users/{user_id}` | Admin-only by route. Allowlist: `full_name`, `email`, `role`, `is_active`. `username`, `auth_source` and `oidc_subject` stay out (identity linking). The tool refuses when the target is the connection's own user ("Change your own account in the web UI"), so an AI cannot change its own user's role or switch itself off. |
| `create_user` | `GET /api/settings/users` | A new user needs a password, so the tool posts nothing (5.9). It checks the username is free, then answers with `links.new_user` prefilled and "Set their password there." |

`update_settings` details:
- **Allowlist.** `UPDATE_SETTINGS_FIELDS` is: the timeouts, the concurrency limits, `log_*`, `auto_cleanup`, `cleanup_retention_days`, `bypass_lock_on_info`, `bypass_lock_on_list`, `stats_refresh_interval_minutes`, `auto_prune_preview`, `dashboard_*_days`, `backup_monitoring_*` and `backup_reports_*`.
- **Kept out.** Everything else stays out, by allowlist rather than denylist, so a field a later release adds is not exposed by accident. That covers every `mcp_*`, `metrics_*` and `mqtt_*` field, `webhook_url`, `email_notifications` and `lock_breaking_enabled`.
- **Answer.** One line per changed field, before and after.

- [ ] **Step 1: Failing tests:**
  - `test_update_settings_refuses_kept_out_fields`, parametrized over `mcp_beta_enabled`, `metrics_token`, `rotate_metrics_token`, `mqtt_password`, `mqtt_tls_client_key`, `webhook_url` and `lock_breaking_enabled`. The input model rejects each; no PUT;
  - `test_update_settings_sends_only_changes`;
  - `test_update_user_refuses_self`;
  - `test_update_user_refuses_non_admin`;
  - `test_create_user_hands_off_without_posting` (the link has no password param);
  - `test_create_user_taken_name`.
- [ ] **Step 2: Implement.**
- [ ] **Step 3:** Suite green.

### Task 9: Hand-off targets in the web UI

Use `ui-ux-pro-max` first. These query parameters are the only change to existing pages (5.9). Each page reads its parameters once on load, opens the dialog prefilled, and then removes the parameters from the URL with `setSearchParams(..., { replace: true })`, so a reload does not reopen the dialog.

**Files:**
- Modify: `frontend/src/pages/Repositories.tsx` (`?import=1&name&path&borg_version&connection_id&encryption`: `openWizard('import')` with those initial values)
- Modify: `frontend/src/pages/SSHConnectionsSingleKey.tsx` (`?deploy=1&host&username&port`: open the deploy dialog prefilled, focus the password field)
- Modify: `frontend/src/pages/CloudStorage.tsx` (`?edit={id}`: open that remote's edit dialog)
- Modify: `frontend/src/pages/Settings.tsx` users tab (`?new=1&username&email&full_name&role`: open the create-user dialog prefilled)
- Test: a vitest per page in its existing `__tests__` folder; stories for the four prefilled dialog states

- [ ] **Step 1: Failing vitest tests:**
  - each page opens its dialog prefilled from the URL;
  - unknown values (an invalid `role`, a non-numeric `port`) are ignored, not crashed on;
  - the URL is cleaned after opening.
- [ ] **Step 2: Implement** with the smallest change each page allows. If a wizard has no way to take initial values, add one optional `initialValues` prop rather than a second wizard.
- [ ] **Step 3: Stories** for the four prefilled states. Then run typecheck, vitest, oxlint and `check:locales`, and screenshot light and dark at 1280 and 375 px.

### Task 10: Contract, level matrix, smoke, docs, progress table

**Files:**
- Modify: `tests/unit/mcp/test_contract.py`: `EXPECTED_TOOLS` gains the manage tools, grouped by task. `set_check_schedule` and `set_restore_check_schedule` are two tools; `create_schedule`/`update_schedule` and the other pairs are separate tools. 25 in all.
- Modify: `tests/integration/test_mcp_smoke.py`: a manage connection lists the manage tools and calls `check_cron`, then `update_settings` with `stats_refresh_interval_minutes`.
- Modify: `tests/integration/test_mcp_real_borg.py`: Borg 1 `create_repository` (repokey) into a temporary directory, then `start_backup`, then `wait_for_job`. Assert the repository is flagged and the job completed. This proves the generated passphrase works with real Borg.
- Modify: `app/mcp/server.py` `INSTRUCTIONS`: one paragraph saying that secrets go through the web UI, links are for the user to open, and `create_backup_plan` asks before it assumes.
- Modify: `app/mcp/STYLE.md`: a `create_repository` example and a hand-off example.
- Modify: `docs/mcp.md`: a new "What the AI can do at Manage" section and a "Saving a generated passphrase" section. Fix any sentence that says Manage is not available yet.
- Modify: `docs/engineering/specs/2026-11-14-mcp-server.md`: the 8.1 row 4 notes.

- [ ] **Step 1:** Update `EXPECTED_TOOLS`. Run the contract suite and the 16-cell level matrix.
- [ ] **Step 2:** Run the smoke and real-Borg integration tests until green. Borg 2 live is again not verifiable locally; say so.
- [ ] **Step 3:** Docs and instructions.
- [ ] **Step 4: `superpowers:verification-before-completion`:**
  - full `tests/unit` and both MCP integration tests;
  - `ruff check` and `ruff format --check` on changed files;
  - the guard scripts pre-commit runs (route access registry, timestamp-parse allowlist, personal paths);
  - frontend typecheck, vitest, oxlint, `check:locales`;
  - Storybook screenshots from Tasks 3 and 9.
- [ ] **Step 5:** Spec 5.14 asks for a manual pass with Claude Code and Claude Desktop at the end of phase 4, on a throwaway data dir with notifications, MQTT and schedules stripped. It touches the owner's client config, so offer it at G2 rather than running it unasked.

## Not in this phase

- Deletes, prune, wipe, forget host key, removing agents, and overwriting restores belong to phase 5, behind preview and confirm.
- Creating notification channels and rclone remotes (both always hold secrets): the hand-off links cover editing them, and creation stays in the web UI.
- User permissions per repository (`/api/settings/users/{id}/permissions*`): not in the 5.5 catalog.
- Database and container plan sources, unless Open question 2 says otherwise.
- Prompts (`set-up-backup` drives `create_backup_plan`) belong to phase 6.

## Open questions

1. **Setting `passphrase_unsaved` directly.** The spec allows only the two new routes in repository code and says the flag is "set only by this path". So `create_repository` posts through the normal create route and then sets the flag with one direct update in `app/mcp/passphrase.py`, which no REST client can reach.
   - Alternative: a create-body field, but any API client could then set it.
   - Risk: if the update fails after the create, the repository exists without the banner. The tool then tells the user to open it in the web UI, and the passphrase stays stored.
   - Accept?
2. **Database and container sources.** The plan wizard turns a discovered database into a dump script on the client (`renderAppScript` in `AppSourcePanel.tsx`). Doing the same in Python would duplicate that logic, which section 2 calls an anti-goal.
   - Proposal: `create_backup_plan` takes file and folder sources only. For a database, the AI writes the dump script with `create_script` and attaches it as the plan's pre-backup script.
   - Alternative: hand off to the plan wizard with a link.
   - Which?
3. **Agent and rclone repositories in `create_repository`.** Agent repositories can use the agent's own passphrase, and rclone repositories need remote setup.
   - Proposal: phase 4 creates server and SSH repositories (Borg 1 and 2). Agent and rclone ones answer with a link to the web UI wizard.
   - OK?
4. **`create_user` posts nothing.** A user needs a password, so the tool only prepares a prefilled link. Generating a temporary password the AI never sees would also work, but then nobody knows it. Accept the link?
5. **`update_user` refuses the connection's own user.** This is not in the spec. It stops an AI from demoting or deactivating the account it runs as, and from raising a role in a single-admin flow. Keep it?
6. **`lock_breaking_enabled` and `email_notifications` stay out of `update_settings`.** The first unlocks a destructive feature, so it belongs with phase 5 or the web UI. The second is tied to notification delivery. OK?
7. **Phase 1 review minor folded in.** Task 1 makes `pick` prefix-only, as 5.4 says, ahead of phase 5. Two phase 1 minors stay open:
   - Origin versus DNS rebinding;
   - activity rows for validation failures and rate-limit refusals.
