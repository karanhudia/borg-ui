"""Tool registry (plan Task 4)."""

import pytest
from pydantic import BaseModel, Field

from app.mcp.levels import Level
from app.mcp.registry import top_level, tool, tools_for
from app.mcp.render import ToolResult


class EchoArgs(BaseModel):
    word: str = Field(description="What to echo", examples=["hello"])


def register_pair():
    @tool(
        name="zz_read_echo",
        title="Echo",
        description="Echo a word back. " * 3,
        level=Level.READ,
        routes=(),
    )
    async def read_echo(ctx, args: EchoArgs) -> ToolResult:
        return ToolResult(f"✓ {args.word}", {"word": args.word})

    @tool(
        name="zz_full_echo",
        title="Echo loudly",
        description="Echo a word back loudly. " * 3,
        level=Level.FULL,
        routes=(),
        read_only=False,
        destructive=True,
    )
    async def full_echo(ctx, args: EchoArgs) -> ToolResult:
        return ToolResult(args.word.upper())


@pytest.mark.unit
def test_tools_for_filters_by_level(scratch_tools):
    register_pair()
    read_names = {spec.name for spec in tools_for(Level.READ)}
    full_names = {spec.name for spec in tools_for(Level.FULL)}
    assert "zz_read_echo" in read_names and "zz_full_echo" not in read_names
    assert {"zz_read_echo", "zz_full_echo"} <= full_names


@pytest.mark.unit
def test_duplicate_name_raises(scratch_tools):
    register_pair()
    with pytest.raises(ValueError):

        @tool(
            name="zz_read_echo", title="x", description="x", level=Level.READ, routes=()
        )
        async def again(ctx, args: EchoArgs) -> ToolResult: ...


@pytest.mark.unit
def test_input_schema_is_the_model_schema(scratch_tools):
    register_pair()
    assert (
        scratch_tools["zz_read_echo"].input_model.model_json_schema()
        == EchoArgs.model_json_schema()
    )


@pytest.mark.unit
def test_top_level_follows_the_registered_tools(scratch_tools):
    from app.mcp import tools  # noqa: F401  (the real catalog)

    assert top_level() == Level.READ
    register_pair()
    assert top_level() == Level.FULL
