"""Every source post-backup script of a plan runs (#1428).

A failing source post-backup script does not stop the ones after it: each
undoes what its own source's pre-backup script did. The failures are
reported together. A failing source pre-backup script still stops the ones
after it, since the backup does not start.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.backup_plan_execution_service import backup_plan_execution_service


def _database(script_prefix: str, script_id: int, order: int) -> dict:
    return {
        "source_type": "local",
        "paths": [f"/dumps/{script_id}"],
        "database": {
            f"{script_prefix}_backup_script_id": script_id,
            "script_execution_order": order,
        },
    }


def _context(prefix: str) -> SimpleNamespace:
    # two databases, each with its own script
    return SimpleNamespace(
        source_locations=[_database(prefix, 11, 1), _database(prefix, 12, 2)],
        script_hooks=[],
    )


def _plan_scripts(fail=(), raise_for=()):
    ran: list[int] = []

    async def execute(run_id, context, **kwargs):
        script_id = kwargs["script_id"]
        ran.append(script_id)
        if script_id in raise_for:
            raise RuntimeError(f"script {script_id} raised")
        if script_id in fail:
            return False, f"script {script_id} failed"
        return True, None

    return ran, patch.object(
        backup_plan_execution_service, "_execute_plan_script", side_effect=execute
    )


@pytest.mark.asyncio
async def test_a_failing_source_post_script_does_not_stop_the_next():
    ran, scripts = _plan_scripts(fail={11})

    with scripts:
        ok, error = await backup_plan_execution_service._execute_source_scripts(
            1, _context("post"), hook_type="source-post-backup", backup_result="success"
        )

    assert ran == [11, 12]
    assert ok is False
    assert error == "script 11 failed"


@pytest.mark.asyncio
async def test_failing_source_post_scripts_are_reported_together():
    ran, scripts = _plan_scripts(fail={11, 12})

    with scripts:
        ok, error = await backup_plan_execution_service._execute_source_scripts(
            1, _context("post"), hook_type="source-post-backup", backup_result="failure"
        )

    assert ran == [11, 12]
    assert ok is False
    assert error == "script 11 failed; script 12 failed"


@pytest.mark.asyncio
async def test_a_raising_source_post_script_does_not_stop_the_next():
    ran, scripts = _plan_scripts(raise_for={11})

    with scripts:
        ok, error = await backup_plan_execution_service._execute_source_scripts(
            1, _context("post"), hook_type="source-post-backup", backup_result="failure"
        )

    assert ran == [11, 12]
    assert ok is False
    assert "script 11 raised" in error


@pytest.mark.asyncio
async def test_a_failing_source_pre_script_still_stops_the_next():
    ran, scripts = _plan_scripts(fail={11})

    with scripts:
        ok, error = await backup_plan_execution_service._execute_source_scripts(
            1, _context("pre"), hook_type="source-pre-backup"
        )

    assert ran == [11]
    assert (ok, error) == (False, "script 11 failed")


@pytest.mark.asyncio
async def test_a_raising_source_pre_script_still_raises():
    ran, scripts = _plan_scripts(raise_for={11})

    with scripts, pytest.raises(RuntimeError, match="script 11 raised"):
        await backup_plan_execution_service._execute_source_scripts(
            1, _context("pre"), hook_type="source-pre-backup"
        )

    assert ran == [11]


@pytest.mark.asyncio
async def test_the_run_reports_every_failed_source_post_script():
    ran, scripts = _plan_scripts(fail={11, 12})

    with scripts:
        warnings = await backup_plan_execution_service._run_post_backup_scripts(
            1, _context("post"), "success"
        )

    assert ran == [11, 12]
    assert warnings == ["script 11 failed; script 12 failed"]
