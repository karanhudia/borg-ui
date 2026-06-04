from pathlib import Path


def test_test_db_uses_per_test_sqlite_file(test_db, tmp_path):
    db_path = Path(test_db.get_bind().url.database)

    assert db_path == tmp_path / "test.db"
