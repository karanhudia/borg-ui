"""MCP read tools against a real Borg 1 repository (plan Task 12, manual pass).

The unit tests fake Borg; this one lists, inspects and browses a real
archive through /mcp, so the live-list and browse paths are exercised for real.
"""

import pytest

from tests.unit.mcp.conftest import (  # noqa: F401  fixtures used below
    McpSession,
    create_connection,
    pro_plan,
)
from tests.utils.borg import create_archive, create_registered_local_repository


@pytest.mark.integration
def test_read_tools_on_a_real_repository(
    test_client,
    test_db,
    tmp_path,
    borg_binary,
    admin_headers,
    create_connection,  # noqa: F811  the shared MCP fixture, imported above
):
    repo, repo_path, source = create_registered_local_repository(
        test_db=test_db,
        borg_binary=borg_binary,
        tmp_path=tmp_path,
        name="Real photos",
        slug="real",
        source_files={"albums/beach.jpg": "x" * 2048, "notes.txt": "hello"},
    )
    result = create_archive(borg_binary, repo_path, "real-2026-11-14", [source])
    assert result.returncode == 0, result.stderr
    _, token = create_connection(admin_headers, level="read")
    session = McpSession(test_client, token)

    listed = session.call("list_archives", repository="Real photos")
    assert not listed["is_error"], listed["text"]
    assert "*real-2026-11-14*" in listed["text"]

    archive = session.call("get_archive", repository="Real photos", archive="latest")
    assert not archive["is_error"], archive["text"]
    assert archive["text"].startswith("*real-2026-11-14* in *Real photos*")

    top = session.call("browse_archive", repository="Real photos", archive="latest")
    assert not top["is_error"], top["text"]
    assert top["data"]["total"] >= 1

    detail = session.call("get_repository", repository="Real photos")
    assert not detail["is_error"], detail["text"]
    assert "Live statistics are not available" not in detail["text"]
