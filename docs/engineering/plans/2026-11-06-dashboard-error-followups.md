# Dashboard Error Follow-ups Implementation Plan

> Execute using Superpowers test-driven development, independent task review and verification before completion. The user authorized implementation and PR publication.

**Goal:** Fix the actionable agent/path, cloud-authorization and diagnostic failures identified on 6 November.

**Architecture:** Preserve the existing service boundaries and typed agent errors. Classify known recoverable failures at the owner, retain original SSH errors, and keep secret-safe diagnostics within existing bounds.

**Tech Stack:** Python/FastAPI/SQLAlchemy, pytest, React/i18next/Storybook.

**Spec:** `docs/engineering/specs/2026-11-06-dashboard-error-followups.md`.

## Global constraints

No version/dependency/schema changes. No credential deletion, auto-reconnection, authorization weakening, repository overwrite, production repair or render speculation. Preserve unknown-error, timeout, transport, lock/retry, terminal-result and redaction contracts. All new translations cover en/de/es/it and changed UI states have stories.

### Task 1: Agent errors and Borg diagnostic summaries

Files: `app/services/agent_filesystem_service.py`, `app/services/repository_executor.py`, focused agent/service/route tests.

- [x] Write failing regressions for missing/unreadable/non-directory failed results and typed error payloads; unknown/malformed and offline/timeout controls.
- [x] Implement a small code-to-status/key mapping using existing filesystem translations and original requested path.
- [x] Reproduce repository.init existing-repository error, then classify only the verified init case as 409 with existing Borg translation. Test non-init and ambiguous errors retain 502 and no repository data is overwritten.
- [x] Reproduce `_tail_reason_line` returning `Local Exception` for real-shaped Borg traceback output. Prefer a genuine terminal exception without footers or secrets; preserve meaningful pre-traceback messages, locks and bounded redaction on both modern and legacy paths.
- [x] Run focused agent, repository route, consumed-result and operation executor tests. Write red/green evidence and review report.

### Task 2: SSH retry error preservation

Files: `app/api/filesystem.py`, `tests/unit/test_api_filesystem.py`.

- [x] Reproduce absolute missing path plus failing relative fallback and assert original error/path stays authoritative.
- [x] Gate compatibility retry on missing-path failures, never permission/auth/host-key/connection errors; retain existing successful relative retries.
- [x] Run filesystem/access/path and SSH helper suites, preserving temporary-key cleanup and access boundaries. Write red/green report.

### Task 3: Cloud authorization recovery

Files: `app/services/rclone_service.py`, `app/api/rclone.py`, corresponding tests, `frontend/src/components/FileExplorerDialog.tsx` and its test/story, `RcloneRemoteDialog` polling/API types and corresponding tests/stories, and four locale files.

- [x] Reproduce invalid_grant browse failure via the real command result/service/route boundary. Recognize only explicit invalid_grant and map to translated 409 recovery guidance; generic errors remain generic failures.
- [x] Reproduce exchange rejection with credentials in provider response; expose only allowlisted reason and HTTP status. Test invalid JSON, unknown/error-description/secret fields and transport failures do not escape or gain trusted status.
- [x] Add a backward-compatible optional structured OAuth session error detail so polling translates safe rejection diagnostics in en/de/es/it, while old plain-string errors still render. Clear detail after success. Hide successful-empty copy while listing errors are visible.
- [x] Ensure callback failures mark the existing OAuth session failed/retryable without modifying saved remote credentials or automatically authorizing.
- [x] Preserve recognized authorization recovery errors in the existing FileExplorerDialog renderer instead of its generic rclone fallback; test that unrelated failures retain existing wording.
- [x] Add en/de/es/it strings and a story showing the existing error surface with recovery guidance. Use the UI skill before UI decisions.
- [x] Run rclone API/service tests, locale parity and relevant frontend/story checks. Write red/green report.

### Task 4: Verification and PR

- [x] Update troubleshooting with actionable Import, path and Cloud Storage recovery steps and operational limits.
- [x] Review each task and the complete diff; run affected suites, backend Ruff, frontend locale/type/lint/build checks where relevant, and full backend unit verification.
- [ ] Commit and push the isolated branch and create a PR with the repository template, exact validation evidence and scope limits. Do not merge this new PR.

## Verification evidence

- Baseline affected suites: 58 passed.
- Final agent diagnostics/restore/consumed-result/operation suite: 343 passed; repository route batch: 125 passed with real duplicate-init data preservation.
- Final SSH/path/access/helper suite: 275 passed, including current OpenSSH mkdir wording and original-error preservation.
- Complete backend unit run: 8,133 passed, 25 skipped, zero failures (8,158 cases). Four disjoint CI-helper-selected file shards ran first; the unchanged 18-case streamed-download file ran serially afterward to avoid its known 100 ms assertion flaking under concurrent load. It was not skipped.
- Fresh final OAuth API/service run after safe session-detail follow-ups: 161 passed. Changed browser/dialog tests: 58 passed. These fresh suites cover the last localized-polling/serializer refinements made while the broad run was in progress.
- Backend Ruff lint/format and whitespace checks passed. Frontend locale parity (5,700 keys), typecheck, lint, Storybook and production build passed; known dependency deprecations and build chunk/dynamic-import warnings remain.
- Task reviews and whole-branch review are independent; CodeRabbit CLI is signed out, so remote analysis was unavailable. Local visual proof uses ignored desktop/mobile snapshots, with no PNGs committed.
- No version, dependency or database-schema changes. Release 2.4.7 was already published independently of this follow-up branch.
