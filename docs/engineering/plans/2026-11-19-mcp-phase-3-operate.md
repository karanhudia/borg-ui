# MCP Phase 3: Operate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, with superpowers:test-driven-development for every task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A connection at `operate` can run what already exists in Borg UI: start backups, plans and schedules, cancel and retry jobs, check, compact, restore check, refresh, preview prune, preview and restore files to a new place, mount and unmount, run the SSH, notification and script tests, find sources, and pause or resume background work. `wait_for_job` reports live progress.

**Architecture:** Same shape as phase 1. Each tool is a handler in `app/mcp/tools/<domain>.py` that resolves names, calls the app's own REST routes through `InternalClient`, and shapes a `ToolResult`. The client gains `post`. `borg_routes.py` gains the write operations the frontend splits by Borg version (run, check, compact). The transport switches from JSON answers to streamed (SSE) answers, because the SDK drops notifications in JSON mode, and the tool context gains a `progress` callback. Registering the first `operate` tool raises `top_level()`, so the settings UI from phase 2 offers Operate with no frontend change.

**Tech Stack:** FastAPI, the official `mcp==2.3.0` SDK (lowlevel `Server`, stateless Streamable HTTP), httpx ASGITransport, pytest.

**Spec:** `docs/engineering/specs/2026-11-14-mcp-server.md` (sections 5.2, 5.4, 5.5 Operate table, 5.7, 5.8, 5.14; review focus 8.3 phase 3 = 5.8 and the `restore_files` destination rule).

## Global Constraints

- Branch `feat/mcp-phase-3` from `main`, worktree `../borg-ui-mcp-3`. Nothing committed or pushed without the gate answer (8.4).
- Tools call REST routes only. No service-layer calls, no Borg calls, no edits to existing routes. Borg 1/2 branching lives only in `app/mcp/borg_routes.py`, mirroring `frontend/src/services/borgApi/client.ts`.
- Every operate tool declares `level=Level.OPERATE`, `read_only=False`, and `idempotent` honestly (start, run and retry are not idempotent; cancel, pause, resume, refresh, unmount are).
- No operate tool declares a `DELETE` route or any route on the destructive list (Task 2). The contract test enforces it.
- Copy follows `app/mcp/STYLE.md`: outcome first, names in italics, one next-step offer, no em dashes, no exclamation marks, no "successfully".
- Every result leaves through `render.finish` (redaction and the 60 kB cap). Secrets read in-process (the notification URL in Task 8) never appear in a result.
- Starting anything returns at once with the job id, what it is doing, and an estimate (5.8). Nothing in this phase blocks except `wait_for_job` (45 s).
- No real paths, hosts, tokens or URLs in tests. Use `/data/example`, `backups.example.com`, `json://example.invalid`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (or the model that implements).

## Review Focus

1. A Borg 2 repository runs, checks and compacts through `/api/v2/backup/*`; a Borg 1 or agent repository through the v1 routes. (Task 2 tests.)
2. `restore_files` never writes into a destination that already holds data, on the server, over SSH or on an agent. Overwriting is phase 5's `restore_files_overwrite`. (Task 6 tests.)
3. A viewer's operate connection starts nothing: the route's RBAC answer reaches the model as a friendly sentence, and activity records `denied_rbac`. (Task 3 test.)
4. `wait_for_job` with a `progressToken` sends at least one progress notification before its result, over one stateless POST. (Task 1 test.)
5. The notification test never puts the channel URL in the result or the activity row. (Task 8 test.)
6. A read connection still sees exactly the phase 1 tools; the level matrix passes for all 16 level and cap pairs. (Task 9.)

---

### Task 1: Streamed answers and progress

**Files:**
- Modify: `app/mcp/server.py` (`json_response=False`; build `ToolContext.progress`)
- Modify: `app/mcp/context.py` (`progress` field)
- Modify: `app/mcp/tools/jobs.py` (`wait_for_job` reports progress each poll)
- Modify: `tests/unit/mcp/conftest.py` (`McpSession` reads SSE answers)
- Test: `tests/unit/mcp/test_endpoint.py`, `tests/unit/mcp/test_tools_jobs.py`

**Interfaces:**
- Produces: `ToolContext.progress: Callable[[float, Optional[str]], Awaitable[None]]`, a no-op when the call carried no `progressToken`. Called with a percentage (0 to 100) and an optional message.
- Produces: `/mcp` answers `text/event-stream` for requests, still 202 for notifications, still 405 for GET.

Why: `StreamableHTTPServerTransport` with `is_json_response_enabled` sends only the final message and drops notifications (SDK `streamable_http.py`, around line 1077). Spec 5.3 and 5.8 need progress on the call's own response stream, which is what SSE mode gives in stateless mode.

- [x] **Step 1: Prototype.** In a scratch test, call `ServerSession.report_progress` (SDK `server/session.py:426`) from a lowlevel handler with `json_response=False` and read the raw SSE body. Confirm the handler reaches the session through `ctx.session` and the token through the request meta. Record the exact call in the ledger; if the API differs, adapt `progress` and keep the interface above.
- [x] **Step 2: Failing tests.**
  - `test_answers_are_event_streams`: `tools/list` answers 200 with `content-type: text/event-stream`, and the helper parses one `result`.
  - `test_wait_for_job_reports_progress`: a running operation at 40% that finishes on the second poll (patch `POLL_SECONDS` to 0), called with `_meta.progressToken = "t1"`; the SSE body has a `notifications/progress` event with `progressToken == "t1"` and `progress == 40` before the result.
  - `test_wait_for_job_without_token_sends_no_notifications`.
- [x] **Step 3: Implement.** `McpSession.post` parses `data:` lines of the event stream into JSON-RPC messages and returns the one whose `id` matches; keep a `messages` attribute for the progress test. Flip `json_response=False`. In `on_call_tool`, build `progress` from the request context; `wait_for_job` calls it after every poll with `progress_percent` (skip when unknown) and `progress_message`.
- [x] **Step 4:** Run the whole MCP unit suite and both MCP integration tests (`test_mcp_smoke.py` uses the official client, which reads SSE already). All green.

### Task 2: Client writes, Borg routes, the destructive list

**Files:**
- Modify: `app/mcp/client.py` (`post`)
- Modify: `app/mcp/borg_routes.py` (`backup_run`, `repository_check`, `repository_compact`)
- Modify: `tests/unit/mcp/test_tools_stubbed.py` (`StubApi.post`, records bodies)
- Modify: `tests/unit/mcp/test_contract.py` (destructive list, forbidden routes, `EXPECTED_TOOLS`)
- Test: `tests/unit/mcp/test_borg_routes.py`, `tests/unit/mcp/test_contract.py`

**Interfaces:**
- Produces: `InternalClient.post(path, /, json=None, **params)`.
- Produces: `borg_routes.backup_run(repo) -> (path, body)`: v2 `POST /api/v2/backup/run {"repository_id": id}`; v1 and agent `POST /api/backup/start {"repository": repo["path"]}`.
- Produces: `borg_routes.repository_check(repo, max_duration=None)`: v2 `/api/v2/backup/check {"repository_id", "max_duration"?}`; else `/api/repositories/{id}/check {"max_duration"?}`.
- Produces: `borg_routes.repository_compact(repo)`: v2 `/api/v2/backup/compact {"repository_id"}`; else `/api/repositories/{id}/compact`.
- Produces: `DESTRUCTIVE_ROUTES` in `test_contract.py`: `POST /api/repositories/{repo_id}/prune`, `POST /api/v2/backup/prune`, every route whose path contains `wipe`, `break-lock`, `delete`, `/rebuild`, plus `POST /api/restore/start` (only `restore_files` may declare it, Task 6).
- Produces: `FORBIDDEN_ROUTES` (5.2 rule 5, closes a phase 1 review minor): any route under `/api/auth/tokens`, `/api/settings/mcp`, `/api/system/licensing`, and any path containing `password`. No tool at any level may declare one.

- [x] **Step 1: Failing tests.** `test_borg_routes.py`: the three functions for Borg 1, Borg 2 and an agent Borg 2 repository (agent goes v1, as `client.ts` does). `test_contract.py`: `test_no_tool_below_full_declares_a_destructive_route` and `test_no_tool_declares_a_forbidden_route`, both iterating `REGISTRY`.
- [x] **Step 2: Implement.** Keep the allowlist idea of phase 1: rename `READ_POST_ALLOWLIST` to stay for read tools; operate tools may declare `POST` freely, subject to the two lists.
- [x] **Step 3:** Contract suite green.

### Task 3: Back up now, run a plan, run a schedule

**Files:**
- Create: `app/mcp/tools/operate.py` (backup and job-control tools; split later only if it passes about 500 lines)
- Modify: `app/mcp/tools/__init__.py`
- Modify: `app/mcp/tools/jobs.py` (export `estimate(ctx, job_type, repository_id)`)
- Test: `tests/unit/mcp/test_tools_operate.py`

**Tools (5.5):**

| Tool | Routes | Answer |
|---|---|---|
| `start_backup` | `POST /api/backup/start`, `POST /api/v2/backup/run`, `GET /api/repositories/` | `⏳ Backup of *Photos* started (backup 412). Usually takes ~6 min. Want me to wait for it?` |
| `run_backup_plan` | `POST /api/backup-plans/{plan_id}/run`, `GET /api/backup-plans/` | The run id, the repositories it will write to, the estimate from the plan's last runs. |
| `run_schedule_now` | `POST /api/schedule/{job_id}/run-now`, `GET /api/schedule/` | What the schedule started, with job ids when the route returns them. |

`estimate`: median duration of the last five completed runs of the same type for the same repository (or plan), from `GET /api/activity/recent`; `None` when there are fewer than two, and then the answer leaves the estimate out instead of guessing. Every start answer ends with the `wait_for_job` offer and puts `job_type` and `job_id` in `structuredContent` so the model can call it.

- [x] **Step 1: Failing tests** (seeded app, `admin_mcp` at operate; Borg routes stubbed through `StubApi` where the seeded app cannot run Borg):
  - `test_start_backup_borg1_posts_path` and `test_start_backup_borg2_posts_id` (stubbed, asserting the exact route and body).
  - `test_start_backup_answer_has_job_and_estimate` with two prior completed backups of 5 and 7 minutes: text says "Usually takes ~6 min".
  - `test_viewer_cannot_start_backup`: viewer user, operate connection, route refuses; result `is_error`, text is the friendly RBAC sentence, activity outcome `denied_rbac`.
  - `test_read_connection_cannot_see_start_backup` (level text from `server._level_text`).
  - `test_run_backup_plan_by_name` and `test_run_schedule_now_by_name` (ambiguous name returns the candidates).
- [x] **Step 2: Implement** the three tools and `estimate`.
- [x] **Step 3:** Suite green.

### Task 4: Cancel and retry

**Files:**
- Modify: `app/mcp/tools/operate.py`
- Test: `tests/unit/mcp/test_tools_operate.py`

| Tool | Routes | Rule |
|---|---|---|
| `cancel_job` | `POST /api/activity/{job_type}/{job_id}/cancel`, `POST /api/backup-plans/runs/{run_id}/cancel` | Plan runs go to the plan route, every other type to the activity route, which already picks backup or operation cancel and checks the role. A 409 renders as "already finished" or "cannot be stopped mid-run" from its key. |
| `retry_job` | `POST /api/backup/jobs/{job_id}/retry`, `POST /api/backup-plans/runs/{run_id}/retry` | Only backups and plan runs. Any other type answers, without calling anything: "Only backups and plan runs can be retried. To run a {label} again, use {tool}." naming `check_repository`, `compact_repository` or `run_restore_check`. |

- [x] **Step 1: Failing tests:** cancel a queued operation (seeded), cancel a plan run (routes to the plan route, stubbed), cancel a finished job (friendly 409), retry a failed backup returns the new job id, retry a check is refused with the pointer and makes no POST.
- [x] **Step 2: Implement.**
- [x] **Step 3:** Suite green.

### Task 5: Repository maintenance

**Files:**
- Modify: `app/mcp/tools/repositories.py`
- Test: `tests/unit/mcp/test_tools_repositories.py`

| Tool | Routes | Notes |
|---|---|---|
| `check_repository` | `POST /api/repositories/{repo_id}/check`, `POST /api/v2/backup/check` | Optional `max_duration` minutes (partial check), passed as the UI passes it. |
| `compact_repository` | `POST /api/repositories/{repo_id}/compact`, `POST /api/v2/backup/compact` | Answer reminds that compact frees what prune and deletes left. |
| `run_restore_check` | `POST /api/repositories/{repo_id}/restore-check` | No arguments beyond the repository: the route uses the repository's saved restore-check settings. |
| `refresh_repository` | `POST /api/repositories/{repo_id}/resync` | "Refreshing the archive list and stats of *Photos*." The route reuses a run in flight; say so when it does. |
| `preview_prune` | `POST /api/repositories/{repo_id}/prune/preview` | Retention fields as in `compare_retention`; at least one rule or a friendly refusal before calling. Answer: archives that would go, oldest and newest of them, space freed as a lower bound ("at least"), and that nothing was deleted. Pro-only file details shown when present. |

None of these may declare the prune route itself; the contract test (Task 2) holds that.

- [x] **Step 1: Failing tests:** each tool on Borg 1 and Borg 2 (stubbed for route choice), `preview_prune` with no rule makes no POST, `preview_prune` text says "at least" and "Nothing was deleted".
- [x] **Step 2: Implement.**
- [x] **Step 3:** Suite green.

### Task 6: Preview a restore, restore files to a new place

**Files:**
- Create: `app/mcp/tools/restore.py`
- Test: `tests/unit/mcp/test_tools_restore.py`

**Interfaces:**
- `preview_restore(repository, archive, paths)`: `POST /api/restore/preview`. Shows the first 50 lines of Borg's dry-run listing, the count, and "nothing was written".
- `restore_files(repository, archive, paths, destination, destination_connection?, layout?)`: `POST /api/restore/start` with `existing_files="refuse"` always.

**The destination rule (5.5, review focus 8.3).** Before the POST, list the destination with the same folder routes the read tools use: `browse_server_folders` route for a server destination, the SSH connection browse route for `destination_connection`, the agent browse route for an agent repository. Refuse when the destination exists and holds anything:

> *Restore stopped.* /data/example/restore already has files in it, and restoring at operate never writes over existing files. Pick an empty or new folder, or ask an admin for a connection with full access to overwrite.

A destination that does not exist is fine (Borg creates it). A listing the user may not read is a refusal, not a pass. Strictly, the spec refuses only when the restored paths already exist; refusing any non-empty destination is stricter, needs one listing instead of one per path, and cannot be fooled by layout options (Open question 2).

`archive` resolves through `resolve.py` like the read tools. The answer gives the restore job id and the `wait_for_job` offer.

- [x] **Step 1: Failing tests:**
  - `test_restore_into_empty_folder_starts` (stubbed listing returns `[]`, asserts body has `existing_files == "refuse"`).
  - `test_restore_into_missing_folder_starts` (listing 404).
  - `test_restore_into_non_empty_folder_refuses_without_posting`, for server, SSH and agent destinations (parametrized).
  - `test_restore_listing_forbidden_refuses`.
  - `test_preview_restore_caps_listing` (200 lines in, 50 out, count stated).
- [x] **Step 2: Implement.**
- [x] **Step 3:** Suite green.

### Task 7: Mount and unmount

**Files:**
- Modify: `app/mcp/tools/archives.py`
- Test: `tests/unit/mcp/test_tools_archives.py`

| Tool | Routes | Notes |
|---|---|---|
| `mount_archive` | `POST /api/mounts/borg` | Repository plus optional archive (Borg 2 sends `archive_id`, Borg 1 `archive_name`, through `borg_routes`). No `mount_point` argument: the app picks one, so the AI cannot aim a mount at an arbitrary path. Agent repositories refuse in the route; render its key. Answer gives the mount point and the `unmount_archive` hint. |
| `unmount_archive` | `POST /api/mounts/borg/unmount/{mount_id}`, `GET /api/mounts` | Takes a mount id or the mount point; with neither and exactly one mount, unmounts it; with several, lists them and asks. |

- [x] **Step 1: Failing tests:** mount Borg 1 by name, Borg 2 by id (stubbed body), unmount by mount point, unmount with two mounts asks.
- [x] **Step 2: Implement.**
- [x] **Step 3:** Suite green.

### Task 8: Tests, sources, background work

**Files:**
- Modify: `app/mcp/tools/connections.py` (`test_ssh_connection`, `test_notification`, `test_script`)
- Modify: `app/mcp/tools/plans.py` (`discover_sources`)
- Modify: `app/mcp/tools/overview.py` (`pause_background_work`, `resume_background_work`)
- Test: matching `test_tools_*.py`

| Tool | Routes | Notes |
|---|---|---|
| `test_ssh_connection` | `POST /api/ssh-keys/connections/{connection_id}/test` | Connection by name or `user@host`. |
| `test_notification` | `GET /api/notifications`, `POST /api/notifications/test` | Reads the channel's stored `service_url` in-process and hands it to the test route; the URL never enters the result, the activity target ("notification channel Ops") or a log. Admin-only, as the routes are. |
| `test_script` | `POST /api/scripts/{script_id}/test` | Admin-only by route. Optional `repository` to inject that repository's context, as the UI does. Output tail capped at 50 lines. |
| `discover_sources` | `POST /api/source-discovery/databases/scan`, `POST /api/source-discovery/containers/scan` | `kind`: `databases`, `containers` or both (default). Lists what was found, one line each. |
| `pause_background_work` / `resume_background_work` | `POST /api/operations/pause`, `POST /api/operations/resume`, `GET /api/operations/queue` | All stages at once, as the Operations page's main switch does. Admin-only by route. Answer says what was queued and stays queued. |

- [x] **Step 1: Failing tests:** `test_notification_result_never_holds_the_url` (seeded channel with `json://secret.example.invalid/abc`; asserts the URL is absent from text, structured content and the `mcp_activity` row), plus one happy path per tool and a non-admin refusal for `test_script` and `pause_background_work`.
- [x] **Step 2: Implement.**
- [x] **Step 3:** Suite green, including `test_redaction_scan.py` over the new tools.

### Task 9: Contract, level matrix, smoke, docs, progress table

**Files:**
- Modify: `tests/unit/mcp/test_contract.py` (`EXPECTED_TOOLS` gains the 21 tools, grouped by task)
- Modify: `tests/unit/mcp/conftest.py` (the `every_level_has_tools` autouse fixture may now be narrowed: operate is real)
- Modify: `tests/integration/test_mcp_smoke.py` (an operate connection lists the operate tools and calls `refresh_repository`)
- Modify: `tests/integration/test_mcp_real_borg.py` (Borg 1: `start_backup` then `wait_for_job` to completion, then `check_repository`)
- Modify: `app/mcp/server.py` `INSTRUCTIONS` (one paragraph: starting work returns at once, offer `wait_for_job`; restores at operate only go to empty or new folders)
- Modify: `app/mcp/STYLE.md` (a `start_backup` example and a refusal example)
- Modify: `docs/mcp.md` (new "What the AI can do at Operate" after the Read section)
- Modify: `docs/engineering/specs/2026-11-14-mcp-server.md` (8.1 row 2 to `done` with "merged as PR #1562"; row 3 notes)

- [x] **Step 1:** Update `EXPECTED_TOOLS`; run the contract suite and the 16-cell level matrix.
- [x] **Step 2:** Smoke and real-Borg integration tests green (Borg 2 live is again not verifiable locally; say so).
- [x] **Step 3:** Docs and instructions. Check `docs/mcp.md` for any sentence saying only Read is available and fix it.
- [x] **Step 4:** `superpowers:verification-before-completion`: full `tests/unit`, both MCP integration tests, `ruff check` and `ruff format --check` on changed files, the guard scripts the pre-commit runs (route access registry, timestamp-parse allowlist). Frontend unchanged, so no frontend run unless Task 1 or 9 touched it.

## Not in this phase

- Overwriting restores (`restore_files_overwrite`), prune itself, deletes: phase 5.
- `upgrade_agents`, schedule and plan edits: phase 4 (manage).
- Per-stage pause from the Operations page: the global switch only.
- Prompts (`free-up-space` uses `preview_prune` and `compact_repository`): phase 6.

## Open questions

1. **Streamed answers for every call.** Switching the endpoint to SSE is the only way progress reaches the client in the SDK's stateless mode. Every MCP client must accept SSE answers (MCP spec, Streamable HTTP), and the official client used in the smoke test does. Proposal: switch for every call, not only calls with a `progressToken`, so there is one code path. Risk: a reverse proxy that buffers SSE delays progress but not the result.
2. **Restore destination rule.** Proposal: refuse any destination that exists and is not empty (one listing, safe for every layout), instead of the spec's per-path check. Stricter than 5.5 asks; it may refuse a restore into a folder that holds unrelated files. Accept the stricter rule?
3. **Notification test reads the stored URL in-process.** The test route takes a raw URL, so the tool reads it from the admin-only list route and passes it on inside the server. The secret never reaches the AI (5.9 holds), and no route changes. Alternative: a new `POST /api/notifications/{id}/test` route. Proposal: in-process, no new route.
4. **Phase 1 review minor folded in.** Task 2 adds the 5.2 rule 5 contract test (no token, MCP settings, licensing or password routes) that phase 1's review left open. The other three minors stay open; `pick` prefix matching must still be fixed before phase 5.
5. **`mount_archive` without a mount point.** Proposal: the AI cannot choose where a mount lands; the app picks. OK?
