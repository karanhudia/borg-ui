---
title: Export and Import
description: "Export Borg UI configuration to borgmatic YAML and import borgmatic configs"
---

# Export and Import

Borg UI can export repository configuration to borgmatic-compatible YAML and import borgmatic YAML back into Borg UI.

Open:

```text
Settings > Management > Export/Import
```

## Export

Exports can include:

- selected repositories or all repositories
- source directories
- repository paths
- exclude patterns
- compression
- repository passphrases, when stored
- retention settings from a matching backup schedule, when selected

A single repository exports as a YAML file. Multiple repositories export as a ZIP file with one YAML file per repository.

Treat exports as sensitive. They can contain repository paths and stored passphrases.

### Automated Export

For unattended backups, run the export command from an environment that has the
same Borg UI database settings as the app, such as inside the Borg UI container:

```bash
python3 -m app.scripts.export_config --output /data/config-exports/borg-ui-config.export
```

By default, the command exports all repositories and includes schedule-derived
retention settings. A single repository export is YAML. Multiple repository
exports are ZIP files containing one YAML file per repository.

Export selected repositories by repeating `--repository-id`:

```bash
python3 -m app.scripts.export_config \
  --repository-id 1 \
  --repository-id 2 \
  --output /data/config-exports/selected-borg-ui-config.zip
```

Exclude schedule-derived retention settings when you only want repository
configuration:

```bash
python3 -m app.scripts.export_config --no-schedules --output /data/config-exports/repositories.export
```

Write the artifact to stdout when a backup script should choose the destination:

```bash
python3 -m app.scripts.export_config --output - > /backup/borg-ui-config.export
```

## Import

Imports accept:

- `.yaml`
- `.yml`
- `.zip` files containing YAML configs

Borg UI supports standard borgmatic config files and Borg UI exports.

Conflict options:

| Option | Behavior |
| --- | --- |
| Skip duplicates | Keep existing repositories and skip duplicates |
| Replace | Update matching repositories |
| Rename | Create imported repositories with new names when needed |

After import, verify repository paths, secrets, retention, any created schedules, and SSH settings before relying on the imported config.

Borgmatic YAML does not preserve exact Borg UI schedule timing. If retention settings create a schedule during import, review its cron expression, timezone, archive template, prune, and compact settings.

SSH repositories imported from borgmatic may need their remote machine connection configured manually in Borg UI.

### Borg 1 or Borg 2

A borgmatic config does not say which Borg it runs. The import reads it from each repository entry and records the repository as Borg 2 when the entry has one of:

- a URL only Borg 2 can open: `sftp://`, `http://`, `https://`, `s3:`, `b2:`, `rclone:`
- a Borg 2 `encryption`: `aes256-ocb`, `chacha20-poly1305`, `authenticated-sha256`, or Borg UI's `repokey-aes-ocb`, `keyfile-aes-ocb`, `repokey-chacha20-poly1305`, `keyfile-chacha20-poly1305`
- `key_location` or `id_hash`, which borgmatic only supports with Borg 2
- `borg_ui_borg_version: 2`, which a Borg UI export writes for a Borg 2 repository

Anything else is imported as Borg 1. **Replace** never changes the Borg version of the repository it replaces: an entry that describes the other version is not imported (delete the repository and import it again). An entry whose hints disagree (for example a `b2:` URL with `encryption: repokey`, or `[user@]host:path`, which only Borg 1 reads as an SSH address, with a Borg 2 encryption) is not imported, nor is a `rest://` URL (Borg 2.0.0b25 replaced it by `ssh://`). Neither is an entry with the blake3 id hash (`authenticated-blake3`, `id_hash: blake3`): Borg UI has no encryption mode for it. The import summary names the reason. Borg 2 repositories need a plan that includes Borg 2.

A Borg UI export writes a Borg 2 repository in that form: the entry carries Borg 2's encryption name and, for a keyfile mode, `key_location: keyfile`. To import a Borg 2 repository with a local path or an `ssh://` URL from a borgmatic config of your own, write the entry the same way:

```yaml
repositories:
  - path: ssh://borg@backup.example.com/./repo
    encryption: aes256-ocb
```

## Not a Full Backup

Export/import is useful for migration and interoperability. It is not a replacement for backing up `/data`.

For full Borg UI recovery, back up `/data` and see [Disaster Recovery](disaster-recovery).

## Related

- [Configuration](configuration)
- [Disaster Recovery](disaster-recovery)
