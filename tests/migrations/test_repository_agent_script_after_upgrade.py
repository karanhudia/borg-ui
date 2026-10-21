"""Upgrade test for revision c4e532c20d7b (repository_scripts.agent_script_name).

The revision relaxes `script_id` to nullable, which SQLite can only do by
rebuilding repository_scripts. From every release before it, a repository's
library hooks keep their settings, and a hook can then name an agent script
instead of a library one (#1386).
"""

import pytest
from sqlalchemy import insert, inspect, select, text
from sqlalchemy.orm import Session

from app.database.models import RepositoryScript
from tests.migrations import upgrade_paths
from tests.migrations.conftest import DIALECTS, require_releases

REVISION = "c4e532c20d7b"
RELEASES = upgrade_paths.releases_before(REVISION) or ["no-release-tags"]

REPOSITORY = 601
SCRIPT = 602
HOOK = 603
ROWS = {
    "repositories": [{"id": REPOSITORY}],
    "scripts": [{"id": SCRIPT}],
    "repository_scripts": [
        {
            "id": HOOK,
            "repository_id": REPOSITORY,
            "script_id": SCRIPT,
            "hook_type": "pre-backup",
            "execution_order": 2.5,
            "custom_timeout": 900,
        }
    ],
}


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("release", RELEASES)
def test_hooks_keep_their_settings_and_can_name_an_agent_script(
    release, dialect, upgraded_from
):
    require_releases()
    db = upgraded_from(release, dialect=dialect, rows=ROWS)

    with Session(db.engine) as session:
        hook = session.get(RepositoryScript, HOOK)
        assert (hook.repository_id, hook.script_id, hook.hook_type) == (
            REPOSITORY,
            SCRIPT,
            "pre-backup",
        )
        assert (hook.execution_order, hook.custom_timeout) == (2.5, 900)
        assert hook.agent_script_name is None

        session.execute(
            insert(RepositoryScript.__table__).values(
                repository_id=REPOSITORY,
                script_id=None,
                agent_script_name="backup-postgres",
                hook_type="post-backup",
                execution_order=1,
                enabled=True,
                created_at=hook.created_at,
            )
        )
        session.commit()
        names = session.scalars(
            select(RepositoryScript.agent_script_name).where(
                RepositoryScript.repository_id == REPOSITORY,
                RepositoryScript.script_id.is_(None),
            )
        ).all()
        assert names == ["backup-postgres"]

    indexes = {i["name"] for i in inspect(db.engine).get_indexes("repository_scripts")}
    assert {
        "ix_repository_scripts_id",
        "ix_repository_scripts_repository_id",
        "ix_repository_scripts_script_id",
    } <= indexes
    if dialect == "sqlite":
        with db.engine.connect() as connection:
            sql = connection.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'repository_scripts'"
                )
            ).scalar_one()
        assert "AUTOINCREMENT" in sql
