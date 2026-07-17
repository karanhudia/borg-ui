"""Tests for the one-time upgrade onto the Alembic baseline.

The Postgres tests are skipped unless BORG_TEST_POSTGRES_URL is set, but they
are not optional detail: SQLite advances its own ids and forgives a missing
setval, so the sequence step can only ever be proven against Postgres.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database.database import Base
from app.database.db_upgrade import alembic_init
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
    assert users.dropped_columns == ["organization_name"]
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
