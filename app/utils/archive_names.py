"""Utilities for generating borg-safe archive names from schedule metadata.

Borg rejects archive names containing whitespace, forward slashes, or
backslashes because the ``REPO::ARCHIVE`` location format uses path-like
parsing and shell argument splitting. This module centralizes both component
sanitization and final archive-name construction.
"""

import re
from typing import Optional


_ARCHIVE_UNSAFE = re.compile(r"[\s/\\]+")


def sanitize_archive_component(name: str) -> str:
    """Replace whitespace and slashes with hyphens, collapsing runs to one."""
    return _ARCHIVE_UNSAFE.sub("-", name)


def build_archive_name(
    job_name: str,
    repo_name: Optional[str],
    template: Optional[str],
    timestamp: str,
    date: Optional[str] = None,
    time_str: Optional[str] = None,
    unix_timestamp: Optional[str] = None,
) -> str:
    """
    Build a sanitized borg archive name.

    If template is provided, resolve placeholders first, then sanitize the
    entire result. If no template, build default name from job_name (and
    repo_name when given) with the timestamp suffix.

    Args:
        job_name:       Raw job name (may contain spaces/slashes).
        repo_name:      Raw repo name (may contain spaces/slashes). Optional.
        template:       Archive name template with {job_name}, {repo_name},
                        {now}, {date}, {time}, {timestamp} placeholders.
        timestamp:      ISO datetime string for {now} placeholder and default name.
        date:           Date string for {date} placeholder (YYYY-MM-DD).
        time_str:       Time string for {time} placeholder (HH:MM:SS).
        unix_timestamp: Unix timestamp string for {timestamp} placeholder.

    Returns:
         Sanitized archive name safe for borg.
    """
    safe_job = sanitize_archive_component(job_name)
    safe_repo = sanitize_archive_component(repo_name) if repo_name else None

    if template:
        archive_name = template
        archive_name = archive_name.replace("{job_name}", safe_job)
        if safe_repo is not None:
            archive_name = archive_name.replace("{repo_name}", safe_repo)
        archive_name = archive_name.replace("{now}", timestamp)
        if date is not None:
            archive_name = archive_name.replace("{date}", date)
        if time_str is not None:
            archive_name = archive_name.replace("{time}", time_str)
        if unix_timestamp is not None:
            archive_name = archive_name.replace("{timestamp}", unix_timestamp)
        # Final sanitization for any remaining unsafe chars (e.g. from custom template text)
        archive_name = re.sub(r"[\s/\\]+", "-", archive_name)
    else:
        if safe_repo:
            archive_name = f"{safe_job}-{safe_repo}-{timestamp}"
        else:
            archive_name = f"{safe_job}-{timestamp}"

    return archive_name
