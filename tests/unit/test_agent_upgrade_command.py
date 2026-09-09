"""The agent's side of a remote upgrade: create one empty file.

The trigger is a systemd .path unit, so the agent needs no sudo and passes no
arguments. It re-checks readiness rather than trusting the capability it last
reported, because the endpoint may have been changed since.
"""

import json
import queue
import time
from pathlib import Path

import pytest

from agent.borg_ui_agent.config import AgentConfig
from agent.borg_ui_agent.self_upgrade import UpgradeReadiness
from agent.borg_ui_agent.session import UPGRADE_CLAIM_SECONDS, AgentSessionRuntime


class _HttpClient:
    """Terminal frames for a command with no job_id go over the socket, so
    agent.upgrade never reaches this. A persisted job does, which is how the
    refusal of a job dispatched mid-upgrade is observed."""

    def __init__(self):
        self.failed = []

    def complete_job(self, job_id, *, result):
        return {"id": job_id, "status": "completed"}

    def fail_job(self, job_id, *, error_message, return_code=None):
        self.failed.append((job_id, error_message))
        return {"id": job_id, "status": "failed"}

    def cancel_job(self, job_id):
        return {"id": job_id, "status": "canceled"}


def _drain(outbox):
    frames = []
    while not outbox.empty():
        frames.append(json.loads(outbox.get_nowait()))
    return frames


@pytest.fixture
def http_client():
    return _HttpClient()


@pytest.fixture
def runtime(http_client):
    return AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: None,
        http_client=http_client,
    )


def _run(runtime, monkeypatch, readiness, running_ids=()):
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.check_self_upgrade", lambda: readiness
    )
    for job_id in running_ids:
        runtime._register_cancel(job_id)
    outbox: "queue.Queue[str]" = queue.Queue()
    runtime._handle_command(
        outbox, {"command_id": "c1", "command": "agent.upgrade", "payload": {}}
    )
    return _drain(outbox)


def test_upgrade_creates_the_trigger_file(runtime, tmp_path: Path, monkeypatch):
    trigger = tmp_path / "upgrade-requested"

    frames = _run(
        runtime, monkeypatch, UpgradeReadiness(supported=True, trigger=trigger)
    )

    assert trigger.is_file()
    results = [f for f in frames if f["type"] == "command_result"]
    assert results[0]["result"] == {"success": True, "trigger": str(trigger)}


def test_upgrade_refuses_while_a_job_is_running(runtime, tmp_path: Path, monkeypatch):
    trigger = tmp_path / "upgrade-requested"

    frames = _run(
        runtime,
        monkeypatch,
        UpgradeReadiness(supported=True, trigger=trigger),
        running_ids=(7,),
    )

    assert not trigger.exists()
    errors = [f for f in frames if f["type"] == "command_error"]
    assert errors[0]["error"]["code"] == "upgrade_busy"


@pytest.mark.parametrize(
    "reason",
    ["unit_missing", "helper_missing", "conf_missing", "path_unit_missing"],
)
def test_upgrade_refuses_when_unsupported(runtime, monkeypatch, reason):
    frames = _run(
        runtime, monkeypatch, UpgradeReadiness(supported=False, reason=reason)
    )

    errors = [f for f in frames if f["type"] == "command_error"]
    assert errors[0]["error"]["code"] == "upgrade_unsupported"
    assert reason in errors[0]["error"]["message"]


def test_upgrade_reports_an_unwritable_trigger_rather_than_dying(
    runtime, tmp_path: Path, monkeypatch
):
    trigger = tmp_path / "missing-dir" / "upgrade-requested"

    frames = _run(
        runtime, monkeypatch, UpgradeReadiness(supported=True, trigger=trigger)
    )

    errors = [f for f in frames if f["type"] == "command_error"]
    assert errors[0]["error"]["code"] == "upgrade_failed"


def test_upgrade_is_not_registered_as_a_job_command():
    """It carries no job_id, so registering it would leave a phantom in hello."""
    assert (
        AgentSessionRuntime._job_id_for_dispatch(
            {"command": "agent.upgrade", "job_id": 5}
        )
        is None
    )


def test_a_job_dispatched_after_the_claim_is_refused(
    runtime, http_client, tmp_path, monkeypatch
):
    """The busy check is a claim, not a sample. A job arriving between it and
    the restart would be orphaned by the restart, so it is refused instead."""
    trigger = tmp_path / "upgrade-requested"
    frames = _run(
        runtime, monkeypatch, UpgradeReadiness(supported=True, trigger=trigger)
    )
    assert [f for f in frames if f["type"] == "command_result"]

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.get_job_handler",
        lambda command: lambda job, client, should_cancel=None: None,
    )
    outbox: "queue.Queue[str]" = queue.Queue()
    runtime._handle_command(
        outbox,
        {
            "command_id": "c2",
            "command": "backup.create",
            "job_id": 42,
            "payload": {},
        },
    )

    # A persisted job reports its outcome over the job API, not the socket.
    assert [f for f in _drain(outbox) if f["type"] == "command_error"] == []
    assert http_client.failed == [(42, "Agent is upgrading and cannot start new jobs")]


def test_a_failed_upgrade_releases_the_claim(runtime, monkeypatch):
    """A claim held after an upgrade that never started would lock the endpoint
    out of running jobs until it was restarted by hand."""
    _run(
        runtime,
        monkeypatch,
        UpgradeReadiness(supported=False, reason="unit_missing"),
    )

    assert runtime._reserve_for_upgrade() == []


def test_a_second_upgrade_request_is_refused_while_one_is_claimed(
    runtime, tmp_path, monkeypatch
):
    trigger = tmp_path / "upgrade-requested"
    _run(runtime, monkeypatch, UpgradeReadiness(supported=True, trigger=trigger))

    frames = _run(
        runtime, monkeypatch, UpgradeReadiness(supported=True, trigger=trigger)
    )

    errors = [f for f in frames if f["type"] == "command_error"]
    assert errors[0]["error"]["code"] == "upgrade_busy"


def test_a_refused_job_is_not_left_in_the_cancel_registry(
    runtime, http_client, tmp_path, monkeypatch
):
    """The session loop registers the id before the worker starts, and the
    refusal returns before the unregister in the handler's finally. Leaking it
    would make hello report a job that is not running, permanently."""
    trigger = tmp_path / "upgrade-requested"
    _run(runtime, monkeypatch, UpgradeReadiness(supported=True, trigger=trigger))
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.get_job_handler",
        lambda command: lambda job, client, should_cancel=None: None,
    )
    cancel_event = runtime._register_cancel(42)

    runtime._handle_command(
        queue.Queue(),
        {"command_id": "c2", "command": "backup.create", "job_id": 42, "payload": {}},
        cancel_event=cancel_event,
    )

    assert runtime._running_job_ids() == []


def test_the_claim_expires_so_an_aborted_helper_cannot_wedge_the_agent(
    runtime, tmp_path, monkeypatch
):
    """The helper aborts on a bad checksum or a non-https server with this
    process still running. A claim without an expiry would leave the endpoint
    refusing every job until someone restarted it by hand."""
    trigger = tmp_path / "upgrade-requested"
    _run(runtime, monkeypatch, UpgradeReadiness(supported=True, trigger=trigger))
    assert runtime._upgrade_claimed()

    # Captured first: patching time.monotonic with a lambda that calls it
    # would recurse, since session.py holds the module, not the function.
    expired_at = time.monotonic() + UPGRADE_CLAIM_SECONDS + 1
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.time.monotonic", lambda: expired_at
    )

    assert not runtime._upgrade_claimed()
