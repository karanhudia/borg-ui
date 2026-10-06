"""One place that turns an HTTPException detail into what a background job
records. A validator refusal is `{"key", "params"}`; an API route hands it to
the frontend, which translates it with its params. Background callers store
it, so they must keep the params too."""

from typing import Any, Optional


def structured_detail(detail: Any) -> Optional[dict]:
    """The `{"key", "params"?}` of a translatable detail, else None."""
    if isinstance(detail, dict) and isinstance(detail.get("key"), str):
        out: dict = {"key": detail["key"]}
        if detail.get("params"):
            out["params"] = detail["params"]
        return out
    return None


def detail_text(detail: Any) -> str:
    """A detail as one line for a log or a text-only column: its message, or
    its key followed by its params. The admission's generic "repository busy"
    key says which operation holds the repository instead."""
    from app.services.job_admission import REPOSITORY_OPERATION_ACTIVE_KEY

    if isinstance(detail, dict):
        message = detail.get("message")
        if message:
            return str(message)
        key = detail.get("key")
        params = detail.get("params")
        active = params.get("active_operation") if isinstance(params, dict) else None
        if key == REPOSITORY_OPERATION_ACTIVE_KEY and active:
            return f"{active} is active on the repository"
        if key:
            if isinstance(params, dict) and params:
                shown = ", ".join(f"{k}={v}" for k, v in params.items())
                return f"{key} ({shown})"
            return str(key)
    return str(detail)
