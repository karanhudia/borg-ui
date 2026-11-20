"""Reveal-once passphrases (spec 2026-11-14-mcp-server 5.9; plan phase 4, Task 2)."""

import logging

import pytest

from app.core.security import (
    MCP_INTERNAL_HEADER,
    create_access_token,
    create_mcp_internal_token,
)
from app.database.models import Repository, User

PASSPHRASE = "generated-example-passphrase-0123456789"


@pytest.fixture
def flagged(test_db):
    repo = Repository(
        name="Photos",
        path="/data/example/photos",
        encryption="repokey",
        passphrase=PASSPHRASE,
        passphrase_unsaved=True,
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


def _reveal(client, repo, headers, **body):
    return client.post(
        f"/api/repositories/{repo.id}/passphrase/reveal", json=body, headers=headers
    )


@pytest.mark.unit
def test_reveal_with_password_answers_the_passphrase(
    test_client, admin_headers, flagged
):
    response = _reveal(test_client, flagged, admin_headers, password="admin123")
    assert response.status_code == 200
    assert response.json() == {
        "passphrase": PASSPHRASE,
        "encryption": "repokey",
        "has_keyfile": False,
    }


@pytest.mark.unit
def test_reveal_does_not_clear_the_flag(test_client, admin_headers, flagged, test_db):
    _reveal(test_client, flagged, admin_headers, password="admin123")
    test_db.refresh(flagged)
    assert flagged.passphrase_unsaved is True


@pytest.mark.unit
def test_wrong_password_reveals_nothing(test_client, admin_headers, flagged):
    response = _reveal(test_client, flagged, admin_headers, password="wrong")
    assert response.status_code == 403
    assert response.json()["detail"]["key"] == "backend.errors.repo.reauthFailed"
    assert PASSPHRASE not in response.text


@pytest.mark.unit
def test_account_without_local_password_types_the_repository_name(
    test_client, test_db, flagged
):
    user = User(username="sso-admin", role="admin", is_active=True, auth_source="oidc")
    test_db.add(user)
    test_db.commit()
    headers = {
        "Authorization": f"Bearer {create_access_token(data={'sub': user.username})}"
    }
    near_miss = _reveal(test_client, flagged, headers, repository_name="photos")
    assert near_miss.status_code == 403
    ok = _reveal(test_client, flagged, headers, repository_name="Photos")
    assert ok.status_code == 200
    assert ok.json()["passphrase"] == PASSPHRASE


@pytest.mark.unit
def test_personal_token_is_refused(test_client, admin_headers, flagged):
    token = test_client.post(
        "/api/settings/tokens", json={"name": "ci"}, headers=admin_headers
    ).json()["token"]
    response = _reveal(
        test_client,
        flagged,
        {"Authorization": f"Bearer {token}"},
        password="admin123",
    )
    assert response.status_code == 403
    assert (
        response.json()["detail"]["key"] == "backend.errors.auth.browserSessionRequired"
    )
    assert PASSPHRASE not in response.text


@pytest.mark.unit
def test_mcp_internal_credential_is_refused(
    test_client, admin_headers, admin_user, create_connection, flagged
):
    row, _ = create_connection(admin_headers, level="read")
    headers = {MCP_INTERNAL_HEADER: create_mcp_internal_token(admin_user.id, row["id"])}
    response = _reveal(test_client, flagged, headers, password="admin123")
    assert response.status_code == 403
    assert PASSPHRASE not in response.text


@pytest.mark.unit
def test_viewer_is_refused(test_client, auth_headers, flagged):
    response = _reveal(test_client, flagged, auth_headers, password="testpass123")
    assert response.status_code == 403
    assert PASSPHRASE not in response.text


@pytest.mark.unit
def test_acknowledge_clears_the_flag_and_reveal_then_refuses(
    test_client, admin_headers, flagged, test_db
):
    response = test_client.post(
        f"/api/repositories/{flagged.id}/passphrase/acknowledge", headers=admin_headers
    )
    assert response.status_code == 204
    test_db.refresh(flagged)
    assert flagged.passphrase_unsaved is False
    again = test_client.post(
        f"/api/repositories/{flagged.id}/passphrase/acknowledge", headers=admin_headers
    )
    assert again.status_code == 204
    refused = _reveal(test_client, flagged, admin_headers, password="admin123")
    assert refused.status_code == 409
    assert (
        refused.json()["detail"]["key"] == "backend.errors.repo.passphraseAlreadySaved"
    )


@pytest.mark.unit
def test_acknowledge_refuses_tokens(test_client, admin_headers, flagged):
    token = test_client.post(
        "/api/settings/tokens", json={"name": "ci"}, headers=admin_headers
    ).json()["token"]
    response = test_client.post(
        f"/api/repositories/{flagged.id}/passphrase/acknowledge",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.unit
def test_reveal_is_logged_without_the_value(
    test_client, admin_headers, flagged, caplog
):
    with caplog.at_level(logging.INFO):
        _reveal(test_client, flagged, admin_headers, password="admin123")
    assert any(
        "passphrase revealed" in record.getMessage() for record in caplog.records
    )
    assert PASSPHRASE not in caplog.text


@pytest.mark.unit
def test_repository_list_shows_the_flag(test_client, admin_headers, flagged):
    listed = test_client.get("/api/repositories/", headers=admin_headers).json()
    repos = listed["repositories"] if isinstance(listed, dict) else listed
    row = next(r for r in repos if r["id"] == flagged.id)
    assert row["passphrase_unsaved"] is True


@pytest.mark.unit
def test_flagged_repository_health_warns():
    from datetime import datetime, timedelta

    from app.api.dashboard import build_full_repository_health

    now = datetime.utcnow()
    repo = Repository(
        name="Photos",
        path="/data/example/photos",
        last_backup=now - timedelta(hours=1),
        last_check=now - timedelta(hours=1),
        last_compact=now - timedelta(hours=1),
        passphrase_unsaved=True,
    )
    health = build_full_repository_health(repo, now)
    assert "Passphrase not saved yet" in health["warnings"]
    assert health["health_status"] in ("warning", "critical")


@pytest.mark.unit
def test_downgrade_drops_the_column(tmp_path):
    from alembic import command
    from sqlalchemy import inspect

    from app.database.db_upgrade import _alembic_config, _engine

    url = f"sqlite:///{tmp_path / 'borg.db'}"

    def migrate(target, down=False):
        engine = _engine(url)
        config = _alembic_config(url)
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            (command.downgrade if down else command.upgrade)(config, target)
            connection.commit()
        engine.dispose()

    def columns():
        engine = _engine(url)
        names = {c["name"] for c in inspect(engine).get_columns("repositories")}
        engine.dispose()
        return names

    migrate("head")
    assert "passphrase_unsaved" in columns()
    migrate("a9e3c7b1d5f2", down=True)
    assert "passphrase_unsaved" not in columns()


@pytest.mark.unit
def test_proxy_auth_types_the_repository_name(test_db, flagged):
    """Proxy-auth users have no password to type, even with a hash left over."""
    from types import SimpleNamespace
    from unittest.mock import patch

    from app.api.repositories import PassphraseRevealRequest, _reauthenticated

    user = SimpleNamespace(auth_source="local", password_hash="$2b$12$x")
    with patch("app.api.repositories.settings.disable_authentication", True):
        assert _reauthenticated(
            user, flagged, PassphraseRevealRequest(repository_name="Photos")
        )


@pytest.mark.unit
def test_observe_mode_health_also_warns():
    """PR #1585 review: a flagged repository switched to observe keeps the warning."""
    from datetime import datetime, timedelta

    from app.api.dashboard import build_observe_repository_health

    now = datetime.utcnow()
    repo = Repository(
        name="Photos",
        path="/data/example/photos",
        mode="observe",
        last_backup=now - timedelta(hours=1),
        passphrase_unsaved=True,
    )
    health = build_observe_repository_health(repo, now)
    assert "Passphrase not saved yet" in health["warnings"]
    assert health["health_status"] in ("warning", "critical")


@pytest.mark.unit
def test_reauthentication_runs_off_the_event_loop(
    test_client, admin_headers, flagged, monkeypatch
):
    """PR #1585 review: bcrypt must not block the worker's event loop."""
    import app.api.repositories as routes

    ran = []
    real = routes.run_in_threadpool

    async def recording(func, *args, **kwargs):
        ran.append(func.__name__)
        return await real(func, *args, **kwargs)

    monkeypatch.setattr(routes, "run_in_threadpool", recording)
    response = _reveal(test_client, flagged, admin_headers, password="admin123")
    assert response.status_code == 200
    assert "_reauthenticated" in ran
