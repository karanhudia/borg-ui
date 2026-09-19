from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Archive,
    Base,
    Operation,
    PruneComparison,
    Repository,
    SystemSettings,
)
from app.services import prune_compare as pc
from app.services.prune_preview import CandidateResult, DryRunFailed, Retention


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def repo(db):
    r = Repository(
        name="r", path="/tmp/r", encryption="none", compression="lz4", borg_version=1
    )
    db.add(r)
    db.add(SystemSettings())
    db.commit()
    # _result()'s fake operation always carries id 99; a real row satisfies
    # the FK this fixture enforces (PRAGMA foreign_keys=ON).
    db.add(
        Operation(
            id=99,
            repository_id=r.id,
            kind="prune",
            category="maintenance",
            status="completed",
            trigger="manual",
            priority=0,
            run_id="r",
        )
    )
    db.commit()
    return r


def _archives(db, repo, n):
    offset = db.query(Archive).filter(Archive.repository_id == repo.id).count()
    rows = []
    for j in range(n):
        i = offset + j
        a = Archive(
            repository_id=repo.id,
            name=f"a{i}",
            series=f"a{i}",
            borg_id=f"{i:064x}",
            start=datetime(2026, 9, 1) + timedelta(days=i),
            deduplicated_size=10 * (i + 1),
            first_seen_at=datetime(2026, 9, 1),
            last_seen_at=datetime(2026, 9, 1),
        )
        db.add(a)
        rows.append(a)
    db.commit()
    return rows


_NO_POLICY = {
    "source": "default",
    "keep_hourly": 0,
    "keep_daily": 0,
    "keep_weekly": 0,
    "keep_monthly": 0,
    "keep_quarterly": 0,
    "keep_yearly": 0,
    "keep_within": None,
}


def _result(kept, deleted, freed, partial=False):
    op = type("Op", (), {"id": 99})()
    return CandidateResult(
        operation=op,
        log="",
        joined=[],
        candidates=[],
        partial_measure=partial,
        freed_at_least=freed,
        kept_count=kept,
        deleted_count=deleted,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lost_size_is_stored_with_the_index_and_null_without_it(
    db, repo, monkeypatch
):
    """Pro with an indexed history stores step 5's total; every other plan
    stores null and the row carries the floor alone (spec 4.5)."""
    monkeypatch.setattr(pc, "retention_defaults", lambda db, r: {"source": "default"})
    _archives(db, repo, 3)

    monkeypatch.setattr(pc, "lost_size_estimate", lambda db, r, c: 4096)
    fake = AsyncMock(side_effect=[_result(2, 1, 30) for _ in range(3)])
    with patch.object(pc, "run_candidate", new=fake):
        rows = await pc.run_comparison(db, repo, run_id="run", depends_on_id=5)
    measured = [r for r in rows if r.retention is not None]
    assert measured and {r.lost_size for r in measured} == {4096}

    monkeypatch.setattr(pc, "lost_size_estimate", lambda db, r, c: None)
    fake = AsyncMock(side_effect=[_result(2, 1, 30) for _ in range(3)])
    with patch.object(pc, "run_candidate", new=fake):
        rows = await pc.run_comparison(db, repo, run_id="run", depends_on_id=5)
    measured = [r for r in rows if r.retention is not None]
    assert {r.lost_size for r in measured} == {None}
    assert {r.freed_at_least for r in measured} == {30}


@pytest.mark.unit
def test_candidates_start_with_current_and_drop_an_equal_preset(db, repo, monkeypatch):
    monkeypatch.setattr(
        pc,
        "retention_defaults",
        lambda db, r: {
            "source": "plan",
            "plan_name": "p",
            "keep_hourly": 0,
            "keep_daily": 7,
            "keep_weekly": 4,
            "keep_monthly": 6,
            "keep_quarterly": 0,
            "keep_yearly": 1,
            "keep_within": None,
        },
    )
    keys = [k for k, _, _ in pc.candidates(db, repo)]
    assert keys == ["current", "longer", "wide"]


@pytest.mark.unit
def test_candidates_without_a_policy_carry_a_none_retention(db, repo, monkeypatch):
    monkeypatch.setattr(
        pc,
        "retention_defaults",
        lambda db, r: {
            "source": "default",
            "keep_hourly": 0,
            "keep_daily": 0,
            "keep_weekly": 0,
            "keep_monthly": 0,
            "keep_quarterly": 0,
            "keep_yearly": 0,
            "keep_within": None,
        },
    )
    rows = pc.candidates(db, repo)
    assert rows[0][0] == "current" and rows[0][2] is None
    assert [k for k, _, _ in rows[1:]] == ["standard", "longer", "wide"]


@pytest.mark.unit
def test_candidates_treat_the_dialog_defaults_as_no_policy(db, repo, monkeypatch):
    """Spec 4.5: with no plan and no manual prune there is no current policy,
    even though retention_defaults prefills the dialog's 7d 4w 6m 1y."""
    monkeypatch.setattr(
        pc,
        "retention_defaults",
        lambda db, r: {
            "source": "default",
            "plan_name": None,
            **Retention().as_params(),
        },
    )
    rows = pc.candidates(db, repo)
    assert rows[0] == ("current", "Current", None)
    assert [k for k, _, _ in rows[1:]] == ["standard", "longer", "wide"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_comparison_skips_a_candidate_whose_dry_run_raised(
    db, repo, monkeypatch
):
    """A Borg failure fails that candidate's inline row, not the comparison."""
    _archives(db, repo, 2)
    monkeypatch.setattr(pc, "retention_defaults", lambda db, r: _NO_POLICY)
    fake = AsyncMock(
        side_effect=[RuntimeError("rc 2"), _result(2, 0, 0), _result(1, 1, 5)]
    )
    with patch.object(pc, "run_candidate", new=fake):
        rows = await pc.run_comparison(db, repo, run_id="run", depends_on_id=None)
    assert {r.candidate for r in rows} == {"current", "longer", "wide"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_comparison_keeps_old_rows_when_every_dry_run_failed(
    db, repo, monkeypatch
):
    _archives(db, repo, 2)
    db.add(
        PruneComparison(
            repository_id=repo.id,
            candidate="standard",
            label="Standard",
            kept_count=1,
            deleted_count=1,
            freed_at_least=5,
            archive_count_at=2,
            computed_at=datetime(2026, 1, 1),
        )
    )
    db.commit()
    monkeypatch.setattr(
        pc,
        "retention_defaults",
        lambda db, r: {"source": "plan", "plan_name": "p", **Retention().as_params()},
    )
    fake = AsyncMock(side_effect=DryRunFailed("boom"))
    with patch.object(pc, "run_candidate", new=fake):
        rows = await pc.run_comparison(db, repo, run_id="run", depends_on_id=None)
    assert rows == []
    assert db.query(PruneComparison).filter_by(repository_id=repo.id).count() == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_comparison_stores_one_row_per_candidate(db, repo, monkeypatch):
    _archives(db, repo, 3)
    monkeypatch.setattr(
        pc,
        "retention_defaults",
        lambda db, r: {
            "source": "default",
            "keep_hourly": 0,
            "keep_daily": 0,
            "keep_weekly": 0,
            "keep_monthly": 0,
            "keep_quarterly": 0,
            "keep_yearly": 0,
            "keep_within": None,
        },
    )
    fake = AsyncMock(
        side_effect=[_result(2, 1, 30), _result(3, 0, 0), _result(1, 2, 50, True)]
    )
    with patch.object(pc, "run_candidate", new=fake):
        rows = await pc.run_comparison(db, repo, run_id="run", depends_on_id=5)
    by_key = {r.candidate: r for r in rows}
    assert set(by_key) == {"current", "standard", "longer", "wide"}
    assert by_key["current"].retention is None
    assert (by_key["current"].kept_count, by_key["current"].deleted_count) == (3, 0)
    assert by_key["current"].operation_id is None
    assert by_key["standard"].freed_at_least == 30
    assert by_key["wide"].partial_measure is True
    assert by_key["wide"].operation_id == 99
    assert all(r.archive_count_at == 3 for r in rows)
    assert fake.call_args_list[0].kwargs == {
        "user_id": None,
        "run_id": "run",
        "depends_on_id": 5,
        "remeasure": False,
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_comparison_replaces_old_rows_and_skips_a_failed_dry_run(
    db, repo, monkeypatch
):
    _archives(db, repo, 2)
    db.add(
        PruneComparison(
            repository_id=repo.id,
            candidate="stale_key",
            label="x",
            kept_count=0,
            deleted_count=0,
            freed_at_least=0,
            archive_count_at=1,
            computed_at=datetime(2026, 1, 1),
        )
    )
    db.commit()
    monkeypatch.setattr(
        pc,
        "retention_defaults",
        lambda db, r: {
            "source": "default",
            "keep_hourly": 0,
            "keep_daily": 0,
            "keep_weekly": 0,
            "keep_monthly": 0,
            "keep_quarterly": 0,
            "keep_yearly": 0,
            "keep_within": None,
        },
    )
    fake = AsyncMock(
        side_effect=[DryRunFailed("boom"), _result(2, 0, 0), _result(1, 1, 5)]
    )
    with patch.object(pc, "run_candidate", new=fake):
        rows = await pc.run_comparison(db, repo, run_id="run", depends_on_id=None)
    keys = {
        r.candidate for r in db.query(PruneComparison).filter_by(repository_id=repo.id)
    }
    assert keys == {"current", "longer", "wide"}
    assert "stale_key" not in keys


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_comparison_keeps_old_rows_when_only_the_no_policy_row_is_left(
    db, repo, monkeypatch
):
    _archives(db, repo, 2)
    db.add(
        PruneComparison(
            repository_id=repo.id,
            candidate="standard",
            label="Standard",
            kept_count=1,
            deleted_count=1,
            freed_at_least=5,
            archive_count_at=2,
            computed_at=datetime(2026, 1, 1),
        )
    )
    db.commit()
    monkeypatch.setattr(pc, "retention_defaults", lambda db, r: _NO_POLICY)
    fake = AsyncMock(side_effect=DryRunFailed("boom"))
    with patch.object(pc, "run_candidate", new=fake):
        rows = await pc.run_comparison(db, repo, run_id="run", depends_on_id=None)
    assert rows == []
    stored = db.query(PruneComparison).filter_by(repository_id=repo.id).all()
    assert [r.candidate for r in stored] == ["standard"]


@pytest.mark.unit
def test_stored_reports_stale_when_the_archive_count_moved(db, repo):
    assert pc.stored(db, repo) == {
        "computed_at": None,
        "archive_count_at": None,
        "stale": True,
        "candidates": [],
    }
    _archives(db, repo, 2)
    db.add(
        PruneComparison(
            repository_id=repo.id,
            candidate="standard",
            label="Standard",
            retention=Retention().as_params(),
            kept_count=1,
            deleted_count=1,
            freed_at_least=20,
            archive_count_at=2,
            computed_at=datetime(2026, 9, 18, 1, 0),
        )
    )
    db.commit()
    payload = pc.stored(db, repo)
    assert payload["stale"] is False
    assert payload["candidates"][0]["key"] == "standard"
    assert payload["candidates"][0]["freed_at_least"] == 20
    assert payload["candidates"][0]["lost_size"] is None
    _archives(db, repo, 1)
    assert pc.stored(db, repo)["stale"] is True


@pytest.mark.unit
def test_space_savings_picks_the_best_row_per_repository_and_drops_zero(db, repo):
    other = Repository(
        name="o", path="/tmp/o", encryption="none", compression="lz4", borg_version=1
    )
    empty = Repository(
        name="e", path="/tmp/e", encryption="none", compression="lz4", borg_version=1
    )
    db.add_all([other, empty])
    db.commit()
    now = datetime(2026, 9, 18)
    db.add_all(
        [
            PruneComparison(
                repository_id=repo.id,
                candidate="standard",
                label="Standard",
                retention={},
                kept_count=1,
                deleted_count=1,
                freed_at_least=20,
                archive_count_at=0,
                computed_at=now,
            ),
            PruneComparison(
                repository_id=repo.id,
                candidate="wide",
                label="Wide",
                retention={},
                kept_count=1,
                deleted_count=1,
                freed_at_least=50,
                archive_count_at=0,
                computed_at=now,
            ),
            PruneComparison(
                repository_id=other.id,
                candidate="wide",
                label="Wide",
                retention={},
                kept_count=1,
                deleted_count=1,
                freed_at_least=70,
                archive_count_at=0,
                computed_at=now,
            ),
            PruneComparison(
                repository_id=empty.id,
                candidate="wide",
                label="Wide",
                retention={},
                kept_count=1,
                deleted_count=0,
                freed_at_least=0,
                archive_count_at=0,
                computed_at=now,
            ),
        ]
    )
    db.commit()
    rows = pc.space_savings(db, [repo, other, empty])
    assert [
        (r["repository_id"], r["candidate"], r["freed_at_least"]) for r in rows
    ] == [(other.id, "wide", 70), (repo.id, "wide", 50)]
    assert (
        rows[0]["repository_name"] == "o" and rows[0]["stale"] is False
    )  # count 0 == archive_count_at 0
