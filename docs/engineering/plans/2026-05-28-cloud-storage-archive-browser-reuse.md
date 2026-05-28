# Cloud Storage Archive Browser Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reuse the archive browsing UI for Cloud Storage remote browsing.

**Architecture:** Extract the archive contents browser chrome into a shared
presentational component that accepts normalized file entries, loading state,
breadcrumbs, and optional archive-specific row adornments. Keep archive and
rclone data fetching in their existing callers.

**Tech Stack:** React, TypeScript, MUI, TanStack Query, lucide-react, Vitest,
Storybook snapshots.

---

## Implementation Tasks

### Task 1: Capture Cloud Storage Navigation Test

**Files:**

- Modify: `frontend/src/pages/__tests__/CloudStorage.test.tsx`

- [ ] Add a test named `navigates folders in the reusable browse dialog`.
- [ ] Mock `rcloneAPI.browseRemote` so path `''` returns a directory named
      `borg-ui`, and path `borg-ui` returns `archive.tar`.
- [ ] Render `<CloudStorage />`, click `Browse remote`, click the `borg-ui`
      folder button, and expect `rcloneAPI.browseRemote` to have been called
      with `(10, 'borg-ui')`.
- [ ] Expect the dialog to show `archive.tar` and a breadcrumb button for
      `Root`.
- [ ] Run:

```bash
cd frontend && npm test -- src/pages/__tests__/CloudStorage.test.tsx --run
```

Expected before implementation: the new test fails because folder rows are not
buttons and no non-root browse call is made.

### Task 2: Extract Reusable Browser Component

**Files:**

- Create: `frontend/src/components/StorageBrowserDialog.tsx`
- Create: `frontend/src/utils/storageBrowserPaths.ts`
- Modify: `frontend/src/components/ArchiveContentsDialog.tsx`
- Test: `frontend/src/components/__tests__/ArchiveContentsDialog.test.tsx`

- [ ] Create `StorageBrowserDialog` with exported `StorageBrowserItem` and
      a shared `normalizeBrowserPath` utility.
- [ ] Render a responsive dialog with title/subtitle, breadcrumbs, loading
      skeletons, directory-first file rows, empty-root and empty-directory
      states, optional banner, optional row badge/tooltip, and optional file
      download action.
- [ ] Use semantic button rows for folders so folder navigation is
      keyboard-accessible.
- [ ] Replace the inline browser markup in `ArchiveContentsDialog` with
      `StorageBrowserDialog`, mapping archive API items into
      `StorageBrowserItem`.
- [ ] Preserve archive behavior: reset path on archive open/change, call
      `getArchiveContents(archive.id, archive.name, path)`, show canary badge
      and banner, and call `onDownloadFile(archive.name, file.path)`.
- [ ] Run:

```bash
cd frontend && npm test -- src/components/__tests__/ArchiveContentsDialog.test.tsx --run
```

Expected after implementation: archive tests continue to pass.

### Task 3: Use Shared Browser In Cloud Storage

**Files:**

- Modify: `frontend/src/pages/CloudStorage.tsx`
- Modify: `frontend/src/pages/CloudStorage.stories.tsx`
- Modify: `frontend/src/pages/__tests__/CloudStorage.test.tsx`

- [ ] Import `StorageBrowserDialog` and map rclone entries to
      `StorageBrowserItem` with `directory` or `file` type.
- [ ] Change the browse mutation variable to `{ remote, path }`, call
      `rcloneAPI.browseRemote(remote.id, path)`, and update `browseState` with
      the returned path and entries.
- [ ] Pass `onNavigate` from the dialog to browse the current remote at the
      selected folder or breadcrumb path.
- [ ] Update the `BrowseDialog` Storybook story to show a nested path and
      entries that demonstrate breadcrumbs.
- [ ] Re-run:

```bash
cd frontend && npm test -- src/pages/__tests__/CloudStorage.test.tsx --run
```

Expected after implementation: the new Cloud Storage navigation test passes.

### Task 4: Validation And Handoff

**Files:**

- Modify generated snapshots under `frontend/storybook-snapshots/`.

- [ ] Run targeted tests:

```bash
cd frontend && npm test -- src/pages/__tests__/CloudStorage.test.tsx src/components/__tests__/ArchiveContentsDialog.test.tsx --run
```

- [ ] Run required frontend validation:

```bash
cd frontend && npm run check:locales
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
```

- [ ] Run snapshots:

```bash
cd frontend && npm run snapshots
```

- [ ] Run a local Storybook or app walkthrough that opens the Cloud Storage
      browse dialog, clicks a folder, and returns via breadcrumb.
- [ ] Update the Linear workpad with validation evidence, commit, push, create
      or update the PR, sweep feedback/checks, and move BOR-81 to Human Review
      only after all gates pass.
