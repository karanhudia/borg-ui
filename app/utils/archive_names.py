"""
Utilities for generating borg-safe archive names from schedule metadata.

Borg rejects archive names containing whitespace, forward slashes, or
backslashes because the ``REPO::ARCHIVE`` location format uses path-like
parsing and shell argument splitting.  This module provides a single
``build_archive_name()`` function used by all three schedule execution
code paths so the sanitization logic lives in exactly one place.
"""
import re
from datetime import datetime

_ARCHIVE_UNSAFE = re.compile(r'[\s/\\]+')


def build_archive_name(
    job_name: str,
    repo_name: str,
    template: str | None,
    timestamp: str,
) -> str:
    """Return a borg-safe archive name for a scheduled backup run.

    Replaces runs of whitespace, forward slashes, and backslashes with a
    single hyphen so the result is valid as the ARCHIVE part of a borg
    ``REPO::ARCHIVE`` location string.

    Args:
        job_name:  Name of the scheduled job (may contain spaces/slashes).
        repo_name: Name of the repository (may contain spaces/slashes).
        template:  Optional archive name template string, e.g.
                   ``"{now}-{job_name}"`` or ``"{repo_name}-{date}"``.
                   Supported placeholders: ``{job_name}``, ``{repo_name}``,
                   ``{now}``, ``{date}``, ``{time}``, ``{timestamp}``.
        timestamp: Pre-formatted timestamp string (caller controls precision;
                   multi-repo path uses ms, single-repo path uses seconds).

    Returns:
        A borg-safe archive name string with no spaces, slashes, or
        backslashes.
    """
    safe_job  = _ARCHIVE_UNSAFE.sub('-', job_name)
    safe_repo = _ARCHIVE_UNSAFE.sub('-', repo_name)

    if template:
        name = template
        name = name.replace("{job_name}",  safe_job)
        name = name.replace("{repo_name}", safe_repo)
        name = name.replace("{now}",       timestamp)
        name = name.replace("{date}",      timestamp[:10])    # YYYY-MM-DD
        name = name.replace("{time}",      timestamp[11:19])  # HH:MM:SS
        name = name.replace("{timestamp}", str(int(datetime.now().timestamp())))
        return name

    if repo_name:
        return f"{safe_job}-{safe_repo}-{timestamp}"
    return f"{safe_job}-{timestamp}"
