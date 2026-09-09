"""The agent's side of a remote upgrade: create one empty file.

The trigger is a systemd .path unit, so the agent needs no sudo and passes no
arguments. It re-checks readiness rather than trusting the capability it last
reported, because the endpoint may have been changed since.
"""

import json
import queue
from pathlib import Path

import pytest

from agent.borg_ui_agent.config import AgentConfig
from agent.borg_ui_agent.self_upgrade import UpgradeReadiness
from agent.borg_ui_agent.session import AgentSessionRuntime


class _HttpClient:
    """Terminal frames for a command with no job_id go over the socket, so this
    only exists to satisfy the constructor."""

    def complete_job(self, job_id, *, result):
        return {"id": job_id, "status": "completed"}

    def fail_job(self, job_id, *, error_message, return_code=None):
        return {"id": job_id, "status": "failed"}

    def cancel_job(self, job_id):
        return {"id": job_id, "status": "canceled"}


def _drain(outbox):
    frames = []
    while not outbox.empty():
        frames.append(json.loads(outbox.get_nowait()))
    return frames


@pytest.fixture
def runtime():
    return AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: None,
        http_client=_HttpClient(),
    )


def _run(runtime, monkeypatch, readiness, running_ids=()):
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.check_self_upgrade", lambda: readiness
    )
    monkeypatch.setattr(
        AgentSessionRuntime, "_running_job_ids", lambda self: list(running_ids)
    )
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
