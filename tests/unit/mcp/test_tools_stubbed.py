"""Tool behaviour against REST answers the seeded app cannot easily produce.

Each test hands a tool canned route answers, so it pins how the tool reads
a response shape (live Borg info, agent 202s, nested storage, activity
types that are not operations).
"""

import asyncio

import pytest

from app.mcp import tools  # noqa: F401  registers the tools
from app.mcp.context import ConnectionContext, ToolContext
from app.mcp.levels import Level
from app.mcp.registry import REGISTRY
from app.mcp.resolve import NotFound

REPO = {"id": 1, "name": "Photos", "borg_version": 1}
AGENT_REPO = {**REPO, "execution_target": "agent"}


class StubApi:
    """Answers GETs from `routes`: a value, or a list answered in turn."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def get(self, path, /, **params):
        self.calls.append((path, params))
        answer = self.routes[path]
        if isinstance(answer, list) and answer and isinstance(answer[0], Turn):
            return answer.pop(0).value if len(answer) > 1 else answer[0].value
        return answer(params) if callable(answer) else answer


class Turn:
    def __init__(self, value):
        self.value = value


def run(name, routes, **args):
    spec = REGISTRY[name]
    conn = ConnectionContext(1, "test", 1, "admin", Level.READ)
    ctx = ToolContext(conn=conn, api=StubApi(routes))
    return asyncio.run(spec.handler(ctx, spec.input_model(**args))), ctx.api


def repo_routes(repo, archives):
    return {
        "/api/repositories/": {"repositories": [repo]},
        f"/api/repositories/{repo['id']}/archives": {"archives": []},
        f"/api/repositories/{repo['id']}/archives/live": {"archives": archives},
    }


LIVE = {"id": "a1b2c3d4e5", "name": "photos-1", "start": "2026-11-10T10:00:00Z"}


@pytest.mark.unit
def test_live_archive_info_is_normalized():
    info = {
        "name": "photos-1",
        "duration": 125.0,
        "stats": {
            "nfiles": 42,
            "original_size": 2048,
            "compressed_size": 1024,
            "deduplicated_size": 512,
        },
    }
    routes = {
        **repo_routes(REPO, [LIVE]),
        "/api/archives/photos-1/info": {"info": info},
    }
    result, _ = run("get_archive", routes, repository="Photos", archive="latest")
    assert "Took: 2 min" in result.text
    assert "Files: 42" in result.text
    assert result.data["archive"]["nfiles"] == 42


@pytest.mark.unit
def test_archives_resolve_by_hex_id_and_borg_id():
    twin = {**LIVE, "id": "ffff000011"}  # same name, older
    routes = {
        **repo_routes(REPO, [LIVE, twin]),
        "/api/archives/photos-1/info": {"info": {}},
    }
    result, _ = run("get_archive", routes, repository="Photos", archive="ffff000011")
    assert not result.is_error

    indexed = {"id": 7, "borg_id": "beef01", "name": "photos-2"}
    routes = {
        "/api/repositories/": {"repositories": [REPO]},
        "/api/repositories/1/archives": {"archives": [indexed]},
    }
    result, _ = run("get_archive", routes, repository="Photos", archive="beef01")
    assert "*photos-2*" in result.text


@pytest.mark.unit
def test_agent_browse_waits_for_a_pending_listing(monkeypatch):
    import app.mcp.tools.archives as archives

    monkeypatch.setattr(archives, "BROWSE_POLL_SECONDS", 0)
    routes = {
        **repo_routes(AGENT_REPO, [LIVE]),
        "/api/browse/1/photos-1": [
            Turn({"status": "pending", "jobId": 9}),
            Turn({"items": [{"name": "a.jpg", "type": "file", "size": 1}]}),
        ],
    }
    result, api = run("browse_archive", routes, repository="Photos", archive="latest")
    assert "a.jpg" in result.text
    browse = [params for path, params in api.calls if path.startswith("/api/browse")]
    assert browse[1]["job_id"] == 9


@pytest.mark.unit
def test_ssh_free_space_comes_from_storage():
    connection = {
        "id": 1,
        "host": "nas",
        "username": "borg",
        "port": 22,
        "status": "connected",
        "storage": {"available": 5, "available_formatted": "5 B", "total": 9},
    }
    routes = {"/api/ssh-keys/connections": {"connections": [connection]}}
    result, _ = run("list_ssh_connections", routes)
    assert "5 B free" in result.text
    assert result.data["connections"][0]["available"] == 5
    assert result.data["connections"][0]["total"] == 9


@pytest.mark.unit
def test_activity_type_aliases_match_operation_kinds():
    routes = {
        "/api/operations/5": {"id": 5, "type": "package_install", "status": "completed"}
    }
    result, _ = run("get_job", routes, job_type="package", job_id=5)
    assert not result.is_error


@pytest.mark.unit
def test_plan_runs_are_read_from_activity_not_operations():
    run_row = {
        "id": 5,
        "type": "backup_plan_run",
        "status": "failed",
        "error_message": "boom",
    }

    def recent(params):
        assert params["job_type"] == "backup_plan_run"
        return [run_row]

    result, api = run(
        "get_job",
        {"/api/activity/recent": recent},
        job_type="backup_plan_run",
        job_id=5,
    )
    assert "Error: boom" in result.text
    assert all(not path.startswith("/api/operations") for path, _ in api.calls)
    with pytest.raises(NotFound):
        run(
            "get_job",
            {"/api/activity/recent": recent},
            job_type="backup_plan_run",
            job_id=6,
        )


@pytest.mark.unit
def test_activity_pages_by_time_not_offset():
    jobs = [
        {
            "id": 3,
            "type": "backup",
            "status": "completed",
            "started_at": "2026-11-10T03:00:00Z",
        },
        {
            "id": 2,
            "type": "backup",
            "status": "completed",
            "started_at": "2026-11-10T02:00:00Z",
        },
        {
            "id": 1,
            "type": "backup",
            "status": "completed",
            "started_at": "2026-11-10T01:00:00Z",
        },
    ]

    def recent(params):
        before = params.get("before")
        rows = [j for j in jobs if before is None or j["started_at"] < before]
        return rows[: params["limit"]]

    first, _ = run("list_activity", {"/api/activity/recent": recent}, limit=1)
    assert first.data["jobs"][0]["id"] == 3
    jobs.insert(
        0,
        {
            "id": 4,
            "type": "backup",
            "status": "running",
            "started_at": "2026-11-10T04:00:00Z",
        },
    )
    second, _ = run(
        "list_activity",
        {"/api/activity/recent": recent},
        limit=1,
        cursor=first.data["next_cursor"],
    )
    assert second.data["jobs"][0]["id"] == 2
