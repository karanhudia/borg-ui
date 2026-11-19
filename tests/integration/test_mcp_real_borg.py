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


def _until_done(session, job_type, job_id, rounds=4):
    for _ in range(rounds):
        waited = session.call("wait_for_job", job_type=job_type, job_id=job_id)
        assert not waited["is_error"], waited["text"]
        if waited["data"]["finished"]:
            return waited
    raise AssertionError(f"{job_type} {job_id} did not finish: {waited['text']}")


@pytest.mark.integration
def test_operate_tools_on_a_real_repository(
    test_client,
    test_db,
    tmp_path,
    borg_binary,
    admin_headers,
    create_connection,  # noqa: F811  the shared MCP fixture, imported above
):
    """Phase 3: back up, check and restore through /mcp against real Borg 1."""
    _, _, source = create_registered_local_repository(
        test_db=test_db,
        borg_binary=borg_binary,
        tmp_path=tmp_path,
        name="Real docs",
        slug="docs",
        source_files={"letters/hello.txt": "hello", "notes.txt": "notes"},
    )
    # Borg keeps the source's own path inside the archive.
    letters = f"{str(source).lstrip('/')}/letters"
    _, token = create_connection(admin_headers, level="operate")
    session = McpSession(test_client, token)

    started = session.call("start_backup", repository="Real docs")
    assert not started["is_error"], started["text"]
    done = _until_done(session, "backup", started["data"]["job_id"])
    assert done["data"]["job"]["status"] in ("completed", "completed_with_warnings"), (
        done["text"]
    )

    check = session.call("check_repository", repository="Real docs")
    assert not check["is_error"], check["text"]
    checked = _until_done(session, "check", check["data"]["job_id"])
    assert checked["data"]["job"]["status"] == "completed", checked["text"]

    full = tmp_path / "full"
    full.mkdir()
    (full / "keep.txt").write_text("mine")
    refused = session.call(
        "restore_files",
        repository="Real docs",
        archive="latest",
        paths=[letters],
        destination=str(full),
    )
    assert refused["is_error"] and "already has files" in refused["text"]
    assert (full / "keep.txt").read_text() == "mine"

    target = tmp_path / "restored"
    restore = session.call(
        "restore_files",
        repository="Real docs",
        archive="latest",
        paths=[letters],
        destination=str(target),
        layout="contents_only",
    )
    assert not restore["is_error"], restore["text"]
    restored = _until_done(session, "restore", restore["data"]["job_id"])
    assert restored["data"]["job"]["status"] == "completed", restored["text"]
    # contents_only puts the folder's contents straight in, with their data
    assert (target / "hello.txt").read_text() == "hello"
