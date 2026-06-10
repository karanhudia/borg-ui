# Docker Startup SSH And Port Hardening Implementation Plan

> **For agentic workers:** Execute task-by-task with failing tests before production code changes. Keep the Linear workpad updated after reproduction, implementation, validation, and publish milestones.

**Goal:** Keep Docker startup compatible with custom runtime ports and legacy `/home/borg/.ssh` mounts.

**Architecture:** Preserve the existing canonical `/data/ssh_keys` migration for normal image directories, but detect a mounted `/home/borg/.ssh` before removal and leave it in place. Extend existing static Docker/runtime tests to cover the mount guard and keep the non-default `PORT=8088` release smoke covered.

**Tech Stack:** Bash entrypoint, Docker, pytest static regression tests.

---

## Task 1: Regression Coverage

**Files:**
- Modify: `tests/unit/test_docker_port_runtime.py`
- Modify: `tests/unit/test_borg_cache_runtime.py`

- [ ] Add assertions that `entrypoint.sh` detects `/home/borg/.ssh` as a mountpoint before removing or linking it.
- [ ] Add assertions that mounted SSH directories are preserved with an explanatory log line.
- [ ] Update existing SSH persistence assertions so they still require normal-directory migration to `/data/ssh_keys`.
- [ ] Run `pytest tests/unit/test_docker_port_runtime.py tests/unit/test_borg_cache_runtime.py -q` and confirm the new assertions fail before the fix.

## Task 2: Entrypoint Fix

**Files:**
- Modify: `entrypoint.sh`

- [ ] Add a small mountpoint detection helper that prefers `mountpoint -q` and falls back to `/proc/self/mountinfo`.
- [ ] In the SSH migration block, copy existing normal-directory files to `/data/ssh_keys` as before.
- [ ] If `/home/borg/.ssh` is a mountpoint, do not `rm -rf` it and do not replace it with a symlink.
- [ ] If `/home/borg/.ssh` is not mounted, remove the normal directory and link it to `/data/ssh_keys` as before.
- [ ] Keep ownership and chmod setup for `/data/ssh_keys` unchanged.

## Task 3: Validation

**Files:**
- No additional source files expected.

- [ ] Run the targeted pytest command and confirm it passes.
- [ ] Run `ruff check app tests` and `ruff format --check app tests`.
- [ ] Build a local Docker image and run it with `/home/borg/.ssh` bind-mounted plus `PORT=8088`, then confirm the server reaches the configured port.
- [ ] Confirm no regression to existing release smoke assertions for `PORT=8088`.
