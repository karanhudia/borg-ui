"""Every supported release's database, seeded, survives the current upgrade.

See upgrade_paths.py for how a release's database is built and what the
checks look at. A release is any tag from v2.3.0 on, plus the last release
of each line before Alembic.
"""

import pytest

from tests.migrations import upgrade_paths
from tests.migrations.conftest import DIALECTS, require_releases

RELEASES = upgrade_paths.releases() or ["no-release-tags"]


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("release", RELEASES)
def test_upgrade_keeps_every_row_readable(release, dialect, upgraded_from):
    require_releases()
    db = upgraded_from(release, dialect=dialect)
    upgrade_paths.assert_upgrade_kept_the_data(db.source, db.url)
