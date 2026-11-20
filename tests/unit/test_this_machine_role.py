from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.database.models import BackupPlan, Repository

ROLE = "this_machine"


def _repo(db, name="This machine (local)", role=ROLE):
    repo = Repository(
        name=name,
        path=f"/backups/{name}",
        encryption="none",
        repository_type="local",
        mode="full",
        system_role=role,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


def _plan(db, name="This machine", role=ROLE):
    plan = BackupPlan(
        name=name,
        source_directories='["/etc"]',
        system_role=role,
        created_at=datetime.utcnow(),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@pytest.mark.unit
def test_plan_and_repository_serialize_system_role(test_client, admin_headers, test_db):
    plan = _plan(test_db)
    repo = _repo(test_db)

    plan_body = test_client.get(f"/api/backup-plans/{plan.id}", headers=admin_headers)
    assert plan_body.status_code == 200
    assert plan_body.json()["system_role"] == ROLE

    repo_body = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)
    assert repo_body.status_code == 200
    body = repo_body.json()
    assert (body.get("repository") or body)["system_role"] == ROLE


@pytest.mark.unit
def test_delete_system_plan_requires_confirmation(test_client, admin_headers, test_db):
    plan = _plan(test_db)

    refused = test_client.delete(f"/api/backup-plans/{plan.id}", headers=admin_headers)
    assert refused.status_code == 409
    assert refused.json()["detail"]["key"] == "backend.errors.thisMachine.confirmDelete"

    deleted = test_client.delete(
        f"/api/backup-plans/{plan.id}?confirm_system=true", headers=admin_headers
    )
    assert deleted.status_code == 200


@pytest.mark.unit
def test_delete_user_plan_needs_no_confirmation(test_client, admin_headers, test_db):
    plan = _plan(test_db, name="Mine", role=None)
    deleted = test_client.delete(f"/api/backup-plans/{plan.id}", headers=admin_headers)
    assert deleted.status_code == 200


@pytest.mark.unit
def test_delete_system_repository_requires_confirmation(
    test_client, admin_headers, test_db
):
    repo = _repo(test_db)

    refused = test_client.delete(f"/api/repositories/{repo.id}", headers=admin_headers)
    assert refused.status_code == 409
    assert refused.json()["detail"]["key"] == "backend.errors.thisMachine.confirmDelete"

    refused = test_client.post(
        f"/api/repositories/{repo.id}/permanent-delete",
        json={"understood": True, "confirmation_phrase": repo.name},
        headers=admin_headers,
    )
    assert refused.status_code == 409

    deleted = test_client.delete(
        f"/api/repositories/{repo.id}?confirm_system=true", headers=admin_headers
    )
    assert deleted.status_code == 200


@pytest.mark.unit
def test_second_this_machine_plan_rejected(test_db):
    _plan(test_db)
    with pytest.raises(IntegrityError):
        _plan(test_db, name="Another")
    test_db.rollback()


@pytest.mark.unit
def test_second_this_machine_repository_rejected(test_db):
    _repo(test_db)
    with pytest.raises(IntegrityError):
        _repo(test_db, name="Another")
    test_db.rollback()
