"""Repository and space tools (plan Task 9)."""

import pytest

from tests.unit.mcp.test_tools_stubbed import run as _run


@pytest.mark.unit
def test_list_repositories(admin_mcp, seeded):
    result = admin_mcp.call("list_repositories")
    assert result["text"].splitlines()[0] == "2 repositories:"
    assert (
        "*Laptop*: Borg 1, on this server, 18.1 GB, 0 archives, last backup 9 days ago"
        in result["text"]
    )
    assert [r["name"] for r in result["data"]["repositories"]] == ["Laptop", "Photos"]
    assert "hunter2" not in str(result)
    assert "pre_backup_script" not in str(result["data"])


@pytest.mark.unit
def test_get_repository(admin_mcp, seeded):
    result = admin_mcp.call("get_repository", repository="photos")
    text = result["text"]
    assert text.startswith("*Photos* is a Borg 1 repository on this server.")
    assert "Checks are not scheduled." in text
    assert "Live statistics are not available right now" in text  # no real repo on disk
    assert result["data"]["repository"]["name"] == "Photos"
    assert "hunter2" not in str(result)


@pytest.mark.unit
def test_get_repository_ambiguous(admin_mcp, seeded, test_db):
    from app.database.models import Repository

    test_db.add(
        Repository(name="Photos old", path="/srv/backups/photos-old", borg_version=1)
    )
    test_db.commit()
    result = admin_mcp.call("get_repository", repository="photo")
    assert result["is_error"]
    assert result["text"] == (
        'I found 2 repositories matching "photo": *Photos* and *Photos old*. Which one?'
    )


@pytest.mark.unit
def test_get_repository_not_found(admin_mcp, seeded):
    result = admin_mcp.call("get_repository", repository="Fotos")
    assert result["is_error"]
    assert result["text"].startswith('I could not find a repository called "Fotos".')


@pytest.mark.unit
def test_get_repository_space(admin_mcp, seeded):
    result = admin_mcp.call("get_repository_space", repository="Photos")
    assert "*Photos* takes 412.6 GB on disk." in result["text"]
    assert "Archives that added the most:" in result["text"]
    assert len(result["data"]["points"]) == 2


@pytest.mark.unit
def test_compare_retention_before_any_comparison(admin_mcp, seeded):
    result = admin_mcp.call("compare_retention", repository="Photos")
    assert result["text"].startswith(
        "Current policy for *Photos*: 7d 4w 6m 1y (Borg UI's default)."
    )
    assert "No comparison has been computed yet." in result["text"]


# Phase 3, Task 5: maintenance


_V1 = {"id": 1, "name": "Photos", "path": "/data/example/photos", "borg_version": 1}
_V2 = {"id": 2, "name": "Media", "path": "/data/example/media", "borg_version": 2}
_REPOS = {
    "/api/repositories/": {"repositories": [_V1, _V2]},
    "/api/activity/recent": [],
}
_JOB = {"job_id": 77, "status": "pending"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "name,repo,route,body",
    [
        (
            "check_repository",
            "Photos",
            "/api/repositories/1/check",
            {"max_duration": 0},
        ),
        (
            "check_repository",
            "Media",
            "/api/v2/backup/check",
            {"repository_id": 2, "max_duration": 0},
        ),
        ("compact_repository", "Photos", "/api/repositories/1/compact", None),
        ("compact_repository", "Media", "/api/v2/backup/compact", {"repository_id": 2}),
        ("run_restore_check", "Media", "/api/repositories/2/restore-check", None),
    ],
)
def test_maintenance_starts_the_right_route(name, repo, route, body):
    result, api = _run(name, {**_REPOS, f"POST {route}": _JOB}, repository=repo)
    assert api.posts == [(route, body)]
    assert result.data["job_id"] == 77
    assert result.text.startswith("⏳ ")
    assert "Want me to wait for it?" in result.text


@pytest.mark.unit
def test_partial_check_passes_max_duration():
    routes = {**_REPOS, "POST /api/repositories/1/check": _JOB}
    _, api = _run("check_repository", routes, repository="Photos", max_duration=30)
    # minutes in, seconds to the route
    assert api.posts == [("/api/repositories/1/check", {"max_duration": 1800})]


@pytest.mark.unit
def test_refresh_repository():
    routes = {
        **_REPOS,
        "POST /api/repositories/1/resync": {"run_id": "r1", "operations": [5, 6]},
    }
    result, api = _run("refresh_repository", routes, repository="Photos")
    assert api.posts == [("/api/repositories/1/resync", None)]
    assert result.text.startswith(
        "⏳ Refreshing the archive list and stats of *Photos*."
    )


@pytest.mark.unit
def test_preview_prune_without_a_rule_posts_nothing():
    result, api = _run("preview_prune", dict(_REPOS), repository="Photos")
    assert result.is_error and api.posts == []
    assert "keep_daily" in result.text


PREVIEW = {
    "archives": [
        {
            "name": "photos-2025-03-01",
            "verdict": "deleted",
            "start": "2025-03-01T02:00:00Z",
        },
        {
            "name": "photos-2025-03-02",
            "verdict": "deleted",
            "start": "2025-03-02T02:00:00Z",
        },
        {
            "name": "photos-2026-11-10",
            "verdict": "kept",
            "start": "2026-11-10T02:00:00Z",
        },
    ],
    "sizes_available": True,
    "deleted_count": 2,
    "kept_count": 1,
    "freed_at_least": 38 * 1024**3,
    "partial_measure": False,
    "lost_files": None,
    "log": "x" * 5000,
}


@pytest.mark.unit
def test_preview_prune_answer():
    routes = {**_REPOS, "POST /api/repositories/1/prune/preview": PREVIEW}
    result, api = _run(
        "preview_prune", routes, repository="Photos", keep_daily=7, keep_weekly=4
    )
    assert api.posts == [
        ("/api/repositories/1/prune/preview", {"keep_daily": 7, "keep_weekly": 4})
    ]
    first = result.text.splitlines()[0]
    assert first == "Pruning *Photos* with 7d 4w would delete 2 archives and keep 1."
    assert "free at least 38.0 GB" in result.text
    assert "*photos-2025-03-01*" in result.text
    assert "Nothing was deleted." in result.text
    assert "log" not in result.data["preview"]


@pytest.mark.unit
def test_preview_prune_without_sizes():
    preview = {**PREVIEW, "sizes_available": False, "freed_at_least": 0}
    routes = {**_REPOS, "POST /api/repositories/1/prune/preview": preview}
    result, _ = _run("preview_prune", routes, repository="Photos", keep_daily=7)
    assert "free at least" not in result.text
    assert "space it frees is not known" in result.text


@pytest.mark.unit
def test_dry_runs_wait_longer_than_ordinary_calls():
    from app.mcp.client import LONG_TIMEOUT

    routes = {**_REPOS, "POST /api/repositories/1/prune/preview": PREVIEW}
    _, api = _run("preview_prune", routes, repository="Photos", keep_daily=7)
    assert api.timeouts["/api/repositories/1/prune/preview"] == LONG_TIMEOUT
