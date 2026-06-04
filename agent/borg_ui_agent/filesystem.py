from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from agent.borg_ui_agent.backup import BackupExecutionResult
from agent.borg_ui_agent.client import AgentClient


class FilesystemBrowseError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)

    def to_result(self) -> dict[str, Any]:
        return {"success": False, "error": {"code": self.code, "message": self.message}}


def browse_filesystem(path: str, *, include_hidden: bool = False) -> dict[str, Any]:
    requested = Path(path or "/").expanduser()
    try:
        current = requested.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FilesystemBrowseError("missing", f"Path not found: {requested}") from exc
    except PermissionError as exc:
        raise FilesystemBrowseError(
            "unreadable", f"Path is not readable: {requested}"
        ) from exc

    if not current.is_dir():
        raise FilesystemBrowseError(
            "not_directory", f"Path is not a directory: {current}"
        )

    items: list[dict[str, Any]] = []
    try:
        for entry in current.iterdir():
            hidden = entry.name.startswith(".")
            if hidden and not include_hidden:
                continue
            try:
                stat = entry.stat()
                is_dir = entry.is_dir()
            except OSError:
                continue
            items.append(
                {
                    "name": entry.name,
                    "path": str(entry),
                    "type": "directory" if is_dir else "file",
                    "size": stat.st_size,
                    "modified_at": stat.st_mtime,
                    "hidden": hidden,
                }
            )
    except PermissionError as exc:
        raise FilesystemBrowseError(
            "unreadable", f"Path is not readable: {current}"
        ) from exc

    items.sort(key=lambda item: (item["type"] != "directory", item["name"].lower()))
    parent = current.parent if current.parent != current else None
    return {
        "success": True,
        "current_path": str(current),
        "parent_path": str(parent) if parent else None,
        "items": items,
    }


def execute_filesystem_browse_job(
    job: dict[str, Any],
    client: AgentClient,
    *,
    should_cancel: Optional[object] = None,
) -> BackupExecutionResult:
    job_id = int(job["id"])
    payload = job.get("payload") or {}
    browse_payload = payload.get("filesystem") or payload
    path = str(browse_payload.get("path") or "/")
    include_hidden = bool(browse_payload.get("include_hidden", False))

    try:
        result = browse_filesystem(path, include_hidden=include_hidden)
    except FilesystemBrowseError as exc:
        client.fail_job(job_id, error_message=exc.message)
        return BackupExecutionResult(
            job_id=job_id, status="failed", message=exc.message
        )
    except Exception as exc:
        message = f"Filesystem browse failed: {exc}"
        client.fail_job(job_id, error_message=message)
        return BackupExecutionResult(job_id=job_id, status="failed", message=message)

    client.complete_job(job_id, result=result)
    return BackupExecutionResult(
        job_id=job_id, status="completed", message="browse complete"
    )
