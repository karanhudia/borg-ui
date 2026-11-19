"""MCP over real HTTP with the official client (plan Task 12).

Starts the app under uvicorn on a free port and talks to /mcp with the MCP
Python SDK's Streamable HTTP client: initialize, list tools, call two.
"""

import asyncio
import secrets
import socket
import threading
import time
from datetime import datetime, timezone

import pytest
import uvicorn

from app.core.security import get_password_hash
from app.database.models import ApiToken, LicensingState, User


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def running_app(test_db):
    from app.api.mcp_connections import mcp_settings
    from app.main import app

    mcp_settings(test_db).mcp_beta_enabled = True
    test_db.add(LicensingState(instance_id="t-mcp-smoke", plan="pro", status="active"))
    user = User(username="smoke", password_hash="x", is_active=True, role="admin")
    test_db.add(user)
    test_db.commit()
    tokens = {}
    for level in ("read", "operate"):
        token = "borgui_" + secrets.token_urlsafe(32)
        test_db.add(
            ApiToken(
                user_id=user.id,
                name=f"smoke {level}",
                token_hash=get_password_hash(token),
                prefix=token[:12],
                created_at=datetime.now(timezone.utc),
                kind="mcp",
                access_level=level,
            )
        )
        tokens[level] = token
    test_db.commit()

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp", tokens
    server.should_exit = True
    thread.join(timeout=15)


async def _session(url, token, calls=(("get_overview", {}), ("list_repositories", {}))):
    from mcp import ClientSession
    from mcp.client.streamable_http import (
        create_mcp_http_client,
        streamable_http_client,
    )

    http = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"})
    async with http, streamable_http_client(url, http_client=http) as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            results = [await session.call_tool(name, args) for name, args in calls]
            return init, tools, *results


@pytest.mark.integration
def test_official_client_round_trip(running_app):
    url, tokens = running_app
    init, tools, overview, repos = asyncio.run(_session(url, tokens["read"]))
    assert init.server_info.name == "borg-ui"
    assert len(tools.tools) == 36
    assert overview.is_error is False
    assert overview.content[0].text.startswith("No repositories yet.")
    assert repos.content[0].text == "No repositories yet."


@pytest.mark.integration
def test_operate_connection_over_the_official_client(running_app):
    """Phase 3: answers are event streams now; the official client reads them,
    and an operate connection sees and calls the operate tools."""
    url, tokens = running_app
    _, tools, unmount = asyncio.run(
        _session(url, tokens["operate"], calls=(("unmount_archive", {}),))
    )
    names = {tool.name for tool in tools.tools}
    assert len(names) == 56
    assert {"start_backup", "restore_files", "wait_for_job"} <= names
    assert unmount.is_error is False
    assert unmount.content[0].text == "Nothing is mounted."
