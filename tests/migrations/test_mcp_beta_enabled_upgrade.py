"""Upgrade test for revision a9e3c7b1d5f2 (system_settings.mcp_beta_enabled).

From every release before it, the settings row keeps its MCP switch and cap
and starts with the MCP beta off, so nobody gets MCP without asking for it.
"""

import pytest
from sqlalchemy.orm import Session

from app.database.models import SystemSettings
from tests.migrations import upgrade_paths
from tests.migrations.conftest import DIALECTS, require_releases

REVISION = "a9e3c7b1d5f2"
RELEASES = upgrade_paths.releases_before(REVISION) or ["no-release-tags"]
SETTINGS_ID = 821
ROWS = {"system_settings": [{"id": SETTINGS_ID, "mqtt_beta_enabled": True}]}


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("release", RELEASES)
def test_settings_start_with_the_mcp_beta_off(release, dialect, upgraded_from):
    require_releases()
    db = upgraded_from(release, dialect=dialect, rows=ROWS)

    with Session(db.engine) as session:
        settings = session.get(SystemSettings, SETTINGS_ID)
        assert settings.mcp_beta_enabled is False
        assert settings.mqtt_beta_enabled is True
