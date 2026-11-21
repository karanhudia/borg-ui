# This machine: protect by default, restore like WhatsApp

**Date:** 2026-11-20
**Status:** Design agreed with Karan 2026-11-20. Phase 1 implemented (PR 1); phases 2 to 4 not started.
**Plan:** to be written under `docs/engineering/plans/2026-11-20-this-machine.md`

## Why

Someone landing on borgui.com or the GitHub repo should see one reason to
install Borg UI within seconds: install it, and the machine it runs on is
protected without choosing anything. When something goes wrong, Borg UI brings
it back. Time Machine on a Mac is the reference, and WhatsApp is the reference
for Borg UI's own settings: a fresh install asks "start fresh or restore?" and
a lost instance comes back from that first screen.

Today every backup is hand-built. Quick Start makes that easier, but the user
still picks folders and a destination, and nothing protects Borg UI itself:
`docs/disaster-recovery.md` tells operators to back up `/data` by hand, and
`app/scripts/export_config.py` leaves out users, tokens, SSH keys, rclone
config and `.secret_key`, so it cannot restore an instance.

## Goals

- A fresh install protects its host after one click ("Start fresh"), with no
  folder or destination choices.
- Borg UI backs up its own state in every snapshot of that plan, and a fresh
  install can restore all of it from the first-start screen.
- Undo first: browse a point in time and restore a file, folder, app's data or
  system config through the existing restore wizard.
- Small by default (a smart source set, deduplicated), with more storage as an
  opt-in: big folders, a second disk, NAS, cloud sync, later Vault.
- Same-disk storage is allowed and never blocks setup. Borg UI nudges toward an
  off-machine copy.
- Every snapshot already carries what a later rebuild needs (package list,
  `/etc`, users, crontabs, container definitions), so v2 rebuild works from
  backups people made with v1.

## Non-goals (this spec)

- Rebuild of a fresh OS from a backup (v2, own spec, Pro).
- Proxmox VM and LXC backup (own spec, Pro).
- Vault hosted storage (own spec, Pro).
- Self-backup of Borg UI installs that use Postgres. The card says so and
  points to the disaster recovery docs. (Builder's call to revisit if cheap.)
- A new scheduler, retention model or destination type. Everything rides on
  existing plans, repositories and rclone sync.

## Anti-goals

- A second, parallel backup system next to backup plans. "This machine" is an
  ordinary plan the user can see and extend.
- Requiring a second disk, an account or any choice before the first snapshot.
- A recovery kit that goes stale when users add or edit ordinary repositories.
- A restore that leaves a half-replaced database if it fails.
- Backing up the live `borg.db`, `borg.db-wal` or `borg.db-shm`.

## Plan tier

Free on every plan: the "This machine" plan, self-backup, the recovery kit,
restore from the first-start screen and the dashboard. Pro: Proxmox, rebuild,
Vault, managed agents (unchanged). The smart source set must not depend on the
Pro-only full container scan; it uses fixed roots plus the free app detection
and database discovery.

## Approaches considered

- **A. Ordinary plan with a system role (chosen).** "This machine" is a normal
  `BackupPlan` and "This machine (local)" a normal `Repository`, each with a
  `system_role` marker. The marker shows a "System" chip, guards against
  accidental deletion, and adds one built-in self-backup step. Schedules,
  retention, restore checks, multiple repositories, rclone sync and the
  activity view are reused as they are. Cost: plan execution knows one special
  step.
- **B. Separate subsystem.** Own table, scheduler and pages. Rejected: it
  duplicates schedules, retention, destinations and sync, and contradicts "just
  the usual process so it can have multiple places".
- **C. Self-backup as a pre-backup script.** No execution changes. Rejected: a
  user can edit or delete the script and silently lose the ability to restore
  Borg UI, and the script would have to handle `.secret_key`.

## Design

### 1. The system plan and repository

- New nullable column `system_role` on `backup_plans` and `repositories`
  (value `this_machine`). At most one plan and one repository per role
  (unique partial index or service check, builder's call).
- **Repository "This machine (local)":**
  - Location: a folder on the host outside the Borg UI data volume, default
    `/var/backups/borg-ui` on the host. In Docker that is
    `<host-root-mount>/var/backups/borg-ui` (default compose mounts host `/`
    at `/local`). On a native install it is `/var/backups/borg-ui` directly.
  - Fallback when no host-root mount is found: `$DATA_DIR/this-machine`. The
    card and nudge then say the snapshots die with the Borg UI volume.
  - Host-root detection (builder's call on the exact rule): a
    `LOCAL_MOUNT_POINTS` entry that contains `etc/os-release` and differs from
    the container's own root. Native installs use `/`.
  - Borg 1, `repokey-blake2`, generated passphrase stored the way repositories
    store passphrases today.
- **Plan "This machine":**
  - Sources: fixed roots `/etc`, `/home`, `/root`, `/opt`, `/srv`,
    `/var/lib/docker/volumes`, `/usr/local/etc` (whichever exist), resolved
    under the host-root mount. New apps under those roots are covered without
    plan edits.
  - Excludes: caches (`**/.cache`, `**/node_modules/.cache`, browser caches),
    `/var/lib/docker/overlay2` and image layers, trash, temp folders, the
    repository folder itself, and the live `borg.db`, `-wal`, `-shm` wherever
    the data volume shows up under the roots.
  - Databases: at creation, run the existing database discovery and app
    detection; each detected database gets the dump step those flows already
    produce. A database that appears later produces a dashboard nudge ("New
    database found, add it to This machine"), never a silent plan edit.
  - Rebuild inputs (written into staging, see 2): installed package list for
    the detected package manager (dpkg/apt, rpm/dnf, apk, pacman), enabled
    systemd units, user crontabs, `docker ps -a` container definitions plus
    compose files found under the roots. Missing tools are skipped, not errors.
  - Schedule: hourly. Retention: 24 hourly, 7 daily, 4 weekly, 6 monthly.
    Prune and compact after backup on. Weekly restore check on, through the
    existing maintenance scheduler.
  - Size estimate shown on the first-start screen before the first run
    (fast walk with a time cap, "about 4.2 GB" wording; builder picks the cap).
- **Guards:** a system plan or repository cannot be deleted without a
  confirmation that names what is lost (Borg UI self-restore). Changing the
  self-backup repository's location, passphrase or SSH key goes through the
  kit flow (see 3), not the ordinary edit form. Everything else (adding
  repositories, rclone sync, schedule, excludes, extra folders) is edited the
  usual way.
- Plans and repositories lists show a small "System" chip. No new sidebar tab.

### 2. Self-backup step

- Runs inside the "This machine" plan before `borg create`, as a built-in step
  in plan execution, not a script.
- Writes `/data/self-backup/staging/` (data dir path, not literal `/data` on
  native; owner-only): `borg-ui-db.sqlite` copied with `_snapshot_sqlite`
  (`app/database/db_upgrade.py`; not named `borg.db`, which the plan excludes
  everywhere), `secret-key` holding the key in use (`SECRET_KEY` wins over
  the `.secret_key` file), `config.export` from the borgmatic export
  (`build_borgmatic_export_artifact`), a `manifest.json` (Borg UI version,
  alembic revision, created at, hostname), and `rebuild/` inputs last.
- The archive includes the staging folder, `ssh_keys/` and `borg_keys/`.
  The staging folder is deleted after the run, success or failure, and at
  start-up; a failed write leaves it empty so the backup still runs. Other
  plans exclude `**/self-backup/staging`.
- Archives are tagged or named so the restore engine can tell self-backup
  content exists (builder's call: an archive comment with the manifest, or a
  fixed path inside the archive).
- If the self-backup step fails, the run still backs up files but finishes as
  a warning, and the card shows "Borg UI settings were not included in the
  last snapshot".
- `_is_configured_sqlite_database` keeps hiding Borg UI's own database from
  the scanner. Self-backup is not a user-picked source.

### 3. Recovery kit

- One file, `borg-ui-recovery-kit-<hostname>-<date>.borgkit`, holding: the
  self-backup repository location(s), its passphrase or keyfile, any SSH key
  needed to reach it, and `.secret_key`. Encrypted with a key derived from a
  recovery code the user writes down.
- Crypto: `cryptography` (already in `requirements.txt`): Scrypt KDF plus
  AES-GCM, versioned JSON envelope. No new dependency. Recovery code: 24
  characters of Crockford base32 in groups of four, generated server-side,
  shown once.
- Which repository it points to: every repository attached to the "This
  machine" plan, preferring off-machine ones. The local one is included too,
  because with the own-host-folder default it survives losing the Borg UI
  volume.
- Offered when the first off-machine repository or rclone sync is added to the
  "This machine" plan. Downloadable again from Settings (new code each time;
  old kits keep working until the self-backup repo's location, passphrase or
  SSH key changes, or `.secret_key` rotates).
- It only goes stale on those changes. The guided flow for them ends with a
  new kit. Ordinary repositories never touch it.
- Borg UI records that a kit was downloaded and when; the nudge stays until
  one exists for the current self-backup state.

### 4. Restore engine

One backend, two entry points (first-start screen, dashboard card).

1. Read the kit and recovery code, or (advanced) a repository location plus
   passphrase typed by hand.
2. Open the repository, list archives that carry self-backup content, newest
   first, with the Borg UI version from the manifest.
3. Refuse archives whose alembic revision is newer than this app's head, with
   a message naming the version needed. Older revisions are fine.
4. Extract `borg-ui-db.sqlite` (as `borg.db`), `secret-key` (as
   `.secret_key`), `ssh_keys/` and `borg_keys/` into
   `$DATA_DIR/restore-pending/` and write a marker.
5. Exit the process with a non-zero code. Docker (`restart: unless-stopped`)
   and the native unit (`Restart=on-failure`) restart it.
6. On start, before the database is opened, `db_upgrade` sees the marker: it
   takes a rollback copy of the current `borg.db` with `_snapshot_sqlite`,
   swaps in the pending files, runs the normal upgrade, and removes the
   marker. If the upgrade fails, it restores the rollback copy and records the
   failure so the UI can show it.
7. After restart, existing startup steps redeploy SSH keys from the database.

From the dashboard (restoring over a running instance): a confirmation that
says what is replaced, then the scheduler is paused and running jobs are
cancelled before step 4. Files on disk are not touched by this restore; they
are restored through the normal restore wizard on the "This machine" timeline.

Restores replace users and passwords too: after a first-start restore the user
logs in with the restored instance's credentials. The first-start screen says
so before they confirm.

### 5. Onboarding

- New screen after `FirstLoginPasswordSetup` and before Quick Start, shown only
  when the instance has no repositories or plans yet:
  - **Start fresh:** creates the "This machine" plan and repository, shows the
    size estimate, starts the first snapshot, then continues to Quick Start
    (skippable).
  - **Restore from a Borg UI backup:** the restore dialog (kit + code, pick a
    snapshot, confirm).
- Existing installs upgrading to this version see a dashboard prompt "Protect
  this machine" instead of the first-start screen.

### 6. Dashboard card and nudge

- "This machine" card at the top of the dashboard: status (Protected, Running,
  Warning, Failed, Not set up), last and next snapshot, space used, last
  restore check, a snapshot timeline (bar per snapshot, height = data changed,
  click to browse), and a Restore button that opens the restore wizard on the
  plan's archives with a choice of "files" or "Borg UI settings".
- Nudge while every repository on the plan is on the same disk (or in the data
  volume fallback): "Your snapshots are on the same disk as your data. They
  help if you delete or break something, not if the disk dies." Data volume
  fallback adds "or if the Borg UI volume is removed". Actions: add a second
  disk, add a NAS or server (existing add-repository flow pre-attached to the
  plan), copy to cloud (existing rclone sync on the local repository). Dismiss
  hides it for 30 days.

### UI rules that apply

`ui-ux-pro-max` for every UI decision. `WizardDialog` for the restore flow,
`ResponsiveDialog` for the kit and confirmations. Storybook stories for every
new state (card states, nudge variants, first-start screen, restore steps,
kit dialog), checked visually in light and dark. No heavy left accent borders.
No em dashes in copy. All copy in the existing i18n files, every language
complete.

### Docs

Update `docs/disaster-recovery.md` (self-backup, kit, restore from first
start) and the onboarding/getting-started docs in the same change. The README
and borgui.com pitch ("install it, your machine is protected") follow once
shipped, in their own repos.

## Phases

1. System role, "This machine" plan and repository creation, source set,
   self-backup step. Backend plus tests.
2. Dashboard card, nudge, "System" chips, upgrade prompt for existing
   installs.
3. Recovery kit (format, Settings download, trigger on first off-machine copy,
   guided self-backup repo changes).
4. Restore engine and the first-start screen.

Each phase lands as its own PR, TDD, with stories for its UI.

### 7. Calls made while checking the design (Claude's, correct if wrong)

- **Off-machine detection:** a repository counts as off-machine when it is
  SSH, has an rclone sync, or is a local path whose device (`st_dev`) differs
  from the host root's. Same device or the data-volume fallback means "same
  disk".
- **Compact cadence:** prune after every run, compact at most once a day
  (hourly compact is wasted I/O).
- **Restoring onto a different machine:** restored plans keep their old paths.
  Paths that do not exist show up through the existing repository and plan
  error states. The "This machine" card offers "Re-point This machine to this
  host" when its sources or local repository are missing.
- **Two live instances:** restoring a kit while the old instance still runs
  means both write the same repositories. The restore confirmation warns
  "Turn off the old Borg UI first"; Borg's repository lock covers the race.

### 8. Permissions: read-all capability (decided by Karan 2026-11-20)

The default container runs as `PUID=1001`, and there is no local privilege
helper today. As that user Borg UI cannot read `/root`, `/etc/shadow`, other
users' homes or many container volumes, cannot create `/var/backups/borg-ui`
on the host, and cannot restore root-owned files in place.

Decision:

- Backups read any file while the web app stays non-root. Mechanism: both
  Borg versions are Python scripts on the image's Python (Borg 2 in a venv
  whose `python` is a symlink), so a capability on `borg` itself does
  nothing, and one on `python3` would cover the whole web app. Instead the
  image ships a dedicated interpreter copy (Borg 2 venv built with
  `--copies`, plus a copied `python3` for Borg 1) that only runs Borg, with
  `cap_dac_read_search+ep` set on those copies. The `borg` entry points
  invoke them in isolated mode (`-I`), so `PYTHON*` variables and user
  site-packages are ignored. The web app's own `python3` gets no capability.
- Honest boundary: the app launches that interpreter, so a compromised web
  app can read any host file through it. It still cannot write outside what
  user 1001 can write, and is not root. That is the trade-off accepted over
  `PUID=0`.
- The default `docker-compose.yml` adds `cap_add: [DAC_READ_SEARCH]` so the
  container may grant it. Docs explain the line.
- The entrypoint (root at start) creates the host snapshot folder under the
  host-root mount and `chown`s it to `PUID:PGID`, before dropping privileges.
- Native installs: the packaging grants the same capability to the system
  `borg` binary through the unit (`AmbientCapabilities=` plus
  `CapabilityBoundingSet=`), builder's call on the exact mechanism.
- Restore: files the app user can write are restored in place. Files it
  cannot are restored next to the original (`<path>.restored-<date>`), and the
  result screen shows a one-line copy command to run as root.
- When the capability is missing (old compose file, rootless Docker, hardened
  hosts): back up what is readable, finish the run as a warning, and the card
  lists skipped folders with "Grant full read access" instructions. Detection:
  a startup probe that tries to read a root-only file through `borg`
  (builder's call on the probe).
- `PUID=0` keeps working as today and needs none of this.

## Left to the builder

Exact host-root detection rule, uniqueness mechanism for `system_role`, how
archives mark self-backup content, size-estimate time cap, cache exclude list
details, kit envelope field names, Storybook story layout.
