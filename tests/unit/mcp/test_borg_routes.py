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
