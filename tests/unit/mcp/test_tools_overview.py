"""Overview and health tools (plan Task 8)."""

import pytest


@pytest.mark.unit
def test_get_overview(admin_mcp, seeded):
    result = admin_mcp.call("get_overview")
    assert not result["is_error"]
    lines = result["text"].splitlines()
    assert lines[0] == "⚠ 1 of 2 repositories needs a look."
    assert any(
        line.startswith("✓ *Photos*: backed up 3 hours ago, 412.6 GB, 2 archives")
        for line in lines
    )
    assert (
        "✗ *Laptop*: backed up 9 days ago, 18.1 GB, 0 archives (No backup in 9 days)"
        in lines
    )
    assert "1 job failed in the last 30 days." in result["text"]
    assert result["text"].rstrip().endswith("Want me to look into *Laptop*?")
    names = [r["name"] for r in result["data"]["repositories"]]
    assert names == ["Laptop", "Photos"]  # worst first
    assert result["data"]["summary"]["total_repositories"] == 2
    assert "hunter2" not in str(result)


@pytest.mark.unit
def test_get_overview_empty(admin_mcp):
    result = admin_mcp.call("get_overview")
    assert result["text"] == (
        "No repositories yet. Want to set one up? That needs Manage access."
    )


@pytest.mark.unit
def test_list_problems(admin_mcp, seeded):
    result = admin_mcp.call("list_problems")
    text = result["text"]
    assert text.splitlines()[0] == "⚠ 2 things need attention."
    assert "✗ *Laptop*: No backup in 9 days" in text
    assert (
        "✗ Backup of *Laptop* failed 1 hour ago: Failed to create/acquire the lock"
        in text
    )
    kinds = sorted(p["kind"] for p in result["data"]["problems"])
    assert kinds == ["failed_job", "repository"]


@pytest.mark.unit
def test_list_problems_none(admin_mcp, test_db, seeded):
    from datetime import datetime

    seeded["laptop"].last_backup = datetime.utcnow()
    test_db.delete(seeded["failed"])
    test_db.commit()
    result = admin_mcp.call("list_problems")
    assert (
        result["text"]
        == "✓ Nothing needs attention. 2 repositories, all backed up recently."
    )


@pytest.mark.unit
def test_get_upcoming_runs_empty(admin_mcp):
    assert admin_mcp.call("get_upcoming_runs")["text"] == (
        "Nothing is scheduled in the next 24 hours."
    )


@pytest.mark.unit
def test_get_system_info_hides_licence_ids(admin_mcp):
    result = admin_mcp.call("get_system_info")
    assert result["text"].startswith("Borg UI 2.")
    assert "Borg 1" in result["text"] or "borg 1" in result["text"]
    dumped = str(result)
    for secret in (
        "instance_id",
        "license_id",
        "customer_id",
        "key_id",
        "entitlement_id",
    ):
        assert secret not in dumped
