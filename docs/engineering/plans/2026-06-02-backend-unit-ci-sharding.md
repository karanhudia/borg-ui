# Backend Unit CI Sharding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split backend unit tests across parallel CI shards while preserving combined coverage reporting.

**Architecture:** Add a small tested Python shard selector that balances pytest-collected test files by test count. Update the GitHub Actions backend unit coverage lane into a four-way matrix and add a combine job that rebuilds the single coverage artifact consumed by Codecov and PR coverage comments.

**Tech Stack:** GitHub Actions, pytest, pytest-cov, coverage.py, Python 3.11, Ruff.

---

## Source Map

- Workflow to modify: `.github/workflows/tests.yml`
- New helper: `scripts/ci/select_pytest_shard.py`
- New helper tests: `tests/unit/test_ci_pytest_shard.py`
- Required backend validation: `ruff check app tests`, `ruff format --check app tests`, targeted pytest.

## Tasks

### Task 1: Add Failing Shard Selector Tests

- [x] Create `tests/unit/test_ci_pytest_shard.py`.
- [x] Assert pytest node output is grouped by file and ignores warning/summary lines.
- [x] Assert shard selection balances files by collected test count and preserves file order within each selected shard.
- [x] Assert invalid shard arguments and empty input fail with `ValueError`.
- [x] Run `.venv/bin/python -m pytest tests/unit/test_ci_pytest_shard.py -q` and confirm it fails because `scripts/ci/select_pytest_shard.py` is missing.

### Task 2: Implement The Selector

- [x] Create `scripts/ci/select_pytest_shard.py`.
- [x] Implement `count_tests_by_file(lines)` by filtering pytest node ID lines and counting the path segment before `::`.
- [x] Implement `select_shard(test_counts, shard_index, shard_total)` using one-based shard indexes and greedy count balancing.
- [x] Implement CLI argument parsing, stdin reading, stdout file-list output, and stderr summary logging.
- [x] Re-run `.venv/bin/python -m pytest tests/unit/test_ci_pytest_shard.py -q` and confirm it passes.

### Task 3: Update CI Workflow

- [x] Convert `backend-unit-coverage` to a four-way matrix with `shard` values `1, 2, 3, 4`.
- [x] Add a collection step that writes pytest node IDs, runs the selector, and records a non-empty shard file list.
- [x] Run pytest for only the selected files while writing `COVERAGE_FILE=coverage-data/unit-${{ matrix.shard }}.coverage`.
- [x] Upload each shard coverage data file as `backend-unit-coverage-${{ matrix.shard }}`.
- [x] Add `backend-unit-coverage-combine` to download shard artifacts, run `coverage combine`, regenerate `coverage.xml` and `htmlcov/`, upload the existing backend coverage artifacts, and post the existing PR coverage comment.
- [x] Update `coverage-backend`, `coverage-frontend`, and `test-results` dependencies/status checks to use the combined backend coverage job.

### Task 4: Validate And Publish

- [x] Run `.venv/bin/python -m pytest tests/unit/test_ci_pytest_shard.py -q`.
- [x] Run `.venv/bin/ruff check app tests`.
- [x] Run `.venv/bin/ruff format --check app tests`.
- [x] Run workflow inspection commands against `.github/workflows/tests.yml`.
- [ ] Commit, push, create the PR, attach it to Linear, ensure the PR has label `symphony`, sweep PR feedback, and wait for green checks.
