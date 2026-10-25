# Security Fixes Landing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development for implementation and task reviews. The controller owns shared validation and advisory merges.

**Goal:** Reconcile, independently validate, and merge three security fixes.
**Architecture:** Separate private advisory PRs on current main; combined frozen candidate for validation; merge in argument, authorization, operator-path order through advisories.
**Tech Stack:** Python/FastAPI/pytest, Borg 1/2, Docker, PostgreSQL/Redis, GitHub security forks.
**Spec:** docs/engineering/specs/2026-10-25-security-fixes-landing.md

## Global Constraints

- Preserve current main 59fe26261c2ad714b8a7e3f96051fa4e7fa3225e and the earlier draft safeguards.
- Keep work private until the maintainer-authorized merge. Do not publish advisories, CVEs, releases, or contact the reporter.
- Do not bump app or managed-agent versions. Credit Benjamin Stein and Codex appropriately.
- No production data changes, unrelated bug fixes, new agent-root model, automatic old-plan migration, or frontend feature changes.
- Existing plans keep stored paths; explain residual risk and administrator review. New operator paths and agent restores follow supplied restrictions.
- Implementation workers never spawn subagents, push, or call external services. Controller owns those actions.

### Task 1: Reconcile refreshed argument-boundary patch

**Workspace:** /private/tmp/borg-security-prs/argument-work
**Base:** 1fb2efba0f601d241677345a852f77b36e7c85d4
**Files:** agent/README.md, agent/borg_ui_agent/repository_ops.py, app/core/borg_router.py, app/services/delete_archive_service.py, app/services/v2/mount_service.py, supplied related tests. Preserve app/services/repository_executor.py, app/services/backup_service.py and their added tests.
**Input:** /private/tmp/borg-security-refresh/argument/GHSA-6r73-fix-on-fccef5d9-2026-10-25.patch; staged comparison tree /private/tmp/borg-security-refresh/argument-tree.
- [ ] Compare author refresh to prior draft, importing additional test hunks for mount and Borg1 service deletion first. Keep dispatch and /-data tests. Existing reference tree has only author patch, so never blindly copy its missing custom protections over ours.
- [ ] Run missing-boundary tests RED before product changes using existing source .venv.
- [ ] Move -o allow_other -f and Borg1 bypass-lock before -- in mount builders, validate mount archive selector, add -- before Borg1 delete-service operand, and validate direct agent delete helper input. Preserve current selector validation and accurate restore-preview comment.
- [ ] Run covering argument, router, delete-service, mount, dispatch and backup tests; ruff check/format and diffcheck. Full Linux suite is a controller gate later.
- [ ] Update existing dated argument spec/plan with refreshed scope and verify no version changes. Commit with attribution, detailed report to this landing workspace task-1-report.md. No push.

### Task 2: Reconcile authorization and document intentional role changes

**Workspace:** /private/tmp/borg-security-prs/authorization-work
**Base:** 25e7adf2dc052146cef56c620b6284fea7e18f62
**Files:** app/core/route_access.py if current main needs declarations; tests/unit/test_api_dashboard.py for additional author regression; docs/access-control.md and existing dated authorization spec/plan.
**Input:** /private/tmp/borg-security-refresh/authorization/GHSA-c7g6-fix-on-fccef5d9-2026-10-25.patch and comparison tree /private/tmp/borg-security-refresh/authorization-tree.
- [ ] Compare refreshed product delta. Preserve equivalent current complete-plan visibility query and stronger descendant/marker symlink checks. Keep accurate current imports; do not replace code merely for import order.
- [ ] Incorporate meaningful missing author regression coverage first and run it; if an actual missing current-main guard/declaration exists, demonstrate RED before fixing it. Do not invent code changes if refreshed behavior already exists.
- [ ] Run authorization/dashboard/discovery/registry coverage, record existing versus added tests, ruff and diffcheck.
- [ ] Update operator/admin documentation for discovery, monitoring, dashboard scoping and current access guards. Explain default discovery may return403; no new UI feature. Commit attribution/report task-2-report.md. No push.

### Task 3: Apply operator-path confinement with migration guidance

**Workspace:** /private/tmp/borg-security-prs/operator-work
**Base:** 59fe26261c2ad714b8a7e3f96051fa4e7fa3225e
**Input:** /private/tmp/borg-security-refresh/operator-paths/GHSA-7r5m-fix-on-fccef5d9-2026-10-25.patch
**Files:** five supplied app files, two supplied tests, docs/access-control.md, docs/security.md, docs/configuration.md and dated operator spec/plan.
- [ ] Read APPLY.md including residual risk and TESTING.md. Extract supplied tests first (git apply --include=tests/**), run representative operator path/restore/mount/SSHFS tests RED. Examples in patch include test_operator_cannot_set_unapproved_source and test_operator_borg_mount_denial_has_no_side_effects.
- [ ] Apply supplied app hunks and retain current-main behavior. Do not add runtime revalidation or old-plan migration. Confirm agent restores/new sources refused for non-admin, existing plan edits/runs preserved, pattern roots and staging metadata checked, SSHFS staging bounded, admin behavior retained except documented escaped SSHFS case.
- [ ] Run both new test modules and neighboring plan/restore/mount/local-path tests, ruff and diffcheck. Investigate concrete defects with narrow TDD fixes.
- [ ] Add access-control exceptions and a clearly linked upgrade section in security docs. Admin audit guidance covers stored source_directories, source_locations, pattern roots in plan/link flags, metadata staging, existing agent paths. Explain selection-time-only checks, later symlink changes, unvalidated pattern-file contents/ZFS/remote metadata limits; no claim complete confinement.
- [ ] Add dated spec/plan describing accepted restrictions and no automatic migration. Commit author Benjamin, Codex coauthor, report task-3-report.md. No push.

### Task 4: Validate exact combined candidate

- [ ] Assemble all three committed branches on recorded current main in an independent private clone and record component SHAs and candidate tree. Resolve only real integration conflicts preserving all guards/docs; review any fixes.
- [ ] In disposable Linux test image with current pinned requirements, install pytest-xdist only in test environment. Run complete pytest tests/unit with4-8 workers, PostgreSQL parametrization when supported, ruff all app/tests/agent, formatcheck and diffcheck. Save full logs and JUnit results. No arbitrary timeout as substitute for successful validation.
- [ ] Exercise real Borg1/2 backup, browse/download/restore/delete/mount argument shapes; run fresh app role/upgrade checks using harmless test data and fresh volumes, plus managed agent and SSH paths where feasible. Use author scripts only after inspection, adapt isolated stack URLs and identities, verify content and admin/operator behavior. Compare suspected baseline failures against untouched current main.
- [ ] Fresh final review of combined code and actual validation evidence. Address critical/important findings with one fix wave and scoped re-review. Keep known documented policy limits explicit.

### Task 5: Land and verify

- [ ] Update private PR bodies with exact-head evidence and compatibility notes; create/attach third private PR. Check all comments and requested changes; make drafts ready only after review/validation.
- [ ] GitHub security forks have no Actions checks and merge through advisory UI, not ordinary gh pr merge. Recheck upstream main and mergeability before each authorized merge; incorporate any new changes and validate affected code. Merge argument, authorization, operator paths in order.
- [ ] Confirm every PR merged remotely and resulting upstream tree contains all guards/docs. Advisories remain unpublished; no release/version edits. Clean up only disposable test resources created here, preserve workspaces for recovery. Report merged links/commits and material operator upgrade guidance.
