import importlib
import json
from collections import deque
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.core.security import get_password_hash
from app.database.models import (
    AgentMachine,
    LicensingState,
    Repository,
    RepositoryStorage,
    RcloneSyncJob,
    RcloneRemote,
    SSHConnection,
    SystemSettings,
)
from app.services.rclone_service import RcloneCommandResult
from app.services.rclone_service import RcloneUnavailable
from tests.unit.helpers import assert_auth_required


def _enable_borg_v2(test_db):
    settings_row = test_db.query(SystemSettings).first()
    if settings_row is None:
        settings_row = SystemSettings()
        test_db.add(settings_row)

    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="test-rclone-direct-borg2")
        test_db.add(state)

    state.plan = "pro"
    state.status = "active"
    state.is_trial = False
    test_db.commit()


class FakeRcloneStdout:
    def __init__(self, lines: list[bytes]):
        self._lines = deque(lines)

    async def readline(self) -> bytes:
        if self._lines:
            return self._lines.popleft()
        return b""


class FakeRcloneOAuthProcess:
    def __init__(self, lines: list[bytes], return_code: int = 0):
        self.stdout = FakeRcloneStdout(lines)
        self.returncode = return_code
        self.killed = False

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.killed = True


@pytest.mark.unit
def test_rclone_status_requires_authentication(test_client: TestClient):
    response = test_client.get("/api/rclone/status")

    assert_auth_required(response)


@pytest.mark.unit
def test_rclone_status_reports_unavailable_binary(
    test_client: TestClient, admin_headers, monkeypatch
):
    async def fake_status():
        raise RcloneUnavailable("rclone binary not found")

    monkeypatch.setattr("app.api.rclone.rclone_service.status", fake_status)

    response = test_client.get("/api/rclone/status", headers=admin_headers)

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "version": None,
        "error": "rclone binary not found",
    }


@pytest.mark.unit
def test_list_rclone_providers_includes_popular_guided_sources(
    test_client: TestClient, admin_headers
):
    response = test_client.get("/api/rclone/providers", headers=admin_headers)

    assert response.status_code == 200
    providers = {
        provider["type"]: provider for provider in response.json()["providers"]
    }
    for provider_type in {
        "drive",
        "onedrive",
        "dropbox",
        "box",
        "s3",
        "b2",
        "azureblob",
        "webdav",
        "sftp",
        "local",
        "custom",
    }:
        assert provider_type in providers
    assert providers["drive"]["auth_type"] == "oauth_token"
    assert providers["onedrive"]["auth_type"] == "oauth_token"
    assert providers["custom"]["type_editable"] is True
    assert any(field["name"] == "token" for field in providers["drive"]["fields"])


@pytest.mark.unit
def test_rclone_provider_metadata_reports_borg_ui_oauth_callbacks_without_secrets(
    test_client: TestClient, admin_headers, monkeypatch
):
    monkeypatch.setattr(
        "app.api.rclone.settings.public_base_url",
        "https://backups.example.com/borg-ui",
    )
    monkeypatch.setattr(
        "app.api.rclone.settings.google_drive_oauth_client_id",
        "google-client-id",
    )
    monkeypatch.setattr(
        "app.api.rclone.settings.google_drive_oauth_client_secret",
        "google-client-secret",
    )
    monkeypatch.setattr(
        "app.api.rclone.settings.onedrive_oauth_client_id",
        "onedrive-client-id",
    )
    monkeypatch.setattr(
        "app.api.rclone.settings.onedrive_oauth_client_secret",
        "onedrive-client-secret",
    )

    response = test_client.get("/api/rclone/providers", headers=admin_headers)

    assert response.status_code == 200
    providers = {
        provider["type"]: provider for provider in response.json()["providers"]
    }
    assert providers["drive"]["oauth_mode"] == "borg_ui"
    assert providers["drive"]["oauth_configured"] is True
    assert (
        providers["drive"]["oauth_callback_url"]
        == "https://backups.example.com/borg-ui/api/rclone/oauth/callback/drive"
    )
    assert providers["onedrive"]["oauth_mode"] == "borg_ui"
    assert providers["onedrive"]["oauth_configured"] is True
    assert (
        providers["onedrive"]["oauth_callback_url"]
        == "https://backups.example.com/borg-ui/api/rclone/oauth/callback/onedrive"
    )
    assert providers["dropbox"]["oauth_mode"] == "rclone_loopback"
    serialized = json.dumps(response.json())
    assert "google-client-id" not in serialized
    assert "google-client-secret" not in serialized
    assert "onedrive-client-id" not in serialized
    assert "onedrive-client-secret" not in serialized


@pytest.mark.unit
def test_start_borg_ui_oauth_session_requires_valid_public_base_url(
    test_client: TestClient, admin_headers, monkeypatch
):
    monkeypatch.setattr("app.api.rclone.settings.public_base_url", None)
    monkeypatch.setattr(
        "app.api.rclone.settings.google_drive_oauth_client_id",
        "google-client-id",
    )
    monkeypatch.setattr(
        "app.api.rclone.settings.google_drive_oauth_client_secret",
        "google-client-secret",
    )

    response = test_client.post(
        "/api/rclone/oauth/sessions",
        headers=admin_headers,
        json={"provider": "drive", "mode": "borg_ui"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "key": "backend.errors.rclone.oauthPublicBaseUrlRequired"
    }


@pytest.mark.unit
def test_start_borg_ui_oauth_session_returns_backend_authorize_url_not_loopback(
    test_client: TestClient, admin_headers, monkeypatch
):
    from app.api import rclone as rclone_api

    rclone_api.RCLONE_OAUTH_SESSIONS.clear()
    monkeypatch.setattr(
        "app.api.rclone.settings.public_base_url",
        "https://backups.example.com",
    )
    monkeypatch.setattr(
        "app.api.rclone.settings.google_drive_oauth_client_id",
        "google-client-id",
    )
    monkeypatch.setattr(
        "app.api.rclone.settings.google_drive_oauth_client_secret",
        "google-client-secret",
    )

    response = test_client.post(
        "/api/rclone/oauth/sessions",
        headers=admin_headers,
        json={
            "provider": "drive",
            "mode": "borg_ui",
            "config": {"type": "drive", "scope": "drive.readonly"},
        },
    )

    assert response.status_code == 201
    started = response.json()
    assert started["provider"] == "drive"
    assert started["status"] == "awaiting_callback"
    assert (
        started["authorization_url"]
        == f"/rclone/oauth/sessions/{started['session_id']}/authorize"
    )
    assert started["local_authorization_url"] is None
    assert started["config"] is None
    assert "google-client-id" not in json.dumps(started)
    session = rclone_api.RCLONE_OAUTH_SESSIONS[started["session_id"]]
    assert session["flow"] == "borg_ui"
    assert session["state"]
    assert (
        "accounts.google.com/o/oauth2/v2/auth" in session["provider_authorization_url"]
    )
    assert "127.0.0.1:53682" not in session["provider_authorization_url"]
    rclone_api.RCLONE_OAUTH_SESSIONS.clear()


@pytest.mark.unit
def test_borg_ui_oauth_callback_validates_state_and_exchanges_code(
    test_client: TestClient, admin_headers, monkeypatch
):
    from app.api import rclone as rclone_api

    rclone_api.RCLONE_OAUTH_SESSIONS.clear()
    monkeypatch.setattr(
        "app.api.rclone.settings.public_base_url",
        "https://backups.example.com",
    )
    monkeypatch.setattr(
        "app.api.rclone.settings.google_drive_oauth_client_id",
        "google-client-id",
    )
    monkeypatch.setattr(
        "app.api.rclone.settings.google_drive_oauth_client_secret",
        "google-client-secret",
    )

    async def fake_exchange(provider: str, code: str, redirect_uri: str):
        assert provider == "drive"
        assert code == "provider-code"
        assert (
            redirect_uri
            == "https://backups.example.com/api/rclone/oauth/callback/drive"
        )
        return {
            "access_token": "real-access",
            "refresh_token": "real-refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

    monkeypatch.setattr(
        rclone_api, "_exchange_borg_ui_oauth_code", fake_exchange, raising=False
    )

    start_response = test_client.post(
        "/api/rclone/oauth/sessions",
        headers=admin_headers,
        json={"provider": "drive", "mode": "borg_ui"},
    )
    session_id = start_response.json()["session_id"]
    state = rclone_api.RCLONE_OAUTH_SESSIONS[session_id]["state"]

    bad_state_response = test_client.get(
        "/api/rclone/oauth/callback/drive",
        params={"state": "wrong", "code": "provider-code"},
    )

    assert bad_state_response.status_code == 400
    assert rclone_api.RCLONE_OAUTH_SESSIONS[session_id]["status"] == "awaiting_callback"

    callback_response = test_client.get(
        "/api/rclone/oauth/callback/drive",
        params={"state": state, "code": "provider-code"},
    )

    assert callback_response.status_code == 200
    assert "Authorization complete" in callback_response.text
    poll_response = test_client.get(
        f"/api/rclone/oauth/sessions/{session_id}",
        headers=admin_headers,
    )
    assert poll_response.status_code == 200
    polled = poll_response.json()
    assert polled["status"] == "authorized"
    assert polled["config"]["type"] == "drive"
    assert json.loads(polled["config"]["token"])["refresh_token"] == "real-refresh"
    assert polled["config"]["_borg_ui_oauth_provider"] == "drive"
    assert "google-client-secret" not in json.dumps(polled)
    rclone_api.RCLONE_OAUTH_SESSIONS.clear()


@pytest.mark.unit
def test_onedrive_oauth_callback_discovers_default_drive_for_rclone_config(
    test_client: TestClient, admin_headers, monkeypatch
):
    from app.api import rclone as rclone_api

    rclone_api.RCLONE_OAUTH_SESSIONS.clear()
    monkeypatch.setattr(
        "app.api.rclone.settings.public_base_url",
        "https://backups.example.com",
    )
    monkeypatch.setattr(
        "app.api.rclone.settings.onedrive_oauth_client_id",
        "onedrive-client-id",
    )
    monkeypatch.setattr(
        "app.api.rclone.settings.onedrive_oauth_client_secret",
        "onedrive-client-secret",
    )

    async def fake_exchange(provider: str, code: str, redirect_uri: str):
        assert provider == "onedrive"
        assert code == "provider-code"
        assert (
            redirect_uri
            == "https://backups.example.com/api/rclone/oauth/callback/onedrive"
        )
        return {
            "access_token": "onedrive-access",
            "refresh_token": "onedrive-refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

    async def fake_default_drive(access_token: str):
        assert access_token == "onedrive-access"
        return {"id": "default-drive-id", "driveType": "business"}

    monkeypatch.setattr(
        rclone_api, "_exchange_borg_ui_oauth_code", fake_exchange, raising=False
    )
    monkeypatch.setattr(
        rclone_api, "_fetch_onedrive_default_drive", fake_default_drive, raising=False
    )

    start_response = test_client.post(
        "/api/rclone/oauth/sessions",
        headers=admin_headers,
        json={"provider": "onedrive", "mode": "borg_ui"},
    )
    session_id = start_response.json()["session_id"]
    state = rclone_api.RCLONE_OAUTH_SESSIONS[session_id]["state"]

    callback_response = test_client.get(
        "/api/rclone/oauth/callback/onedrive",
        params={"state": state, "code": "provider-code"},
    )

    assert callback_response.status_code == 200
    poll_response = test_client.get(
        f"/api/rclone/oauth/sessions/{session_id}",
        headers=admin_headers,
    )
    polled = poll_response.json()
    assert polled["status"] == "authorized"
    assert polled["config"]["type"] == "onedrive"
    assert polled["config"]["drive_id"] == "default-drive-id"
    assert polled["config"]["drive_type"] == "business"
    assert json.loads(polled["config"]["token"])["refresh_token"] == "onedrive-refresh"
    assert polled["config"]["_borg_ui_oauth_provider"] == "onedrive"
    rclone_api.RCLONE_OAUTH_SESSIONS.clear()


@pytest.mark.unit
def test_create_borg_ui_oauth_remote_injects_provider_credentials_and_redacts_response(
    test_client: TestClient, admin_headers, tmp_path, monkeypatch
):
    config_root = tmp_path / "rclone"
    monkeypatch.setattr("app.api.rclone.settings.rclone_config_root", str(config_root))
    monkeypatch.setattr(
        "app.api.rclone.settings.google_drive_oauth_client_id",
        "google-client-id",
    )
    monkeypatch.setattr(
        "app.api.rclone.settings.google_drive_oauth_client_secret",
        "google-client-secret",
    )

    response = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "gdrive-prod",
            "provider": "drive",
            "config_source": "managed",
            "redacted_config": {
                "type": "drive",
                "scope": "drive",
                "token": '{"access_token":"real-access","refresh_token":"real-refresh"}',
                "_borg_ui_oauth_provider": "drive",
            },
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["redacted_config"]["token"] == "***"
    serialized = json.dumps(created)
    assert "google-client-id" not in serialized
    assert "google-client-secret" not in serialized
    assert "real-access" not in serialized
    config_body = (config_root / "rclone.conf").read_text(encoding="utf-8")
    assert (
        'token = {"access_token":"real-access","refresh_token":"real-refresh"}'
        in config_body
    )
    assert "client_id = google-client-id" in config_body
    assert "client_secret = google-client-secret" in config_body
    assert "_borg_ui_oauth_provider" not in config_body


@pytest.mark.unit
def test_start_rclone_oauth_session_returns_authorization_url_and_token_config(
    test_client: TestClient, admin_headers, monkeypatch
):
    fake_process = FakeRcloneOAuthProcess(
        [
            b"NOTICE: If your browser doesn't open go to http://127.0.0.1:53682/auth?state=abc\n",
            b"Paste the following into your remote machine --->\n",
            b'{"access_token":"real-access","refresh_token":"real-refresh"}\n',
            b"<---End paste\n",
        ]
    )

    async def fake_start_oauth_process(provider, *, client_id=None, client_secret=None):
        assert provider == "drive"
        assert client_id is None
        assert client_secret is None
        return fake_process

    monkeypatch.setattr("app.api.rclone._start_oauth_process", fake_start_oauth_process)

    response = test_client.post(
        "/api/rclone/oauth/sessions",
        headers=admin_headers,
        json={"provider": "drive"},
    )

    assert response.status_code == 201
    started = response.json()
    assert started["provider"] == "drive"
    assert (
        started["authorization_url"]
        == f"/rclone/oauth/sessions/{started['session_id']}/authorize"
    )
    assert started["local_authorization_url"] == "http://127.0.0.1:53682/auth?state=abc"
    assert started["status"] in {"awaiting_callback", "authorized"}

    poll_response = test_client.get(
        f"/api/rclone/oauth/sessions/{started['session_id']}",
        headers=admin_headers,
    )

    assert poll_response.status_code == 200
    polled = poll_response.json()
    assert polled["status"] == "authorized"
    assert polled["config"] == {
        "type": "drive",
        "token": '{"access_token":"real-access","refresh_token":"real-refresh"}',
    }
    cleanup_response = test_client.delete(
        f"/api/rclone/oauth/sessions/{started['session_id']}",
        headers=admin_headers,
    )
    assert cleanup_response.status_code == 204


@pytest.mark.unit
def test_rclone_oauth_authorization_url_redirects_through_backend(
    test_client: TestClient, admin_token, monkeypatch
):
    from app.api import rclone as rclone_api

    rclone_api.RCLONE_OAUTH_SESSIONS.clear()
    rclone_api.RCLONE_OAUTH_SESSIONS["oauth-proxy"] = {
        "provider": "drive",
        "status": "awaiting_callback",
        "authorization_url": "/rclone/oauth/sessions/oauth-proxy/authorize",
        "local_authorization_url": "http://127.0.0.1:53682/auth?state=abc",
        "config": None,
        "error": None,
        "output": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "ready_event": None,
        "process": None,
        "task": None,
    }

    async def fake_fetch_redirect(url: str) -> str:
        assert url == "http://127.0.0.1:53682/auth?state=abc"
        return "https://accounts.google.com/o/oauth2/v2/auth?state=abc"

    monkeypatch.setattr(
        rclone_api, "_fetch_oauth_authorization_redirect", fake_fetch_redirect
    )

    response = test_client.get(
        f"/api/rclone/oauth/sessions/oauth-proxy/authorize?token={admin_token}",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert (
        response.headers["location"]
        == "https://accounts.google.com/o/oauth2/v2/auth?state=abc"
    )
    rclone_api.RCLONE_OAUTH_SESSIONS.clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_exchange_borg_ui_oauth_code_maps_malformed_json_to_exchange_error(
    monkeypatch,
):
    from app.api import rclone as rclone_api

    monkeypatch.setattr(
        rclone_api.settings,
        "google_drive_oauth_client_id",
        "google-client-id",
    )
    monkeypatch.setattr(
        rclone_api.settings,
        "google_drive_oauth_client_secret",
        "google-client-secret",
    )

    class MalformedJsonResponse:
        status_code = 200

        def json(self):
            raise ValueError("malformed provider response")

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, *_args, **_kwargs):
            return MalformedJsonResponse()

    monkeypatch.setattr(rclone_api.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(HTTPException) as exc_info:
        await rclone_api._exchange_borg_ui_oauth_code(
            "drive",
            "provider-code",
            "https://backups.example.com/api/rclone/oauth/callback/drive",
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == {
        "key": "backend.errors.rclone.oauthCodeExchangeFailed"
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_onedrive_default_drive_maps_malformed_json_to_exchange_error(
    monkeypatch,
):
    from app.api import rclone as rclone_api

    class MalformedJsonResponse:
        status_code = 200

        def json(self):
            raise ValueError("malformed graph response")

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def get(self, *_args, **_kwargs):
            return MalformedJsonResponse()

    monkeypatch.setattr(rclone_api.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(HTTPException) as exc_info:
        await rclone_api._fetch_onedrive_default_drive("access-token")

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == {
        "key": "backend.errors.rclone.oauthCodeExchangeFailed"
    }


@pytest.mark.unit
def test_start_rclone_oauth_session_retires_previous_active_session(
    test_client: TestClient, admin_headers, monkeypatch
):
    from app.api import rclone as rclone_api

    old_process = FakeRcloneOAuthProcess([])
    rclone_api.RCLONE_OAUTH_SESSIONS.clear()
    rclone_api.RCLONE_OAUTH_SESSIONS["old-oauth"] = {
        "provider": "drive",
        "status": "awaiting_callback",
        "authorization_url": "/rclone/oauth/sessions/old-oauth/authorize",
        "local_authorization_url": "http://127.0.0.1:53682/auth?state=old",
        "config": None,
        "error": None,
        "output": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "ready_event": None,
        "process": old_process,
        "task": None,
    }
    new_process = FakeRcloneOAuthProcess(
        [
            b"NOTICE: If your browser doesn't open go to http://127.0.0.1:53682/auth?state=new\n"
        ]
    )

    async def fake_start_oauth_process(provider, *, client_id=None, client_secret=None):
        return new_process

    monkeypatch.setattr("app.api.rclone._start_oauth_process", fake_start_oauth_process)

    response = test_client.post(
        "/api/rclone/oauth/sessions",
        headers=admin_headers,
        json={"provider": "drive"},
    )

    assert response.status_code == 201
    assert old_process.killed is True
    assert "old-oauth" not in rclone_api.RCLONE_OAUTH_SESSIONS
    rclone_api.RCLONE_OAUTH_SESSIONS.clear()


@pytest.mark.unit
def test_rclone_oauth_session_cleanup_prunes_expired_and_excess(monkeypatch):
    from app.api import rclone as rclone_api

    rclone_api.RCLONE_OAUTH_SESSIONS.clear()
    now = datetime(2026, 5, 28, tzinfo=timezone.utc)
    monkeypatch.setattr(rclone_api, "RCLONE_OAUTH_SESSION_TTL_SECONDS", 30)
    monkeypatch.setattr(rclone_api, "RCLONE_OAUTH_MAX_SESSIONS", 1)
    rclone_api.RCLONE_OAUTH_SESSIONS["expired"] = {
        "updated_at": now - timedelta(seconds=31),
        "task": None,
        "process": None,
    }
    rclone_api.RCLONE_OAUTH_SESSIONS["older"] = {
        "updated_at": now,
        "task": None,
        "process": None,
    }
    rclone_api.RCLONE_OAUTH_SESSIONS["newer"] = {
        "updated_at": now,
        "task": None,
        "process": None,
    }

    rclone_api._cleanup_rclone_oauth_sessions(now)

    assert list(rclone_api.RCLONE_OAUTH_SESSIONS) == ["newer"]
    rclone_api.RCLONE_OAUTH_SESSIONS.clear()


@pytest.mark.unit
def test_rclone_oauth_output_is_capped(monkeypatch):
    from app.api import rclone as rclone_api

    monkeypatch.setattr(rclone_api, "RCLONE_OAUTH_OUTPUT_LIMIT_CHARS", 10)
    session = {"output": []}

    rclone_api._append_oauth_output(session, "first-line")
    rclone_api._append_oauth_output(session, "0123456789abcdef")

    assert "".join(session["output"]) == "6789abcdef"
    assert len("".join(session["output"])) <= 10


@pytest.mark.unit
def test_start_rclone_oauth_session_rejects_non_oauth_provider(
    test_client: TestClient, admin_headers
):
    response = test_client.post(
        "/api/rclone/oauth/sessions",
        headers=admin_headers,
        json={"provider": "s3"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "key": "backend.errors.rclone.oauthUnsupported"
    }


@pytest.mark.unit
def test_create_and_list_rclone_remote(
    test_client: TestClient, admin_headers, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "app.api.rclone.settings.rclone_config_root", str(tmp_path / "rclone")
    )

    response = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "prod-s3",
            "provider": "s3",
            "config_source": "managed",
            "redacted_config": {"type": "s3", "provider": "AWS"},
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "prod-s3"
    assert created["provider"] == "s3"
    assert created["config_path"].endswith("/rclone.conf")
    config_file = tmp_path / "rclone" / "rclone.conf"
    config_body = config_file.read_text(encoding="utf-8")
    assert "[prod-s3]" in config_body
    assert "type = s3" in config_body
    assert "provider = AWS" in config_body

    response = test_client.get("/api/rclone/remotes", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["remotes"][0]["name"] == "prod-s3"

    duplicate = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": " prod-s3 ",
            "provider": "s3",
            "config_source": "managed",
            "redacted_config": {"type": "s3", "provider": "AWS"},
        },
    )

    assert duplicate.status_code == 409
    response = test_client.get("/api/rclone/remotes", headers=admin_headers)
    assert response.status_code == 200
    assert [remote["name"] for remote in response.json()["remotes"]] == ["prod-s3"]

    traversal = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "../../escape",
            "provider": "s3",
            "config_source": "managed",
            "redacted_config": {"type": "s3", "provider": "AWS"},
        },
    )

    assert traversal.status_code == 400
    assert (
        traversal.json()["detail"]["key"] == "backend.errors.rclone.invalidRemoteName"
    )


@pytest.mark.unit
def test_list_rclone_remotes_includes_repository_usage_count(
    test_client: TestClient, admin_headers, test_db
):
    used_remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    unused_remote = RcloneRemote(
        name="archive-b2", provider="b2", config_source="managed"
    )
    repositories = [
        Repository(name="Photos", path="/cache/repositories/1", encryption="none"),
        Repository(name="Documents", path="/cache/repositories/2", encryption="none"),
    ]
    test_db.add_all([used_remote, unused_remote, *repositories])
    test_db.commit()
    test_db.refresh(used_remote)
    test_db.refresh(unused_remote)
    for repository in repositories:
        test_db.refresh(repository)

    test_db.add_all(
        [
            RepositoryStorage(
                repository_id=repositories[0].id,
                backend="rclone",
                rclone_remote_id=used_remote.id,
                rclone_remote_path="borg-ui/repositories/photos",
                cache_path="/cache/repositories/1",
                sync_policy="after_success",
                sync_status="current",
            ),
            RepositoryStorage(
                repository_id=repositories[1].id,
                backend="rclone",
                rclone_remote_id=used_remote.id,
                rclone_remote_path="borg-ui/repositories/documents",
                cache_path="/cache/repositories/2",
                sync_policy="after_success",
                sync_status="pending",
            ),
        ]
    )
    test_db.commit()

    response = test_client.get("/api/rclone/remotes", headers=admin_headers)

    assert response.status_code == 200
    remotes = {remote["name"]: remote for remote in response.json()["remotes"]}
    assert remotes["prod-s3"]["usage_count"] == 2
    assert remotes["archive-b2"]["usage_count"] == 0


@pytest.mark.unit
def test_create_rclone_remote_rejects_blank_provider(
    test_client: TestClient, admin_headers
):
    response = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "prod-s3",
            "provider": "   ",
            "config_source": "managed",
            "redacted_config": {"type": "s3", "provider": "AWS"},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {"key": "backend.errors.rclone.invalidProvider"}


@pytest.mark.unit
def test_create_managed_rclone_remote_redacts_sensitive_config_values(
    test_client: TestClient, admin_headers, tmp_path, monkeypatch
):
    config_root = tmp_path / "rclone"
    monkeypatch.setattr("app.api.rclone.settings.rclone_config_root", str(config_root))

    response = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "gdrive-prod",
            "provider": "drive",
            "config_source": "managed",
            "redacted_config": {
                "type": "drive",
                "token": '{"access_token":"real-access","refresh_token":"real-refresh"}',
                "client_secret": "real-client-secret",
                "scope": "drive",
            },
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["redacted_config"]["token"] == "***"
    assert created["redacted_config"]["client_secret"] == "***"
    assert created["redacted_config"]["scope"] == "drive"
    config_body = (config_root / "rclone.conf").read_text(encoding="utf-8")
    assert "real-access" in config_body
    assert "real-refresh" in config_body
    assert "real-client-secret" in config_body

    response = test_client.get("/api/rclone/remotes", headers=admin_headers)

    listed = response.json()["remotes"][0]
    assert listed["redacted_config"]["token"] == "***"
    assert listed["redacted_config"]["client_secret"] == "***"


@pytest.mark.unit
def test_update_managed_rclone_remote_preserves_redacted_existing_secrets(
    test_client: TestClient, admin_headers, tmp_path, monkeypatch
):
    config_root = tmp_path / "rclone"
    monkeypatch.setattr("app.api.rclone.settings.rclone_config_root", str(config_root))

    create_response = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "gdrive-prod",
            "provider": "drive",
            "config_source": "managed",
            "redacted_config": {
                "type": "drive",
                "token": '{"access_token":"real-access","refresh_token":"real-refresh"}',
                "scope": "drive",
            },
        },
    )
    remote_id = create_response.json()["id"]

    response = test_client.put(
        f"/api/rclone/remotes/{remote_id}",
        headers=admin_headers,
        json={
            "name": "gdrive-archive",
            "provider": "drive",
            "redacted_config": {
                "type": "drive",
                "token": "***",
                "scope": "drive.readonly",
            },
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "gdrive-archive"
    assert updated["redacted_config"]["token"] == "***"
    assert updated["redacted_config"]["scope"] == "drive.readonly"
    config_body = (config_root / "rclone.conf").read_text(encoding="utf-8")
    assert "[gdrive-prod]" not in config_body
    assert "[gdrive-archive]" in config_body
    assert "real-access" in config_body
    assert "real-refresh" in config_body
    assert "scope = drive.readonly" in config_body


@pytest.mark.unit
def test_update_managed_rclone_remote_does_not_write_redaction_marker_without_existing_config(
    test_client: TestClient, admin_headers, tmp_path, monkeypatch
):
    config_root = tmp_path / "rclone"
    monkeypatch.setattr("app.api.rclone.settings.rclone_config_root", str(config_root))

    create_response = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "gdrive-prod",
            "provider": "drive",
            "config_source": "managed",
            "redacted_config": {
                "type": "drive",
                "token": '{"access_token":"real-access","refresh_token":"real-refresh"}',
                "scope": "drive",
            },
        },
    )
    remote_id = create_response.json()["id"]
    (config_root / "rclone.conf").unlink()

    response = test_client.put(
        f"/api/rclone/remotes/{remote_id}",
        headers=admin_headers,
        json={"name": "gdrive-archive"},
    )

    assert response.status_code == 200
    config_body = (config_root / "rclone.conf").read_text(encoding="utf-8")
    assert "[gdrive-archive]" in config_body
    assert "type = drive" in config_body
    assert "scope = drive" in config_body
    assert "***" not in config_body
    assert "token =" not in config_body


@pytest.mark.unit
def test_create_managed_rclone_remote_removes_config_file_on_commit_failure(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    config_root = tmp_path / "rclone"
    monkeypatch.setattr("app.api.rclone.settings.rclone_config_root", str(config_root))
    original_commit = test_db.commit
    state = {"failed": False}

    def fail_once():
        if not state["failed"]:
            state["failed"] = True
            raise RuntimeError("database unavailable")
        return original_commit()

    monkeypatch.setattr(test_db, "commit", fail_once)

    response = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "prod-s3",
            "provider": "s3",
            "config_source": "managed",
            "redacted_config": {"type": "s3", "provider": "AWS"},
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "key": "backend.errors.rclone.failedToCreateRemote"
    }
    assert not (config_root / "rclone.conf").exists()


@pytest.mark.unit
def test_update_rclone_remote_renames_managed_config_section(
    test_client: TestClient, admin_headers, tmp_path, monkeypatch
):
    config_root = tmp_path / "rclone"
    monkeypatch.setattr("app.api.rclone.settings.rclone_config_root", str(config_root))

    create_response = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "prod-s3",
            "provider": "s3",
            "config_source": "managed",
            "redacted_config": {"type": "s3", "provider": "AWS"},
        },
    )
    remote_id = create_response.json()["id"]

    response = test_client.put(
        f"/api/rclone/remotes/{remote_id}",
        headers=admin_headers,
        json={
            "name": "archive-b2",
            "provider": "b2",
            "redacted_config": {"type": "b2", "account": "redacted"},
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "archive-b2"
    assert updated["provider"] == "b2"
    config_body = (config_root / "rclone.conf").read_text(encoding="utf-8")
    assert "[prod-s3]" not in config_body
    assert "[archive-b2]" in config_body
    assert "type = b2" in config_body
    assert "account = redacted" in config_body


@pytest.mark.unit
def test_update_rclone_remote_rejects_duplicate_name(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    other = RcloneRemote(name="archive-b2", provider="b2", config_source="managed")
    test_db.add_all([remote, other])
    test_db.commit()
    test_db.refresh(remote)

    response = test_client.put(
        f"/api/rclone/remotes/{remote.id}",
        headers=admin_headers,
        json={"name": " archive-b2 "},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"key": "backend.errors.rclone.remoteExists"}


@pytest.mark.unit
def test_delete_rclone_remote_removes_managed_config_section(
    test_client: TestClient, admin_headers, tmp_path, monkeypatch
):
    config_root = tmp_path / "rclone"
    monkeypatch.setattr("app.api.rclone.settings.rclone_config_root", str(config_root))
    create_response = test_client.post(
        "/api/rclone/remotes",
        headers=admin_headers,
        json={
            "name": "prod-s3",
            "provider": "s3",
            "config_source": "managed",
            "redacted_config": {"type": "s3", "provider": "AWS"},
        },
    )
    remote_id = create_response.json()["id"]

    response = test_client.delete(
        f"/api/rclone/remotes/{remote_id}", headers=admin_headers
    )

    assert response.status_code == 204
    response = test_client.get("/api/rclone/remotes", headers=admin_headers)
    assert response.json()["remotes"] == []
    assert not (config_root / "rclone.conf").exists()


@pytest.mark.unit
def test_delete_rclone_remote_rejects_used_remote(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(
        name="Photos", path="/cache/repositories/1", encryption="none"
    )
    test_db.add_all([remote, repository])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(repository)
    test_db.add(
        RepositoryStorage(
            repository_id=repository.id,
            backend="rclone",
            rclone_remote_id=remote.id,
            rclone_remote_path="borg-ui/photos",
            cache_path="/cache/repositories/1",
            sync_policy="after_success",
            sync_status="current",
        )
    )
    test_db.commit()

    response = test_client.delete(
        f"/api/rclone/remotes/{remote.id}", headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"key": "backend.errors.rclone.remoteInUse"}
    assert test_db.query(RcloneRemote).filter(RcloneRemote.id == remote.id).one()


@pytest.mark.unit
def test_test_remote_updates_status(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)

    monkeypatch.setattr(
        "app.api.rclone.rclone_service.about",
        AsyncMock(return_value={"success": True, "stdout": "ok", "stderr": ""}),
    )

    response = test_client.post(
        f"/api/rclone/remotes/{remote.id}/test", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "connected"
    test_db.refresh(remote)
    assert remote.last_test_status == "connected"


@pytest.mark.unit
def test_browse_remote_returns_redacted_entries(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)

    monkeypatch.setattr(
        "app.api.rclone.rclone_service.lsjson",
        AsyncMock(
            return_value=[
                {
                    "Name": "config",
                    "Path": "borg-ui/repositories/app/config",
                    "IsDir": False,
                }
            ]
        ),
    )

    response = test_client.get(
        f"/api/rclone/remotes/{remote.id}/browse",
        headers=admin_headers,
        params={"path": "borg-ui/repositories/app"},
    )

    assert response.status_code == 200
    assert response.json()["entries"][0]["name"] == "config"


@pytest.mark.unit
def test_browse_remote_returns_paths_relative_to_remote_root(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)

    monkeypatch.setattr(
        "app.api.rclone.rclone_service.lsjson",
        AsyncMock(
            return_value=[
                {"Name": "snapshots", "Path": "snapshots", "IsDir": True, "Size": -1},
                {"Name": "manifest.json", "Path": "manifest.json", "IsDir": False},
            ]
        ),
    )

    response = test_client.get(
        f"/api/rclone/remotes/{remote.id}/browse",
        headers=admin_headers,
        params={"path": "borg-ui"},
    )

    assert response.status_code == 200
    assert response.json()["path"] == "borg-ui"
    assert response.json()["entries"] == [
        {
            "name": "snapshots",
            "path": "borg-ui/snapshots",
            "is_dir": True,
            "size": None,
            "modified": None,
        },
        {
            "name": "manifest.json",
            "path": "borg-ui/manifest.json",
            "is_dir": False,
            "size": None,
            "modified": None,
        },
    ]


@pytest.mark.unit
def test_repository_rclone_status_endpoint(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(
        name="App",
        path="/cache/repositories/1",
        encryption="none",
        repository_type="rclone",
    )
    test_db.add_all([remote, repository])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(repository)
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        rclone_remote_id=remote.id,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path="/cache/repositories/1",
        sync_policy="after_success",
        sync_status="pending",
    )
    test_db.add(storage)
    test_db.commit()

    response = test_client.get(
        f"/api/repositories/{repository.id}/rclone/status", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["rclone_target"] == "prod-s3:borg-ui/repositories/app"
    assert response.json()["sync_status"] == "pending"


@pytest.mark.unit
def test_create_rclone_repository_rejects_client_cache_path(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "App",
            "path": "/client/ignored",
            "encryption": "none",
            "storage_backend": "rclone",
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_cache_path": "/tmp/client-owned-cache",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"] == "backend.errors.rclone.cachePathServerOwned"
    )


@pytest.mark.unit
def test_create_local_repository_with_cloud_mirror_preserves_primary_path_and_syncs(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    repo_path = tmp_path / "repositories" / "app"
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )
    sync = AsyncMock(
        return_value=RcloneCommandResult(
            success=True,
            return_code=0,
            stdout="",
            stderr="",
            command=["rclone", "sync"],
            redacted_command="rclone sync <path> <path>",
        )
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.sync", sync
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Local App",
            "path": str(repo_path),
            "encryption": "none",
            "storage_backend": "local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "after_success",
            "rclone_extra_flags": ["--fast-list"],
        },
    )

    assert response.status_code == 200
    repository = test_db.query(Repository).filter(Repository.name == "Local App").one()
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == str(repo_path)
    assert repository.repository_type == "local"
    assert storage.cache_path == str(repo_path)
    assert storage.sync_direction == "primary_to_remote"
    assert storage.sync_status == "current"
    assert response.json()["repository"]["storage_backend"] == "local"
    assert response.json()["repository"]["rclone_storage"]["rclone_target"] == (
        "prod-s3:borg-ui/repositories/app"
    )
    assert "rclone_cache_path" not in response.json()["repository"]


@pytest.mark.unit
def test_create_local_repository_cloud_mirror_rejects_client_cache_path(
    test_client: TestClient, admin_headers, test_db, tmp_path
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Local App",
            "path": str(tmp_path / "repositories" / "app"),
            "encryption": "none",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_cache_path": "/tmp/client-owned-cache",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"] == "backend.errors.rclone.cachePathServerOwned"
    )


@pytest.mark.unit
def test_create_ssh_repository_with_cloud_mirror_uses_server_owned_mount_strategy(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    connection = SSHConnection(host="storage.example", username="borg", port=22)
    test_db.add_all([remote, connection])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(connection)
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.sync",
        AsyncMock(
            return_value=RcloneCommandResult(
                success=True,
                return_code=0,
                stdout="",
                stderr="",
                command=["rclone", "sync"],
                redacted_command="rclone sync <path> <path>",
            )
        ),
    )
    mount_service = AsyncMock()
    mount_service.active_mounts = {
        "mount-ssh-repo": type(
            "MountInfo", (), {"mount_point": "/tmp/sshfs_mount_9/backups/app"}
        )()
    }
    mount_service.mount_ssh_directory.return_value = (
        "/tmp/sshfs_mount_9",
        "mount-ssh-repo",
    )
    mount_service.unmount.return_value = True
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_repository_service.ssh_mount_service",
        mount_service,
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "SSH App",
            "path": "/backups/app",
            "encryption": "none",
            "storage_backend": "ssh",
            "repository_type": "ssh",
            "connection_id": connection.id,
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "after_success",
        },
    )

    assert response.status_code == 200
    repository = test_db.query(Repository).filter(Repository.name == "SSH App").one()
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == "ssh://borg@storage.example:22/backups/app"
    assert repository.connection_id == connection.id
    assert storage.cache_path is None
    assert storage.sync_direction == "sshfs_mount_to_remote"
    assert storage.sync_status == "current"
    assert response.json()["repository"]["rclone_storage"]["sync_direction"] == (
        "sshfs_mount_to_remote"
    )
    assert "rclone_cache_path" not in response.json()["repository"]


@pytest.mark.unit
def test_create_ssh_repository_cloud_mirror_rejects_client_cache_path(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    connection = SSHConnection(host="storage.example", username="borg", port=22)
    test_db.add_all([remote, connection])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(connection)

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "SSH App",
            "path": "/backups/app",
            "encryption": "none",
            "storage_backend": "ssh",
            "repository_type": "ssh",
            "connection_id": connection.id,
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_cache_path": "/tmp/client-owned-stage",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"] == "backend.errors.rclone.cachePathServerOwned"
    )


@pytest.mark.unit
def test_create_ssh_repository_cloud_mirror_requires_stored_connection(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "SSH App",
            "path": "/backups/app",
            "encryption": "none",
            "storage_backend": "ssh",
            "repository_type": "ssh",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.rclone.mirrorUnsupportedPrimary"
    )


@pytest.mark.unit
def test_create_ssh_repository_cloud_mirror_first_sync_failure_preserves_repository(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    connection = SSHConnection(host="storage.example", username="borg", port=22)
    test_db.add_all([remote, connection])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(connection)
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )
    mount_service = AsyncMock()
    mount_service.active_mounts = {
        "mount-ssh-repo": type(
            "MountInfo", (), {"mount_point": "/tmp/sshfs_mount_9/backups/app"}
        )()
    }
    mount_service.mount_ssh_directory.return_value = (
        "/tmp/sshfs_mount_9",
        "mount-ssh-repo",
    )
    mount_service.unmount.return_value = True
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_repository_service.ssh_mount_service",
        mount_service,
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.sync",
        AsyncMock(
            return_value=RcloneCommandResult(
                success=False,
                return_code=1,
                stdout="",
                stderr="remote unavailable",
                command=["rclone", "sync"],
                redacted_command="rclone sync <path> <path>",
            )
        ),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "SSH App",
            "path": "/backups/app",
            "encryption": "none",
            "storage_backend": "ssh",
            "repository_type": "ssh",
            "connection_id": connection.id,
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "after_success",
        },
    )

    assert response.status_code == 200
    repository = test_db.query(Repository).filter(Repository.name == "SSH App").one()
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == "ssh://borg@storage.example:22/backups/app"
    assert storage.sync_status == "failed"
    assert storage.last_sync_error == "remote unavailable"
    assert response.json()["repository"]["rclone_storage"]["sync_status"] == "failed"


@pytest.mark.unit
def test_create_agent_repository_with_cloud_mirror_records_agent_owned_strategy(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    agent = AgentMachine(
        name="Laptop",
        agent_id="agt_laptop_mirror",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.rclone_sync"],
    )
    test_db.add_all([remote, agent])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(agent)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Agent Mirror App",
            "path": "/agent/repositories/app",
            "encryption": "none",
            "execution_target": "agent",
            "executor_type": "agent",
            "agent_machine_id": agent.id,
            "storage_backend": "agent_local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "manual",
        },
    )

    assert response.status_code == 200
    repository = (
        test_db.query(Repository).filter(Repository.name == "Agent Mirror App").one()
    )
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.executor_type == "agent"
    assert repository.agent_machine_id == agent.id
    assert repository.path == "/agent/repositories/app"
    assert storage.cache_path is None
    assert storage.sync_direction == "agent_to_remote"
    assert response.json()["repository"]["rclone_storage"]["sync_direction"] == (
        "agent_to_remote"
    )
    assert response.json()["repository"]["rclone_storage"]["cache_path"] is None
    assert response.json()["repository"]["agent_machine_name"] == "Laptop"
    assert response.json()["repository"]["agent_machine_status"] == "online"
    assert (
        response.json()["repository"]["rclone_storage"]["agent_machine_name"]
        == "Laptop"
    )
    assert (
        response.json()["repository"]["rclone_storage"]["agent_machine_status"]
        == "online"
    )
    assert "rclone_cache_path" not in response.json()["repository"]


@pytest.mark.unit
def test_create_agent_repository_cloud_mirror_rejects_client_cache_path(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    agent = AgentMachine(
        name="Laptop",
        agent_id="agt_laptop_cache_reject",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.rclone_sync"],
    )
    test_db.add_all([remote, agent])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(agent)

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Agent Mirror App",
            "path": "/agent/repositories/app",
            "encryption": "none",
            "execution_target": "agent",
            "executor_type": "agent",
            "agent_machine_id": agent.id,
            "storage_backend": "agent_local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_cache_path": "/tmp/client-owned-agent-stage",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"] == "backend.errors.rclone.cachePathServerOwned"
    )
    assert test_db.query(RepositoryStorage).count() == 0


@pytest.mark.unit
def test_create_agent_repository_cloud_mirror_requires_agent_sync_capability(
    test_client: TestClient, admin_headers, test_db
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    agent = AgentMachine(
        name="Laptop",
        agent_id="agt_laptop_missing_capability",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.info"],
    )
    test_db.add_all([remote, agent])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(agent)

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Agent Mirror App",
            "path": "/agent/repositories/app",
            "encryption": "none",
            "execution_target": "agent",
            "executor_type": "agent",
            "agent_machine_id": agent.id,
            "storage_backend": "agent_local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["key"] == "backend.errors.agents.capabilityMissing"
    assert (
        test_db.query(Repository).filter(Repository.name == "Agent Mirror App").first()
        is None
    )
    assert test_db.query(RepositoryStorage).count() == 0


@pytest.mark.unit
def test_create_agent_repository_cloud_mirror_rejects_soft_deleted_agent(test_db):
    from app.api.repositories import _require_agent_rclone_sync_capability

    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    agent = AgentMachine(
        name="Deleted Laptop",
        agent_id="agt_deleted_laptop_mirror",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        deleted_at=datetime.utcnow(),
        capabilities=["repository.rclone_sync"],
    )
    test_db.add_all([remote, agent])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(agent)

    with pytest.raises(HTTPException) as exc_info:
        _require_agent_rclone_sync_capability(agent.id, test_db)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["key"] == "backend.errors.agents.agentNotQueueable"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_agent_repository_borg2_requires_plan_feature(
    admin_user, test_db, monkeypatch
):
    from app.api.repositories import RepositoryCreate, create_repository

    agent = AgentMachine(
        name="Laptop",
        agent_id="agt_laptop_borg2_plan",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.info"],
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)

    async def unexpected_agent_create(*_args, **_kwargs):
        return {"success": True}

    monkeypatch.setattr(
        "app.api.repositories._create_agent_repository_record",
        unexpected_agent_create,
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_repository(
            RepositoryCreate(
                name="Agent Borg2 App",
                path="/agent/repositories/borg2-app",
                borg_version=2,
                encryption="none",
                execution_target="agent",
                executor_type="agent",
                agent_machine_id=agent.id,
                storage_backend="agent_local",
            ),
            admin_user,
            test_db,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["key"] == "backend.errors.plan.featureNotAvailable"
    assert (
        test_db.query(Repository).filter(Repository.name == "Agent Borg2 App").first()
        is None
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_mirrored_agent_repository_requires_new_agent_sync_capability(
    admin_user, test_db, monkeypatch
):
    from app.api.repositories import RepositoryUpdate, update_repository

    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    original_agent = AgentMachine(
        name="Mirror Agent",
        agent_id="agt_mirror_capable",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.rclone_sync"],
    )
    replacement_agent = AgentMachine(
        name="Info Agent",
        agent_id="agt_info_only",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.info"],
    )
    test_db.add_all([remote, original_agent, replacement_agent])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(original_agent)
    test_db.refresh(replacement_agent)
    repository = Repository(
        name="Agent Mirror App",
        path="/agent/repositories/app",
        encryption="none",
        compression="lz4",
        execution_target="agent",
        executor_type="agent",
        agent_machine_id=original_agent.id,
    )
    test_db.add(repository)
    test_db.commit()
    test_db.refresh(repository)
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        rclone_remote_id=remote.id,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path=None,
        sync_policy="manual",
        sync_status="current",
        sync_direction="agent_to_remote",
    )
    test_db.add(storage)
    test_db.commit()
    monkeypatch.setattr(
        "app.api.repositories.mqtt_service.sync_state_with_db",
        lambda *args, **kwargs: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await update_repository(
            repository.id,
            RepositoryUpdate(agent_machine_id=replacement_agent.id),
            admin_user,
            test_db,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["key"] == "backend.errors.agents.capabilityMissing"
    test_db.refresh(repository)
    assert repository.agent_machine_id == original_agent.id


@pytest.mark.unit
def test_create_agent_repository_cloud_mirror_first_sync_failure_preserves_repository(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(
        name="prod-s3",
        provider="s3",
        config_source="managed",
        redacted_config={"type": "s3", "provider": "AWS"},
    )
    agent = AgentMachine(
        name="Laptop",
        agent_id="agt_laptop_sync_failure",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.rclone_sync"],
    )
    test_db.add_all([remote, agent])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(agent)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )

    def fake_queue(db, repository, *, job_kind, operation=None, **_kwargs):
        return SimpleNamespace(id=77)

    async def fake_wait(db, agent_job_id, **_kwargs):
        raise HTTPException(
            status_code=502,
            detail={
                "key": "backend.errors.agents.repositoryOperationFailed",
                "message": "agent rclone failed",
            },
        )

    monkeypatch.setattr(
        "app.services.rclone_repository_service.queue_agent_repository_operation_job",
        fake_queue,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.wait_for_agent_repository_operation_job",
        fake_wait,
        raising=False,
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Agent Mirror App",
            "path": "/agent/repositories/app",
            "encryption": "none",
            "execution_target": "agent",
            "executor_type": "agent",
            "agent_machine_id": agent.id,
            "storage_backend": "agent_local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "after_success",
        },
    )

    assert response.status_code == 200
    repository = (
        test_db.query(Repository).filter(Repository.name == "Agent Mirror App").one()
    )
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == "/agent/repositories/app"
    assert storage.sync_status == "failed"
    assert storage.last_sync_error == "agent rclone failed"
    assert response.json()["repository"]["rclone_storage"]["sync_status"] == "failed"


@pytest.mark.unit
def test_update_agent_repository_cloud_mirror_preflight_failure_rolls_back_storage(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    agent = AgentMachine(
        name="Laptop",
        agent_id="agt_laptop_update_rollback",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.rclone_sync"],
    )
    test_db.add_all([remote, agent])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(agent)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )

    create_response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Agent Mirror App",
            "path": "/agent/repositories/app",
            "encryption": "none",
            "execution_target": "agent",
            "executor_type": "agent",
            "agent_machine_id": agent.id,
            "storage_backend": "agent_local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/old",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "manual",
            "rclone_extra_flags": ["--fast-list"],
        },
    )

    assert create_response.status_code == 200
    repository = (
        test_db.query(Repository).filter(Repository.name == "Agent Mirror App").one()
    )
    test_db.refresh(repository)
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    storage.sync_status = "current"
    test_db.commit()
    test_db.refresh(storage)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(side_effect=TimeoutError("remote timed out")),
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={
            "name": "Agent Mirror App",
            "path": "/agent/repositories/app",
            "encryption": "none",
            "compression": "lz4",
            "execution_target": "agent",
            "executor_type": "agent",
            "agent_machine_id": agent.id,
            "storage_backend": "agent_local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/new",
            "rclone_remote_path_verified": False,
            "rclone_sync_policy": "after_success",
            "rclone_extra_flags": [],
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.rclone.remotePathPreflightFailed"
    )
    test_db.refresh(repository)
    test_db.refresh(storage)
    assert repository.path == "/agent/repositories/app"
    assert repository.agent_machine_id == agent.id
    assert storage.rclone_remote_path == "borg-ui/repositories/old"
    assert storage.cache_path is None
    assert storage.sync_direction == "agent_to_remote"
    assert storage.sync_policy == "manual"
    assert storage.sync_status == "current"
    assert storage.extra_flags == ["--fast-list"]


@pytest.mark.unit
def test_create_local_repository_cloud_mirror_blocks_unverified_non_empty_target(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[{"Name": "existing", "IsDir": True}]),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Local App",
            "path": str(tmp_path / "repositories" / "app"),
            "encryption": "none",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_sync_policy": "manual",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.rclone.remotePathNotVerified"
    )
    assert (
        test_db.query(Repository).filter(Repository.name == "Local App").first() is None
    )


@pytest.mark.unit
def test_create_local_repository_cloud_mirror_first_sync_failure_preserves_repository(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    repo_path = tmp_path / "repositories" / "app"
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.sync",
        AsyncMock(
            return_value=RcloneCommandResult(
                success=False,
                return_code=1,
                stdout="",
                stderr="remote unavailable",
                command=["rclone", "sync"],
                redacted_command="rclone sync <path> <path>",
            )
        ),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Local App",
            "path": str(repo_path),
            "encryption": "none",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "after_success",
        },
    )

    assert response.status_code == 200
    repository = test_db.query(Repository).filter(Repository.name == "Local App").one()
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == str(repo_path)
    assert storage.sync_status == "failed"
    assert storage.last_sync_error == "remote unavailable"
    assert response.json()["repository"]["rclone_storage"]["sync_status"] == "failed"


@pytest.mark.unit
def test_create_local_repository_cloud_mirror_scheduled_policy_returns_next_run(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    repo_path = tmp_path / "repositories" / "scheduled-app"
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Scheduled Mirror App",
            "path": str(repo_path),
            "encryption": "none",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/scheduled-app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "scheduled",
            "rclone_sync_cron_expression": "0 */6 * * *",
            "rclone_sync_timezone": "UTC",
        },
    )

    assert response.status_code == 200
    repository = (
        test_db.query(Repository)
        .filter(Repository.name == "Scheduled Mirror App")
        .one()
    )
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    payload = response.json()["repository"]["rclone_storage"]
    assert storage.sync_policy == "scheduled"
    assert storage.sync_cron_expression == "0 */6 * * *"
    assert storage.sync_timezone == "UTC"
    assert storage.next_scheduled_sync_at is not None
    assert payload["sync_cron_expression"] == "0 */6 * * *"
    assert payload["sync_timezone"] == "UTC"
    assert payload["next_scheduled_sync_at"] is not None


@pytest.mark.unit
def test_create_scheduled_cloud_mirror_requires_cron_expression(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Missing Cron Mirror",
            "path": str(tmp_path / "repositories" / "missing-cron"),
            "encryption": "none",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/missing-cron",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "scheduled",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"] == "backend.errors.rclone.scheduleCronRequired"
    )
    assert (
        test_db.query(Repository)
        .filter(Repository.name == "Missing Cron Mirror")
        .first()
        is None
    )


@pytest.mark.unit
def test_import_local_repository_with_cloud_mirror_preserves_primary_path_and_syncs(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    repo_path = tmp_path / "repositories" / "imported"
    repo_path.mkdir(parents=True)
    (repo_path / "config").write_text("[repository]\nversion = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.api.repositories.verify_existing_repository",
        AsyncMock(
            return_value={
                "success": True,
                "info": {"encryption": {"mode": "none"}},
            }
        ),
    )
    monkeypatch.setattr(
        "app.api.repositories.BorgRouter.update_stats",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.sync",
        AsyncMock(
            return_value=RcloneCommandResult(
                success=True,
                return_code=0,
                stdout="",
                stderr="",
                command=["rclone", "sync"],
                redacted_command="rclone sync <path> <path>",
            )
        ),
    )

    response = test_client.post(
        "/api/repositories/import",
        headers=admin_headers,
        json={
            "name": "Imported Local App",
            "path": str(repo_path),
            "encryption": "none",
            "storage_backend": "local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/imported",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "after_success",
            "rclone_extra_flags": ["--fast-list"],
        },
    )

    assert response.status_code == 200
    repository = (
        test_db.query(Repository).filter(Repository.name == "Imported Local App").one()
    )
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == str(repo_path)
    assert repository.repository_type == "local"
    assert storage.cache_path == str(repo_path)
    assert storage.sync_direction == "primary_to_remote"
    assert storage.sync_status == "current"
    assert response.json()["repository"]["storage_backend"] == "local"
    assert response.json()["repository"]["rclone_storage"]["rclone_target"] == (
        "prod-s3:borg-ui/repositories/imported"
    )


@pytest.mark.unit
def test_create_rclone_repository_derives_cache_path_and_syncs(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(
        "app.api.repositories.rclone_repository_service.cache_root", str(cache_root)
    )
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.sync",
        AsyncMock(
            return_value=RcloneCommandResult(
                success=True,
                return_code=0,
                stdout="",
                stderr="",
                command=["rclone", "sync"],
                redacted_command="rclone sync <path> <path>",
            )
        ),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "App",
            "path": "/client/ignored",
            "encryption": "none",
            "storage_backend": "rclone",
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_sync_policy": "after_success",
        },
    )

    assert response.status_code == 200
    repository = test_db.query(Repository).filter(Repository.name == "App").one()
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == str(cache_root / "repositories" / str(repository.id))
    assert storage.cache_path == repository.path
    assert storage.rclone_remote_path == "borg-ui/repositories/app"
    assert storage.sync_status == "current"
    assert response.json()["repository"]["rclone_storage"]["rclone_target"] == (
        "prod-s3:borg-ui/repositories/app"
    )


@pytest.mark.unit
def test_create_direct_borg2_rclone_repository_uses_url_without_storage_row(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    _enable_borg_v2(test_db)
    init_mock = AsyncMock(return_value={"success": True, "already_existed": False})
    sync_mock = AsyncMock()
    v2_create_mock = AsyncMock(
        return_value={"success": True, "stdout": "", "stderr": ""}
    )
    monkeypatch.setattr("app.api.repositories.initialize_borg_repository", init_mock)
    monkeypatch.setattr(
        "app.api.repositories.rclone_repository_service.sync_repository", sync_mock
    )
    monkeypatch.setattr("app.api.v2.repositories._rcreate", v2_create_mock)
    mqtt_reasons = []
    monkeypatch.setattr(
        "app.api.repositories.mqtt_service.sync_state_with_db",
        lambda _db, *, reason: mqtt_reasons.append(reason),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "Direct Borg2 Cloud Repo",
            "path": "rclone://prod-s3/borg-ui/direct",
            "borg_version": 2,
            "encryption": "none",
            "storage_backend": "rclone_direct",
        },
    )

    assert response.status_code == 200
    repository = (
        test_db.query(Repository)
        .filter(Repository.name == "Direct Borg2 Cloud Repo")
        .one()
    )
    assert repository.path == "rclone://prod-s3/borg-ui/direct"
    assert repository.repository_type == "rclone"
    assert repository.borg_version == 2
    assert (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .first()
        is None
    )
    assert response.json()["repository"]["storage_backend"] == "rclone_direct"
    init_mock.assert_awaited_once()
    assert init_mock.await_args.kwargs["borg_version"] == 2
    sync_mock.assert_not_awaited()
    v2_create_mock.assert_not_awaited()
    assert mqtt_reasons == ["repository creation"]


@pytest.mark.unit
def test_import_direct_borg2_rclone_repository_verifies_url_without_hydrate(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    _enable_borg_v2(test_db)
    verify_mock = AsyncMock(
        return_value={"success": True, "info": {"encryption": {"mode": "none"}}}
    )
    hydrate_mock = AsyncMock(return_value={"sync_status": "current"})
    v2_info_mock = AsyncMock(
        return_value={"success": True, "stdout": '{"repository": {"id": "abc"}}'}
    )
    monkeypatch.setattr("app.api.repositories.verify_existing_repository", verify_mock)
    monkeypatch.setattr(
        "app.api.repositories.rclone_repository_service.hydrate_repository",
        hydrate_mock,
    )
    monkeypatch.setattr("app.api.v2.repositories._rinfo", v2_info_mock)
    mqtt_reasons = []
    monkeypatch.setattr(
        "app.api.repositories.mqtt_service.sync_state_with_db",
        lambda _db, *, reason: mqtt_reasons.append(reason),
    )

    response = test_client.post(
        "/api/repositories/import",
        headers=admin_headers,
        json={
            "name": "Imported Direct Borg2 Cloud Repo",
            "path": "rclone://prod-s3/borg-ui/imported",
            "borg_version": 2,
            "encryption": "none",
            "storage_backend": "rclone_direct",
        },
    )

    assert response.status_code == 200
    repository = (
        test_db.query(Repository)
        .filter(Repository.name == "Imported Direct Borg2 Cloud Repo")
        .one()
    )
    assert repository.path == "rclone://prod-s3/borg-ui/imported"
    assert repository.repository_type == "rclone"
    assert repository.borg_version == 2
    assert (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .first()
        is None
    )
    assert response.json()["repository"]["storage_backend"] == "rclone_direct"
    verify_mock.assert_awaited_once()
    assert verify_mock.await_args.kwargs["borg_version"] == 2
    hydrate_mock.assert_not_awaited()
    v2_info_mock.assert_not_awaited()
    assert mqtt_reasons == ["repository import"]


@pytest.mark.unit
def test_import_direct_borg2_rclone_repository_persists_keyfile_before_verify(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    _enable_borg_v2(test_db)
    repo_path = "rclone://prod-s3/borg-ui/keyfile-import"
    keyfile_content = "BORG_KEY test-keyfile"
    monkeypatch.setenv("HOME", str(tmp_path))

    async def verify_repository(**kwargs):
        from app.api.repositories import _borg_keyfile_name

        keyfile_path = (
            tmp_path / ".config" / "borg" / "keys" / _borg_keyfile_name(repo_path)
        )
        assert kwargs["path"] == repo_path
        assert keyfile_path.read_text() == keyfile_content
        assert keyfile_path.stat().st_mode & 0o777 == 0o600
        return {
            "success": True,
            "info": {"encryption": {"mode": "keyfile-aes-ocb"}},
        }

    monkeypatch.setattr(
        "app.api.repositories.verify_existing_repository", verify_repository
    )
    monkeypatch.setattr(
        "app.api.repositories.mqtt_service.sync_state_with_db",
        lambda *args, **kwargs: None,
    )

    response = test_client.post(
        "/api/repositories/import",
        headers=admin_headers,
        json={
            "name": "Imported Direct Keyfile Repo",
            "path": repo_path,
            "borg_version": 2,
            "encryption": "keyfile-aes-ocb",
            "passphrase": "secret",
            "keyfile_content": keyfile_content,
            "storage_backend": "rclone_direct",
        },
    )

    assert response.status_code == 200
    repository = (
        test_db.query(Repository)
        .filter(Repository.name == "Imported Direct Keyfile Repo")
        .one()
    )
    assert repository.has_keyfile is True
    assert response.json()["repository"]["storage_backend"] == "rclone_direct"


@pytest.mark.unit
def test_get_direct_borg2_rclone_repository_reports_direct_storage_backend(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    repository = Repository(
        name="Direct Repo Detail",
        path="rclone://prod-s3/borg-ui/direct-detail",
        encryption="none",
        compression="lz4",
        repository_type="rclone",
        execution_target="local",
        executor_type="server",
        borg_version=2,
    )
    test_db.add(repository)
    test_db.commit()
    test_db.refresh(repository)
    monkeypatch.setattr(
        "app.api.repositories.get_repository_stats",
        AsyncMock(return_value={"total_size": 0, "archive_count": 0}),
    )

    response = test_client.get(
        f"/api/repositories/{repository.id}", headers=admin_headers
    )

    assert response.status_code == 200
    payload = response.json()["repository"]
    assert payload["repository_type"] == "rclone"
    assert payload["storage_backend"] == "rclone_direct"
    assert "rclone_storage" not in payload


@pytest.mark.unit
@pytest.mark.parametrize(
    ("payload_overrides", "expected_key"),
    [
        (
            {"borg_version": 1},
            "backend.errors.rclone.directBorg2Required",
        ),
        (
            {"path": "/tmp/not-a-rclone-url"},
            "backend.errors.rclone.directInvalidUrl",
        ),
        (
            {
                "cloud_mirror_enabled": True,
                "rclone_remote_id": 1,
                "rclone_remote_path": "borg-ui/mirror",
            },
            "backend.errors.rclone.directIncompatiblePayload",
        ),
        (
            {"rclone_sync_policy": "manual"},
            "backend.errors.rclone.directIncompatiblePayload",
        ),
        (
            {"connection_id": 1},
            "backend.errors.rclone.directIncompatiblePayload",
        ),
        (
            {
                "executor_type": "agent",
                "execution_target": "agent",
                "agent_machine_id": 1,
            },
            "backend.errors.rclone.directIncompatiblePayload",
        ),
    ],
)
def test_direct_borg2_rclone_repository_validates_incompatible_create_payloads(
    test_client: TestClient,
    admin_headers,
    test_db,
    payload_overrides,
    expected_key,
):
    _enable_borg_v2(test_db)
    if payload_overrides.get("rclone_remote_id"):
        test_db.add(RcloneRemote(id=1, name="prod-s3", provider="s3"))
    if payload_overrides.get("connection_id"):
        test_db.add(
            SSHConnection(
                id=1,
                host="server.example.com",
                username="borg",
                port=22,
                ssh_key_id=1,
            )
        )
    test_db.commit()

    payload = {
        "name": "Invalid Direct Borg2 Cloud Repo",
        "path": "rclone://prod-s3/borg-ui/direct",
        "borg_version": 2,
        "encryption": "none",
        "storage_backend": "rclone_direct",
    }
    payload.update(payload_overrides)

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["detail"]["key"] == expected_key


@pytest.mark.unit
def test_update_normal_repository_rejects_switching_to_direct_rclone_mode(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    repository = Repository(
        name="Normal Repo",
        path="/backups/normal",
        encryption="none",
        compression="lz4",
        repository_type="local",
        borg_version=2,
    )
    test_db.add(repository)
    test_db.commit()
    test_db.refresh(repository)
    monkeypatch.setattr(
        "app.api.repositories.BorgRouter.verify_repository",
        AsyncMock(return_value={"success": True}),
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={
            "path": "rclone://prod-s3/borg-ui/direct",
            "storage_backend": "rclone_direct",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["key"] == "backend.errors.rclone.updateUnsupported"


@pytest.mark.unit
def test_update_direct_borg2_rclone_repository_accepts_noop_form_fields(
    test_client: TestClient, admin_headers, test_db
):
    repository = Repository(
        name="Direct Repo",
        path="rclone://prod-s3/borg-ui/direct",
        encryption="none",
        compression="lz4",
        repository_type="rclone",
        execution_target="local",
        executor_type="server",
        borg_version=2,
    )
    test_db.add(repository)
    test_db.commit()
    test_db.refresh(repository)

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={
            "name": "Direct Repo Renamed",
            "path": "rclone://prod-s3/borg-ui/direct",
            "storage_backend": "rclone_direct",
            "execution_target": "local",
            "executor_type": "server",
            "agent_machine_id": None,
            "connection_id": None,
            "cloud_mirror_enabled": False,
            "rclone_remote_id": None,
            "rclone_remote_path": None,
            "rclone_remote_path_verified": False,
            "rclone_sync_policy": "after_success",
            "rclone_extra_flags": [],
            "rclone_cache_path": None,
        },
    )

    assert response.status_code == 200
    test_db.refresh(repository)
    assert repository.name == "Direct Repo Renamed"
    assert repository.path == "rclone://prod-s3/borg-ui/direct"
    assert repository.repository_type == "rclone"
    assert repository.connection_id is None
    assert repository.agent_machine_id is None
    assert (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .first()
        is None
    )


@pytest.mark.unit
def test_update_direct_borg2_rclone_repository_rejects_mirror_fields(
    test_client: TestClient, admin_headers, test_db
):
    repository = Repository(
        name="Direct Repo",
        path="rclone://prod-s3/borg-ui/direct",
        encryption="none",
        compression="lz4",
        repository_type="rclone",
        execution_target="local",
        executor_type="server",
        borg_version=2,
    )
    test_db.add(repository)
    test_db.commit()
    test_db.refresh(repository)

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={
            "storage_backend": "rclone_direct",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": 1,
            "rclone_remote_path": "borg-ui/mirror",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.rclone.directIncompatiblePayload"
    )


@pytest.mark.unit
def test_create_rclone_repository_persists_sync_failure_state(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    monkeypatch.setattr(
        "app.api.repositories.rclone_repository_service.cache_root",
        str(tmp_path / "cache"),
    )
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.sync",
        AsyncMock(
            return_value=RcloneCommandResult(
                success=False,
                return_code=1,
                stdout="",
                stderr="remote unavailable",
                command=["rclone", "sync"],
                redacted_command="rclone sync <path> <path>",
            )
        ),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "App",
            "path": "/client/ignored",
            "encryption": "none",
            "storage_backend": "rclone",
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_sync_policy": "after_success",
        },
    )

    assert response.status_code == 200
    repository = test_db.query(Repository).filter(Repository.name == "App").one()
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert storage.sync_status == "failed"
    assert storage.last_sync_error == "remote unavailable"


@pytest.mark.unit
def test_create_rclone_repository_unexpected_init_failure_does_not_persist_record(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    monkeypatch.setattr(
        "app.api.repositories.rclone_repository_service.cache_root",
        str(tmp_path / "cache"),
    )
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(side_effect=RuntimeError("borg init crashed")),
    )

    response = test_client.post(
        "/api/repositories/",
        headers=admin_headers,
        json={
            "name": "App",
            "path": "/client/ignored",
            "encryption": "none",
            "storage_backend": "rclone",
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_sync_policy": "manual",
        },
    )

    assert response.status_code == 500
    assert test_db.query(Repository).filter(Repository.name == "App").first() is None


@pytest.mark.unit
@pytest.mark.parametrize("endpoint", ["/api/repositories/", "/api/repositories/import"])
def test_rclone_repository_rejects_borg2_payload(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch, endpoint
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    monkeypatch.setattr(
        "app.api.repositories.rclone_repository_service.cache_root",
        str(tmp_path / "cache"),
    )
    monkeypatch.setattr(
        "app.api.repositories.initialize_borg_repository",
        AsyncMock(return_value={"success": True, "already_existed": False}),
    )
    monkeypatch.setattr(
        "app.api.repositories.rclone_repository_service.hydrate_repository",
        AsyncMock(return_value={"sync_status": "current"}),
    )
    monkeypatch.setattr(
        "app.api.repositories.verify_existing_repository",
        AsyncMock(
            return_value={
                "success": True,
                "info": {"encryption": {"mode": "none"}},
            }
        ),
    )

    response = test_client.post(
        endpoint,
        headers=admin_headers,
        json={
            "name": "Borg2 Cloud Repo",
            "path": "/client/ignored",
            "borg_version": 2,
            "encryption": "none",
            "storage_backend": "rclone",
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_sync_policy": "manual",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["key"] == "backend.errors.rclone.borgV2Unsupported"


@pytest.mark.unit
def test_import_rclone_repository_verify_failure_removes_repository_record(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    monkeypatch.setattr(
        "app.api.repositories.rclone_repository_service.cache_root",
        str(tmp_path / "cache"),
    )
    monkeypatch.setattr(
        "app.api.repositories.rclone_repository_service.hydrate_repository",
        AsyncMock(return_value={"sync_status": "current"}),
    )
    monkeypatch.setattr(
        "app.api.repositories.verify_existing_repository",
        AsyncMock(return_value={"success": False, "error": "not a borg repo"}),
    )

    response = test_client.post(
        "/api/repositories/import",
        headers=admin_headers,
        json={
            "name": "Imported Cloud Repo",
            "path": "/client/ignored",
            "encryption": "none",
            "storage_backend": "rclone",
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/imported",
            "rclone_sync_policy": "manual",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.repo.failedToVerifyRepository"
    )
    assert (
        test_db.query(Repository)
        .filter(Repository.name == "Imported Cloud Repo")
        .first()
        is None
    )
    assert test_db.query(RepositoryStorage).count() == 0


@pytest.mark.unit
def test_import_rclone_repository_flushes_storage_before_hydrate(
    test_client: TestClient, admin_headers, test_db, tmp_path, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    test_db.add(remote)
    test_db.commit()
    test_db.refresh(remote)
    monkeypatch.setattr(
        "app.api.repositories.rclone_repository_service.cache_root",
        str(tmp_path / "cache"),
    )

    async def hydrate_with_storage_lookup(db, repository):
        storage = (
            db.query(RepositoryStorage)
            .filter(RepositoryStorage.repository_id == repository.id)
            .first()
        )
        assert storage is not None
        return {"sync_status": "current"}

    monkeypatch.setattr(
        "app.api.repositories.rclone_repository_service.hydrate_repository",
        hydrate_with_storage_lookup,
    )
    monkeypatch.setattr(
        "app.api.repositories.verify_existing_repository",
        AsyncMock(
            return_value={
                "success": True,
                "info": {"encryption": {"mode": "none"}},
            }
        ),
    )

    response = test_client.post(
        "/api/repositories/import",
        headers=admin_headers,
        json={
            "name": "Imported Cloud Repo",
            "path": "/client/ignored",
            "encryption": "none",
            "storage_backend": "rclone",
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/imported",
            "rclone_sync_policy": "manual",
        },
    )

    assert response.status_code == 200
    repository = (
        test_db.query(Repository).filter(Repository.name == "Imported Cloud Repo").one()
    )
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert storage.cache_path == str(
        tmp_path / "cache" / "repositories" / str(repository.id)
    )


@pytest.mark.unit
def test_update_rclone_repository_storage_fields(
    test_client: TestClient, admin_headers, test_db
):
    old_remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    new_remote = RcloneRemote(name="archive-s3", provider="s3", config_source="managed")
    repository = Repository(name="App", path="/cache/repositories/1", encryption="none")
    test_db.add_all([old_remote, new_remote, repository])
    test_db.commit()
    test_db.refresh(old_remote)
    test_db.refresh(new_remote)
    test_db.refresh(repository)
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        rclone_remote_id=old_remote.id,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path="/cache/repositories/1",
        sync_policy="after_success",
        sync_status="current",
        extra_flags=[],
    )
    test_db.add(storage)
    test_db.commit()

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={
            "rclone_remote_id": new_remote.id,
            "rclone_remote_path": "borg-ui/repositories/archive",
            "rclone_sync_policy": "manual",
            "rclone_extra_flags": ["--fast-list"],
        },
    )

    assert response.status_code == 200
    test_db.refresh(storage)
    assert storage.rclone_remote_id == new_remote.id
    assert storage.rclone_remote_path == "borg-ui/repositories/archive"
    assert storage.sync_policy == "manual"
    assert storage.extra_flags == ["--fast-list"]


@pytest.mark.unit
def test_update_local_repository_enables_cloud_mirror_with_default_policy(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(name="App", path="/repositories/app", encryption="none")
    test_db.add_all([remote, repository])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(repository)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={
            "storage_backend": "local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_extra_flags": ["--fast-list"],
        },
    )

    assert response.status_code == 200
    test_db.refresh(repository)
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert repository.path == "/repositories/app"
    assert repository.repository_type == "local"
    assert storage.cache_path == "/repositories/app"
    assert storage.sync_direction == "primary_to_remote"
    assert storage.rclone_remote_id == remote.id
    assert storage.rclone_remote_path == "borg-ui/repositories/app"
    assert storage.sync_policy == "after_success"
    assert storage.extra_flags == ["--fast-list"]


@pytest.mark.unit
def test_update_local_repository_cloud_mirror_adds_scheduled_policy(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(name="App", path="/repositories/app", encryption="none")
    test_db.add_all([remote, repository])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(repository)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[]),
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={
            "storage_backend": "local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "scheduled",
            "rclone_sync_cron_expression": "*/30 * * * *",
            "rclone_sync_timezone": "UTC",
        },
    )

    assert response.status_code == 200
    storage = (
        test_db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .one()
    )
    assert storage.sync_policy == "scheduled"
    assert storage.sync_cron_expression == "*/30 * * * *"
    assert storage.sync_timezone == "UTC"
    assert storage.next_scheduled_sync_at is not None


@pytest.mark.unit
def test_manual_rclone_sync_records_job_without_clearing_schedule(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(name="App", path="/repositories/app", encryption="none")
    test_db.add_all([remote, repository])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(repository)
    next_run = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2)
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        rclone_remote_id=remote.id,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path="/repositories/app",
        sync_policy="scheduled",
        sync_status="pending",
        sync_direction="primary_to_remote",
        sync_cron_expression="0 */6 * * *",
        sync_timezone="UTC",
        next_scheduled_sync_at=next_run,
    )
    test_db.add(storage)
    test_db.commit()
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.sync",
        AsyncMock(
            return_value=RcloneCommandResult(
                success=True,
                return_code=0,
                stdout="manual sync completed",
                stderr="",
                command=["rclone", "sync"],
                redacted_command="rclone sync <path> <path>",
            )
        ),
    )

    response = test_client.post(
        f"/api/repositories/{repository.id}/rclone/sync",
        headers=admin_headers,
    )

    assert response.status_code == 200
    test_db.refresh(storage)
    sync_job = (
        test_db.query(RcloneSyncJob)
        .filter(
            RcloneSyncJob.repository_id == repository.id,
            RcloneSyncJob.triggered_by == "manual",
        )
        .one()
    )
    assert response.json()["sync_status"] == "current"
    assert storage.next_scheduled_sync_at == next_run
    assert sync_job.triggered_by == "manual"
    assert sync_job.status == "completed"
    assert sync_job.log_text == "manual sync completed"


@pytest.mark.unit
def test_update_local_repository_cloud_mirror_preflight_failure_uses_error_key(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(name="App", path="/repositories/app", encryption="none")
    test_db.add_all([remote, repository])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(repository)
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(side_effect=TimeoutError("rclone timed out")),
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={
            "storage_backend": "local",
            "cloud_mirror_enabled": True,
            "rclone_remote_id": remote.id,
            "rclone_remote_path": "borg-ui/repositories/app",
            "rclone_remote_path_verified": True,
            "rclone_sync_policy": "manual",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.rclone.remotePathPreflightFailed"
    )
    assert test_db.query(RepositoryStorage).count() == 0


@pytest.mark.unit
def test_update_mirrored_local_repository_path_updates_cloud_mirror_source(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    repository = Repository(
        name="App",
        path="/repositories/app",
        encryption="none",
        repository_type="local",
    )
    test_db.add_all([remote, repository])
    test_db.commit()
    test_db.refresh(remote)
    test_db.refresh(repository)
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        rclone_remote_id=remote.id,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path="/repositories/app",
        sync_policy="manual",
        sync_status="current",
        sync_direction="primary_to_remote",
    )
    test_db.add(storage)
    test_db.commit()
    monkeypatch.setattr(
        "app.api.repositories.BorgRouter.verify_repository",
        AsyncMock(return_value={"success": True}),
    )
    monkeypatch.setattr(
        "app.api.repositories.mqtt_service.sync_state_with_db",
        lambda *args, **kwargs: None,
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={"path": "/repositories/app-new"},
    )

    assert response.status_code == 200
    test_db.refresh(repository)
    test_db.refresh(storage)
    assert repository.path == "/repositories/app-new"
    assert storage.cache_path == "/repositories/app-new"


@pytest.mark.unit
def test_update_cloud_mirror_remote_change_blocks_unverified_non_empty_target(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    old_remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    new_remote = RcloneRemote(name="archive-s3", provider="s3", config_source="managed")
    repository = Repository(
        name="App",
        path="/repositories/app",
        encryption="none",
        repository_type="local",
    )
    test_db.add_all([old_remote, new_remote, repository])
    test_db.commit()
    test_db.refresh(old_remote)
    test_db.refresh(new_remote)
    test_db.refresh(repository)
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        rclone_remote_id=old_remote.id,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path="/repositories/app",
        sync_policy="manual",
        sync_status="current",
        sync_direction="primary_to_remote",
    )
    test_db.add(storage)
    test_db.commit()
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[{"Name": "existing", "IsDir": True}]),
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={"rclone_remote_id": new_remote.id},
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.rclone.remotePathNotVerified"
    )
    test_db.refresh(storage)
    assert storage.rclone_remote_id == old_remote.id


@pytest.mark.unit
def test_update_ssh_cloud_mirror_remote_change_rolls_back_on_preflight_failure(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    old_remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
    new_remote = RcloneRemote(name="archive-s3", provider="s3", config_source="managed")
    connection = SSHConnection(host="storage.example", username="borg", port=22)
    repository = Repository(
        name="SSH App",
        path="ssh://borg@storage.example:22/backups/app",
        encryption="none",
        repository_type="ssh",
        connection_id=1,
        execution_target="ssh",
        executor_type="server",
    )
    test_db.add_all([old_remote, new_remote, connection, repository])
    test_db.commit()
    test_db.refresh(old_remote)
    test_db.refresh(new_remote)
    test_db.refresh(connection)
    repository.connection_id = connection.id
    test_db.commit()
    test_db.refresh(repository)
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        rclone_remote_id=old_remote.id,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path=None,
        sync_policy="manual",
        sync_status="current",
        sync_direction="sshfs_mount_to_remote",
    )
    test_db.add(storage)
    test_db.commit()
    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_service.lsjson",
        AsyncMock(return_value=[{"Name": "existing", "IsDir": True}]),
    )

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        headers=admin_headers,
        json={"rclone_remote_id": new_remote.id},
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.rclone.remotePathNotVerified"
    )
    test_db.refresh(storage)
    assert storage.rclone_remote_id == old_remote.id
    assert storage.rclone_remote_path == "borg-ui/repositories/app"
    assert storage.cache_path is None
    assert storage.sync_direction == "sshfs_mount_to_remote"


@pytest.mark.unit
def test_rclone_storage_migration_downgrade_drops_created_tables():
    migration = importlib.import_module(
        "app.database.migrations.113_add_rclone_storage"
    )
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        migration.upgrade(db)
        inspector = inspect(engine)
        assert inspector.has_table("rclone_remotes")
        assert inspector.has_table("repository_storage")
        assert inspector.has_table("rclone_sync_jobs")

        migration.downgrade(db)
        inspector = inspect(engine)
        assert not inspector.has_table("rclone_sync_jobs")
        assert not inspector.has_table("repository_storage")
        assert not inspector.has_table("rclone_remotes")
    finally:
        db.close()


@pytest.mark.unit
def test_rclone_storage_migration_runs_with_connection():
    migration = importlib.import_module(
        "app.database.migrations.113_add_rclone_storage"
    )
    engine = create_engine("sqlite:///:memory:")

    with engine.connect() as connection:
        migration.upgrade(connection)
        inspector = inspect(engine)
        assert inspector.has_table("rclone_remotes")
        assert inspector.has_table("repository_storage")
        assert inspector.has_table("rclone_sync_jobs")


@pytest.mark.unit
def test_rclone_storage_migration_uses_postgresql_identity_columns():
    migration = importlib.import_module(
        "app.database.migrations.113_add_rclone_storage"
    )

    class FakeDialect:
        name = "postgresql"

    class FakeBind:
        dialect = FakeDialect()

    class FakeDb:
        def get_bind(self):
            return FakeBind()

    assert migration._id_primary_key(FakeDb()) == (
        "id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"
    )
    assert migration._timestamp_type(FakeDb()) == "TIMESTAMP"


@pytest.mark.unit
def test_scheduled_rclone_mirror_migration_downgrade_removes_added_fields():
    base_migration = importlib.import_module(
        "app.database.migrations.113_add_rclone_storage"
    )
    migration = importlib.import_module(
        "app.database.migrations.114_add_scheduled_rclone_mirror_jobs"
    )
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        base_migration.upgrade(db)
        migration.upgrade(db)
        inspector = inspect(engine)
        storage_columns = {
            column["name"] for column in inspector.get_columns("repository_storage")
        }
        job_columns = {
            column["name"] for column in inspector.get_columns("rclone_sync_jobs")
        }
        index_names = {
            index["name"] for index in inspector.get_indexes("repository_storage")
        }
        assert "sync_cron_expression" in storage_columns
        assert "sync_timezone" in storage_columns
        assert "last_scheduled_sync_at" in storage_columns
        assert "next_scheduled_sync_at" in storage_columns
        assert "triggered_by" in job_columns
        assert "scheduled_for" in job_columns
        assert "log_text" in job_columns
        assert "ix_repository_storage_next_scheduled_sync_at" in index_names

        migration.downgrade(db)
        inspector = inspect(engine)
        storage_columns = {
            column["name"] for column in inspector.get_columns("repository_storage")
        }
        job_columns = {
            column["name"] for column in inspector.get_columns("rclone_sync_jobs")
        }
        index_names = {
            index["name"] for index in inspector.get_indexes("repository_storage")
        }

        assert "ix_repository_storage_next_scheduled_sync_at" not in index_names
        if migration._sqlite_supports_drop_column(db):
            assert "sync_cron_expression" not in storage_columns
            assert "sync_timezone" not in storage_columns
            assert "last_scheduled_sync_at" not in storage_columns
            assert "next_scheduled_sync_at" not in storage_columns
            assert "triggered_by" not in job_columns
            assert "scheduled_for" not in job_columns
            assert "log_text" not in job_columns
    finally:
        db.close()
