"""Routes refuse a custom flag the repository's Borg major does not have (#1263).

The flag is refused where it is entered, with the allowlist's reason, instead
of failing every backup or check at Borg's argument parsing (exit 2).
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.database.models import BackupPlan, Repository


def _repo(test_db, borg_version: int, **fields) -> Repository:
    repo = Repository(
        name=f"Borg {borg_version}",
        path=f"/repos/borg{borg_version}",
        encryption="none" if borg_version == 1 else "authenticated",
        repository_type="local",
        mode="full",
        borg_version=borg_version,
        **fields,
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


def _plan(repo_ids: list[int], **overrides) -> dict:
    payload = {
        "name": "Plan",
        "source_type": "local",
        "source_directories": ["/srv/project"],
        "compression": "lz4",
        "custom_flags": None,
        "check_extra_flags": None,
        "repositories": [
            {"repository_id": repo_id, "enabled": True, "execution_order": index + 1}
            for index, repo_id in enumerate(repo_ids)
        ],
    }
    payload.update(overrides)
    return payload


def _assert_refused(response, flag: str) -> None:
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["key"] == "backend.errors.repo.invalidBorgFlags"
    assert flag in detail["params"]["reason"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides,flag",
    [
        ({"custom_flags": "--upload-ratelimit 512"}, "--upload-ratelimit"),
        (
            {"check_extra_flags": "--save-space", "run_check_after": True},
            "--save-space",
        ),
    ],
)
def test_plan_refuses_a_flag_a_linked_borg2_repository_lacks(
    test_client: TestClient, admin_headers, test_db, overrides, flag
):
    borg1 = _repo(test_db, 1)
    borg2 = _repo(test_db, 2)

    response = test_client.post(
        "/api/backup-plans/",
        json=_plan([borg1.id, borg2.id], **overrides),
        headers=admin_headers,
    )

    _assert_refused(response, flag)
    assert "Borg 2" in response.json()["detail"]["params"]["reason"]
    assert test_db.query(BackupPlan).count() == 0


@pytest.mark.unit
def test_plan_link_override_is_checked_against_its_own_repository(
    test_client: TestClient, admin_headers, test_db
):
    borg1 = _repo(test_db, 1)
    borg2 = _repo(test_db, 2)

    def plan(repo, name):
        payload = _plan([repo.id], name=name, custom_flags="--stats")
        payload["repositories"][0]["custom_flags_override"] = "--noatime"
        return test_client.post(
            "/api/backup-plans/", json=payload, headers=admin_headers
        )

    accepted = plan(borg1, "Borg 1 plan")
    assert accepted.status_code in (200, 201), accepted.text
    _assert_refused(plan(borg2, "Borg 2 plan"), "--noatime")


@pytest.mark.unit
def test_plan_without_flags_checks_the_repository_flags_it_falls_back_to(
    test_client: TestClient, admin_headers, test_db
):
    """With neither a plan nor a link value the backup takes the
    repository's own flags; one stored before the check existed counts."""
    borg2 = _repo(test_db, 2, custom_flags="--noatime")

    # a blank plan value is stored as none, so it falls back the same way
    for blank in (None, "", "  "):
        _assert_refused(
            test_client.post(
                "/api/backup-plans/",
                json=_plan([borg2.id], custom_flags=blank),
                headers=admin_headers,
            ),
            "--noatime",
        )


@pytest.mark.unit
def test_plan_check_flags_count_only_when_the_plan_runs_a_check(
    test_client: TestClient, admin_headers, test_db
):
    """The check flags input is hidden while checks are off, and its value
    reaches no check; a stored Borg 1 option must not block the save."""
    borg2 = _repo(test_db, 2)

    response = test_client.post(
        "/api/backup-plans/",
        json=_plan([borg2.id], check_extra_flags="--save-space", run_check_after=False),
        headers=admin_headers,
    )

    assert response.status_code in (200, 201), response.text


@pytest.mark.unit
def test_a_disabled_link_is_checked_when_it_is_resumed(
    test_client: TestClient, admin_headers, test_db
):
    """Like the other link checks: a disabled link is not run, so its flags
    are checked when it is resumed, not when the plan is saved."""
    borg1 = _repo(test_db, 1)
    borg2 = _repo(test_db, 2)
    payload = _plan([borg1.id, borg2.id], custom_flags="--noatime")
    payload["repositories"][1]["enabled"] = False

    saved = test_client.post("/api/backup-plans/", json=payload, headers=admin_headers)
    assert saved.status_code in (200, 201), saved.text

    _assert_refused(
        test_client.post(
            f"/api/backup-plans/{saved.json()['id']}/repositories/{borg2.id}/toggle",
            headers=admin_headers,
        ),
        "--noatime",
    )


@pytest.mark.unit
def test_repository_update_checks_flags_against_the_stored_major(
    test_client: TestClient, admin_headers, test_db
):
    borg2 = _repo(test_db, 2)

    response = test_client.put(
        f"/api/repositories/{borg2.id}",
        json={"custom_flags": "--checkpoint-interval 600"},
        headers=admin_headers,
    )

    _assert_refused(response, "--checkpoint-interval")
    test_db.refresh(borg2)
    assert borg2.custom_flags is None


@pytest.mark.unit
def test_repository_update_refuses_flags_before_it_touches_a_new_path(
    test_client: TestClient, admin_headers, test_db
):
    """A new path is initialized during the update; a refused flag must
    leave nothing behind."""
    borg2 = _repo(test_db, 2)

    with patch(
        "app.api.repositories.BorgRouter.initialize_repository", new=AsyncMock()
    ) as initialize:
        response = test_client.put(
            f"/api/repositories/{borg2.id}",
            json={"path": "/repos/new-borg2", "custom_flags": "--noatime"},
            headers=admin_headers,
        )

    _assert_refused(response, "--noatime")
    initialize.assert_not_awaited()
    test_db.refresh(borg2)
    assert borg2.path == "/repos/borg2"


@pytest.mark.unit
def test_check_schedule_and_manual_check_follow_the_repository_major(
    test_client: TestClient, admin_headers, test_db
):
    borg1 = _repo(test_db, 1)
    borg2 = _repo(test_db, 2)

    _assert_refused(
        test_client.put(
            f"/api/repositories/{borg2.id}/check-schedule",
            json={
                "cron_expression": "0 3 * * *",
                "max_duration": 0,
                "check_extra_flags": "--glob-archives 'web-*'",
            },
            headers=admin_headers,
        ),
        "--glob-archives",
    )
    _assert_refused(
        test_client.post(
            f"/api/repositories/{borg1.id}/check",
            json={"max_duration": 0, "check_extra_flags": "--find-lost-archives"},
            headers=admin_headers,
        ),
        "--find-lost-archives",
    )
