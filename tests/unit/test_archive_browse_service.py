import pytest

from app.services.archive_browse_service import build_browse_items


@pytest.mark.unit
def test_build_browse_items_hides_new_borg_ui_canary_paths_only():
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
    legacy_canary_items = build_browse_items(
        items, "data/restore-canaries/repository-2"
    )
    documents_items = build_browse_items(items, "documents")

    assert [item["name"] for item in root_items] == ["data", "documents"]
    assert [item["name"] for item in legacy_canary_items] == [".borgui-canary"]
    assert [item["name"] for item in documents_items] == ["report.pdf"]
