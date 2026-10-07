"""Upgrade test for revision a4b5c6d7e8f9 (backup_plans.run_restore_check_after).

The revision adds a NOT NULL column, which SQLite can only do by rebuilding
backup_plans. That rebuild is where #860 lost every plan's repositories
(#1303). From every release before it, plans keep their repositories and
scripts and start with the new option off.
"""

import pytest
from sqlalchemy import select

from app.database.models import BackupPlan, BackupPlanRepository, BackupPlanScript
from sqlalchemy.orm import Session
from tests.migrations import upgrade_paths
from tests.migrations.conftest import DIALECTS, require_releases

REVISION = "a4b5c6d7e8f9"
RELEASES = upgrade_paths.releases_before(REVISION) or ["no-release-tags"]

PLAN = 500
ROWS = {
    "repositories": [{"id": 501}, {"id": 502}],
    "scripts": [{"id": 503}],
    "backup_plans": [{"id": PLAN, "name": "nightly"}],
    "backup_plan_repositories": [
        {"backup_plan_id": PLAN, "repository_id": 501},
        {"backup_plan_id": PLAN, "repository_id": 502},
    ],
    "backup_plan_scripts": [{"backup_plan_id": PLAN, "script_id": 503}],
}


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("release", RELEASES)
def test_plans_keep_their_links_and_start_with_the_option_off(
    release, dialect, upgraded_from
):
    require_releases()
    db = upgraded_from(release, dialect=dialect, rows=ROWS)

    with Session(db.engine) as session:
        plan = session.get(BackupPlan, PLAN)
        assert plan.run_restore_check_after is False
        repositories = session.scalars(
            select(BackupPlanRepository.repository_id).where(
                BackupPlanRepository.backup_plan_id == PLAN
            )
        ).all()
        assert sorted(repositories) == [501, 502]
        scripts = session.scalars(
            select(BackupPlanScript.script_id).where(
                BackupPlanScript.backup_plan_id == PLAN
            )
        ).all()
        assert scripts == [503]
