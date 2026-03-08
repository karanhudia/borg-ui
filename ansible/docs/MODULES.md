# Module Reference — borgui.borg_ui

## borg_ui_repository

Manage backup repositories in borg-ui.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `base_url` | str | yes | | Base URL of borg-ui instance |
| `token` | str | no | | JWT Bearer token (no_log) |
| `secret_key` | str | no | | SECRET_KEY to mint JWT (no_log) |
| `secret_key_file` | path | no | | File containing SECRET_KEY |
| `username` | str | no | admin | JWT embed username |
| `insecure` | bool | no | false | Skip TLS verify |
| `name` | str | yes | | Repository name (identity key) |
| `path` | str | no* | | Filesystem path (*required when present) |
| `encryption` | str | no | repokey | Encryption mode |
| `compression` | str | no | auto,lz4 | Compression mode |
| `source_directories` | list | no | [] | Directories to back up |
| `exclude_patterns` | list | no | [] | Glob patterns to exclude |
| `pre_backup_script` | str | no | | Shell script run before backup |
| `post_backup_script` | str | no | | Shell script run after backup |
| `hook_timeout` | int | no | 300 | Overall hook timeout (s) |
| `pre_hook_timeout` | int | no | 300 | Pre-backup hook timeout (s) |
| `post_hook_timeout` | int | no | 300 | Post-backup hook timeout (s) |
| `continue_on_hook_failure` | bool | no | false | Continue backup if hook fails |
| `mode` | str | no | full | `full` or `partial` |
| `bypass_lock` | bool | no | false | Bypass borg lock on backup |
| `custom_flags` | str | no | | Extra flags passed to borg |
| `source_connection_id` | int | no | | SSH connection ID for source |
| `passphrase` | str | no | | Borg passphrase (create only, no_log) |
| `state` | str | no | present | `present` or `absent` |
| `cascade` | bool | no | false | Remove dependent schedules on delete |

**Returns**: `changed`, `diff`, `repository`

**Deletion safety**: With `cascade: false` (default), deletion fails if schedules reference this repository and lists them. With `cascade: true`, removes the repository from all referencing schedules first (deletes the schedule if it becomes empty).

---

## borg_ui_schedule

Manage scheduled backup jobs in borg-ui.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `base_url` | str | yes | | |
| `token` / `secret_key` / `secret_key_file` | str | one required | | Auth |
| `name` | str | yes | | Job name (identity key) |
| `cron_expression` | str | no* | | Cron schedule (*required when present) |
| `enabled` | bool | no | true | |
| `description` | str | no | | Human-readable description |
| `repositories` | list | no | [] | List of repository **names** (resolved to IDs) |
| `run_prune_after` | bool | no | false | |
| `run_compact_after` | bool | no | false | |
| `prune_keep_daily` | int | no | 7 | |
| `prune_keep_weekly` | int | no | 4 | |
| `prune_keep_monthly` | int | no | 6 | |
| `prune_keep_yearly` | int | no | 1 | |
| `prune_keep_hourly` | int | no | 0 | |
| `prune_keep_quarterly` | int | no | 0 | |
| `state` | str | no | present | `present` or `absent` |

**Returns**: `changed`, `diff`, `schedule`

---

## borg_ui_connection

Manage SSH connections in borg-ui.

> **Note**: SSH connections are created via the borg-ui UI or the `quick-setup` API endpoint.
> This module manages the attributes of existing connections.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `base_url` | str | yes | | |
| `token` / `secret_key` / `secret_key_file` | str | one required | | Auth |
| `api_username` | str | no | admin | JWT embed username (API user) |
| `host` | str | yes | | SSH server hostname (identity) |
| `ssh_username` | str | yes | | SSH login username (identity) |
| `port` | int | no | 22 | SSH port (identity) |
| `use_sftp_mode` | bool | no | false | |
| `default_path` | str | no | | Default path on remote host |
| `ssh_path_prefix` | str | no | | SSH path prefix |
| `mount_point` | str | no | | Mount point |
| `state` | str | no | present | `present` or `absent` |
| `cascade` | bool | no | false | Ignored — server handles FK cleanup |

**Identity key**: `host` + `ssh_username` + `port`

**Returns**: `changed`, `diff`, `connection`

---

## borg_ui_notification

Manage Apprise notification channels in borg-ui.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `base_url` | str | yes | | |
| `token` / `secret_key` / `secret_key_file` | str | one required | | Auth |
| `api_username` | str | no | admin | |
| `name` | str | yes | | Channel name (identity key) |
| `service_url` | str | no* | | Apprise URL (no_log; *required when present) |
| `enabled` | bool | no | true | |
| `title_prefix` | str | no | | Optional notification title prefix |
| `include_job_name_in_title` | bool | no | false | |
| `notify_on_backup_start` | bool | no | false | |
| `notify_on_backup_success` | bool | no | false | |
| `notify_on_backup_failure` | bool | no | true | |
| `notify_on_restore_success` | bool | no | false | |
| `notify_on_restore_failure` | bool | no | true | |
| `notify_on_check_success` | bool | no | false | |
| `notify_on_check_failure` | bool | no | true | |
| `notify_on_schedule_failure` | bool | no | true | |
| `monitor_all_repositories` | bool | no | true | |
| `repository_ids` | list | no | | Specific repo IDs (when monitor_all=false) |
| `state` | str | no | present | `present` or `absent` |

**Returns**: `changed`, `diff`, `notification`

---

## borg_ui_backup

Trigger, monitor, or cancel backup runs. **Not idempotent by design.**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `base_url` | str | yes | | |
| `token` / `secret_key` / `secret_key_file` | str | one required | | Auth |
| `api_username` | str | no | admin | |
| `repository` | str | no* | | Repository name (*required for action=start) |
| `action` | str | yes | | `start`, `status`, or `cancel` |
| `job_id` | int | no* | | Job ID (*required for status/cancel) |
| `wait` | bool | no | false | Wait for completion (start only) |
| `wait_timeout` | int | no | 3600 | Seconds to wait |
| `poll_interval` | int | no | 5 | Seconds between status polls |

**Returns**: `changed`, `job_id`, `status`, `message`, `logs`, `progress_details`

**check_mode**: Returns `changed=True` without starting the backup.
