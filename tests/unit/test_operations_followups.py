import pytest

from app.services.operations.followups import FOLLOWUPS, chain_for


@pytest.mark.unit
def test_chain_table_matches_spec_7_4():
    assert FOLLOWUPS == {
        "import_connect": ("stats", "archive_sync", "history_index"),
        "backup": ("archive_sync", "history_index", "stats"),
        "prune": ("archive_sync", "history_merge", "stats"),
        "delete_archive": ("archive_sync", "history_merge", "stats"),
        "compact": ("stats",),
        "check": (),
        "wipe": ("archive_sync", "history_merge", "stats"),
        "restore": (),
        "restore_check": (),
        "rclone_sync": (),
        "package_install": (),
        "stats": (),
        "archive_sync": (),
        "history_index": (),
        "history_merge": (),
    }


@pytest.mark.unit
def test_chain_for_filters_to_available_executors():
    assert chain_for("import_connect") == ["stats", "archive_sync", "history_index"]
    assert chain_for("import_connect", available={"stats", "archive_sync"}) == [
        "stats",
        "archive_sync",
    ]
    assert chain_for("prune", available={"stats", "archive_sync"}) == [
        "archive_sync",
        "stats",
    ]
    assert chain_for("check") == []


@pytest.mark.unit
def test_chain_for_rejects_unknown_kind():
    with pytest.raises(ValueError):
        chain_for("bogus")
