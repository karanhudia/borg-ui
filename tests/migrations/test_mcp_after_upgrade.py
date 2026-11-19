"""Upgrade test for the MCP revision.

From every release before it, an existing personal token stays a personal
token with no MCP level, and the settings row allows MCP up to full access.
"""

import pytest
from sqlalchemy.orm import Session

from app.database.models import ApiToken, SystemSettings
from tests.migrations import upgrade_paths
from tests.migrations.conftest import DIALECTS, require_releases

REVISION = "e4b7c2a9d1f3"
RELEASES = upgrade_paths.releases_before(REVISION) or ["no-release-tags"]
USER_ID, TOKEN_ID, SETTINGS_ID = 811, 812, 813
ROWS = {
    "users": [
        {
            "id": USER_ID,
            "username": "mcp-upgrade",
            "password_hash": "x",
            "is_active": True,
        }
    ],
    "api_tokens": [
        {
            "id": TOKEN_ID,
            "user_id": USER_ID,
            "name": "ci",
            "token_hash": "h",
            "prefix": "borgui_abcde",
        }
    ],
    "system_settings": [{"id": SETTINGS_ID}],
}


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("release", RELEASES)
def test_tokens_stay_personal_and_mcp_is_allowed_after_upgrade(
    release, dialect, upgraded_from
):
    require_releases()
    db = upgraded_from(release, dialect=dialect, rows=ROWS)

    with Session(db.engine) as session:
        token = session.get(ApiToken, TOKEN_ID)
        assert token.kind == "api"
        assert token.access_level is None
        assert token.skip_routine_confirmations is False
        settings = session.get(SystemSettings, SETTINGS_ID)
        assert settings.mcp_enabled is True
        assert settings.mcp_max_access_level == "full"
