from unittest.mock import AsyncMock, patch

import pytest

from app.database.models import Operation, Repository


@pytest.mark.unit
def test_record_import_connect_creates_completed_row_and_followups(test_db):
    from app.services.operations.enqueue import record_import_connect
    import app.services.operations.executors.index  # noqa: F401

    repo = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    test_db.add(repo)
    test_db.commit()
    op = record_import_connect(test_db, repo, user_id=None)
    rows = test_db.query(Operation).order_by(Operation.id).all()
    assert rows[0].id == op.id
    assert rows[0].kind == "import_connect" and rows[0].status == "completed"
    assert rows[0].trigger == "import" and rows[0].completed_at is not None
    assert rows[0].result == {"verified": True}
    assert [r.kind for r in rows[1:]] == ["stats", "archive_sync"]
    assert rows[1].depends_on_id == op.id
    assert all(r.run_id == op.run_id and r.trigger == "followup" for r in rows[1:])


@pytest.mark.unit
def test_import_repository_records_operation_and_skips_inline_stats(
    test_client, test_db, admin_headers, tmp_path
):
    import app.services.operations.executors.index  # noqa: F401

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "config").write_text("[repository]\n", encoding="utf-8")
    verify_result = {"success": True, "info": {"encryption": {"mode": "none"}}}
    with (
        patch(
            "app.api.repositories.verify_existing_repository",
            new=AsyncMock(return_value=verify_result),
        ),
        patch(
            "app.core.borg_router.BorgRouter.update_stats", new=AsyncMock()
        ) as update_stats,
        patch(
            "app.api.repositories.mqtt_service.sync_state_with_db",
            return_value=None,
        ),
    ):
        response = test_client.post(
            "/api/repositories/import",
            json={
                "name": "imported",
                "path": str(repo_path),
                "encryption": "none",
                "compression": "lz4",
            },
            headers=admin_headers,
        )
    assert response.status_code in (200, 201), response.text
    update_stats.assert_not_awaited()
    repo = test_db.query(Repository).filter_by(name="imported").one()
    kinds = [
        o.kind
        for o in test_db.query(Operation)
        .filter_by(repository_id=repo.id)
        .order_by(Operation.id)
    ]
    assert kinds == ["import_connect", "stats", "archive_sync"]
    first = test_db.query(Operation).filter_by(repository_id=repo.id).first()
    assert first.status == "completed"
    assert first.triggered_by_user_id is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_import_records_operation_and_followups(test_db):
    """The agent import path returns before the server-managed handoff, so it
    needs its own coverage that import_connect and its follow-ups are queued.
    """
    import app.services.operations.executors.index  # noqa: F401
    from app.api.repositories import RepositoryImport, _create_agent_repository_record
    from app.core.security import get_password_hash
    from app.database.models import AgentMachine, User

    agent = AgentMachine(
        name="Import Agent",
        agent_id="agt_import",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.init"],
    )
    user = User(username="importer", password_hash=get_password_hash("x"), role="admin")
    test_db.add_all([agent, user])
    test_db.commit()

    payload = RepositoryImport(
        name="agent-imported",
        path="/srv/agent-repo",
        encryption="none",
        compression="lz4",
        agent_machine_id=agent.id,
        execution_target="agent",
    )
    with patch(
        "app.api.repositories.mqtt_service.sync_state_with_db", return_value=None
    ):
        await _create_agent_repository_record(payload, user, test_db, imported=True)

    repo = test_db.query(Repository).filter_by(name="agent-imported").one()
    operations = (
        test_db.query(Operation)
        .filter_by(repository_id=repo.id)
        .order_by(Operation.id)
        .all()
    )
    assert [o.kind for o in operations] == [
        "import_connect",
        "stats",
        "archive_sync",
    ]
    assert operations[0].status == "completed"
    assert operations[0].triggered_by_user_id == user.id
    assert [o.status for o in operations[1:]] == ["queued", "queued"]
    assert operations[1].depends_on_id == operations[0].id
    assert operations[2].depends_on_id == operations[1].id
    assert {o.run_id for o in operations} == {operations[0].run_id}
    assert [o.trigger for o in operations] == ["import", "followup", "followup"]
    assert [o.triggered_by_user_id for o in operations] == [user.id] * 3


def _rollback_spy(session):
    """Count rollbacks on the request session without changing their effect."""
    calls = {"n": 0}
    real_rollback = session.rollback

    def counting_rollback(*args, **kwargs):
        calls["n"] += 1
        return real_rollback(*args, **kwargs)

    return calls, counting_rollback


# The failure is injected into the enqueue step that runs AFTER the recorder
# has added and flushed the import_connect row: the row genuinely sits in the
# session when the rollback must happen. Failing the recorder itself would
# leave nothing to roll back and prove nothing.
_CHAIN_FAILURE = patch(
    "app.services.operations.enqueue.enqueue_chain",
    side_effect=RuntimeError("chain build failed"),
)


@pytest.mark.unit
def test_import_records_failure_rolls_back_the_session(
    test_client, test_db, admin_headers, tmp_path
):
    """If building the follow-up chain raises after import_connect has been
    flushed, the endpoint must roll the session back before continuing
    best-effort - otherwise the half-flushed row is committed later without
    its follow-ups, and the session is left unusable (#897 review finding)."""
    import app.services.operations.executors.index  # noqa: F401

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "config").write_text("[repository]\n", encoding="utf-8")
    verify_result = {"success": True, "info": {"encryption": {"mode": "none"}}}
    rollback_calls, counting_rollback = _rollback_spy(test_db)

    with (
        patch(
            "app.api.repositories.verify_existing_repository",
            new=AsyncMock(return_value=verify_result),
        ),
        patch("app.core.borg_router.BorgRouter.update_stats", new=AsyncMock()),
        patch(
            "app.api.repositories.mqtt_service.sync_state_with_db", return_value=None
        ),
        _CHAIN_FAILURE,
        patch.object(test_db, "rollback", counting_rollback),
    ):
        response = test_client.post(
            "/api/repositories/import",
            json={
                "name": "imported-rollback",
                "path": str(repo_path),
                "encryption": "none",
                "compression": "lz4",
            },
            headers=admin_headers,
        )

    # Best-effort: the import still succeeds despite the follow-up failure ...
    assert response.status_code in (200, 201), response.text
    # ... the session was rolled back to contain it ...
    assert rollback_calls["n"] >= 1
    # ... which discards the flushed import_connect row instead of leaving it
    # for a later commit, while the repository committed before it survives.
    assert (
        test_db.query(Operation).filter(Operation.kind == "import_connect").all() == []
    )
    assert test_db.query(Repository).filter_by(name="imported-rollback").one()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_import_failure_rolls_back_the_session(test_db):
    """The agent import path records import_connect through the same recorder
    and must roll back the same way when the enqueue step fails after the
    flush."""
    import app.services.operations.executors.index  # noqa: F401
    from app.api.repositories import RepositoryImport, _create_agent_repository_record
    from app.core.security import get_password_hash
    from app.database.models import AgentMachine, User

    agent = AgentMachine(
        name="Rollback Agent",
        agent_id="agt_rollback",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=["repository.init"],
    )
    user = User(
        username="rollback-importer", password_hash=get_password_hash("x"), role="admin"
    )
    test_db.add_all([agent, user])
    test_db.commit()
    payload = RepositoryImport(
        name="agent-rollback",
        path="/srv/agent-rollback",
        encryption="none",
        compression="lz4",
        agent_machine_id=agent.id,
        execution_target="agent",
    )
    rollback_calls, counting_rollback = _rollback_spy(test_db)

    with (
        patch(
            "app.api.repositories.mqtt_service.sync_state_with_db", return_value=None
        ),
        _CHAIN_FAILURE,
        patch.object(test_db, "rollback", counting_rollback),
    ):
        await _create_agent_repository_record(payload, user, test_db, imported=True)

    assert rollback_calls["n"] >= 1
    assert (
        test_db.query(Operation).filter(Operation.kind == "import_connect").all() == []
    )
    assert test_db.query(Repository).filter_by(name="agent-rollback").one()
