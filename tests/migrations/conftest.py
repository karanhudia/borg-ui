from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from tests.migrations import upgrade_paths
from tests.migrations.upgrade_paths import ReleaseDatabase

DIALECTS = ["sqlite", "postgresql"]


def require_releases() -> list[str]:
    """The releases to test from; fails in CI, skips elsewhere, without tags."""
    found = upgrade_paths.releases()
    missing = upgrade_paths.missing_releases()
    if found and not missing:
        return found
    reason = (
        "release tags not found (fetch them with `git fetch --tags <upstream>`)"
        if not found
        else f"release tags missing: {', '.join(missing)}"
    )
    if upgrade_paths.tags_required():
        pytest.fail(reason)
    pytest.skip(reason)


def postgres_url(dialect: str) -> str | None:
    if dialect == "sqlite":
        return None
    if not upgrade_paths.POSTGRES_URL:
        pytest.skip("BORG_TEST_POSTGRES_URL is not set")
    return upgrade_paths.POSTGRES_URL


@pytest.fixture(scope="session")
def release_trees(tmp_path_factory):
    """Unpacked release trees, shared by every test of the session."""
    return tmp_path_factory.mktemp("releases")


@dataclass
class UpgradedDatabase:
    """A release's database after the current upgrade ran on it."""

    source: ReleaseDatabase
    url: str
    engine: Engine


@pytest.fixture
def upgraded_from(release_trees, tmp_path):
    """Build a database with a release's own code, add rows, upgrade it.

        def test_my_revision(upgraded_from):
            db = upgraded_from("v2.3.0", rows={"repositories": [{"name": "a"}]})

    Every table also gets one generated row; a database from before Alembic
    gets one orphan per foreign key as well. `rows` values fill only the
    columns given; the rest are generated, foreign keys pointing at the
    generated rows. Give an `id` to point another added row at this one.
    The added rows' keys are in `db.source.added`. A release that
    does not have one of the tables yet is skipped.
    """
    engines = []

    def build(release: str, *, dialect: str = "sqlite", rows: dict | None = None):
        url = postgres_url(dialect)
        work = tmp_path / f"{release}-{dialect}-{len(engines)}"
        source = upgrade_paths.build_release(
            release, release_trees, work, postgres_url=url, rows=rows
        )
        if source.missing_tables:
            pytest.skip(f"{release} has no {', '.join(source.missing_tables)}")
        upgraded = upgrade_paths.upgrade(source, postgres_url=url)
        engine = create_engine(upgraded)
        engines.append(engine)
        return UpgradedDatabase(source=source, url=upgraded, engine=engine)

    yield build
    for engine in engines:
        engine.dispose()
