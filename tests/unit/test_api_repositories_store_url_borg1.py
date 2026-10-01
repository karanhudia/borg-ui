"""A repository URL only Borg 2 can open is refused for a Borg 1 repository.

Borg 1 rejects none of these URLs: it reads ``sftp://host/repo`` as a local
directory and ``s3:bucket`` as an ssh host named ``s3``, so a row recorded that
way fails on every job with an error that names something else.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.repositories import (
    RepositoryCreate,
    RepositoryImport,
    _reject_borg2_only_url_for_borg1,
    _uses_borg2_payload,
)
from app.core.security import get_password_hash
from app.database.models import (
    AgentJob,
    AgentMachine,
    LicensingState,
    Repository,
    SSHConnection,
)

ERROR_KEYS = {
    "backend.errors.repo.borg2OnlyUrl",
    "backend.errors.repo.borg2OnlyUrlOrSshHost",
}


def _refusal(scheme: str, executor: str = "agent") -> dict:
    if scheme.endswith("//") or executor != "agent":
        return {
            "key": "backend.errors.repo.borg2OnlyUrl",
            "params": {"scheme": scheme},
        }
    # An agent hands `name:path` to Borg 1, which reads an ssh host: the answer
    # names the host too.
    return {
        "key": "backend.errors.repo.borg2OnlyUrlOrSshHost",
        "params": {"scheme": scheme, "host": scheme[:-1]},
    }


BORG2_ONLY_URLS = [
    ("rest://", "rest://borg@backup.example.com/srv/repo"),
    ("sftp://", "sftp://borg@backup.example.com:22/srv/repo"),
    ("http://", "http://backup.example.com:8080/repo"),
    ("https://", "https://backup.example.com/repo"),
    ("s3:", "s3:profile@/bucket/repo"),
    ("b2:", "b2:bucket/repo"),
    ("rclone:", "rclone:remote:repo"),
]

BORG1_URLS = [
    "/srv/backups/repo",
    "file:///srv/backups/repo",
    "ssh://borg@backup.example.com:22/./repo",
    "borg@backup.example.com:repo",
    "backup.example.com:/srv/repo",
    # Only the scheme position counts: these are a host and a directory.
    "borg@s3:repo",
    "/srv/backups/s3:archive",
]


def _enable_paid_features(test_db) -> None:
    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="test-instance-store-url-borg1")
        test_db.add(state)
    state.plan = "pro"
    state.status = "active"
    state.is_trial = False
    test_db.commit()


def _agent(test_db) -> AgentMachine:
    agent = AgentMachine(
        name="Store URL Agent",
        agent_id="agt_store_url",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.init"],
        borg_versions=[
            {"major": 1, "version": "1.4.5", "path": "/usr/local/bin/borg"},
            {"major": 2, "version": "2.0.0b24", "path": "/usr/local/bin/borg2"},
        ],
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)
    return agent


def _ssh_connection(test_db) -> SSHConnection:
    connection = SSHConnection(host="backup.example.com", username="borg", port=22)
    test_db.add(connection)
    test_db.commit()
    test_db.refresh(connection)
    return connection


def _executor_fields(executor: str, test_db) -> dict:
    if executor == "agent":
        return {
            "executor_type": "agent",
            "execution_target": "agent",
            "agent_machine_id": _agent(test_db).id,
        }
    if executor == "connection":
        return {"connection_id": _ssh_connection(test_db).id}
    return {}


def _post(test_client: TestClient, admin_headers, route: str, payload: dict):
    """Post with every Borg call stubbed, so a payload that gets past the
    validation is recorded the way a reachable repository would be."""
    with (
        patch(
            "app.api.repositories.initialize_borg_repository",
            new=AsyncMock(return_value={"success": True}),
        ) as initialize,
        patch(
            "app.api.repositories.verify_existing_repository",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "info": {"encryption": {"mode": "none"}},
                }
            ),
        ) as verify,
        patch(
            "app.api.repositories.wait_for_agent_repository_operation_job",
            new=AsyncMock(return_value={"status": "completed"}),
        ),
        patch(
            "app.api.repositories.dispatch_agent_job_best_effort",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.api.v2.repositories._rcreate",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "already_existed": False,
                    "stdout": "",
                    "stderr": "",
                }
            ),
        ),
        patch(
            "app.api.v2.repositories._rinfo",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "stdout": json.dumps({"repository": {"id": 1}}),
                    "stderr": "",
                }
            ),
        ),
        patch("app.api.repositories.mqtt_service.sync_state_with_db"),
    ):
        response = test_client.post(route, json=payload, headers=admin_headers)
    return response, initialize, verify


ROUTES = ["/api/repositories/", "/api/repositories/import"]
# With an SSH connection the path is a directory on that host, not a URL.
EXECUTORS = ["server", "agent"]
CONNECTION_URL = "ssh://borg@backup.example.com:22"
CONNECTION_PATHS = [
    ("/srv/backups/repo", f"{CONNECTION_URL}/srv/backups/repo"),
    (f"{CONNECTION_URL}/srv/backups/repo", f"{CONNECTION_URL}/srv/backups/repo"),
    ("s3:archive", f"{CONNECTION_URL}/s3:archive"),
    ("b2:archive", f"{CONNECTION_URL}/b2:archive"),
    ("rclone:archive", f"{CONNECTION_URL}/rclone:archive"),
]


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("executor", EXECUTORS)
@pytest.mark.parametrize(("scheme", "url"), BORG2_ONLY_URLS)
@pytest.mark.parametrize("version_fields", [{"borg_version": 1}, {}])
def test_borg2_only_url_is_refused_for_borg1(
    test_client: TestClient,
    admin_headers,
    test_db,
    route,
    executor,
    scheme,
    url,
    version_fields,
):
    _enable_paid_features(test_db)
    payload = {
        "name": "Store URL Repo",
        "path": url,
        "encryption": "none",
        "compression": "lz4",
        **version_fields,
        **_executor_fields(executor, test_db),
    }

    response, initialize, verify = _post(test_client, admin_headers, route, payload)

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == _refusal(scheme, executor)
    initialize.assert_not_awaited()
    verify.assert_not_awaited()
    assert test_db.query(AgentJob).count() == 0
    assert test_db.query(Repository).count() == 0


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(("scheme", "url"), BORG2_ONLY_URLS)
@pytest.mark.parametrize("version_fields", [{"borg_version": 1}, {}])
def test_agent_repository_is_refused_by_the_major_it_would_be_recorded_with(
    test_client: TestClient, admin_headers, test_db, route, scheme, url, version_fields
):
    """A Borg 2 encryption mode sends a server payload to the Borg 2 routes;
    an agent repository keeps the major the payload states."""
    _enable_paid_features(test_db)
    payload = {
        "name": "Store URL Repo",
        "path": url,
        "encryption": "repokey-aes-ocb",
        "passphrase": "hunter2",
        "compression": "lz4",
        **version_fields,
        **_executor_fields("agent", test_db),
    }

    response, _, _ = _post(test_client, admin_headers, route, payload)

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == _refusal(scheme)
    assert test_db.query(AgentJob).count() == 0
    assert test_db.query(Repository).count() == 0


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("alias", ["s3", "b2", "rclone"])
@pytest.mark.parametrize(
    ("scp_path", "ssh_path"), [("/srv/repo", "/srv/repo"), ("repo", "/./repo")]
)
def test_ssh_host_named_like_a_store_needs_the_ssh_url_form(
    test_client: TestClient, admin_headers, test_db, route, alias, scp_path, ssh_path
):
    """`s3:/srv/repo` is an ssh host for Borg 1 and a bucket for Borg 2; the
    text cannot tell which one is meant, `ssh://s3/srv/repo` can."""
    _enable_paid_features(test_db)
    payload = {
        "name": "Alias Repo",
        "encryption": "none",
        "compression": "lz4",
        "borg_version": 1,
        **_executor_fields("agent", test_db),
    }

    refused, _, _ = _post(
        test_client, admin_headers, route, {**payload, "path": f"{alias}:{scp_path}"}
    )
    accepted, _, _ = _post(
        test_client,
        admin_headers,
        route,
        {**payload, "path": f"ssh://{alias}{ssh_path}"},
    )

    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"] == _refusal(f"{alias}:")
    assert accepted.status_code == 200, accepted.text
    assert test_db.query(Repository).one().path == f"ssh://{alias}{ssh_path}"


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("alias", ["s3", "b2", "rclone"])
def test_server_repository_is_not_pointed_at_an_ssh_url(
    test_client: TestClient, admin_headers, test_db, route, alias
):
    """The server reaches an ssh host through an SSH connection only, so the
    hint an agent gets would lead a server repository into the next refusal."""
    payload = {
        "name": "Server Repo",
        "encryption": "none",
        "compression": "lz4",
        "borg_version": 1,
    }

    refused, _, _ = _post(
        test_client, admin_headers, route, {**payload, "path": f"{alias}:/srv/repo"}
    )
    ssh_url, _, _ = _post(
        test_client,
        admin_headers,
        route,
        {**payload, "path": f"ssh://{alias}/srv/repo"},
    )

    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"] == _refusal(f"{alias}:", "server")
    assert ssh_url.status_code == 400, ssh_url.text
    assert (
        ssh_url.json()["detail"]["key"]
        == "backend.errors.repo.sshUrlWithoutConnectionId"
    )
    assert test_db.query(Repository).count() == 0


@pytest.mark.unit
@pytest.mark.parametrize("url", ["SFTP://backup.example.com/repo", "  s3:bucket/repo"])
def test_borg2_only_url_match_ignores_case_and_leading_space(
    test_client: TestClient, admin_headers, test_db, url
):
    _enable_paid_features(test_db)
    payload = {
        "name": "Store URL Repo",
        "path": url,
        "encryption": "none",
        "borg_version": 1,
        **_executor_fields("agent", test_db),
    }

    response, _, _ = _post(
        test_client, admin_headers, "/api/repositories/import", payload
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["key"] in ERROR_KEYS
    assert test_db.query(Repository).count() == 0


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("url", BORG1_URLS)
def test_borg1_agent_repository_keeps_every_borg1_url(
    test_client: TestClient, admin_headers, test_db, route, url
):
    _enable_paid_features(test_db)
    payload = {
        "name": "Borg 1 Agent Repo",
        "path": url,
        "encryption": "none",
        "compression": "lz4",
        "borg_version": 1,
        **_executor_fields("agent", test_db),
    }

    response, _, _ = _post(test_client, admin_headers, route, payload)

    assert response.status_code == 200, response.text
    repository = test_db.query(Repository).one()
    assert repository.path == url
    assert repository.borg_version == 1


@pytest.mark.unit
def test_borg1_server_repository_keeps_local_path(
    test_client: TestClient, admin_headers, test_db, tmp_path
):
    payload = {
        "name": "Borg 1 Local Repo",
        "path": str(tmp_path / "repo"),
        "encryption": "none",
        "compression": "lz4",
        "borg_version": 1,
    }

    response, initialize, _ = _post(
        test_client, admin_headers, "/api/repositories/", payload
    )

    assert response.status_code == 200, response.text
    initialize.assert_awaited_once()
    assert test_db.query(Repository).one().borg_version == 1


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(("path", "stored_path"), CONNECTION_PATHS)
def test_borg1_connection_repository_keeps_ssh_target(
    test_client: TestClient, admin_headers, test_db, route, path, stored_path
):
    payload = {
        "name": "Borg 1 SSH Repo",
        "path": path,
        "encryption": "none",
        "compression": "lz4",
        "borg_version": 1,
        **_executor_fields("connection", test_db),
    }

    response, _, _ = _post(test_client, admin_headers, route, payload)

    assert response.status_code == 200, response.text
    repository = test_db.query(Repository).one()
    assert repository.path == stored_path
    assert repository.borg_version == 1


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("executor", ["server", "agent"])
@pytest.mark.parametrize(("scheme", "url"), BORG2_ONLY_URLS)
def test_borg2_repository_keeps_every_store_url(
    test_client: TestClient, admin_headers, test_db, route, executor, scheme, url
):
    _enable_paid_features(test_db)
    payload = {
        "name": "Borg 2 Store Repo",
        "path": url,
        "encryption": "repokey-aes-ocb",
        "passphrase": "hunter2",
        "compression": "lz4",
        "borg_version": 2,
        **_executor_fields(executor, test_db),
    }

    response, _, _ = _post(test_client, admin_headers, route, payload)

    assert response.status_code in (200, 201), response.text
    repository = test_db.query(Repository).one()
    assert repository.path == url
    assert repository.borg_version == 2


@pytest.mark.unit
@pytest.mark.parametrize("model", [RepositoryCreate, RepositoryImport])
@pytest.mark.parametrize(("scheme", "url"), BORG2_ONLY_URLS)
def test_guard_follows_the_major_the_payload_selects(model, scheme, url):
    def check(agent=True, **fields):
        payload = model(name="r", path=url, **fields)
        _reject_borg2_only_url_for_borg1(
            payload.path,
            borg2=_uses_borg2_payload(payload),
            connection_id=payload.connection_id,
            agent=agent,
        )

    for agent, executor in ((True, "agent"), (False, "server")):
        with pytest.raises(HTTPException) as refused:
            check(agent=agent, borg_version=1)
        assert refused.value.status_code == 400
        assert refused.value.detail == _refusal(scheme, executor)

    check(borg_version=2)
    # A Borg 2 encryption mode selects Borg 2 the same way the routes read it.
    check(encryption="repokey-aes-ocb")
    check(borg_version=1, connection_id=7)


def _stored_repository(test_db, executor: str, **fields) -> Repository:
    values = {
        "name": "Stored Repo",
        "path": "/srv/backups/repo",
        "encryption": "none",
        "compression": "lz4",
        "repository_type": "local",
        "borg_version": 1,
    }
    if executor == "agent":
        values.update(
            executor_type="agent",
            execution_target="agent",
            agent_machine_id=_agent(test_db).id,
        )
    elif executor == "connection":
        connection = _ssh_connection(test_db)
        values.update(
            connection_id=connection.id,
            repository_type="ssh",
            path=f"{CONNECTION_URL}/srv/backups/repo",
        )
    values.update(fields)
    repository = Repository(**values)
    test_db.add(repository)
    test_db.commit()
    test_db.refresh(repository)
    return repository


def _put(test_client: TestClient, admin_headers, repository_id: int, payload: dict):
    with (
        patch("app.api.repositories.BorgRouter") as router,
        patch("app.api.repositories.mqtt_service.sync_state_with_db"),
    ):
        router.return_value.verify_repository = AsyncMock(
            return_value={"success": True}
        )
        router.return_value.initialize_repository = AsyncMock(
            return_value={"success": True}
        )
        # The route asks the router for the URL it saves. These repositories
        # are Borg 1, for which the router hands back the URL the route built.
        router.return_value.ssh_repository_url.side_effect = (
            lambda raw_path, connection_details, borg1_url=None: borg1_url
        )
        response = test_client.put(
            f"/api/repositories/{repository_id}", json=payload, headers=admin_headers
        )
    return response, router


@pytest.mark.unit
@pytest.mark.parametrize("executor", EXECUTORS)
@pytest.mark.parametrize(("scheme", "url"), BORG2_ONLY_URLS)
def test_update_refuses_borg2_only_url_for_borg1_repository(
    test_client: TestClient, admin_headers, test_db, executor, scheme, url
):
    _enable_paid_features(test_db)
    repository = _stored_repository(test_db, executor)
    stored_path = repository.path

    response, router = _put(test_client, admin_headers, repository.id, {"path": url})

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == _refusal(scheme, executor)
    router.assert_not_called()
    test_db.expire_all()
    assert test_db.query(Repository).one().path == stored_path


@pytest.mark.unit
@pytest.mark.parametrize(("path", "stored_path"), CONNECTION_PATHS)
def test_update_keeps_directory_on_ssh_connection(
    test_client: TestClient, admin_headers, test_db, path, stored_path
):
    repository = _stored_repository(
        test_db, "connection", path=f"{CONNECTION_URL}/srv/backups/old"
    )

    response, _ = _put(test_client, admin_headers, repository.id, {"path": path})

    assert response.status_code == 200, response.text
    test_db.expire_all()
    row = test_db.query(Repository).one()
    assert (row.path, row.borg_version) == (stored_path, 1)


@pytest.mark.unit
@pytest.mark.parametrize(("scheme", "url"), BORG2_ONLY_URLS)
def test_update_refuses_store_url_when_the_connection_is_removed(
    test_client: TestClient, admin_headers, test_db, scheme, url
):
    repository = _stored_repository(test_db, "connection")
    stored_path = repository.path

    response, router = _put(
        test_client,
        admin_headers,
        repository.id,
        {"path": url, "connection_id": None},
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == _refusal(scheme, "server")
    router.assert_not_called()
    test_db.expire_all()
    assert test_db.query(Repository).one().path == stored_path


@pytest.mark.unit
@pytest.mark.parametrize(("scheme", "url"), BORG2_ONLY_URLS)
def test_update_keeps_store_url_for_borg2_repository(
    test_client: TestClient, admin_headers, test_db, scheme, url
):
    _enable_paid_features(test_db)
    repository = _stored_repository(
        test_db, "agent", borg_version=2, path="/srv/backups/borg2"
    )

    response, _ = _put(test_client, admin_headers, repository.id, {"path": url})

    assert response.status_code == 200, response.text
    test_db.expire_all()
    assert test_db.query(Repository).one().path == url


@pytest.mark.unit
@pytest.mark.parametrize(
    "path", ["/srv/backups/moved", "ssh://borg@backup.example.com:22/./moved"]
)
def test_update_keeps_borg1_path_change(
    test_client: TestClient, admin_headers, test_db, path
):
    _enable_paid_features(test_db)
    repository = _stored_repository(test_db, "agent")

    response, _ = _put(test_client, admin_headers, repository.id, {"path": path})

    assert response.status_code == 200, response.text
    test_db.expire_all()
    assert test_db.query(Repository).one().path == path


@pytest.mark.unit
@pytest.mark.parametrize("executor", EXECUTORS)
@pytest.mark.parametrize(("scheme", "url"), BORG2_ONLY_URLS)
def test_update_of_a_row_recorded_before_the_refusal_still_works(
    test_client: TestClient, admin_headers, test_db, executor, scheme, url
):
    """The edit form sends the stored path and `connection_id` (null without an
    SSH connection) with every change; neither makes the path a new one."""
    _enable_paid_features(test_db)
    repository = _stored_repository(test_db, executor, path=url)

    response, router = _put(
        test_client,
        admin_headers,
        repository.id,
        {"name": "Renamed", "path": url, "connection_id": None},
    )

    assert response.status_code == 200, response.text
    router.assert_not_called()
    test_db.expire_all()
    row = test_db.query(Repository).one()
    assert (row.name, row.path, row.borg_version) == ("Renamed", url, 1)
