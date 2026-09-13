"""Preserve existing archive history while adding durable row identities."""

from datetime import datetime

import pytest
from alembic import command
from sqlalchemy import MetaData, Table, inspect, select
from sqlalchemy.orm import Session

from app.database.db_upgrade import _alembic_config, _engine
from app.database.models import Archive, Repository
from app.services.operations.executors.index import apply_listing

PREVIOUS = "e1f2a3b4c5d6"
REVISION = "f2a3b4c5d6e7"


def _migrate(url, target, *, down=False):
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            config = _alembic_config(url)
            config.attributes["connection"] = connection
            (command.downgrade if down else command.upgrade)(config, target)
            connection.commit()
    finally:
        engine.dispose()


@pytest.mark.unit
def test_upgrade_and_downgrade_preserve_history_and_initialize_legacy_identity(
    tmp_path,
):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    engine = _engine(url)
    metadata = MetaData()
    archives = Table("archives", metadata, autoload_with=engine)
    changes = Table("archive_changes", metadata, autoload_with=engine)
    now = datetime(2026, 9, 12)
    with engine.begin() as connection:
        repo_id = connection.execute(
            Repository.__table__.insert().values(name="r", path="/tmp/r")
        ).inserted_primary_key[0]
        archive_id = connection.execute(
            archives.insert().values(
                repository_id=repo_id,
                borg_id="old",
                name="old",
                series="old",
                start=now,
                first_seen_at=now,
                last_seen_at=now,
            )
        ).inserted_primary_key[0]
        connection.execute(
            changes.insert().values(archive_id=archive_id, path="keep", change="added")
        )
    _migrate(url, REVISION)
    with Session(engine) as db:
        row = db.get(Archive, archive_id)
        assert row.generation_id is None
        # An absent legacy row also needs an identity for a fresh merge.
        _, removed = apply_listing(
            db, db.get(Repository, repo_id), [], timezone_name="UTC"
        )
        assert removed == [archive_id]
        generation = row.generation_id
        assert generation
        db.expire_all()
        assert db.get(Archive, archive_id).generation_id == generation
        apply_listing(db, db.get(Repository, repo_id), [], timezone_name="UTC")
        assert row.generation_id == generation
    _migrate(url, PREVIOUS, down=True)
    assert "generation_id" not in {
        c["name"] for c in inspect(engine).get_columns("archives")
    }
    with engine.connect() as connection:
        assert connection.execute(select(changes.c.path)).scalars().all() == ["keep"]
        assert connection.execute(select(archives.c.borg_id)).scalars().all() == ["old"]
    engine.dispose()
