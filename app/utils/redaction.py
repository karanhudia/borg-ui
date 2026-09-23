"""Secret redaction for log output.

`install_log_redaction()` runs once at startup and passes every log record,
from structlog, stdlib, uvicorn or alembic alike, through `redact_secrets`.
Call sites never need to redact before logging.
"""

import logging
import re
from typing import Optional

# scheme://userinfo@host, plain or percent-encoded (a URL inside a query
# string). The netloc runs up to the first path, query, quote or whitespace;
# userinfo is cut at the last `@` because a password may contain `@`.
_URL_PATTERNS = [
    (re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)([^\s/?#\"'<>\\]+)"), "@", ":"),
    (
        re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*%3A%2F%2F)([^\s/?#&\"'<>\\]+)"),
        "%40",
        "%3A",
    ),
]

_SECRET_WORDS = (
    r"(?:pass(?:word|phrase)|secret|(?:api|access|private)[_-]?key"
    r"|(?:access|refresh|auth)[_-]?token)"
)
_SECRET_KEY = rf"[\w-]*{_SECRET_WORDS}[\w-]*"  # AWS_SECRET_ACCESS_KEY, db_password
# key=value (structlog console, env assignments, query strings, including a
# percent-encoded `%3D` inside an encoded URL), "key": "value" (JSON) and
# `--flag value` (CLI arguments). A quoted value is masked whole, spaces and
# shell-escaped quotes ('"'"') included. Booleans and nulls are flags, not
# secrets, and an existing `***` is left alone so redacting twice is a no-op.
_KEY_VALUE = re.compile(
    rf"""(?i)(\b{_SECRET_KEY}["']?\s*(?:=|%3D)\s*|"{_SECRET_KEY}"\s*:\s*"""
    rf"""|(?<![\w-])--{_SECRET_KEY}\s+)"""
    r"""("(?:[^"\\]|\\.)*"|'(?:[^']|'"'"')*'"""
    r"""|(?!(?:true|false|null|none)\b|\*\*\*)[^\s"'&,;}]+)"""
)


def _redact_value(match: re.Match) -> str:
    key, value = match.group(1), match.group(2)
    quote = value[0] if value[0] in "\"'" else ""
    return f"{key}{quote}***{quote}"


def _redact_netloc(match: re.Match, at: str, colon: str) -> str:
    scheme, netloc = match.group(1), match.group(2)
    idx = netloc.lower().rfind(at.lower())
    if idx < 0:
        return match.group(0)
    userinfo, host = netloc[:idx], netloc[idx + len(at) :]
    cut = userinfo.lower().find(colon.lower())
    if cut >= 0:
        userinfo = f"{userinfo[:cut]}{colon}***"
    elif scheme.lower().startswith("ssh"):
        return match.group(0)  # an SSH user name is not a secret, keys are
    else:
        userinfo = "***"  # a bare userinfo is the credential (Basic auth token)
    return f"{scheme}{userinfo}{at}{host}"


def redact_secrets(text: Optional[str]) -> Optional[str]:
    """`text` with URL credentials and secret-named values replaced by `***`."""
    if not text:
        return text
    for pattern, at, colon in _URL_PATTERNS:
        text = pattern.sub(lambda m: _redact_netloc(m, at, colon), text)
    return _KEY_VALUE.sub(_redact_value, text)


_exception_formatter = logging.Formatter()


def install_log_redaction() -> None:
    """Redact every log record at creation. Idempotent."""
    previous = logging.getLogRecordFactory()
    if getattr(previous, "redacts_secrets", False):
        return

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        try:
            message = record.getMessage()
            redacted = redact_secrets(message)
            if redacted != message:
                record.msg, record.args = redacted, ()
            if record.exc_info and not record.exc_text:
                record.exc_text = redact_secrets(
                    _exception_formatter.formatException(record.exc_info)
                )
        except Exception:
            pass  # a malformed record is logging's to report, not ours
        return record

    factory.redacts_secrets = True
    logging.setLogRecordFactory(factory)
