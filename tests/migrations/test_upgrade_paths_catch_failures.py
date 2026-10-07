"""The path suite fails when an upgrade loses data or leaves it unreadable.

Each test plants a broken change in a copy of the current code and runs the
same build, upgrade and checks as test_upgrade_paths.py, expecting them to
fail and to name what went wrong.
"""

import pytest
from alembic.script import ScriptDirectory

from app.database.db_upgrade import _alembic_config
from tests.migrations import upgrade_paths
from tests.migrations.conftest import DIALECTS, postgres_url, require_releases

LEGACY = upgrade_paths.LEGACY_RELEASES[-1]
CURRENT_LINE = "v2.3.0"

INJECTED = '''"""{doc}"""

import sqlalchemy as sa
from alembic import op

revision = "f00dfeed0001"
down_revision = "{head}"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("{sql}"))


def downgrade():
    pass
'''


def _with_revision(tmp_path, doc: str, sql: str):
    code = upgrade_paths.copy_code(tmp_path / "code")
    head = ScriptDirectory.from_config(_alembic_config("sqlite://")).get_current_head()
    versions = code / "app" / "database" / "alembic" / "versions"
    (versions / "f00dfeed0001_injected.py").write_text(
        INJECTED.format(doc=doc, head=head, sql=sql)
    )
    return code


def _upgrade_with(code, release, dialect, release_trees, tmp_path):
    url = postgres_url(dialect)
    source = upgrade_paths.build_release(
        release, release_trees, tmp_path / "work", postgres_url=url
    )
    return source, upgrade_paths.upgrade(source, postgres_url=url, code=code)


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("release", [LEGACY, CURRENT_LINE])
def test_a_revision_that_loses_rows_fails(release, dialect, release_trees, tmp_path):
    require_releases()
    code = _with_revision(
        tmp_path,
        "A table rebuild that does not copy the rows back.",
        "DELETE FROM backup_plan_repositories",
    )
    source, url = _upgrade_with(code, release, dialect, release_trees, tmp_path)

    with pytest.raises(AssertionError, match=r"lost rows:\n  backup_plan_repositories"):
        upgrade_paths.assert_upgrade_kept_the_data(source, url)


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("release", [LEGACY, CURRENT_LINE])
def test_a_revision_that_clears_references_fails(
    release, dialect, release_trees, tmp_path
):
    require_releases()
    code = _with_revision(
        tmp_path,
        "What a cascading rebuild does to the rows pointing at the table.",
        "UPDATE backup_plan_runs SET backup_plan_id = NULL",
    )
    source, url = _upgrade_with(code, release, dialect, release_trees, tmp_path)

    with pytest.raises(
        AssertionError, match=r"changed references:\n  backup_plan_runs.backup_plan_id"
    ):
        upgrade_paths.assert_upgrade_kept_the_data(source, url)


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("release", [LEGACY, CURRENT_LINE])
def test_a_revision_that_loses_values_fails(release, dialect, release_trees, tmp_path):
    require_releases()
    code = _with_revision(
        tmp_path,
        "Clears every repository's passphrase.",
        "UPDATE repositories SET passphrase = NULL",
    )
    source, url = _upgrade_with(code, release, dialect, release_trees, tmp_path)

    with pytest.raises(
        AssertionError, match=r"changed values:\n  repositories.passphrase"
    ):
        upgrade_paths.assert_upgrade_kept_the_data(source, url)


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("release", [LEGACY, CURRENT_LINE])
def test_a_revision_that_leaves_an_unreadable_value_fails(
    release, dialect, release_trees, tmp_path
):
    require_releases()
    code = _with_revision(
        tmp_path,
        "Writes a passphrase without encrypting it.",
        "UPDATE repositories SET passphrase = 'plaintext'",
    )
    source, url = _upgrade_with(code, release, dialect, release_trees, tmp_path)

    with pytest.raises(AssertionError, match=r"unreadable tables:\n  Repository: "):
        upgrade_paths.assert_upgrade_kept_the_data(source, url)


def test_migrating_sqlite_with_foreign_keys_on_fails(release_trees, tmp_path):
    """The #1303 loss: a batch rebuild with foreign keys on cascades its DROP.

    The migration environment turns them off for SQLite; without that, the
    rebuild of backup_plans in a4b5c6d7e8f9 empties the tables pointing at it
    on the way up from a database that predates Alembic.
    """
    require_releases()
    code = upgrade_paths.copy_code(tmp_path / "code")
    env = code / "app" / "database" / "alembic" / "env.py"
    statement = 'connection.exec_driver_sql("PRAGMA foreign_keys=OFF")'
    source_text = env.read_text()
    assert statement in source_text, "env.py changed; update this test"
    env.write_text(source_text.replace(statement, "pass"))
    source, url = _upgrade_with(code, LEGACY, "sqlite", release_trees, tmp_path)

    with pytest.raises(AssertionError) as failure:
        upgrade_paths.assert_upgrade_kept_the_data(source, url)
    assert "backup_plan_repositories" in str(failure.value)
    assert "backup_plan_scripts" in str(failure.value)
