"""Per-repository index mode on the repository routes (spec section 6.8)."""

from app.database.models import Repository, SystemSettings


def _repo(test_db, name="r", **kw):
    repo = Repository(
        name=name, path=f"/tmp/{name}", encryption="none", compression="lz4", **kw
    )
    test_db.add(repo)
    if test_db.query(SystemSettings).first() is None:
        test_db.add(SystemSettings())
    test_db.commit()
    test_db.refresh(repo)
    return repo


def test_a_new_repository_reads_as_full(test_client, admin_headers, test_db):
    repo = _repo(test_db)
    response = test_client.get("/api/repositories/", headers=admin_headers)
    assert response.status_code == 200
    row = next(r for r in response.json()["repositories"] if r["id"] == repo.id)
    assert row["index_mode"] == "full"


def test_the_detail_payload_carries_the_mode(test_client, admin_headers, test_db):
    repo = _repo(test_db)
    response = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["repository"]["index_mode"] == "full"


def test_the_mode_can_be_set(test_client, admin_headers, test_db):
    repo = _repo(test_db)
    response = test_client.put(
        f"/api/repositories/{repo.id}",
        json={"index_mode": "archives"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    test_db.refresh(repo)
    assert repo.index_mode == "archives"


def test_an_unknown_mode_is_refused(test_client, admin_headers, test_db):
    repo = _repo(test_db)
    response = test_client.put(
        f"/api/repositories/{repo.id}",
        json={"index_mode": "sometimes"},
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_leaving_full_cancels_queued_index_work(test_client, admin_headers, test_db):
    from tests.utils.operations import seed_operation

    repo = _repo(test_db)
    queued = seed_operation(test_db, "history_index", repository=repo, status="queued")
    other = seed_operation(test_db, "backup", repository=repo, status="queued")
    response = test_client.put(
        f"/api/repositories/{repo.id}",
        json={"index_mode": "archives"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    test_db.refresh(queued)
    test_db.refresh(other)
    assert queued.status == "cancelled"
    # A backup someone asked for is not index work and is left alone.
    assert other.status == "queued"


def test_archives_mode_keeps_a_queued_listing(test_client, admin_headers, test_db):
    from tests.utils.operations import seed_operation

    repo = _repo(test_db)
    queued = seed_operation(test_db, "archive_sync", repository=repo, status="queued")
    test_client.put(
        f"/api/repositories/{repo.id}",
        json={"index_mode": "archives"},
        headers=admin_headers,
    )
    test_db.refresh(queued)
    assert queued.status == "queued"


def test_a_running_index_is_left_to_finish(test_client, admin_headers, test_db):
    from tests.utils.operations import seed_operation

    repo = _repo(test_db)
    running = seed_operation(
        test_db, "history_index", repository=repo, status="running"
    )
    test_client.put(
        f"/api/repositories/{repo.id}",
        json={"index_mode": "off"},
        headers=admin_headers,
    )
    test_db.refresh(running)
    assert running.status == "running"


def test_returning_to_full_enqueues_one_catch_up_run(
    test_client, admin_headers, test_db
):
    from app.database.models import Operation

    repo = _repo(test_db, index_mode="off")
    response = test_client.put(
        f"/api/repositories/{repo.id}",
        json={"index_mode": "full"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    kinds = [
        op.kind
        for op in test_db.query(Operation)
        .filter(Operation.repository_id == repo.id)
        .all()
    ]
    assert "archive_sync" in kinds


def test_setting_the_same_mode_again_does_nothing(test_client, admin_headers, test_db):
    from app.database.models import Operation

    repo = _repo(test_db)
    response = test_client.put(
        f"/api/repositories/{repo.id}",
        json={"index_mode": "full"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert (
        test_db.query(Operation).filter(Operation.repository_id == repo.id).count() == 0
    )
