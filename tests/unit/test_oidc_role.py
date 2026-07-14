"""
Unit tests for OIDC role resolution (_resolve_oidc_role).
"""

import pytest

from app.api.auth import _resolve_oidc_role
from app.database.models import SystemSettings


def _settings(admin_groups="admin", default_role="viewer"):
    return SystemSettings(
        oidc_admin_groups=admin_groups, oidc_default_role=default_role
    )


@pytest.mark.unit
class TestResolveOidcRole:
    def test_admin_group_membership_grants_admin_without_role_claim(self):
        """The fix: being in an allow-listed admin group grants admin even when
        the IdP sends no role claim (e.g. Zitadel emits only project roles)."""
        identity = {"role": None, "groups": ["admin"]}
        assert _resolve_oidc_role(identity, _settings()) == "admin"

    def test_no_group_no_role_falls_back_to_default(self):
        identity = {"role": None, "groups": ["viewer"]}
        assert _resolve_oidc_role(identity, _settings()) == "viewer"

    def test_no_admin_groups_configured_never_grants_admin(self):
        identity = {"role": None, "groups": ["admin"]}
        assert _resolve_oidc_role(identity, _settings(admin_groups="")) == "viewer"

    # --- backward compatibility with an explicit role claim ------------------
    def test_admin_role_claim_with_matching_group_stays_admin(self):
        identity = {"role": "admin", "groups": ["admin"]}
        assert _resolve_oidc_role(identity, _settings()) == "admin"

    def test_admin_role_claim_without_matching_group_is_rejected(self):
        identity = {"role": "admin", "groups": ["users"]}
        assert _resolve_oidc_role(identity, _settings()) == "viewer"

    def test_explicit_non_admin_role_claim_is_honored(self):
        identity = {"role": "operator", "groups": ["admin"]}
        assert _resolve_oidc_role(identity, _settings()) == "operator"
