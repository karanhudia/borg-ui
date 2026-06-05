from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import SystemSettings

DEFAULT_LOG_SAVE_POLICY = "failed_and_warnings"
LOG_SAVE_POLICIES = {"failed_only", "failed_and_warnings", "all_jobs"}
PENDING_STATUSES = {"pending", "queued", "scheduled"}
RUNNING_STATUSES = {"running", "installing", "in_progress"}
FAILED_STATUSES = {"failed", "cancelled", "canceled"}
WARNING_STATUSES = {"completed_with_warnings"}
WARNING_MARKERS = ("warning", "error")


def get_log_save_policy(db: Session) -> str:
    settings = db.query(SystemSettings).first()
    policy = getattr(settings, "log_save_policy", None) if settings else None
    return policy if policy in LOG_SAVE_POLICIES else DEFAULT_LOG_SAVE_POLICY


def job_has_logs_by_policy(
    job: Any,
    log_save_policy: str,
    output_text: Any = None,
    file_path: str | None = None,
    status: str | None = None,
    exit_code: int | str | None = None,
) -> bool:
    job_status = _normalize_status(
        status if status is not None else getattr(job, "status", None)
    )
    if job_status in PENDING_STATUSES:
        return False

    resolved_exit_code = exit_code
    if resolved_exit_code is None:
        resolved_exit_code = getattr(job, "exit_code", None)

    has_source = _has_log_source(output_text=output_text, file_path=file_path)
    is_log_capable = job is not None
    if job_status in RUNNING_STATUSES:
        return has_source or is_log_capable

    policy = (
        log_save_policy
        if log_save_policy in LOG_SAVE_POLICIES
        else DEFAULT_LOG_SAVE_POLICY
    )
    has_failed = job_status in FAILED_STATUSES or _is_nonzero_exit(resolved_exit_code)

    if policy == "failed_only":
        return has_failed
    if policy == "failed_and_warnings":
        return (
            has_failed
            or job_status in WARNING_STATUSES
            or _has_warning_or_error_output(output_text)
        )
    if policy == "all_jobs":
        return has_source or is_log_capable

    return False


def _normalize_status(status: Any) -> str:
    return str(status or "").strip().lower()


def _is_nonzero_exit(exit_code: int | str | None) -> bool:
    if exit_code in (None, ""):
        return False
    try:
        return int(exit_code) != 0
    except (TypeError, ValueError):
        return True


def _has_log_source(*, output_text: Any, file_path: str | None) -> bool:
    return bool(file_path) or any(part.strip() for part in _text_parts(output_text))


def _has_warning_or_error_output(output_text: Any) -> bool:
    haystack = "\n".join(_text_parts(output_text)).lower()
    return any(marker in haystack for marker in WARNING_MARKERS)


def _text_parts(output_text: Any) -> list[str]:
    if output_text is None:
        return []
    if isinstance(output_text, str):
        return [output_text]
    if isinstance(output_text, Iterable):
        return [str(part) for part in output_text if part is not None]
    return [str(output_text)]
