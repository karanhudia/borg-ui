# Auto-Filled Variable Value Disclosure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or equivalent task-by-task execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users verify database source script values that are auto-filled from the selected source.

**Architecture:** Keep the change inside the backup-plan Scripts step. Derive a compact list of non-empty database script parameters from each source row, expose them through a focusable tooltip next to the existing chip, and update the existing component test and Storybook state.

**Tech Stack:** React 18, MUI 7, lucide-react, Vitest, Testing Library, Storybook.

---

## Task 1: Add Failing Test Coverage

**Files:**
- Modify: `frontend/src/pages/backup-plans/__tests__/ScriptsStep.test.tsx`

- [ ] Add `@testing-library/user-event` to the test imports.
- [ ] Extend the existing database source fixtures so the SQLite row has a pre
  parameter and a post parameter, while the MySQL row keeps empty parameter maps.
- [ ] Assert the existing `Auto-filled from source` chips still render.
- [ ] Assert a button named `View auto-filled source values for SQLite database`
  exists and the corresponding MySQL button does not.
- [ ] Hover or focus the SQLite button and assert the tooltip shows
  `Pre: SQLITE_DATABASE_PATH=/home/app/state.sqlite` and
  `Post: SQLITE_DUMP_PATH=/var/tmp/borg-ui/database-dumps/sqlite`.
- [ ] Run
  `cd frontend && npm test -- --run src/pages/backup-plans/__tests__/ScriptsStep.test.tsx`
  and confirm the new assertions fail before implementation.

## Task 2: Implement Tooltip Disclosure

**Files:**
- Modify: `frontend/src/pages/backup-plans/wizard-step/ScriptsStep.tsx`
- Modify: `frontend/src/locales/en.json`

- [ ] Import MUI `IconButton` and `Tooltip`, plus a lucide help/info icon.
- [ ] Add a helper that converts a parameter record into sorted non-empty
  `KEY=value` strings.
- [ ] Add a helper that returns pre/post grouped tooltip lines for each database
  source row.
- [ ] Render the existing chip unchanged.
- [ ] Render a small focusable icon button only when grouped tooltip lines
  exist. Use `aria-label` from a new translation key and pass the database name
  as the interpolation value.
- [ ] Use `Tooltip` with a line-preserving title so multiple values remain
  scannable.
- [ ] Run the focused test and confirm it passes.

## Task 3: Update Storybook Coverage

**Files:**
- Modify: `frontend/src/pages/backup-plans/wizard-step/ScriptsStep.stories.tsx`

- [ ] Add a post-script parameter to the existing database source story state.
- [ ] Add the new tooltip aria-label translation key to the story translation
  map.
- [ ] Confirm the story still renders the existing database source summary and
  now includes a visible tooltip trigger for the auto-filled values.

## Task 4: Validate And Publish

**Commands:**
- `cd frontend && npm test -- --run src/pages/backup-plans/__tests__/ScriptsStep.test.tsx`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- Local UI walkthrough with Storybook or an equivalent local frontend runtime
- `git diff --check`

- [ ] Confirm focused tests pass.
- [ ] Confirm all required frontend validation commands pass.
- [ ] Capture local UI walkthrough evidence in the Linear workpad.
- [ ] Commit, push, create/update the PR using `.github/PULL_REQUEST_TEMPLATE.md`,
  attach it to Linear, add the `symphony` label, sweep PR feedback/checks, and
  move Linear to Human Review only after the completion bar is met.
