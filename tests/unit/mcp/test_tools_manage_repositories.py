"""Manage: repository tools (plan phase 4, Task 4; spec 5.5 Manage, 5.9)."""

import logging

import pytest

from app.database.models import McpActivity, Repository
from app.mcp import borg_routes
from tests.unit.mcp.test_tools_stubbed import run

V1 = {"id": 1, "name": "Photos", "path": "/data/example/photos", "borg_version": 1}
V2 = {"id": 2, "name": "Media", "path": "/data/example/media", "borg_version": 2}
REPOS = {"/api/repositories/": {"repositories": [V1, V2]}}
CREATED_V1 = {"success": True, "repository": {"id": 9, "name": "Docs"}}
CREATED_V2 = {"id": 9, "name": "Docs", "borg_version": 2}


@pytest.fixture
def no_flag(monkeypatch):
    marked = []
    monkeypatch.setattr(
        "app.mcp.passphrase.mark_unsaved", lambda app, repo_id: marked.append(repo_id)
    )
    return marked


@pytest.mark.unit
def test_repository_create_routes():
    assert borg_routes.repository_create({"borg_version": 1}) == "/api/repositories/"
    assert borg_routes.repository_create({"borg_version": 2}) == "/api/v2/repositories/"
    assert (
        borg_routes.repository_create({"borg_version": 2, "execution_target": "agent"})
        == "/api/repositories/"
    )
    assert borg_routes.repository_import({"borg_version": 2}) == (
        "/api/v2/repositories/import"
    )


@pytest.mark.unit
def test_create_repository_borg2_posts_v2(no_flag):
    routes = {"POST /api/v2/repositories/": CREATED_V2}
    result, api = run(
        "create_repository",
        routes,
        name="Docs",
        path="/data/example/docs",
        borg_version=2,
    )
    path, body = api.posts[0]
    assert path == "/api/v2/repositories/"
    assert body["encryption"] == "repokey-aes-ocb"
    assert no_flag == [9]
    assert not result.is_error


@pytest.mark.unit
def test_create_repository_generates_and_never_returns_the_passphrase(no_flag):
    routes = {"POST /api/repositories/": CREATED_V1}
    result, api = run(
        "create_repository", routes, name="Docs", path="/data/example/docs"
    )
    body = api.posts[0][1]
    secret = body["passphrase"]
    assert len(secret) >= 32 and "\n" not in secret
    assert body["encryption"] == "repokey"
    assert secret not in result.text
    assert secret not in repr(result.data)
    assert "passphrase" in result.text.lower()
    assert "/repositories?reveal=9" in result.text
    assert no_flag == [9]


@pytest.mark.unit
def test_create_unencrypted_does_not_mark(no_flag):
    routes = {"POST /api/repositories/": CREATED_V1}
    _, api = run(
        "create_repository",
        routes,
        name="Docs",
        path="/data/example/docs",
        encryption="none",
    )
    assert "passphrase" not in api.posts[0][1]
    assert no_flag == []


@pytest.mark.unit
def test_create_repository_over_ssh_resolves_the_connection(no_flag):
    routes = {
        "/api/ssh-keys/connections": {
            "connections": [
                {"id": 4, "host": "backups.example.com", "username": "borg"}
            ]
        },
        "POST /api/repositories/": CREATED_V1,
    }
    _, api = run(
        "create_repository",
        routes,
        name="Docs",
        path="/backups/docs",
        ssh_connection="borg@backups.example.com",
    )
    assert api.posts[0][1]["connection_id"] == 4


@pytest.mark.unit
def test_create_repository_failed_flag_tells_the_user(monkeypatch):
    def boom(app, repo_id):
        raise RuntimeError("db gone")

    monkeypatch.setattr("app.mcp.passphrase.mark_unsaved", boom)
    routes = {"POST /api/repositories/": CREATED_V1}
    result, _ = run("create_repository", routes, name="Docs", path="/data/example/docs")
    assert result.is_error
    assert "web UI" in result.text


@pytest.mark.unit
def test_import_encrypted_hands_off_without_posting():
    result, api = run(
        "import_repository", {}, name="Old", path="/data/example/old", borg_version=1
    )
    assert api.posts == []
    assert "/repositories?import=1" in result.text
    assert "passphrase=" not in result.text
    assert "Enter the passphrase there" in result.text


@pytest.mark.unit
def test_import_unencrypted_posts():
    routes = {"POST /api/repositories/import": CREATED_V1}
    _, api = run(
        "import_repository",
        routes,
        name="Old",
        path="/data/example/old",
        encrypted=False,
    )
    assert api.posts[0][1]["encryption"] == "none"
    assert "passphrase" not in api.posts[0][1]


@pytest.mark.unit
def test_update_repository_sends_only_allowlisted_fields():
    from app.mcp.tools.manage_repositories import UPDATE_REPOSITORY_FIELDS

    routes = {**REPOS, "PUT /api/repositories/1": {"success": True}}
    result, api = run(
        "update_repository",
        routes,
        repository="Photos",
        name="Pictures",
        compression="zstd",
    )
    path, body = api.puts[0]
    assert path == "/api/repositories/1"
    assert body == {"name": "Pictures", "compression": "zstd"}
    assert set(body) <= UPDATE_REPOSITORY_FIELDS
    assert "passphrase" not in UPDATE_REPOSITORY_FIELDS
    assert "path" not in UPDATE_REPOSITORY_FIELDS
    assert "Pictures" in result.text


@pytest.mark.unit
@pytest.mark.parametrize("field", ["passphrase", "path", "encryption", "connection_id"])
def test_update_repository_rejects_kept_out_fields(field):
    from pydantic import ValidationError

    from app.mcp.registry import REGISTRY

    with pytest.raises(ValidationError):
        REGISTRY["update_repository"].input_model(repository="Photos", **{field: "x"})


@pytest.mark.unit
def test_update_repository_with_nothing_to_change_does_not_put():
    result, api = run("update_repository", dict(REPOS), repository="Photos")
    assert getattr(api, "puts", []) == []
    assert result.is_error


@pytest.mark.unit
def test_set_check_schedule_rejects_bad_cron_without_put():
    routes = {
        **REPOS,
        "POST /api/schedule/validate-cron": {"success": False, "error": "bad hour"},
    }
    result, api = run(
        "set_check_schedule", routes, repository="Photos", schedule="0 25 * * *"
    )
    assert result.is_error
    assert getattr(api, "puts", []) == []


@pytest.mark.unit
def test_set_check_schedule_puts_cron_timezone_and_seconds():
    routes = {
        **REPOS,
        "POST /api/schedule/validate-cron": {
            "success": True,
            "cron_expression": "0 3 * * 0",
            "timezone": "Europe/Berlin",
            "next_runs": ["2026-11-22T02:00:00+00:00"],
        },
        "PUT /api/repositories/1/check-schedule": {"success": True},
    }
    result, api = run(
        "set_check_schedule",
        routes,
        repository="Photos",
        schedule="0 3 * * 0",
        timezone="Europe/Berlin",
        max_duration=30,
    )
    assert api.puts == [
        (
            "/api/repositories/1/check-schedule",
            {
                "cron_expression": "0 3 * * 0",
                "timezone": "Europe/Berlin",
                "max_duration": 1800,
            },
        )
    ]
    assert "Next" in result.text


@pytest.mark.unit
def test_set_restore_check_schedule_off_clears():
    routes = {**REPOS, "PUT /api/repositories/1/restore-check-schedule": {}}
    _, api = run(
        "set_restore_check_schedule", routes, repository="Photos", schedule="off"
    )
    assert api.puts == [
        ("/api/repositories/1/restore-check-schedule", {"cron_expression": ""})
    ]


@pytest.mark.unit
def test_create_repository_end_to_end_flags_and_hides(
    mcp, create_connection, admin_headers, test_db, tmp_path, skip_if_no_borg, caplog
):
    _, token = create_connection(admin_headers, name="manage", level="manage")
    session = mcp(token)
    with caplog.at_level(logging.DEBUG):
        result = session.call(
            "create_repository", name="Docs", path=str(tmp_path / "docs")
        )
    assert not result["is_error"], result
    repo = test_db.query(Repository).filter(Repository.name == "Docs").one()
    test_db.refresh(repo)
    assert repo.passphrase_unsaved is True
    secret = repo.passphrase
    assert secret
    text = repr(result)
    assert secret not in text
    assert secret not in caplog.text
    row = (
        test_db.query(McpActivity).filter(McpActivity.tool == "create_repository").one()
    )
    assert secret not in repr(
        {c.name: getattr(row, c.name) for c in McpActivity.__table__.columns}
    )
