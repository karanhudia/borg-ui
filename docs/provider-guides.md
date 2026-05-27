---
title: Provider Guides
nav_order: 5
description: "Use Borg UI with BorgBase, hosted Borg services, NAS devices, and existing Borg repositories"
---

# Provider Guides

Borg UI manages Borg repositories and backup workflows. It does not replace the
storage provider. Use the path below that matches where your repository already
lives or where you want new archives to be stored.

| Setup | Use in Borg UI |
| --- | --- |
| Local disk or mounted share | Mount the host path into the Borg UI container and use the container path. |
| NAS or Linux server over SSH | Add a Remote Machine, then create or import an SSH repository. |
| Hosted Borg service | Add the provider as a Remote Machine and keep the provider's repository path exactly as given. |
| Existing Borg repository | Use Import Existing. Choose Full mode if Borg UI should run backups, or Observability-only if another tool already writes archives. |

## BorgBase

BorgBase repositories are SSH repositories, but they are not normal servers with
a general-purpose filesystem. BorgBase repository URLs commonly look like this:

```text
ssh://abcd@abcd.repo.borgbase.com/./repo
```

Map that URL into Borg UI like this:

```text
Host: abcd.repo.borgbase.com
Port: 22
Username: abcd
Default path: /./repo
Repository path: /./repo
```

Keep the `/./repo` path from BorgBase. Do not shorten it to `/repo`; the `./`
segment is part of the hosted SSH path Borg uses for that repository.

Typical flow:

1. Create or import the Borg UI system SSH key.
2. Add the Borg UI public key to BorgBase.
3. Create or select the repository in BorgBase.
4. Add a Remote Machine in Borg UI using the host, username, port, and default path from the BorgBase URL.
5. Create a remote repository or use Import Existing with the same repository path.
6. Save, then verify that archives can be listed or that repository creation succeeds.

## Other Hosted Borg Providers

Hosted Borg providers often use SSH URLs with provider-specific path syntax, for
example a `./` segment or a path relative to a restricted account. Keep that
syntax when entering the Remote Machine default path and repository path.

If verification fails:

- compare the provider's full SSH URL with the host, username, port, and path in Borg UI
- preserve any `./` path segment from the provider URL
- confirm the Borg UI public key is authorized by the provider
- use Import Existing when the repository was created outside Borg UI

## Existing Scripts or Cron Backups

If scripts, cron, or another backup tool already writes to a Borg repository,
import the repository instead of recreating it.

Use Full mode when Borg UI should take over backup runs and schedules. Use
Observability-only mode when Borg UI should browse archives, restore files, run
checks, and show health without writing new backup archives.
