"""Shared backup maintenance status constants."""

COMPLETED_BACKUP_STATUSES = {"completed", "completed_with_warnings"}

RUNNING_BACKUP_MAINTENANCE_FAILURES = {
    "running_prune": "prune_failed",
    "running_compact": "compact_failed",
    "running_check": "check_failed",
}
