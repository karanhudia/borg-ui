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

## Not a Full Backup

Export/import is useful for migration and interoperability. It is not a replacement for backing up `/data`.

For full Borg UI recovery, back up `/data` and see [Disaster Recovery](disaster-recovery).

## Related

- [Configuration](configuration)
- [Disaster Recovery](disaster-recovery)
