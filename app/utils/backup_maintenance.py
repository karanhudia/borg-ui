"""Shared backup maintenance status constants."""

COMPLETED_BACKUP_STATUSES = {"completed", "completed_with_warnings"}

RUNNING_BACKUP_MAINTENANCE_FAILURES = {
    "running_prune": "prune_failed",
    "running_compact": "compact_failed",
    "running_check": "check_failed",
}

# The maintenance word a backup carries while its post-backup step runs, and
# the kind of the child operation running it (spec 6.3).
MAINTENANCE_STATUS_KIND = {
    "running_prune": "prune",
    "running_compact": "compact",
    "running_check": "check",
}
