# Private Borg Argument Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Prepare a tested private PR containing the supplied argument-boundary fix adapted to current main.

**Architecture:** Retain Benjamin's shared server/agent operand validators and option separators. Adapt only changed call sites and add validation at the server-to-agent dispatch boundary.

**Tech Stack:** Python, FastAPI, pytest, Borg command builders.

**Spec:** `docs/engineering/specs/2026-10-25-private-borg-argument-boundaries.md`

## Global Constraints

- All commits and PRs stay in the temporary private advisory fork.
- Do not bump the app or managed agent version in a pull request.
- No frontend changes, new path policies, releases, or advisory publication.
  Implementation workers do not merge; the controller owns the authorized landing.
- Preserve supported Borg flags, normal archive selectors, and single/batch agent deletion behavior.
- Credit Benjamin Stein for the supplied patch.

### Task 1: Adapt and verify the supplied argument-boundary patch

**Files:** All non-version implementation and test paths in `0001-fix-separate-Borg-options-from-archive-and-path-oper.patch`; additionally `app/services/repository_executor.py` and `tests/unit/test_agent_argument_dispatch.py`.

**Interfaces:** Existing `validate_operand(value, field, archive_path=False)`, `validate_source(value)`, `RepositoryOperationPayload.delete_archive_command(archive)`, and `build_agent_backup_payload(repository, archive_name, ...)` retain their interfaces.

- [x] Apply only the supplied test hunks first. Add dispatch-boundary tests that use a real Repository and assert that `build_agent_backup_payload` rejects `source_directories=["--review-sentinel"]` and `archive_name="--review-sentinel"`, while a normal name and sources are preserved.

```python
with pytest.raises(ValueError):
    build_agent_backup_payload(repository, "daily", source_directories=["--review-sentinel"])
```

- [x] Run the new dispatch tests and a supplied normal builder-boundary test before applying implementation. Record expected assertion failures caused by missing validation/separators; fix test setup errors first.
- [x] Apply the supplied implementation, excluding `agent/README.md`, `agent/borg_ui_agent/__init__.py`, and `pyproject.toml` version hunks. Resolve the moved archive-delete separator in the current shared helper and retain the current selector validation location. Never replace newer agent operations with the older patch version.
- [x] Validate the agent-bound archive and every selected source in the payload builder before payload construction:

```python
validate_operand(archive_name, "archive name")
for source in source_paths:
    validate_source(source)
```

- [x] Add a behavior note in `agent/README.md` without naming a not-yet-assigned fixed version: Borg operands are separated from options and option-shaped names/paths are refused. Record queued old-job/agent-upgrade and Borg 2 runtime requirements in the implementation report and PR draft.
- [x] Run focused server/agent argument tests, changed command-builder tests, `ruff check app tests agent`, `ruff format --check app tests agent`, and `pytest tests/unit`. Use `.venv/bin/python -m pytest` and the matching ruff binary. Save outputs in the plan workspace. Report environment failures precisely and compare suspected baseline failures in an untouched copy rather than weakening tests.
- [x] Inspect the complete diff, confirm no version changes or unrelated files, and commit with Benjamin Stein attribution and `Co-authored-by: Codex <codex@openai.com>`. Do not push; the controller handles private remote/PR creation.

## Implementation notes (2026-10-25)

Adapted Benjamin Stein's patch to the current shared single/batch archive-delete
helper and kept current selector validation locations. Added batch selector
validation and server-to-agent backup validation for persisted sources, explicit
source overrides, and archive names. Updated the newer restore-preview and batch
delete tests to require the same validation and separators.

Recorded RED: 12 dispatch/router failures and 4 batch-delete failures before the
relevant implementation. Final focused suite: 705 passed, 6 existing skips.
`ruff check app tests agent`, `ruff format --check app tests agent`, and
`git diff --check` pass.

At the original private-draft checkpoint, the full `pytest tests/unit` invocation
was incomplete. An unrelated process registry test failed identically on an
untouched copy of the base because this sandbox blocked `ps`. Historical logs,
the baseline comparison, and the original implementation report are in the
ignored `.superpowers/sdd/2026-10-25-private-borg-argument-boundaries/` workspace.
The landing controller now owns the exact combined Linux gate before merge.

Release review must coordinate agent upgrades and handling of already queued
jobs. No existing agent version is proof of this fix. Borg 2 normal-operation
runtime verification remains required; there is no Borg 2 executable here.

## Refreshed landing reconciliation (2026-10-25)

**Base:** `1fb2efba0f601d241677345a852f77b36e7c85d4`, incorporating current main
`59fe26261c2ad714b8a7e3f96051fa4e7fa3225e`.

- [x] Compare the refreshed author tree against our prior draft. Preserve
  dispatch validation, mounted SSH `/-data` compatibility, current selector
  checks, and the accurate restore-preview comment.
- [x] Import mount/router and Borg 1 service-delete boundary regressions first;
  add direct agent-delete helper rejection coverage for both majors.
- [x] Observe RED: 9 expected failures and 6 passes before implementation.
  Restore dry-run boundary coverage already passes and adds both-major coverage.
- [x] Put mount flags before `--`, validate mount archive selectors, close Borg 1
  service-delete options, and validate the direct agent-delete helper input.
- [x] Run scoped argument, router, delete, mount, dispatch, and backup coverage;
  ruff lint/format and diff checks. The controller runs the full Linux suite.
- [x] Complete self-review, retain versions, include landing spec/plan, and commit
  with Benjamin Stein and Codex attribution. No push by the implementation worker.

Evidence and the final reconciliation report are in the ignored landing
workspace `.superpowers/sdd/2026-10-25-security-fixes-landing/task-1-*`.


Refreshed scoped verification: 534 passed, 8 existing skips, 50 warnings across
13 modules; targeted GREEN was 15 passed after the 9-failure RED. Changed Python
files pass ruff lint/format; `git diff --check` passes. The scoped warnings include
existing deprecations and agent-preview resource warnings; this is not a claim
that the suite is warning-free. No app or agent version files changed.
