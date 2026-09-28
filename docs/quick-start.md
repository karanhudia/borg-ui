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

1. **What**: choose what to back up. Pick **Files on this server** for folders
   on the machine running Borg UI, **Files on another computer** for a
   server, NAS or PC that Borg UI can reach over SSH, or **Another computer
   with the Borg UI agent** (Pro or Enterprise) for a machine that runs the
   [agent](managed-agents) and connects out to Borg UI, for example a laptop
   behind a firewall.
2. **Connect** (another computer only): for SSH, pick a computer Borg UI
   already knows, or add one with its host name, username and password. Borg UI installs its
   SSH key there with that password once; the password is not saved. Adding a
   computer needs an account that can manage SSH; otherwise you can only pick
   an existing one. For the agent, pick an enrolled computer or choose **Add a
   computer**, which shows the install command; Quick Start selects the
   computer as soon as its agent connects.
3. **Folders**: add one or more folders. In Docker, your server's disk usually
   appears under `/local` (see
   [Understand Container Paths](usage-guide#understand-container-paths)).
   For another computer, the folder button browses that computer.
4. **Where**: a disk on this server, or another server over SSH (Borg must be
   installed there; see [Remote Machines](ssh-keys)). With the agent, backups
   go to a disk on that same computer. Borg UI suggests a
   folder, `/local/borg-backups/<name>` on this server. The location cannot
   be inside a folder you are backing up.
5. **Protect**: name the backup and set a passphrase. Save the passphrase
   somewhere outside this server (the **Download** button gives you a text
   file). Without it, the backups cannot be restored.
6. **When**: every day at 02:00 by default, or every 6 hours, weekly, or a
   custom schedule.
7. **Review**: check the summary and press **Create backup**.

When it finishes you can run the first backup right away or leave it to the
schedule.

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
