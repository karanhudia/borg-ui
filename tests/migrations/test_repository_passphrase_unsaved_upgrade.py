"""Upgrade test for revision b4f1d7e2c9a6 (repositories.passphrase_unsaved).

From every release before it, existing repositories keep their passphrase and
start with no "save your passphrase" reminder: only a passphrase Borg UI
generates over MCP sets the flag.
"""

import pytest
from sqlalchemy.orm import Session

from app.database.models import Repository
from tests.migrations import upgrade_paths
from tests.migrations.conftest import DIALECTS, require_releases

REVISION = "b4f1d7e2c9a6"
RELEASES = upgrade_paths.releases_before(REVISION) or ["no-release-tags"]
REPO_ID = 822
ROWS = {
    "repositories": [
        {
            "id": REPO_ID,
            "name": "Upgraded",
            "path": "/data/example/upgraded",
            "encryption": "repokey",
        }
    ]
}


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("release", RELEASES)
def test_existing_repositories_start_without_the_reminder(
    release, dialect, upgraded_from
):
    require_releases()
    db = upgraded_from(release, dialect=dialect, rows=ROWS)

    with Session(db.engine) as session:
        repo = session.get(Repository, REPO_ID)
        assert repo.passphrase_unsaved is False
        assert repo.name == "Upgraded"
