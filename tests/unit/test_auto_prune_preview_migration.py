"""Tests for revision d4e5f6a7b8c9 (system_settings.auto_prune_preview)."""

import pytest
import sqlalchemy as sa

from tests.unit.test_paused_stages_migration import (  # noqa: F401 (url is a fixture)
    _columns,
    _migrate,
    _read,
    _seed,
    url,
)

REVISION = "d4e5f6a7b8c9"
PREVIOUS = "c3d4e5f6a7b8"


@pytest.mark.unit
def test_existing_install_keeps_automatic_previews_on(url):  # noqa: F811
    _migrate(url, PREVIOUS)
    _seed(url, "paused_stages", [])
    _migrate(url, REVISION)
    assert _read(url, "auto_prune_preview", sa.Boolean) is True

    _migrate(url, PREVIOUS, down=True)
    assert "auto_prune_preview" not in {c["name"] for c in _columns(url)}
