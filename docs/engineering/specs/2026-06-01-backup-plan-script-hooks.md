# Backup Plan Script Hooks Spec

## Problem

Backup Plans only support one saved pre-backup script and one saved
post-backup script through `pre_backup_script_id` and
`post_backup_script_id`. Repository script configuration supports an ordered
saved-script chain, per-assignment parameter values, pre-script failure
behavior, and post-script run conditions. Backup Plan users need that same
saved-script hook model without legacy inline script authoring.

## Desired Outcome

Backup Plan create/edit exposes plan-level saved script chains for pre-backup
and post-backup hooks. Users can add multiple scripts, set their order, provide
parameter values, choose pre-script failure handling, and choose post-script
run conditions. Existing Backup Plans with the old single pre/post script
fields still load, save, and execute without data loss.

## Current Behavior Signal

`RepositoryScriptsTab` loads ordered `RepositoryScript` rows and displays
multiple saved scripts per hook. `Backup Plans/ScriptsStep` delegates to
`ScriptSelectorSection`, which renders exactly one pre-backup select, one
post-backup select, parameter inputs for those two scripts, and the repository
scripts checkbox.

The reproduction command passed on the current baseline:

```bash
cd frontend
npm test -- src/components/__tests__/ScriptSelectorSection.test.tsx src/pages/backup-plans/__tests__/ScriptsStep.test.tsx --run
```

## Scope

In scope:

- Add a first-class `backup_plan_scripts` assignment table modeled after
  `repository_scripts`.
- Add API payload and detail response support for Backup Plan script hooks.
- Preserve old `pre_backup_script_id`, `post_backup_script_id`, and parameter
  fields as compatibility input/output and execution fallback.
- Execute plan-level script chains in configured order.
- Update the Backup Plan Scripts step, review step, payload mapping, state
  hydration, locales, and Storybook state.
- Add focused backend and frontend tests.

Out of scope:

- Inline script authoring in Backup Plans.
- Changing repository script management behavior.
- Adding drag-and-drop ordering. Explicit up/down controls or stable order
  numbers are enough for this slice.
- Changing schedule wizard script behavior outside Backup Plans.

## Data Model

Add `BackupPlanScript`:

- `backup_plan_id`, `script_id`
- `hook_type`: `pre-backup` or `post-backup`
- `execution_order`
- `enabled`
- `custom_timeout`
- `custom_run_on`
- `continue_on_error`
- `skip_on_failure`
- `parameter_values`
- `created_at`

Use `Text` for `parameter_values`, matching `RepositoryScript`, so encrypted
password values use the same helpers. Keep a unique constraint on
`backup_plan_id`, `script_id`, and `hook_type` to avoid duplicate assignments
within one hook.

## API Contract

`BackupPlanPayload` accepts `script_hooks?: BackupPlanScriptPayload[]`.

Each item includes:

- `script_id`
- `hook_type`
- `execution_order`
- `enabled`
- `custom_timeout`
- `custom_run_on`
- `continue_on_error`
- `skip_on_failure`
- `parameter_values`

Create/update behavior:

- If `script_hooks` is supplied, validate every script exists, validate hook
  type and run condition, encrypt password parameters, replace the plan's hook
  rows, and also mirror the first pre/post assignment into the old single
  fields for compatibility.
- If `script_hooks` is omitted, keep accepting the legacy single pre/post
  fields and serialize them as hook rows in detail responses when no explicit
  `backup_plan_scripts` rows exist.
- Deleting a script clears both legacy Backup Plan script columns and
  `BackupPlanScript` assignments for that script.

## Execution

Plan execution runs:

1. Plan pre-backup hook chain before source scripts and repository work.
2. Existing database source pre-scripts.
3. Repository work.
4. Existing database source post-scripts filtered by backup result.
5. Plan post-backup hook chain filtered by backup result.

Pre-backup hook failures:

- `skip_on_failure=true`: mark the run as skipped/cancelled before repository
  work without treating it as a script failure.
- `continue_on_error=true`: record the failed script execution and continue to
  the next script or repository work.
- default: fail the run before repository work.

Post-backup hook failures remain non-destructive to completed repository work:
they add a warning to the plan run, matching the existing single post-script
behavior.

Post-backup hook run conditions use assignment `custom_run_on` when present,
otherwise the script's default `run_on`. Supported values are `success`,
`failure`, `warning`, and `always`.

## UI

Replace the plan-level `ScriptSelectorSection` usage in the Backup Plan Scripts
step with a controlled saved-script chain editor:

- Separate "Pre-backup scripts" and "Post-backup scripts" sections.
- Each section lists assigned saved scripts in execution order.
- Users can add a script from the script library, remove it, move it up/down,
  configure parameter values, and set hook-specific behavior.
- Pre-backup rows show failure behavior.
- Post-backup rows show run condition.
- The existing "Also run repository scripts" checkbox stays.
- Database source script summary stays above plan-level scripts.
- No inline script controls are shown.

Use existing Borg UI product primitives and MUI controls. Use icons for add,
remove, configure, and reorder actions. Keep the layout compact and operational:
outlined rows, chips for order/run condition/failure behavior, no heavy side
accent borders, and no nested cards.

## Acceptance Criteria

- Backup Plan users can attach multiple saved scripts to a plan.
- Each attached script can define when it should run, including success and
  failure conditions matching repository script behavior.
- Backup Plan scripting does not offer legacy inline script authoring.
- Existing Backup Plan data continues to load and save without losing existing
  script configuration.
- Backend execution records each plan script execution in order.
- Storybook demonstrates Backup Plan script chains.
- Local app walkthrough covers opening Backup Plan create/edit, adding multiple
  saved scripts with conditions, saving, reopening, and confirming persistence.

## Validation

- Backend unit tests for API create/update/detail compatibility and script
  deletion cleanup.
- Backend execution tests for ordered pre/post hook chains and run-condition
  filtering.
- Frontend unit tests for payload/state mapping and the Scripts step editor.
- Storybook story for the changed Backup Plan Scripts step state.
- Required validation commands:

```bash
ruff check app tests
ruff format --check app tests
pytest tests/unit/test_api_backup_plans.py tests/unit/test_api_scripts_library.py
cd frontend && npm run check:locales
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
```

