"""Per-repository index mode vocabulary and filter (spec section 6.8)."""

import pytest

from app.services.operations import index_mode as im


def test_full_keeps_every_index_kind():
    assert im.filter_kinds(
        "full", ["archive_sync", "history_merge", "history_index", "stats"]
    ) == ["archive_sync", "history_merge", "history_index", "stats"]


def test_archives_drops_only_the_history_kinds():
    assert im.filter_kinds(
        "archives", ["archive_sync", "history_merge", "history_index", "stats"]
    ) == ["archive_sync", "stats"]


def test_off_drops_every_index_kind():
    assert (
        im.filter_kinds(
            "off", ["archive_sync", "history_merge", "history_index", "stats"]
        )
        == []
    )


def test_kinds_outside_the_index_category_are_never_dropped():
    # The mode governs derived data, not the work a user asked for. A chain
    # that ever carries a non-index kind keeps it in every mode.
    assert im.filter_kinds("off", ["backup", "stats"]) == ["backup"]


def test_an_unknown_mode_reads_as_the_default():
    # A row written by a newer version, or hand-edited. Indexing everything
    # is the safe reading: the repository keeps working.
    assert im.filter_kinds("nonsense", ["history_index"]) == ["history_index"]


def test_indexes_history():
    assert im.indexes_history("full") is True
    assert im.indexes_history("archives") is False
    assert im.indexes_history("off") is False


def test_mode_of_a_repository_without_the_column_set():
    class Repo:
        index_mode = None

    assert im.mode_of(Repo()) == "full"


@pytest.mark.parametrize("mode", im.INDEX_MODES)
def test_every_mode_has_a_kind_set(mode):
    assert mode in im.MODE_KINDS
