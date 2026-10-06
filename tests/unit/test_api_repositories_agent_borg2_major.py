"""An agent repository is recorded with the Borg major the server path reads.

``POST /api/repositories/`` and ``/import`` read a payload as Borg 2 when it
says ``borg_version: 2`` or names an encryption mode only Borg 2 has. A server
repository goes to the Borg 2 routes then; an agent repository is recorded and
initialised with that major too, and refused where those routes refuse.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.borg2 import BORG2_ENCRYPTION_MODES, REMOVED_REPOSITORY_URL_MESSAGE
from app.database.models import AgentJob, Repository
from tests.unit.test_api_repositories_store_url_borg1 import (
    ROUTES,
    _enable_paid_features,
    _executor_fields,
    _post,
)

BORG2_ONLY_MODES = [
    "repokey-aes-ocb",
    "repokey-chacha20-poly1305",
    "keyfile-aes-ocb",
    "keyfile-chacha20-poly1305",
]


def _payload(test_db, **fields) -> dict:
    return {
        "name": "Agent Repo",
        "path": "/agent/repo",
        "passphrase": "hunter2",
        "compression": "lz4",
        **_executor_fields("agent", test_db),
        **fields,
    }


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("mode", BORG2_ONLY_MODES)
@pytest.mark.parametrize("version_fields", [{"borg_version": 1}, {}])
def test_borg2_mode_records_agent_repository_as_borg2(
    test_client: TestClient, admin_headers, test_db, route, mode, version_fields
):
    _enable_paid_features(test_db)
    payload = _payload(test_db, encryption=mode, **version_fields)

    response, _, _ = _post(test_client, admin_headers, route, payload)

    assert response.status_code == 200, response.text
    repository = test_db.query(Repository).one()
    assert repository.borg_version == 2
    assert repository.encryption == mode
    # Create asks the agent to run repository.init with Borg 2; import runs none.
    jobs = test_db.query(AgentJob).all()
    if route.endswith("/import"):
        assert jobs == []
    else:
        assert [job.payload["repository"]["borg_version"] for job in jobs] == [2]


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("mode", ["repokey", "keyfile", "repokey-blake2", "none"])
def test_borg1_payload_records_agent_repository_as_borg1(
    test_client: TestClient, admin_headers, test_db, route, mode
):
    _enable_paid_features(test_db)
    payload = _payload(test_db, encryption=mode)

    response, _, _ = _post(test_client, admin_headers, route, payload)

    assert response.status_code == 200, response.text
    assert test_db.query(Repository).one().borg_version == 1


@pytest.mark.unit
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("mode", BORG2_ENCRYPTION_MODES)
def test_borg2_version_with_borg2_mode_is_recorded_as_borg2(
    test_client: TestClient, admin_headers, test_db, route, mode
):
    _enable_paid_features(test_db)
    payload = _payload(test_db, encryption=mode, borg_version=2)

    response, _, _ = _post(test_client, admin_headers, route, payload)

    assert response.status_code == 200, response.text
    assert test_db.query(Repository).one().borg_version == 2


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["repokey", "keyfile-blake2", "none", "bogus"])
def test_borg2_agent_create_refuses_a_mode_repo_create_does_not_know(
    test_client: TestClient, admin_headers, test_db, mode
):
    """The Borg 2 create route refuses these before Borg runs; so does the
    agent path, instead of queueing a repository.init bound to fail."""
    _enable_paid_features(test_db)
    payload = _payload(test_db, encryption=mode, borg_version=2)

    response, _, _ = _post(test_client, admin_headers, ROUTES[0], payload)

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == {
        "key": "backend.errors.repo.invalidEncryption",
        "params": {"mode": mode, "valid": BORG2_ENCRYPTION_MODES},
    }
    assert test_db.query(AgentJob).count() == 0
    assert test_db.query(Repository).count() == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("route", "key"),
    [
        (ROUTES[0], "backend.errors.repo.initFailed"),
        (ROUTES[1], "backend.errors.repo.verificationFailed"),
    ],
)
@pytest.mark.parametrize("version_fields", [{"borg_version": 2}, {}])
def test_borg2_agent_repository_refuses_a_rest_url(
    test_client: TestClient, admin_headers, test_db, route, key, version_fields
):
    """Borg 2 reads rest:// as a local directory; the Borg 2 routes answer
    with this text, and so does the agent path."""
    _enable_paid_features(test_db)
    payload = _payload(
        test_db,
        path="rest://borg@backup.example.com/srv/repo",
        encryption="repokey-aes-ocb",
        **version_fields,
    )

    response, _, _ = _post(test_client, admin_headers, route, payload)

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == {
        "key": key,
        "params": {"error": REMOVED_REPOSITORY_URL_MESSAGE},
    }
    assert test_db.query(AgentJob).count() == 0
    assert test_db.query(Repository).count() == 0
