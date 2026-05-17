# BOR-27 Managed Agent Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the existing managed CLI agent branch so it can be reviewed as the BOR-27 client/server remote-agent MVP.

**Architecture:** Keep the branch's split architecture: FastAPI server APIs and persistence under `app/`, lightweight polling CLI under `agent/`, and React/MUI management UI under `frontend/src/pages/ManagedAgents.tsx`. The hardening pass focuses on merge correctness, Storybook coverage, and validation rather than expanding the product surface.

**Tech Stack:** Python/FastAPI/SQLAlchemy/Pytest/Ruff, React/Vite/MUI/Storybook/Vitest, Linear/GitHub workflow.

---

### Task 1: Merge And Reconcile Latest Main

**Files:**
- Modify: merge-conflicted backend and frontend files already touched by `origin/main`.
- Track: Linear `## Codex Workpad`.

- [x] **Step 1: Fetch and sync branch**

Run:

```bash
git fetch origin
git pull --ff-only origin feature/managed-cli-agent
```

Expected: feature branch is current with origin.

- [x] **Step 2: Restore merge base when needed**

Run:

```bash
git fetch --unshallow origin
git merge-base feature/managed-cli-agent origin/main
```

Expected: a merge base SHA is printed.

- [x] **Step 3: Merge `origin/main`**

Run:

```bash
git -c merge.conflictstyle=zdiff3 merge origin/main
```

Expected: conflicts are surfaced and then resolved.

- [x] **Step 4: Verify merge hygiene**

Run:

```bash
git diff --check
```

Expected: no whitespace errors or conflict markers.

### Task 2: Capture Current Behavior Signal

**Files:**
- Read: `frontend/src/pages/ManagedAgents.tsx`
- Read: `app/api/agents.py`
- Read: `app/api/managed_machines.py`
- Read: `agent/borg_ui_agent/*`

- [x] **Step 1: Confirm branch contains managed-agent implementation**

Run:

```bash
rg -n "ManagedAgents|managedAgentsAPI|AgentMachine|AgentRuntime" frontend/src app agent tests
```

Expected: server APIs, frontend page, agent runtime, and tests are present.

- [x] **Step 2: Confirm missing Storybook coverage**

Run:

```bash
rg --files frontend/src | rg 'ManagedAgents|managed.*stories|Agent.*stories'
```

Expected before fix: only `frontend/src/pages/ManagedAgents.tsx` appears, with no story.

### Task 3: Add Managed Agents Storybook Coverage

**Files:**
- Modify: `frontend/src/pages/ManagedAgents.tsx`
- Create: `frontend/src/pages/ManagedAgents.stories.tsx`
- Generated: `frontend/storybook-snapshots/pages-managedagents--fleet-overview.png`

- [x] **Step 1: Export presentational subcomponents**

Change `AgentList`, `JobsTable`, and `TokensTable` to named exports so Storybook can render the real UI states without mocking auth and network hooks.

- [x] **Step 2: Add realistic story data**

Create `frontend/src/pages/ManagedAgents.stories.tsx` with sample online/offline agents, queued/running/completed jobs, and active/used/revoked tokens. Render the exported components in a constrained page-width MUI layout.

- [x] **Step 3: Run snapshot generation**

Run:

```bash
cd frontend && npm run snapshots
```

Expected: Storybook builds and writes a `pages-managedagents--fleet-overview.png` snapshot.

### Task 4: Validation And Fixes

**Files:**
- Modify only files implicated by failing checks.
- Update: Linear workpad validation checkboxes.

- [x] **Step 1: Backend validation**

Run:

```bash
ruff check app tests
ruff format --check app tests
pytest tests/unit/test_api_agents.py tests/unit/test_agent_runtime.py tests/unit/test_api_backup.py tests/unit/test_api_repositories.py -q
```

Expected: all pass.

- [x] **Step 2: Frontend validation**

Run:

```bash
cd frontend && npm run check:locales
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
```

Expected: all pass.

- [x] **Step 3: Runtime walkthrough**

Run Borg UI locally using an available repository smoke path and capture evidence that `/managed-agents` renders the management surface.

### Task 5: Publish For Review

**Files:**
- Update: `.github/PULL_REQUEST_TEMPLATE.md` content through PR body.
- Update: Linear workpad only.

- [ ] **Step 1: Commit final hardening changes**

Run:

```bash
git status --short
git add app/api/backup.py app/api/repositories.py docs/engineering/specs/2026-05-17-bor-27-managed-agent-hardening.md docs/engineering/plans/2026-05-17-bor-27-managed-agent-hardening.md frontend/src/pages/ManagedAgents.tsx frontend/src/pages/ManagedAgents.stories.tsx frontend/storybook-snapshots/pages-managedagents--fleet-overview.png
git commit -m "test: cover managed agents hardening"
```

Expected: one focused commit after the merge commit.

- [ ] **Step 2: Push and open/update PR**

Run the repository push workflow, attach the PR to BOR-27, apply the `symphony` label, sweep PR feedback, and move Linear to `Human Review` only after checks are green.
