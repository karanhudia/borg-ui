"""Archive and file tools (plan Task 9)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.database.models import Archive, ArchiveChange


def _browse_items(n):
    items = [
        {
            "name": "Documents",
            "type": "directory",
            "size": None,
            "mtime": None,
            "path": "Documents",
        }
    ]
    items += [
        {
            "name": f"file-{i:06d}.jpg",
            "type": "file",
            "size": 2048,
            "mtime": "2026-11-10T10:00:00+00:00",
            "path": f"file-{i:06d}.jpg",
        }
        for i in range(n)
    ]
    return items


@pytest.fixture
def fake_browse():
    def install(items):
        return patch(
            "app.api.browse.archive_cache.get", new=AsyncMock(return_value=items)
        )

    return install


@pytest.mark.unit
def test_list_archives_pages(admin_mcp, seeded):
    first = admin_mcp.call("list_archives", repository="Photos", limit=1)
    assert first["text"].splitlines()[0] == "*Photos* has 2 archives:"
    assert "*photos-2026-11-10*" in first["text"]
    assert (
        "Showing 1 of 2 archives. Ask for the next page to see more." in first["text"]
    )
    second = admin_mcp.call(
        "list_archives",
        repository="Photos",
        limit=1,
        cursor=first["data"]["next_cursor"],
    )
    assert "*photos-2026-11-11*" in second["text"]
    assert second["data"]["next_cursor"] is None


@pytest.mark.unit
def test_unreadable_repository_says_why(admin_mcp, seeded):
    # No index rows and no repository on disk: Borg's live listing fails.
    from app.mcp.errors import backend_message

    result = admin_mcp.call("list_archives", repository="Laptop")
    assert result["is_error"]
    assert result["text"] == backend_message(
        "backend.errors.repo.failedToListArchives", {}
    )


@pytest.mark.unit
def test_get_archive_latest(admin_mcp, seeded):
    result = admin_mcp.call("get_archive", repository="Photos", archive="latest")
    assert result["text"].startswith("*photos-2026-11-10* in *Photos*")
    assert "Files: 100" in result["text"]
    assert "New data added: at least 976.6 KB" in result["text"]


@pytest.mark.unit
def test_browse_archive_pages_a_huge_folder(admin_mcp, seeded, fake_browse):
    with fake_browse(_browse_items(100_000)):
        result = admin_mcp.call("browse_archive", repository="Photos", archive="latest")
    lines = result["text"].splitlines()
    assert lines[0] == "The top of *photos-2026-11-10* (100001 entries):"
    assert lines[2] == "📁 Documents/"
    assert result["text"].endswith(
        "Showing 25 of 100001 entries. Ask for the next page to see more."
    )
    assert len(result["data"]["items"]) == 25
    assert len(result["text"]) < 5000


@pytest.mark.unit
def test_browse_archive_unknown_path(admin_mcp, seeded, fake_browse):
    with fake_browse([]):
        result = admin_mcp.call(
            "browse_archive", repository="Photos", archive="latest", path="home/nope"
        )
    assert (
        result["text"]
        == "Nothing at /home/nope in *photos-2026-11-10*. Try its parent, /home."
    )


@pytest.fixture
def history(test_db, seeded, pro_plan):
    photos = seeded["photos"]
    archives = (
        test_db.query(Archive)
        .filter(Archive.repository_id == photos.id)
        .order_by(Archive.start)
        .all()
    )
    for a in archives:
        a.history_state = "indexed"
    test_db.add(
        ArchiveChange(
            archive_id=archives[0].id,
            path="home/alex/notes.md",
            change="added",
            size_after=100,
        )
    )
    test_db.add(
        ArchiveChange(
            archive_id=archives[1].id,
            path="home/alex/notes.md",
            change="modified",
            size_before=100,
            size_after=250,
        )
    )
    test_db.commit()
    return archives


@pytest.mark.unit
def test_search_files(admin_mcp, history):
    result = admin_mcp.call("search_files", repository="Photos", query="notes")
    assert result["text"].splitlines()[0] == '1 path in *Photos* match "notes":'
    assert "home/alex/notes.md: first seen" in result["text"]


@pytest.mark.unit
def test_get_file_history(admin_mcp, history):
    result = admin_mcp.call(
        "get_file_history", repository="Photos", path="/home/alex/notes.md"
    )
    lines = result["text"].splitlines()
    assert "2 changes recorded, newest first:" in lines[0]
    assert lines[2].startswith("~ modified in *photos-2026-11-10*")
    assert lines[3].startswith("+ added in *photos-2026-11-11*")


@pytest.mark.unit
def test_compare_archives(admin_mcp, history):
    result = admin_mcp.call("compare_archives", repository="Photos", archive="latest")
    assert (
        "compared with the previous archive: 0 added, 0 removed, 1 modified."
        in result["text"]
    )
    assert "~ home/alex/notes.md (250 B)" in result["text"]
