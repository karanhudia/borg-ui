"""
Unit tests for system API endpoints
"""
import base64
from importlib import import_module
from importlib.util import find_spec

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

LICENSING_AVAILABLE = find_spec("app.services.licensing_service") is not None


@pytest.mark.unit
class TestSystemEndpoints:
    """Test system API endpoints"""

    def test_system_info(self, test_client: TestClient, admin_headers):
        response = test_client.get("/api/system/info", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "app_version" in data
        assert "plan" in data
        assert "features" in data
        if LICENSING_AVAILABLE:
            assert "entitlement" in data
            assert "ui_state" in data["entitlement"]

    def test_system_info_without_auth(self, test_client: TestClient):
        response = test_client.get("/api/system/info")

        assert response.status_code == 200

    def test_system_info_uses_reported_versions_and_plan(self, test_client: TestClient, admin_headers):
        plan = MagicMock()
        plan.value = "pro"

        with patch("app.api.system.borg.get_system_info", new=AsyncMock(return_value={"borg_version": "1.2.3"})):
            with patch("app.api.system.borg2.get_system_info", new=AsyncMock(return_value={"success": True, "borg_version": "2.0.0"})):
                with patch("app.api.system.get_current_plan", return_value=plan):
                    response = test_client.get("/api/system/info", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["borg_version"] == "1.2.3"
        assert data["borg2_version"] == "2.0.0"
        assert data["plan"] == "pro"

    def test_system_info_falls_back_when_borg_checks_fail(self, test_client: TestClient, admin_headers):
        plan = MagicMock()
        plan.value = "community"

        with patch("builtins.open", side_effect=FileNotFoundError):
            with patch("app.api.system.borg.get_system_info", new=AsyncMock(side_effect=RuntimeError("boom"))):
                with patch("app.api.system.borg2.get_system_info", new=AsyncMock(side_effect=RuntimeError("boom"))):
                    with patch("app.api.system.get_current_plan", return_value=plan):
                        response = test_client.get("/api/system/info", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["app_version"] == "dev"
        assert data["borg_version"] is None
        assert data["borg2_version"] is None
        assert data["plan"] == "community"

    def test_system_info_reads_version_file(self, test_client: TestClient, admin_headers):
        with patch("app.api.system.open", mock_open(read_data="7.8.9"), create=True):
            with patch("app.api.system.borg.get_system_info", new=AsyncMock(return_value={"borg_version": "1.4.3"})):
                with patch("app.api.system.borg2.get_system_info", new=AsyncMock(return_value={"success": False})):
                    plan = MagicMock()
                    plan.value = "pro"
                    with patch("app.api.system.get_current_plan", return_value=plan):
                        response = test_client.get("/api/system/info", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["app_version"] == "7.8.9"
        assert data["borg_version"] == "1.4.3"
        assert data["borg2_version"] is None
        assert data["plan"] == "pro"

    def test_system_info_returns_safe_fallback_on_unexpected_error(self, test_client: TestClient, admin_headers):
        with patch("app.api.system.get_current_plan", side_effect=RuntimeError("db down")):
            response = test_client.get("/api/system/info", headers=admin_headers)

        assert response.status_code == 200
        expected = {
            "app_version": "unknown",
            "borg_version": None,
            "borg2_version": None,
            "plan": "community",
            "features": {},
        }
        if LICENSING_AVAILABLE:
            expected["feature_access"] = {}
            expected["entitlement"] = {
                "status": "none",
                "is_trial": False,
                "trial_consumed": False,
                "expires_at": None,
                "starts_at": None,
                "refresh_after": None,
                "instance_id": None,
                "entitlement_id": None,
                "license_id": None,
                "customer_id": None,
                "ui_state": "community",
                "last_refresh_at": None,
                "last_refresh_error": None,
            }
        assert response.json() == expected

    def test_system_info_includes_entitlement_summary(self, test_client: TestClient, admin_headers, test_db, monkeypatch):
        """System info should expose the locally validated entitlement summary."""
        if not LICENSING_AVAILABLE:
            pytest.skip("licensing service not available in this branch")

        licensing_service = import_module("app.services.licensing_service")
        from app.config import settings

        get_or_create_licensing_state = licensing_service.get_or_create_licensing_state
        import_offline_entitlement = licensing_service.import_offline_entitlement
        utc_now = licensing_service.utc_now

        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        monkeypatch.setattr(settings, "activation_public_key", base64.b64encode(public_key).decode("utf-8"))
        monkeypatch.setattr(settings, "activation_public_key_file", None)

        state = get_or_create_licensing_state(test_db)
        now = utc_now()
        payload = {
            "entitlement_id": "ent_api_01",
            "instance_id": state.instance_id,
            "customer_id": "cust_api_01",
            "license_id": "lic_api_01",
            "plan": "pro",
            "status": "active",
            "is_trial": True,
            "feature_overrides": [],
            "max_users": 5,
            "issued_at": now.isoformat(),
            "starts_at": now.isoformat(),
            "expires_at": now.replace(year=now.year + 1).isoformat(),
            "refresh_after": now.isoformat(),
            "metadata": {"edition": "official", "channel": "trial"},
            "signature_version": "v1",
        }
        signature = base64.b64encode(
            private_key.sign(licensing_service._canonical_payload(payload))
        ).decode("utf-8")
        import_offline_entitlement(test_db, {"payload": payload, "signature": signature})

        response = test_client.get("/api/system/info", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["plan"] == "pro"
        assert data["entitlement"]["status"] == "active"
        assert data["entitlement"]["is_trial"] is True
        assert data["entitlement"]["instance_id"] == state.instance_id
        assert isinstance(data["feature_access"], dict)
