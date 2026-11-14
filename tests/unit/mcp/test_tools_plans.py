"""Backup plan and schedule tools (plan Task 11)."""

import pytest


@pytest.mark.unit
def test_empty_states(admin_mcp):
    assert admin_mcp.call("list_backup_plans")["text"] == "No backup plans yet."
    assert admin_mcp.call("list_schedules")["text"] == "No schedules yet."


@pytest.mark.unit
def test_list_and_get_backup_plan(admin_mcp, secrets_seeded):
    listed = admin_mcp.call("list_backup_plans")
    assert listed["text"].splitlines()[0] == "1 backup plan:"
    assert (
        "*Nightly photos*: /local/photos to 0 repositories, `0 2 * * *` (UTC)"
        in listed["text"]
    )
    plan = admin_mcp.call("get_backup_plan", plan="nightly")
    assert plan["text"].startswith("*Nightly photos*")
    assert "Backs up: /local/photos" in plan["text"]
    assert "Keeps: 7d 4w 6m 1y" in plan["text"]
    runs = admin_mcp.call("list_plan_runs", plan="Nightly photos")
    assert runs["text"] == "*Nightly photos* has not run yet."


@pytest.mark.unit
def test_list_and_get_schedule(admin_mcp, secrets_seeded):
    listed = admin_mcp.call("list_schedules")
    assert "*Nightly*" in listed["text"] and "`0 3 * * *` (UTC)" in listed["text"]
    one = admin_mcp.call("get_schedule", schedule="Nightly")
    assert one["text"].startswith("*Nightly*")
    assert "When: `0 3 * * *` (UTC)" in one["text"]


@pytest.mark.unit
def test_check_cron(admin_mcp):
    ok = admin_mcp.call("check_cron", expression="0 2 * * *", timezone="Europe/Berlin")
    assert ok["text"].startswith("✓ `0 2 * * *` is valid (Europe/Berlin). Next runs:")
    assert len(ok["data"]["next_runs"]) == 5
    short = admin_mcp.call("check_cron", expression="every night")
    assert short["is_error"] and "five fields" in short["text"]
    bad = admin_mcp.call("check_cron", expression="99 2 * * *")
    assert bad["is_error"] and bad["text"].startswith("`99 2 * * *` does not work:")
