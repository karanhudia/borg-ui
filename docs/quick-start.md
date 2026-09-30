---
title: Quick Start
nav_order: 4
description: "Set up your first scheduled, self-maintaining backup in a few questions"
---

# Quick Start

Quick Start is the fastest way to a working backup. It asks a few plain
questions and then creates everything for you: the repository, and a backup
plan with a schedule and automatic cleanup.

Open it from **New backup** at the top of the sidebar. On a fresh install with
no repositories and no backup plans, it also opens once by itself on the
Dashboard. You can also start it from the empty Repositories and Backup Plans
pages.

Quick Start needs an account that can create repositories. Accounts without
that permission do not see the button.

## The steps

1. **App**: pick the app you are backing up, such as Immich, or **Something
   else** for plain folders. See [Backing up an app](#backing-up-an-app).
2. **What**: choose where the data lives. Pick **Files on this server** for folders
   on the machine running Borg UI, **Files on another computer** for a
   server, NAS or PC that Borg UI can reach over SSH, or **Another computer
   with the Borg UI agent** (Pro or Enterprise) for a machine that runs the
   [agent](managed-agents) and connects out to Borg UI, for example a laptop
   behind a firewall.
3. **Connect** (another computer only): for SSH, pick a computer Borg UI
   already knows, or add one with its host name, username and password. Borg UI installs its
   SSH key there with that password once; the password is not saved. Adding a
   computer needs an account that can manage SSH; otherwise you can only pick
   an existing one. For the agent, pick an enrolled computer or choose **Add a
   computer**, which shows the install command; Quick Start selects the
   computer as soon as its agent connects.
4. **Folders**: add one or more folders. In Docker, your server's disk usually
   appears under `/local` (see
   [Understand Container Paths](usage-guide#understand-container-paths)).
   For another computer, the folder button browses that computer.
5. **Where**: a disk on this server, or another server over SSH (Borg must be
   installed there; see [Remote Machines](ssh-keys)). With the agent, backups
   go to a disk on that same computer. Borg UI suggests a
   folder, `/local/borg-backups/<name>` on this server. The location cannot
   be inside a folder you are backing up.
6. **Protect**: name the backup and set a passphrase. Save the passphrase
   somewhere outside this server (the **Download** button gives you a text
   file). Without it, the backups cannot be restored.
7. **When**: every day at 02:00 by default (an app brings its own time), or every 6 hours, weekly, or a
   custom schedule.
8. **Review**: check the summary and press **Create backup**.

When it finishes you can run the first backup right away or leave it to the
schedule.

## Backing up an app

When you pick an app, Quick Start looks for its Docker container on the chosen
machine and fills in its data folder. It also:

- lists what is inside that folder in plain words, with the size of each
  part and, for the app's database dumps, when the latest one was written,
- gives every folder a **Back up** box: ticked, except folders the app can rebuild by itself (untick the database dumps and the dump check is dropped too),
- schedules the backup after the app's own maintenance, and
- adds a check that runs before each backup, where the app needs one.

Each app lists what it does, and the app version it was checked against, on
the **Folders** step.

If Borg UI runs in Docker and cannot see the app's folder, Quick Start shows
the line to add to the `volumes` of Borg UI in `docker-compose.yml`. Add it,
restart Borg UI, and press **Scan again**. If the container is not found, for
example on an agent, type the folder yourself.

In Quick Start the check runs on the Borg UI server, so it is only added when
the app runs on this server. The Backup Plans **Apps** tab runs it on the
app's own machine.

### Immich

Borg UI backs up Immich's `UPLOAD_LOCATION` folder, which holds your photos and
the database dumps Immich writes every night at 02:00. The backup runs at
03:00. It skips `thumbs` and `encoded-video`; after a restore, run the
**Generate Thumbnails** and **Transcode Videos** jobs in Immich to rebuild them.

Older installs that still mount their media at `/usr/src/app/upload` are
found too. Folders the container mounts as external libraries are listed as
**External library** and backed up by default; Immich only indexes those, so
they are not in its own folder.

Keep **Administration > Settings > Backup** turned on in Immich. The check
stops the backup when no database dump is newer than 26 hours, so an archive
never holds your photos without the database that organizes them. See
[Immich's backup guide](https://docs.immich.app/administration/backup-and-restore).

In the Backup Plans wizard, the **Apps** tab of the source chooser adds an app
to a plan the same way, on this server or an SSH machine. A plan can hold
several apps. Each app's check runs on the machine the app is on, and removing
the app from the plan removes its excludes and check too.

## What it sets up

| Setting | Default |
| --- | --- |
| Encryption | On (`repokey`), protected by your passphrase |
| Compression | `zstd,3` |
| Keep | 7 daily, 4 weekly, 6 monthly, 1 yearly |
| After each backup | Delete old backups (prune), free up space (compact), check integrity for up to an hour |
| Schedule | On |

Open **Customize** on the review step to change any of these. Everything Quick
Start creates is a normal repository and backup plan, so you can edit it later
from Repositories and Backup Plans.

## If something fails

The progress list shows which step stopped and why. **Retry** continues from
that step and does not create the repository twice. **Edit answers** takes you
back to the form; once the repository exists, changes to its location,
passphrase or encryption no longer apply, but the plan name, folders and
schedule do.

## When to use the full wizards

Quick Start covers the common case. Use Repositories and Backup Plans directly
for cloud storage, database and container sources, several repositories in one
plan, or scripts.
