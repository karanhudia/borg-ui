"""Typed helpers over Operation rows."""

from typing import Optional

from app.database.models import Operation
from app.services.operations.vocab import SUCCESS_STATUSES, TERMINAL_STATUSES


def is_terminal(op: Operation) -> bool:
    return op.status in TERMINAL_STATUSES


def is_success(op: Operation) -> bool:
    return op.status in SUCCESS_STATUSES


def serialize_operation(
    op: Operation,
    *,
    repository_name: Optional[str] = None,
    repository_path: Optional[str] = None,
    has_logs: bool = False,
    followups: Optional[list[dict]] = None,
) -> dict:
    """Return the OperationItem dict (a superset of ActivityItem, spec 9.1)."""
    params = op.params or {}
    return {
        "activity_key": f"operation:{op.id}",
        "id": op.id,
        "type": op.kind,
        "kind": op.kind,
        "category": op.category,
        "status": op.status,
        "trigger": op.trigger,
        "priority": op.priority,
        "run_id": op.run_id,
        "depends_on_id": op.depends_on_id,
        "repository_id": op.repository_id,
        "repository": repository_name,
        "repository_path": repository_path,
        "started_at": op.started_at,
        "completed_at": op.completed_at,
        "created_at": op.created_at,
        "error_message": op.error_message,
        "skip_reason": op.skip_reason,
        "log_file_path": op.log_file_path,
        "triggered_by": "schedule" if op.trigger == "schedule" else "manual",
        "schedule_id": op.scheduled_job_id,
        "schedule_name": None,
        "backup_plan_id": None,
        "backup_plan_run_id": op.backup_plan_run_id,
        "backup_plan_name": None,
        "archive_name": params.get("archive_name"),
        "package_name": None,
        "has_logs": has_logs,
        "progress_percent": op.progress_percent,
        "progress_current": op.progress_current,
        "progress_total": op.progress_total,
        "progress_message": op.progress_message,
        "execution_mode": op.execution_mode,
        "params": op.params,
        "result": op.result,
        "followups": list(followups or []),
    }
