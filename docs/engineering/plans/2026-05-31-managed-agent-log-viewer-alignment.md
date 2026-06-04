# Managed Agent Log Viewer Alignment Implementation Plan

**Goal:** Align Managed Agents log actions and viewers with Borg UI's shared log-viewing pattern.

**Architecture:** Move the generic log viewer files into `components/shared`, preserve old import paths with re-export shims, and extend the shared dialog to accept custom log fetchers for managed-agent APIs. Managed Agents maps agent/job log entries into the shared terminal log line shape.

**Tech Stack:** React, TypeScript, MUI, lucide-react, TanStack Query, Vitest, Storybook snapshots.

---

### Task 1: Red Tests For Managed Agents Logs

**Files:**
- Modify: `frontend/src/pages/__tests__/ManagedAgents.test.tsx`
- Modify: `frontend/src/components/__tests__/LogViewerDialog.test.tsx`

- [ ] **Step 1: Add failing Managed Agents tests**

Add tests asserting that the agent-card "View agent logs" action and job-row
"View logs" action render an `Eye` icon instead of `Terminal`, and that job
logs open with the shared viewer title `Agent Job Logs - Job #<id>`.

- [ ] **Step 2: Add failing shared viewer test**

Add a test proving `LogViewerDialog` can use a caller-provided `onFetchLogs`
function instead of the activity API.

- [ ] **Step 3: Run the targeted tests and confirm RED**

Run:

```bash
cd frontend && npm run test -- src/pages/__tests__/ManagedAgents.test.tsx src/components/__tests__/LogViewerDialog.test.tsx --run -t "logs"
```

Expected before implementation: tests fail because Managed Agents uses terminal
icons/raw dialogs and `LogViewerDialog` has no custom fetcher prop.

### Task 2: Shared Log Viewer Source

**Files:**
- Move: `frontend/src/components/LogViewerDialog.tsx` to `frontend/src/components/shared/LogViewerDialog.tsx`
- Move: `frontend/src/components/TerminalLogViewer.tsx` to `frontend/src/components/shared/TerminalLogViewer.tsx`
- Create: `frontend/src/components/LogViewerDialog.tsx`
- Create: `frontend/src/components/TerminalLogViewer.tsx`
- Modify: `frontend/src/components/__tests__/LogViewerDialog.test.tsx`

- [ ] **Step 1: Move source files to shared**

Update imports inside the moved files for their new location. Export shared
types for log lines and fetch results.

- [ ] **Step 2: Preserve old import paths**

Add thin re-export shims at the old component paths so existing consumers do
not need a broad import churn.

- [ ] **Step 3: Extend `LogViewerDialog`**

Add an optional `onFetchLogs(offset)` prop. When present, use it for
`TerminalLogViewer`; when absent, keep the existing activity API behavior.
Skip activity-status polling for custom log sources.

- [ ] **Step 4: Run shared viewer tests and confirm GREEN**

Run:

```bash
cd frontend && npm run test -- src/components/__tests__/LogViewerDialog.test.tsx --run
```

Expected after implementation: `LogViewerDialog` tests pass.

### Task 3: Managed Agents Integration

**Files:**
- Modify: `frontend/src/pages/ManagedAgents.tsx`
- Modify: `frontend/src/pages/__tests__/ManagedAgents.test.tsx`
- Modify: `frontend/src/pages/ManagedAgents.stories.tsx`

- [ ] **Step 1: Replace log icons**

Import `Eye` from `lucide-react` and use it only for log-view actions. Keep
`Terminal` where the UI describes an install command.

- [ ] **Step 2: Replace raw log dialogs**

Create `AgentJobLogsDialog` and update `AgentSessionLogsDialog` to wrap shared
`LogViewerDialog`. Convert managed-agent API log entries into
`{ line_number, content }` viewer lines, preserving command and job context for
session logs.

- [ ] **Step 3: Update stories**

Add or update Managed Agents stories so reviewers can see agent session logs
and agent job logs in the shared viewer.

- [ ] **Step 4: Run Managed Agents tests and confirm GREEN**

Run:

```bash
cd frontend && npm run test -- src/pages/__tests__/ManagedAgents.test.tsx --run
```

Expected after implementation: Managed Agents tests pass.

### Task 4: Verification And Handoff

**Files:**
- Generated: `frontend/storybook-snapshots/**`

- [ ] **Step 1: Run required frontend checks**

Run:

```bash
cd frontend && npm run check:locales
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
```

- [ ] **Step 2: Run Storybook snapshots**

Run:

```bash
cd frontend && npm run snapshots
```

- [ ] **Step 3: Run runtime walkthrough**

Launch Borg UI locally and verify the Managed Agents agent-card and job-row log
actions open the shared log viewer with expected log content.
