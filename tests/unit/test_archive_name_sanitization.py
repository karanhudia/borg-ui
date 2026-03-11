import pytest

from app.utils.archive_names import build_archive_name, sanitize_archive_component


TS_SEC = "2026-03-09T05:00:11"
TS_MS = "2026-03-09T05:00:11.675"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("my job", "my-job"),
        ("my/job", "my-job"),
        ("my\\job", "my-job"),
        ("a  b//c", "a-b-c"),
        ("a/ b", "a-b"),
        ("", ""),
        ("clean-name", "clean-name"),
    ],
)
def test_sanitize_archive_component(raw: str, expected: str) -> None:
    assert sanitize_archive_component(raw) == expected


SANITIZE_CASES = [
    ("nightly", "docker01", None, TS_SEC, "nightly-docker01-2026-03-09T05:00:11"),
    (
        "personal vm",
        "docker01",
        None,
        TS_SEC,
        "personal-vm-docker01-2026-03-09T05:00:11",
    ),
    (
        "personal vm /opt backup",
        "my/repo",
        None,
        TS_MS,
        "personal-vm-opt-backup-my-repo-2026-03-09T05:00:11.675",
    ),
    ("nightly", None, None, TS_SEC, "nightly-2026-03-09T05:00:11"),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("job_name", "repo_name", "template", "timestamp", "expected"),
    SANITIZE_CASES,
)
def test_build_archive_name_default_path(
    job_name: str,
    repo_name: str | None,
    template: str | None,
    timestamp: str,
    expected: str,
) -> None:
    assert build_archive_name(job_name, repo_name, template, timestamp) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("job_name", "repo_name", "template", "timestamp", "expected"),
    [
        (
            "personal vm /opt backup",
            "docker01",
            "{now}-{job_name}",
            TS_SEC,
            "2026-03-09T05:00:11-personal-vm-opt-backup",
        ),
        (
            "nightly",
            "my repo",
            "{repo_name}-{now}",
            TS_SEC,
            "my-repo-2026-03-09T05:00:11",
        ),
        (
            "backup",
            "repo",
            "{job_name}-{date}-{time}-{timestamp}",
            TS_SEC,
            "backup-2026-03-09-05:00:11-1741496411",
        ),
        (
            "backup",
            None,
            "my backup/{job_name}",
            TS_SEC,
            "my-backup-backup",
        ),
    ],
)
def test_build_archive_name_template_path(
    job_name: str,
    repo_name: str | None,
    template: str,
    timestamp: str,
    expected: str,
) -> None:
    result = build_archive_name(
        job_name=job_name,
        repo_name=repo_name,
        template=template,
        timestamp=timestamp,
        date="2026-03-09",
        time_str="05:00:11",
        unix_timestamp="1741496411",
    )
    assert result == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("job_name", "repo_name", "template", "timestamp"),
    [
        ("nightly", "docker01", None, TS_SEC),
        ("personal vm", "docker01", None, TS_SEC),
        ("personal vm /opt backup", "my/repo", None, TS_MS),
        ("a/b schedule", "c/d repo", "{job_name}_{repo_name}_{now}", TS_SEC),
    ],
)
def test_build_archive_name_never_returns_borg_unsafe_chars(
    job_name: str,
    repo_name: str | None,
    template: str | None,
    timestamp: str,
) -> None:
    archive = build_archive_name(
        job_name=job_name,
        repo_name=repo_name,
        template=template,
        timestamp=timestamp,
        date="2026-03-09",
        time_str="05:00:11",
        unix_timestamp="1741496411",
    )

    assert " " not in archive
    assert "/" not in archive
    assert "\\" not in archive

    location = f"/local/docker01::{archive}"
    assert location.count("::") == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_name",
    [
        "personal vm /opt backup",
        "my schedule /etc",
        "backup /home /opt",
        "web server /var/www",
        "a b",
        "a/b",
    ],
)
def test_unsanitized_name_is_invalid_for_borg(bad_name: str) -> None:
    raw_archive = f"2026-03-09T05:00:11-{bad_name}"
    assert (" " in raw_archive) or ("/" in raw_archive)

    fixed = build_archive_name(bad_name, None, None, TS_SEC)
    assert " " not in fixed
    assert "/" not in fixed
    assert "\\" not in fixed
