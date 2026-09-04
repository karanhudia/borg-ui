import pytest

from app.services.operations.history_fold import Change, fold_pair, fold_sequence


def _d(*changes):
    return {c.path: c for c in changes}


@pytest.mark.unit
class TestFoldTable:
    """One test per row of the spec 8.4 table."""

    def test_added_then_nothing_copies(self):
        r = Change("a", "added", size_after=3)
        assert fold_pair(_d(r), {}) == _d(r)

    def test_added_then_modified_is_added_with_new_size(self):
        out = fold_pair(
            _d(Change("a", "added", size_after=3)),
            _d(Change("a", "modified", size_before=3, size_after=5, mode_changed=True)),
        )
        assert out["a"] == Change(
            "a", "added", size_before=None, size_after=5, mode_changed=True
        )

    def test_added_then_removed_disappears(self):
        out = fold_pair(
            _d(Change("a", "added", size_after=3)),
            _d(Change("a", "removed", size_before=3)),
        )
        assert "a" not in out

    def test_modified_then_nothing_copies(self):
        r = Change("a", "modified", size_before=1, size_after=2)
        assert fold_pair(_d(r), {}) == _d(r)

    def test_modified_then_modified_keeps_first_size_before(self):
        out = fold_pair(
            _d(Change("a", "modified", size_before=1, size_after=2)),
            _d(
                Change("a", "modified", size_before=2, size_after=9, owner_changed=True)
            ),
        )
        assert out["a"] == Change(
            "a", "modified", size_before=1, size_after=9, owner_changed=True
        )

    def test_modified_then_removed_keeps_first_size_before(self):
        out = fold_pair(
            _d(Change("a", "modified", size_before=1, size_after=2)),
            _d(Change("a", "removed", size_before=2)),
        )
        assert out["a"] == Change("a", "removed", size_before=1)

    def test_removed_then_nothing_copies(self):
        r = Change("a", "removed", size_before=4)
        assert fold_pair(_d(r), {}) == _d(r)

    def test_removed_then_added_is_modified(self):
        out = fold_pair(
            _d(Change("a", "removed", size_before=4)),
            _d(Change("a", "added", size_after=7)),
        )
        assert out["a"] == Change("a", "modified", size_before=4, size_after=7)

    def test_summary_then_any_keeps_newer_and_adds_count(self):
        out = fold_pair(
            _d(Change("x/y/z", "summary", summary_count=10)),
            _d(Change("x/y/z", "summary", summary_count=5)),
        )
        assert out["x/y/z"] == Change("x/y/z", "summary", summary_count=15)
        out = fold_pair(_d(Change("x/y/z", "summary", summary_count=10)), {})
        assert out["x/y/z"].summary_count == 10

    def test_flags_are_ored(self):
        out = fold_pair(
            _d(Change("a", "modified", mode_changed=True)),
            _d(Change("a", "modified", owner_changed=True)),
        )
        assert out["a"].mode_changed and out["a"].owner_changed

    def test_untouched_newer_rows_survive(self):
        newer = _d(Change("b", "added", size_after=1))
        assert fold_pair({}, newer) == newer

    def test_inputs_are_not_mutated(self):
        older = _d(Change("a", "added", size_after=3))
        newer = _d(Change("a", "removed", size_before=3))
        fold_pair(older, newer)
        assert "a" in older and "a" in newer


@pytest.mark.unit
def test_fold_sequence_equals_direct_diff_of_endpoints():
    """Three archives: A1 full listing, A2 and A3 deltas. Folding A2 into A3
    must equal a direct A1 to A3 diff; folding all three must equal a full
    listing of A3 (spec 12, test_changes_fold)."""
    a1 = _d(
        Change("a", "added", size_after=10),
        Change("b", "added", size_after=3),
        Change("c", "added", size_after=8),
    )
    a2 = _d(
        Change("a", "modified", size_before=10, size_after=12),
        Change("b", "removed", size_before=3),
        Change("d", "added", size_after=5),
    )
    a3 = _d(
        Change("a", "modified", size_before=12, size_after=20),
        Change("b", "added", size_after=7),
        Change("d", "removed", size_before=5),
        Change("c", "modified", size_before=8, size_after=8, mode_changed=True),
    )
    direct_a1_a3 = _d(
        Change("a", "modified", size_before=10, size_after=20),
        Change("b", "modified", size_before=3, size_after=7),
        Change("c", "modified", size_before=8, size_after=8, mode_changed=True),
    )
    assert fold_sequence([a2, a3]) == direct_a1_a3
    full_a3 = _d(
        Change("a", "added", size_after=20),
        Change("b", "added", size_after=7),
        Change("c", "added", size_after=8, mode_changed=True),
    )
    assert fold_sequence([a1, a2, a3]) == full_a3
    assert fold_sequence([]) == {}
    assert fold_sequence([a1]) == a1


@pytest.mark.unit
class TestRowConversion:
    def test_round_trip_through_row_dict(self):
        from app.services.operations.history_fold import change_to_row_dict

        c = Change("a/b", "modified", size_before=1, size_after=2, owner_changed=True)
        row = change_to_row_dict(c, archive_id=7)
        assert row == {
            "archive_id": 7,
            "path": "a/b",
            "change": "modified",
            "size_before": 1,
            "size_after": 2,
            "mode_changed": False,
            "owner_changed": True,
            "summary_count": None,
        }

    def test_rows_to_changes_reads_orm_rows(self):
        from app.database.models import ArchiveChange
        from app.services.operations.history_fold import rows_to_changes

        rows = [
            ArchiveChange(
                archive_id=1, path="p", change="added", size_after=4, mode_changed=None
            ),
            ArchiveChange(archive_id=1, path="q/r", change="summary", summary_count=3),
        ]
        out = rows_to_changes(rows)
        assert out["p"] == Change("p", "added", size_after=4)
        assert out["q/r"] == Change("q/r", "summary", summary_count=3)
