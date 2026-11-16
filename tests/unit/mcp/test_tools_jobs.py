"""Jobs and activity tools (plan Task 10)."""

import pytest


@pytest.fixture
def logged(seeded, test_db, tmp_path):
    log = tmp_path / "backup.log"
    log.write_text("\n".join(f"line {i}" for i in range(1, 1501)) + "\n")
    seeded["failed"].log_file_path = str(log)
    test_db.commit()
    return seeded


@pytest.mark.unit
def test_list_activity(admin_mcp, seeded):
    result = admin_mcp.call("list_activity")
    first = result["text"].splitlines()[0]
    assert first.startswith("✗ Backup of *Laptop* failed, 1 hour ago (backup ")
    assert first.endswith(": Failed to create/acquire the lock")
    assert result["data"]["jobs"][0]["type"] == "backup"


@pytest.mark.unit
def test_list_activity_filters(admin_mcp, seeded):
    assert (
        admin_mcp.call("list_activity", repository="Photos")["text"]
        == "No matching activity."
    )
    assert (
        admin_mcp.call("list_activity", since="30m")["text"] == "No matching activity."
    )
    bad = admin_mcp.call("list_activity", since="last tuesday")
    assert bad["is_error"] and "24h, 7d or 2026-11-01" in bad["text"]


@pytest.mark.unit
def test_list_running_jobs_idle(admin_mcp, seeded):
    assert (
        admin_mcp.call("list_running_jobs")["text"] == "Nothing is running right now."
    )


@pytest.mark.unit
def test_get_job(admin_mcp, seeded):
    job_id = seeded["failed"].id
    result = admin_mcp.call("get_job", job_type="backup", job_id=job_id)
    assert result["text"].startswith("✗ Backup of *Laptop*: failed")
    assert "took 2 min" in result["text"]
    assert "Error: Failed to create/acquire the lock" in result["text"]
    wrong = admin_mcp.call("get_job", job_type="check", job_id=job_id)
    assert wrong["is_error"] and f"Ask for backup {job_id}." in wrong["text"]
    missing = admin_mcp.call("get_job", job_type="backup", job_id=99999)
    assert missing["is_error"] and "could not find backup 99999" in missing["text"]


@pytest.mark.unit
def test_get_job_log_tail_and_paging(admin_mcp, logged):
    job_id = logged["failed"].id
    result = admin_mcp.call("get_job_log", job_type="backup", job_id=job_id)
    assert result["text"].startswith(
        f"Lines 1301 to 1500 of 1500 from backup {job_id}:"
    )
    assert "line 1500" in result["text"] and "line 1300\n" not in result["text"]
    assert "There are 1300 earlier lines." in result["text"]
    earlier = admin_mcp.call(
        "get_job_log",
        job_type="backup",
        job_id=job_id,
        cursor=result["data"]["next_cursor"],
    )
    assert earlier["text"].startswith(f"Lines 1101 to 1300 of 1500")
    big = admin_mcp.call("get_job_log", job_type="backup", job_id=job_id, lines=5000)
    assert big["data"]["first_line"] == 501  # capped at 1000 lines


@pytest.mark.unit
def test_wait_for_a_finished_job_returns_at_once(admin_mcp, seeded):
    import time

    started = time.monotonic()
    result = admin_mcp.call(
        "wait_for_job", job_type="backup", job_id=seeded["failed"].id
    )
    assert time.monotonic() - started < 5
    assert result["data"]["finished"] is True


@pytest.mark.unit
def test_explain_failure_picks_the_latest(admin_mcp, logged):
    result = admin_mcp.call("explain_failure")
    text = result["text"]
    assert text.startswith("✗ Backup of *Laptop* failed 1 hour ago after 2 min.")
    for heading in (
        "**What failed**",
        "**Error**",
        "**Last log lines**",
        "**Similar recent failures**",
    ):
        assert heading in text
    assert "line 1500" in text and "line 1460" not in text
    assert len(result["data"]["log_tail"]) == 40
    assert "None on this repository recently." in text


@pytest.mark.unit
def test_explain_failure_nothing_failed(admin_mcp):
    assert admin_mcp.call("explain_failure")["text"] == "✓ Nothing has failed recently."


@pytest.mark.unit
def test_log_cursor_survives_a_growing_log(admin_mcp, logged):
    job_id = logged["failed"].id
    first = admin_mcp.call("get_job_log", job_type="backup", job_id=job_id)
    with open(logged["failed"].log_file_path, "a") as log:
        log.write("\n".join(f"late {i}" for i in range(200)) + "\n")
    earlier = admin_mcp.call(
        "get_job_log",
        job_type="backup",
        job_id=job_id,
        cursor=first["data"]["next_cursor"],
    )
    assert earlier["text"].startswith("Lines 1101 to 1300 of 1700")
