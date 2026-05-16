# Storybook Snapshots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Storybook and committed UI screenshots, starting with `RepositoryCard`.

**Architecture:** Use Storybook's React Vite builder so stories run through the same Vite/React stack as the frontend. Generate snapshots from a static Storybook build by reading `storybook-static/index.json`, serving the build locally, opening each story iframe with Playwright, and writing deterministic PNGs under `frontend/storybook-snapshots/`.

**Tech Stack:** React 18, Vite 7, Storybook 10, MUI, React Query, Playwright, npm scripts.

---

### Task 1: Add Storybook Tooling

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/.storybook/main.ts`
- Create: `frontend/.storybook/preview.tsx`
- Modify: `frontend/eslint.config.mjs`
- Modify: `.gitignore`

- [x] Add dev dependencies:
  - `storybook`
  - `@storybook/react-vite`
  - `@storybook/addon-docs`
  - `playwright`
- [x] Add scripts:
  - `storybook`: `storybook dev -p 6006`
  - `build-storybook`: `storybook build -o storybook-static`
  - `snapshots`: `npm run build-storybook && node scripts/generate-storybook-snapshots.mjs`
- [x] Configure Storybook to load `../src/**/*.stories.@(ts|tsx)` and use `@storybook/react-vite`.
- [x] Configure the preview with Borg UI's i18n, global CSS, MUI theme, `CssBaseline`, and `QueryClientProvider`.
- [x] Disable the React Refresh lint rule for `.storybook/**` and `*.stories.tsx` files because Storybook metadata exports are expected.
- [x] Ignore `frontend/storybook-static` while leaving `frontend/storybook-snapshots` tracked.

### Task 2: Add Repository Card Story

**Files:**
- Create: `frontend/src/components/RepositoryCard.stories.tsx`

- [x] Create stable sample `Repository` data with a Borg 2 full repository, schedule badge, archive count, total size, source paths, and recent dates.
- [x] Patch `repositoriesAPI.getRunningJobs` in the story module to return no active jobs so the card does not rely on a backend.
- [x] Provide no-op action handlers and an allow-all `canDo` function.
- [x] Render the component inside a fixed-width story frame so screenshots are stable and readable.

### Task 3: Add Snapshot Generator

**Files:**
- Create: `frontend/scripts/generate-storybook-snapshots.mjs`

- [x] Build a small static-file server with Node's `http`, `fs`, and `path` modules.
- [x] Read `storybook-static/index.json` and select entries with `type === "story"`.
- [x] Launch Chromium with Playwright, visit `/iframe.html?id=<story-id>&viewMode=story`, wait for `#storybook-root`, disable transitions and animations, and capture `#storybook-root`.
- [x] Write screenshots to `frontend/storybook-snapshots/<story-id>.png`.
- [x] Remove stale PNG snapshots for stories that no longer exist.
- [x] Fail clearly if Storybook has not been built or if Playwright's browser is unavailable.

### Task 4: Update Agent Guidance

**Files:**
- Modify: `AGENTS.md`

- [x] Add guidance that new UI work must include or update a Storybook story and committed screenshot snapshot for the changed feature or component.
- [x] Add guidance that UI components should remain small and composed from smaller components, with snapshots added or updated for each UI component.
- [x] Keep the existing no-heavy-left-accent UI preference intact.

### Task 5: Validate and Publish

**Commands:**
- `cd frontend && npm run snapshots`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- `git diff --check`

- [x] Confirm the red signal: `npm run storybook` and `npm run snapshots` fail before the tooling exists.
- [x] Confirm `npm run snapshots` builds Storybook and writes `frontend/storybook-snapshots/components-repositorycard--default.png`.
- [x] Confirm required frontend checks pass.
- [ ] Commit the plan, tooling, story, generated snapshot, and AGENTS update.
- [ ] Push the BOR-18 branch, open a PR, attach it to Linear, label it `symphony`, sweep feedback, and move BOR-18 to Human Review only after checks are green.

### Self-Review

- The plan covers every BOR-18 acceptance criterion.
- The snapshot path is deterministic and produces committed artifacts without committing the static Storybook build.
- The sample scope is intentionally limited to `RepositoryCard` for this PR.
- `ui-ux-pro-max` remains unavailable in this session; this plan follows the available repository and Superpowers guidance instead.
