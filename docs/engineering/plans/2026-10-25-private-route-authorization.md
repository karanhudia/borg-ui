# Private Route Authorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Prepare a tested private PR of Benjamin's authorization patch adapted to current main.

**Spec:** `docs/engineering/specs/2026-10-25-private-route-authorization.md`

**Architecture:** Retain supplied endpoint guards and repository visibility helpers. Extend current unresolved dispatch failure query with the same visible-plan scope used by dashboard overview.

## Global Constraints

- All commits and PRs stay in the temporary private advisory fork.
- Do not bump the app or managed agent version in a pull request.
- No frontend changes, unrelated access-policy expansion, merges, releases, or advisory publication.
- Preserve newer API imports and current operations.
- Credit Benjamin Stein for the supplied patch.

### Task 1: Adapt and verify route authorization

**Files:** Non-version implementation and tests from `0001-fix-enforce-missing-authorization-and-declare-route-.patch`; additionally current dispatch-failure helper and focused dashboard tests.

- [ ] Apply supplied tests first and add hidden-plan, mixed-access plan, fully visible plan and administrator dispatch-failure cases. Reuse fixtures and real database models. Verify RED before implementation.
- [ ] Apply supplied implementation. Resolve current import context in `app/api/scripts_library.py` and `app/api/v2/archives.py` without losing newer imports.
- [ ] Add current `GET /api/repositories/{repository_id}/agent-scripts` route inventory entry matching the actual guard.
- [ ] Scope current `unresolved_dispatch_failures` feed to fully visible plans for restricted users. An optional visible-plan-id set on the helper is suitable; `None` means unrestricted and an empty set returns no plan failures. Avoid duplicating permission logic.
- [ ] Run focused authorization and route-registry tests, then ruff check/format and full `pytest tests/unit` using the source repo .venv. Save logs. Compare suspected failures against untouched main rather than weakening tests. Unit evidence may be shared with the other security branch only for unchanged baseline failures.
- [ ] Self-review, verify no version or frontend changes, and commit with original Benjamin authorship plus Codex coauthor. No push; controller handles the verified private remote and PR. Report changed product behaviors and pending review accurately.

### Task 2: Reconcile the refreshed author patch for landing

**Base:** `25e7adf2dc052146cef56c620b6284fea7e18f62`, including current main
`59fe26261c2ad714b8a7e3f96051fa4e7fa3225e`.

- [x] Compare each refreshed author file. Keep equivalent dashboard filtering,
  existing import placement, analytics consent invalidation, and stronger
  discovery candidate/marker symlink authorization.
- [x] Add the author's combined dispatch-failure regression without removing the
  existing three parameterized cases. Verify it against current code, then show
  it fails when the dispatch visibility filter is temporarily bypassed and
  restore the filter. No missing production guard has been identified.
- [x] Update access-control documentation with discovery restrictions, possible
  default-list `403`, administrator monitoring/report actions, dashboard scoping,
  and dependency guards that reinforce existing policies.
- [x] Verify the merged route inventory, authorization/dashboard/discovery and
  related repository/settings/proxy coverage, scoped ruff check/format and
  `git diff --check`. Record exact outcomes and warnings in the private landing
  report. The controller owns the combined Linux full unit gate.
- [x] Review scope, preserve versions/frontend, and commit locally with Benjamin
  Stein and Codex attribution. No network, push, merge, or policy expansion.
