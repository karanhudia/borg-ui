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
start authorization from Borg UI, complete the provider login, return to Borg UI,
and save the remote after the dialog detects the server-side token result.
Provider credentials are saved in the dialog; provider secrets and Borg
UI-owned access/refresh tokens are not exposed in ordinary browser responses. For
OneDrive, Borg UI also records the default Microsoft Graph drive ID and drive
type returned for the signed-in account. Enter a specific drive ID manually when
targeting a SharePoint document library or another non-default drive.

### Google Drive OAuth Setup

For a self-hosted Borg UI at `https://borg.example.com`, use these steps:

1. Set `PUBLIC_BASE_URL=https://borg.example.com` on the Borg UI backend or
   container. If Borg UI is served under a sub-path, include it.
2. In Google Cloud Console, create or select a project and enable the Google
   Drive API.
3. Configure the OAuth consent screen. While the app is in testing, add the
   Google accounts that should be allowed to authorize Drive access as test
   users.
4. Create an OAuth client of type **Web application** and add this authorized
   redirect URI:

   ```text
   https://borg.example.com/api/rclone/oauth/callback/drive
   ```

5. In Borg UI, open **Cloud Storage**, choose **Add remote**, select
   **Google Drive**, and paste the OAuth client ID and client secret into
   **Provider OAuth app**.
6. Save the credentials, start Borg UI OAuth, complete Google's sign-in page,
   then return to the Borg UI dialog. The dialog checks authorization
   automatically; save the remote when the token is ready.

If Borg UI-owned OAuth is not configured, or if you are using providers such as
Dropbox or Box, Cloud Storage keeps the rclone loopback/manual authorization
path available for advanced setups. Access-key providers such as S3,
Backblaze B2, and Azure Blob store their keys in Borg UI's server-managed
`rclone.conf` and return redacted values through the API.

OAuth access-token expiry is controlled by the provider. Cloud Storage shows
token status, expiry, and refresh-token availability for managed OAuth remotes;
rclone refreshes access when the provider issued a refresh token.

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
segment is part of the hosted SSH path Borg uses for that repository. The
repository name may appear as `repo` in BorgBase, but Borg UI should receive the
path form from the SSH URL.

BorgBase **SFTP Access** is not required for this flow. Borg UI uses the Borg
repository over SSH with the public key you authorize in BorgBase.

Typical flow:

1. In Borg UI, go to Remote Machines and create or import the system SSH key.
   Copy the full public key value.
2. In BorgBase, add that public key under SSH Keys and remember the key name.
3. Create or select the BorgBase repository. Grant the key full access, leave
   SFTP Access disabled, and copy the SSH repository URL.
4. Add a manual Remote Machine in Borg UI using the host, username, port, and
   default path from the BorgBase URL.
5. Create a full remote repository or use Import Existing. Select Remote Client,
   choose the SSH connection, and enter the same repository path from the URL.
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
Default path: /home
Repository path: /./borg-repository
Remote Borg Path: borg-1.4, when you need Hetzner's Borg 1.4 binary
```

Use `/home` as the Remote Machine default path for Storage Box browsing and
key deployment. Keep the `./` path segment in the repository path, and use the
sub-account username and host when the Storage Box uses a sub-account. Leave
Remote Borg Path blank when Hetzner's default Borg version is correct for the
repository.

If Borg UI needs to install the public key for a Storage Box, enable SFTP
deployment mode on the Remote Machine. Hetzner's port 23 key format is the
normal one-line OpenSSH public key format.

## Other Hosted Borg Providers

Hosted Borg providers often use SSH URLs with provider-specific path syntax, for
example a `./` segment or a path relative to a restricted account. Keep that
syntax when entering repository paths, and only use it as the Remote Machine
default path when the provider exposes the same path for browsing.

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
