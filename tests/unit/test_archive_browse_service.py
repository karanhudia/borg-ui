import pytest

from app.services.archive_browse_service import build_browse_items


@pytest.mark.unit
def test_build_browse_items_marks_new_borg_ui_canary_paths_as_managed():
    items = [
        {
            "path": ".borg-ui/restore-canaries/repository-2/.borgui-canary/manifest.json",
            "type": "f",
            "size": 1,
        },
        {
            "path": "data/restore-canaries/repository-2/.borgui-canary/manifest.json",
            "type": "f",
            "size": 1,
        },
        {"path": "documents/report.pdf", "type": "f", "size": 12},
    ]

    root_items = build_browse_items(items, "")
    canary_root_items = build_browse_items(items, ".borg-ui")
    legacy_canary_items = build_browse_items(
        items, "data/restore-canaries/repository-2"
    )
    documents_items = build_browse_items(items, "documents")

    assert [item["name"] for item in root_items] == [".borg-ui", "data", "documents"]
    assert root_items[0]["managed"] is True
    assert root_items[0]["managed_type"] == "restore_canary"
    assert [item["name"] for item in canary_root_items] == ["restore-canaries"]
    assert canary_root_items[0]["managed_type"] == "restore_canary"
    assert [item["name"] for item in legacy_canary_items] == [".borgui-canary"]
    assert "managed_type" not in legacy_canary_items[0]
    assert [item["name"] for item in documents_items] == ["report.pdf"]
