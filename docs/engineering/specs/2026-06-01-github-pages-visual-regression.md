# GitHub Pages Visual Regression

## Goal

Replace paid Argos uploads with a GitHub-only visual regression workflow that:

- builds Storybook screenshots with the existing Playwright capture script,
- stores the approved `main` screenshots as a baseline in a repository branch,
- publishes PR comparison reports to the existing GitHub Pages site, and
- updates the PR description with a stable report link and changed/added/removed
  summary.

## Requirements

- PR visual checks are opt-in by label (`run-visuals`) or manual dispatch.
- `main` pushes update the visual baseline automatically.
- No user should need to download a workflow artifact to review visual changes.
- The report must show before, after, and diff images for changed screenshots,
  plus added and removed screenshots.
- The existing docs site must remain intact when visual reports are deployed.
- The workflow should use GitHub Actions, GitHub Pages, and repository storage
  only. No Argos, Chromatic, Percy, or other paid visual SaaS.
- PR body updates must be limited to a marked section so the existing PR
  template and human-written content are preserved.

## Architecture

- `frontend/scripts/visual-regression-report.mjs` compares baseline and actual
  PNG directories, emits `summary.json`, copies review images, creates diff
  PNGs, and writes a static `index.html` report.
- `frontend/scripts/visual-pr-description.mjs` builds and replaces a marked PR
  body section using the report summary and deployed Pages URL.
- `.github/workflows/visual-regression.yml` runs on `main`, labeled PRs, and
  manual dispatch. It generates screenshots, maintains a
  `visual-regression-state` branch containing `/visual/baseline` and
  `/visual/reports`, builds the docs site from `main`, overlays `/visual`, and
  deploys the full Pages artifact.
- `.github/workflows/pages.yml` overlays `/visual` from the state branch before
  docs deploys, so regular docs deployments do not wipe visual reports.

## Non-Goals

- Per-story change detection before screenshot capture.
- A required visual check for every PR.
- Long-term report retention beyond the repository state branch contents.
- Replacing Storybook or the existing Playwright screenshot capture script.

## Validation

- Focused Vitest tests for PNG comparison, report generation, PR body section
  replacement, workflow wiring, and Pages overlay wiring.
- `git diff --check`.
- Frontend script tests.
- Frontend typecheck, lint, and build before pushing.
