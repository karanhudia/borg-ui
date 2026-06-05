"""Shared helpers for job log visibility policies."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.models import ScriptExecution, SystemSettings

DEFAULT_LOG_SAVE_POLICY = "failed_and_warnings"
VALID_LOG_SAVE_POLICIES = {"failed_only", "failed_and_warnings", "all_jobs"}


def get_log_save_policy(db: Session) -> str:
    settings = db.query(SystemSettings).first()
    policy = getattr(settings, "log_save_policy", None)
    if policy in VALID_LOG_SAVE_POLICIES:
        return str(policy)
    return DEFAULT_LOG_SAVE_POLICY


def script_execution_has_logs(
    execution: ScriptExecution, *, log_save_policy: str
) -> bool:
    status = execution.status or ""
    if status == "pending":
        return False

    failed = bool(
        status in {"failed", "cancelled"}
        or (execution.exit_code is not None and execution.exit_code != 0)
        or execution.error_message
    )
    if log_save_policy == "failed_only":
        return failed

    if log_save_policy == "all_jobs":
        return True

    output = "\n".join(
        part
        for part in [execution.stdout, execution.stderr, execution.error_message]
        if part
    ).lower()
    has_warning_or_error = "warning" in output or "error" in output
    return failed or has_warning_or_error
