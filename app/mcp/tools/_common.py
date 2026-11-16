"""Small helpers shared by the tool modules."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

GLYPH = {"healthy": "✓", "warning": "⚠", "critical": "✗"}
STATUS_GLYPH = {
    "completed": "✓",
    "completed_with_warnings": "⚠",
    "failed": "✗",
    "cancelled": "✗",
    "running": "⏳",
    "queued": "⏳",
    "pending": "⏳",
}
JOB_LABEL = {
    "backup": "Backup",
    "check": "Check",
    "compact": "Compact",
    "prune": "Prune",
    "restore": "Restore",
    "restore_check": "Restore check",
    "archive_delete": "Archive delete",
    "delete": "Archive delete",
    "archive_sync": "Archive sync",
}


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def plural(count: int, word: str, many: str | None = None) -> str:
    return f"{count} {word if count == 1 else (many or word + 's')}"


def job_label(kind: str | None) -> str:
    return JOB_LABEL.get(kind or "", (kind or "job").replace("_", " ").capitalize())
