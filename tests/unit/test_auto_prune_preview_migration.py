"""Tests for revision d4e5f6a7b8c9 (system_settings.auto_prune_preview)."""

import pytest
from sqlalchemy import inspect, text

from tests.unit.test_paused_stages_migration import _migrate, _seed

REVISION = "d4e5f6a7b8c9"
PREVIOUS = "c3d4e5f6a7b8"


@pytest.mark.unit
def test_existing_install_keeps_automatic_previews_on(tmp_path):
    from app.database.db_upgrade import _engine

    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    _seed(url, "paused_stages", "'[]'")
    _migrate(url, REVISION)
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            value = connection.execute(
                text("SELECT auto_prune_preview FROM system_settings")
            ).scalar_one()
        assert value == 1

        _migrate(url, PREVIOUS, down=True)
        columns = {c["name"] for c in inspect(engine).get_columns("system_settings")}
        assert "auto_prune_preview" not in columns
    finally:
        engine.dispose()
