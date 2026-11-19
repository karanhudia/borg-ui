"""Borg 1/2 read routes, as frontend/src/services/borgApi/client.ts routes them."""

import pytest

from app.mcp import borg_routes

V1 = {"id": 7, "borg_version": 1, "execution_target": "local"}
V2 = {"id": 7, "borg_version": 2, "execution_target": "local"}
AGENT_V2 = {"id": 7, "borg_version": 2, "execution_target": "agent"}
ARCHIVE = {"id": 41, "borg_id": "ab12", "name": "laptop-2026-11-14"}


@pytest.mark.unit
def test_repository_routes():
    assert borg_routes.repository_info(V1) == ("/api/repositories/7/info", {})
    assert borg_routes.repository_info(V2) == ("/api/v2/repositories/7/info", {})
    assert borg_routes.repository_info(AGENT_V2) == ("/api/repositories/7/info", {})
    assert borg_routes.repository_stats(V2) == ("/api/v2/repositories/7/stats", {})
    assert borg_routes.archives_list(V1) == ("/api/repositories/7/archives/live", {})
    assert borg_routes.archives_list(V2) == ("/api/v2/repositories/7/archives/live", {})


@pytest.mark.unit
def test_archive_info():
    # Borg 1 archives are addressed by name; the v1 route adds `aid:` for Borg 2.
    assert borg_routes.archive_info(V1, ARCHIVE) == (
        "/api/archives/laptop-2026-11-14/info",
        {"repository": 7, "include_files": False},
    )
    assert borg_routes.archive_info(V2, ARCHIVE)[0] == "/api/v2/archives/ab12/info"


@pytest.mark.unit
def test_archive_contents():
    assert borg_routes.archive_contents(V1, ARCHIVE, "home") == (
        "/api/browse/7/laptop-2026-11-14",
        {"path": "home"},
    )
    assert borg_routes.archive_contents(V2, ARCHIVE, "home") == (
        "/api/v2/archives/ab12/contents",
        {"repository": 7, "path": "home"},
    )
    assert borg_routes.archive_contents(AGENT_V2, ARCHIVE, "") == (
        "/api/browse/7/aid:ab12",
        {"path": ""},
    )


@pytest.mark.unit
def test_live_archives_use_their_id_as_the_borg_id():
    live = {"id": "cd34", "name": "x"}
    assert borg_routes.archive_info(V2, live)[0] == "/api/v2/archives/cd34/info"
    assert borg_routes.archive_info(AGENT_V2, live)[0] == "/api/archives/cd34/info"


REPO_V1 = {**V1, "path": "/data/example/repo"}
AGENT_V2_PATH = {**AGENT_V2, "path": "/data/example/agent"}


@pytest.mark.unit
def test_backup_run():
    assert borg_routes.backup_run(REPO_V1) == (
        "/api/backup/start",
        {"repository": "/data/example/repo"},
    )
    assert borg_routes.backup_run(V2) == ("/api/v2/backup/run", {"repository_id": 7})
    assert borg_routes.backup_run(AGENT_V2_PATH) == (
        "/api/backup/start",
        {"repository": "/data/example/agent"},
    )


@pytest.mark.unit
def test_repository_check():
    # The v1 route treats a missing max_duration as 3600 s (a partial check);
    # 0 is the explicit full check. The value is seconds.
    assert borg_routes.repository_check(V1) == (
        "/api/repositories/7/check",
        {"max_duration": 0},
    )
    assert borg_routes.repository_check(V1, max_duration=1800) == (
        "/api/repositories/7/check",
        {"max_duration": 1800},
    )
    assert borg_routes.repository_check(V2, max_duration=1800) == (
        "/api/v2/backup/check",
        {"repository_id": 7, "max_duration": 1800},
    )
    assert borg_routes.repository_check(AGENT_V2) == (
        "/api/repositories/7/check",
        {"max_duration": 0},
    )


@pytest.mark.unit
def test_repository_compact():
    assert borg_routes.repository_compact(V1) == ("/api/repositories/7/compact", None)
    assert borg_routes.repository_compact(V2) == (
        "/api/v2/backup/compact",
        {"repository_id": 7},
    )
    assert borg_routes.repository_compact(AGENT_V2) == (
        "/api/repositories/7/compact",
        None,
    )


@pytest.mark.unit
def test_restore_archive_selector():
    # The restore routes take a Borg 1 name, or a Borg 2 id they turn into aid:.
    assert borg_routes.restore_archive(V1, ARCHIVE) == "laptop-2026-11-14"
    assert borg_routes.restore_archive(V2, ARCHIVE) == "ab12"
    assert borg_routes.restore_archive(AGENT_V2, ARCHIVE) == "ab12"


@pytest.mark.unit
def test_mount_body():
    assert borg_routes.mount_body(V1, ARCHIVE) == {
        "repository_id": 7,
        "archive_name": "laptop-2026-11-14",
    }
    # Borg 2 series share a name; the id names exactly one archive.
    assert borg_routes.mount_body(V2, ARCHIVE) == {
        "repository_id": 7,
        "archive_name": "laptop-2026-11-14",
        "archive_id": "ab12",
    }
    assert borg_routes.mount_body(V1, None) == {"repository_id": 7}
