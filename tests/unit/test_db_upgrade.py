"""Tests for the one-time upgrade onto the Alembic baseline.

The Postgres tests are skipped unless BORG_TEST_POSTGRES_URL is set, but they
are not optional detail: SQLite advances its own ids and forgives a missing
setval, so the sequence step can only ever be proven against Postgres.
"""

import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.database.database import Base
from app.database.db_upgrade import (
    _TRANSFORM_SENTINELS,
    _catch_up_source,
    _unresolved_transforms,
    alembic_init,
)
from app.database.models import BackupJob, BackupPlanRun, BackupPlanRunRepository
from app.database.models import Repository, User

POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")
requires_postgres = pytest.mark.skipif(
    not POSTGRES_URL, reason="BORG_TEST_POSTGRES_URL is not set"
)


def _legacy_db(path, populate=None, extra_columns=()):
    """A database as it looks before the cut: the model's tables, no stamp.

    Foreign keys are deliberately left unenforced while building, so a test can
    create the kind of dangling reference a real install accumulated while
    migration 075 had the pragma switched off.
    """
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table, column, ddl in extra_columns:
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))
    if populate:
        session = sessionmaker(bind=engine)()
        populate(session)
        session.commit()
        session.close()
    engine.dispose()
    return engine


def _open(path):
    return sessionmaker(bind=create_engine(f"sqlite:///{path}"))()


@pytest.mark.unit
def test_fresh_install_builds_the_baseline_and_stays_put(tmp_path):
    db = tmp_path / "borg.db"

    report = alembic_init(db)

    assert report.action == "fresh"
    assert report.rows == 0
    assert db.exists()
    # No data means nothing to move aside, so no rollback file is invented.
    assert not (tmp_path / "borg_bak.db").exists()


@pytest.mark.unit
def test_restart_of_a_fresh_install_does_nothing(tmp_path):
    db = tmp_path / "borg.db"
    alembic_init(db)

    assert alembic_init(db).action == "skipped"
    # An empty database is legitimately empty: a third boot must not mistake it
    # for unfinished work and migrate it on top of its own rollback.
    assert alembic_init(db).action == "skipped"
    assert not (tmp_path / "borg_bak.db").exists()


@pytest.mark.unit
def test_transfer_keeps_every_row_and_moves_the_source_aside(tmp_path):
    db = tmp_path / "borg.db"

    def populate(s):
        for i in range(3):
            s.add(Repository(name=f"repo-{i}", path=f"/srv/repo-{i}"))
        s.add(User(username="admin", password_hash="x"))

    _legacy_db(db, populate)

    report = alembic_init(db)

    assert report.action == "transferred"
    assert report.rows == 4
    assert report.source_kept_at == tmp_path / "borg_bak.db"
    assert (tmp_path / "borg_bak.db").exists()
    assert not (tmp_path / "borg_new.db").exists()

    session = _open(db)
    assert session.query(Repository).count() == 3
    assert session.query(User).count() == 1
    assert {r.name for r in session.query(Repository)} == {"repo-0", "repo-1", "repo-2"}
    session.close()


@pytest.mark.unit
def test_restart_after_a_transfer_does_not_touch_the_rollback(tmp_path):
    db = tmp_path / "borg.db"
    _legacy_db(db, lambda s: s.add(Repository(name="r", path="/srv/r")))
    alembic_init(db)
    backup_bytes = (tmp_path / "borg_bak.db").read_bytes()

    assert alembic_init(db).action == "skipped"

    # The rollback is the original database; a restart must not overwrite it
    # with the already migrated one.
    assert (tmp_path / "borg_bak.db").read_bytes() == backup_bytes


@pytest.mark.unit
def test_a_column_no_model_has_is_dropped_and_reported(tmp_path):
    db = tmp_path / "borg.db"
    _legacy_db(
        db,
        lambda s: s.add(User(username="admin", password_hash="x")),
        extra_columns=[("users", "organization_name", "VARCHAR")],
    )

    report = alembic_init(db)

    users = next(t for t in report.tables if t.name == "users")
    # organization_name is in no model, so the copy leaves it behind and reports it.
    # The catch-up ladder can add other columns the baseline dropped (profile_type,
    # from migration 082), dropped and reported the same way -- so assert membership,
    # not the exact set.
    assert "organization_name" in users.dropped_columns
    assert users.rows == 1
    assert any("organization_name" in line for line in report.lines())


@pytest.mark.unit
def test_a_row_pointing_at_a_deleted_row_is_kept_and_its_pointer_cleared(tmp_path):
    db = tmp_path / "borg.db"

    def populate(s):
        s.add(Repository(id=1, name="r", path="/srv/r"))
        s.add(
            BackupPlanRun(
                id=1, backup_plan_id=None, trigger="manual", status="completed"
            )
        )
        s.flush()
        # backup_job_id 999 never existed: exactly what an install collects while
        # foreign keys are silently switched off.
        s.add(
            BackupPlanRunRepository(
                backup_plan_run_id=1, repository_id=1, backup_job_id=999
            )
        )

    _legacy_db(db, populate)

    report = alembic_init(db)

    junction = next(
        t for t in report.tables if t.name == "backup_plan_run_repositories"
    )
    assert junction.orphans_cleared == {"backup_job_id": 1}
    assert junction.rows == 1  # kept, not dropped

    session = _open(db)
    row = session.query(BackupPlanRunRepository).one()
    assert row.backup_job_id is None
    assert row.repository_id == 1
    session.close()


@pytest.mark.unit
def test_a_self_reference_pointing_forward_survives(tmp_path):
    """The case real data cannot prove.

    A row may reference one with a higher id, so no insert order satisfies the
    constraint; the value has to be set after every row exists. No install we
    have has such a row, so only a made-up one covers it.
    """
    db = tmp_path / "borg.db"

    def populate(s):
        s.add(Repository(id=1, name="r", path="/srv/r"))
        s.add(BackupJob(id=1, repository="r", status="failed", retry_source_job_id=2))
        s.add(BackupJob(id=2, repository="r", status="completed"))

    _legacy_db(db, populate)

    report = alembic_init(db)

    assert report.action == "transferred"
    session = _open(db)
    assert session.get(BackupJob, 1).retry_source_job_id == 2
    assert session.get(BackupJob, 2).retry_source_job_id is None
    session.close()


@pytest.mark.unit
def test_an_existing_rollback_is_never_overwritten(tmp_path):
    db = tmp_path / "borg.db"
    _legacy_db(db, lambda s: s.add(Repository(name="r", path="/srv/r")))
    (tmp_path / "borg_bak.db").write_text("an older rollback nobody may lose")

    with pytest.raises(RuntimeError, match="refusing to overwrite the rollback"):
        alembic_init(db)

    assert (tmp_path / "borg_bak.db").read_text() == "an older rollback nobody may lose"
    assert db.exists()


@pytest.mark.unit
def test_the_target_enforces_foreign_keys(tmp_path):
    """Without this the SQLite path would accept what Postgres rejects, and
    every SQLite-only test here would pass while proving nothing."""
    db = tmp_path / "borg.db"
    alembic_init(db)

    from app.database.db_upgrade import _engine

    with _engine(f"sqlite:///{db}").connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


@pytest.mark.unit
@requires_postgres
def test_transfer_to_postgres_advances_every_sequence(tmp_path):
    """SQLite derives the next id from the data; Postgres does not.

    Without setval the first insert that does not name an id collides with a
    transferred row. This cannot be caught on SQLite at all.
    """
    db = tmp_path / "borg.db"

    def populate(s):
        for i in range(1, 4):
            s.add(Repository(id=i, name=f"repo-{i}", path=f"/srv/repo-{i}"))

    _legacy_db(db, populate)
    _reset_postgres()

    report = alembic_init(db, POSTGRES_URL)

    assert report.action == "transferred"
    assert report.sequences_reset > 0

    session = sessionmaker(bind=create_engine(POSTGRES_URL))()
    fresh = Repository(name="after-transfer", path="/srv/new")
    session.add(fresh)
    session.flush()
    assert fresh.id > 3  # would be 1 and collide without setval
    session.rollback()
    session.close()


@pytest.mark.unit
@requires_postgres
def test_a_leftover_sqlite_file_next_to_a_migrated_postgres_is_ignored(tmp_path):
    """Once Postgres is at head it IS the database; a SQLite file in the data dir
    is irrelevant -- it may be a deliberately kept rollback, or one an entrypoint
    script recreated empty. Either way the boot must not stall on it."""
    db = tmp_path / "borg.db"
    _legacy_db(db, lambda s: s.add(Repository(name="r", path="/srv/r")))
    _reset_postgres()
    assert alembic_init(db, POSTGRES_URL).action == "transferred"

    # The source file is still there (the transfer left it as the rollback), and
    # a fresh empty one could even reappear. Neither triggers another transfer.
    assert alembic_init(db, POSTGRES_URL).action == "skipped"
    db.write_bytes(b"")  # an empty file an entrypoint script might recreate
    assert alembic_init(db, POSTGRES_URL).action == "skipped"


def _reset_postgres():
    engine = create_engine(POSTGRES_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.mark.unit
def test_a_pre_transform_source_is_migrated_then_transferred(tmp_path):
    """A database from before migration 034 still keeps its check schedule as
    repositories.check_interval_days, a column the baseline dropped. The catch-up
    runs the legacy ladder on a throwaway copy first, so 034 turns the interval
    into a cron expression before a single row is copied -- the schedule is carried
    forward, not lost, and no manual stop on an intermediate release is needed."""
    db = tmp_path / "borg.db"
    _legacy_db(
        db,
        lambda s: s.add(Repository(id=1, name="r", path="/srv/r")),
        extra_columns=[("repositories", "check_interval_days", "INTEGER")],
    )
    # a weekly schedule stored the old way -- an interval, not yet a cron expression
    with create_engine(f"sqlite:///{db}").begin() as conn:
        conn.execute(
            text("UPDATE repositories SET check_interval_days = 7 WHERE id = 1")
        )

    report = alembic_init(db)

    assert report.action == "transferred"
    session = _open(db)
    # migration 034's conversion: 7 days -> weekly on Sunday at 2 AM
    assert session.get(Repository, 1).check_cron_expression == "0 2 * * 0"
    session.close()

    # the interval was transformed away by the ladder, not dropped by the copy: the
    # copy never saw the column, so it is not among the report's dropped columns.
    repos = next((t for t in report.tables if t.name == "repositories"), None)
    assert "check_interval_days" not in (repos.dropped_columns if repos else [])


@pytest.mark.unit
def test_a_database_too_old_for_the_catch_up_is_refused_and_left_untouched(
    tmp_path, monkeypatch
):
    """The safety net. The ladder is lenient, so a sentinel can survive it -- a
    database older than the oldest migration, or a migration that raised. When one
    does, the upgrade refuses before copying anything: the source is untouched and
    remains the database, with no half-built target and no rollback invented."""
    db = tmp_path / "borg.db"
    _legacy_db(
        db,
        lambda s: s.add(Repository(id=1, name="r", path="/srv/r")),
        extra_columns=[("repositories", "check_interval_days", "INTEGER")],
    )
    # a ladder that could not perform the transform (here: 034 raised and was skipped)
    monkeypatch.setattr(
        "app.database.migrations.run_migrations",
        lambda engine: ["034_convert_check_interval_to_cron"],
    )

    with pytest.raises(RuntimeError, match="older than the automatic upgrade"):
        alembic_init(db)

    assert db.exists()
    assert not (tmp_path / "borg_bak.db").exists()
    assert not (tmp_path / "borg_new.db").exists()
    assert not (tmp_path / "borg_catchup.db").exists()
    cols = {
        c["name"]
        for c in inspect(create_engine(f"sqlite:///{db}")).get_columns("repositories")
    }
    assert "check_interval_days" in cols  # the source was not migrated in place


@pytest.mark.unit
def test_the_whole_legacy_ladder_runs_clean_on_a_representative_schema(tmp_path):
    """The automated twin of running the upgrade against a real database.

    Every one of the 135 frozen migrations either applies or defensively no-ops
    against a populated, current-shaped schema, and none raises. A future migration
    that is not idempotent on an already-migrated database would surface here as a
    non-empty failure list -- rather than as a silent skip the safety net then has
    to catch in production. This is the coverage a faithful "database at version N"
    cannot give us: the old startup built its schema with create_all first, so a
    historical schema cannot be reconstructed from the current models alone."""
    from app.database.migrations import run_migrations

    db = tmp_path / "borg.db"
    _legacy_db(db, lambda s: s.add(Repository(id=1, name="r", path="/srv/r")))

    failed = run_migrations(create_engine(f"sqlite:///{db}"))

    assert failed == [], f"legacy migrations raised: {failed}"


@pytest.mark.unit
def test_a_pre_028_source_is_split_and_keeps_its_original(tmp_path):
    """The second data-moving transform (028). An old database carries a single
    repositories.hook_timeout; the ladder backfills the pre_/post_hook_timeout
    split from it. Unlike 034 the baseline kept hook_timeout, so its value survives
    the copy regardless -- which is why it is not a sentinel -- but the split still
    has to be reproduced, and this proves it end to end."""
    db = tmp_path / "borg.db"
    _legacy_db(db, lambda s: s.add(Repository(id=1, name="r", path="/srv/r")))
    with create_engine(f"sqlite:///{db}").begin() as conn:
        # a source from before the split: the two halves do not exist yet
        conn.execute(text("ALTER TABLE repositories DROP COLUMN pre_hook_timeout"))
        conn.execute(text("ALTER TABLE repositories DROP COLUMN post_hook_timeout"))
        conn.execute(text("UPDATE repositories SET hook_timeout = 120 WHERE id = 1"))

    assert alembic_init(db).action == "transferred"

    with create_engine(f"sqlite:///{db}").connect() as conn:
        row = conn.execute(
            text(
                "SELECT hook_timeout, pre_hook_timeout, post_hook_timeout "
                "FROM repositories WHERE id = 1"
            )
        ).one()
    assert row == (120, 120, 120)


def _boom(*_args, **_kwargs):
    raise AssertionError("the legacy ladder must not run on an Alembic database")


@pytest.mark.unit
def test_an_alembic_database_at_head_is_left_to_alembic_not_the_ladder(
    tmp_path, monkeypatch
):
    """Steady state: a restart of a migrated database does nothing, and never
    reaches for the legacy ladder. A sentinel column added by hand would trip the
    catch-up if it ran -- proof by silence that it does not."""
    db = tmp_path / "borg.db"
    alembic_init(db)  # now Alembic-managed and at head
    with create_engine(f"sqlite:///{db}").begin() as conn:
        conn.execute(
            text("ALTER TABLE repositories ADD COLUMN check_interval_days INT")
        )

    import app.database.migrations as legacy

    monkeypatch.setattr(legacy, "run_migrations", _boom)

    assert alembic_init(db).action == "skipped"


@pytest.mark.unit
def test_an_alembic_database_behind_head_follows_alembic_not_the_ladder(
    tmp_path, monkeypatch
):
    """The durable fork, for the day a second revision exists. A managed database
    that is merely behind head is moved forward by Alembic -- not misread as legacy
    and dragged through the ladder. Simulate a pending revision by reporting the
    baseline as behind head."""
    db = tmp_path / "borg.db"
    alembic_init(db)  # Alembic-managed
    with create_engine(f"sqlite:///{db}").begin() as conn:
        conn.execute(
            text("ALTER TABLE repositories ADD COLUMN check_interval_days INT")
        )

    import app.database.db_upgrade as dbu
    import app.database.migrations as legacy

    monkeypatch.setattr(legacy, "run_migrations", _boom)
    monkeypatch.setattr(dbu, "_is_at_head", lambda engine: False)  # look one behind

    report = alembic_init(db)

    assert report.action == "migrated"
    # the ladder never ran (it would have raised), and the source was upgraded in
    # place -- no transfer, no rollback file, the hand-added column untouched.
    assert not (tmp_path / "borg_bak.db").exists()
    cols = {
        c["name"]
        for c in inspect(create_engine(f"sqlite:///{db}")).get_columns("repositories")
    }
    assert "check_interval_days" in cols


@pytest.mark.unit
def test_catch_up_skips_the_ladder_on_an_already_alembic_source(tmp_path, monkeypatch):
    """The source side of the same rule: the legacy ladder must never run against a
    database that already has alembic_version. It is only reached when an Alembic
    SQLite database is moved into a fresh Postgres (the target is empty, so the
    durable fork does not short-circuit); the ladder would be a no-op there, but it
    must not run at all. Exercise the function directly -- the SQLite-to-SQLite path
    never reaches it, because an Alembic source is caught by the fork first."""
    db = tmp_path / "borg.db"
    alembic_init(db)  # a fresh Alembic-managed database, stamped at head

    import app.database.migrations as legacy

    monkeypatch.setattr(legacy, "run_migrations", _boom)  # blow up if the ladder runs

    catch_up = tmp_path / "borg_catchup.db"
    _catch_up_source(db, catch_up)  # must not raise

    # the snapshot is kept for the transfer to copy from, and it carries the stamp
    assert catch_up.exists()
    with create_engine(f"sqlite:///{catch_up}").connect() as conn:
        assert inspect(conn).has_table("alembic_version")


@pytest.mark.unit
@requires_postgres
def test_an_alembic_sqlite_moves_to_postgres_without_running_the_ladder(
    tmp_path, monkeypatch
):
    """End to end: a SQLite database already on Alembic, then pointed at Postgres,
    copies its rows across without walking the legacy ladder again."""
    db = tmp_path / "borg.db"
    alembic_init(db)  # fresh Alembic SQLite, at head, no rollback file to collide
    session = sessionmaker(bind=create_engine(f"sqlite:///{db}"))()
    session.add(Repository(name="r", path="/srv/r"))
    session.commit()
    session.close()
    _reset_postgres()

    import app.database.migrations as legacy

    monkeypatch.setattr(legacy, "run_migrations", _boom)  # the ladder must not run

    report = alembic_init(db, POSTGRES_URL)

    assert report.action == "transferred"
    session = sessionmaker(bind=create_engine(POSTGRES_URL))()
    assert session.query(Repository).count() == 1
    session.close()


@pytest.mark.unit
def test_unresolved_transforms_ignores_a_fully_migrated_source():
    assert (
        _unresolved_transforms({"repositories": {"id", "check_cron_expression"}}) == []
    )
    assert _unresolved_transforms({}) == []


@pytest.mark.unit
def test_sentinel_columns_are_absent_from_the_baseline():
    """A sentinel only holds while its column is genuinely gone from the baseline.
    If a future baseline re-adds one, the copy would preserve it and the safety net
    would wrongly refuse a healthy database -- catch that here."""
    baseline = {
        name: {c.name for c in table.columns}
        for name, table in Base.metadata.tables.items()
    }
    for table, column, _ in _TRANSFORM_SENTINELS:
        assert column not in baseline.get(table, set()), (
            f"{table}.{column} is a sentinel but still exists in the baseline"
        )
