import pytest
from fastapi import HTTPException
from unittest.mock import call, patch

from app.api.schedule import (
    _dedupe_repository_ids,
    _get_schedule_target_repositories,
    _require_schedule_payload_access,
)
from app.database.models import Repository


@pytest.mark.unit
class TestScheduleHelperFunctions:
    def test_dedupe_repository_ids_preserves_order(self):
        assert _dedupe_repository_ids([3, 1, 3, 2, 1, 4]) == [3, 1, 2, 4]

    def test_dedupe_repository_ids_handles_empty_values(self):
        assert _dedupe_repository_ids([]) == []
        assert _dedupe_repository_ids(None) == []

    def test_get_schedule_target_repositories_returns_legacy_single_and_multi_repos(
        self, test_db
    ):
        legacy_repo = Repository(
            name="legacy", path="/repos/legacy", encryption="none", mode="full"
        )
        single_repo = Repository(
            name="single", path="/repos/single", encryption="none", mode="full"
        )
        multi_repo_a = Repository(
            name="multi-a", path="/repos/multi-a", encryption="none", mode="full"
        )
        multi_repo_b = Repository(
            name="multi-b", path="/repos/multi-b", encryption="none", mode="full"
        )
        test_db.add_all([legacy_repo, single_repo, multi_repo_a, multi_repo_b])
        test_db.commit()
        test_db.refresh(legacy_repo)
        test_db.refresh(single_repo)
        test_db.refresh(multi_repo_a)
        test_db.refresh(multi_repo_b)

        legacy, single, multi, unique_ids = _get_schedule_target_repositories(
            test_db,
            legacy_repo.path,
            single_repo.id,
            [multi_repo_b.id, multi_repo_a.id, multi_repo_b.id],
        )

        assert legacy.id == legacy_repo.id
        assert single.id == single_repo.id
        assert [repo.id for repo in multi] == [multi_repo_b.id, multi_repo_a.id]
        assert unique_ids == [multi_repo_b.id, multi_repo_a.id]

    def test_get_schedule_target_repositories_raises_for_missing_repository_id(
        self, test_db
    ):
        with pytest.raises(HTTPException) as exc:
            _get_schedule_target_repositories(test_db, None, 99999, None)

        assert exc.value.status_code == 404
        assert exc.value.detail["key"] == "backend.errors.schedule.repositoryNotFound"

    def test_get_schedule_target_repositories_rejects_observe_mode(self, test_db):
        observe_repo = Repository(
            name="observe-only",
            path="/repos/observe-only",
            encryption="none",
            mode="observe",
        )
        test_db.add(observe_repo)
        test_db.commit()
        test_db.refresh(observe_repo)

        with pytest.raises(HTTPException) as exc:
            _get_schedule_target_repositories(test_db, None, observe_repo.id, None)

        assert exc.value.status_code == 400
        assert (
            exc.value.detail["key"] == "backend.errors.schedule.observabilityOnlyRepo"
        )

    def test_require_schedule_payload_access_checks_each_repository(
        self, test_db, admin_user
    ):
        legacy_repo = Repository(
            name="legacy", path="/repos/legacy", encryption="none", mode="full"
        )
        single_repo = Repository(
            name="single", path="/repos/single", encryption="none", mode="full"
        )
        multi_repo = Repository(
            name="multi", path="/repos/multi", encryption="none", mode="full"
        )
        test_db.add_all([legacy_repo, single_repo, multi_repo])
        test_db.commit()
        test_db.refresh(legacy_repo)
        test_db.refresh(single_repo)
        test_db.refresh(multi_repo)

        with patch("app.api.schedule.check_repo_access") as mock_check:
            legacy, single, multi, unique_ids = _require_schedule_payload_access(
                test_db,
                admin_user,
                legacy_repo.path,
                single_repo.id,
                [multi_repo.id, multi_repo.id],
                "operator",
            )

        assert legacy.id == legacy_repo.id
        assert single.id == single_repo.id
        assert [repo.id for repo in multi] == [multi_repo.id]
        assert unique_ids == [multi_repo.id]
        assert mock_check.call_args_list == [
            call(test_db, admin_user, legacy_repo, "operator"),
            call(test_db, admin_user, single_repo, "operator"),
            call(test_db, admin_user, multi_repo, "operator"),
        ]
