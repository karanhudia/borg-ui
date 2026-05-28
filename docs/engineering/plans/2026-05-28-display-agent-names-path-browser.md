# Display Agent Names In Path Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show configured managed-agent names in path browser chips instead of ordinal labels such as `Agent #5`.

**Architecture:** `FileExplorerDialog` owns the visible connection chip, so add an optional `agentName` prop and centralize its fallback label there. Existing callers that know the selected agent pass its `name`; callers with only an ID keep the existing `Agent #<id>` fallback.

**Tech Stack:** React, TypeScript, MUI, Vitest, Storybook.

---

### Task 1: Prove The Existing Bug

**Files:**
- Modify: `frontend/src/components/__tests__/FileExplorerDialog.test.tsx`

- [ ] **Step 1: Add a failing managed-agent chip test**

Add a test in the rendering section that renders:

```tsx
<FileExplorerDialog
  open={true}
  onClose={mockOnClose}
  onSelect={mockOnSelect}
  connectionType="agent"
  agentId={42}
  agentName="Build Runner"
/>
```

Assert `Build Runner` is visible and `Agent #42` is absent.

- [ ] **Step 2: Run the focused test**

Run: `cd frontend && npm run test -- src/components/__tests__/FileExplorerDialog.test.tsx --run -t "shows the agent name in the managed-agent connection chip"`

Expected: FAIL because the dialog still renders `Agent #42`.

### Task 2: Implement The Dialog Prop

**Files:**
- Modify: `frontend/src/components/FileExplorerDialog.tsx`
- Modify: `frontend/src/components/PathSelectorField.tsx`

- [ ] **Step 1: Add the optional prop**

Add `agentName?: string` to `FileExplorerDialogProps` and `PathSelectorFieldProps`, then pass it through from `PathSelectorField` to `FileExplorerDialog`.

- [ ] **Step 2: Use a trimmed display label**

In `FileExplorerDialog`, compute:

```ts
const agentLabel = agentName?.trim() || (agentId ? `Agent #${agentId}` : '')
```

Use `agentLabel` for the managed-agent chip label.

- [ ] **Step 3: Verify the focused test passes**

Run: `cd frontend && npm run test -- src/components/__tests__/FileExplorerDialog.test.tsx --run -t "shows the agent name in the managed-agent connection chip"`

Expected: PASS.

### Task 3: Pass Names From Affected Flows

**Files:**
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Modify: `frontend/src/components/RepositoryWizard.tsx`

- [ ] **Step 1: Pass the backup-plan source agent name**

In `SourceSelectionDialog`, pass `agentName={selectedAgent?.name}` to `PathSelectorField` alongside `agentId={selectedAgent?.id}`.

- [ ] **Step 2: Pass the repository wizard agent name**

In `RepositoryWizard`, derive:

```ts
const selectedAgentMachine =
  wizardState.executionTarget === 'agent' && wizardState.agentMachineId
    ? agentMachines.find((agent) => agent.id === Number(wizardState.agentMachineId))
    : null
```

Pass `agentName={selectedAgentMachine?.name}` to the repository path `FileExplorerDialog`.

### Task 4: Storybook Coverage

**Files:**
- Create: `frontend/src/components/FileExplorerDialog.stories.tsx`
- Generated: `frontend/storybook-snapshots/components-fileexplorerdialog--managed-agent-browser.png`

- [ ] **Step 1: Add a focused story**

Create a Storybook story titled `Components/FileExplorerDialog` with a `ManagedAgentBrowser` story that mocks `/managed-machines/agents/42/filesystem/browse` and renders the open dialog with `agentName="Build Runner"`.

- [ ] **Step 2: Generate snapshots**

Run: `cd frontend && npm run snapshots`

Expected: snapshot generation succeeds and creates or updates the FileExplorerDialog snapshot.

### Task 5: Full Frontend Validation And Handoff

**Files:**
- No new source files beyond previous tasks.

- [ ] **Step 1: Run required checks**

Run:

```bash
cd frontend && npm run check:locales
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
```

Expected: all commands pass.

- [ ] **Step 2: Run local UI walkthrough**

Run Borg UI locally with `./scripts/dev.sh`, open a managed-agent path browser in the affected flow, and confirm the visible chip displays the configured agent name.

- [ ] **Step 3: Commit and publish**

Commit the code, story, and snapshot changes, push the feature branch, create/update the PR with the repository template, attach it to Linear, sweep PR feedback/checks, and move BOR-82 to Human Review when green.
