# Symphony Issue-to-PR Latency Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the BOR-29 recommendations so Symphony creates Borg UI PRs faster while keeping validation decisions explicit and reviewable.

**Architecture:** Add a repository-owned validation selector and manifest, update Symphony workflow/skills to use it, reduce bootstrap and prompt overhead, and split broad CI lanes after the local selector is in place. The selector is advisory but conservative: agents may broaden selected commands, while unmapped or high-risk changes automatically fall back to full validation.

**Tech Stack:** Python 3 standard library, pytest, GitHub Actions, npm/Vitest, Markdown workflow docs.

---

## Task 1: Add Validation Selector

**Files:**

- Create: `scripts/select_validation.py`
- Create: `tests/unit/test_select_validation.py`
- Modify: `docs/symphony.md`

Steps:

- [ ] Define changed-file domains: `docs`, `backend`, `frontend`, `storybook`, `ci`, `workflow`, `runtime`, `dependencies`, and `security`.
- [ ] Implement a CLI that reads `git diff --name-only origin/main...HEAD` by default and emits JSON with `domains`, `local_commands`, `broadening_reasons`, and `notes`.
- [ ] Add explicit mappings:
  - docs-only -> `git diff --check`, plus `cd docs && npm run build` when `docs/**/*.md` or VitePress config changes;
  - backend leaf -> `ruff check app tests`, `ruff format --check app tests`, and mapped pytest paths;
  - backend shared/config/dependency -> full backend unit fallback;
  - frontend leaf -> focused Vitest path, `npm run typecheck`, `npm run lint`, and locale check only for locale changes;
  - frontend build/config/dependency -> full frontend fallback;
  - UI story/snapshot -> relevant story plus snapshot command;
  - workflow/CI/security -> full affected safety gate.
- [ ] Add unit tests for each mapping and for conservative fallback when a file is unknown.
- [ ] Document that selector output is a minimum gate and agents may broaden it.

Validation:

```bash
python3 -m pytest tests/unit/test_select_validation.py -q
python3 scripts/select_validation.py --base origin/main --format json
```

## Task 2: Wire Selector Into Push and Land Skills

**Files:**

- Modify: `.codex/skills/push/SKILL.md`
- Modify: `.codex/skills/land/SKILL.md`
- Modify: `WORKFLOW.md`

Steps:

- [ ] Replace hard-coded broad local gate examples in `push` with a selector-first workflow.
- [ ] Keep the existing broad backend/frontend commands as fallback when selector output contains `full_backend` or `full_frontend`.
- [ ] Update `land` fallback to trust the Human Review handoff only when the selector manifest and PR head are unchanged; otherwise rerun selector-selected commands.
- [ ] Update `WORKFLOW.md` to require the validation manifest in the workpad before every push and Human Review transition.

Validation:

```bash
git diff --check
python3 scripts/select_validation.py --base origin/main --format json
```

## Task 3: Reduce Bootstrap and Prompt Overhead

**Files:**

- Modify: `WORKFLOW.md`
- Modify: `docs/symphony.md`

Steps:

- [ ] Remove unconditional `cd frontend && npm ci` from the `after_create` hook.
- [ ] Add a lazy dependency rule: frontend dependencies are installed only when the selector chooses a frontend command or the agent enters a frontend implementation path.
- [ ] Add a `### Current Digest` requirement to the workpad instructions with branch/head, active plan item, validation manifest, blockers, and PR/check state.
- [ ] Update retry instructions to use the digest and unchecked items instead of replaying old notes as active context.
- [ ] Add guidance that host-profile concurrency tuning is a later measured optimization, not the first implementation step.

Validation:

```bash
git diff --check WORKFLOW.md docs/symphony.md
```

## Task 4: Split CI Lanes

**Files:**

- Modify: `.github/workflows/tests.yml`
- Modify: `tests/README.md`

Steps:

- [ ] Add a lightweight changed-domain job that writes output used by downstream jobs.
- [ ] Keep required jobs green by making irrelevant lanes exit with a clear "not applicable" message inside the job.
- [ ] Split backend unit coverage into a matrix by test path group and merge coverage artifacts.
- [ ] Split backend integration into a matrix by Borg domain.
- [ ] Split frontend Vitest coverage with Vitest `--shard=N/M` and merge reports.
- [ ] Keep smoke lanes separate and run only relevant smoke tiers for PRs, while nightly scheduled CI runs all tiers.

Validation:

```bash
git diff --check .github/workflows/tests.yml tests/README.md
```

CI-only validation after pushing:

```text
Backend / Lint & Format
Backend / Unit Tests
Backend / Integration Tests
Frontend / Code Quality
Frontend / Unit Tests
Frontend / Build
Smoke / Core
Smoke / Extended
Smoke / SSH
CI / Summary
```

## Task 5: Add Measurement

**Files:**

- Modify: `WORKFLOW.md`
- Create: `docs/engineering/specs/2026-05-17-symphony-issue-pr-latency-reduction-metrics.md`

Steps:

- [ ] Require workpad notes for command duration, time-to-first-PR, time-in-review, time-in-merge, and validation manifest hash.
- [ ] Document the Linear fields and workpad markers needed for a weekly latency report.
- [ ] Add a rule that broad validation fallback must record the reason so future analysis can distinguish necessary safety work from avoidable default work.

Validation:

```bash
git diff --check WORKFLOW.md docs/engineering/specs/2026-05-17-symphony-issue-pr-latency-reduction-metrics.md
```

## Rollout Order

Implement Tasks 1 and 2 first so validation quality is protected before reducing bootstrap or CI breadth. Task 3 should then reduce dependency and prompt overhead while leaving host-profile concurrency tuning for measured follow-up work. Task 4 should be merged after selector data proves the mappings are stable. Task 5 should land with or immediately after Task 1 so future latency changes are measurable.
