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
