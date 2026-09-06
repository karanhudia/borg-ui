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


def test_parse_archive_items_serializes_mtime_with_the_render_zone():
    from app.services.archive_browse_service import parse_archive_items

    stdout = '{"path": "docs/report.txt", "type": "f", "size": 11, "mtime": "2026-07-01T03:00:00"}'

    # UTC provenance (server-side listing under TZ=UTC): naive value gains offset.
    utc = parse_archive_items(stdout, timezone_name="UTC")
    assert utc[0]["mtime"] == "2026-07-01T03:00:00+00:00"

    # Agent-reported zone: naive value converts from that zone to UTC.
    berlin = parse_archive_items(stdout, timezone_name="Europe/Berlin")
    assert berlin[0]["mtime"] == "2026-07-01T01:00:00+00:00"

    # No zone (agent predating timezone reporting): server-local fallback,
    # like #871's last_backup - always offset-carrying, never a naive string.
    fallback = parse_archive_items(stdout)
    assert fallback[0]["mtime"].endswith("+00:00")


def test_parse_archive_items_keeps_unparseable_and_missing_mtime():
    from app.services.archive_browse_service import parse_archive_items

    stdout = (
        '{"path": "a.txt", "type": "f", "mtime": "not-a-time"}\n'
        '{"path": "b.txt", "type": "f"}'
    )
    items = parse_archive_items(stdout, timezone_name="UTC")
    assert items[0]["mtime"] == "not-a-time"
    assert items[1]["mtime"] is None
