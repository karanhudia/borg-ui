# Backup Plan Agent Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move managed-agent backup source ownership out of repository setup and make Backup Plans the normal source configuration surface.

**Architecture:** Repository records may still read legacy source fields for compatibility, but managed-agent create/edit should no longer require or capture them for normal full-mode setup. Backup Plan execution already passes plan source settings into agent jobs; tests will pin that contract for agent repositories with no repository-level sources. Manual repository backup remains a legacy path and returns a plan-source-specific error when no legacy repository sources exist.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, MUI, Vitest, Storybook.

---

### Task 1: Backend Agent Repository Setup

**Files:**
- Modify: `tests/unit/test_api_repositories.py`
- Modify: `app/api/repositories.py`

- [ ] **Step 1: Write the failing create test**

Add a test near `test_create_agent_repository_records_target_without_server_init`:

```python
def test_create_agent_repository_without_source_paths(
    self, test_client: TestClient, admin_headers, test_db
):
    agent = AgentMachine(
        name="Laptop",
        agent_id="agt_laptop_no_sources",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)

    with (
        patch(
            "app.api.repositories.initialize_borg_repository",
            new=AsyncMock(return_value={"success": True}),
        ) as initialize,
        patch("app.api.repositories.mqtt_service.sync_state_with_db"),
    ):
        response = test_client.post(
            "/api/repositories/",
            json={
                "name": "Agent Repo Without Sources",
                "path": "/agent/repo-no-sources",
                "encryption": "none",
                "compression": "lz4",
                "execution_target": "agent",
                "agent_machine_id": agent.id,
            },
            headers=admin_headers,
        )

    assert response.status_code == 200
    initialize.assert_not_awaited()
    repo = test_db.query(Repository).filter_by(name="Agent Repo Without Sources").one()
    assert repo.executor_type == "agent"
    assert repo.execution_target == "agent"
    assert repo.agent_machine_id == agent.id
    assert repo.source_directories is None
    assert repo.source_locations is None
    assert repo.source_ssh_connection_id is None
```

- [ ] **Step 2: Verify it fails**

Run:

```bash
pytest tests/unit/test_api_repositories.py::TestRepositoriesCreate::test_create_agent_repository_without_source_paths -q
```

Expected: FAIL with HTTP 400 using `backend.errors.repo.atLeastOneSourceDirRequired`.

- [ ] **Step 3: Implement minimal backend change**

In `_validate_agent_repository_payload`, remove the full-mode source directory requirement. Keep passphrase and queueable-agent validation intact.

- [ ] **Step 4: Verify it passes**

Run the same pytest command and expect PASS.

### Task 2: Plan-Run Agent Execution Contract

**Files:**
- Modify: `tests/unit/test_api_backup_plans.py`
- No production code expected unless the test exposes a regression.

- [ ] **Step 1: Write the failing or pinning test**

Adjust `test_execute_plan_run_routes_agent_repository_through_agent_job` so the repository has no legacy `source_directories`, while the plan still has `source_directories=json.dumps(["/srv/project"])`.

Expected assertions:

```python
assert repo.source_directories is None
assert agent_job.payload["backup"]["source_paths"] == ["/srv/project"]
```

- [ ] **Step 2: Verify the contract**

Run:

```bash
pytest tests/unit/test_api_backup_plans.py::TestBackupPlanRoutes::test_execute_plan_run_routes_agent_repository_through_agent_job -q
```

Expected: PASS if plan sources are already authoritative.

### Task 3: Explicit Manual Backup Behavior

**Files:**
- Modify: `tests/unit/test_api_backup.py`
- Modify: `app/services/repository_executor.py`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] **Step 1: Write the failing manual-backup test**

Add a test near the existing agent manual backup tests:

```python
def test_start_backup_for_agent_repository_without_sources_explains_plan_sources(
    self, test_client: TestClient, admin_headers, test_db
):
    agent = AgentMachine(
        name="Laptop",
        agent_id="agt_laptop_no_sources",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
    )
    repo = Repository(
        name="Agent Repo Without Sources",
        path="/agent/repo-no-sources",
        encryption="none",
        compression="lz4",
        repository_type="local",
        execution_target="agent",
        executor_type="agent",
        agent_machine_id=agent.id,
    )
    test_db.add_all([agent, repo])
    test_db.commit()

    response = test_client.post(
        "/api/backup/start",
        json={"repository": repo.path},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "key": "backend.errors.repo.agentManualBackupRequiresPlanSources"
    }
```

- [ ] **Step 2: Verify it fails**

Run:

```bash
pytest tests/unit/test_api_backup.py::TestBackupStart::test_start_backup_for_agent_repository_without_sources_explains_plan_sources -q
```

Expected: FAIL with the old generic source directory key.

- [ ] **Step 3: Implement minimal backend and locale change**

Change `validate_agent_backup_repository` so an absent repository-source manual backup raises `backend.errors.repo.agentManualBackupRequiresPlanSources`. Add the same key to all locale files.

- [ ] **Step 4: Verify it passes**

Run the same pytest command and expect PASS.

### Task 4: Frontend Wizard Flow And Copy

**Files:**
- Modify: `frontend/src/components/RepositoryWizard.tsx`
- Modify: `frontend/src/components/wizard/WizardStepReview.tsx`
- Modify: `frontend/src/components/__tests__/RepositoryWizard.test.tsx`
- Modify: `frontend/src/components/wizard/WizardStepReview.stories.tsx`
- Modify: locale files as needed.

- [ ] **Step 1: Write failing wizard test**

Change the managed-agent create test so it does not visit the source step or add source paths. It should assert the step list omits `Source` and submitted payload has `source_directories: []`, `source_locations: []`, and `source_connection_id: null`.

- [ ] **Step 2: Verify it fails**

Run:

```bash
cd frontend && npm test -- --run src/components/__tests__/RepositoryWizard.test.tsx -t "submits managed-agent execution target fields"
```

Expected: FAIL because current code shows the source step and disables progression until a source path is added.

- [ ] **Step 3: Implement wizard changes**

Remove the normal agent full-mode source step from create/import/edit unless legacy repository source settings already exist. Add review copy that says managed-agent source paths are configured on Backup Plans when no legacy source paths are present.

- [ ] **Step 4: Add Storybook coverage**

Create a `WizardStepReview` story for an agent repository with no repository sources and visible plan-owned source copy.

- [ ] **Step 5: Verify targeted frontend tests**

Run:

```bash
cd frontend && npm test -- --run src/components/__tests__/RepositoryWizard.test.tsx src/components/wizard/__tests__/WizardStepReview.test.tsx
```

Expected: PASS.

### Task 5: Validation And Handoff

**Files:**
- Update: `frontend/storybook-snapshots/*` from snapshot generation.
- Update: Linear workpad and PR metadata.

- [ ] **Step 1: Run required backend checks**

```bash
ruff check app tests
ruff format --check app tests
pytest tests/unit/test_api_repositories.py tests/unit/test_api_backup.py tests/unit/test_api_backup_plans.py
```

- [ ] **Step 2: Run required frontend checks**

```bash
cd frontend && npm run check:locales && npm run typecheck && npm run lint && npm run build
```

- [ ] **Step 3: Generate Storybook snapshots**

```bash
cd frontend && npm run snapshots
```

- [ ] **Step 4: Runtime walkthrough**

Launch the app with the repository-supported local workflow and verify the managed-agent repository create path reaches review without source paths and the Backup Plan source step remains the source configuration surface.

- [ ] **Step 5: Publish**

Commit, push, open/link the PR, add the `symphony` label, run the PR feedback sweep, confirm green checks, update the Linear workpad, and move BOR-41 to Human Review.
