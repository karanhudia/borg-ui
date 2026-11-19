"""Upgrade test for revision c8d2e5f1a3b7 (backup_plans.prune_scope_to_plan).

Like a4b5c6d7e8f9 the revision adds a NOT NULL column, which SQLite does by
rebuilding backup_plans (where #860 lost plans' repositories, #1303). From
every release before it, plans keep their repositories and scripts and start
with the option off, so their prune still covers the whole repository
(issue #1549).
"""

import pytest
from sqlalchemy import select

from app.database.models import BackupPlan, BackupPlanRepository, BackupPlanScript
from sqlalchemy.orm import Session
from tests.migrations import upgrade_paths
from tests.migrations.conftest import DIALECTS, require_releases

REVISION = "c8d2e5f1a3b7"
RELEASES = upgrade_paths.releases_before(REVISION) or ["no-release-tags"]

PLAN = 600
ROWS = {
    "repositories": [{"id": 601}, {"id": 602}],
    "scripts": [{"id": 603}],
    "backup_plans": [{"id": PLAN, "name": "nightly"}],
    "backup_plan_repositories": [
        {"backup_plan_id": PLAN, "repository_id": 601},
        {"backup_plan_id": PLAN, "repository_id": 602},
    ],
    "backup_plan_scripts": [{"backup_plan_id": PLAN, "script_id": 603}],
}


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("release", RELEASES)
def test_plans_keep_their_links_and_prune_the_whole_repository(
    release, dialect, upgraded_from
):
    require_releases()
    db = upgraded_from(release, dialect=dialect, rows=ROWS)

    with Session(db.engine) as session:
        plan = session.get(BackupPlan, PLAN)
        assert plan.prune_scope_to_plan is False
        repositories = session.scalars(
            select(BackupPlanRepository.repository_id).where(
                BackupPlanRepository.backup_plan_id == PLAN
            )
        ).all()
        assert sorted(repositories) == [601, 602]
        scripts = session.scalars(
            select(BackupPlanScript.script_id).where(
                BackupPlanScript.backup_plan_id == PLAN
            )
        ).all()
        assert scripts == [603]
