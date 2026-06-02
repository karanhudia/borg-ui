# Backend Unit CI Sharding

## Problem

The backend unit coverage lane currently runs every `tests/unit` test in one GitHub Actions job. Local reproduction collected 2,093 unit tests across 117 files before executing any tests, and the serial coverage sample was still early in the suite after roughly 90 seconds on the local ARM runner. In CI, that same lane is reported to take more than 10 minutes.

## Goals

- Reduce backend unit test wall-clock time in CI by running the unit suite in parallel shards.
- Preserve backend unit coverage reporting, the PR coverage comment, and the Codecov upload.
- Keep the split deterministic and easy to adjust as the suite grows.
- Avoid adding a new pytest plugin when a small repo-native helper is enough.

## Non-Goals

- Changing frontend, integration, smoke, or security workflow behavior.
- Skipping slow tests or weakening coverage thresholds/reporting.
- Solving runtime fixture performance inside individual tests.

## Design

### Shard Selection

Add `scripts/ci/select_pytest_shard.py`, a small Python CLI that reads pytest node IDs from standard input, groups them by test file, counts tests per file, and assigns files to a requested shard with greedy count balancing. Grouping by file preserves module/class fixture locality better than splitting individual node IDs, while count balancing avoids the worst imbalance of simple alphabetical path slicing.

The selector accepts one-based `--shard-index` and `--shard-total` arguments. It writes selected file paths to standard output and writes a compact shard summary to standard error, so workflow shell steps can safely redirect stdout into a pytest file list.

### GitHub Actions

Convert `backend-unit-coverage` into a four-way matrix job. Each shard:

- installs the same backend dependencies and Borg package as the existing job;
- collects `tests/unit` node IDs with pytest;
- uses the selector to choose its file list;
- runs pytest with coverage enabled for that shard;
- uploads its `unit-<shard>.coverage` data file as a shard artifact.

Add a follow-up `backend-unit-coverage-combine` job that downloads all shard coverage data, runs `coverage combine`, generates `coverage.xml` and `htmlcov/`, uploads the same downstream artifact names the workflow already expects, and posts the existing PR coverage comment from the combined report.

Update the backend Codecov upload and summary job dependencies to depend on the combined coverage job instead of the old single unit coverage job artifact.

## Acceptance Mapping

- Backend unit tests run as four CI shards, giving parallel wall-clock speedup while preserving test coverage.
- Coverage data from all shards is combined into one backend coverage XML artifact before Codecov upload and PR coverage comment.
- The selector is deterministic, tested, and does not rely on unpinned third-party sharding dependencies.
- Existing integration, frontend, smoke, and coverage upload lanes keep their current behavior except for depending on the combined backend coverage artifact.

## Validation

- `python -m pytest tests/unit/test_ci_pytest_shard.py -q`
- `ruff check app tests`
- `ruff format --check app tests`
- Relevant workflow inspection confirming `backend-unit-coverage` is a matrix and `coverage-backend` downloads the combined artifact.
