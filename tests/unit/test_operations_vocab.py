import pytest

from app.services.operations import vocab

EXPECTED_KINDS = {
    "import_connect": ("import", False),
    "backup": ("backup", True),
    "restore": ("restore", False),
    "restore_check": ("restore", False),
    "check": ("maintenance", True),
    "prune": ("maintenance", True),
    "compact": ("maintenance", True),
    "delete_archive": ("maintenance", True),
    "wipe": ("maintenance", True),
    "rclone_sync": ("mirror", False),
    "package_install": ("system", False),
    "stats": ("index", False),
    "archive_sync": ("index", False),
    "history_index": ("index", True),
    "history_merge": ("index", False),
}


@pytest.mark.unit
def test_every_kind_has_category_and_exclusivity():
    assert set(vocab.KINDS) == set(EXPECTED_KINDS)
    for kind, (category, exclusive) in EXPECTED_KINDS.items():
        assert vocab.category_for(kind) == category
        assert vocab.is_exclusive(kind) is exclusive
        assert category in vocab.CATEGORIES


@pytest.mark.unit
def test_vocabularies_match_spec():
    assert vocab.CATEGORIES == (
        "import",
        "backup",
        "restore",
        "maintenance",
        "index",
        "mirror",
        "system",
    )
    assert vocab.STATUSES == (
        "queued",
        "running",
        "completed",
        "completed_with_warnings",
        "failed",
        "cancelled",
        "skipped",
    )
    assert vocab.TRIGGERS == (
        "manual",
        "schedule",
        "plan",
        "import",
        "followup",
        "reconcile",
        "retry",
    )
    assert vocab.TERMINAL_STATUSES == frozenset(
        {"completed", "completed_with_warnings", "failed", "cancelled", "skipped"}
    )
    assert vocab.SUCCESS_STATUSES == frozenset({"completed", "completed_with_warnings"})
    assert vocab.INDEX_KINDS == frozenset(
        {"stats", "archive_sync", "history_index", "history_merge"}
    )


@pytest.mark.unit
def test_priorities_by_trigger():
    assert vocab.priority_for_trigger("manual") == 0
    assert vocab.priority_for_trigger("plan") == 0
    assert vocab.priority_for_trigger("import") == 0
    assert vocab.priority_for_trigger("retry") == 0
    assert vocab.priority_for_trigger("schedule") == 5
    assert vocab.priority_for_trigger("followup") == 10
    assert vocab.priority_for_trigger("reconcile") == 20


@pytest.mark.unit
def test_legacy_status_map():
    assert vocab.LEGACY_STATUS_MAP == {
        "pending": "queued",
        "needs_backup": "skipped",
        "running_prune": "running",
        "running_compact": "running",
        "prune_failed": "failed",
        "compact_failed": "failed",
    }


@pytest.mark.unit
def test_validators_reject_unknown_values():
    assert vocab.validate_kind("stats") == "stats"
    with pytest.raises(ValueError):
        vocab.validate_kind("nope")
    with pytest.raises(ValueError):
        vocab.validate_status("pending")
    with pytest.raises(ValueError):
        vocab.validate_trigger("cron")
