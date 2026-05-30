# Rclone Path Browsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development for implementation and
> superpowers:verification-before-completion before claiming completion. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Borg 2 advanced direct rclone repository setup use connected
rclone remotes and browse a remote folder while preserving manual rclone URL
entry.

**Architecture:** Keep the direct Borg 2 rclone repository contract as a single
stored `path` value. Extend the Location step with optional connected-storage
selection that composes `rclone://<remote>/<path>` and routes the existing
folder icon to the shared rclone remote folder picker instead of the local/SSH
filesystem picker.

**Tech Stack:** React, TypeScript, MUI, lucide/MUI icons, Vitest, Storybook
snapshots.

---

## Design Notes

- Use the existing compact MUI wizard form style. The UI skill recommended a
  SaaS dashboard system, but this is an operational form surface, so avoid
  decorative glass/hero patterns and keep the change as ordinary labeled form
  controls.
- Keep the direct URL field visible and editable because manual Borg 2 rclone
  URLs remain supported.
- Add a `Rclone Remote` select only for Borg 2 direct rclone mode when remotes
  are available. Selecting a remote updates the direct URL prefix and preserves
  the current relative remote path when possible.
- Enable the folder icon in direct rclone mode when a connected remote is
  selected. It opens `RcloneRemoteFolderPickerDialog` and writes the selected
  folder back as a full direct rclone URL.
- Preserve the Cloud Mirror step and its rclone path browsing behavior for
  non-direct repository locations.

## Task 1: Capture The Direct Rclone Location Regression

**Files:**

- Modify: `frontend/src/components/wizard/__tests__/WizardStepLocation.test.tsx`

- [ ] Add a failing test proving Borg 2 direct rclone mode renders the connected
      `Rclone Remote` select, keeps the direct URL field editable, and enables a
      `Browse rclone remote` icon button when a remote is selected.
- [ ] Update the current direct rclone test so it no longer asserts disabled
      filesystem browsing in direct mode.
- [ ] Run:

```bash
cd frontend && npm run test -- --run src/components/wizard/__tests__/WizardStepLocation.test.tsx -t "direct rclone"
```

Expected before implementation: the new test fails because `WizardStepLocation`
does not accept or render rclone remotes and the browse button is disabled in
direct mode.

## Task 2: Capture End-To-End Wizard Browsing

**Files:**

- Modify: `frontend/src/components/__tests__/RepositoryWizard.test.tsx`

- [ ] Add a failing test that selects Borg 2, enables direct rclone mode,
      selects `prod-s3`, opens the rclone browser, chooses
      `borg-ui/repositories`, and verifies the direct URL field becomes
      `rclone://prod-s3/borg-ui/repositories`.
- [ ] Submit the wizard and assert the payload keeps
      `storage_backend: "rclone_direct"` and sends the composed URL in `path`
      without cached rclone mirror fields.
- [ ] Run:

```bash
cd frontend && npm run test -- --run src/components/__tests__/RepositoryWizard.test.tsx -t "direct Borg 2 rclone"
```

Expected before implementation: the new test fails because direct mode has no
remote select and its folder icon does not open the rclone browser.

## Task 3: Implement Direct Rclone Remote Selection And Browse

**Files:**

- Modify: `frontend/src/components/wizard/WizardStepLocation.tsx`
- Modify: `frontend/src/components/RepositoryWizard.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify as needed: `frontend/src/locales/de.json`,
  `frontend/src/locales/es.json`, `frontend/src/locales/it.json`

- [ ] Extend the Location step props/data with optional `rcloneStatus`,
      `rcloneRemotes`, `rcloneRemoteId`, `rcloneRemotePath`, and
      `onBrowseDirectRclonePath`.
- [ ] Add small helpers for parsing and composing `rclone://remote/path` values
      inside the Location step or wizard file.
- [ ] Add dedicated helper unit tests for `parseDirectRcloneUrl`,
      `formatDirectRcloneUrl`, and `normalizeRcloneRemotePath`, covering empty
      strings, missing remote names, invalid schemes, missing or trailing
      slashes, and normalized relative paths before relying on the helpers in
      the wizard flow.
- [ ] Render the connected remote select in direct mode when rclone is
      available and remotes are loaded.
- [ ] On remote selection, update `rcloneRemoteId`, preserve the relative
      folder path when present, and compose the direct repository URL.
- [ ] On direct URL edits, keep the selected remote and relative path in sync
      when the URL matches a loaded remote.
- [ ] In `RepositoryWizard`, pass rclone data to the Location step, route direct
      browse clicks to `RcloneRemoteFolderPickerDialog`, and write selected
      folders back to the direct URL field.
- [ ] Preserve existing Cloud Mirror path browsing behavior and existing direct
      rclone payload shape.

## Task 4: Storybook And Snapshots

**Files:**

- Modify: `frontend/src/components/wizard/WizardStepLocation.stories.tsx`
- Snapshot: `frontend/storybook-snapshots/`

- [ ] Update the direct Borg 2 rclone story to show a connected remote selected
      and an editable composed URL.
- [ ] Run:

```bash
cd frontend && npm run snapshots
```

## Task 5: Validation And Handoff

**Files:**

- Modify as required by validation fixes only.

- [ ] Run targeted frontend tests:

```bash
cd frontend && npm run test -- --run src/components/wizard/__tests__/WizardStepLocation.test.tsx src/components/__tests__/RepositoryWizard.test.tsx
```

- [ ] Run required frontend validation:

```bash
cd frontend && npm run check:locales
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
```

- [ ] Run an app walkthrough that opens the repository wizard, selects Borg 2,
      enables direct rclone mode, selects a connected remote, browses a remote
      folder, and observes the composed direct URL.
- [ ] Commit, push, create/update the PR with `.github/PULL_REQUEST_TEMPLATE.md`,
      ensure the `symphony` PR label, sweep PR feedback/checks, and move BOR-100
      to Human Review only when all gates pass.

## Self-Review

- The plan maps each acceptance criterion to a test, implementation task, story,
  or walkthrough.
- Existing Cloud Mirror and manual direct URL behavior are explicitly preserved.
- No placeholders remain; command paths are concrete.
