"""
Utility for building sanitized borg archive names.

Borg rejects archive names containing whitespace or slashes ("Invalid location format").
This module centralizes archive name generation and sanitization.
"""

import re
from typing import Optional

TIME_PLACEHOLDER_PATTERN = re.compile(
    r"\{(?:now|utcnow)(?::[^{}]*)?\}|\{(?:date|time|timestamp)\}"
)


def sanitize_archive_component(name: str) -> str:
    """Replace whitespace and slashes with hyphens (consecutive runs collapse to one)."""
    return re.sub(r"[\s/\\]+", "-", name)


def _build_default_archive_name(
    safe_job: str, safe_repo: Optional[str], timestamp: str, stable_series: bool
) -> str:
    parts = [safe_job]
    if safe_repo:
        parts.append(safe_repo)
    if not stable_series:
        parts.append(timestamp)
    return "-".join(parts)


def _normalize_stable_archive_name(name: str) -> str:
    archive_name = re.sub(r"[\s/\\]+", "-", name)
    archive_name = re.sub(r"-+", "-", archive_name)
    return archive_name.strip("-")


def build_archive_name(
    job_name: str,
    repo_name: Optional[str],
    template: Optional[str],
    timestamp: str,
    date: Optional[str] = None,
    time_str: Optional[str] = None,
    unix_timestamp: Optional[str] = None,
    stable_series: bool = False,
) -> str:
    """
    Build a sanitized borg archive name.

    If template is provided, resolve placeholders first, then sanitize the
    entire result. If no template, build default name from job_name (and
    repo_name when given) with the timestamp suffix. For Borg 2 archive
    series, stable_series removes time placeholders and omits the timestamp
    suffix so repeated backups reuse the same archive name.

    Args:
        job_name:       Raw job name (may contain spaces/slashes).
        repo_name:      Raw repo name (may contain spaces/slashes). Optional.
        template:       Archive name template with {job_name}, {repo_name},
                        {now}, {date}, {time}, {timestamp} placeholders.
        timestamp:      ISO datetime string for {now} placeholder and default name.
        date:           Date string for {date} placeholder (YYYY-MM-DD).
        time_str:       Time string for {time} placeholder (HH:MM:SS).
        unix_timestamp: Unix timestamp string for {timestamp} placeholder.
        stable_series:  Build a stable Borg 2 archive series name.

    Returns:
        Sanitized archive name safe for borg.
    """
    safe_job = sanitize_archive_component(job_name)
    safe_repo = sanitize_archive_component(repo_name) if repo_name else None

    if template:
        archive_name = template
        archive_name = archive_name.replace("{job_name}", safe_job)
        archive_name = archive_name.replace("{plan_name}", safe_job)
        if safe_repo is not None:
            archive_name = archive_name.replace("{repo_name}", safe_repo)

        if stable_series:
            archive_name = TIME_PLACEHOLDER_PATTERN.sub("", archive_name)
            archive_name = _normalize_stable_archive_name(archive_name)
            if not archive_name:
                archive_name = _build_default_archive_name(
                    safe_job, safe_repo, timestamp, stable_series=True
                )
        else:
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
        archive_name = _build_default_archive_name(
            safe_job, safe_repo, timestamp, stable_series
        )

    return archive_name
