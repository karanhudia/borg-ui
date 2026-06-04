from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services import agent_job_dispatcher


@pytest.mark.unit
@pytest.mark.asyncio
async def test_best_effort_dispatch_rolls_back_and_filters_log_context(monkeypatch):
    async def raise_dispatch_error(*args, **kwargs):
        raise RuntimeError("dispatch failed")

    warning_calls = []

    monkeypatch.setattr(
        agent_job_dispatcher,
        "dispatch_agent_job_if_connected",
        raise_dispatch_error,
    )
    monkeypatch.setattr(
        agent_job_dispatcher,
        "logger",
        SimpleNamespace(
            warning=lambda *args, **kwargs: warning_calls.append((args, kwargs))
        ),
    )
    db = SimpleNamespace(rollback=Mock())
    job = SimpleNamespace(id=17, agent_machine_id=23)

    result = await agent_job_dispatcher.dispatch_agent_job_best_effort(
        db,
        job,
        error="caller error",
        agent_job_id=999,
        agent_machine_id=888,
        repository_id=5,
    )

    assert result is False
    db.rollback.assert_called_once_with()
    assert len(warning_calls) == 1
    _, log_context = warning_calls[0]
    assert log_context["error"] == "dispatch failed"
    assert log_context["agent_job_id"] == 17
    assert log_context["agent_machine_id"] == 23
    assert log_context["repository_id"] == 5
