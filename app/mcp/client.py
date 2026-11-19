"""In-process REST client for MCP tools (spec 2026-11-14-mcp-server, 5.4).

Tools call the app's own routes, so every rule the web UI follows (RBAC,
plan gates, validation, Borg 1/2 handling) applies to them unchanged. Each
request carries a fresh 60 s credential for the connection's user; the
user's MCP token never leaves the endpoint.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from app.core.security import MCP_INTERNAL_HEADER, create_mcp_internal_token

INTERNAL_BASE_URL = "http://borg-ui.internal"
DEFAULT_TIMEOUT = 120
# Borg dry runs (prune and restore previews) and source scans read a lot on
# big repositories and hosts; they get longer before the call gives up.
LONG_TIMEOUT = 600
# Requests past their deadline, kept referenced until their route finishes.
_DETACHED: set[asyncio.Task] = set()


class ApiError(Exception):
    """A non-2xx answer from a route, with the backend error key when given."""

    def __init__(
        self,
        status: int,
        key: Optional[str] = None,
        params: Optional[dict] = None,
        message: Optional[str] = None,
    ):
        super().__init__(key or message or f"HTTP {status}")
        self.status = status
        self.key = key
        self.params = params or {}
        self.message = message

    @classmethod
    def from_response(cls, response: httpx.Response) -> "ApiError":
        try:
            detail = response.json().get("detail")
        except (ValueError, AttributeError):
            detail = None
        if isinstance(detail, dict):
            # Routes nest message params under `params` (the frontend reads
            # them there); plan refusals put their metadata at the top.
            params = {k: v for k, v in detail.items() if k not in ("key", "params")}
            if isinstance(detail.get("params"), dict):
                params.update(detail["params"])
            return cls(response.status_code, detail.get("key"), params)
        if isinstance(detail, str):
            return cls(response.status_code, message=detail)
        return cls(response.status_code)


class UnsafePath(ValueError):
    """A path that would leave the route a tool meant to call."""

    text = "That name cannot be used here. Use the name exactly as Borg UI lists it."


def _check_path(path: str) -> None:
    # Tools build paths from names; "..", "#" or "?" would point the request
    # at another route than the one the tool declares.
    if "#" in path or "?" in path or ".." in path.split("/"):
        raise UnsafePath(path)


class InternalClient:
    def __init__(self, app, *, user_id: int, connection_id: int):
        self._app = app
        self._user_id = user_id
        self._connection_id = connection_id

    async def get(self, path: str, /, **params) -> Any:
        return await self.request("GET", path, params=params)

    async def post(
        self, path: str, /, json: Any = None, timeout: Optional[float] = None, **params
    ) -> Any:
        return await self.request(
            "POST", path, params=params, json=json, timeout=timeout
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Any = None,
        timeout: Optional[float] = None,
    ) -> Any:
        _check_path(path)
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        headers = {
            MCP_INTERNAL_HEADER: create_mcp_internal_token(
                self._user_id, self._connection_id
            )
        }
        # A crashing route answers 500 here, as it would over the network.
        transport = httpx.ASGITransport(app=self._app, raise_app_exceptions=False)
        limit = timeout or DEFAULT_TIMEOUT

        async def send() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=transport, base_url=INTERNAL_BASE_URL
            ) as client:
                return await client.request(
                    method, path, params=clean, json=json, headers=headers
                )

        # The ASGI transport ignores httpx timeouts (only network transports
        # enforce them), so the deadline is ours. The request runs as its own
        # task because cancelling a sync route waits for its worker thread:
        # at the deadline the caller is answered at once, and the route is
        # cancelled as when a client hangs up (a running thread still ends on
        # its own).
        task = asyncio.ensure_future(send())
        try:
            done, _ = await asyncio.wait({task}, timeout=limit)
        except BaseException:
            task.cancel()
            raise
        if not done:
            task.cancel()
            _DETACHED.add(task)
            task.add_done_callback(_DETACHED.discard)
            raise httpx.ReadTimeout(f"{method} {path} took over {limit} s")
        response = task.result()
        if response.is_success:
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        raise ApiError.from_response(response)
