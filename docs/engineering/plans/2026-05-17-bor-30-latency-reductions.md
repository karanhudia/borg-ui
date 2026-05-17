# BOR-30 Latency Reductions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Subagent execution is not used because BOR-30 is an unattended single-workspace orchestration session.

**Goal:** Implement selector-driven validation, lazy Symphony bootstrap, conservative Odroid defaults, compact workpad digest guidance, and path-aware CI lanes for Borg UI's Symphony workflow.

**Architecture:** Add a pure Python validation selector that turns changed files into a reviewable JSON manifest with minimum local commands, CI lane intent, and explicit broadening reasons. Wire that manifest into Symphony workflow guidance, push/land skills, and CI lane applicability while keeping conservative full backend/frontend fallbacks for risky or unmapped changes.

**Tech Stack:** Python 3 standard library, pytest, GitHub Actions, npm/Vitest, Markdown workflow docs.

---

## File Structure

- Create `scripts/select_validation.py`: selector CLI and importable selection helpers.
- Create `tests/unit/test_select_validation.py`: unit tests covering selector mappings, broadening reasons, manifest shape, and GitHub Actions output.
- Modify `WORKFLOW.md`: lazy bootstrap, lower Odroid concurrency, current digest/manifest requirements, and validation selector usage before push/Human Review.
- Modify `.codex/skills/push/SKILL.md`: selector-first push validation with conservative fallback handling.
- Modify `.codex/skills/land/SKILL.md`: selector manifest trust/fallback rules during landing.
- Modify `docs/symphony.md`: operator guidance for lazy frontend dependencies, selector use, Odroid profile, and digest review evidence.
- Modify `.github/workflows/tests.yml`: changed-file classification job and path-aware no-op behavior for backend, frontend, build, coverage, and smoke lanes.
- Modify `tests/README.md`: document path-aware CI lane behavior.

## Task 1: Reproduction Evidence

- [x] **Step 1: Capture workflow/bootstrap signal**

  Run:

  ```bash
  nl -ba WORKFLOW.md | sed -n '19,36p'
  ```

  Expected: `hooks.after_create` includes `cd frontend && npm ci`, and `agent.max_concurrent_agents` is above the desired Odroid default.

- [x] **Step 2: Capture selector absence**

  Run:

  ```bash
  test -e scripts/select_validation.py; printf '%s\n' $?
  ```

  Expected: prints `1`.

- [x] **Step 3: Capture broad push/land and CI signals**

  Run:

  ```bash
  nl -ba .codex/skills/push/SKILL.md | sed -n '58,78p'
  nl -ba .codex/skills/land/SKILL.md | sed -n '105,115p'
  nl -ba .github/workflows/tests.yml | sed -n '22,190p'
  ```

  Expected: push/land use hard-coded backend/frontend gates and CI lanes run broad test commands without selector-driven applicability.

## Task 2: Validation Selector TDD

- [x] **Step 1: Write failing selector tests**

  Create `tests/unit/test_select_validation.py` with tests for:

  ```python
  def test_docs_only_selects_diff_check_and_docs_build_for_docs_site():
      manifest = select_validation(["docs/testing.md"])
      assert "docs" in manifest["domains"]
      assert command_ids(manifest) == ["diff-check", "docs-build"]

  def test_backend_leaf_selects_lint_format_and_relevant_pytest():
      manifest = select_validation(["app/api/repositories.py"])
      assert "backend" in manifest["domains"]
      assert command_ids(manifest) == [
          "diff-check",
          "backend-ruff-check",
          "backend-ruff-format",
          "backend-api-tests",
      ]

  def test_frontend_config_broadens_to_full_frontend():
      manifest = select_validation(["frontend/package.json"])
      assert "frontend" in manifest["domains"]
      assert "frontend-dependency-change" in reason_ids(manifest)
      assert manifest["ci_lanes"]["frontend_build"] is True

  def test_unknown_file_requires_full_backend_and_frontend_fallback():
      manifest = select_validation(["unexpected.bin"])
      assert "unmapped-change" in reason_ids(manifest)
      assert manifest["ci_lanes"]["backend_unit"] is True
      assert manifest["ci_lanes"]["frontend_build"] is True
  ```

- [x] **Step 2: Verify red**

  Run:

  ```bash
  python3 -m pytest --noconftest tests/unit/test_select_validation.py -q
  ```

  Expected: fails because `scripts/select_validation.py` does not exist.

- [x] **Step 3: Implement selector**

  Add `scripts/select_validation.py` with:

  - `select_validation(changed_files, all_changes=False)` returning a deterministic dict.
  - CLI options `--base`, `--head`, `--changed-files`, `--all`, and `--format json|text|github-output`.
  - Domains: `backend`, `frontend`, `docs`, `workflow`, `ci`, `smoke`, `dependencies`, `security`, `runtime`, `storybook`.
  - Local command objects with `id`, `command`, and `reason`.
  - CI booleans for `backend_lint`, `backend_unit`, `backend_integration`, `frontend_quality`, `frontend_unit`, `frontend_build`, `smoke_core`, `smoke_extended`, and `smoke_ssh`.
  - Broadening reasons for dependency, CI/workflow, smoke/runtime, security, and unmapped changes.

- [x] **Step 4: Verify green**

  Run:

  ```bash
  python3 -m pytest --noconftest tests/unit/test_select_validation.py -q
  ```

  Expected: all selector tests pass.

## Task 3: Workflow and Skill Wiring

- [x] **Step 1: Update `WORKFLOW.md`**

  Change bootstrap and prompt guidance:

  ```yaml
  hooks:
    after_create: |
      git clone --filter=blob:none git@github.com:karanhudia/borg-ui.git .
      echo "Frontend dependencies are installed lazily when selected validation or implementation requires them."
  agent:
    max_concurrent_agents: 3
  ```

  Add requirements that every push/Human Review handoff records a selector manifest, broadening reasons, and a compact `### Current Digest`.

- [x] **Step 2: Update `push` skill**

  Replace hard-coded changed-file gates with:

  ```bash
  python3 scripts/select_validation.py --base origin/main --format json | tee /tmp/borg-ui-validation-manifest.json
  python3 scripts/select_validation.py --base origin/main --format text
  ```

  Keep the existing full backend/frontend commands as the documented fallback when the manifest includes broadening reasons that require them or the selector cannot run.

- [x] **Step 3: Update `land` skill**

  Require landing to trust a Human Review handoff only when PR head SHA and manifest hash match; otherwise rerun selector-selected commands and broaden on any manifest fallback reason.

- [x] **Step 4: Update `docs/symphony.md`**

  Document lazy frontend dependency installation, selector-first validation, Odroid default concurrency, and digest evidence.

## Task 4: Path-Aware CI

- [x] **Step 1: Add changed-file job**

  Add a first `changed-files` job in `.github/workflows/tests.yml` that checks out with `fetch-depth: 0`, runs `scripts/select_validation.py --format github-output`, and exposes applicability outputs for downstream jobs.

- [x] **Step 2: Make lanes green when not applicable**

  For backend, frontend, build, coverage, and smoke jobs:

  ```yaml
  - name: Report not applicable
    if: needs.changed-files.outputs.run_backend_unit != 'true'
    run: echo "Backend unit lane not applicable for this change set."
  ```

  Keep jobs present and successful instead of skipping required check names.

- [x] **Step 3: Preserve artifacts only when applicable**

  Gate artifact download/upload steps on the corresponding lane output so no-op lanes do not fail due to missing coverage or build artifacts.

- [x] **Step 4: Update CI docs**

  Update `tests/README.md` to explain that required lanes stay green with an explicit not-applicable message for unrelated PR changes, while scheduled runs still exercise broad coverage.

## Task 5: Validation and Handoff

- [x] **Step 1: Selector evidence**

  Run representative manifests:

  ```bash
  python3 scripts/select_validation.py --changed-files <(printf 'docs/testing.md\n') --format json
  python3 scripts/select_validation.py --changed-files <(printf 'app/api/repositories.py\n') --format json
  python3 scripts/select_validation.py --changed-files <(printf 'frontend/package.json\n') --format json
  python3 scripts/select_validation.py --changed-files <(printf 'unexpected.bin\n') --format json
  ```

- [x] **Step 2: Repository validation**

  Run:

  ```bash
  git diff --check
  python3 -m pytest --noconftest tests/unit/test_select_validation.py -q
  ruff check app tests
  ruff format --check app tests
  ```

  Workflow and CI changes may broaden into frontend validation. BOR-30's final
  selector manifest selected frontend fallback, so frontend locale/type/lint/build
  validation was required and executed after lazy `npm ci`.

- [ ] **Step 3: Publish**

  Commit with the `commit` skill, push with the `push` skill, attach the PR to BOR-30, add label `symphony`, sweep PR comments/reviews/checks, update the workpad digest/validation evidence, and move the issue to Human Review only when green.

## Self-Review

- Spec coverage: covers selector/manifest, push/land/Symphony docs, lazy bootstrap, Odroid concurrency, compact digest, and path-aware CI lanes.
- Scope control: does not change app runtime behavior or frontend UI. No Storybook story or snapshot is required.
- Conservative fallback: unknown, dependency, CI/workflow, smoke/runtime, and security changes broaden instead of silently narrowing validation.
- Validation design: selector behavior is testable locally before CI path awareness relies on it.
