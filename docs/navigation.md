---
title: Navigation
nav_order: 5
description: "What each Borg UI tab is for and how to follow the product flow"
---

# Navigation

Use the sidebar as the main path through Borg UI. Some tabs appear only when
your account has the right permission, the feature is enabled, or the current
license supports it.

## Normal Path

For a new setup, follow the sidebar in this order:

1. Open Dashboard to check overall health.
2. Add storage targets from Repositories or Cloud Storage, and register infrastructure endpoints
   from Remote Clients or Remote Machines.
3. Create a plan from Backup Plans.
4. Configure automatic runs from the plan schedule or the Schedule page.
5. Watch work in Activity and browse results in Archives.
6. Adjust preferences, notifications, and system options from Settings.

## Overview

| Sidebar area | Tab | Use it for |
| --- | --- | --- |
| Main | Dashboard | Check repository health, recent activity, backup freshness, and restore-check status. |
| Main | Activity | Review job history, live or recent logs, failures, and completed backup, restore, check, prune, compact, script, or package work. |
| Infrastructure | Remote Clients | Register other Borg UI client servers, check health and version compatibility, and switch this browser to a remote client. |
| Infrastructure | Remote Machines | Add SSH-connected machines for remote repositories, remote backup sources, and SSH restore destinations. |
| Infrastructure | Managed Agents | Enroll and manage Borg UI agents on remote machines. |
| Infrastructure | Cloud Storage | Configure reusable rclone remotes for Cloud Mirror targets and advanced direct Borg 2 rclone repository URLs. |
| Storage | Repositories | Create, import, inspect, maintain, and restore from Borg repositories. A repository is the storage target. |
| Backups | Backup Plans | Define what to back up, where it should go, when it should run, and what maintenance should run afterward. |
| Backups | Backup | Run older repository-based backups or legacy backup jobs. New workflows should usually start from Backup Plans. |
| Backups | Schedule | Review scheduled repository work, scheduled restore checks, and plan schedules from one operational view. |
| Backups | Archives | Browse archives, select files or folders, restore data, and run archive-level actions. |

## Settings

Settings are grouped so personal preferences stay separate from operational
administration.

### Personal

| Tab | Use it for |
| --- | --- |
| Account | Update profile details, password, passkeys, two-factor authentication, and account security. |
| Users | Manage users and repository access. This appears for accounts that can manage users. |
| Appearance | Choose theme and display preferences. |
| Preferences | Set personal UI behavior and default preferences. |
| Notifications | Configure backup, restore, schedule, check, and report notifications. |

### System

| Tab | Use it for |
| --- | --- |
| Licensing | Manage license status and plan-gated capabilities. |
| System | Configure runtime settings, backup health thresholds, timeouts, and maintenance controls. |
| Monitoring & Reports | Configure backup reports, monitoring behavior, and recent activity included in reports. |
| MQTT | Configure MQTT and Home Assistant integration. This appears when MQTT is enabled. |
| Cache | Configure Redis/cache behavior and clear cache entries when needed. |
| Logs | Review log storage and cleanup controls. |
| Packages | Install or inspect optional runtime packages when package management is available. |

### Management

| Tab | Use it for |
| --- | --- |
| Mounts | Manage archive mount points and mount-related operations. |
| Scripts | Manage reusable scripts for pre-backup, post-backup, and operational hooks. |
| Export/Import | Export Borg UI configuration or import supported configuration data. |

### Advanced

| Tab | Use it for |
| --- | --- |
| Beta | Enable or disable the beta features that still require an admin switch. |

## Where To Go Next

- For a first backup, continue with the [Usage Guide](usage-guide#create-a-backup-plan).
- For Borg UI instances on other machines, see [Remote Clients](remote-clients).
- For SSH targets or remote sources, see [Remote Machines](ssh-keys).
- For notification setup, see [Notifications](notifications).
