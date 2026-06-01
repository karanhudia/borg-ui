# GitHub Pages Visual Regression Implementation Plan

**Goal:** Replace Argos with opt-in GitHub Pages visual reports and automatic
`main` baselines.

**Architecture:** Reuse the existing Storybook screenshot capture script. Add a
PNG comparison/report generator, a PR-description section updater, and a
GitHub Actions workflow that stores visual state in a branch while deploying the
current docs site plus `/visual` reports through GitHub Pages.

**Tech Stack:** GitHub Actions, GitHub Pages, VitePress docs, Node ESM scripts,
Vitest, `pngjs`, Storybook, Playwright.

---

## Files

- Create: `frontend/scripts/visual-regression-report.mjs`
- Create: `frontend/scripts/visual-regression-report.test.mjs`
- Create: `frontend/scripts/visual-pr-description.mjs`
- Create: `frontend/scripts/visual-pr-description.test.mjs`
- Modify: `frontend/scripts/argos-workflow-config.test.mjs`
- Modify: `frontend/package.json`
- Rename: `.github/workflows/argos-visual-regression.yml` to
  `.github/workflows/visual-regression.yml`
- Modify: `.github/workflows/pages.yml`
- Modify: `docs/testing.md`

## Tasks

### Task 1: Report Generator

- [x] Write failing tests that create tiny PNG baselines/actuals and expect
      changed, added, removed, and unchanged summary counts.
- [x] Implement `visual-regression-report.mjs` with `compareVisualSnapshots()`,
      diff PNG output, `summary.json`, and static `index.html`.
- [x] Run `cd frontend && npm run test -- scripts/visual-regression-report.test.mjs --run`.

### Task 2: PR Body Section

- [x] Write failing tests for marker replacement and generated report summary.
- [x] Implement `visual-pr-description.mjs` pure helpers and CLI update flow.
- [x] Run `cd frontend && npm run test -- scripts/visual-pr-description.test.mjs --run`.

### Task 3: Workflow Wiring

- [x] Update workflow tests to expect GitHub Pages visual regression instead of
      Argos upload.
- [x] Replace the Argos workflow with a label-gated GitHub Pages visual workflow.
- [x] Update `pages.yml` so docs deployments preserve `/visual`.
- [x] Update package scripts from `argos:*` to `visual:*`.
- [x] Run `cd frontend && npm run test -- scripts/argos-workflow-config.test.mjs --run`.

### Task 4: Docs and Verification

- [x] Update `docs/testing.md` with the label/manual review flow and Pages report
      URL behavior.
- [x] Run `git diff --check`.
- [x] Run focused frontend script tests.
- [x] Run `cd frontend && npm run check:locales && npm run typecheck && npm run lint && npm run build`.
