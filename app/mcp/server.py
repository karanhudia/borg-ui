"""The MCP endpoint (spec 2026-11-14-mcp-server, 5.1 to 5.4).

A lowlevel MCP `Server` behind the official SDK's stateless Streamable HTTP
transport, registered as one route on the FastAPI app. Stateless means any
gunicorn worker answers any call; nothing lives in a session.
"""

from __future__ import annotations

import base64
import json
import time
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Optional

import mcp.types as types
import structlog
from anyio import to_thread
from fastapi import FastAPI
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from pydantic import ValidationError
from starlette.routing import Route

from app.config import get_runtime_app_version
from app.core.features import FEATURES, get_current_plan, has_feature
from app.mcp import activity, auth
from app.mcp.client import InternalClient
from app.mcp.context import ConnectionContext, ToolContext
from app.mcp.db import session_scope
from app.mcp.registry import REGISTRY, ToolSpec, tools_for
from app.mcp.render import ToolResult, finish

logger = structlog.get_logger()

SCOPE_KEY = "borgui_mcp"
_LOGO = Path("app/static/logo.svg")

INSTRUCTIONS = """You are connected to Borg UI, a web app that manages BorgBackup.

How it fits together
- A repository stores archives. Each archive is one backup at a point in time.
- A backup plan says what to back up (sources), where to (one or more
  repositories), when (a schedule) and how long to keep it (retention).
  Prefer plans for anything that should happen more than once.
- A schedule runs a plan or a repository backup on a cron expression.
- Check verifies a repository. A restore check proves files can be restored.
- Prune applies retention and removes old archives. Compact then frees the space.

How to work
- Start with get_overview or list_problems when the user asks how things are.
- Refer to things by name. If a name is ambiguous the tool will say so: ask the
  user which one they mean, do not pick.
- Lists are paged. If a result says there is more, ask for the next page only
  when the user needs it.
- Sizes and times in the text are already formatted for people. Exact values
  are in the structured result.
- This connection has an access level (read, operate, manage or full). You only
  see the tools that level allows. If the user asks for something you have no
  tool for, tell them it needs a higher access level, which they can change in
  Borg UI under Settings > MCP.
- Starting a backup, check, compact, restore or plan run answers at once with
  a job. Offer to wait for it with wait_for_job; ask again if it is still running.
- At operate access, restore_files only writes into an empty or new folder. If
  the user wants to restore over existing files, say that needs full access.
- Never ask the user for a passphrase, password, private key or token. When one
  is needed, Borg UI gives you a link to the page where the user enters it."""


def _icons() -> Optional[list[types.Icon]]:
    if not _LOGO.is_file():
        return None
    encoded = base64.b64encode(_LOGO.read_bytes()).decode()
    return [
        types.Icon(
            src=f"data:image/svg+xml;base64,{encoded}", mime_type="image/svg+xml"
        )
    ]


def _conn(ctx) -> ConnectionContext:
    return ctx.request.scope[SCOPE_KEY]


def _app(ctx) -> FastAPI:
    return ctx.request.scope["borgui_app"]


def _tool(spec: ToolSpec) -> types.Tool:
    return types.Tool(
        name=spec.name,
        title=spec.title,
        description=spec.description,
        input_schema=spec.input_model.model_json_schema(),
        annotations=types.ToolAnnotations(
            title=spec.title,
            read_only_hint=spec.read_only,
            destructive_hint=spec.destructive,
            idempotent_hint=spec.idempotent,
            open_world_hint=False,
        ),
    )


async def on_list_tools(ctx, params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[_tool(s) for s in tools_for(_conn(ctx).level)])


def _gate(app) -> Optional[str]:
    """Why tool calls are refused right now, or None."""
    from app.api.mcp_connections import mcp_settings

    with session_scope(app) as db:
        if not has_feature(db, "mcp"):
            plan = get_current_plan(db).value.capitalize()
            required = FEATURES["mcp"].value.capitalize()
            return (
                f"MCP access is part of Borg UI {required}. This install is on "
                f"{plan}. An admin can upgrade under Settings > Plan."
            )
        if not mcp_settings(db).mcp_enabled:
            return (
                "MCP access is turned off on this Borg UI. An administrator can "
                "turn it on under Settings > System."
            )
    return None


def _validation_text(spec: ToolSpec, exc: ValidationError) -> str:
    lines = [f"Some arguments for {spec.title} are not right:"]
    for error in exc.errors(include_input=False, include_url=False):
        field = ".".join(str(part) for part in error["loc"]) or "arguments"
        lines.append(f"- {field}: {error['msg']}")
    return "\n".join(lines)


def _level_text(conn: ConnectionContext, spec: Optional[ToolSpec], name: str) -> str:
    if spec is None:
        return f"There is no Borg UI tool called {name}."
    return (
        f"This connection has {conn.level.label} access, and {spec.title} needs "
        f"{spec.level.label}. You can change that under Settings > MCP."
    )


async def on_call_tool(ctx, params) -> types.CallToolResult:
    app, conn = _app(ctx), _conn(ctx)
    name = params.name
    started = time.monotonic()

    refusal = await to_thread.run_sync(_gate, app)
    if refusal:
        return finish(ToolResult(refusal, is_error=True))

    spec = REGISTRY.get(name)
    if spec is None or spec.level > conn.level:
        await to_thread.run_sync(
            lambda: activity.record(
                app,
                conn,
                tool=name[:64],
                outcome="denied_level",
                error_key=None,
                target=None,
                duration_ms=0,
            )
        )
        return finish(ToolResult(_level_text(conn, spec, name), is_error=True))

    activity.reserve(conn)
    try:
        if not await to_thread.run_sync(activity.allow, app, conn):
            return finish(
                ToolResult(
                    "That is a lot of calls in one minute. Give it a moment and try again.",
                    is_error=True,
                )
            )

        try:
            args = spec.input_model.model_validate(params.arguments or {})
        except ValidationError as exc:
            return finish(ToolResult(_validation_text(spec, exc), is_error=True))

        tool_ctx = ToolContext(
            conn=conn,
            api=InternalClient(
                app, user_id=conn.user_id, connection_id=conn.connection_id
            ),
            progress=lambda percent, message=None: ctx.session.report_progress(
                percent, 100, message
            ),
        )
        from app.mcp.errors import outcome_for, render_error

        try:
            result = await spec.handler(tool_ctx, args)
            outcome, error_key = ("error" if result.is_error else "ok"), None
        except Exception as exc:  # every failure becomes a friendly sentence
            result = render_error(exc, tool=spec.name)
            outcome, error_key = outcome_for(exc)

        duration_ms = int((time.monotonic() - started) * 1000)
        await to_thread.run_sync(
            lambda: activity.record(
                app,
                conn,
                tool=spec.name,
                outcome=outcome,
                error_key=error_key,
                target=tool_ctx.target,
                duration_ms=duration_ms,
            )
        )
        return finish(result)
    finally:
        activity.release(conn)


def build_server() -> Server:
    return Server(
        "borg-ui",
        version=get_runtime_app_version(),
        title="Borg UI",
        instructions=INSTRUCTIONS,
        icons=_icons(),
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


async def _send_plain(
    send, status: int, body: str, headers: dict | None = None
) -> None:
    raw = [(b"content-type", b"text/plain; charset=utf-8")]
    raw += [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    await send({"type": "http.response.start", "status": status, "headers": raw})
    await send({"type": "http.response.body", "body": body.encode()})


def _bearer(headers: dict[bytes, bytes]) -> Optional[str]:
    for name in (b"authorization", b"x-borg-authorization"):
        value = headers.get(name, b"").decode("latin-1")
        if value.startswith("Bearer "):
            return value[7:].strip()
    return None


def _origin_ok(headers: dict[bytes, bytes]) -> bool:
    """No Origin (a native client) passes; a browser origin must be this host."""
    origin = headers.get(b"origin")
    if origin is None:
        return True
    host = headers.get(b"host", b"").decode("latin-1").lower()
    value = origin.decode("latin-1").lower()
    return "://" in value and value.split("://", 1)[1].rstrip("/") == host


MAX_BODY = 4 * 1024 * 1024  # the SDK's own limit, enforced while reading


async def _read_body(receive) -> Optional[bytes]:
    """The request body, or None once it passes MAX_BODY."""
    body = bytearray()
    while True:
        message = await receive()
        body += message.get("body", b"")
        if len(body) > MAX_BODY:
            return None
        if not message.get("more_body"):
            return bytes(body)


class McpEndpoint:
    """Raw ASGI endpoint: auth, origin check, client info, then the SDK."""

    def __init__(self, app: FastAPI):
        self.app = app
        self.server = build_server()
        self.manager: Optional[StreamableHTTPSessionManager] = None
        self._stack: Optional[AsyncExitStack] = None

    async def start(self) -> None:
        self.manager = StreamableHTTPSessionManager(
            app=self.server, stateless=True, json_response=False
        )
        self._stack = AsyncExitStack()
        await self._stack.enter_async_context(self.manager.run())

    async def stop(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = self.manager = None

    async def __call__(self, scope, receive, send) -> None:
        if scope["method"] != "POST":
            await _send_plain(send, 405, "Use POST.", {"Allow": "POST"})
            return
        headers = dict(scope["headers"])
        if not _origin_ok(headers):
            await _send_plain(send, 403, "Origin not allowed.")
            return
        token = _bearer(headers)
        conn = await auth.authenticate(self.app, token) if token else None
        if conn is None:
            await _send_plain(
                send,
                401,
                "A Borg UI MCP token is required.",
                {"WWW-Authenticate": "Bearer"},
            )
            return
        if self.manager is None:
            await _send_plain(send, 503, "Borg UI is starting.")
            return

        body = await _read_body(receive)
        if body is None:
            await _send_plain(send, 413, "That request is too large.")
            return
        await self._note_client(conn, body)
        scope = {**scope, SCOPE_KEY: conn, "borgui_app": self.app}
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.manager.handle_request(scope, replay, send)

    async def _note_client(self, conn: ConnectionContext, body: bytes) -> None:
        try:
            message = json.loads(body)
        except ValueError:
            return
        if not isinstance(message, dict) or message.get("method") != "initialize":
            return
        info = (message.get("params") or {}).get("clientInfo") or {}
        name, version = str(info.get("name") or ""), str(info.get("version") or "")
        await to_thread.run_sync(
            auth.save_client_info, self.app, conn.connection_id, name, version
        )


def mount(app: FastAPI) -> McpEndpoint:
    """Register /mcp and the startup/shutdown hooks that run the transport."""
    from app.mcp import tools  # noqa: F401  registers the tools

    endpoint = McpEndpoint(app)
    app.router.routes.append(
        Route("/mcp", endpoint=endpoint, methods=["GET", "POST", "DELETE"])
    )
    app.router.on_startup.append(endpoint.start)
    app.router.on_shutdown.append(endpoint.stop)
    return endpoint
