"""Operation vocabulary. Single source of truth for kinds, categories,
statuses, triggers, and priorities (spec section 6.3). The frontend mirror
lands in phase 3 at frontend/src/types/operations.ts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class KindSpec:
    category: str
    exclusive: bool


KINDS: dict[str, KindSpec] = {
    "import_connect": KindSpec("import", False),
    "backup": KindSpec("backup", True),
    "restore": KindSpec("restore", False),
    "restore_check": KindSpec("restore", False),
    "check": KindSpec("maintenance", True),
    "prune": KindSpec("maintenance", True),
    "compact": KindSpec("maintenance", True),
    "delete_archive": KindSpec("maintenance", True),
    "wipe": KindSpec("maintenance", True),
    "rclone_sync": KindSpec("mirror", False),
    "package_install": KindSpec("system", False),
    "stats": KindSpec("index", False),
    "archive_sync": KindSpec("index", False),
    "history_index": KindSpec("index", True),
    "history_merge": KindSpec("index", False),
}

CATEGORIES: tuple[str, ...] = (
    "import",
    "backup",
    "restore",
    "maintenance",
    "index",
    "mirror",
    "system",
)

STATUSES: tuple[str, ...] = (
    "queued",
    "running",
    "completed",
    "completed_with_warnings",
    "failed",
    "cancelled",
    "skipped",
)

TRIGGERS: tuple[str, ...] = (
    "manual",
    "schedule",
    "plan",
    "import",
    "followup",
    "reconcile",
    "retry",
)

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "completed_with_warnings", "failed", "cancelled", "skipped"}
)
SUCCESS_STATUSES: frozenset[str] = frozenset({"completed", "completed_with_warnings"})
INDEX_KINDS: frozenset[str] = frozenset(
    {"stats", "archive_sync", "history_index", "history_merge"}
)

PRIORITY_MANUAL = 0
PRIORITY_SCHEDULE = 5
PRIORITY_FOLLOWUP = 10
PRIORITY_RECONCILE = 20

_PRIORITY_BY_TRIGGER = {
    "manual": PRIORITY_MANUAL,
    "plan": PRIORITY_MANUAL,
    "import": PRIORITY_MANUAL,
    "retry": PRIORITY_MANUAL,
    "schedule": PRIORITY_SCHEDULE,
    "followup": PRIORITY_FOLLOWUP,
    "reconcile": PRIORITY_RECONCILE,
}

LEGACY_STATUS_MAP: dict[str, str] = {
    "pending": "queued",
    "needs_backup": "skipped",
    "running_prune": "running",
    "running_compact": "running",
    "prune_failed": "failed",
    "compact_failed": "failed",
}


def validate_kind(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"Unknown operation kind: {kind!r}")
    return kind


def validate_status(status: str) -> str:
    if status not in STATUSES:
        raise ValueError(f"Unknown operation status: {status!r}")
    return status


def validate_trigger(trigger: str) -> str:
    if trigger not in TRIGGERS:
        raise ValueError(f"Unknown operation trigger: {trigger!r}")
    return trigger


def category_for(kind: str) -> str:
    return KINDS[validate_kind(kind)].category


def is_exclusive(kind: str) -> bool:
    return KINDS[validate_kind(kind)].exclusive


def priority_for_trigger(trigger: str) -> int:
    return _PRIORITY_BY_TRIGGER[validate_trigger(trigger)]
