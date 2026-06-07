# Repository Break-Lock Action Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a direct repository-card `Break lock` action that reuses the existing lock-break API, RBAC helper, and confirmation dialog.

**Architecture:** Keep backend behavior unchanged because `POST /api/repositories/{repo_id}/break-lock` already enforces repository operator access and the global lock-breaking setting. Add a small callback surface through `RepositoryCard` and `RepositoryGroups`, then have `Repositories` open the existing `LockErrorDialog` with the selected repository.

**Tech Stack:** React, TypeScript, MUI, lucide-react, TanStack Query, Vitest, Storybook.

---

## Task 1: RepositoryCard Red/Green Coverage

**Files:**

- Modify: `frontend/src/components/__tests__/RepositoryCard.test.tsx`
- Modify: `frontend/src/components/RepositoryCard.tsx`
- Modify: `frontend/src/components/RepositoryCard.stories.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [x] **Step 1: Add failing RepositoryCard tests**

Add `onBreakLock: vi.fn()` to `mockCallbacks`, then add tests that expect:

```tsx
expect(screen.getByRole('button', { name: /Break Lock/i })).toBeInTheDocument()
expect(screen.queryByRole('button', { name: /Break Lock/i })).not.toBeInTheDocument()
fireEvent.click(screen.getByRole('button', { name: /Break Lock/i }))
expect(mockCallbacks.onBreakLock).toHaveBeenCalledTimes(1)
```

The visible case passes `canBreakLock={true}`. The hidden case passes `canBreakLock={false}`.

- [x] **Step 2: Verify the new tests fail for the missing prop/button**

Run:

```bash
cd frontend && npm test -- --run src/components/__tests__/RepositoryCard.test.tsx
```

Expected: FAIL because `RepositoryCard` does not render a `Break Lock` button yet.

- [x] **Step 3: Implement the minimal RepositoryCard prop and button**

Update `RepositoryCardProps` with:

```ts
onBreakLock: () => void
canBreakLock?: boolean
```

Import `Unlock` from `lucide-react`. In the separated action cluster, render an `IconButton` before `Wipe contents` when `canBreakLock` is true:

```tsx
<Tooltip title={t('repositoryCard.buttons.breakLock')} arrow>
  <span>
    <IconButton
      size="small"
      onClick={onBreakLock}
      aria-label={t('repositoryCard.buttons.breakLock')}
      disabled={isMaintenanceRunning}
      sx={coloredIconBtnSx('warning')}
    >
      <Unlock size={16} />
    </IconButton>
  </span>
</Tooltip>
```

Render the divider when either `canBreakLock` or the existing wipe/delete group is available.

- [x] **Step 4: Add locale and Storybook coverage**

Add `repositoryCard.buttons.breakLock` to all locale files, using the existing lock-dialog translations:

```json
"breakLock": "Break Lock"
```

Update `RepositoryCard.stories.tsx` default args with `onBreakLock: noop` and `canBreakLock: true`, then add a `WithoutBreakLockAccess` story with `canBreakLock: false`.

- [x] **Step 5: Verify RepositoryCard tests pass**

Run:

```bash
cd frontend && npm test -- --run src/components/__tests__/RepositoryCard.test.tsx
```

Expected: PASS.

## Task 2: Repositories Page Wiring

**Files:**

- Modify: `frontend/src/pages/repositories-page/RepositoryGroups.tsx`
- Modify: `frontend/src/pages/Repositories.tsx`
- Modify: `frontend/src/pages/__tests__/Repositories.test.tsx` if an existing page-level test file is present

- [x] **Step 1: Add failing page wiring coverage where local test structure exists**

If an existing Repositories page test file is present, mock a repository where `useLockBreakPermissions().canBreakLock` returns true, click the repo-card `Break Lock` button, and assert the lock dialog heading appears:

```tsx
fireEvent.click(screen.getByRole('button', { name: /Break Lock/i }))
expect(screen.getByRole('heading', { name: /Repository Locked/i })).toBeInTheDocument()
```

- [x] **Step 2: Verify the page wiring test fails before implementation**

Run the specific Repositories page test command if the file exists. If no page test harness exists, record that the component-level red/green tests cover the new callback surface and rely on runtime walkthrough for page wiring.

- [x] **Step 3: Thread the callback through RepositoryGroups**

Add `onBreakLock: (repository: Repository) => void` to `RepositoryGroupsProps` and pass it to `RepositoryCard`:

```tsx
onBreakLock={() => onBreakLock(repository)}
canBreakLock={canBreakLock(repository)}
```

Use a prop named `canBreakLock: (repository: Repository) => boolean` for the group-level predicate.

- [x] **Step 4: Wire Repositories to LockErrorDialog**

In `Repositories.tsx`, add:

```ts
const handleBreakLockRepository = (repository: Repository) => {
  setLockError({
    repositoryId: repository.id,
    repositoryName: repository.name,
    borgVersion: repository.borg_version,
  })
}
```

Pass `onBreakLock={handleBreakLockRepository}` and `canBreakLock={(repository) => canBreakLock({ repository_id: repository.id })}` to `RepositoryGroups`.

- [x] **Step 5: Verify page or component tests pass**

Run the same targeted frontend test command from Step 2 plus the `RepositoryCard` command.

## Task 3: Validation And Handoff

**Files:**

- Modify only if validation exposes defects.

- [x] **Step 1: Run targeted frontend tests**

Run:

```bash
cd frontend && npm test -- --run src/components/__tests__/RepositoryCard.test.tsx
```

Expected: PASS.

- [x] **Step 2: Run required frontend validation**

Run:

```bash
cd frontend && npm run check:locales
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
```

Expected: each command exits 0.

- [x] **Step 3: Run backend spot checks only if backend files change**

If backend files remain unchanged, record existing backend break-lock tests as inspected but not rerun for code changes. If backend files change, run:

```bash
pytest tests/unit/test_api_repositories_dispatch.py::TestRepositoryApiDispatch -q
ruff check app tests
ruff format --check app tests
```

- [x] **Step 4: Runtime walkthrough**

Launch Borg UI locally using the repo-supported script or smoke runner, open the Repositories page, click the repo-card `Break lock` action for an eligible repo, confirm the `Repository Locked` dialog opens, and verify a non-eligible permission state hides the button.

- [ ] **Step 5: Publish**

Commit the focused changes, push the ticket branch, create a PR with `.github/PULL_REQUEST_TEMPLATE.md`, attach the PR to Linear, ensure the PR has the `symphony` label, run the PR feedback sweep, and move the issue to `Human Review` only after checks are green.
