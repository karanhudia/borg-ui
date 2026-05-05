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
| `operator` | Can operate repositories they have access to, plus use operator-level tools such as schedules and mounts |
| `admin` | Can manage users, settings, repositories, SSH, packages, scripts, logs, cache, and permissions |

Admins have access to every repository.

## Repository Roles

| Role | Allows |
| --- | --- |
| `viewer` | View the repository, browse archives, restore files |
| `operator` | Everything viewer can do, plus run backups, maintenance, and archive deletion |

Repository roles are assigned per user.

## All-Repositories Access

A user can also have an all-repositories role:

| All-repositories role | Meaning |
| --- | --- |
| empty | Only explicitly assigned repositories are available |
| `viewer` | Viewer access to every repository |
| `operator` | Operator access to every repository |

Explicit per-repository access can grant a specific repository to a restricted user, or upgrade one repository when all-repositories access is `viewer`.

A per-repository role does not reduce an all-repositories role. For example, if a user has all-repositories `operator`, adding `viewer` on one repository does not downgrade that repository.

A user's repository role cannot be higher than their global role. Viewers can only receive repository `viewer`. Operators can receive repository `viewer` or `operator`.

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
