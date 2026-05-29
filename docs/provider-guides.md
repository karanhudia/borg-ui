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
| NAS or Linux server over SSH | Add a Remote Machine, then create or import an SSH repository. See the NAS notes below when SSH and SFTP paths differ. |
| Hosted Borg service | Add the provider as a Remote Machine and keep the provider's repository path exactly as given. BorgBase and Hetzner need the most care. |
| Cloud or object storage through rclone | Add the provider in Cloud Storage, then select that reusable remote when configuring a cloud mirror. |
| Existing Borg repository | Use Import Existing. Choose Full mode if Borg UI should run backups, or Observability-only if another tool already writes archives. |

## Which Setups Need Provider Guidance?

| Environment | Guidance to use |
| --- | --- |
| BorgBase | Use the BorgBase mapping below because the `/./repo` path segment is part of the repository URL. |
| Hetzner Storage Box | Use the Hetzner mapping below because Borg access uses port 23, relative `./` paths, and sometimes a named remote Borg binary. |
| Synology DSM | Use the NAS mapping below when SFTP shows a share path but Borg needs the full `/volumeN/...` path. |
| Unraid | Use the NAS mapping below with one consistent share path, usually under `/mnt/user/<share>/...`. |
| Google Drive, OneDrive, Dropbox, Box, S3, B2, Azure Blob, WebDAV, SFTP | Use Cloud Storage and pick the matching rclone provider template. |
| Other hosted Borg providers | Preserve the host, port, username, and path exactly as the provider gives them. |

## Cloud Storage with rclone

Cloud Storage manages reusable rclone remotes. Open Cloud Storage, choose
**Add remote**, pick the provider, and review the provider-specific config
template before saving. Google Drive and OneDrive use Borg UI-owned OAuth
callbacks when `PUBLIC_BASE_URL` and provider client credentials are configured;
start authorization from Borg UI, complete the provider login, and check
authorization to add the returned token JSON to the managed config editor.
Provider secrets stay on the backend and are not exposed in the browser. For
OneDrive, Borg UI also records the default Microsoft Graph drive ID and drive
type returned for the signed-in account. Enter a specific drive ID manually when
targeting a SharePoint document library or another non-default drive.

If Borg UI-owned OAuth is not configured, or if you are using providers such as
Dropbox or Box, Cloud Storage keeps the rclone loopback/manual authorization
path available for advanced setups. Access-key providers such as S3,
Backblaze B2, and Azure Blob store their keys in Borg UI's server-managed
`rclone.conf` and return redacted values through the API.

Use **Custom rclone backend** when the provider is not listed. Keep the `type`
field set to the exact rclone backend name and add any provider-specific keys
from the rclone documentation.

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

## Hetzner Storage Box

Hetzner Storage Box repositories need explicit mapping because Borg access uses
the extended SSH service on port 23 and paths are usually written as relative
Storage Box paths. A repository URL can look like this:

```text
ssh://u123456@u123456.your-storagebox.de:23/./borg-repository
```

Map it into Borg UI like this:

```text
Host: u123456.your-storagebox.de
Port: 23
Username: u123456
Default path: /./borg-repository
Repository path: /./borg-repository
Remote Borg Path: borg-1.4, when you need Hetzner's Borg 1.4 binary
```

Keep the `./` path segment and use the sub-account username and host when the
Storage Box uses a sub-account. Leave Remote Borg Path blank when Hetzner's
default Borg version is correct for the repository.

If Borg UI needs to install the public key for a Storage Box, enable SFTP
deployment mode on the Remote Machine. Hetzner's port 23 key format is the
normal one-line OpenSSH public key format.

## Other Hosted Borg Providers

Hosted Borg providers often use SSH URLs with provider-specific path syntax, for
example a `./` segment or a path relative to a restricted account. Keep that
syntax when entering the Remote Machine default path and repository path.

If verification fails:

- compare the provider's full SSH URL with the host, username, port, and path in Borg UI
- preserve any `./` path segment from the provider URL
- confirm the Borg UI public key is authorized by the provider
- use Import Existing when the repository was created outside Borg UI

## Synology, Unraid, and Other NAS Targets

Synology, Unraid, and similar NAS setups usually do not need separate provider
pages. They do need careful path mapping when the path shown by browsing is not
the exact path Borg needs over SSH.

Use this general mapping:

```text
Host: nas.example.com
Port: 22, or your custom SSH port
Username: the NAS user that can run Borg and access the repository path
Default path: the path Borg UI should browse first
Repository path: the Borg repository path in that same browsing namespace
```

For Synology, SFTP browsing may show a share path such as `/backups/repo` while
Borg needs `/volume1/backups/repo` over SSH. Configure the Remote Machine SSH
path prefix, for example `/volume1`, and keep the repository path as
`/backups/repo`. See [Remote Machines](ssh-keys#synology-and-nas-path-prefixes)
for the path-prefix model.

For Unraid, choose one path style and keep it consistent. User shares commonly
live under `/mnt/user`, for example:

```text
Repository path: /mnt/user/backups/borg-repository
```

Avoid mixing `/mnt/user/...` paths with `/mnt/diskN/...` paths for the same
repository. Also confirm the SSH account can run Borg; share-only NAS users may
not have shell access.

## Existing Scripts or Cron Backups

If scripts, cron, or another backup tool already writes to a Borg repository,
import the repository instead of recreating it.

Use Full mode when Borg UI should take over backup runs and schedules. Use
Observability-only mode when Borg UI should browse archives, restore files, run
checks, and show health without writing new backup archives.
