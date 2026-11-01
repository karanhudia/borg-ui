---
title: Testing
nav_order: 11
description: "Local and CI checks for Borg UI"
permalink: /testing
---

# Testing

Run checks that match the area you changed.

## Docs

```bash
cd docs
npm ci
npm run build
```

## Frontend

```bash
cd frontend
npm install
npm run typecheck
npm run lint
npm run format:check
npm test
npm run build
```

### Storybook Visual Regression

Storybook visual snapshots are handled by a two-stage GitHub Actions workflow.
The unprivileged `Capture Storybook Visual Snapshots` workflow runs automatically
for frontend changes in both same-repository and fork pull requests. Its
screenshots are passed as an artifact to `GitHub Pages Visual Regression`, which
runs only trusted `main` code to publish the report, update the state branch,
and update the PR description. The publisher also runs on `main` pushes that
touch frontend source, stories, Storybook config, frontend scripts, or frontend
package metadata.

The workflow builds Storybook, captures screenshots with Playwright, compares
them against the baseline stored on the `visual-regression-state` branch, and
publishes a static report under `/visual/reports/pr-<number>/` on GitHub Pages.
For PR reports, tiny pixel drift below 0.1% is treated as unchanged unless the
workflow can map that screenshot to a Storybook file touched by the PR; touched
stories still appear even when their visual diff is small.
The PR description is updated with the report link plus changed, added, and
removed screenshot lists. Merging to `main` refreshes the baseline under
`/visual/baseline/` for future PRs. When a pull request is closed or merged, its
`/visual/reports/pr-<number>/` report directory is removed from GitHub Pages.

For local proof runs:

```bash
cd frontend
npm run snapshots
```

Capture uses two isolated browser workers by default and still covers every
story at desktop and mobile sizes. Set `STORYBOOK_SNAPSHOT_WORKERS=1` for a
serial diagnostic run, or an integer up to 16 to tune available CPU/memory.
Keep readiness checks enabled when changing capture scheduling.

Do not commit generated PNGs from `frontend/visual-screenshots/` or
`frontend/storybook-snapshots/`.

## Backend

```bash
ruff check app tests
ruff format --check app tests
pytest
```

### PR CI selection and timing

`Tests` always starts and always reports `CI / Summary`. Only a PR whose complete
git diff contains exclusively `frontend/src/`, `frontend/.storybook/`,
`frontend/scripts/`, or `frontend/public/` changes may skip backend-only lanes.
Renames, dependency manifests, frontend/root configuration, CI, docs, backend,
and unrecognized paths select the full suite. Missing diff metadata also selects
the full suite. Push, nightly, and manual runs always run the full suite.

Frontend quality, unit coverage, builds, and the Python contract guards remain
required on every PR. The contract guards cover frontend/backend Borg routing
and security allowlist applicability; include new Python checks that read
frontend sources in `Frontend / Python Contract Guards`. All three smoke suites
keep both Borg variants on every PR. An unexpected skip, cancellation, failure,
or missing job fails the summary. Security checks retain their existing scope.

Backend unit tests use four deterministic file shards balanced by historical
runtime. All shards download the same per-run timing baseline. Missing, invalid,
or stale history falls back to collected test counts, with no tests excluded.
JUnit reports include setup, call, and teardown; `--durations=50` identifies slow
fixtures and tests. Only a fully successful `main` push saves shared history, so
the first run after introducing this feature uses count balancing. Subsequent
PRs can use the resulting measurements.

Unit, integration, and migration JUnit reports are available as workflow
artifacts. To profile locally:

```bash
pytest tests/unit --durations=50 --junitxml=test-results/unit.xml -o junit_family=xunit1
python scripts/ci/pytest_durations.py test-results/unit.xml --output test-results/durations.json
```

The shared fixed test-user credentials reuse two real bcrypt hashes per session;
users and databases are still recreated per test. Password-security tests call
the production hashing code directly and retain the actual work factor.

New pushes cancel obsolete PR test, security, and screenshot-capture runs. The
trusted visual publisher keeps its separate serialization and permissions.

## Smoke Tests

Smoke tests need a running Borg UI instance.

```bash
docker compose up -d --build
python3 tests/smoke/run_core_smoke.py --url http://localhost:8081
```

Run broader suites when touching backup, restore, repository, archive, SSH, or scheduling behavior.

Some smoke tests require host capabilities or external setup:

- FUSE archive mounting tests require FUSE support.
- Remote SSH tests require SSH test configuration.
- OIDC tests require an OIDC test setup.

## What To Run

| Change              | Minimum check                        |
| ------------------- | ------------------------------------ |
| Docs only           | `cd docs && npm run build`           |
| Frontend UI         | frontend typecheck, lint, tests      |
| Backend API         | backend lint and relevant pytest     |
| Backup/restore core | relevant unit tests plus smoke tests |
| Docker/runtime      | build image and run smoke tests      |
