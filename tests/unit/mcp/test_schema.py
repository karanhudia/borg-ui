"""MCP schema: token kind and level, admin settings, activity rows."""

from datetime import datetime, timezone

import pytest

from app.core.features import FEATURES, Plan
from app.database.models import ApiToken, McpActivity, SystemSettings, User


def _user(db):
    user = User(username="mcp-owner", password_hash="x", is_active=True, role="admin")
    db.add(user)
    db.commit()
    return user


@pytest.mark.unit
def test_mcp_is_a_pro_feature():
    assert FEATURES["mcp"] == Plan.PRO


@pytest.mark.unit
def test_existing_tokens_are_api_tokens(test_db):
    user = _user(test_db)
    token = ApiToken(user_id=user.id, name="ci", token_hash="h", prefix="borgui_abcde")
    test_db.add(token)
    test_db.commit()
    test_db.refresh(token)
    assert token.kind == "api"
    assert token.access_level is None
    assert token.skip_routine_confirmations is False


@pytest.mark.unit
def test_system_settings_defaults_allow_mcp(test_db):
    settings = SystemSettings()
    test_db.add(settings)
    test_db.commit()
    test_db.refresh(settings)
    assert settings.mcp_enabled is True
    assert settings.mcp_max_access_level == "full"


@pytest.mark.unit
def test_activity_survives_connection_delete(test_db):
    user = _user(test_db)
    token = ApiToken(
        user_id=user.id,
        name="Claude on my laptop",
        token_hash="h",
        prefix="borgui_abcde",
        kind="mcp",
        access_level="read",
    )
    test_db.add(token)
    test_db.commit()
    test_db.add(
        McpActivity(
            connection_id=token.id,
            connection_name=token.name,
            user_id=user.id,
            tool="get_overview",
            effective_level="read",
            outcome="ok",
            duration_ms=12,
            created_at=datetime.now(timezone.utc),
        )
    )
    test_db.commit()

    test_db.delete(token)
    test_db.commit()

    row = test_db.query(McpActivity).one()
    assert row.connection_id is None
    assert row.connection_name == "Claude on my laptop"
