"""In-process REST client for MCP tools (spec 2026-11-14-mcp-server, 5.4).

Tools call the app's own routes, so every rule the web UI follows (RBAC,
plan gates, validation, Borg 1/2 handling) applies to them unchanged. Each
request carries a fresh 60 s credential for the connection's user; the
user's MCP token never leaves the endpoint.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from app.core.security import MCP_INTERNAL_HEADER, create_mcp_internal_token

INTERNAL_BASE_URL = "http://borg-ui.internal"


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


class InternalClient:
    def __init__(self, app, *, user_id: int, connection_id: int):
        self._app = app
        self._user_id = user_id
        self._connection_id = connection_id

    async def get(self, path: str, /, **params) -> Any:
        return await self.request("GET", path, params=params)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Any = None,
    ) -> Any:
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        headers = {
            MCP_INTERNAL_HEADER: create_mcp_internal_token(
                self._user_id, self._connection_id
            )
        }
        # A crashing route answers 500 here, as it would over the network.
        transport = httpx.ASGITransport(app=self._app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url=INTERNAL_BASE_URL, timeout=120
        ) as client:
            response = await client.request(
                method, path, params=clean, json=json, headers=headers
            )
        if response.is_success:
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        raise ApiError.from_response(response)
