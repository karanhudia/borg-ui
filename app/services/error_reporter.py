"""Sends `Error - Report` analytics events for backend errors.

The fingerprint, normalization and scrubbing rules are shared with the
frontend (`frontend/src/utils/errorReporting.ts`): change both together, or the
same error splits into two rows. The fingerprint's message is scrubbed before it
is normalized: FNV is unkeyed, so a short secret could be brute-forced from it. The regexes stay within what JavaScript
supports for that reason.

Nothing here may raise into a caller or block it: the caller only builds the
event and enqueues it; the database read and the HTTP post happen on one
daemon thread.

ponytail: jobs outside the operations runner (older `backup_service` paths)
report only through their unhandled exceptions; add their failure points if
the Errors tab shows them missing.
"""

from __future__ import annotations

import hashlib
import json
import queue
import re
import threading
import time
import traceback
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

import requests

from app.config import get_runtime_app_version, settings
from app.database.database import SessionLocal
from app.database.models import LicensingState, User
from app.utils.redaction import redact_secrets

BackendErrorKind = Literal["request", "startup", "migration", "job"]

ENDPOINT = "https://t.borgui.com/e"
EVENT_NAME = "Error - Report"
MESSAGE_LIMIT = 500
STACK_LIMIT = 8192
PROPS_LIMIT = 16384
REPEAT_WINDOW = 600.0
HOURLY_CAP = 30
CONSENT_TTL = 60.0

_APP_DIR = Path(__file__).resolve().parents[1]
_SESSION_KEY = uuid.uuid4().hex

_FNV_OFFSET = 0xCBF29CE484222325
_FNV_PRIME = 0x100000001B3
_MASK64 = 0xFFFFFFFFFFFFFFFF


def fnv1a64(text: str) -> str:
    h = _FNV_OFFSET
    for byte in text.encode("utf-8"):
        h = ((h ^ byte) * _FNV_PRIME) & _MASK64
    return f"{h:016x}"


_NORMALIZE = [
    (
        re.compile(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
        ),
        "<uuid>",
    ),
    (re.compile(r"\b0[xX][0-9a-fA-F]+\b"), "<hex>"),
    (re.compile(r"\b[0-9a-fA-F]{8,}\b"), "<hex>"),
    (re.compile(r"'[^']*'|\"[^\"]*\""), "<str>"),
    (re.compile(r"(^|[^\w.])(?:[A-Za-z]:\\|/(?=[^\s/]))[^\s,;)]*"), r"\1<path>"),
    (re.compile(r"\b\d+\b"), "<n>"),
]

# Translation keys identify the failure; quoted paths and other params do not.
# Match JSON and Python dict reprs (HTTPException messages use the latter).
_STRUCTURED_ERROR_KEY = re.compile(
    r"""(['"])key\1\s*:\s*(['"])(backend\.errors\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\2"""
)


def normalize_message(message: str) -> str:
    message = _STRUCTURED_ERROR_KEY.sub(lambda match: f"key: {match[3]}", message)
    for pattern, replacement in _NORMALIZE:
        message = pattern.sub(replacement, message)
    return message


_SCRUB = [
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z ]*PRIVATE KEY-----|$)"
        ),
        "[redacted]",
    ),
    # rclone config lines: the value runs to the end of the line (tokens are JSON)
    (
        re.compile(
            r"^([ \t]*(?:pass|password|token|secret_access_key|client_secret)[ \t]*=[ \t]*)\S.*$",
            re.IGNORECASE | re.MULTILINE,
        ),
        r"\1[redacted]",
    ),
    # BORG_PASSPHRASE=, BORG_NEW_PASSPHRASE=, password=, api_key=, token= ...
    (
        re.compile(
            r"\b([\w-]{0,64}(?:passphrase|password|pass|token|secret|key))=(\"[^\"]*\"|'[^']*'|[^\s,;&'\"]+)",
            re.IGNORECASE,
        ),
        r"\1=[redacted]",
    ),
    (
        re.compile(
            r"(Authorization:[ \t]*)(?:(?:Bearer|Basic|Token)[ \t]+)?[^\s,;'\"]+",
            re.IGNORECASE,
        ),
        r"\1[redacted]",
    ),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE), r"\1[redacted]"),
    # Diagnostics can include an auth scheme without an Authorization header.
    (
        re.compile(r"\bBasic\s+[A-Za-z0-9+/_-]+={0,2}", re.IGNORECASE),
        "Basic [redacted]",
    ),
]


SCRUB_INPUT_LIMIT = 65536


def scrub_secrets(text: str) -> str:
    # bounds the regex work on the request path; the result is truncated anyway
    text = text[:SCRUB_INPUT_LIMIT]
    for pattern, replacement in _SCRUB:
        text = pattern.sub(replacement, text)
    return text


# -- flood control -------------------------------------------------------------

_lock = threading.Lock()
_flood: dict[str, list[float]] = {}  # fingerprint -> [last sent at, folded count]
_sent_times: deque[float] = deque()


def _now() -> float:
    return time.monotonic()


def _admit(fingerprint: str) -> Optional[int]:
    """The `count` to send with this report, or None to hold it back."""
    with _lock:
        now = _now()
        state = _flood.setdefault(fingerprint, [float("-inf"), 0])
        state[1] += 1
        if now - state[0] < REPEAT_WINDOW:
            return None
        while _sent_times and now - _sent_times[0] >= 3600:
            _sent_times.popleft()
        if len(_sent_times) >= HOURLY_CAP:
            return None
        count, state[0], state[1] = state[1], now, 0
        _sent_times.append(now)
        return count


# -- consent and instance key --------------------------------------------------

_consent_cache: Optional[tuple[float, bool, Optional[str]]] = None
# bumped on every invalidation: a read that started before one must not
# cache what it saw. The lock never covers the database read, so the
# preferences request that invalidates never waits on the reporter.
_consent_generation = 0
_consent_lock = threading.Lock()


def invalidate_consent_cache() -> None:
    """An analytics preference changed: the next report reads it again."""
    global _consent_cache, _consent_generation
    with _consent_lock:
        _consent_cache = None
        _consent_generation += 1


def _consent() -> tuple[bool, Optional[str]]:
    """(allowed, instance_key). An unreadable database is not a no."""
    global _consent_cache
    now = time.monotonic()
    with _consent_lock:
        if _consent_cache is not None and _consent_cache[0] > now:
            return _consent_cache[1], _consent_cache[2]
        generation = _consent_generation
    allowed, key = True, None
    try:
        db = SessionLocal()
        try:
            said_no = (
                db.query(User.id).filter(User.analytics_enabled.is_(False)).first()
            )
            allowed = said_no is None
            # read only: never create the licensing row from here
            state = db.query(LicensingState.instance_id).first()
            if state is not None and state.instance_id:
                key = hashlib.sha256(state.instance_id.encode()).hexdigest()
        finally:
            db.close()
    except Exception:
        pass
    with _consent_lock:
        if generation == _consent_generation:
            _consent_cache = (now + CONSENT_TTL, allowed, key)
    return allowed, key


# -- sending -------------------------------------------------------------------

_queue: "queue.Queue[Optional[dict]]" = queue.Queue(maxsize=100)
_worker: Optional[threading.Thread] = None


def _drain(q: "queue.Queue[Optional[dict]]") -> None:
    while True:
        event = q.get()
        try:
            if event is None:
                return
            _post(event)
        except Exception:
            pass
        finally:
            q.task_done()


def _post(event: dict) -> None:
    allowed, key = _consent()
    if not allowed:
        return
    if key:
        event["instance_key"] = key
    requests.post(
        ENDPOINT,
        data=json.dumps({"events": [event]}),
        headers={
            "Content-Type": "text/plain",
            "User-Agent": f"borg-ui-backend/{get_runtime_app_version()}",
        },
        timeout=3,
    )


def _enqueue(event: dict) -> None:
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(
                target=_drain, args=(_queue,), name="error-reporter", daemon=True
            )
            _worker.start()
    try:
        _queue.put_nowait(event)
    except queue.Full:
        pass


def flush(timeout: float = 3.0) -> None:
    """Wait until queued reports are sent, or `timeout` seconds pass."""
    try:
        deadline = time.monotonic() + timeout
        with _queue.all_tasks_done:
            while _queue.unfinished_tasks:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                _queue.all_tasks_done.wait(remaining)
    except Exception:
        pass


# -- reports -------------------------------------------------------------------


def _report(
    *,
    kind: str,
    type_: str,
    message: str,
    fingerprint_parts: list[str],
    component: Optional[str],
    handled: bool,
    stack: Optional[str] = None,
    status: Optional[int] = None,
    error_key: Optional[str] = None,
) -> None:
    if not settings.error_reporting_enabled:
        return
    fingerprint = fnv1a64("|".join(fingerprint_parts))
    count = _admit(fingerprint)
    if count is None:
        return
    props: dict = {
        "origin": "backend",
        "kind": kind,
        "type": type_,
        "message": scrub_secrets(message)[:MESSAGE_LIMIT],
    }
    if stack:
        # a Python traceback ends with the innermost frame and the exception
        # line, so keep the tail; scrubbing 64 KB keeps any secret cut at that
        # boundary far outside the 8 KB that is sent
        props["stack"] = scrub_secrets(stack[-SCRUB_INPUT_LIMIT:])[-STACK_LIMIT:]
    props["fingerprint"] = fingerprint
    if component:
        props["component"] = component
    if status is not None:
        props["status"] = status
    # Keep only a bounded translation key, never detail params or free text.
    if isinstance(error_key, str) and len(error_key) <= 160:
        match = re.fullmatch(
            r"backend\.errors\.([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*)",
            error_key,
        )
        if match:
            props["error_key"] = match.group(1)
    props["handled"] = handled
    props["count"] = count
    if len(json.dumps(props, separators=(",", ":"))) > PROPS_LIMIT:
        props.pop("stack", None)
    _enqueue(
        {
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "source": "app",
            "name": EVENT_NAME,
            "session_key": _SESSION_KEY,
            "app_version": get_runtime_app_version()[:32],
            "props": props,
        }
    )


def _type_name(exc: BaseException) -> str:
    cls = type(exc)
    if cls.__module__ == "builtins":
        return cls.__qualname__
    return f"{cls.__module__}.{cls.__qualname__}"


def _top_frame(exc: BaseException) -> str:
    """`module:function` of the innermost traceback frame in the app's code."""
    for frame in reversed(traceback.extract_tb(exc.__traceback__)):
        try:
            relative = Path(frame.filename).resolve().relative_to(_APP_DIR)
        except ValueError:
            continue
        module = ".".join(("app", *relative.with_suffix("").parts))
        return f"{module}:{frame.name}"
    return ""


def _format_stack(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def report_exception(
    exc: BaseException,
    *,
    kind: BackendErrorKind,
    component: Optional[str] = None,
    status: Optional[int] = None,
    error_key: Optional[str] = None,
) -> None:
    try:
        type_ = _type_name(exc)
        message = str(exc)
        _report(
            kind=kind,
            type_=type_,
            message=message,
            fingerprint_parts=[
                "backend",
                kind,
                type_,
                _top_frame(exc),
                normalize_message(scrub_secrets(message)),
            ],
            component=component,
            handled=False,
            stack=_format_stack(exc),
            status=status,
            error_key=error_key,
        )
    except Exception:
        pass


def report_failure(
    *,
    kind: BackendErrorKind,
    type_: str,
    message: str,
    component: Optional[str] = None,
    handled: bool = True,
) -> None:
    try:
        safe_message = redact_secrets(message) or ""
        _report(
            kind=kind,
            type_=type_,
            message=safe_message,
            fingerprint_parts=[
                "backend",
                kind,
                type_,
                component or "",
                normalize_message(scrub_secrets(safe_message)),
            ],
            component=component,
            handled=handled,
            # Handled Borg failures carry stderr in the message rather than
            # an exception traceback. Keep it inspectable beyond the 500-char
            # summary through the same bounded, redacted detail field.
            stack=safe_message if len(safe_message) > MESSAGE_LIMIT else None,
        )
    except Exception:
        pass


def _reset_for_tests() -> None:
    """Clears flood state, the consent cache and the queue (tests only).

    A worker stuck in a slow post keeps the old queue, emptied, and exits after
    it, so nothing it held reaches a later test.
    """
    global _queue, _worker, _consent_cache
    with _lock:
        _flood.clear()
        _sent_times.clear()
        _consent_cache = None
        old, _queue, _worker = _queue, queue.Queue(maxsize=100), None
    while True:
        try:
            old.get_nowait()
            old.task_done()
        except queue.Empty:
            break
    try:
        old.put_nowait(None)
    except queue.Full:
        pass
