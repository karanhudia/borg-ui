"""The repository status route and the hub row under an index mode
(spec sections 6.8, 10.1, 10.2)."""

from app.database.models import (
    Repository,
    SystemSettings,
    utc_now,
)
from app.services.operations.repository_status import repository_status


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


def _cells(test_db, repo):
    now = utc_now().replace(tzinfo=None)
    payload = repository_status(test_db, repo, now=now, pro=True)
    return {cell["cell"] for cell in payload["cells"]}


def test_the_status_route_omits_the_index_cell_for_an_off_repository(test_db):
    repo = _repo(test_db, index_mode="off")
    assert "index" not in _cells(test_db, repo)


def test_archives_mode_keeps_the_index_cell(test_db):
    # The listing and the size still refresh, so the cell still means
    # something (spec 6.8).
    repo = _repo(test_db, index_mode="archives")
    assert "index" in _cells(test_db, repo)


def test_full_mode_keeps_the_index_cell(test_db):
    repo = _repo(test_db)
    assert "index" in _cells(test_db, repo)


def test_the_hub_row_carries_the_mode(test_client, test_db, admin_headers):
    repo = _repo(test_db, index_mode="archives")
    response = test_client.get("/api/operations/repositories", headers=admin_headers)
    assert response.status_code == 200
    row = next(
        r for r in response.json()["repositories"] if r["repository_id"] == repo.id
    )
    assert row["index_mode"] == "archives"
