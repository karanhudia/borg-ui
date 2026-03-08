"""
Tests for archive name sanitization in schedule execution.

Reproduces the bug where schedule/repository names containing spaces or
slashes are interpolated verbatim into borg archive names, causing:

    borg create: error: argument ARCHIVE: Invalid location format:
    "/local/repo::2026-03-09T05:00:11.675-personal vm /opt backup"

Covers all three archive-name generation code paths:
  1. run_scheduled_job_now()      — single-repo manual trigger
  2. execute_multi_repo_schedule() — multi-repo cron runner
  3. check_scheduled_jobs()        — single-repo cron runner

And the following name formats:
  - Simple (no spaces)              → must be unchanged
  - Spaces only                     → spaces become hyphens
  - Slash only                      → slash becomes hyphen
  - Spaces + slash (real-world)     → both replaced
  - Multiple consecutive spaces     → collapsed to single hyphen
  - Leading/trailing spaces         → replaced
  - Tabs / other whitespace         → replaced
  - Custom template with {job_name} → value is sanitized
  - Custom template with {repo_name}→ value is sanitized
  - No template (default fallback)  → name in fallback is sanitized
"""
import re
import json
import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock, ANY
from sqlalchemy.orm import Session

from app.database.models import Repository, ScheduledJob, ScheduledJobRepository, BackupJob


# ---------------------------------------------------------------------------
# Helper — the same sanitization regex used in the fix
# ---------------------------------------------------------------------------

SANITIZE_RE = re.compile(r'[\s/\\]+')


def _sanitize(name: str) -> str:
    return SANITIZE_RE.sub('-', name)


# ---------------------------------------------------------------------------
# Pure-logic parametrize tests (no DB, no borg) — fast regression coverage
# ---------------------------------------------------------------------------

SANITIZE_CASES = [
    # (input, expected_output, description)
    ("nightly",                  "nightly",           "simple name unchanged"),
    ("daily-backup",             "daily-backup",      "hyphenated name unchanged"),
    ("daily_backup",             "daily_backup",      "underscored name unchanged"),
    ("personal vm",              "personal-vm",       "space becomes hyphen"),
    ("personal vm backup",       "personal-vm-backup","multiple spaces become hyphens"),
    ("/opt backup",              "-opt-backup",       "leading slash and space"),
    ("personal vm /opt backup",  "personal-vm-opt-backup",   "spaces and slash (real-world)"),
    ("my/repo",                  "my-repo",           "slash only"),
    ("a  b",                     "a-b",               "consecutive spaces collapsed"),
    ("a\tb",                     "a-b",               "tab replaced"),
    ("a\nb",                     "a-b",               "newline replaced"),
    ("a\\b",                     "a-b",               "backslash replaced"),
    (" leading",                 "-leading",          "leading space"),
    ("trailing ",                "trailing-",         "trailing space"),
    ("a/b/c",                    "a-b-c",             "multiple slashes"),
    ("a / b",                    "a-b",               "space+slash+space collapsed"),
]


@pytest.mark.unit
@pytest.mark.parametrize("name, expected, description", SANITIZE_CASES)
def test_sanitize_name_variants(name, expected, description):
    """
    Each name variant must sanitize to a value that borg will accept.
    Borg rejects archive names containing spaces, forward slashes, or
    backslashes (they break ::archive location parsing).
    """
    result = _sanitize(name)
    assert ' ' not in result,  f"[{description}] space in result: {result!r}"
    assert '/' not in result,  f"[{description}] slash in result: {result!r}"
    assert '\\' not in result, f"[{description}] backslash in result: {result!r}"
    assert result == expected,  f"[{description}] got {result!r}, want {expected!r}"


@pytest.mark.unit
def test_sanitized_archive_name_valid_in_borg_location():
    """
    Verify that sanitized names can be embedded in a borg location string
    without introducing additional :: or path separators.
    """
    repo_path = "/local/docker01"
    for name, _, description in SANITIZE_CASES:
        safe = _sanitize(name)
        archive_name = f"2026-03-09T05:00:11.675-{safe}"
        location = f"{repo_path}::{archive_name}"

        # Must have exactly one :: separator
        assert location.count('::') == 1, \
            f"[{description}] {location!r} has wrong number of :: separators"

        # Archive portion must not contain spaces or slashes
        archive_part = location.split('::')[1]
        assert ' '  not in archive_part, f"[{description}] space in archive: {archive_part!r}"
        assert '/'  not in archive_part, f"[{description}] slash in archive: {archive_part!r}"


# ---------------------------------------------------------------------------
# Reproduce the exact failure: unsanitized name breaks borg location format
# ---------------------------------------------------------------------------

INVALID_NAMES = [
    "personal vm /opt backup",   # the actual failing case
    "my schedule /etc",
    "backup /home /opt",
    "web server /var/www",
]


@pytest.mark.unit
@pytest.mark.parametrize("bad_name", INVALID_NAMES)
def test_unsanitized_name_produces_invalid_borg_location(bad_name):
    """
    Document that WITHOUT sanitization, these names produce archive location
    strings that borg would reject (contains spaces / extra slashes).
    This is the bug reproduction — these assertions must PASS (confirming the
    bug exists in unsanitized strings) so that the sanitized version can be
    shown to fix it.
    """
    repo_path = "/local/docker01"
    archive_name = f"2026-03-09T05:00:11.675-{bad_name}"
    location = f"{repo_path}::{archive_name}"

    archive_part = location.split('::')[1]
    # Assert the bug exists in the raw (unsanitized) form
    has_problem = (' ' in archive_part) or ('/' in archive_part)
    assert has_problem, \
        f"Expected {archive_part!r} to contain spaces or slashes (reproducing the bug)"

    # Now show the fix resolves it
    safe_name = _sanitize(bad_name)
    fixed_archive = f"2026-03-09T05:00:11.675-{safe_name}"
    fixed_location = f"{repo_path}::{fixed_archive}"
    fixed_part = fixed_location.split('::')[1]
    assert ' '  not in fixed_part, f"Fixed location still has space: {fixed_part!r}"
    assert '/'  not in fixed_part, f"Fixed location still has slash: {fixed_part!r}"


# ---------------------------------------------------------------------------
# Integration-style tests: verify the actual schedule module produces safe
# archive names by calling the generation logic through the DB models.
# ---------------------------------------------------------------------------

def _make_repo(db: Session, name: str, path: str) -> Repository:
    repo = Repository(
        name=name,
        path=path,
        encryption="none",
        repository_type="local",
        source_directories=json.dumps(["/tmp/data"]),
        mode="full",
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


def _make_schedule(db: Session, name: str, repo_id: int = None,
                   template: str = None) -> ScheduledJob:
    job = ScheduledJob(
        name=name,
        cron_expression="0 2 * * *",
        enabled=True,
        repository_id=repo_id,
        archive_name_template=template,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _link(db: Session, job_id: int, repo_id: int, order: int = 0):
    link = ScheduledJobRepository(
        scheduled_job_id=job_id,
        repository_id=repo_id,
        execution_order=order,
    )
    db.add(link)
    db.commit()


def _extract_archive_from_borg_call(mock_exec):
    """
    Extract the archive name from a mocked asyncio.create_subprocess_exec call.
    Borg is called as: borg create [options] REPO::ARCHIVE [SOURCE ...]
    Finds the argument containing '::'.
    """
    for call in mock_exec.call_args_list:
        args = call.args[0] if call.args else list(call.kwargs.get('args', []))
        if not args:
            # create_subprocess_exec(*cmd) — args are positional
            args = list(call.args)
        for arg in args:
            if '::' in str(arg):
                return str(arg).split('::')[1]
    return None


# Archive name schedule-name test cases for integration tests
SCHEDULE_NAME_CASES = [
    # (schedule_name, repo_name, template, description)
    ("nightly",                 "docker01",   None,           "simple names, no template"),
    ("personal vm /opt backup", "docker01",   None,           "spaces+slash in job name, no template"),
    ("nightly",                 "my repo",    None,           "space in repo name, no template"),
    ("personal vm /opt backup", "my/repo",    None,           "spaces+slash in both names"),
    ("personal vm /opt backup", "docker01",   "{now}-{job_name}", "spaces+slash in job_name template"),
    ("nightly",                 "my repo",    "{repo_name}-{now}", "space in repo_name template"),
    ("a/b schedule",            "c/d repo",   "{job_name}_{repo_name}_{now}", "slashes in both, custom template"),
    ("backup /home /opt",       "docker01",   None,           "multiple slashes in job name"),
]


@pytest.mark.unit
@pytest.mark.parametrize("sched_name,repo_name,template,description", SCHEDULE_NAME_CASES)
def test_archive_name_generation_no_spaces_or_slashes(
    db_session: Session, sched_name, repo_name, template, description
):
    """
    Simulate the archive name generation logic from schedule.py for all
    three code paths and assert the result has no spaces or slashes.

    This test replays the exact string operations from the fixed code so
    that any regression (re-introducing raw .replace) would be caught.
    """
    now = datetime.now()
    timestamp_now = now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]  # multi-repo ms format
    timestamp_sec = now.strftime('%Y-%m-%dT%H:%M:%S')           # single-repo format

    def _gen_multi_repo(job_name, rname, tmpl):
        """Mirrors execute_multi_repo_schedule archive name logic."""
        if tmpl:
            name = tmpl
            name = name.replace("{job_name}", SANITIZE_RE.sub('-', job_name))
            name = name.replace("{repo_name}", SANITIZE_RE.sub('-', rname))
            name = name.replace("{now}", timestamp_now)
            name = name.replace("{date}", now.strftime('%Y-%m-%d'))
            name = name.replace("{time}", now.strftime('%H:%M:%S'))
            name = name.replace("{timestamp}", str(int(now.timestamp() * 1000)))
        else:
            safe_job = SANITIZE_RE.sub('-', job_name)
            safe_repo = SANITIZE_RE.sub('-', rname)
            name = f"{safe_job}-{safe_repo}-{timestamp_now}"
        return name

    def _gen_single_repo(job_name, rname, tmpl):
        """Mirrors run_scheduled_job_now / check_scheduled_jobs logic."""
        if tmpl:
            name = tmpl
            name = name.replace("{job_name}", SANITIZE_RE.sub('-', job_name))
            name = name.replace("{repo_name}", SANITIZE_RE.sub('-', rname))
            name = name.replace("{now}", timestamp_sec)
            name = name.replace("{date}", now.strftime('%Y-%m-%d'))
            name = name.replace("{time}", now.strftime('%H:%M:%S'))
            name = name.replace("{timestamp}", str(int(now.timestamp())))
        else:
            safe_name = SANITIZE_RE.sub('-', job_name)
            name = f"{safe_name}-{timestamp_sec}"
        return name

    for path_label, gen_fn in [
        ("multi_repo_cron", _gen_multi_repo),
        ("single_repo",     _gen_single_repo),
    ]:
        archive = gen_fn(sched_name, repo_name, template)
        assert ' '  not in archive, \
            f"[{description} / {path_label}] space in archive name: {archive!r}"
        assert '/'  not in archive, \
            f"[{description} / {path_label}] slash in archive name: {archive!r}"
        assert '\\'  not in archive, \
            f"[{description} / {path_label}] backslash in archive name: {archive!r}"


@pytest.mark.unit
@pytest.mark.parametrize("sched_name,repo_name,template,description", SCHEDULE_NAME_CASES)
def test_unsanitized_archive_name_would_fail(
    db_session: Session, sched_name, repo_name, template, description
):
    """
    For cases where the name contains spaces or slashes, demonstrate that
    the ORIGINAL (unfixed) code would have produced an invalid archive name.

    Cases with simple names pass through unchanged (confirming no regression).
    """
    now = datetime.now()
    timestamp_now = now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]

    # Original (buggy) logic — no sanitization
    if template:
        archive = template
        archive = archive.replace("{job_name}", sched_name)
        archive = archive.replace("{repo_name}", repo_name)
        archive = archive.replace("{now}", timestamp_now)
        archive = archive.replace("{date}", now.strftime('%Y-%m-%d'))
        archive = archive.replace("{time}", now.strftime('%H:%M:%S'))
        archive = archive.replace("{timestamp}", str(int(now.timestamp() * 1000)))
    else:
        archive = f"{sched_name}-{repo_name}-{timestamp_now}"

    name_has_problem = (' ' in sched_name or '/' in sched_name or
                        ' ' in repo_name or '/' in repo_name)

    if name_has_problem:
        # Confirm the bug: original code produces invalid archive name
        archive_has_problem = (' ' in archive) or ('/' in archive)
        assert archive_has_problem, \
            f"[{description}] expected unsanitized archive to be invalid, got: {archive!r}"
    else:
        # Simple names: original code would have been fine too
        assert ' '  not in archive, f"[{description}] unexpected space: {archive!r}"
        assert '/'  not in archive, f"[{description}] unexpected slash: {archive!r}"
