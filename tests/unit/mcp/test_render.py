"""Formatting, paging and the result cap (plan Task 5)."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.mcp.render import (
    RESULT_CAP,
    BadCursor,
    ToolResult,
    clamp_limit,
    duration,
    finish,
    human_size,
    more_line,
    page,
    when,
)


@pytest.mark.unit
def test_human_units():
    assert human_size(41020000000) == "38.2 GB"
    assert human_size(0) == "0 B"
    assert human_size(1536) == "1.5 KB"
    assert human_size(None) == "unknown"
    assert duration(372) == "6 min"
    assert duration(4320) == "1 h 12 min"
    assert duration(42) == "42 s"
    assert duration(None) == "unknown"


@pytest.mark.unit
def test_when_is_relative_plus_absolute():
    assert when(None) == "never"
    three_hours_ago = datetime.now(timezone.utc) - timedelta(hours=3, minutes=1)
    text = when(three_hours_ago)
    assert text.startswith("3 hours ago (") and text.endswith(" UTC)")
    assert when("2026-11-14T06:10:00+00:00").endswith("(2026-11-14 06:10 UTC)")
    assert when("2026-11-14T06:10:00").endswith(
        "(2026-11-14 06:10 UTC)"
    )  # naive is UTC


@pytest.mark.unit
def test_limits():
    assert clamp_limit(5000) == 200
    assert clamp_limit(None) == 25
    assert clamp_limit(0) == 1


@pytest.mark.unit
def test_paging_walks_the_list():
    items = list(range(60))
    first, cursor = page(items, 25, None)
    assert first == list(range(25)) and cursor
    second, cursor = page(items, 25, cursor)
    third, cursor = page(items, 25, cursor)
    assert third == list(range(50, 60)) and cursor is None
    with pytest.raises(BadCursor):
        page(items, 25, "not-a-cursor")


@pytest.mark.unit
def test_more_line():
    assert more_line(25, 60, "archives", "abc") == (
        "Showing 25 of 60 archives. Ask for the next page to see more."
    )
    assert more_line(10, 10, "archives", None) == ""


@pytest.mark.unit
def test_finish_caps_long_text():
    text = "\n".join("x" * 99 for _ in range(2000))  # 200,000 characters
    result = finish(ToolResult(text))
    out = result.content[0].text
    assert len(out) <= RESULT_CAP
    assert out.endswith(
        "Output was shortened to fit. Ask for a smaller page or a narrower path."
    )


@pytest.mark.unit
def test_finish_trims_huge_data():
    result = finish(
        ToolResult("ok", {"items": [{"n": i, "pad": "y" * 20} for i in range(100_000)]})
    )
    data = result.structured_content
    assert data["truncated"] is True
    assert len(json.dumps(data)) <= RESULT_CAP


@pytest.mark.unit
def test_finish_scrubs_secrets():
    result = finish(
        ToolResult("url ssh://u:hunter2@host/repo", {"passphrase": "hunter2"})
    )
    assert "hunter2" not in result.content[0].text
    assert result.structured_content["passphrase"] == "[hidden]"
