"""
Unit tests for OIDC claim normalization.
"""

import pytest

from app.core.oidc import normalize_groups_claim


@pytest.mark.unit
class TestNormalizeGroupsClaim:
    def test_list_of_strings(self):
        assert normalize_groups_claim(["admin", "viewer"]) == ["admin", "viewer"]

    def test_single_string(self):
        assert normalize_groups_claim("admin") == ["admin"]

    def test_zitadel_role_dict_uses_keys(self):
        """Zitadel emits project roles as an object keyed by role name."""
        claim = {
            "admin": {"310049588908064772": "myorg.zitadel.cloud"},
            "viewer": {"310049588908064772": "myorg.zitadel.cloud"},
        }
        assert normalize_groups_claim(claim) == ["admin", "viewer"]

    def test_empty_and_none(self):
        assert normalize_groups_claim({}) == []
        assert normalize_groups_claim([]) == []
        assert normalize_groups_claim(None) == []
        assert normalize_groups_claim("") == []

    def test_list_drops_non_strings_and_blanks(self):
        assert normalize_groups_claim(["admin", None, "  ", 123]) == ["admin", "123"]
