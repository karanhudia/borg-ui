---
title: Usage Guide
nav_order: 4
description: "Create repositories, build backup plans, browse archives, and restore files"
---

# Usage Guide

This guide covers the normal path after installation.

If you are unsure where to start in the app, use the
[Navigation](navigation) guide to understand what each sidebar tab is for. This
usage guide focuses on the common backup and restore flow.

## First Login

Open Borg UI:

```text
http://localhost:8081
```

Default credentials:

```text
admin / admin123
```

Change the password in Settings > Account.

## Understand Container Paths

Borg UI sees paths inside the container, not host paths.

If Docker maps:

```yaml
- /mnt/usb-drive:/local:rw
```

then this host path:

```text
/mnt/usb-drive/borg-backups/laptop
```

is this Borg UI path:

```text
/local/borg-backups/laptop
```

Use the container path in repositories, sources, and restore destinations.

## Create a Local Repository

1. Go to Repositories.
2. Choose Create Repository.
3. Select a local or mounted path.
4. Enter a path under a mounted location, for example:

```text
/local/borg-backups/laptop
```

5. Choose encryption settings.
6. Save.

Keep repository passphrases and keyfiles safe. Borg UI can help manage repositories, but Borg encryption recovery still depends on your secrets.

## Create a Remote Repository

Remote repositories use a Remote Machine connection.

1. Go to Remote Machines.
2. Add and test the remote machine.
3. Go to Repositories.
4. Choose Create Repository.
5. Select a remote or SSH location.
6. Pick the remote machine and enter the repository path, for example:

```text
/backups/laptop
```

7. Choose encryption settings.
8. Save.

Use remote repositories when the Borg archive should live on another server or off-site storage.

For BorgBase, Hetzner Storage Box, other hosted Borg providers, and NAS path
mapping notes, see [Provider Guides](provider-guides).

## Add a Cloud Mirror

Cloud mirrors keep the primary repository local, SSH-backed, or managed-agent-backed and sync a copy to an rclone remote.

1. Go to Cloud Storage and configure the rclone remote.
2. Go to Repositories and create or edit a local, SSH, or managed-agent repository.
3. Open the Cloud Mirror step.
4. Enable the mirror, choose the rclone remote, and enter or browse a relative remote path.
5. Review and save.

For SSH repositories, Borg UI mounts the repository on the server with SSHFS during each mirror sync, then unmounts it after rclone finishes. Borg UI owns that temporary mount path; the UI and API do not ask for a cache or staging path.

For managed-agent repositories, the selected agent syncs its agent-local repository path to the configured rclone remote. Borg UI owns the mirror metadata and rclone target; the agent owns any temporary rclone execution files and removes them after the sync.

## Use a Direct Borg 2 rclone Repository

Direct rclone repositories are an advanced Borg 2 mode. Borg writes directly to a `rclone:` repository URL instead of writing to a normal primary location and syncing a Cloud Mirror.

Use the standard Cloud Mirror flow when you want Borg UI to keep a normal local, SSH, or managed-agent primary repository and mirror it off-site. Use direct rclone only when you intentionally want Borg 2 itself to operate through rclone and you accept that Borg UI will not show cache hydration or mirror sync status for that repository.

1. Go to Repositories and create or import a repository.
2. In Location, select Borg v2.
3. Open Advanced storage mode and enable direct Borg 2 rclone repository.
4. Enter a URL such as:

```text
rclone://remote-name/path/to/repository
```

5. Continue through Security, Advanced, and Review.

The rclone remote must be configured for the same account and environment that runs Borg. Borg UI validates this mode as Borg 2-only and blocks SSH, managed-agent, cached rclone, and Cloud Mirror settings on the same repository.

## Import an Existing Repository

Use Import Existing when a Borg repository already exists and you want Borg UI to manage or monitor it.

1. Go to Repositories.
2. Choose Import Existing.
3. Select the repository location.
4. Enter the passphrase or upload the keyfile if the repository needs one.
5. Save, then verify archives can be listed.

Full mode lets Borg UI run backups for the repository. Observability-only mode is for repositories backed up by something else; Borg UI can browse archives, restore files, run checks, and show health, but it will not run backups or scheduled backups for that repository.

If the repository comes from BorgBase, Hetzner Storage Box, another hosted Borg
service, or a NAS with special path mapping, keep the provider's repository path
exactly as given. See [Provider Guides](provider-guides).

## Repository vs Backup Plan

A repository is the storage target. Use it to inspect repository-level information such as path, archive count, total size, last backup, last check, archives, restores, and maintenance actions.

A Backup Plan is the backup workflow. It defines what to back up, which repository or repositories to use, when the backup should run, and which scripts or maintenance actions should run around it.

Community plans can use one repository. Pro plans can use multiple repositories, such as one local target and one off-site target, and can run them one after another or in parallel.

## Choose Backup Sources

Use paths that exist inside the container.

Examples:

```text
/local/Documents
/local/photos
/local/projects
```

If you need multiple host locations, mount them explicitly:

```yaml
volumes:
  - /home/user/Documents:/documents:ro
  - /mnt/photos:/photos:ro
  - /mnt/backups:/backups:rw
environment:
  - LOCAL_MOUNT_POINTS=/documents,/photos,/backups
```

Then use `/documents`, `/photos`, and `/backups` in the UI.

For remote sources, choose a Remote Machine in the Backup Plan and select paths from that machine.

### Filesystem snapshot sources

Borg UI can create Btrfs or ZFS snapshots for local Backup Plan source paths.
The snapshot command runs inside the Borg UI runtime before Borg starts; it does
not run on Remote Machines or managed agents.

For Btrfs, the `btrfs` command must be available inside the Borg UI runtime. If
the Host requirements area says `btrfs not found`, check the Borg UI container
or host runtime, not only the NAS shell. Custom images should include
`btrfs-progs`.

For Synology DSM 7, treat Btrfs snapshot mode as a runtime-level operation:

- Mount or select the shared-folder Btrfs subvolume at the same path Borg UI can
  see.
- Verify the selected path from inside the Borg UI runtime with
  `btrfs subvolume show /path/to/source`.
- Verify the runtime user can create and remove a read-only snapshot with
  `btrfs subvolume snapshot -r /path/to/source /path/to/staging/test` and
  `btrfs subvolume delete /path/to/staging/test`.
- DSM shared-folder ACLs are not enough for these commands. Use a Borg UI
  runtime account or narrowly scoped sudo rule that can run the Btrfs subvolume
  snapshot and delete commands.

For database sources, open the Database tab in the source chooser, scan the Borg
UI server or a Remote Machine, select the detected database or a template, then
choose Add database. This queues the database in the Database tab; choose Use
these paths to save the source selection to the plan. By default Borg UI backs
up a generated dump directory on the same machine where the database was found.
Use Database capture mode only if you need to back up the original live path
instead of a generated dump.

You can add more than one database before choosing Use these paths. When you use
generated database scripts, Borg UI tracks the script assignments for each
selected database source, so each database runs with its own dump path and
metadata.

## Create a Backup Plan

Create a Backup Plan after the repository exists.

If the repository already has source paths, you can start from the repository:

1. Go to Repositories.
2. Find the local or remote repository.
3. Choose Create Backup Plan.
4. Name the plan.
5. Choose whether to move the repository source settings into the plan.
6. If the repository already has a schedule, choose whether to copy it to the plan and pause the old repository schedule.
7. Save, then review the plan from Backup Plans.

For a new setup, start from Backup Plans:

1. Go to Backup Plans.
2. Choose Create Backup Plan.
3. Choose local paths or a remote source.
4. Select one or more repositories as storage targets.
5. Configure archive settings, scripts, and maintenance options.
6. Configure the schedule, or leave it disabled for manual runs.
7. Review and save.

In the Scripts step, add saved scripts from the script library to the
pre-backup or post-backup chain. Plan scripts can be reordered, can receive
their own parameter values, and can define behavior such as continuing or
skipping on pre-backup failure. Post-backup scripts can run always, only after
success, only after failure, or only after a warning. Backup Plans use saved
scripts only; create or edit the script body from the Scripts page first.

For a local repository, the plan can back up local container paths such as `/local/Documents` into `/local/borg-backups/laptop`.

For a remote repository, the plan can back up local or remote sources into the SSH repository. If you want both a local copy and an off-site copy, add both repositories to the plan when your license allows multiple repositories.

## Find Plans for a Repository

1. Go to Repositories.
2. Find the repository.
3. Choose View linked backup plans.

Backup Plans opens with a repository filter applied, so the list only shows plans that write to that repository. Use Clear repository filter to return to all plans.

## Run a Backup Plan

1. Go to Backup Plans.
2. Find the plan.
3. Choose Run.

The job page shows live progress, logs, and final status for each repository in the plan.

If an older repository still has legacy source settings, its repository card can also show Legacy Backup. Use Backup Plans for new backup workflows.

## Browse Archives

1. Go to Archives.
2. Select a repository.
3. Pick an archive.
4. Browse folders and files.

Redis is used to speed up repeated archive browsing. The first browse of a large archive can still take time because Borg has to list archive contents.

## Restore Files

1. Go to Archives.
2. Open an archive.
3. Select files or folders.
4. Choose Restore.
5. Pick a destination path that exists inside the container.

Example destination:

```text
/local/restore-test
```

If `/local` maps to `/mnt/usb-drive`, restored files appear under:

```text
/mnt/usb-drive/restore-test
```

## Remote Machines

Use Remote Machines for SSH-based sources and destinations.

Typical flow:

1. Go to Remote Machines.
2. Generate or import the system SSH key.
3. Add a remote machine with host, port, username, and optional default path.
4. Deploy the public key or copy it into the remote user's `authorized_keys`.
5. Test the connection.
6. Use that remote machine when creating remote repositories or remote backup sources.

The old `/ssh-keys` route redirects to Remote Machines.

Remote source backups and SSH restore destinations use SSHFS. The container needs FUSE access for those flows; see [Installation](installation#optional-fuse-access).

## Backup Plan Schedules

Backup Plan schedules run backups automatically.

1. Go to Backup Plans.
2. Create or edit a plan.
3. Open the Schedule step.
4. Set the cron expression and timezone.
5. Turn the schedule on or off.
6. Save.

Plans can also run prune, compact, and check after successful repository backups.

The Schedules area still shows scheduled repository work. New backup schedules should usually live on Backup Plans.

Use notifications for scheduled backup failures so failures do not go unnoticed.

## Maintenance

Repository maintenance actions include:

- check
- prune
- compact
- break lock, when you are certain no Borg process is running

Use check and restore verification regularly. A backup that cannot be restored is not useful.

Scheduled repository checks and restore checks are managed from Schedule.

See [Disaster Recovery](disaster-recovery) for restore-check modes and recovery drills.

## Notifications

Configure notifications in Settings > Notifications.

Recommended minimum:

- backup failure
- backup warning
- restore failure
- schedule failure
- check failure

See [Notifications](notifications).

## Job Logs

Activity and job views show backup, restore, restore-check, check, prune, compact, and package-install history.

Admins can delete supported job entries and associated log files. This removes UI history; it does not delete Borg archives. Archive deletion is a separate archive operation.

## Troubleshooting

Common path, permission, lock, and archive-browsing issues are covered on the
[Troubleshooting](troubleshooting) page:

- [Permission denied](troubleshooting#permission-denied)
- [Path not found](troubleshooting#path-not-found)
- [Repository locked](troubleshooting#repository-locked)
- [Slow archive browsing](troubleshooting#slow-archive-browsing)
