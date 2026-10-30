# Analytics journey events

Status: implemented on branch `claude/eloquent-faraday-b6b274` (borg-ui#1365 and the
whole-journey follow-up). Ships in the first release after it merges.

This is the catalog the dashboard reads. Every app event is named `Category - Action`
and must be in the ingest allowlist (`src/catalog.ts` in borg-ui-analytics) or it is
rejected as `unknown_name`. Props are the event's `props` object.

## Envelope (every app event)

| Field | Meaning |
|---|---|
| `instance_key` | SHA-256 of the install's random id. Joins to `orders.ik` and buy-link `ik`. |
| `user_key` | SHA-256 of install id plus user id. |
| `session_key` | Random per page load. |
| `path` | Route only: ids, `aid:` selectors and the deployment base path removed (`/archives/:id/:id`, `/repositories/:id/prune-preview`). Static segments stay (`/settings/beta`). Segments right after `archives` (two) and `repositories` (one) are always `:id`, and only `prune-preview` may follow a repository id. Below the root only a known Settings tab or Schedule view is kept. Anything else becomes `:id`, and a path whose first segment is not an app route is sent as `/:other`. |
| `plan`, `app_version` | Current plan name and app version. |

Privacy rules, enforced in `frontend/src/utils/analytics.ts`: any `*_name` prop and any
string that looks like a path, URL or user@host is hashed at any depth. Journey
failure events include a coarse `error_class` and, when available, a bounded
backend translation `error_key`, never a message or error parameters.

`error_class` values: `network`, `timeout`, `validation` (400, 422), `auth` (401),
`permission` (403), `not_found`, `conflict`, `rate_limited`, `server` (5xx), `client`
(other 4xx), `unknown` (not an HTTP error), `check_failed` (a connection test whose request worked but whose check failed).

## 1. Paywalls (how many hit them, on which feature)

`Plan - FeatureBlocked`: a locked feature was shown or refused. One per gate per mount.

| Prop | Meaning |
|---|---|
| `feature` | Stable key (`unknown` if a backend refusal names none): `borg_v2`, `backup_plan_multi_repository`, `backup_plan_mixed_sources`, `rclone`, `remote_clients`, `database_discovery`, `container_backups`, `backup_reports`, `alerting_monitoring`, `archive_history`, `extra_users`, `rbac`. |
| `current_plan`, `required_plan`, `allowed` (false) | |
| `surface` | Where: `plan_gate` (default), `repository_wizard`, `source_selection_dialog`, `backup_plan_card`, `archive_search`, `archive_changes`, `archive_file_history`, `prune_lost_files`, `api`, and the surfaces callers pass to PlanGate. |
| `operation` | What the user was doing (`render_gate`, `run_plan`, `source_kind_pivot`, `teaser`, or for `surface=api` the API area such as `repositories`). |
| `gate_mode` | `upgrade_prompt`, `preview`, `fallback`, `disabled`, `teaser` (prompt that is its own gate), `api_error` (backend refused with `backend.errors.plan.*`). |

Sources: `PlanGate` (all modes), `UpgradePrompt` with a `surface` (archive teasers),
plan card Run lock, source picker Database/Container tabs, repository wizard rclone
locks, backup plan multi-repo and mixed-source locks, and the API interceptors for any
backend plan refusal.

The user limit is a paywall too: the backend refuses a new user over the plan's limit with `feature: extra_users` (`required` pro from Community, enterprise from Pro), which arrives as `surface: api`, `gate_mode: api_error`.

Not paywalls, so no event: Borg 2 option hidden
in Quick Start and encryption fields, remote clients hidden in the backend switcher,
archive history hidden in the pipeline board.

`Plan - FeatureUsed`: a gated (or tracked community) feature was used. Same props with
`allowed: true`.

## 2. Biggest blocker (paywalls plus errors and abandons)

`API - Fail`: a change (not a read) failed in either API client.

| Prop | Meaning |
|---|---|
| `area` | First fixed segment of the API path (`repositories`, `backup-plans`, `ssh-keys`, ...), `other` if not a plain word. Never the rest of the path. |
| `method` | `post`, `put`, `patch`, `delete`. |
| `status` | HTTP status, absent on network errors. |
| `error_class` | See above. |
| `error_key` | Optional backend translation key without `backend.errors.` (for example, `repo.failedToInitializeRepository`). Only dot-separated identifiers from that namespace, at most 160 characters including the prefix, are accepted. Free text and error parameters are omitted. |

Not sent for GET/HEAD, for 401 (expired session), or for plan refusals (those are
`Plan - FeatureBlocked`).

Backend `Error - Report` request diagnostics also retain the HTTP `status` and
the same optional `error_key`, even when reporting the underlying exception of a
wrapped HTTP failure. The existing `component` identifies the matched API route
template, without concrete resource IDs or query strings. Exception grouping
and API responses are unchanged.

Wizard funnels, from `useWizardFunnel`:

| Event | When | Props |
|---|---|---|
| `Wizard - Start` | Wizard opened | `wizard`, `mode` where it has one |
| `Wizard - View` | First time each step is reached while open | `step`, `wizard`, `mode` |
| `Wizard - Cancel` | Closed through its own close/cancel (abandon) | last `step`, `wizard`, `mode` |

`wizard`: `repository` (`mode` create/edit/import; steps location, cloudMirror, source,
security, advanced, config, review, by mode), `schedule` (`mode`; steps basic, schedule,
scripts, maintenance, review), `restore` (steps files, destination, review),
`backup_plan` (`mode` create/edit; steps source, repositories, settings, scripts,
schedule, review), `add_agent` (steps target, details,
command; closing after the agent connected is not a cancel). Closing because the
submit succeeded never sends Cancel. Submit failures show up as `API - Fail`.

Connection tests send `success` and, on failure, `error_class`:

| Event | Props |
|---|---|
| `SSH Connection - Test` | `resource` (`connection`, `connection_diagnostics`), `trigger: after_edit` for the automatic test after editing, `success`, `error_class` |
| `System - Test` | `section: cloud_storage`, `operation: test_remote_complete`, `provider`, `success`, `error_class` |
| `Remote Client - Test` | `surface`, `status`, `compatibility`, `success`, `error_class` |
| `Notification - Test` | `success`, `error_class` |

Backup outcomes (`Backup - Complete` / `Backup - Fail`), sent when the browser sees a
run finish:

| Source | Props |
|---|---|
| Backup plan runs (Backup Plans page) | `entity: backup_plan`, `trigger`, `status` (`completed`, `completed_with_warnings`, `failed`, `partial`, `cancelled`, `skipped`), `duration_seconds`, `repository_count`, `failed_repository_count`, `skip_reason` |
| Legacy manual jobs (Backup page) | `descriptor: manual`, `trigger`, `status`, `duration_seconds`, ... |
| Schedules (Schedule page) | `entity: schedule`, `trigger: scheduled`, `status`, ... |

The first `Backup - Complete|Fail` per `instance_key` is the first backup outcome.
Runs that finish with no browser open are not seen.

## 3. Which paywall converts best

Each gate carries one `feature` key through every step:

| Step | Event | Join |
|---|---|---|
| Shown | `Plan - FeatureBlocked` | `feature` |
| Buy click | `Plan - View` with `operation: open_buy_link` | `feature`, `src`, `surface`, `selected_plan` |
| Trial start | `Plan - Start` with `operation: start_feature_trial` | `feature`, `surface` |
| Trial result | `Plan - Complete` (`result`) or `Plan - Fail` (`reason` or `error_class`) | `feature`, `surface` |
| Buy link | `https://borgui.com/buy?plan=..&src=app-gate-<feature>&ik=<instance_key>` | storefront records `src` and `ik` on the order |

`UpgradePrompt` always keys its link and events by feature when it has one, including
prompts rendered by `PlanGate` (no trial offered there). `src=app-upgrade-prompt` only
remains for a prompt with no feature. Other buy links: LicensingTab and PlanInfoDrawer
(`surface: plan_drawer`, `src=app-drawer|app-trial|app-expired`).

Gate to order: `Plan - FeatureBlocked.instance_key` to `orders.ik`, attributed by the
order's `src`.

## 4. What users use most

`pageview` events carry the normalized route (see envelope). Main actions, one usage
event each:

| Feature | Event |
|---|---|
| Backup run | `Backup - Start` (`descriptor` manual, backup_plan, quick_start, legacy_repository; `entity` backup_plan/schedule) |
| Restore | `Archive - Start` with `operation: restore` (no surface on the Archives page, `archive_detail` on the archive page) and `Archive - Complete\|Fail` from the Archives page |
| Browse archive | `Archive - View` with `operation: open_archive` (`surface: archive_contents` or `archive_detail`) |
| Mount | `Archive - Mount` (`operation: mount_archive`), `Mount - Unmount\|Delete` |
| Prune, check, compact | `Maintenance - Start` with `operation_type` Prune, Check, Compact |
| Schedules | `Backup - Create\|Edit\|Delete\|Start` with `entity: schedule` |
| Notifications | `Notification - Create\|Edit\|Delete\|Test` |
| Cloud (rclone) | `System - *` with `section: cloud_storage`, plus `Plan - FeatureUsed` `rclone` |
| Agents | `System - *` on Managed Agents, plus `Plan - FeatureUsed` `managed_agents` |
| SSH | `SSH Connection - Create\|Edit\|Delete\|Test\|Upload\|Start` |

## 5. Quick Start

| Event | When | Props |
|---|---|---|
| `Quick Start - Start` | Dialog opened | `trigger` (`auto` first-run, `manual` header/empty-state) |
| `Quick Start - View` | First time each step is reached | `step` (`app`, `what`, `connect`, `folders`, `destination`, `protect`, `schedule`, `review`, `progress`), `path` once past `what` |
| `Quick Start - Complete` | Repository and plan created | `path`, `app_choice` (`folders`, `app`), `app` (template id) |
| `Quick Start - Fail` | Creating failed | `path`, `app_choice`, `app` |
| `Quick Start - Cancel` | Closed before finishing | last `step`, `path` once chosen |
| `Backup - Start` | "Run now" after finishing | `descriptor: quick_start` |

`path`: `local`, `ssh`, `agent`.

## Allowlist changes

Categories added: `Quick Start`, `Wizard`, `API`. Actions: none new (`Start`, `View`,
`Complete`, `Fail`, `Cancel`, `Test` already allowed).
