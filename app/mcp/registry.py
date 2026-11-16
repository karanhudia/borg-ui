"""Tool registry: every MCP tool declares its level and the routes it calls."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, get_type_hints

from pydantic import BaseModel

from app.mcp.levels import Level


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    level: Level
    routes: tuple[str, ...]  # "GET /api/dashboard/overview"
    input_model: type[BaseModel]
    handler: Callable[[Any, BaseModel], Awaitable[Any]]
    read_only: bool = True
    destructive: bool = False
    idempotent: bool = True


REGISTRY: dict[str, ToolSpec] = {}


def tool(
    *,
    name: str,
    title: str,
    description: str,
    level: Level,
    routes: tuple[str, ...] | list[str],
    read_only: bool = True,
    destructive: bool = False,
    idempotent: bool = True,
):
    """Register an async handler `(ctx, args) -> ToolResult`.

    The input model is the annotation of the handler's second parameter.
    """

    def register(handler):
        if name in REGISTRY:
            raise ValueError(f"MCP tool registered twice: {name}")
        params = list(inspect.signature(handler).parameters)
        input_model = get_type_hints(handler)[params[1]]
        REGISTRY[name] = ToolSpec(
            name=name,
            title=title,
            description=description,
            level=level,
            routes=tuple(routes),
            input_model=input_model,
            handler=handler,
            read_only=read_only,
            destructive=destructive,
            idempotent=idempotent,
        )
        return handler

    return register


def tools_for(level: Level) -> list[ToolSpec]:
    return sorted(
        (spec for spec in REGISTRY.values() if spec.level <= level),
        key=lambda spec: spec.name,
    )
