---
title: Disaster Recovery
nav_order: 9
description: "Recover Borg UI, restore data, and validate backups with restore checks"
---

# Disaster Recovery

A backup is useful only when you can restore it.

Borg UI uses Borg Backup behind the scenes. Your backup data lives in standard Borg repositories, not in a proprietary Borg UI format.

That means Borg UI does not need to be running for a data recovery. If you have the Borg repository, the required secrets, and access to the storage location, you can restore with the Borg CLI.

Borg UI adds the web interface, schedules, repository checks, restore checks, logs, notifications, and remote-machine management around Borg.

## Recovery Priorities

The minimum needed to recover data is:

| Item | Why it matters |
| --- | --- |
| Borg repository | This is the backup data |
| Repository passphrase or keyfile | Encrypted Borg repositories cannot be restored without it |
| Storage access | Local path, SSH access, or remote repository credentials |
| Restore machine | Any machine or container with Borg installed and enough space to restore |

The extra items needed to rebuild the same Borg UI instance are:

| Item | Why it matters |
| --- | --- |
| Borg UI `/data` volume | Contains the database, generated secret key, logs, SSH material, schedules, and job metadata |
| Compose file and `.env` | Recreates ports, volume mounts, user IDs, path mappings, and deployment settings |
| Same container path mappings | Lets existing repositories, sources, and restore destinations keep working |
| Remote-machine SSH access | Needed for Borg UI-managed SSH repositories and remote sources |

Keep repository passphrases outside Borg UI too. If the only copy of a passphrase was in Borg UI and `/data` is gone, Borg UI cannot recover that encrypted repository for you.

The generated `/data/.secret_key` is part of app state. If it changes, existing sessions are invalidated and stored encrypted app secrets, such as SSH private keys and script secrets, may no longer decrypt.

## Repository Checks vs Restore Checks

Use both.

| Check | What it proves |
| --- | --- |
| Repository check | Borg can verify repository integrity |
| Restore check | Borg UI can extract data from the latest archive into a temporary directory |

A repository check does not prove your restore path works. A restore check does not prove every old archive is good.

## Restore Checks

Restore checks are configured in:

```text
Schedule > Restore Checks
```

Borg UI selects the latest archive, restores into a disposable directory under `/data`, records logs, and deletes the temporary restore directory when the job finishes.

Restore check modes:

| Mode | Use when |
| --- | --- |
| Managed canary payload | You want a fast default check for every repository |
| Selected probe paths | You want to verify important real files or folders |
| Full archive drill | You want to test extracting the whole latest archive |

### Managed Canary

Canary mode is the safest default. Borg UI adds a small managed payload to backups and later restores it to verify file presence, size, and hash.

If the latest archive was created before the canary payload existed, the check can fail with a missing canary message. Run a new backup once, then run the restore check again.

### Probe Paths

Probe-path mode restores archive paths you choose.

Use it for representative files such as:

```text
etc/hostname
srv/app/config.yml
var/lib/app/database.sqlite
```

Paths are archive-relative paths. Use the archive browser in the restore-check dialog when you are unsure.

### Full Archive

Full-archive mode extracts the entire latest archive.

Use it only when you have enough temporary space under `/data` and enough time for the job to finish.

## Recommended Routine

For each important repository:

1. Schedule a managed canary restore check weekly.
2. Add probe paths for the files that matter most.
3. Run a full-archive drill occasionally, during a maintenance window.
4. Review failed or warning restore-check jobs from the Restore Checks history.
5. Treat stale restore checks as a recovery risk, not cosmetic noise.

The dashboard does not penalize repositories that never configured restore checks. Once restore checks are configured or have run, failed and stale checks affect repository health. Stale checks warn after 14 days without a successful run and become critical after 30 days.

## Manual Restore Drill

Run this before you need it in an incident:

1. Create a restore staging path, for example `/local/restore-drill`.
2. Open Archives.
3. Select the repository and archive.
4. Select a small but meaningful folder or file set.
5. Restore to the staging path, not over the original source.
6. Verify the restored data with the application or tooling that normally uses it.
7. Remove the staging data after verification.

Use a staging path first. Restoring directly over damaged production data makes mistakes harder to undo.

## During an Incident

1. Stop writes to the damaged source system.
2. Pick the archive from before the damage happened.
3. Restore to a clean staging path.
4. Verify files, ownership, permissions, and application-level consistency.
5. Move or promote the restored data using your normal system tools.
6. Run a fresh backup after the system is healthy again.

If the repository reports a lock, do not break it until you have confirmed no Borg process is still running.

## Rebuild Borg UI

If the Borg UI host is lost but the repositories survive:

1. Recreate the Docker Compose file and `.env`.
2. Restore the Borg UI `/data` volume, including `borg.db` and `.secret_key`.
3. Mount local repositories and restore destinations at the same container paths as before.
4. Restore SSH access for remote repositories and remote machines.
5. Start Borg UI.
6. Confirm login, repositories, schedules, and remote machines.
7. Run restore checks for critical repositories.

If `/data` is not recoverable, install Borg UI fresh and import the existing repositories again. Existing Borg archives are still usable if you still have the repository data, passphrases or keyfiles, and SSH access. Borg UI job history, schedules, users, saved settings, and encrypted app secrets from the old instance are gone.

## Borg CLI Fallback

Borg UI is not required to restore a Borg repository. If the UI is unavailable, use Borg directly from a machine with repository access:

```bash
export BORG_PASSPHRASE='your-repository-passphrase'
borg list /path/to/repository
mkdir -p /tmp/borg-restore
cd /tmp/borg-restore
borg extract /path/to/repository::ARCHIVE_NAME path/in/archive
```

For SSH repositories, use the same Borg repository URL and SSH key that Borg UI uses.

Use this fallback in your recovery drills too. It proves you are not dependent on the web UI being alive.
