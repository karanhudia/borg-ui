---
title: Access Control
nav_order: 9
description: "RBAC, repository permissions, and API token management"
---

# Access Control

Borg UI uses global roles for app-wide permissions and repository roles for repository access.

## Global Roles

| Role | What it means |
| --- | --- |
| `viewer` | Can use repositories they have access to |
| `operator` | Can operate repositories they have access to and use operator-level tools such as schedules, mounts, and the local file browser |
| `admin` | Can manage users, settings, repositories, SSH, notifications, packages, scripts, logs, cache, and permissions |

Admins have access to every repository.

## Global Permissions

Current global permissions are:

| Capability | Required global role |
| --- | --- |
| Create, import, edit, and delete repositories | `admin` |
| Manage users and repository permissions | `admin` |
| Manually run backup freshness monitoring or send a backup health report | `admin` |
| Manage system, licensing, cache, logs, packages, SSH, scripts, notifications, export/import, beta, and MQTT settings | `admin` |
| Delete job history entries and associated log files | `admin` |
| Create, edit, run, duplicate, and delete schedules | `operator`, plus operator access to the schedule repositories |
| Mount and unmount Borg archives (new non-admin mount targets must resolve below `DATA_DIR/mounts`) | `operator` |
| Browse local paths and create folders (operators are limited to `LOCAL_MOUNT_POINTS`, admins are not) | `operator` |
| Discover databases and scan database or container sources | `operator` or `admin`, subject to the source restrictions below |
| Restore to a saved SSH connection | `operator` |

Activity and job history are visible to signed-in users. Admins can delete supported job entries and their log files.

Repository deletion and permanent deletion require the global `admin` role;
repository `operator` access, including all-repositories access, does not grant
either action. Listing users in Settings also requires `admin`. Manual monitoring
and report actions retain their feature entitlement checks in addition to the
administrator requirement.

## Source Discovery

Database discovery, database scans, and container scans require the global
`operator` or `admin` role. Viewers cannot use these endpoints.

Operators can scan local database paths only within `LOCAL_MOUNT_POINTS`.
Authorization checks resolve symlinks for roots, discovered directories, SQLite
files, and database marker paths before probing them. A link into an unapproved
path causes a `403` response. Local container scans also check the returned bind
mount and volume source paths before probing their backup sources or sizes.
Operators cannot scan databases or containers through a saved SSH connection;
those remote scans require `admin`.

The default database discovery request checks every engine's default scan path.
It can return `403` for an operator if any default path is outside the configured
local mounts, even when another default path would be allowed. An administrator
can run discovery, or an operator can submit an explicit database scan containing
only approved paths. Administrators are exempt from the discovery mount limits.
Database discovery and container backup feature entitlements still apply.

## Dashboard Visibility

Dashboard repository counts, storage totals, health rows, and repository job rows
follow the signed-in user's repository access. A schedule or backup plan linked
to multiple repositories is visible only when the user can view every linked
repository. This rule also applies to unresolved backup plan dispatch failures,
including failure messages. Administrators retain visibility across repositories.

Schedules, plans, and activity rows without a repository association can remain
visible as system rows. System metrics and global alerts also remain visible to
signed-in users.

## API Enforcement

API authorization applies independently of which controls the UI displays. The
route access registry documents the application's routes; runtime dependencies,
endpoint policies, and handler checks enforce access. The inventory check also
requires a matching role guard for routes declared `admin` or `operator`.

Some explicit dependency guards reinforce existing restrictions: rclone provider,
OAuth, and remote management; remote client proxying; script testing and orphan
cleanup; job history deletion; and Borg 2 repository creation/import and archive
deletion, prune, compact, and check operations already had administrator checks.
The additional guards preserve those policies. Download and proxy routes that
accept query tokens continue to authenticate the token owner's role.

## Repository Roles

| Role | Allows |
| --- | --- |
| `viewer` | View the repository and browse archives |
| `operator` | Everything viewer can do, plus restore files, run backups, maintenance, and archive deletion |

Repository roles are assigned per user.

Repository action rules are:

| Action | Required repository role |
| --- | --- |
| View repository and browse archives | `viewer` |
| Restore files (agent repositories require global `admin`) | `operator` |
| Run backups | `operator` |
| Run repository maintenance such as check, restore check, prune, and compact | `operator` |
| Delete archives | `operator` |

## Operator Path Restrictions

For non-admin users, newly selected server backup sources must be absolute,
contain no `..` segment, and resolve inside `LOCAL_MOUNT_POINTS`, including
symlink resolution. They must neither contain nor be inside `/app` or `DATA_DIR`.
These checks cover both source formats and new `R`/`r` backup roots in plan
`custom_flags` and repository-link `custom_flags_override`, including disabled
links. New agent sources and agent pattern roots require an administrator.

New database dump paths, container export paths, and btrfs staging directories
must be absolute, contain no `..`, and avoid the application and data directories
in both directions. They can be outside `LOCAL_MOUNT_POINTS`, so the defaults
under `/var/tmp/borg-ui` remain usable.

Restoring an agent repository requires a global administrator; operators receive
a permission error before a restore is queued. Server restores retain their
local mount-point restrictions. SSH destinations, restore checks, previews, and
archive downloads keep their existing access rules.

Existing plans keep their stored sources, metadata, and pattern roots and can
still run or have other fields edited. Copying an administrator-configured
repository's sources into a plan remains supported. A plan with no repositories
left has no trusted stored paths: every selected path is checked again.

See [Operator path restriction upgrades](security#operator-path-restriction-upgrades)
for the required administrator review and the limits of selection-time checks.

## All-Repositories Access

A user can also have an all-repositories role:

| All-repositories role | Meaning |
| --- | --- |
| empty | Only explicitly assigned repositories are available |
| `viewer` | Viewer access to every repository |
| `operator` | Operator access to every repository |

Explicit per-repository access can grant a specific repository to a restricted user, or upgrade one repository when all-repositories access is `viewer`.

A per-repository role does not reduce an all-repositories role. For example, if a user has all-repositories `operator`, adding `viewer` on one repository does not downgrade that repository.

The UI only offers repository roles that match the user's global role. Viewers are assigned repository `viewer`; operators can be assigned repository `viewer` or `operator`.

## Managing Access

Admins manage users and repository access from:

```text
Settings > Users
```

Open a user and choose repository access. Admins can:

- set the user's global role
- set all-repositories access
- grant access to one repository
- change a repository role
- remove repository access

Users can see their own access from:

```text
Settings > Account
```

## OIDC and Trusted Headers

OIDC and trusted-header auth can set:

- global role
- all-repositories role
- user identity fields such as username, email, and full name

For OIDC, template mode can copy roles and repository permissions from a template user when a new SSO user is created.

Admin role claims are only accepted when the user also matches the configured admin group allow-list.

## API Tokens

Users can generate and revoke API tokens from:

```text
Settings > Account
```

Generated tokens are shown once.

Manual API calls currently still use the bearer token from a normal login. Do
not rely on generated account tokens as standalone API credentials yet. See
[API](api) for the supported bearer-token flow and manual backup examples.

## Related

- [Authentication and SSO](authentication)
- [API](api)
- [Usage Guide](usage-guide)
- [Security](security)
