import json
from unittest.mock import AsyncMock

import pytest

from app.core.borg import BorgInterface


@pytest.mark.unit
@pytest.mark.asyncio
async def test_break_lock_cleans_cache_locks_from_borg_cache_dir(
    monkeypatch, tmp_path
) -> None:
    cache_root = tmp_path / "active-borg-cache"
    repo_id = "repo123"
    cache_dir = cache_root / repo_id
    cache_dir.mkdir(parents=True)
    lock_file = cache_dir / "lock.exclusive"
    lock_file.write_text("stale", encoding="utf-8")
    monkeypatch.setenv("BORG_CACHE_DIR", str(cache_root))
    monkeypatch.setenv("HOME", str(tmp_path / "root-home"))

    borg = BorgInterface()
    borg._execute_command = AsyncMock(
        side_effect=[
            {"success": True, "stdout": "", "stderr": ""},
            {
                "success": True,
                "stdout": json.dumps({"repository": {"id": repo_id}}),
                "stderr": "",
            },
        ]
    )

    await borg.break_lock("/repo")

    assert not lock_file.exists()


@pytest.mark.unit
def test_borg_cache_root_falls_back_to_borg_base_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("BORG_CACHE_DIR", raising=False)
    cache_root = tmp_path / "borg-base" / ".cache" / "borg"

    assert BorgInterface._get_borg_cache_root(
        {"BORG_BASE_DIR": str(tmp_path / "borg-base")}
    ) == str(cache_root)


@pytest.mark.unit
def test_borg_cache_root_falls_back_to_xdg_cache_home(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("BORG_CACHE_DIR", raising=False)
    monkeypatch.delenv("BORG_BASE_DIR", raising=False)
    cache_root = tmp_path / "xdg-cache" / "borg"

    assert BorgInterface._get_borg_cache_root(
        {"XDG_CACHE_HOME": str(tmp_path / "xdg-cache")}
    ) == str(cache_root)
