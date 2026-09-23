"""Secret redaction for log output.

`install_log_redaction()` runs once at startup and passes every log record,
from structlog, stdlib, uvicorn or alembic alike, through `redact_secrets`.
Call sites never need to redact before logging.
"""

import logging
import re
from typing import Optional
from urllib.parse import unquote_plus

# scheme://userinfo@host, plain or percent-encoded (a URL inside a query
# string). The netloc runs up to the first path, query, quote or whitespace;
# userinfo is cut at the last `@` because a password may contain `@`.
#
# Every pattern here starts only where a token (scheme, key) starts, never
# mid-token: a `\b` start rescans the rest of a long `a-b-c-...` run from
# each boundary, which is quadratic and stalls logging on big output.
# The whole scheme-character run from its start, so `-https://` or
# `+ssh://` still reach the netloc check.
_SCHEME_START = r"(?<![a-z0-9+.\-])[a-z0-9+.\-]+"
_URL_PATTERNS = [
    (re.compile(rf"(?i)({_SCHEME_START}://)([^\s/?#\"'<>\\]+)"), "@", ":"),
    (
        re.compile(rf"(?i)({_SCHEME_START}%3A%2F%2F)([^\s/?#&\"'<>\\]+)"),
        "%40",
        "%3A",
    ),
]

_SECRET_WORDS = (
    r"(?:pass(?:word|phrase)|secret|(?:api|access|private)[_-]?key"
    r"|(?:access|refresh|auth)[_-]?token)"
)
# A whole key token containing a secret word: AWS_SECRET_ACCESS_KEY, db_password.
_SECRET_KEY = rf"(?=[\w-]*{_SECRET_WORDS})[\w-]+"
# A quoted value is masked whole: spaces, backslash escapes (Python's repr
# writes 'it\'s') and shell-escaped quotes ('"'"') included. The closing
# quote is optional and the value stops at a line end, so an unterminated
# value is still masked and never sends the scan to the end of the text.
_DOUBLE_QUOTED = r""""(?:[^"\\\n]|\\.)*"""
_SINGLE_QUOTED = r"""'(?:[^'\\\n]|\\.|'"'"')*"""
_QUOTED = rf"""{_DOUBLE_QUOTED}"?|{_SINGLE_QUOTED}'?"""
# A quote inside a bare value is part of the secret (`ab"cd`); one followed
# by a delimiter or the end closes the string around it (JSON, a repr).
_INNER_QUOTE = r"""["'](?![\s,;:}\]&#]|$)"""
# key=value (structlog console, env assignments, query strings, including a
# percent-encoded `%3D` inside an encoded URL), "key": "value" (JSON),
# 'key': 'value' (a Python dict formatted into the message) and
# `--flag value` (CLI arguments). Booleans and nulls are flags, not
# secrets, and an existing `***` is left alone so redacting twice is a no-op.
_KEY_VALUE = re.compile(
    rf"""(?i)((?<![\w-]){_SECRET_KEY}["']?\s*(?:=|%3D)\s*|(["']){_SECRET_KEY}\2\s*:\s*"""
    rf"""|(?<![\w-])--{_SECRET_KEY}\s+)"""
    rf"""((?!["']?\*\*\*)(?:{_QUOTED}|(?!(?:true|false|null|none)\b)(?:[^\s"'&,;}}]|{_INNER_QUOTE})+))"""
)

_SECRET_NAME = re.compile(rf"(?i){_SECRET_KEY}")
# ?key=value / &key=value. The key is decoded before the name check because
# URL parsers (redis-py included) decode it too: `pass%77ord` is `password`.
_QUERY_KEY = re.compile(r"""[?&]([^?=&\s"'#]+)=""")
# A secret's value: quoted up to its closing quote (escaped quotes, `&`
# and `?` inside it included), an unterminated quote up to the next `&`, `#` or line end, or
# a bare value up to the next `&` (a literal `?` is part of the value).
_QUERY_VALUE = re.compile(
    rf"""{_DOUBLE_QUOTED}"|{_SINGLE_QUOTED}'|["'][^&#\n]*|(?:[^&\s"'#]|{_INNER_QUOTE})*"""
)


def _mask(value: str) -> str:
    """`***`, keeping the value's quotes (a closing one only if it had one)."""
    quote = value[0] if value[:1] in ('"', "'") else ""
    closing = quote if quote and len(value) > 1 and value.endswith(quote) else ""
    return f"{quote}***{closing}"


def _redact_query(text: str) -> str:
    """Mask the values of secret-named query parameters.

    A scan rather than one substitution: only a secret key's value is read
    and skipped. Any other value is scanned on from just after its `=`, so a
    URL nested in it has its own query checked, and each character is read
    a bounded number of times however deeply URLs nest.
    """
    out, pos = [], 0
    while match := _QUERY_KEY.search(text, pos):
        out.append(text[pos : match.end()])
        pos = match.end()
        if _SECRET_NAME.fullmatch(unquote_plus(match.group(1))):
            value = _QUERY_VALUE.match(text, pos)
            out.append(_mask(value.group()))
            pos = value.end()
    out.append(text[pos:])
    return "".join(out)


def _redact_value(match: re.Match) -> str:
    return f"{match.group(1)}{_mask(match.group(3))}"


def _redact_netloc(match: re.Match, at: str, colon: str) -> str:
    scheme, netloc = match.group(1), match.group(2)
    idx = netloc.lower().rfind(at.lower())
    if idx < 0:
        return match.group(0)
    userinfo, host = netloc[:idx], netloc[idx + len(at) :]
    cut = userinfo.lower().find(colon.lower())
    if cut >= 0:
        userinfo = f"{userinfo[:cut]}{colon}***"
    elif scheme.lower().lstrip("0123456789+.-").startswith("ssh"):
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
    text = _redact_query(text)
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
