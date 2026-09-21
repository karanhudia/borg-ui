import json
from pathlib import Path

from app.services.prune_preview import Verdict, parse_prune_verdicts

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _wrap_log_json(text: str, prefix: str = "[stderr] ") -> str:
    """The stored form: each line a --log-json record with a stream prefix,
    as app/services/prune_service.py writes its log file."""
    return "\n".join(
        prefix
        + json.dumps(
            {
                "type": "log_message",
                "time": 1789637876.6,
                "message": line,
                "levelname": "INFO",
                "name": "borg.output.list",
            }
        )
        for line in text.splitlines()
        if line
    )


class TestParsePruneVerdicts:
    def test_borg1_lines_join_by_id_and_carry_the_rule(self):
        out = parse_prune_verdicts((FIXTURES / "prune_dry_run_borg1.log").read_text())
        assert out == [
            Verdict(
                "a4bc6debbd7f130fbdb8b637a49cf6e10ae44196e271537c76f4cc79895770d7",
                "daily-4",
                "kept",
                "daily #1",
            ),
            Verdict(
                "9f35416b07a424f7f0ff1624b54cf1df72e07c5efa5f10fc0a8c9f8ab31ff2ba",
                "daily-3",
                "deleted",
                None,
            ),
            Verdict(
                "d0edfe0a5d7cd33a747f8d72cd4b2b87bfa314c3fcd3e275e8a60a9878d372d4",
                "daily-2",
                "deleted",
                None,
            ),
            Verdict(
                "da727048048744c9f9fa3d15fe577ef59d14bf06807e87d5f5c871199e27ee4a",
                "daily-1",
                "kept",
                "daily[oldest] #2",
            ),
        ]

    def test_borg2_series_share_a_name_and_are_told_apart_by_id(self):
        out = parse_prune_verdicts((FIXTURES / "prune_dry_run_borg2.log").read_text())
        assert [v.name for v in out] == ["other", "daily", "daily", "daily", "daily"]
        assert [v.verdict for v in out] == [
            "kept",
            "kept",
            "deleted",
            "deleted",
            "kept",
        ]
        assert len({v.borg_id for v in out}) == 5
        assert out[0].rule == "daily #1"
        assert out[-1].rule == "daily[oldest] #2"

    def test_log_json_records_with_stream_prefix_parse_the_same(self):
        raw = (FIXTURES / "prune_dry_run_borg1.log").read_text()
        assert parse_prune_verdicts(_wrap_log_json(raw)) == parse_prune_verdicts(raw)
        assert parse_prune_verdicts(
            _wrap_log_json(raw, "[stdout] ")
        ) == parse_prune_verdicts(raw)

    def test_name_with_spaces_and_brackets(self):
        line = (
            "Would prune:                                 my [odd] name   "
            "Thu, 2026-09-17 15:07:55 [" + "ab" * 32 + "]"
        )
        out = parse_prune_verdicts(line)
        assert out == [Verdict("ab" * 32, "my [odd] name", "deleted", None)]

    def test_non_verdict_lines_are_skipped(self):
        assert (
            parse_prune_verdicts(
                "Ignoring --stats. It is not supported when using --dry-run.\n\n"
            )
            == []
        )
        assert parse_prune_verdicts("") == []


from unittest.mock import AsyncMock, patch

import pytest

from app.services import prune_preview
from app.services.prune_preview import (
    MEASURE_CAP,
    freed_at_least,
    join_verdicts,
    remeasure_candidates,
)
from tests.unit.test_api_archive_index import _archive, _repo

HEX = lambda n: f"{n:064x}"  # noqa: E731


def _verdicts(*specs):
    return [Verdict(HEX(n), name, verdict, rule) for n, name, verdict, rule in specs]


class TestJoinVerdicts:
    def test_joins_rows_by_borg_id_in_borg_order(self, test_db):
        repo = _repo(test_db)
        a = _archive(test_db, repo, "daily-1", 1)
        a.borg_id = HEX(1)
        b = _archive(test_db, repo, "daily-2", 2)
        b.borg_id = HEX(2)
        test_db.commit()
        out = join_verdicts(
            test_db,
            repo,
            _verdicts(
                (2, "daily-2", "kept", "daily #1"), (1, "daily-1", "deleted", None)
            ),
        )
        assert [(p.id, p.verdict, p.rule) for p in out] == [
            (b.id, "kept", "daily #1"),
            (a.id, "deleted", None),
        ]
        assert out[1].series == "nas" and out[1].deduplicated_size == 100

    def test_unknown_id_keeps_the_line_without_a_row(self, test_db):
        repo = _repo(test_db)
        out = join_verdicts(test_db, repo, _verdicts((9, "ghost", "deleted", None)))
        assert (
            out[0].id is None
            and out[0].deduplicated_size is None
            and out[0].name == "ghost"
        )

    def test_a_row_the_last_listing_reported_removed_is_not_joined(
        self, test_db, monkeypatch
    ):
        repo = _repo(test_db)
        a = _archive(test_db, repo, "gone", 1)
        a.borg_id = HEX(1)
        test_db.commit()
        monkeypatch.setattr(
            prune_preview, "pending_removed_ids", lambda db, rid: {a.id}
        )
        out = join_verdicts(test_db, repo, _verdicts((1, "gone", "deleted", None)))
        assert out[0].id is None


class TestFreedAtLeast:
    def test_sums_measured_candidates_and_skips_unmeasured(self, test_db):
        repo = _repo(test_db)
        a = _archive(test_db, repo, "a", 1, size=100)
        b = _archive(test_db, repo, "b", 2, size=250)
        c = _archive(test_db, repo, "c", 3)
        c.deduplicated_size = None
        test_db.commit()
        assert freed_at_least([a, b, c]) == 350


class TestRemeasureCandidates:
    @pytest.mark.asyncio
    async def test_measures_up_to_the_cap_and_reports_partial(self, test_db):
        repo = _repo(test_db)
        rows = [
            _archive(test_db, repo, f"a{i}", 1 + i % 28) for i in range(MEASURE_CAP + 1)
        ]
        with (
            patch.object(
                prune_preview, "_prepare_repository_borg_env", return_value=({}, None)
            ),
            patch.object(
                prune_preview,
                "fill_archive_info",
                new=AsyncMock(return_value=MEASURE_CAP),
            ) as fill,
        ):
            partial = await remeasure_candidates(test_db, repo, rows)
        assert partial is True
        assert fill.await_args.kwargs["limit"] == MEASURE_CAP
        assert len(fill.await_args.args[2]) == MEASURE_CAP + 1

    @pytest.mark.asyncio
    async def test_partial_when_fewer_were_filled_than_asked(self, test_db):
        repo = _repo(test_db)
        rows = [_archive(test_db, repo, "a", 1), _archive(test_db, repo, "b", 2)]
        with (
            patch.object(
                prune_preview, "_prepare_repository_borg_env", return_value=({}, None)
            ),
            patch.object(
                prune_preview, "fill_archive_info", new=AsyncMock(return_value=1)
            ),
        ):
            assert await remeasure_candidates(test_db, repo, rows) is True

    @pytest.mark.asyncio
    async def test_a_failed_measurement_falls_back_to_stored_values(self, test_db):
        repo = _repo(test_db)
        rows = [_archive(test_db, repo, "a", 1, size=5)]
        with (
            patch.object(
                prune_preview, "_prepare_repository_borg_env", return_value=({}, None)
            ),
            patch.object(
                prune_preview,
                "fill_archive_info",
                new=AsyncMock(
                    side_effect=RuntimeError("Failed to create/acquire the lock")
                ),
            ),
        ):
            assert await remeasure_candidates(test_db, repo, rows) is True
        assert rows[0].deduplicated_size == 5

    @pytest.mark.asyncio
    async def test_not_partial_within_the_cap(self, test_db):
        repo = _repo(test_db)
        rows = [_archive(test_db, repo, "a", 1)]
        with (
            patch.object(
                prune_preview, "_prepare_repository_borg_env", return_value=({}, None)
            ),
            patch.object(
                prune_preview, "fill_archive_info", new=AsyncMock(return_value=1)
            ),
        ):
            assert await remeasure_candidates(test_db, repo, rows) is False


class TestRunCandidate:
    @pytest.mark.asyncio
    async def test_without_remeasure_uses_stored_sizes_and_flags_unmeasured(
        self, test_db
    ):
        """Spec 4.5 and Appendix B: the comparison runs after a backup and
        re-measures nothing; a candidate never measured makes it partial."""
        from datetime import datetime

        from app.services.prune_preview import Retention, run_candidate

        repo = _repo(test_db)
        a = _archive(test_db, repo, "daily-1", 1)
        a.borg_id = HEX(1)
        a.deduplicated_size = 40
        a.stats_measured_at = datetime(2026, 9, 1)
        b = _archive(test_db, repo, "daily-2", 2)
        b.borg_id = HEX(2)
        b.deduplicated_size = None
        b.stats_measured_at = None
        test_db.commit()
        op = type("Op", (), {"status": "completed", "id": 1})()
        with (
            patch.object(
                prune_preview, "run_prune_dry_run", new=AsyncMock(return_value=(op, ""))
            ),
            patch.object(
                prune_preview,
                "parse_prune_verdicts",
                return_value=_verdicts(
                    (1, "daily-1", "deleted", None), (2, "daily-2", "deleted", None)
                ),
            ),
            patch.object(prune_preview, "remeasure_candidates", new=AsyncMock()) as rm,
        ):
            r = await run_candidate(
                test_db, repo, Retention(), user_id=None, remeasure=False
            )
        rm.assert_not_awaited()
        assert (r.freed_at_least, r.partial_measure, r.deleted_count) == (40, True, 2)


from app.database.models import ArchiveChange
from app.services.prune_preview import lost_files


def _change(test_db, archive, path, change, size_before=None, size_after=None):
    test_db.add(
        ArchiveChange(
            archive_id=archive.id,
            path=path,
            change=change,
            size_before=size_before,
            size_after=size_after,
        )
    )
    test_db.commit()


def _series(test_db, repo, *names_days, series="nas"):
    rows = [_archive(test_db, repo, n, d, series=series) for n, d in names_days]
    return {series: rows}


class TestLostFiles:
    def test_path_removed_before_every_survivor_is_lost(self, test_db):
        repo = _repo(test_db)
        by = _series(test_db, repo, ("a1", 1), ("a2", 2), ("a3", 3))
        a1, a2, a3 = by["nas"]
        _change(test_db, a1, "docs/x.txt", "added", size_after=10)
        _change(test_db, a2, "docs/x.txt", "removed", size_before=10)
        out = lost_files(test_db, repo, by, deleted_ids={a1.id, a2.id})
        assert out["total_count"] == 1 and out["total_size"] == 10
        assert out["top"][0]["path"] == "docs/x.txt"
        assert out["top"][0]["last_held_archive_id"] == a1.id
        assert out["top"][0]["last_held_archive_name"] == "a1"
        assert out["by_folder"] == [{"folder": "docs", "count": 1, "size": 10}]
        assert out["incomplete"] is False and out["unindexed_archive_ids"] == []

    def test_path_still_present_at_a_survivor_is_not_lost(self, test_db):
        repo = _repo(test_db)
        by = _series(test_db, repo, ("a1", 1), ("a2", 2), ("a3", 3))
        a1, a2, a3 = by["nas"]
        _change(test_db, a1, "docs/x.txt", "added", size_after=10)
        _change(test_db, a3, "docs/x.txt", "removed", size_before=10)
        # a2 survives and still holds the path (no row: state carries over)
        out = lost_files(test_db, repo, by, deleted_ids={a1.id, a3.id})
        assert out["total_count"] == 0

    def test_re_added_then_removed_again_uses_the_latest_removal(self, test_db):
        repo = _repo(test_db)
        by = _series(test_db, repo, ("a1", 1), ("a2", 2), ("a3", 3), ("a4", 4))
        a1, a2, a3, a4 = by["nas"]
        _change(test_db, a1, "p", "added", size_after=1)
        _change(test_db, a2, "p", "removed", size_before=1)
        _change(test_db, a3, "p", "added", size_after=5)
        _change(test_db, a4, "p", "removed", size_before=5)
        out = lost_files(test_db, repo, by, deleted_ids={a1.id, a2.id, a3.id})
        assert out["total_size"] == 5
        assert out["top"][0]["last_held_archive_id"] == a3.id

    def test_never_removed_path_is_lost_when_the_whole_series_goes(self, test_db):
        """Borg 1 prunes the repository as one set: an old series can lose
        every archive to a newer series' keeps."""
        repo = _repo(test_db)
        by = _series(test_db, repo, ("old-1", 1), ("old-2", 2), series="old")
        o1, o2 = by["old"]
        _change(test_db, o1, "keep/me", "added", size_after=7)
        out = lost_files(test_db, repo, by, deleted_ids={o1.id, o2.id})
        assert (
            out["total_count"] == 1 and out["top"][0]["last_held_archive_id"] == o2.id
        )

    def test_path_a_survivor_of_another_series_holds_is_not_lost(self, test_db):
        # A renamed plan: the old series goes, the new one still holds the file.
        repo = _repo(test_db)
        by = {}
        by.update(_series(test_db, repo, ("n1", 1), ("n2", 2), series="nas"))
        by.update(_series(test_db, repo, ("d1", 3), ("d2", 4), series="docs"))
        n1, n2 = by["nas"]
        d1, d2 = by["docs"]
        _change(test_db, n1, "shared", "added", size_after=3)
        _change(test_db, n1, "gone", "added", size_after=5)
        _change(test_db, d1, "shared", "added", size_after=3)
        # "shared" survives in docs (d1 and d2 keep it); "gone" was only ever in nas
        out = lost_files(test_db, repo, by, deleted_ids={n1.id, n2.id})
        assert [f["path"] for f in out["top"]] == ["gone"]
        assert out["total_count"] == 1 and out["top"][0]["series"] == "nas"
        assert out["moved_count"] == 0

    def test_a_path_two_series_both_lose_is_one_file_held_last_by_the_newer(
        self, test_db
    ):
        repo = _repo(test_db)
        by = {}
        by.update(_series(test_db, repo, ("n1", 1), ("n2", 2), series="nas"))
        by.update(_series(test_db, repo, ("d1", 3), ("d2", 4), series="docs"))
        n1, n2 = by["nas"]
        d1, d2 = by["docs"]
        _change(test_db, n1, "p", "added", size_after=7)
        _change(test_db, d1, "p", "added", size_after=7)
        out = lost_files(test_db, repo, by, deleted_ids={n1.id, n2.id, d1.id, d2.id})
        assert out["total_count"] == 1 and out["total_size"] == 7
        assert out["top"][0]["last_held_archive_name"] == "d2"

    def test_same_name_and_size_under_another_path_is_moved_not_lost(self, test_db):
        # The source was remounted: March backed up "Users/x", everything
        # since backs up "local/Users/x". Same file, and it survives.
        repo = _repo(test_db)
        by = {}
        by.update(_series(test_db, repo, ("old", 1), series="old"))
        by.update(_series(test_db, repo, ("new", 2), series="new"))
        old = by["old"][0]
        new = by["new"][0]
        _change(test_db, old, "Users/x/movie.mp4", "added", size_after=100)
        _change(test_db, old, "Users/x/notes.txt", "added", size_after=7)
        _change(test_db, new, "local/Users/x/movie.mp4", "added", size_after=100)
        _change(test_db, new, "local/Users/x/notes.txt", "added", size_after=8)
        out = lost_files(test_db, repo, by, deleted_ids={old.id})
        assert [f["path"] for f in out["top"]] == ["Users/x/notes.txt"]
        assert (out["total_count"], out["total_size"]) == (1, 7)
        assert (out["moved_count"], out["moved_size"]) == (1, 100)

    def test_one_survivor_rescues_one_file_not_every_namesake(self, test_db):
        # Two different files of the same name and byte count: one survivor
        # under a new prefix accounts for one of them, the other is lost.
        repo = _repo(test_db)
        by = {}
        by.update(_series(test_db, repo, ("old", 1), series="old"))
        by.update(_series(test_db, repo, ("new", 2), series="new"))
        old, new = by["old"][0], by["new"][0]
        _change(test_db, old, "a/index.html", "added", size_after=100)
        _change(test_db, old, "b/index.html", "added", size_after=100)
        _change(test_db, new, "local/a/index.html", "added", size_after=100)
        out = lost_files(test_db, repo, by, deleted_ids={old.id})
        assert (out["moved_count"], out["total_count"]) == (1, 1)

    def test_a_survivor_that_modified_the_file_no_longer_holds_its_old_size(
        self, test_db
    ):
        # The surviving copy grew to 200 bytes; the deleted 100-byte version
        # is gone for good and must stay in the lost totals.
        repo = _repo(test_db)
        by = {}
        by.update(_series(test_db, repo, ("old", 1), series="old"))
        by.update(_series(test_db, repo, ("n1", 2), ("n2", 3), series="new"))
        old = by["old"][0]
        n1, n2 = by["new"]
        _change(test_db, old, "Users/x/movie.mp4", "added", size_after=100)
        _change(test_db, n1, "local/Users/x/movie.mp4", "added", size_after=100)
        _change(
            test_db,
            n2,
            "local/Users/x/movie.mp4",
            "modified",
            size_before=100,
            size_after=200,
        )
        out = lost_files(test_db, repo, by, deleted_ids={old.id, n1.id})
        assert (out["moved_count"], out["total_count"]) == (0, 1)

    def test_an_unrelated_namesake_of_the_same_size_does_not_rescue(self, test_db):
        # Same name, same byte count, unrelated tree: not the same file, so
        # the deleted one is still lost.
        repo = _repo(test_db)
        by = {}
        by.update(_series(test_db, repo, ("old", 1), series="old"))
        by.update(_series(test_db, repo, ("new", 2), series="new"))
        old, new = by["old"][0], by["new"][0]
        _change(test_db, old, "projects/a/README.md", "added", size_after=100)
        _change(test_db, new, "sites/b/README.md", "added", size_after=100)
        out = lost_files(test_db, repo, by, deleted_ids={old.id})
        assert (out["moved_count"], out["total_count"]) == (0, 1)

    def test_the_estimate_is_none_while_the_index_is_incomplete(
        self, test_db, monkeypatch
    ):
        """An unindexed archive moves the total either way, so there is no
        ceiling to show (spec 4.4/4.5)."""
        from app.services import prune_preview as pp

        repo = _repo(test_db)
        monkeypatch.setattr(pp, "history_capability", lambda db, r, **kw: "available")
        monkeypatch.setattr(
            pp, "lost_files", lambda *a, **k: {"incomplete": True, "total_size": 500}
        )
        assert pp.lost_size_estimate(test_db, repo, []) is None
        monkeypatch.setattr(
            pp, "lost_files", lambda *a, **k: {"incomplete": False, "total_size": 500}
        )
        assert pp.lost_size_estimate(test_db, repo, []) == 500

    def test_a_file_of_unknown_size_is_never_matched_by_name(self, test_db):
        repo = _repo(test_db)
        by = {}
        by.update(_series(test_db, repo, ("old", 1), series="old"))
        by.update(_series(test_db, repo, ("new", 2), series="new"))
        old, new = by["old"][0], by["new"][0]
        _change(test_db, old, "a/notes.txt", "added", size_after=None)
        _change(test_db, new, "local/a/notes.txt", "added", size_after=None)
        out = lost_files(test_db, repo, by, deleted_ids={old.id})
        assert (out["moved_count"], out["total_count"]) == (0, 1)

    def test_a_copy_removed_before_the_survivor_does_not_rescue(self, test_db):
        repo = _repo(test_db)
        by = {}
        by.update(_series(test_db, repo, ("old", 1), series="old"))
        by.update(_series(test_db, repo, ("n1", 2), ("n2", 3), series="new"))
        old = by["old"][0]
        n1, n2 = by["new"]
        _change(test_db, old, "Users/x/movie.mp4", "added", size_after=100)
        _change(test_db, n1, "local/Users/x/movie.mp4", "added", size_after=100)
        _change(test_db, n2, "local/Users/x/movie.mp4", "removed", size_before=100)
        # n1 survives and holds the copy at its time, so the file is safe
        out = lost_files(test_db, repo, by, deleted_ids={old.id})
        assert out["moved_count"] == 1 and out["total_count"] == 0
        # with n1 gone too, the only kept archive has neither path
        out = lost_files(test_db, repo, by, deleted_ids={old.id, n1.id})
        assert out["moved_count"] == 0 and out["total_count"] == 2

    def test_unindexed_survivor_of_another_series_marks_incomplete(self, test_db):
        repo = _repo(test_db)
        by = {}
        by.update(_series(test_db, repo, ("n1", 1), series="nas"))
        by.update(_series(test_db, repo, ("d1", 2), series="docs"))
        n1 = by["nas"][0]
        d1 = by["docs"][0]
        d1.history_state = "pending"
        test_db.commit()
        _change(test_db, n1, "f", "added", size_after=1)
        out = lost_files(test_db, repo, by, deleted_ids={n1.id})
        assert out["total_count"] == 1
        assert out["incomplete"] is True and out["unindexed_archive_ids"] == [d1.id]

    def test_unindexed_archive_of_a_touched_series_marks_incomplete(self, test_db):
        repo = _repo(test_db)
        by = _series(test_db, repo, ("a1", 1), ("a2", 2))
        a1, a2 = by["nas"]
        a2.history_state = "pending"
        test_db.commit()
        out = lost_files(test_db, repo, by, deleted_ids={a1.id})
        assert out["incomplete"] is True and out["unindexed_archive_ids"] == [a2.id]

    def test_untouched_series_is_not_walked_without_candidates(self, test_db):
        repo = _repo(test_db)
        by = {}
        by.update(_series(test_db, repo, ("n1", 1), ("n2", 2), series="nas"))
        by.update(_series(test_db, repo, ("d1", 1), series="docs"))
        d1 = by["docs"][0]
        d1.history_state = "pending"
        test_db.commit()
        out = lost_files(test_db, repo, by, deleted_ids={by["nas"][0].id})
        assert out["incomplete"] is False

    def test_top_is_largest_first_and_capped(self, test_db, monkeypatch):
        monkeypatch.setattr(prune_preview, "TOP_LOST", 2)
        repo = _repo(test_db)
        by = _series(test_db, repo, ("a1", 1), ("a2", 2), ("a3", 3))
        a1, a2, a3 = by["nas"]
        for i, size in enumerate((5, 50, 500)):
            _change(test_db, a1, f"f{i}", "added", size_after=size)
            _change(test_db, a2, f"f{i}", "removed", size_before=size)
        out = lost_files(test_db, repo, by, deleted_ids={a1.id, a2.id})
        assert out["total_count"] == 3 and [t["size"] for t in out["top"]] == [500, 50]
