# This machine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One click protects the Borg UI host with an ordinary, flagged backup plan that also backs up Borg UI itself, and a fresh install can restore Borg UI from a recovery kit on its first screen.

**Architecture:** "This machine" is a normal `BackupPlan` plus a local `Repository`, both marked `system_role = "this_machine"`, created by calling the existing create routes. Plan execution gains one built-in pre-backup step (self-backup staging) for that plan. A recovery kit (Scrypt + AES-GCM envelope) points at the plan's repositories; a restore engine extracts Borg UI state into a pending folder, exits, and `db_upgrade`'s entrypoint run swaps it in before migrations.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, `cryptography` (already pinned), Borg 1 CLI, React + MUI + TanStack Query, Storybook, Vitest, pytest.

**Spec:** `docs/engineering/specs/2026-11-20-this-machine.md`

## Global Constraints

- Free on every plan: no `PlanGate`, no feature check, no use of the Pro-only full container scan (`/containers/scan`). App detection and database discovery are free and may be used.
- No new Python or npm dependency. Crypto comes from `cryptography==50.0.2`.
- Never back up the live `borg.db`, `borg.db-wal`, `borg.db-shm`.
- Self-backup on Postgres installs is out of scope: status reports `self_backup_supported: false`.
- No em dashes in code comments, copy, i18n strings, commit messages.
- Every new string in all four locales (`frontend/src/locales/{en,de,es,it}.json`), complete. No partial localization.
- UI: run `ui-ux-pro-max` before UI work; `ResponsiveDialog` / `WizardDialog` only, no raw MUI `Dialog`; no heavy left accent borders; a Storybook story for every new state; render light and dark before pushing (fnm Node 24, see project memory).
- Do not bump `VERSION` or agent versions.
- Work in worktree `../borg-ui-this-machine` (branch `feat/this-machine` for phase 1; one branch per phase from fresh `origin/main` for later phases, after the previous phase merges).
- Alembic: before writing a migration, `git fetch origin main` and set `down_revision` to the single head of `origin/main` at that moment (`python -m alembic heads` from the worktree with `DATA_DIR` pointed at a scratch folder). Recheck before pushing.
- Backend tests run with `../borg-ui/.venv311/bin/python -m pytest`. Frontend with `cd frontend && npx vitest run <path>`; worktrees need `npm ci` in `frontend/` once.
- Names fixed by the spec: plan `This machine`, repository `This machine (local)`, role value `this_machine`, host folder `/var/backups/borg-ui`, data-volume fallback `$DATA_DIR/this-machine`, staging `$DATA_DIR/self-backup/staging/`, kit file `borg-ui-recovery-kit-<hostname>-<YYYY-MM-DD>.borgkit`, pending folder `$DATA_DIR/restore-pending/`.
- Schedule `0 * * * *` (hourly), retention 24 hourly / 7 daily / 4 weekly / 6 monthly / 0 yearly, prune after every run, compact at most once a day, weekly restore check.

## Review Focus

1. **Host root missing or partial** (custom `LOCAL_STORAGE_PATH`, rootless Docker): setup must still succeed with the data-volume fallback and say so, never 500. Test in Task 1.2.
2. **Restore archive from a newer Borg UI** (alembic revision not in this app's script directory): refuse before extracting anything, name the version. Test in Task 4.1.
3. **Swap fails mid-way** (migration error after files moved): the previous `borg.db`, `.secret_key`, `ssh_keys/` are back exactly and the marker records the error. Test in Task 4.2.
4. **Wrong recovery code or tampered kit**: a typed error the UI shows as "code doesn't match", no stack trace, no partial state. Test in Task 3.1.
5. **Staging left behind** after a crash or failed run: next run starts from an empty staging folder and staging never lands in a non-system plan. Test in Task 1.3.

---

## Phase 1: system plan, sources, self-backup (PR 1)

### Task 1.1: `system_role` columns and delete guard

**Files:**
- Create: `app/database/alembic/versions/<rev>_add_system_role.py`
- Modify: `app/database/models.py` (`Repository` ~line 291, `BackupPlan` ~line 891)
- Modify: `app/api/backup_plans.py` (`delete_backup_plan`, ~line 2306), `app/api/repositories.py` (`delete_repository`, ~line 6090; `permanent-delete`, ~line 6201)
- Test: `tests/unit/test_this_machine_role.py`

**Interfaces:**
- Produces: `Repository.system_role: Optional[str]`, `BackupPlan.system_role: Optional[str]`, constant `THIS_MACHINE_ROLE = "this_machine"` in `app/services/this_machine.py` (file created here with only the constant). Serialized plans and repositories include `"system_role"`. Deleting a system plan or repository needs query param `confirm_system=true`, else 409 with `detail={"key": "backend.errors.thisMachine.confirmDelete"}`.

- [ ] **Step 1: Write failing tests**

```python
def test_plan_and_repository_serialize_system_role(client, db, admin_headers): ...
    # create plan + repo with system_role="this_machine" directly in db
    # GET /api/backup-plans/{id} -> body["system_role"] == "this_machine"
    # GET /api/repositories/{id} -> body["system_role"] == "this_machine"

def test_delete_system_plan_requires_confirmation(client, db, admin_headers):
    r = client.delete(f"/api/backup-plans/{plan.id}", headers=admin_headers)
    assert r.status_code == 409
    assert r.json()["detail"]["key"] == "backend.errors.thisMachine.confirmDelete"
    r = client.delete(f"/api/backup-plans/{plan.id}?confirm_system=true", headers=admin_headers)
    assert r.status_code == 200

def test_delete_system_repository_requires_confirmation(...)  # same for repositories, both delete routes

def test_second_this_machine_plan_rejected(db):
    # inserting a second BackupPlan with system_role="this_machine" raises IntegrityError
```

- [ ] **Step 2:** Run `pytest tests/unit/test_this_machine_role.py -v`. Expected: FAIL (no column).
- [ ] **Step 3:** Add nullable `system_role = Column(String, nullable=True)` to both models; migration adds both columns plus a unique index on each `system_role` (NULLs stay unconstrained in SQLite and Postgres). Add `system_role` to both serializers and the confirmation check to the three delete routes. Add `backend.errors.thisMachine.confirmDelete` to the backend error key catalog the frontend translates (all four locales).
- [ ] **Step 4:** Run tests. Expected: PASS. Also `pytest tests/migrations -q`.
- [ ] **Step 5: Commit** `feat(this-machine): system role on plans and repositories`

### Task 1.2: Host root, source set, setup service and API

**Files:**
- Modify: `app/services/this_machine.py`
- Create: `app/api/this_machine.py`; register in `app/main.py` next to the other `/api` routers (`prefix="/api/this-machine"`, tag `This machine`)
- Test: `tests/unit/test_this_machine_setup.py`

**Interfaces:**
- Consumes: `THIS_MACHINE_ROLE`, `create_repository(RepositoryCreate, current_user, db)` in `app/api/repositories.py`, `create_backup_plan(BackupPlanPayload, current_user, db)` in `app/api/backup_plans.py` (called directly, not over HTTP).
- Produces:
  - `find_host_root(mount_points: list[str], container_root: Path = Path("/")) -> Optional[Path]`: first mount point containing `etc/os-release` whose `os.stat().st_dev`/inode differs from `container_root`'s. Native installs (`settings.native_install` or no `/.dockerenv`, use whatever the codebase already uses to tell native from Docker) return `Path("/")`.
  - `snapshot_location(host_root: Optional[Path], data_dir: Path) -> tuple[Path, bool]`: `(host_root / "var/backups/borg-ui", False)` or `(data_dir / "this-machine", True)`; the bool is `in_data_volume`.
  - `SOURCE_ROOTS = ("etc", "home", "root", "opt", "srv", "var/lib/docker/volumes", "usr/local/etc")`
  - `source_directories(host_root: Path) -> list[str]`: the roots that exist under `host_root`, as absolute container paths.
  - `exclude_patterns(host_root: Path, repo_path: Path, data_dir: Path) -> list[str]`: caches (`**/.cache`, `**/node_modules/.cache`, `**/Cache`, `**/.local/share/Trash`), `var/lib/docker/overlay2`, `var/lib/docker/image`, `**/tmp`, `repo_path`, and `**/borg.db`, `**/borg.db-wal`, `**/borg.db-shm`.
  - `async setup_this_machine(db: Session, user: User) -> SetupResult` (`SetupResult` dataclass: `plan_id: int`, `repository_id: int`, `in_data_volume: bool`, `skipped_roots: list[str]`). Idempotent: returns the existing ids if a system plan exists. Generates a 32-byte urlsafe passphrase, encryption `repokey-blake2`, compression `lz4`, Borg 1. Plan payload uses the global schedule/retention values; `run_prune_after=True`, `run_compact_after=True`, `run_restore_check_after=False`; sets the repository's weekly restore check through the same fields the restore-check scheduler reads (`Repository` restore check cron columns, ~line 470 of models). Database dumps: call the database discovery used by `GET /api/source-discovery/databases` and app detection (`POST /apps/detect` internals) and attach each detection's script drafts as source scripts, exactly as the plan wizard's payload does.
  - `estimate_size(paths: list[str], excludes: list[str], time_cap_s: float = 5.0) -> SizeEstimate` (`bytes: int`, `complete: bool`).
  - Routes: `GET /api/this-machine` -> `ThisMachineStatus` (Task 2.1 fills it; here returns `{"configured": bool, "plan_id", "repository_id", "in_data_volume", "self_backup_supported"}`), `GET /api/this-machine/estimate` -> `{"bytes", "complete", "in_data_volume"}`, `POST /api/this-machine/setup` -> `SetupResult`. Setup and estimate need the admin role.
  - Compact at most once a day: the plan runs compact only when the repository's last compact is older than 24h. Add this check where `run_compact_after` is honoured in `backup_plan_execution_service.py`, gated on `system_role` so user plans keep today's behaviour.

- [ ] **Step 1: Write failing tests** (use `tmp_path` fake host roots)

```python
def test_find_host_root_needs_os_release(tmp_path): ...       # no etc/os-release -> None
def test_find_host_root_skips_container_root(tmp_path): ...   # same dev/inode as container_root -> None
def test_snapshot_location_falls_back_to_data_volume(tmp_path):
    assert snapshot_location(None, tmp_path) == (tmp_path / "this-machine", True)
def test_source_directories_only_existing_roots(tmp_path): ...   # creates etc, home only -> 2 paths
def test_excludes_cover_live_database_and_repo(tmp_path):
    ex = exclude_patterns(root, root / "var/backups/borg-ui", tmp_path / "data")
    assert "**/borg.db-wal" in ex and str(root / "var/backups/borg-ui") in ex
async def test_setup_creates_flagged_plan_and_repo(db, admin_user, fake_borg_init, tmp_path):
    result = await setup_this_machine(db, admin_user)
    plan = db.get(BackupPlan, result.plan_id)
    assert plan.name == "This machine" and plan.system_role == "this_machine"
    assert plan.cron_expression == "0 * * * *" and plan.schedule_enabled
    assert (plan.prune_keep_hourly, plan.prune_keep_daily, plan.prune_keep_weekly,
            plan.prune_keep_monthly, plan.prune_keep_yearly) == (24, 7, 4, 6, 0)
    repo = db.get(Repository, result.repository_id)
    assert repo.name == "This machine (local)" and repo.system_role == "this_machine"
async def test_setup_is_idempotent(...)            # second call returns same ids, one plan in db
async def test_setup_without_host_root_uses_data_volume(...)  # in_data_volume True, still 201
def test_setup_route_requires_admin(client, operator_headers): ...  # 403
def test_system_plan_compacts_at_most_daily(...)   # last compact 2h ago -> compact skipped; 25h -> runs
```

`fake_borg_init`: patch whatever `create_repository` calls to run `borg init` (`initialize_borg_repository`) the way `tests/unit/test_api_repositories*.py` already does.

- [ ] **Step 2:** Run `pytest tests/unit/test_this_machine_setup.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement the functions and routes above in the named files.
- [ ] **Step 4:** Run tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(this-machine): set up the host plan and repository`

### Task 1.3: Self-backup step in plan execution

**Files:**
- Create: `app/services/self_backup.py`
- Modify: `app/services/backup_plan_execution_service.py` (`_run_pre_backup_scripts` ~line 1688; `execute_run` ~line 1555 for cleanup)
- Test: `tests/unit/test_self_backup.py`

**Interfaces:**
- Consumes: `_snapshot_sqlite(source: Path, dest: Path)` from `app/database/db_upgrade.py`; `BorgmaticExportService(db).export_all_repositories(repository_ids=None, include_schedules=True)` + `build_borgmatic_export_artifact(configs)` from `app/services/borgmatic_service.py`; `resolve_secret_key_file(data_dir)` from `app/config.py`; `settings.ssh_keys_dir`.
- Produces:
  - `staging_dir(data_dir: Path) -> Path` = `data_dir / "self-backup" / "staging"`
  - `write_staging(db: Session, data_dir: Path, *, app_version: str, alembic_revision: str, hostname: str) -> list[str]`: empties then fills staging with `borg.db` (via `_snapshot_sqlite`), `config.export` (artifact bytes; skipped silently when there are no repositories to export), `manifest.json` `{"borg_ui_version", "alembic_revision", "created_at" (UTC ISO), "hostname", "format": 1}`. Returns the paths to add to `borg create`: staging dir, the secret key file, `ssh_keys_dir`. Raises `SelfBackupUnsupported` on non-SQLite databases.
  - `collect_rebuild_inputs(host_root: Optional[Path], staging: Path) -> list[str]`: writes `staging/rebuild/` with whichever exist: `dpkg-status` (copy of `var/lib/dpkg/status`), `apk-installed` (`var/lib/apk/db/installed`), `pacman.txt` (names under `var/lib/pacman/local`), `rpm.txt` (`rpm -qa --root <host_root>` when `rpm` is on PATH), `crontabs/` (copy of `var/spool/cron`), `systemd-enabled.txt` (symlink names under `etc/systemd/system/*.wants`), `containers.json` (`docker inspect` of `docker ps -aq` over the mounted socket). Returns the names written; anything missing is skipped, never an error. Called by `write_staging`; no host root means nothing written.
  - `clear_staging(data_dir: Path) -> None` (no error if absent)
  - Self-backup content path inside archives: the staging folder's absolute path. The restore engine finds `manifest.json` by listing the archive for `*/self-backup/staging/manifest.json`.
  - Execution: in `_run_pre_backup_scripts`, after plan and source scripts succeed and only when `context` belongs to a plan with `system_role == THIS_MACHINE_ROLE`, call `write_staging` and add the returned paths to this run's source directories (extend whatever `PlanRunContext` field feeds `borg create` paths; add a field `extra_source_paths: list[str]` if none fits). On exception, return `PreHookVerdict(warning="Borg UI settings were not included in this snapshot: <reason>")`, never failed. `execute_run` calls `clear_staging` in a `finally` for system plans.

- [ ] **Step 1: Write failing tests**

```python
def test_write_staging_copies_db_and_manifest(tmp_path, sqlite_db_file, db): 
    paths = write_staging(db, tmp_path, app_version="2.4.10", alembic_revision="abc", hostname="h")
    s = staging_dir(tmp_path)
    assert (s / "borg.db").exists() and json.loads((s / "manifest.json").read_text())["alembic_revision"] == "abc"
    assert str(s) in paths
def test_write_staging_empties_leftovers(tmp_path, ...):   # stale file in staging is gone after write
def test_write_staging_refuses_postgres(...):               # raises SelfBackupUnsupported
def test_clear_staging_tolerates_missing(tmp_path): clear_staging(tmp_path)
def test_rebuild_inputs_skip_missing_tools(tmp_path):
    # host root with only var/lib/dpkg/status and var/spool/cron/crontabs/root; docker and rpm absent
    assert set(collect_rebuild_inputs(root, s)) == {"dpkg-status", "crontabs"}
async def test_system_plan_run_includes_staging_paths(...): # borg create argv contains staging, secret key, ssh_keys
async def test_user_plan_run_has_no_staging(...):          # non-system plan: no staging paths, staging dir never created
async def test_self_backup_failure_is_warning(...):        # write_staging raises -> run status "completed_with_warnings" (whatever the warning status is called), files still backed up
async def test_staging_cleared_after_failed_run(...):      # borg create fails -> staging dir absent
```

- [ ] **Step 2:** Run `pytest tests/unit/test_self_backup.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement as above.
- [ ] **Step 4:** Run the new tests plus `pytest tests/unit -k "backup_plan" -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(this-machine): back up Borg UI itself in the host plan`

### Task 1.4: Read-all capability in the image

**Files:**
- Modify: `Dockerfile.runtime-base` (builder stage ~line 59; final stage ~line 145-165)
- Modify: `docker-compose.yml` (borg-ui service), `entrypoint.sh` (before the privilege drop ~line 320)
- Modify: `packaging/native/start.sh` and the native installer that builds `${APP_ROOT}/venv` (mirror: a `--copies` read venv with the capability, set by the installer which runs as root)
- Modify: `app/services/this_machine.py` (probe)
- Test: `tests/unit/test_this_machine_capability.py`; manual image check below

**Interfaces:**
- Produces:
  - Image: `/opt/borg1-read` = `python3 -m venv --copies --system-site-packages`; `/opt/borg2-venv` built with `--copies`. In the final stage (file capabilities do not survive `COPY --from` reliably): `apt-get install libcap2-bin`, `setcap cap_dac_read_search+ep` on `/opt/borg1-read/bin/python3` and `/opt/borg2-venv/bin/python3`. `/usr/local/bin/borg` becomes `#!/bin/sh\nexec /opt/borg1-read/bin/python3 -I -m borg "$@"`; `/usr/local/bin/borg2` becomes the same with `/opt/borg2-venv/bin/python3`. The app's own `python3` gets nothing.
  - `docker-compose.yml`: `cap_add: [DAC_READ_SEARCH]` with a one-line comment.
  - Entrypoint: if a host-root mount exists (same rule as `find_host_root`, in shell: `[ -f "$m/etc/os-release" ]` over `LOCAL_MOUNT_POINTS`), `mkdir -p "$m/var/backups/borg-ui" && chown "$PUID:$PGID" "$m/var/backups/borg-ui" && chmod 700 ...`. Failures log a warning, never stop start-up.
  - `has_read_all(host_root: Optional[Path]) -> bool`: runs `borg` wrapper's interpreter (`/opt/borg1-read/bin/python3 -I -c "open(sys.argv[1],'rb').read(1)" <host_root>/etc/shadow`) and returns exit 0; returns True when running as root; False when no host root.
  - `ThisMachineStatus.read_all_access: bool` (cached at startup).

- [ ] **Step 1: Write failing tests** for `has_read_all` with a patched subprocess runner: root -> True; probe exit 0 -> True; exit 1 -> False; no host root -> False.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement Dockerfile, compose, entrypoint, native installer, probe.
- [ ] **Step 4:** Tests PASS, then build and check the image:

```bash
docker build -f Dockerfile.runtime-base -t borg-ui-runtime:cap . && docker build -t borg-ui:cap .
docker run --rm --cap-add DAC_READ_SEARCH -v /:/local:ro --entrypoint gosu borg-ui:cap borg sh -c 'borg --version && /opt/borg1-read/bin/python3 -I -c "open(\"/local/etc/shadow\",\"rb\").read(1)" && echo READ_OK && python3 -c "open(\"/local/etc/shadow\",\"rb\")" || echo APP_DENIED_OK'
```

Expected: a Borg version, `READ_OK`, then a PermissionError and `APP_DENIED_OK`. Without `--cap-add`: no `READ_OK`. Run on a Linux Docker host (Docker Desktop for Mac hides the host's `/etc/shadow`; use the dev container host or CI).
- [ ] **Step 5: Commit** `feat(this-machine): read-all capability for Borg only`

### Task 1.5: Docs for phase 1

**Files:** `docs/disaster-recovery.md`, `docs/installation.md` (the `cap_add` line and what it grants), `docs/quick-start.md` (mention This machine exists).
- [ ] Write the sections, plain language, no em dashes. Then run the docs build the repo uses (`cd docs && npm run build` if present) and expect success.
- [ ] Commit `docs(this-machine): protecting the host and Borg UI itself`
- [ ] Open PR 1 via the `prep-pr` skill (local CodeRabbit loop until zero findings).

## Phase 2: dashboard card, nudge, chips, upgrade prompt (PR 2)

### Task 2.1: Status API

**Files:** `app/services/this_machine.py`, `app/api/this_machine.py`, test `tests/unit/test_this_machine_status.py`

**Interfaces:**
- Produces `GET /api/this-machine` -> `ThisMachineStatus`:
  `configured: bool`, `plan_id`, `repository_id`, `state: Literal["protected","running","warning","failed","not_set_up"]`, `last_snapshot_at`, `next_snapshot_at`, `space_used_bytes`, `last_restore_check: {status, finished_at} | None`, `self_backup_supported: bool`, `self_backup_included_last_run: bool`, `read_all_access: bool`, `skipped_paths: list[str]` (permission-denied paths from the last run's Borg output, max 20), `off_machine: bool`, `in_data_volume: bool`, `nudge_dismissed_until: datetime | None`, `kit_current: bool` (Task 3.2 fills it; False until then), `new_databases: list[str]` (detections not attached to the plan), `timeline: list[{archive_id, name, created_at, changed_bytes}]` (last 48 archives, `changed_bytes` from each archive's stats `deduplicated_size`).
- `is_off_machine(repo: Repository, host_root_dev: int) -> bool`: SSH or agent repo, or has an rclone `RepositoryStorage`, or local path whose `st_dev != host_root_dev`. `off_machine` is any repository on the plan.
- `sources_missing: bool`: true when none of the plan's source directories exist or the local repository path is gone (restored onto another host). `POST /api/this-machine/repoint` (admin) recomputes `source_directories`/`exclude_patterns` for the current host root and, if the local repository path is gone, creates a new "This machine (local)" there (old record kept, renamed "This machine (local, previous host)" and unlinked from the plan).
- `POST /api/this-machine/nudge/dismiss` -> sets `nudge_dismissed_until = now + 30 days` (store on `SystemSettings`; add the column in this phase's migration).
- `state`: running if an active plan run; failed if last run failed; warning if last run had warnings or `not read_all_access`; protected if last run succeeded; not_set_up if not configured.

- [ ] Tests first: one per `state` branch, `is_off_machine` for local same-dev, local other-dev, ssh, rclone; dismiss sets 30 days; `sources_missing` true after deleting the fake host's roots and `repoint` fixes it while keeping the old repository record; `new_databases` lists a detection not attached to the plan; `skipped_paths` parsed from a captured Borg log fixture with two `Permission denied` lines. Run, FAIL, implement, PASS, commit `feat(this-machine): status endpoint`.

### Task 2.2: Card, timeline, nudge (frontend)

**Files:**
- Create: `frontend/src/pages/dashboard-v3/ThisMachineCard.tsx`, `ThisMachineTimeline.tsx`, `ThisMachineNudge.tsx`, `useThisMachine.ts`, `ThisMachineCard.stories.tsx`, `ThisMachineCard.test.tsx`
- Modify: `frontend/src/pages/DashboardV3.tsx` (card first), `frontend/src/services/api.ts` (new `thisMachineAPI`: `status()`, `estimate()`, `setup()`, `dismissNudge()`), locales x4.

**Interfaces:**
- Consumes `GET /api/this-machine` and Task 2.1 fields verbatim.
- `ThisMachineCard({ status, onRestore, onAddDisk, onAddServer, onCopyToCloud, onDismissNudge, onSetUp })`, pure; `useThisMachine()` wraps the query (`queryKey: ['this-machine']`) and actions.
- Nudge copy (en), exact: same disk: "Your snapshots are on the same disk as your data. They help if you delete or break something, not if the disk dies." Data volume adds: " or if the Borg UI volume is removed." Actions: "Add a second disk", "Add a NAS or server", "Copy to cloud", "Remind me in 30 days". Add-disk and add-server open the existing add-repository flow with the plan id preset to attach on save; copy-to-cloud opens the existing rclone sync setup for the local repository.
- Skipped-folders state: "12 folders were skipped because Borg UI can't read them." + "Grant full read access" linking to the installation docs section from Task 1.5.
- New databases: "New database found: {{name}}. Add it to This machine" (one line per entry in `new_databases`) opening the plan editor's database source step for that detection.
- Moved host: when `sources_missing`, "This machine's folders aren't on this host. Re-point This machine to this host" calling `repoint()`.
- Restore button opens the existing `RestoreWizard` (`frontend/src/components/RestoreWizard.tsx`) on the chosen timeline archive; "Borg UI settings" choice is added in Task 4.3.

- [ ] Run `ui-ux-pro-max` for the card, timeline and nudge.
- [ ] Tests first (`ThisMachineCard.test.tsx`): renders each `state`; new-database line per entry; re-point line only when `sources_missing`; nudge hidden when `off_machine` or dismissed; data-volume wording appears only when `in_data_volume`; skipped-folders line only when `skipped_paths` non-empty; clicking a timeline bar calls `onRestore(archive_id)`.
- [ ] `npx vitest run src/pages/dashboard-v3/ThisMachineCard.test.tsx` FAIL, implement, PASS.
- [ ] Stories: Protected, Running, Warning (skipped folders), Failed, NotSetUp, SameDiskNudge, DataVolumeNudge, OffMachine, SelfBackupUnsupported (Postgres). Render light and dark, `npm run lint && npm run typecheck`.
- [ ] Commit `feat(this-machine): dashboard card and off-machine nudge`

### Task 2.3: System chips and upgrade prompt

**Files:** `frontend/src/pages/backup-plans/BackupPlansContent.tsx` (~line 303 chip area), the repository card in `frontend/src/pages/repositories-page/`, delete confirmations for both (send `confirm_system=true` after a confirmation that says "Borg UI will no longer back up this machine or itself"), stories for both lists with a system item, locales x4.
- Upgrade prompt for existing installs: `ThisMachineCard` with `state="not_set_up"` and `configured=false` shows "Protect this machine" with the estimate and a Set up button (calls `setup()`), only for admins.
- [ ] Tests first: chip renders when `system_role` set; delete of a system plan shows the system confirmation and sends `confirm_system=true`. FAIL, implement, PASS, stories, light/dark, commit `feat(this-machine): system chips and setup prompt`.
### Task 2.4: Restore next to the original when it can't be written

**Files:** `app/services/restore_service.py` (in-place restore path), the restore result UI the existing restore job card renders (`frontend/src/components/RestoreJobCard.tsx`), locales x4, test `tests/unit/test_restore_side_by_side.py`

**Interfaces:**
- When an in-place restore (destination = original location) of an archive from a `system_role` plan hits permission denied on a path, that path's subtree is restored to `<path>.restored-<YYYY-MM-DD>` instead (Borg 1 `extract` into a temp dir under the same parent, then rename; fall back to the snapshot folder when the parent isn't writable either). The job result carries `side_by_side: list[{original, restored}]`.
- `RestoreJobCard` shows, when `side_by_side` is non-empty: "Some files belong to root, so they were restored next to the originals. To put them back, run:" and one copy-able `sudo cp -a <restored>/. <original>/` line per entry (host paths, i.e. without the host-root mount prefix).
- User plans keep today's behaviour.
- [ ] Tests first: fake extract raising permission denied for `/local/etc/nginx` produces `side_by_side == [{"original": "/etc/nginx", "restored": "/etc/nginx.restored-2026-11-20"}]` (freeze date); a non-system plan still fails as today; card test renders the command with host paths. FAIL, implement, PASS, story for the card state, commit `feat(this-machine): restore root-owned files side by side`.

- [ ] Update `docs/navigation.md` / dashboard docs if they describe dashboard cards. Open PR 2 via `prep-pr`.

## Phase 3: recovery kit (PR 3)

### Task 3.1: Kit format

**Files:** create `app/services/recovery_kit.py`, test `tests/unit/test_recovery_kit.py`

**Interfaces:**
- `generate_recovery_code() -> str`: 24 Crockford base32 chars (`0123456789ABCDEFGHJKMNPQRSTVWXYZ`) from `secrets`, formatted `XXXX-XXXX-XXXX-XXXX-XXXX-XXXX`.
- `normalize_code(code: str) -> str`: uppercase, strip dashes/spaces, map `O->0`, `I->1`, `L->1`.
- `KitPayload` (pydantic): `repositories: list[KitRepository]` (`name, path, borg_version, encryption, passphrase, keyfile_b64 | None, ssh: {host, port, username, private_key_b64} | None`, off-machine first), `secret_key_b64`, `created_at`, `hostname`, `borg_ui_version`.
- `seal(payload: KitPayload, code: str) -> bytes`: JSON envelope `{"format": "borgkit", "v": 1, "kdf": "scrypt", "n": 2**15, "r": 8, "p": 1, "salt": b64, "nonce": b64, "ct": b64}`, Scrypt 32-byte key from `normalize_code(code)`, AES-GCM with the envelope header (`format`, `v`) as associated data.
- `open_kit(data: bytes, code: str) -> KitPayload`; raises `KitInvalid` (not a kit / unknown version) or `KitCodeMismatch` (`InvalidTag`).
- `kit_fingerprint(payload: KitPayload) -> str`: sha256 over sorted (path, passphrase, keyfile, ssh key) of each repository plus the secret key. Used for staleness.

- [ ] Tests first: round trip; wrong code -> `KitCodeMismatch`; flipped byte in `ct` -> `KitCodeMismatch`; garbage -> `KitInvalid`; `v: 2` -> `KitInvalid`; normalize accepts lowercase and `O`/`I`; code length and alphabet; fingerprint changes when a passphrase changes and not when order of input repositories changes. FAIL, implement, PASS, commit `feat(this-machine): recovery kit format`.

### Task 3.2: Kit download, staleness, trigger

**Files:** `app/services/recovery_kit.py`, `app/api/this_machine.py`, migration adding `SystemSettings.recovery_kit_fingerprint` and `recovery_kit_downloaded_at`, test `tests/unit/test_recovery_kit_api.py`

**Interfaces:**
- `build_kit_payload(db: Session) -> KitPayload`: every repository linked to the system plan, off-machine first (`is_off_machine`), plus `.secret_key`.
- `POST /api/this-machine/recovery-kit` (admin) -> JSON `{"code": str, "filename": str, "kit_b64": str}`; stores fingerprint and downloaded-at. New code every call.
- `ThisMachineStatus.kit_current = stored fingerprint == kit_fingerprint(build_kit_payload(db))`; `kit_prompt: bool` = `off_machine and not kit_current`.
- Guarded changes: `PUT /api/repositories/{id}` on a system repository that changes `path`, `passphrase` or `connection_id` returns 409 `backend.errors.thisMachine.useGuidedChange` unless `guided=true`; the guided UI (Task 3.3) sends `guided=true` and then opens the kit dialog. Everything else edits normally.

- [ ] Tests first: kit opens with returned code and lists off-machine repo first; adding an rclone sync makes `kit_prompt` True; downloading makes `kit_current` True; changing the system repo passphrase with `guided=true` makes it False; editing an unrelated repository keeps it True; non-admin 403; PUT without `guided` on path change -> 409. FAIL, implement, PASS, commit.

### Task 3.3: Kit dialog and Settings entry (frontend)

**Files:** create `frontend/src/components/recovery-kit/RecoveryKitDialog.tsx` (+ `.stories.tsx`, `.test.tsx`); modify `ThisMachineCard.tsx` (kit prompt line), `frontend/src/components/ExportImportTab.tsx` (a "Recovery kit" section: last downloaded, "Download a new kit"), the system repository edit form (path/passphrase/connection changes go through a confirm step that then opens the kit dialog), `api.ts`, locales x4.
- Dialog (`ResponsiveDialog`): title "Save your recovery kit"; body "If this machine is lost, a fresh Borg UI install needs this file and this code to bring everything back."; the code in monospace; "Write the code down or put it in your password manager. The file alone can't be opened without it."; checkbox "I saved the code somewhere off this machine"; "Download recovery kit" enabled only after the checkbox; download uses the returned filename.
- Auto-open: when `kit_prompt` flips to true after the user adds an off-machine copy in this session; otherwise the card shows "Save your recovery kit" as an action.
- [ ] `ui-ux-pro-max`; tests first (download disabled until checked; filename from API; card shows kit action when `kit_prompt`); stories (Default, Checked, Error); light/dark; commit. Update `docs/disaster-recovery.md` kit section and `docs/export-import.md`. Open PR 3 via `prep-pr`.

## Phase 4: restore engine and first-start screen (PR 4)

### Task 4.1: Inspect and stage a restore

**Files:** create `app/services/self_restore.py`; modify `app/api/this_machine.py`; test `tests/unit/test_self_restore.py`

**Interfaces:**
- Consumes: `open_kit`, `KitPayload`, Borg 1 CLI helpers in `app/core/borg.py` / `borg_router.py` for `list` and `extract` with a passphrase env.
- `pending_dir(data_dir) -> Path` = `data_dir / "restore-pending"`; marker `pending_dir / "READY"` (JSON: `archive`, `repository_path`, `manifest`, `requested_at`).
- `async list_restorable(source: KitPayload | ManualSource) -> list[RestorableArchive]` (`ManualSource`: `path`, `passphrase`, optional `ssh`; `RestorableArchive`: `repository_index`, `archive`, `created_at`, `borg_ui_version`, `alembic_revision`, `compatible: bool`, `reason_key: str | None`). Tries repositories in kit order, first that opens wins; reads each archive's `manifest.json` with `borg extract --stdout`; newest first; at most 50.
- `compatible` = revision is in this app's alembic script directory (`ScriptDirectory.from_config(_alembic_config(url)).get_revision(rev)` does not raise). Otherwise `reason_key="backend.errors.thisMachine.newerBackup"` with the version in params.
- `async stage_restore(source, archive: str) -> None`: refuses incompatible; extracts `*/self-backup/staging/borg.db`, the secret key file, and `ssh_keys/` into `pending_dir` (flattened to `borg.db`, `.secret_key`, `ssh_keys/`); writes `READY` last.
- Routes (admin only; on first start the user who just set the password is that admin): `POST /api/this-machine/restore/inspect` (multipart kit file + code, or manual source) -> `list[RestorableArchive]`; `POST /api/this-machine/restore` (same source + `archive`) -> 202, then pauses the scheduler, cancels running jobs via the existing cancel paths, and schedules `os._exit(3)` 1s after the response.
- [ ] Tests first (fake borg runner returning fixture manifests): wrong code -> 400 with `backend.errors.thisMachine.kitCodeMismatch`; newer revision listed with `compatible=False`; `stage_restore` on incompatible raises and leaves no `pending_dir`; compatible stage writes the three items then `READY`; kit with a dead first repository falls through to the second; restore route refused for a non-admin once repositories exist. FAIL, implement, PASS, commit.

### Task 4.2: Swap at startup

**Files:** `app/services/self_restore.py` (pure function, no app imports beyond config), `app/database/db_upgrade.py` `__main__` block (~line 850), `packaging/native/start.sh` (already runs db_upgrade; confirm), test `tests/unit/test_self_restore_swap.py`

**Interfaces:**
- `apply_pending_restore(data_dir: Path, db_path: Path, secret_key_file: Path, ssh_keys_dir: Path, upgrade: Callable[[], object]) -> SwapResult` (`status: Literal["none","applied","rolled_back"]`, `error: str | None`). Steps: no `READY` -> `none`. Otherwise move current `borg.db` (+ `-wal`/`-shm` after a `_snapshot_sqlite` into `borg.db.pre-restore`), `.secret_key`, `ssh_keys/` aside into `data_dir/restore-rollback/<timestamp>/`; move pending items into place; call `upgrade()`; on success delete `pending_dir` and keep the rollback folder (one, newest); on any exception put the rollback items back exactly, write `data_dir/restore-failed.json` (`error`, `archive`, `at`), delete `pending_dir`, return `rolled_back`.
- `__main__`: call `apply_pending_restore(..., upgrade=upgrade_from_settings)` before the normal `upgrade_from_settings()` and skip the second call when it returned `applied`.
- `ThisMachineStatus.last_restore: {status, error, at} | None` reads `restore-failed.json` / a `restore-applied.json` written on success; the UI shows it once.

- [ ] Tests first: no marker -> `none`, files untouched; applied -> new db in place, rollback folder exists, pending gone; `upgrade` raising -> original bytes of all three restored, `restore-failed.json` written, result `rolled_back`; leftover `-wal` from the old db never ends up beside the restored db. FAIL, implement, PASS, commit.

### Task 4.3: Restore wizard and first-start screen (frontend)

**Files:**
- Create: `frontend/src/components/self-restore/SelfRestoreWizard.tsx` (`WizardDialog`: Kit, Snapshot, Confirm), `SelfRestoreWizard.stories.tsx`, `.test.tsx`; `frontend/src/components/welcome/WelcomeDialog.tsx` (+ stories, test)
- Modify: `frontend/src/components/quick-start/QuickStartProvider.tsx` and `useQuickStartAutoOpen.ts`: when auto-open fires (zero repositories and plans, on `/dashboard`) open `WelcomeDialog` instead; "Start fresh" calls `thisMachineAPI.setup()`, shows the estimate it fetched on open, then calls `openQuickStart()`; "Restore from a Borg UI backup" opens `SelfRestoreWizard`.
- Modify: `ThisMachineCard` Restore button: a choice "Files" (existing `RestoreWizard`) or "Borg UI settings" (`SelfRestoreWizard` with the kit step replaced by "this machine's repositories").
- Modify: `api.ts`, locales x4.
- Copy (en), exact: Start fresh card "Borg UI starts protecting this machine right away: your config, home folders, app data and databases, every hour. About {{size}} to start. You can add more places later." Restore card "Moving to a new machine or reinstalling? Bring back your repositories, plans, schedules, SSH keys and history." Confirm step: "This replaces everything in this Borg UI, including users and passwords. After the restart, sign in with the restored account." and "Turn off the old Borg UI first, so both don't write to the same repositories." Incompatible row: "Made by Borg UI {{version}}. Update this Borg UI to restore it."
- After `POST /restore` returns 202, the wizard shows "Restarting..." and polls `/api/health` (or the existing health endpoint) until it answers, then reloads to the login page.
- [ ] `ui-ux-pro-max`; tests first: WelcomeDialog shows instead of Quick Start when empty; Start fresh calls setup then opens Quick Start; restore wizard disables Next until kit and code given; incompatible archives not selectable; wrong code shows the mismatch message. FAIL, implement, PASS.
- [ ] Stories: Welcome (estimate loading, estimate shown, data-volume warning), wizard each step, incompatible list, wrong code, restarting. Light and dark.
- [ ] Commit `feat(this-machine): first-start screen and Borg UI restore`

### Task 4.4: End-to-end check and docs

- [ ] Add a browser e2e in `tests/e2e/` following `docs/engineering/specs/2026-11-13-browser-e2e.md` (fresh `DATA_DIR`): fresh instance, Start fresh, run the plan once, download kit, wipe `DATA_DIR` except the snapshot folder, start a new instance, restore from the kit, log in with the original user, see the original plan. Unset `SSH_AUTH_SOCK` locally.
- [ ] `docs/disaster-recovery.md`: "Restore Borg UI from a recovery kit" walkthrough, replacing the manual `/data` backup advice as the primary path; `docs/quick-start.md` and onboarding docs: the first-start screen.
- [ ] Full suites: `../borg-ui/.venv311/bin/python -m pytest tests/unit -q -n 4` and `cd frontend && npx vitest run && npm run lint && npm run typecheck`. Expected: all pass.
- [ ] Open PR 4 via `prep-pr`.
