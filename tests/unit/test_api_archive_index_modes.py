"""Manual index work under a per-repository index mode (spec section 6.8):
never blocked by the mode, never repeating, and never re-enabling history
behind a mode that excludes it."""

from app.database.models import (
    Archive,
    ArchiveChange,
    LicensingState,
    Operation,
    Repository,
    SystemSettings,
    utc_now,
)


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


def _archive(test_db, repo, name="a1"):
    archive = Archive(
        repository_id=repo.id,
        borg_id=f"id-{name}",
        name=name,
        start=utc_now().replace(tzinfo=None),
        series="nas",
        history_state="indexed",
    )
    test_db.add(archive)
    test_db.commit()
    test_db.refresh(archive)
    return archive


def _pro(test_db):
    state = test_db.query(LicensingState).first()
    if state is None:
        test_db.add(
            LicensingState(instance_id="t-index-mode", plan="pro", status="active")
        )
    else:
        state.plan = "pro"
        state.status = "active"
    test_db.commit()


def _kinds(test_db, body):
    return [test_db.get(Operation, i).kind for i in body["operations"]]


def test_rebuild_from_history_drops_the_history_stage_in_archives_mode(
    test_client, test_db, admin_headers
):
    _pro(test_db)
    repo = _repo(test_db, index_mode="archives")
    response = test_client.post(
        f"/api/repositories/{repo.id}/rebuild",
        json={"from": "history"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["index_mode"] == "archives"
    assert body["repeats"] is False
    kinds = _kinds(test_db, body)
    assert "history_index" not in kinds
    assert kinds == ["stats"]


def test_rebuild_from_history_still_clears_the_change_rows(
    test_client, test_db, admin_headers
):
    # Spec 6.8: clearing history is an explicit action and stays available
    # in every mode. The rows go; only the re-indexing stage is dropped.
    _pro(test_db)
    repo = _repo(test_db, index_mode="archives")
    archive = _archive(test_db, repo)
    test_db.add(ArchiveChange(archive_id=archive.id, path="x", change="added"))
    test_db.commit()

    response = test_client.post(
        f"/api/repositories/{repo.id}/rebuild",
        json={"from": "history"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    test_db.refresh(archive)
    assert archive.history_state == "pending"
    assert test_db.query(ArchiveChange).count() == 0


def test_rebuild_still_runs_for_an_off_repository(test_client, test_db, admin_headers):
    repo = _repo(test_db, index_mode="off")
    response = test_client.post(
        f"/api/repositories/{repo.id}/rebuild",
        json={"from": "stats"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert _kinds(test_db, body) == ["stats"]
    assert body["repeats"] is False


def test_rebuild_on_a_full_repository_repeats(test_client, test_db, admin_headers):
    repo = _repo(test_db)
    response = test_client.post(
        f"/api/repositories/{repo.id}/rebuild",
        json={"from": "stats"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["repeats"] is True
    assert response.json()["index_mode"] == "full"


def test_resync_lists_an_off_repository_once(test_client, test_db, admin_headers):
    repo = _repo(test_db, index_mode="off")
    response = test_client.post(
        f"/api/repositories/{repo.id}/resync", headers=admin_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert _kinds(test_db, body) == ["archive_sync", "stats"]
    assert body["index_mode"] == "off"
    assert body["repeats"] is False


def test_a_stats_rebuild_repeats_in_archives_mode(test_client, test_db, admin_headers):
    """`archives` keeps refreshing the listing and the size, so a stage the
    mode still runs is not a one-off look (spec 6.8)."""
    repo = _repo(test_db, index_mode="archives")
    response = test_client.post(
        f"/api/repositories/{repo.id}/rebuild",
        json={"from": "stats"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["index_mode"] == "archives"
    assert body["repeats"] is True


def test_resync_does_not_claim_to_repeat_in_archives_mode(
    test_client, test_db, admin_headers
):
    """Resync asks for the whole reconcile chain, and `archives` drops its
    history stages, so the flag warns rather than over-promising."""
    repo = _repo(test_db, index_mode="archives")
    response = test_client.post(
        f"/api/repositories/{repo.id}/resync", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["repeats"] is False
