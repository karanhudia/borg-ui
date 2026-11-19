"""Archive and file tools (plan Task 9)."""

from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.mcp.test_tools_stubbed import run as _run

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
    assert "Showing 1 of 2 archives. For more, pass cursor" in first["text"]
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
    # No index rows and no repository on disk: Borg's live listing fails,
    # and the nested `params.error` reaches the sentence.
    result = admin_mcp.call("list_archives", repository="Laptop")
    assert result["is_error"]
    assert result["text"].startswith("Failed to list archives: Repository ")
    assert result["text"].endswith("does not exist.")


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
    assert (
        f'Showing 25 of 100001 entries. For more, pass cursor "{result["data"]["next_cursor"]}".'
        in result["text"]
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


# Phase 3, Task 7: mount and unmount

_V1 = {"id": 1, "name": "Photos", "path": "/data/example/photos", "borg_version": 1}
_V2 = {"id": 2, "name": "Media", "path": "/data/example/media", "borg_version": 2}
_ARCH = {
    "id": 41,
    "borg_id": "ab12cd",
    "name": "media-2026-11-14",
    "start": "2026-11-14T02:00:00Z",
}
_MOUNTED = {
    "mount_id": "m-1",
    "mount_point": "/data/example/mounts/media",
    "mount_type": "borg",
    "source": "media",
}


def _mount_routes(repo):
    return {
        "/api/repositories/": {"repositories": [_V1, _V2]},
        f"/api/repositories/{repo['id']}/archives": {"archives": [_ARCH]},
        "POST /api/mounts/borg": _MOUNTED,
    }


@pytest.mark.unit
def test_mount_borg1_archive_by_name():
    result, api = _run(
        "mount_archive", _mount_routes(_V1), repository="Photos", archive="latest"
    )
    assert api.posts == [
        ("/api/mounts/borg", {"repository_id": 1, "archive_name": "media-2026-11-14"})
    ]
    assert result.text.startswith(
        "✓ Mounted *media-2026-11-14* at /data/example/mounts/media."
    )
    assert "unmount_archive" in result.text
    assert result.data["mount_id"] == "m-1"


@pytest.mark.unit
def test_mount_borg2_sends_the_id():
    _, api = _run(
        "mount_archive", _mount_routes(_V2), repository="Media", archive="latest"
    )
    assert api.posts[0][1]["archive_id"] == "ab12cd"


@pytest.mark.unit
def test_mount_whole_repository():
    result, api = _run("mount_archive", _mount_routes(_V1), repository="Photos")
    assert api.posts == [("/api/mounts/borg", {"repository_id": 1})]
    assert result.text.startswith("✓ Mounted *Photos* at ")


@pytest.mark.unit
def test_mount_takes_no_mount_point():
    from app.mcp.registry import REGISTRY

    assert "mount_point" not in REGISTRY["mount_archive"].input_model.model_fields


_MOUNTS = [
    {**_MOUNTED, "created_at": "2026-11-19T01:00:00Z"},
    {
        **_MOUNTED,
        "mount_id": "m-2",
        "mount_point": "/data/example/mounts/photos",
        "source": "photos",
        "created_at": "2026-11-19T02:00:00Z",
    },
]


@pytest.mark.unit
def test_unmount_by_mount_point():
    routes = {
        "/api/mounts": _MOUNTS,
        "POST /api/mounts/borg/unmount/m-2": {"success": True},
    }
    result, api = _run("unmount_archive", routes, mount="/data/example/mounts/photos")
    assert api.posts == [("/api/mounts/borg/unmount/m-2", None)]
    assert result.text == "✓ Unmounted /data/example/mounts/photos."


@pytest.mark.unit
def test_unmount_only_mount_without_arguments():
    routes = {
        "/api/mounts": _MOUNTS[:1],
        "POST /api/mounts/borg/unmount/m-1": {"success": True},
    }
    _, api = _run("unmount_archive", routes)
    assert api.posts == [("/api/mounts/borg/unmount/m-1", None)]


@pytest.mark.unit
def test_unmount_with_several_mounts_asks():
    result, api = _run("unmount_archive", {"/api/mounts": _MOUNTS})
    assert api.posts == [] and result.is_error
    assert "2 mounts" in result.text and "/data/example/mounts/photos" in result.text


@pytest.mark.unit
def test_unmount_with_nothing_mounted():
    result, api = _run("unmount_archive", {"/api/mounts": []})
    assert api.posts == [] and result.text == "Nothing is mounted."
