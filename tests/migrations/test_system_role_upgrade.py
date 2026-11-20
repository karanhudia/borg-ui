"""Upgrade test for revision b4d8f2a6c1e9 (system_role on plans and repositories).

From every release before it, existing plans and repositories keep their data
and start with no system role, so nothing becomes "This machine" by itself.
"""

import pytest
from sqlalchemy.orm import Session

from app.database.models import BackupPlan, Repository
from tests.migrations import upgrade_paths
from tests.migrations.conftest import DIALECTS, require_releases

REVISION = "b4d8f2a6c1e9"
RELEASES = upgrade_paths.releases_before(REVISION) or ["no-release-tags"]
REPO_ID = 7301
PLAN_ID = 7302
ROWS = {
    "repositories": [{"id": REPO_ID, "name": "Old repo", "path": "/backups/old"}],
    "backup_plans": [
        {"id": PLAN_ID, "name": "Old plan", "source_directories": '["/srv"]'}
    ],
}


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("release", RELEASES)
def test_existing_rows_have_no_system_role(release, dialect, upgraded_from):
    require_releases()
    db = upgraded_from(release, dialect=dialect, rows=ROWS)

    with Session(db.engine) as session:
        repo = session.get(Repository, REPO_ID)
        plan = session.get(BackupPlan, PLAN_ID)
        assert repo.name == "Old repo" and repo.system_role is None
        assert plan.name == "Old plan" and plan.system_role is None
