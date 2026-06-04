# Argos Visual Regression CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Storybook visual snapshots out of maintained git artifacts and into Argos CI uploads.

**Architecture:** Reuse the existing Storybook static build and Playwright capture script, but write screenshots into an ignored Argos upload directory. A dedicated GitHub Actions workflow installs frontend dependencies, installs Chromium, runs the capture script, and uploads screenshots with `@argos-ci/cli`.

**Tech Stack:** GitHub Actions, npm, Storybook 10, Playwright, Vitest, Argos CLI.

---

## Task 1: Add Regression Tests For Workflow Wiring

**Files:**
- Create: `frontend/scripts/argos-workflow-config.test.mjs`
- Create: `frontend/scripts/snapshot-output-config.test.mjs`

- [ ] Add a test that reads `frontend/package.json` and `.github/workflows/argos-visual-regression.yml`, then asserts the Argos CLI dependency, package scripts, pull request trigger, frontend path filters, `npm run argos:ci`, and `GITHUB_TOKEN` environment are present.
- [ ] Add a test for a small snapshot output resolver that defaults to `frontend/argos-screenshots` and supports `STORYBOOK_SNAPSHOTS_DIR`.
- [ ] Run `cd frontend && npm run test -- scripts/argos-workflow-config.test.mjs scripts/snapshot-output-config.test.mjs --run` and confirm it fails before implementation.

## Task 2: Wire Argos Screenshot Capture

**Files:**
- Create: `frontend/scripts/snapshot-output-config.mjs`
- Create: `frontend/scripts/upload-argos-snapshots.mjs`
- Modify: `frontend/scripts/generate-storybook-snapshots.mjs`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `.gitignore`

- [ ] Add `@argos-ci/cli` as a frontend dev dependency.
- [ ] Move the capture output default from `frontend/storybook-snapshots/` to `frontend/argos-screenshots/`.
- [ ] Keep `STORYBOOK_SNAPSHOTS_DIR` as an override for targeted local proof.
- [ ] Add `argos:screenshots`, `argos:upload`, and `argos:ci` package scripts.
- [ ] Ensure the upload script reads the same `STORYBOOK_SNAPSHOTS_DIR`-aware output path as the capture script.
- [ ] Ignore both `frontend/argos-screenshots/` and `frontend/storybook-snapshots/`.

## Task 3: Add CI Workflow

**Files:**
- Create: `.github/workflows/argos-visual-regression.yml`

- [ ] Add a pull request and main push workflow filtered to frontend Storybook/source/package/script files and the workflow itself.
- [ ] Install dependencies with `npm ci`, install Chromium with Playwright, run `npm run argos:ci`, harden checkout with `persist-credentials: false`, and pass `GITHUB_TOKEN` for PR metadata plus optional `ARGOS_TOKEN` from repository secrets when token authentication is required.

## Task 4: Remove Maintained Snapshot Artifacts And Update Docs

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/testing.md`
- Delete tracked files under: `frontend/storybook-snapshots/`

- [ ] Update agent guidance so UI changes still require Storybook stories but no longer require committed screenshot PNGs.
- [ ] Document the Argos visual regression workflow, ignored screenshot output, and repository-level Argos setup expectation.
- [ ] Remove tracked PNG snapshots from git.

## Task 5: Validate And Publish

**Commands:**
- `cd frontend && npm run test -- scripts/argos-workflow-config.test.mjs scripts/snapshot-output-config.test.mjs --run`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- `git diff --check`

- [ ] Confirm the focused tests pass.
- [ ] Confirm all required frontend validation commands pass.
- [ ] Commit, push, create a PR using `.github/PULL_REQUEST_TEMPLATE.md`, attach it to Linear, add the `symphony` label, sweep feedback/checks, and move Linear to Human Review only when green.
