"""Borg 1's short SSH form is refused for a Borg 2 repository.

Borg 1 reads ``[user@]host:path`` as an SSH address. Borg 2 has no such form:
it reads the text as a local directory, so the repository would be created on
the machine that runs Borg instead of that host.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.borg2 import borg1_ssh_address_host
from app.database.models import AgentJob, Repository
from tests.unit.test_api_repositories_store_url_borg1 import (
    EXECUTORS,
    ROUTES,
    _enable_paid_features,
    _executor_fields,
    _post,
    _put,
    _stored_repository,
)

ADDRESSES = [
    ("borg@backup.example.com:repo", "borg@backup.example.com"),
    ("borg@backup.example.com:/srv/repo", "borg@backup.example.com"),
    ("backup.example.com:/srv/repo", "backup.example.com"),
    ("  backup:repo", "backup"),
]

NOT_ADDRESSES = [
    "/srv/backups/repo",
    "/srv/backups/a@b:c",
    "relative/dir:x",
    "file:///srv/backups/repo",
    "ssh://borg@backup.example.com/./repo",
    "sftp://borg@backup.example.com/srv/repo",
    "s3:profile@/bucket/repo",
    "b2:bucket/repo",
    "rclone:remote:repo",
    "",
    None,
]


def _refusal(host: str) -> dict:
    return {
        "key": "backend.errors.repo.borg1OnlySshAddress",
        "params": {"host": host},
    }


@pytest.mark.unit
@pytest.mark.parametrize(("path", "host"), ADDRESSES)
def test_short_ssh_form_names_its_host(path, host):
    assert borg1_ssh_address_host(path) == host


@pytest.mark.unit
@pytest.mark.parametrize("path", NOT_ADDRESSES)
def test_other_paths_are_no_short_ssh_form(path):
    assert borg1_ssh_address_host(path) is None


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("executor", EXECUTORS)
@pytest.mark.parametrize(("path", "host"), ADDRESSES)
@pytest.mark.parametrize("version_fields", [{"borg_version": 2}, {}])
def test_short_ssh_form_is_refused_for_borg2(
    test_client: TestClient,
    admin_headers,
    test_db,
    route,
    executor,
    path,
    host,
    version_fields,
):
    """By version or by a Borg 2 encryption mode alike."""
    _enable_paid_features(test_db)
    payload = {
        "name": "Borg 2 Repo",
        "path": path,
        "encryption": "repokey-aes-ocb",
        "passphrase": "hunter2",
        "compression": "lz4",
        **version_fields,
        **_executor_fields(executor, test_db),
    }

    response, initialize, verify = _post(test_client, admin_headers, route, payload)

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == _refusal(host)
    initialize.assert_not_awaited()
    verify.assert_not_awaited()
    assert test_db.query(AgentJob).count() == 0
    assert test_db.query(Repository).count() == 0


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
def test_borg2_directory_on_an_ssh_connection_may_hold_a_colon(
    test_client: TestClient, admin_headers, test_db, route
):
    """With a connection the path is a directory on that host."""
    _enable_paid_features(test_db)
    payload = {
        "name": "Borg 2 Repo",
        "path": "backup:archive",
        "encryption": "repokey-aes-ocb",
        "passphrase": "hunter2",
        "compression": "lz4",
        "borg_version": 2,
        **_executor_fields("connection", test_db),
    }

    response, _, _ = _post(test_client, admin_headers, route, payload)

    assert response.status_code in (200, 201), response.text
    assert test_db.query(Repository).one().borg_version == 2


@pytest.mark.unit
@pytest.mark.parametrize("executor", EXECUTORS)
@pytest.mark.parametrize(("path", "host"), ADDRESSES)
def test_update_refuses_short_ssh_form_for_borg2_repository(
    test_client: TestClient, admin_headers, test_db, executor, path, host
):
    _enable_paid_features(test_db)
    repository = _stored_repository(
        test_db, executor, borg_version=2, encryption="repokey-aes-ocb"
    )
    stored_path = repository.path

    response, router = _put(test_client, admin_headers, repository.id, {"path": path})

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == _refusal(host.strip())
    router.assert_not_called()
    test_db.expire_all()
    assert test_db.query(Repository).one().path == stored_path


@pytest.mark.unit
@pytest.mark.parametrize("executor", EXECUTORS)
def test_update_keeps_a_borg2_row_recorded_with_the_short_ssh_form(
    test_client: TestClient, admin_headers, test_db, executor
):
    """Only a new path is checked: the form resends the stored one."""
    _enable_paid_features(test_db)
    path = "borg@backup.example.com:repo"
    repository = _stored_repository(
        test_db, executor, borg_version=2, encryption="repokey-aes-ocb", path=path
    )

    response, _ = _put(
        test_client,
        admin_headers,
        repository.id,
        {"name": "Renamed", "path": path, "connection_id": None},
    )

    assert response.status_code == 200, response.text
    test_db.expire_all()
    assert test_db.query(Repository).one().name == "Renamed"


@pytest.mark.unit
@pytest.mark.parametrize(
    "route", ["/api/v2/repositories/", "/api/v2/repositories/import"]
)
@pytest.mark.parametrize(("path", "host"), ADDRESSES)
def test_borg2_routes_refuse_the_short_ssh_form(
    test_client: TestClient, admin_headers, test_db, route, path, host
):
    """The Borg 2 routes are an API of their own, not only the v1 routes'
    delegate."""
    _enable_paid_features(test_db)
    payload = {
        "name": "Borg 2 Repo",
        "path": path,
        "encryption": "repokey-aes-ocb",
        "passphrase": "hunter2",
    }

    response, initialize, verify = _post(test_client, admin_headers, route, payload)

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == _refusal(host)
    assert test_db.query(Repository).count() == 0
