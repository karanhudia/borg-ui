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
