# Backup Plan Script Hooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repository-style saved script hook chains to Backup Plans while preserving existing single pre/post script data.

**Architecture:** Add a `BackupPlanScript` assignment model and migration, accept/return `script_hooks` in Backup Plan APIs, and execute ordered plan hook chains through the existing script execution runner. Replace the Backup Plan Scripts step's two-select UI with a controlled chain editor backed by wizard state and payload mapping.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, React 18, MUI, i18next, Vitest, Storybook.

---

## Files

- Create: `app/database/migrations/118_add_backup_plan_scripts.py`
- Modify: `app/database/models.py`
- Modify: `app/api/backup_plans.py`
- Modify: `app/api/scripts_library.py`
- Modify: `app/services/backup_plan_execution_service.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/backup-plans/types.ts`
- Modify: `frontend/src/pages/backup-plans/state.ts`
- Modify: `frontend/src/utils/backupPlanPayload.ts`
- Modify: `frontend/src/pages/backup-plans/wizard-step/ScriptsStep.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/ReviewStep.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/ScriptsStep.stories.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`
- Test: `tests/unit/test_api_backup_plans.py`
- Test: `tests/unit/test_api_scripts_library.py`
- Test: `frontend/src/pages/backup-plans/__tests__/ScriptsStep.test.tsx`
- Test: `frontend/src/pages/__tests__/BackupPlans.test.tsx`

## Task 1: Backend Persistence Contract

- [ ] Add failing API tests in `tests/unit/test_api_backup_plans.py`.

```python
def test_create_plan_stores_ordered_script_hooks(self, test_client, admin_headers, test_db):
    repo = _create_repo(test_db, "Primary", "/repos/primary")
    first = _create_script(
        test_db,
        "Prepare One",
        parameters=json.dumps([{"name": "TARGET", "type": "text", "required": False, "default": "", "description": ""}]),
    )
    second = _create_script(test_db, "Prepare Two")
    response = test_client.post(
        "/api/backup-plans/",
        json=_payload([repo.id], script_hooks=[
            {"script_id": first.id, "hook_type": "pre-backup", "execution_order": 1, "enabled": True, "continue_on_error": True, "skip_on_failure": False, "parameter_values": {"TARGET": "db"}},
            {"script_id": second.id, "hook_type": "pre-backup", "execution_order": 2, "enabled": True, "continue_on_error": False, "skip_on_failure": False},
        ]),
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert [hook["script_id"] for hook in response.json()["script_hooks"]] == [first.id, second.id]
```

- [ ] Run the new test and confirm it fails because `script_hooks` is not accepted/serialized.

```bash
pytest tests/unit/test_api_backup_plans.py::TestBackupPlanRoutes::test_create_plan_stores_ordered_script_hooks -q
```

- [ ] Add `BackupPlanScript` to `app/database/models.py` and relate it to `BackupPlan` and `Script`.

- [ ] Add migration `118_add_backup_plan_scripts.py` that creates `backup_plan_scripts` with indexes and an idempotent table-exists guard.

- [ ] Add Pydantic `BackupPlanScriptPayload`, validation helpers, serialization, encrypted parameter processing, and replace-on-save logic in `app/api/backup_plans.py`.

- [ ] Mirror first pre/post hook into legacy fields during create/update and serialize legacy fields as `script_hooks` when no assignment rows exist.

- [ ] Run the targeted API test and confirm it passes.

```bash
pytest tests/unit/test_api_backup_plans.py::TestBackupPlanRoutes::test_create_plan_stores_ordered_script_hooks -q
```

## Task 2: Backend Execution Contract

- [ ] Add failing execution tests in `tests/unit/test_api_backup_plans.py` for ordered pre hooks, post run-condition filtering, and legacy fallback.

```python
@pytest.mark.asyncio
async def test_execute_plan_run_runs_plan_script_hooks_in_order(self, test_db):
    repo = _create_repo(test_db, "Primary", "/repos/primary")
    first = _create_script(test_db, "Prepare One")
    second = _create_script(test_db, "Prepare Two")
    plan, run = _create_execution_plan(test_db, [repo])
    test_db.add_all([
        BackupPlanScript(backup_plan_id=plan.id, script_id=second.id, hook_type="pre-backup", execution_order=2, enabled=True),
        BackupPlanScript(backup_plan_id=plan.id, script_id=first.id, hook_type="pre-backup", execution_order=1, enabled=True),
    ])
    test_db.commit()
    calls = []
    async def fake_single(run_id, context, *, hook_type, script_id=None, **kwargs):
        calls.append((hook_type, script_id))
        return True, None
    async def fake_execute_backup(job_id, repository, db, **kwargs):
        job = db.query(BackupJob).filter_by(id=job_id).one()
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        db.commit()
    with patch.object(backup_plan_execution_service, "_execute_plan_script", side_effect=fake_single), patch(
        "app.services.backup_plan_execution_service.backup_service.execute_backup",
        side_effect=fake_execute_backup,
    ):
        await backup_plan_execution_service.execute_run(run.id)
    assert calls[:2] == [("pre-backup", first.id), ("pre-backup", second.id)]
```

- [ ] Run the new execution tests and confirm they fail on the current single-script path.

- [ ] Extend `PlanRunContext` with `script_hooks` and load ordered assignments in `_prepare_run`.

- [ ] Refactor `_execute_plan_script` so it can execute a specific assignment and respect assignment timeout, parameter values, and context string.

- [ ] Add `_execute_plan_script_hooks` for pre/post chains, failure behavior, and post-backup run-condition filtering.

- [ ] Run the targeted execution tests and existing plan script tests.

```bash
pytest tests/unit/test_api_backup_plans.py -k "script or hooks" -q
```

## Task 3: Script Deletion Cleanup

- [ ] Add a failing test in `tests/unit/test_api_scripts_library.py` proving deleting a script removes `BackupPlanScript` rows and clears legacy fields.

- [ ] Update `compute_script_usage_counts` and delete cleanup in `app/api/scripts_library.py` to include `BackupPlanScript`.

- [ ] Run the focused script library tests.

```bash
pytest tests/unit/test_api_scripts_library.py -k "backup_plan_references or usage" -q
```

## Task 4: Frontend State And Payload Mapping

- [ ] Add failing frontend tests that `planToState` converts old pre/post fields to `scriptHooks`, preserves API `script_hooks`, and `buildBackupPlanPayload` emits ordered `script_hooks`.

```bash
cd frontend
npm test -- src/pages/__tests__/BackupPlans.test.tsx --run
```

- [ ] Add shared frontend types: `ScriptRunCondition`, `ScriptFailureMode`, and `BackupPlanScriptHook`.

- [ ] Extend `WizardState` with `scriptHooks`.

- [ ] Map legacy pre/post fields into `scriptHooks` in `planToState` when no `script_hooks` exist.

- [ ] Emit `script_hooks` in `buildBackupPlanPayload` and keep legacy first pre/post fields for compatibility.

- [ ] Run focused mapping tests.

```bash
cd frontend
npm test -- src/pages/__tests__/BackupPlans.test.tsx --run
```

## Task 5: Backup Plan Scripts Step UI

- [ ] Add failing tests in `frontend/src/pages/backup-plans/__tests__/ScriptsStep.test.tsx` for adding two scripts, choosing post run condition, configuring pre failure behavior, and not rendering inline script controls.

- [ ] Replace the `ScriptSelectorSection` usage in `ScriptsStep.tsx` with controlled chain sections for pre and post hooks.

- [ ] Use MUI outlined rows, lucide icon buttons, chips, `ScriptParameterInputs`, and compact controls. Keep the database source scripts summary and repository-scripts checkbox.

- [ ] Update `ReviewStep.tsx` to summarize ordered plan script hooks rather than only one pre/post script.

- [ ] Add/adjust locale keys in all frontend locale files.

- [ ] Run focused UI tests.

```bash
cd frontend
npm test -- src/pages/backup-plans/__tests__/ScriptsStep.test.tsx --run
```

## Task 6: Storybook And Visual Proof

- [ ] Update `ScriptsStep.stories.tsx` with a `PlanScriptChains` story showing multiple pre and post hooks, parameter values, failure behavior, and run condition chips.

- [ ] Run Storybook snapshot generation for local proof if the build is stable.

```bash
cd frontend
npm run snapshots
```

## Task 7: Full Validation And Handoff

- [ ] Run backend checks.

```bash
ruff check app tests
ruff format --check app tests
pytest tests/unit/test_api_backup_plans.py tests/unit/test_api_scripts_library.py
```

- [ ] Run frontend checks.

```bash
cd frontend
npm run check:locales
npm run typecheck
npm run lint
npm run build
```

- [ ] Launch Borg UI locally and walk through Backup Plan create/edit scripts.

```bash
./scripts/dev.sh
```

- [ ] Commit, push, open/update the PR with the Borg UI PR template, attach it to Linear, add `symphony`, run the PR feedback sweep, and move Linear to Human Review only after checks are green.
