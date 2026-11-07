# Agent Session Revocation Implementation Plan

**Goal:** Prepare Benjamin Stein's tested revocation patch as a private PR.
**Architecture:** Shared guarded status writes and a per-message status read.
**Tech Stack:** FastAPI, SQLAlchemy, pytest, GitHub advisory private fork.
**Spec:** docs/engineering/specs/2026-11-07-agent-session-revocation.md

## Constraints

Keep the patch private, retain Benjamin's authorship, do not bump versions,
and preserve the minimal scope and residual limitations recorded in the spec.

## Task 1: Apply and verify the supplied patch

Files: app/api/agents.py, app/api/managed_machines.py,
app/core/agent_auth.py, tests/unit/test_agent_revocation_live_session.py.

- [x] Create an isolated checkout of current main.
- [x] Apply the test file first, temporarily omitting imports of the two new
  symbols so existing handler behavior can run before the product patch.
- [x] Run the hello-wait, stale REST heartbeat and agent-list regressions:
  three expected assertion failures on current main.
- [x] Restore the exact supplied test file and apply the three product files.
- [x] Run all 12 supplied tests: passed with 34 existing deprecation warnings.
- [x] Run backend lint/format and the full unit suite; investigate failures.
- [ ] Review the diff and compatibility notes, commit with author credit,
  push only to the private advisory fork and create/verify its PR.

## Verification results

Backend lint/format and diff checks pass. The full 8-worker Python 3.11 run
completed in 159.76 seconds: 8161 passed, 25 skipped, 3 failed, 1 setup error,
720 warnings. The four exceptions reproduce identically on unchanged main:
process-child inspection, two macOS interactive installer checks, and binding
a local HTTP test server. All four pass when rerun with process inspection and
local socket access (4 passed, 34 warnings). All 8165 non-skipped tests therefore
have passing evidence across the full run and targeted rerun. This is not a
single unrestricted full-suite result. PostgreSQL cases were skipped because
BORG_TEST_POSTGRES_URL is unset. No live-stack or PostgreSQL validation was run.

The exact supplied patch reverses cleanly from the final product/test diff.
CodeRabbit is signed out; local self-review found no additional blocker within
the supplied scope. The known guard-to-delivery race remains documented.
