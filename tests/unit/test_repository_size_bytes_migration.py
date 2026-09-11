"""Tests for revision a9b8c7d6e5f4 (repository size bytes and measured_at)."""

from alembic import command
import pytest
from sqlalchemy import inspect, text

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "a9b8c7d6e5f4"
PREVIOUS = "e1f2a3b4c5d6"
COLUMNS = {"total_size_bytes", "total_size_measured_at"}


def _migrate(url, target, *, down=False):
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if down else command.upgrade)(config, target)
        connection.commit()
    engine.dispose()


def _columns(url):
    engine = _engine(url)
    try:
        return {c["name"] for c in inspect(engine).get_columns("repositories")}
    finally:
        engine.dispose()


@pytest.mark.unit
def test_upgrade_adds_and_downgrade_drops_the_columns(tmp_path):
    """The DDL of both directions on an empty schema; the populated
    downgrade is covered below."""
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    assert not COLUMNS & _columns(url)
    _migrate(url, REVISION)
    assert COLUMNS <= _columns(url)
    _migrate(url, PREVIOUS, down=True)
    assert not COLUMNS & _columns(url)


@pytest.mark.unit
def test_revision_follows_the_index_mode_revision_and_the_graph_has_one_head():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config("sqlite://"))
    assert script.get_revision(REVISION).down_revision == PREVIOUS
    assert len(script.get_heads()) == 1


def _required_columns(engine) -> dict:
    """Placeholder values for every NOT NULL column of `repositories` that
    has no default, so a row can be inserted whatever the schema demands."""
    placeholders = {}
    for column in inspect(engine).get_columns("repositories"):
        if column["nullable"] or column.get("default") is not None:
            continue
        if column.get("autoincrement") is True or column["name"] == "id":
            continue
        kind = str(column["type"]).upper()
        if "INT" in kind or "BOOL" in kind:
            placeholders[column["name"]] = 0
        elif "DATE" in kind or "TIME" in kind:
            placeholders[column["name"]] = "2026-01-01 00:00:00"
        else:
            placeholders[column["name"]] = "x"
    return placeholders


@pytest.mark.unit
def test_upgrade_backfills_bytes_from_the_formatted_size(tmp_path):
    """A repository that showed a size keeps showing one in the new field:
    the string's two decimals are all the precision there is, and the time
    of that old measurement is unknown, so `measured_at` stays NULL."""
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    engine = _engine(url)
    required = _required_columns(engine)
    with engine.begin() as connection:
        for name, total_size in (
            ("tb", "2.40 TB"),
            ("kb", "490.23 KB"),
            ("zero", "0.00 B"),
            ("old-shape", "1.5GB"),
            ("bare", "4096"),
            ("unknown", "Unknown"),
            ("none", None),
        ):
            values = {
                **required,
                "name": name,
                "path": f"/repos/{name}",
                "total_size": total_size,
            }
            columns = ", ".join(values)
            marks = ", ".join(f":{column}" for column in values)
            connection.execute(
                text(f"INSERT INTO repositories ({columns}) VALUES ({marks})"), values
            )
    engine.dispose()

    _migrate(url, REVISION)

    engine = _engine(url)
    with engine.connect() as connection:
        rows = dict(
            connection.execute(
                text("SELECT name, total_size_bytes FROM repositories")
            ).fetchall()
        )
        measured = connection.execute(
            text(
                "SELECT count(*) FROM repositories WHERE total_size_measured_at IS NOT NULL"
            )
        ).scalar()
    engine.dispose()
    assert rows == {
        "tb": 2_638_827_906_662,
        "kb": 501_996,
        "zero": 0,
        "old-shape": 1_610_612_736,
        "bare": 4096,
        "unknown": None,
        "none": None,
    }
    assert measured == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    "text_value, expected",
    [
        ("2.40 TB", 2_638_827_906_662),
        ("1.00 KB", 1024),
        ("512.00 B", 512),
        ("3.5 gb", 3_758_096_384),
        ("Unknown", None),
        ("N/A", None),
        ("", None),
        (None, None),
        ("-1.00 KB", None),
        ("1.00 XB", None),
        ("1.5GB", 1_610_612_736),
        ("1 GiB", 1_073_741_824),
        ("4096", 4096),
        ("NaN KB", None),
        ("Infinity GB", None),
    ],
)
def test_bytes_from_formatted(text_value, expected):
    import importlib.util
    from pathlib import Path

    versions = Path(__file__).resolve().parents[2] / "app/database/alembic/versions"
    path = next(versions.glob("a9b8c7d6e5f4_*.py"))
    spec = importlib.util.spec_from_file_location("size_bytes_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.bytes_from_formatted(text_value) == expected


@pytest.mark.unit
def test_downgrade_keeps_the_rows_that_reference_repositories(tmp_path):
    """On SQLite the batch drop recreates `repositories` (copy, DROP TABLE,
    rename); with foreign keys enforced the drop would cascade into the
    archive index and the operation history. The downgrade switches the
    pragma off around the recreate, so a populated database survives it."""
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, REVISION)
    engine = _engine(url)
    required = _required_columns(engine)
    with engine.begin() as connection:
        values = {**required, "name": "r", "path": "/repos/r", "total_size": "1.00 KB"}
        columns = ", ".join(values)
        marks = ", ".join(f":{column}" for column in values)
        connection.execute(
            text(f"INSERT INTO repositories ({columns}) VALUES ({marks})"), values
        )
        repository_id = connection.execute(text("SELECT id FROM repositories")).scalar()
        connection.execute(
            text(
                "INSERT INTO archives (repository_id, borg_id, name, series, start, "
                "history_state, history_truncated, history_attempts, first_seen_at, "
                "last_seen_at) VALUES (:r, 'b1', 'a1', 's', '2026-01-01 00:00:00', "
                "'pending', 0, 0, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            ),
            {"r": repository_id},
        )
        connection.execute(
            text(
                "INSERT INTO operations (repository_id, kind, category, status, trigger, "
                "priority, run_id, created_at) VALUES (:r, 'stats', 'index', 'completed', "
                "'manual', 10, 'run-1', '2026-01-01 00:00:00')"
            ),
            {"r": repository_id},
        )
    engine.dispose()

    _migrate(url, PREVIOUS, down=True)

    engine = _engine(url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM archives")).scalar() == 1
        assert connection.execute(text("SELECT count(*) FROM operations")).scalar() == 1
    engine.dispose()
    assert not COLUMNS & _columns(url)
