"""Upgrade test for revision d3e8a1c6b2f9 (maintenance concurrency settings).

From every release before the revision, the settings row keeps its backup
limits and gets the old behaviour for maintenance: no cap, and maintenance
takes no backup slot.
"""

import pytest
from sqlalchemy.orm import Session

from app.database.models import SystemSettings
from tests.migrations import upgrade_paths
from tests.migrations.conftest import DIALECTS, require_releases

REVISION = "d3e8a1c6b2f9"
RELEASES = upgrade_paths.releases_before(REVISION) or ["no-release-tags"]
SETTINGS_ID = 731
ROWS = {"system_settings": [{"id": SETTINGS_ID, "max_concurrent_backups": 1}]}


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("release", RELEASES)
def test_maintenance_keeps_the_old_behaviour_after_upgrade(
    release, dialect, upgraded_from
):
    require_releases()
    db = upgraded_from(release, dialect=dialect, rows=ROWS)

    with Session(db.engine) as session:
        settings = session.get(SystemSettings, SETTINGS_ID)
        assert settings.max_concurrent_backups == 1
        assert settings.max_concurrent_maintenance is None
        assert settings.maintenance_counts_toward_backup_limit is False
