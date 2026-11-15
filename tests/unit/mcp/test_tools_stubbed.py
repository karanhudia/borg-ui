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


@pytest.mark.unit
def test_list_problems_says_when_failures_were_cut():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)

    def failed(params):
        rows = [
            {
                "id": i,
                "type": "backup",
                "status": "failed",
                "repository": "Photos",
                "completed_at": (now - timedelta(hours=i + 1)).isoformat(),
            }
            for i in range(30)
        ]
        return rows[: params["limit"]]

    routes = {
        "/api/dashboard/overview": {"repository_health": []},
        "/api/activity/recent": failed,
    }
    result, _ = run("list_problems", routes)
    assert "Only the 10 most recent failures were checked" in result.text
    assert 'list_activity with status "failed"' in result.text


PLAN = {
    "id": 3,
    "name": "Nightly",
    "enabled": True,
    "schedule_enabled": True,
    "schedule_mode": "availability",
    "availability_check_interval_minutes": 15,
    "cron_expression": None,
}


@pytest.mark.unit
def test_availability_plans_and_schedules_say_how_they_run():
    routes = {"/api/backup-plans/": {"backup_plans": [PLAN]}}
    result, _ = run("list_backup_plans", routes)
    assert "not scheduled" not in result.text
    assert "when the target is reachable, checked every 15 min" in result.text
    assert result.data["backup_plans"][0]["schedule_mode"] == "availability"

    job = {**PLAN, "repository": None}
    routes = {"/api/schedule/": {"jobs": [job]}, "/api/schedule/3": {"job": job}}
    listed, _ = run("list_schedules", routes)
    assert "None" not in listed.text and "checked every 15 min" in listed.text
    one, _ = run("get_schedule", routes, schedule="Nightly")
    assert "When: when the target is reachable, checked every 15 min" in one.text


@pytest.mark.unit
def test_plan_runs_ask_for_enough_rows():
    def runs(params):
        rows = [{"id": i, "status": "completed"} for i in range(30, 0, -1)]
        return {"runs": rows[: params.get("limit", 20)]}

    routes = {
        "/api/backup-plans/": {"backup_plans": [PLAN]},
        "/api/backup-plans/3/runs": runs,
    }
    result, _ = run("list_plan_runs", routes, plan="Nightly", limit=25)
    assert len(result.data["runs"]) == 25
    assert result.data["next_cursor"]


@pytest.mark.unit
def test_get_schedule_keeps_targets_from_the_list():
    listed = {"id": 4, "name": "Ids", "repository": None, "repository_ids": [1, 2]}
    detail = {"id": 4, "name": "Ids", "cron_expression": "0 2 * * *"}
    routes = {"/api/schedule/": {"jobs": [listed]}, "/api/schedule/4": {"job": detail}}
    result, _ = run("get_schedule", routes, schedule="Ids")
    assert result.data["schedule"]["repository_ids"] == [1, 2]


@pytest.mark.unit
def test_list_problems_warns_on_any_cut_even_when_the_last_job_is_old():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": i,
            "type": "backup",
            "status": "failed",
            "repository": "Photos",
            "completed_at": (now - timedelta(hours=i + 1)).isoformat(),
        }
        for i in range(9)
    ] + [
        {
            "id": 9 + i,
            "type": "backup",
            "status": "failed",
            "repository": "Photos",
            "completed_at": (now - timedelta(days=9 + i)).isoformat(),
        }
        for i in range(5)
    ]
    routes = {
        "/api/dashboard/overview": {"repository_health": []},
        "/api/activity/recent": lambda params: rows[: params["limit"]],
    }
    result, _ = run("list_problems", routes)
    assert "Only the 10 most recent failures were checked" in result.text


def _feed(rows):
    """/api/activity/recent: newest sort_at first, never ending inside a tie."""

    def recent(params):
        before = params.get("before")
        fit = [r for r in rows if before is None or r["sort_at"] < before]
        page = fit[: params["limit"]]
        if page:
            page += [r for r in fit[len(page) :] if r["sort_at"] == page[-1]["sort_at"]]
        return page

    return {"/api/activity/recent": recent}


@pytest.mark.unit
def test_activity_pages_on_sort_at_and_keeps_ties_together():
    rows = [
        {
            "id": 1,
            "type": "backup_plan_run",
            "status": "failed",
            "started_at": "2026-11-01T00:00:00Z",
            "sort_at": "2026-11-10T05:00:00Z",
        },
        {
            "id": 2,
            "type": "backup",
            "status": "completed",
            "started_at": "2026-11-10T04:00:00Z",
            "sort_at": "2026-11-10T04:00:00Z",
        },
        {
            "id": 3,
            "type": "backup",
            "status": "completed",
            "started_at": "2026-11-10T04:00:00Z",
            "sort_at": "2026-11-10T04:00:00Z",
        },
        {
            "id": 4,
            "type": "backup",
            "status": "completed",
            "started_at": "2026-11-10T03:00:00Z",
            "sort_at": "2026-11-10T03:00:00Z",
        },
    ]
    seen, cursor = [], None
    for _ in range(4):
        result, _ = run("list_activity", _feed(rows), limit=2, cursor=cursor)
        seen += [j["id"] for j in result.data.get("jobs", [])]
        cursor = result.data.get("next_cursor")
        if not cursor:
            break
    assert seen == [1, 2, 3, 4]


@pytest.mark.unit
def test_agent_browse_deadline_counts_request_time(monkeypatch):
    import app.mcp.tools.archives as archives

    clock = iter(range(0, 10_000, 10))  # every look at the clock: +10 s
    monkeypatch.setattr(archives.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(archives, "BROWSE_POLL_SECONDS", 0)
    calls = []

    def pending(params):
        calls.append(params)
        return {"status": "pending", "jobId": 9}

    routes = {**repo_routes(AGENT_REPO, [LIVE]), "/api/browse/1/photos-1": pending}
    with pytest.raises(NotFound):
        run("browse_archive", routes, repository="Photos", archive="latest")
    assert len(calls) <= 5  # 40 s at 10 s a look, not 40 sleeps


@pytest.mark.unit
def test_live_log_buffer_is_sliced_to_the_page():
    buffer = [{"line_number": i, "content": f"live {i}"} for i in range(1, 501)]
    routes = {
        "/api/operations/7": {"id": 7, "type": "backup", "status": "running"},
        # A running local backup's log route ignores offset and limit.
        "/api/activity/backup/7/logs": {"lines": buffer, "total_lines": 500},
    }
    result, _ = run("get_job_log", routes, job_type="backup", job_id=7)
    assert result.data["first_line"] == 301
    assert result.data["lines"] == [f"live {i}" for i in range(301, 501)]
    assert result.text.startswith("Lines 301 to 500 of 500")


@pytest.mark.unit
def test_activity_only_jobs_are_found_past_the_first_page():
    rows = [
        {
            "id": i,
            "type": "script_execution",
            "status": "completed",
            "sort_at": f"2026-11-10T00:{i // 60:02d}:{i % 60:02d}Z",
        }
        for i in range(250, 0, -1)
    ]
    result, _ = run("get_job", _feed(rows), job_type="script_execution", job_id=1)
    assert not result.is_error


@pytest.mark.unit
def test_plan_runs_page_by_run_id():
    runs = [{"id": i, "status": "completed"} for i in (3, 2, 1)]
    routes = {
        "/api/backup-plans/": {"backup_plans": [PLAN]},
        "/api/backup-plans/3/runs": lambda params: {"runs": runs[: params["limit"]]},
    }
    first, _ = run("list_plan_runs", routes, plan="Nightly", limit=1)
    assert [r["id"] for r in first.data["runs"]] == [3]
    runs.insert(0, {"id": 4, "status": "running"})
    second, _ = run(
        "list_plan_runs",
        routes,
        plan="Nightly",
        limit=1,
        cursor=first.data["next_cursor"],
    )
    assert [r["id"] for r in second.data["runs"]] == [2]


@pytest.mark.unit
def test_list_problems_warns_even_when_nothing_recent_failed():
    from datetime import datetime, timedelta, timezone

    old = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()
    rows = [
        {"id": i, "type": "backup", "status": "failed", "completed_at": old}
        for i in range(15)
    ]
    routes = {
        "/api/dashboard/overview": {"repository_health": []},
        "/api/activity/recent": lambda params: rows[: params["limit"]],
    }
    result, _ = run("list_problems", routes)
    assert "Nothing needs attention" not in result.text
    assert 'list_activity with status "failed"' in result.text


@pytest.mark.unit
def test_feed_search_past_its_cap_says_it_stopped(monkeypatch):
    import app.mcp.tools.jobs as jobs

    monkeypatch.setattr(jobs, "FEED_PAGES", 2)
    rows = [
        {
            "id": i,
            "type": "script_execution",
            "status": "completed",
            "sort_at": f"2026-11-10T{i // 3600:02d}:{i // 60 % 60:02d}:{i % 60:02d}Z",
        }
        for i in range(500, 0, -1)
    ]
    with pytest.raises(NotFound) as caught:
        run("get_job", _feed(rows), job_type="script_execution", job_id=1)
    assert "searched the newest 400" in caught.value.text
