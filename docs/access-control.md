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
| `operator` | Can operate repositories they have access to and use operator-level tools such as schedules and mounts |
| `admin` | Can manage users, settings, repositories, SSH, packages, scripts, logs, cache, and permissions |

Admins have access to every repository.

## Global Permissions

Current global permissions are:

| Capability | Required global role |
| --- | --- |
| Create, import, edit, and delete repositories | `admin` |
| Manage users and repository permissions | `admin` |
| Manage system, cache, logs, packages, SSH, scripts, export/import, beta, and MQTT settings | `admin` |
| View all activity across users | `admin` |
| Create, edit, run, duplicate, and delete schedules | `operator`, plus operator access to the schedule repositories |
| Mount and unmount Borg archives | `operator` |

## Repository Roles

| Role | Allows |
| --- | --- |
| `viewer` | View the repository, browse archives, restore files |
| `operator` | Everything viewer can do, plus run backups, maintenance, and archive deletion |

Repository roles are assigned per user.

Repository action rules are:

| Action | Required repository role |
| --- | --- |
| View repository and browse archives | `viewer` |
| Restore files | `viewer` |
| Run backups | `operator` |
| Run repository maintenance such as check, restore check, prune, and compact | `operator` |
| Delete archives | `operator` |

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

Current backend authentication still uses the normal login bearer token for API requests. Do not rely on generated API tokens as standalone API credentials until token authentication is wired through the backend.

## Related

- [Authentication and SSO](authentication)
- [Usage Guide](usage-guide)
- [Security](security)
