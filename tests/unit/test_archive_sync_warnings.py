"""Persistent listing failures are visible without clearing stored archive data."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.database.models import Repository
from tests.utils.operations import seed_operation


@pytest.mark.parametrize(
    "statuses, warned",
    [
        ([], False),
        (["failed"], False),
        (["failed", "failed"], True),
        (["completed", "failed", "failed"], True),
        (["failed", "completed", "failed"], False),
        (["failed", "failed", "completed"], False),
        (["failed", "failed", "completed_with_warnings"], False),
        (["failed", "failed", "running"], True),
        (["failed", "failed", "cancelled"], True),
        (["failed", "failed", "skipped"], True),
    ],
)
def test_repository_warning_tracks_consecutive_sync_failures(
    test_client, test_db, admin_headers, statuses, warned
):
    repo = Repository(name="Archive", path="/repos/archive", encryption="none")
    test_db.add(repo)
    test_db.commit()
    start = datetime(2026, 10, 26, 1)
    for offset, status in enumerate(statuses):
        at = start + timedelta(minutes=offset)
        seed_operation(
            test_db,
            "archive_sync",
            repository_id=repo.id,
            status=status,
            created_at=at,
            completed_at=None if status == "running" else at,
            error_message="SSH key cannot be decrypted. Re-import the original key."
            if status == "failed"
            else None,
        )

    response = test_client.get("/api/repositories/", headers=admin_headers)
    assert response.status_code == 200
    row = next(row for row in response.json()["repositories"] if row["id"] == repo.id)
    warning = row["archive_sync_warning"]
    assert (warning is not None) is warned
    if warned:
        assert warning["operation_id"] > 0
        assert "Re-import the original key" in warning["error_message"]
        assert warning["last_success_at"] == (
            "2026-10-26T01:00:00+00:00" if statuses[0] == "completed" else None
        )


def test_warning_is_scoped_and_off_mode_suppresses_it(
    test_client, test_db, admin_headers
):
    enabled = Repository(name="enabled", path="/repos/enabled", encryption="none")
    disabled = Repository(
        name="disabled", path="/repos/disabled", encryption="none", index_mode="off"
    )
    clean = Repository(name="clean", path="/repos/clean", encryption="none")
    test_db.add_all([enabled, disabled, clean])
    test_db.commit()
    for repo in (enabled, disabled):
        for offset in range(2):
            seed_operation(
                test_db,
                "archive_sync",
                repository_id=repo.id,
                status="failed",
                completed_at=datetime(2026, 10, 26, 1, offset),
                error_message="Connection refused BORG_PASSPHRASE=fixture-secret",
            )
    for offset in range(2):
        seed_operation(
            test_db,
            "stats",
            repository_id=clean.id,
            status="failed",
            completed_at=datetime(2026, 10, 26, 1, offset),
        )

    response = test_client.get("/api/repositories/", headers=admin_headers)
    assert response.status_code == 200
    rows = {row["id"]: row for row in response.json()["repositories"]}
    assert (
        "Connection refused"
        in rows[enabled.id]["archive_sync_warning"]["error_message"]
    )
    assert "fixture-secret" not in response.text
    assert rows[disabled.id]["archive_sync_warning"] is None
    assert rows[clean.id]["archive_sync_warning"] is None

    # Detail reads would otherwise ask Borg for live statistics. The warning
    # is derived only from the same stored operations used by the list.
    with patch(
        "app.api.repositories.get_repository_stats", new=AsyncMock(return_value={})
    ):
        detail = test_client.get(
            f"/api/repositories/{enabled.id}", headers=admin_headers
        )
    assert detail.status_code == 200
    assert (
        detail.json()["repository"]["archive_sync_warning"]
        == rows[enabled.id]["archive_sync_warning"]
    )
