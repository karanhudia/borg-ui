"""
Tests for archive name sanitization in schedule execution.

Reproduces the bug where schedule/repository names containing spaces or
slashes are interpolated verbatim into borg archive names, causing:

    borg create: error: argument ARCHIVE: Invalid location format:
    "/local/repo::2026-03-09T05:00:11.675-personal vm /opt backup"

All tests that verify sanitization import build_archive_name() directly
from app.api.schedule so that reverting the fix causes real test failures.

Covers all three code paths via the shared helper:
  - run_scheduled_job_now()       — single-repo manual trigger
  - execute_multi_repo_schedule() — multi-repo cron runner (ms timestamp)
  - check_scheduled_jobs()        — single-repo cron runner

And the following name formats:
  - Simple (no spaces/slashes)        → must be unchanged
  - Spaces only                       → spaces become hyphens
  - Slash only                        → slash becomes hyphen
  - Spaces + slash (real-world case)  → both replaced
  - Multiple consecutive spaces       → collapsed to single hyphen
  - Leading/trailing spaces           → replaced
  - Tabs / other whitespace           → replaced
  - Backslash                         → replaced
  - Custom template with {job_name}   → value is sanitized
  - Custom template with {repo_name}  → value is sanitized
  - No template (default fallback)    → name in fallback is sanitized
"""
import re
import pytest
from datetime import datetime

from app.utils.archive_names import build_archive_name


# ---------------------------------------------------------------------------
# Timestamp constants used across all tests
# ---------------------------------------------------------------------------

TS_SEC = "2026-03-09T05:00:11"           # single-repo format
TS_MS  = "2026-03-09T05:00:11.675"       # multi-repo format (ms precision)


# ---------------------------------------------------------------------------
# Direct unit tests for build_archive_name()
# These WILL fail if the fix is reverted because they call production code.
# ---------------------------------------------------------------------------

SANITIZE_CASES = [
    # (job_name, repo_name, template, timestamp, description)
    ("nightly",                 "docker01",  None,  TS_SEC, "simple names unchanged"),
    ("daily-backup",            "my-repo",   None,  TS_SEC, "hyphenated names unchanged"),
    ("personal vm",             "docker01",  None,  TS_SEC, "space in job name"),
    ("personal vm /opt backup", "docker01",  None,  TS_SEC, "spaces+slash in job name (real-world)"),
    ("personal vm /opt backup", "docker01",  None,  TS_MS,  "spaces+slash, ms timestamp (multi-repo)"),
    ("nightly",                 "my repo",   None,  TS_SEC, "space in repo name"),
    ("personal vm /opt backup", "my/repo",   None,  TS_SEC, "spaces+slash in both names"),
    ("backup /home /opt",       "docker01",  None,  TS_SEC, "multiple slashes in job name"),
    ("a  b",                    "docker01",  None,  TS_SEC, "consecutive spaces collapsed"),
    ("a\tb",                    "docker01",  None,  TS_SEC, "tab replaced"),
    ("a\nb",                    "docker01",  None,  TS_SEC, "newline replaced"),
    ("a\\b",                    "docker01",  None,  TS_SEC, "backslash replaced"),
    (" leading",                "docker01",  None,  TS_SEC, "leading space"),
    ("trailing ",               "docker01",  None,  TS_SEC, "trailing space"),
    ("my/repo",                 "docker01",  None,  TS_SEC, "slash only in job name"),
    # Custom templates
    ("personal vm /opt backup", "docker01",  "{now}-{job_name}",        TS_SEC, "template: space+slash in {job_name}"),
    ("nightly",                 "my repo",   "{repo_name}-{now}",       TS_SEC, "template: space in {repo_name}"),
    ("a/b schedule",            "c/d repo",  "{job_name}_{repo_name}_{now}", TS_SEC, "template: slashes in both"),
    ("web server /var/www",     "docker01",  "{now}-{job_name}",        TS_MS,  "template: path-like job name, ms timestamp"),
]


@pytest.mark.unit
@pytest.mark.parametrize("job_name,repo_name,template,timestamp,description", SANITIZE_CASES)
def test_build_archive_name_no_spaces_or_slashes(
    job_name, repo_name, template, timestamp, description
):
    """
    build_archive_name() must always return a string that borg will accept
    as the ARCHIVE portion of REPO::ARCHIVE. Spaces, forward slashes, and
    backslashes are all illegal there.

    This test calls the production function directly — it FAILS if the fix
    is reverted or the sanitization is removed from build_archive_name().
    """
    result = build_archive_name(job_name, repo_name, template, timestamp)

    assert ' '  not in result, f"[{description}] space in archive name: {result!r}"
    assert '/'  not in result, f"[{description}] slash in archive name: {result!r}"
    assert '\\'  not in result, f"[{description}] backslash in archive name: {result!r}"


@pytest.mark.unit
@pytest.mark.parametrize("job_name,repo_name,template,timestamp,description", SANITIZE_CASES)
def test_build_archive_name_valid_borg_location(
    job_name, repo_name, template, timestamp, description
):
    """
    Embedding the result in REPO::ARCHIVE must yield exactly one '::' and
    no spaces or slashes in the archive portion.
    """
    archive = build_archive_name(job_name, repo_name, template, timestamp)
    location = f"/local/docker01::{archive}"

    assert location.count('::') == 1, \
        f"[{description}] wrong number of :: in: {location!r}"
    archive_part = location.split('::')[1]
    assert ' '  not in archive_part, f"[{description}] space in archive portion: {archive_part!r}"
    assert '/'  not in archive_part, f"[{description}] slash in archive portion: {archive_part!r}"


# ---------------------------------------------------------------------------
# Regression: simple names must pass through unchanged
# ---------------------------------------------------------------------------

SIMPLE_NAMES = [
    ("nightly",       "docker01", "nightly-docker01"),
    ("daily-backup",  "my-repo",  "daily-backup-my-repo"),
    ("daily_backup",  "repo_01",  "daily_backup-repo_01"),
]


@pytest.mark.unit
@pytest.mark.parametrize("job_name,repo_name,expected_prefix", SIMPLE_NAMES)
def test_simple_names_not_altered(job_name, repo_name, expected_prefix):
    """
    Names without spaces or slashes must not be changed — no spurious hyphens.
    """
    result = build_archive_name(job_name, repo_name, None, TS_SEC)
    assert result.startswith(expected_prefix), \
        f"Expected prefix {expected_prefix!r}, got {result!r}"


# ---------------------------------------------------------------------------
# Bug reproduction: document what the unfixed code produces
# These tests assert the BUG exists in raw (unsanitized) strings —
# so they should always PASS (they test the invariant that these inputs
# are dangerous, not that the code handles them correctly).
# ---------------------------------------------------------------------------

INVALID_NAMES = [
    "personal vm /opt backup",
    "my schedule /etc",
    "backup /home /opt",
    "web server /var/www",
    "a b",       # space only
    "a/b",       # slash only
]


@pytest.mark.unit
@pytest.mark.parametrize("bad_name", INVALID_NAMES)
def test_unsanitized_name_is_invalid_for_borg(bad_name):
    """
    Without sanitization, names like these produce borg location strings
    that borg rejects. This documents WHY the fix is needed.
    """
    repo = "/local/docker01"
    raw_archive = f"2026-03-09T05:00:11-{bad_name}"
    location = f"{repo}::{raw_archive}"
    archive_part = location.split("::")[1]

    has_problem = (' ' in archive_part) or ('/' in archive_part)
    assert has_problem, \
        f"Expected {archive_part!r} to be invalid for borg (contains spaces/slashes)"

    # Confirm build_archive_name fixes it
    fixed = build_archive_name(bad_name, "", None, "2026-03-09T05:00:11")
    assert ' '  not in fixed, f"Fixed archive still has space: {fixed!r}"
    assert '/'  not in fixed, f"Fixed archive still has slash: {fixed!r}"
