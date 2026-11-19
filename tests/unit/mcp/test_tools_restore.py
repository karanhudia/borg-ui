"""Restore tools (phase 3, Task 6): preview, and restore only into an empty
or new folder (spec 5.5; overwriting is phase 5's restore_files_overwrite)."""

import pytest

from app.mcp.client import ApiError
from tests.unit.mcp.test_tools_stubbed import run

V1 = {"id": 1, "name": "Photos", "path": "/data/example/photos", "borg_version": 1}
V2 = {"id": 2, "name": "Media", "path": "/data/example/media", "borg_version": 2}
AGENT = {
    "id": 3,
    "name": "Laptop",
    "path": "/data/example/laptop",
    "borg_version": 1,
    "execution_target": "agent",
    "agent_machine_id": 9,
}
ARCHIVE = {
    "id": 41,
    "borg_id": "ab12cd",
    "name": "photos-2026-11-14",
    "start": "2026-11-14T02:00:00Z",
}
SSH = {
    "id": 4,
    "host": "backups.example.com",
    "username": "borg",
    "port": 22,
    "ssh_key_id": 6,
}
DEST = "/data/example/restore"


def _routes(repo, listing_route, listing):
    return {
        "/api/repositories/": {"repositories": [V1, V2, AGENT]},
        f"/api/repositories/{repo['id']}/archives": {"archives": [ARCHIVE]},
        "/api/ssh-keys/connections": {"connections": [SSH]},
        listing_route: listing,
        "/api/activity/recent": [],
        "POST /api/restore/start": {"job_id": 55, "status": "pending"},
    }


SERVER = "/api/filesystem/browse"
AGENT_BROWSE = "/api/managed-machines/agents/9/filesystem/browse"


def _raise(exc):
    def answer(params):
        raise exc

    return answer


def _restore(repo, listing_route, listing, **extra):
    args = {
        "repository": repo["name"],
        "archive": "latest",
        "paths": ["home/alex/notes"],
        "destination": DEST,
        **extra,
    }
    return run("restore_files", _routes(repo, listing_route, listing), **args)


@pytest.mark.unit
def test_restore_into_empty_folder_starts():
    result, api = _restore(V1, SERVER, {"current_path": DEST, "items": []})
    ((path, body),) = api.posts
    assert path == "/api/restore/start"
    assert body["existing_files"] == "refuse"
    assert body["archive"] == "photos-2026-11-14"
    assert body["destination"] == DEST and body["repository_id"] == 1
    assert body["paths"] == ["home/alex/notes"]
    assert result.text.startswith("⏳ Restore of *Photos* started (restore 55).")


@pytest.mark.unit
def test_borg2_restore_sends_the_archive_id():
    _, api = _restore(V2, SERVER, {"items": []})
    assert api.posts[0][1]["archive"] == "ab12cd"


@pytest.mark.unit
def test_restore_into_missing_folder_starts():
    missing = _raise(ApiError(404, "backend.errors.filesystem.pathNotFound"))
    _, api = _restore(V1, SERVER, missing)
    assert len(api.posts) == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "repo,route,extra",
    [
        (V1, SERVER, {}),
        (V1, SERVER, {"destination_connection": "borg@backups.example.com"}),
        (AGENT, AGENT_BROWSE, {}),
    ],
    ids=["server", "ssh", "agent"],
)
def test_restore_into_non_empty_folder_refuses_without_posting(repo, route, extra):
    listing = {"items": [{"name": "old.txt", "is_directory": False}]}
    result, api = _restore(repo, route, listing, **extra)
    assert result.is_error and api.posts == []
    assert result.text.startswith(f"Restore stopped. {DEST} already has files in it")
    assert "full access" in result.text


@pytest.mark.unit
def test_ssh_destination_lists_over_ssh():
    _, api = _restore(
        V1, SERVER, {"items": []}, destination_connection="borg@backups.example.com"
    )
    listing = [p for path, p in api.calls if path == SERVER][0]
    assert listing["connection_type"] == "ssh"
    assert (listing["ssh_key_id"], listing["host"], listing["username"]) == (
        6,
        "backups.example.com",
        "borg",
    )
    body = api.posts[0][1]
    assert body["destination_type"] == "ssh" and body["destination_connection_id"] == 4


@pytest.mark.unit
@pytest.mark.parametrize(
    "error",
    [
        ApiError(403, "backend.errors.auth.notEnoughPermissions"),
        ApiError(400, "backend.errors.filesystem.pathNotDirectory"),
    ],
    ids=["forbidden", "a-file"],
)
def test_restore_listing_refused_refuses(error):
    result, api = _restore(V1, SERVER, _raise(error))
    assert result.is_error and api.posts == []
    assert "could not look inside" in result.text


PREVIEW_LINES = "\n".join(f"x home/alex/notes/file{i}.md" for i in range(200))


@pytest.mark.unit
def test_preview_restore_caps_listing():
    routes = {
        "/api/repositories/": {"repositories": [V1]},
        "/api/repositories/1/archives": {"archives": [ARCHIVE]},
        "POST /api/restore/preview": {"preview": PREVIEW_LINES},
    }
    result, api = run(
        "preview_restore",
        routes,
        repository="Photos",
        archive="latest",
        paths=["home/alex/notes"],
    )
    ((path, body),) = api.posts
    assert path == "/api/restore/preview" and body["archive"] == "photos-2026-11-14"
    assert result.text.startswith(
        "Restoring home/alex/notes from *photos-2026-11-14* would write 200 entries."
    )
    assert "file49.md" in result.text and "file50.md" not in result.text
    assert "and 150 more" in result.text
    assert "Nothing was written." in result.text


@pytest.mark.unit
def test_agent_listing_includes_hidden_files():
    """Review fix: the agent hides dotfiles unless asked, and a folder holding
    only .bashrc is not empty."""
    _, api = _restore(AGENT, AGENT_BROWSE, {"items": []})
    listing = [p for path, p in api.calls if path == AGENT_BROWSE][0]
    assert listing["include_hidden"] is True


@pytest.mark.unit
def test_agent_repository_refuses_an_ssh_destination():
    """Agent restores write on the agent's own host; an SSH destination would
    be silently ignored, so say so instead of starting."""
    result, api = _restore(
        AGENT,
        AGENT_BROWSE,
        {"items": []},
        destination_connection="borg@backups.example.com",
    )
    assert result.is_error and api.posts == []
    assert result.text.startswith("*Laptop* restores on its agent machine")


@pytest.mark.unit
def test_restore_preview_waits_long():
    from app.mcp.client import LONG_TIMEOUT

    routes = {
        "/api/repositories/": {"repositories": [V1]},
        "/api/repositories/1/archives": {"archives": [ARCHIVE]},
        "POST /api/restore/preview": {"preview": ""},
    }
    _, api = run(
        "preview_restore", routes, repository="Photos", archive="latest", paths=["x"]
    )
    assert api.timeouts["/api/restore/preview"] == LONG_TIMEOUT
