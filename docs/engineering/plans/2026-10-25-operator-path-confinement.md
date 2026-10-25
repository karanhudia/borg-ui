# Operator Path Confinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. This task is executed by its assigned implementer; the landing controller owns independent review and integration.

**Goal:** Restrict newly selected operator paths and document upgrade compatibility.

**Architecture:** Reuse path helpers in the five supplied backend files. Validate at selection boundaries, leaving stored-plan execution unchanged.

**Tech Stack:** Python, FastAPI, pytest, ruff.

**Spec:** `docs/engineering/specs/2026-10-25-operator-path-confinement.md`

## Global Constraints

- Preserve main `59fe26261c2ad714b8a7e3f96051fa4e7fa3225e` and existing plan behavior.
- No runtime migration, frontend changes, agent-root policy, or version bump.
- Keep work private; no push, external service calls, or child agents.
- Attribute Benjamin Stein and Codex.

### Task 1: Import regression tests and record RED

**Files:** `tests/unit/test_operator_path_confinement.py`, `tests/unit/test_mount_path_confinement.py`.

- [x] Extract tests only with `git apply --include='tests/**' /private/tmp/borg-security-refresh/operator-paths/GHSA-7r5m-fix-on-fccef5d9-2026-10-25.patch`.
- [x] Run representative source, agent restore, Borg mount, and SSHFS escape tests with the host `.venv/bin/python -m pytest`; save expected failures outside the checkout.

### Task 2: Apply backend confinement and permission detail

**Files:** `app/api/backup_plans.py`, `app/api/mounts.py`, `app/api/restore.py`, `app/services/mount_service.py`, `app/utils/local_paths.py` and the operator test module.

- [x] Apply product hunks using `git apply --include='app/**'` on the same patch.
- [x] Extend the agent restore regression with `assert response.json()['detail'] == {'key': 'backend.errors.auth.notEnoughPermissions'}` for the denied caller and confirm RED.
- [x] Change only the new agent role-denial detail to that existing permission key and confirm GREEN; retain the existing server destination detail.
- [x] Run both new modules plus neighboring backup-plan, restore, mount, and local-path tests, scoped ruff lint/format, and `git diff --check`.

### Task 3: Explain upgrade behavior and commit

**Files:** `docs/access-control.md`, `docs/security.md`, `docs/configuration.md`, and these dated spec/plan files.

- [x] Document new path/restore/mount restrictions and link security upgrade guidance from configuration and access-control docs.
- [x] Explain unchanged old plans, administrator audit steps, selection-time symlink limits, pattern-file/ZFS/database `backup_paths` exclusions, server-side checks of remote metadata strings without remote filesystem or symlink confinement, and SSHFS escape behavior for admins.
- [x] Self-review the exact diff against the spec and checks; create one attributed commit without version changes.
- [x] Report SHA, commands, results, log paths, and limits to the landing controller; leave no running tests or processes.
