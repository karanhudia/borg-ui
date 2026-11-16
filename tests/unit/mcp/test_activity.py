"""Activity log, rate limit and pruning (plan Task 7)."""

from datetime import datetime, timedelta

import pytest
from pydantic import BaseModel

from app.database.models import McpActivity
from app.mcp import activity
from app.mcp.levels import Level
from app.mcp.registry import tool
from app.mcp.render import ToolResult
from tests.unit.mcp.test_registry import register_pair


class NoArgs(BaseModel):
    pass


def register_users_peek():
    @tool(
        name="zz_users_peek",
        title="Peek at users",
        description="Reads the user list. " * 3,
        level=Level.READ,
        routes=("GET /api/settings/users",),
    )
    async def users_peek(ctx, args: NoArgs) -> ToolResult:
        await ctx.api.get("/api/settings/users")
        return ToolResult("ok")


@pytest.fixture
def session(scratch_tools, mcp, create_connection, auth_headers):
    register_pair()
    register_users_peek()
    row, token = create_connection(auth_headers, name="viewer laptop")
    return row, mcp(token)


def _rows(test_db):
    test_db.expire_all()
    return test_db.query(McpActivity).order_by(McpActivity.id).all()


@pytest.mark.unit
def test_successful_call_is_recorded(session, test_db):
    row, mcp_session = session
    mcp_session.call("zz_read_echo", word="hi")
    [entry] = _rows(test_db)
    assert (entry.tool, entry.effective_level, entry.outcome) == (
        "zz_read_echo",
        "read",
        "ok",
    )
    assert entry.connection_id == row["id"]
    assert entry.connection_name == "viewer laptop"
    assert entry.duration_ms >= 0


@pytest.mark.unit
def test_refusals_are_recorded(session, test_db):
    _, mcp_session = session
    assert mcp_session.call("zz_users_peek")["is_error"]
    assert mcp_session.call("zz_full_echo", word="x")["is_error"]
    outcomes = [(r.tool, r.outcome) for r in _rows(test_db)]
    assert outcomes == [
        ("zz_users_peek", "denied_rbac"),
        ("zz_full_echo", "denied_level"),
    ]


@pytest.mark.unit
def test_rate_limit_refuses_without_recording(session, test_db, test_user):
    row, mcp_session = session
    now = datetime.utcnow()
    for _ in range(activity.RATE_LIMIT):
        test_db.add(
            McpActivity(
                connection_id=row["id"],
                connection_name="x",
                user_id=test_user.id,
                tool="t",
                effective_level="read",
                outcome="ok",
                duration_ms=0,
                created_at=now,
            )
        )
    test_db.commit()
    refused = mcp_session.call("zz_read_echo", word="hi")
    assert refused["is_error"] and "a lot of calls" in refused["text"]
    assert len(_rows(test_db)) == activity.RATE_LIMIT
    test_db.query(McpActivity).update({"created_at": now - timedelta(seconds=61)})
    test_db.commit()
    assert mcp_session.call("zz_read_echo", word="hi")["text"] == "✓ hi"


@pytest.mark.unit
def test_calls_still_running_count_against_the_limit(session, test_db, monkeypatch):
    row, mcp_session = session
    monkeypatch.setitem(activity._in_flight, row["id"], activity.RATE_LIMIT)
    refused = mcp_session.call("zz_read_echo", word="hi")
    assert refused["is_error"] and "a lot of calls" in refused["text"]
    assert activity._in_flight[row["id"]] == activity.RATE_LIMIT
    activity._in_flight[row["id"]] = activity.RATE_LIMIT - 1
    assert mcp_session.call("zz_read_echo", word="hi")["text"] == "✓ hi"
    assert activity._in_flight[row["id"]] == activity.RATE_LIMIT - 1


@pytest.mark.unit
def test_prune_keeps_thirty_days_and_newest_rows(test_db, test_user, monkeypatch):
    from app.main import app

    monkeypatch.setattr(activity, "RETENTION_ROWS", 50)
    now = datetime.utcnow()
    old = [
        McpActivity(
            connection_name="x",
            user_id=test_user.id,
            tool="t",
            effective_level="read",
            outcome="ok",
            duration_ms=0,
            created_at=now - timedelta(days=31),
        )
        for _ in range(5)
    ]
    recent = [
        McpActivity(
            connection_name="x",
            user_id=test_user.id,
            tool="t",
            effective_level="read",
            outcome="ok",
            duration_ms=0,
            created_at=now - timedelta(minutes=i),
        )
        for i in range(60)
    ]
    test_db.add_all(old + recent)
    test_db.commit()
    newest_ids = sorted(r.id for r in recent)[-50:]
    activity.prune(app, now=now)
    remaining = _rows(test_db)
    assert len(remaining) == 50
    assert all(r.created_at > now - timedelta(days=30) for r in remaining)
    assert {r.created_at for r in remaining} == {r.created_at for r in recent[:50]}


@pytest.mark.unit
def test_activity_route_lists_newest_first(session, test_client, auth_headers):
    row, mcp_session = session
    mcp_session.call("zz_read_echo", word="one")
    mcp_session.call("zz_full_echo", word="two")
    listed = test_client.get(
        f"/api/settings/mcp/connections/{row['id']}/activity", headers=auth_headers
    ).json()
    assert [entry["tool"] for entry in listed] == ["zz_full_echo", "zz_read_echo"]
    assert all("arguments" not in entry for entry in listed)


@pytest.mark.unit
def test_a_failing_record_does_not_fail_the_call(session, monkeypatch):
    _, mcp_session = session

    def broken(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(activity, "_insert", broken)
    assert mcp_session.call("zz_read_echo", word="hi")["text"] == "✓ hi"


@pytest.mark.unit
def test_returned_errors_are_recorded_as_errors(session, test_db):
    @tool(
        name="zz_soft_fail",
        title="Fails softly",
        description="Returns an error without raising. " * 2,
        level=Level.READ,
        routes=(),
    )
    async def soft_fail(ctx, args: NoArgs) -> ToolResult:
        return ToolResult("nope", is_error=True)

    _, mcp_session = session
    assert mcp_session.call("zz_soft_fail")["is_error"]
    assert _rows(test_db)[-1].outcome == "error"


@pytest.mark.unit
def test_activity_route_pages_by_id(session, test_client, auth_headers):
    row, mcp_session = session
    for word in ("a", "b", "c"):
        mcp_session.call("zz_read_echo", word=word)
    route = f"/api/settings/mcp/connections/{row['id']}/activity"
    first = test_client.get(route, params={"limit": 2}, headers=auth_headers).json()
    rest = test_client.get(
        route, params={"limit": 2, "before_id": first[-1]["id"]}, headers=auth_headers
    ).json()
    assert len(first) == 2 and len(rest) == 1
    assert rest[0]["id"] < first[-1]["id"]
