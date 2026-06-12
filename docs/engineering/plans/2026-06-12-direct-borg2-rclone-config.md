# Direct Borg 2 Rclone Config Implementation Plan

**Goal:** Ensure Direct Borg 2 rclone repositories use Borg UI's managed
rclone configuration for repository creation, verification, backup, and
maintenance commands.

**Architecture:** Borg UI stores rclone remotes in the managed config at
`settings.rclone_config_root/rclone.conf`. Cloud Mirror passes that config to
the `rclone` CLI explicitly, while Borg 2 direct rclone commands run through
`app/core/borg2.py`. The fix belongs in the Borg 2 command environment so every
Borg 2 subprocess can resolve Borg UI-managed rclone remotes without per-call
special cases.

**Tech Stack:** Python, FastAPI service layer, Borg 2 command wrapper, pytest.

---

## Tasks

### Task 1: Reproduce Missing Rclone Config in Borg 2 Process Env

**Files:**

- Modify: `tests/unit/test_borg2.py`

- [x] Add a failing pytest that calls `borg2.rcreate(...)` for a
  `rclone://prod-s3/borg-ui/direct` repository with
  `asyncio.create_subprocess_exec` patched.
- [x] Capture the subprocess `env` argument and assert `RCLONE_CONFIG` equals
  `<settings.rclone_config_root>/rclone.conf`.
- [x] Run the focused `test_rcreate_injects_managed_rclone_config_into_process_env`
  test and confirm it fails because `RCLONE_CONFIG` is missing.

### Task 2: Inject Managed Rclone Config Centrally

**Files:**

- Modify: `app/core/borg2.py`

- [x] Update `Borg2Interface._base_env` to set `RCLONE_CONFIG` to
  `Path(settings.rclone_config_root) / "rclone.conf"` before merging explicit
  per-call env overrides.
- [x] Preserve explicit per-call `env["RCLONE_CONFIG"]` overrides by keeping
  the existing final `env.update(extra)` merge.
- [x] Run the targeted pytest from Task 1 and confirm it passes.

### Task 3: Validate Direct Rclone Regression Surface

**Files:**

- Test: `tests/unit/test_borg2.py`
- Test: `tests/unit/test_api_rclone.py`
- Test: `tests/unit/test_v2_backup_service.py`

- [x] Run the targeted backend pytest batch for Borg 2, direct rclone
  repository API handling, and v2 backup service behavior.
- [x] Run `ruff check app tests`.
- [x] Run `ruff format --check app tests`.
- [x] Run a dev-stack smoke check that creates a Borg 2 Direct rclone
  repository through the API, reloads it, and runs a backup through Borg 2.
- [x] Record validation results in the Linear workpad.
