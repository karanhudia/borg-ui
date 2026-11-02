"""Bounded, redacted causal hints for restore failures.

Keep translation keys stable while retaining the Borg cause in structured params,
which the operation API and failure reporter already carry.
"""

import json

from app.utils.redaction import redact_secrets


def restore_diagnostic(output: str) -> str:
    messages = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            messages.append(line)
            continue
        if not isinstance(record, dict):
            continue
        # Progress and informational JSON records are not the cause. Borg's
        # --log-json warnings/errors carry their human description in message.
        if record.get("type") == "log_message" and record.get("levelname") in (
            "WARNING",
            "ERROR",
            "CRITICAL",
        ):
            message = record.get("message")
            if isinstance(message, str) and message.strip():
                messages.append(message.strip())
    diagnostic = redact_secrets("\n".join(messages[-5:])) or ""
    if len(diagnostic) > 1000:
        marker = "\n... [truncated] ...\n"
        diagnostic = diagnostic[:200] + marker + diagnostic[-(800 - len(marker)) :]
    return diagnostic


def restore_error_detail(
    key: str, output: str, *, exit_code: int | None = None
) -> dict:
    params = {}
    if exit_code is not None:
        params["exitCode"] = exit_code
    diagnostic = restore_diagnostic(output)
    if diagnostic:
        params["error"] = diagnostic
        if key in (
            "restoreFailedZeroFiles",
            "restoreFailedZeroFilesPermission",
            "restoreFailedZeroFilesPathNotFound",
            "restoreFailedExitCode",
            "restoreFailed",
        ):
            # New keys leave previously stored errors without params.error
            # readable; only hints we actually have request interpolation.
            key += "Details"
    detail = {"key": f"backend.errors.service.{key}"}
    if params:
        detail["params"] = params
    return detail


def zero_file_restore_detail(exit_code: int, output: str) -> dict:
    diagnostic = restore_diagnostic(output)
    if exit_code == 105 or "permission denied" in diagnostic.lower():
        key = "restoreFailedZeroFilesPermission"
    elif exit_code == 107 or "no such file" in diagnostic.lower():
        key = "restoreFailedZeroFilesPathNotFound"
    elif not diagnostic:
        key = "restoreFailedZeroFilesNoOutput"
    else:
        key = "restoreFailedZeroFiles"
    return restore_error_detail(key, output, exit_code=exit_code)
