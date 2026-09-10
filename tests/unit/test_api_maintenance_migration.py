"""Phase 5: the maintenance kinds answer from `operations` and write no
legacy rows (spec section 13, Appendix A.2)."""

import pytest

from app.database.models import Operation, Repository
from tests.utils.operations import seed_job_operation


def _repo(test_db, name="nas"):
    repo = Repository(
        name=name, path=f"/tmp/{name}", encryption="none", compression="lz4"
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


@pytest.mark.unit
class TestCheckMigration:
    def test_starting_a_check_creates_an_operation_and_no_check_job(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)

        response = test_client.post(
            f"/api/repositories/{repo.id}/check",
            json={"max_duration": 3600},
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"

        op = test_db.get(Operation, body["job_id"])
        assert op is not None
        assert op.kind == "check"
        assert op.category == "maintenance"
        assert op.trigger == "manual"
        assert op.params["max_duration"] == 3600
        # The runner may already have picked the row up in this process, so
        # assert it is not terminal rather than racing it for "queued".
        assert op.status in ("queued", "running")

    def test_a_second_check_is_rejected_with_409(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        first = test_client.post(
            f"/api/repositories/{repo.id}/check", json={}, headers=admin_headers
        )
        assert first.status_code == 200

        second = test_client.post(
            f"/api/repositories/{repo.id}/check", json={}, headers=admin_headers
        )

        assert second.status_code == 409
        assert (
            second.json()["detail"]["key"] == "backend.errors.repo.checkAlreadyRunning"
        )

    def test_a_check_queues_behind_a_running_backup_instead_of_409(
        self, test_client, test_db, admin_headers
    ):
        """The point of the phase: work waits for the lane rather than being
        refused (spec 7.2)."""
        repo = _repo(test_db)
        test_db.add(
            seed_job_operation(
                test_db,
                "backup",
                repository_id=repo.id,
                repository=repo.path,
                status="running",
            )
        )
        test_db.commit()

        response = test_client.post(
            f"/api/repositories/{repo.id}/check", json={}, headers=admin_headers
        )

        assert response.status_code == 200
        assert test_db.get(Operation, response.json()["job_id"]).status == "queued"


@pytest.mark.unit
class TestCheckReadRoutes:
    def test_status_route_serves_the_operation(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        started = test_client.post(
            f"/api/repositories/{repo.id}/check", json={}, headers=admin_headers
        ).json()

        response = test_client.get(
            f"/api/repositories/check-jobs/{started['job_id']}", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == started["job_id"]
        # The contract keeps the legacy vocabulary the frontend polls for.
        # The runner may already have picked the row up in this process (it
        # wakes on enqueue rather than waiting for its poll interval), so
        # assert it is not terminal rather than racing it for "pending".
        assert body["status"] in ("pending", "running")
        assert "progress" in body

    def test_status_route_still_serves_a_pre_phase_5_row(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        legacy = seed_job_operation(
            test_db, "check", repository_id=repo.id, status="completed", progress=100
        )
        test_db.commit()

        response = test_client.get(
            f"/api/repositories/check-jobs/{legacy.id}", headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_list_route_shows_both_worlds(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        test_db.add(
            seed_job_operation(
                test_db, "check", repository_id=repo.id, status="completed"
            )
        )
        test_db.commit()
        test_client.post(
            f"/api/repositories/{repo.id}/check", json={}, headers=admin_headers
        )

        response = test_client.get(
            f"/api/repositories/{repo.id}/check-jobs", headers=admin_headers
        )

        assert response.status_code == 200
        assert len(response.json()["jobs"]) == 2

    def test_list_route_can_filter_to_scheduled_checks(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        test_client.post(
            f"/api/repositories/{repo.id}/check", json={}, headers=admin_headers
        )

        response = test_client.get(
            f"/api/repositories/{repo.id}/check-jobs?scheduled_only=true",
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["jobs"] == []

    def test_status_route_404s_for_an_unknown_id(
        self, test_client, test_db, admin_headers
    ):
        response = test_client.get(
            "/api/repositories/check-jobs/424242", headers=admin_headers
        )

        assert response.status_code == 404


@pytest.mark.unit
class TestPruneMigration:
    def test_starting_a_prune_creates_an_operation_with_the_policy(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)

        response = test_client.post(
            f"/api/repositories/{repo.id}/prune",
            json={"keep_daily": 5, "keep_within": "2d"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        op = test_db.get(Operation, response.json()["job_id"])
        assert op.kind == "prune"
        assert op.params["keep_daily"] == 5
        assert op.params["keep_within"] == "2d"

    def test_a_dry_run_prune_answers_inline_and_is_never_queued(
        self, test_client, test_db, admin_headers, monkeypatch
    ):
        async def fake_prune(self, job_id, *args, **kwargs):
            from app.services.operations.job_facade import MaintenanceJobFacade

            op = test_db.get(Operation, job_id)
            MaintenanceJobFacade(test_db, op).status = "completed"
            test_db.commit()

        monkeypatch.setattr("app.core.borg_router.BorgRouter.prune", fake_prune)

        repo = _repo(test_db)
        response = test_client.post(
            f"/api/repositories/{repo.id}/prune",
            json={"dry_run": True},
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["dry_run"] is True
        op = test_db.get(Operation, body["job_id"])
        assert op.status == "completed"


@pytest.mark.unit
class TestCompactMigration:
    def test_starting_a_compact_creates_an_operation(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)

        response = test_client.post(
            f"/api/repositories/{repo.id}/compact", headers=admin_headers
        )

        assert response.status_code == 200
        op = test_db.get(Operation, response.json()["job_id"])
        assert op.kind == "compact"
        # The runner may already have picked the row up in this process (it
        # wakes on enqueue rather than waiting for its poll interval), so
        # assert it is not terminal rather than racing it for "queued".
        assert op.status in ("queued", "running")


@pytest.mark.unit
class TestDeleteArchiveMigration:
    def test_deleting_an_archive_queues_an_operation(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)

        response = test_client.delete(
            f"/api/archives/nightly-2026-09-01?repository={repo.path}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        op = test_db.get(Operation, response.json()["job_id"])
        assert op.kind == "delete_archive"
        assert op.params["archive_name"] == "nightly-2026-09-01"

    def test_a_second_delete_of_the_same_archive_is_rejected(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)

        test_client.delete(
            f"/api/archives/nightly-2026-09-01?repository={repo.path}",
            headers=admin_headers,
        )
        second = test_client.delete(
            f"/api/archives/nightly-2026-09-01?repository={repo.path}",
            headers=admin_headers,
        )

        assert second.status_code == 409

    def test_a_delete_of_another_archive_is_allowed(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)

        test_client.delete(
            f"/api/archives/nightly-2026-09-01?repository={repo.path}",
            headers=admin_headers,
        )
        other = test_client.delete(
            f"/api/archives/nightly-2026-09-02?repository={repo.path}",
            headers=admin_headers,
        )

        assert other.status_code == 200


@pytest.mark.unit
class TestRestoreCheckMigration:
    def test_starting_a_restore_check_creates_a_restore_category_operation(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)

        response = test_client.post(
            f"/api/repositories/{repo.id}/restore-check",
            json={"full_archive": True},
            headers=admin_headers,
        )

        assert response.status_code == 200
        op = test_db.get(Operation, response.json()["job_id"])
        assert op.kind == "restore_check"
        assert op.category == "restore"
