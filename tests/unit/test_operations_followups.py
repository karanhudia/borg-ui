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


@pytest.mark.unit
def test_chain_for_drops_history_kinds_for_community():
    from app.services.operations.followups import HISTORY_KINDS

    assert HISTORY_KINDS == {"history_index", "history_merge"}
    assert chain_for("backup", history=False) == ["archive_sync", "stats"]
    assert chain_for("import_connect", history=False) == ["stats", "archive_sync"]
    assert chain_for("backup", history=True) == [
        "archive_sync",
        "history_index",
        "stats",
    ]
    assert chain_for(
        "backup", available={"archive_sync", "history_index"}, history=False
    ) == ["archive_sync"]


@pytest.mark.unit
def test_history_enabled_follows_plan(db_session):
    from app.database.models import LicensingState
    from app.services.operations.followups import history_enabled

    assert history_enabled(db_session) is False
    # get_or_create_licensing_state creates the single row on first access
    # above, so flip that row's plan rather than inserting a second one
    # (LicensingState lookups always take the first row in the table).
    state = db_session.query(LicensingState).first()
    state.plan = "pro"
    state.status = "active"
    db_session.commit()
    assert history_enabled(db_session) is True


@pytest.mark.unit
def test_community_keeps_history_merge_so_removed_archives_are_deleted():
    """history_merge is the only place an Archive row is deleted, so dropping
    it on Community would leave every pruned archive in the table forever.
    Only history_index is plan gated (spec 11.2)."""
    from app.services.operations.followups import PLAN_GATED_KINDS

    assert PLAN_GATED_KINDS == {"history_index"}
    assert chain_for("prune", history=False) == [
        "archive_sync",
        "history_merge",
        "stats",
    ]
    assert chain_for("delete_archive", history=False) == [
        "archive_sync",
        "history_merge",
        "stats",
    ]
    assert chain_for("wipe", history=False) == [
        "archive_sync",
        "history_merge",
        "stats",
    ]
