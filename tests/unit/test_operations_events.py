from datetime import datetime

import pytest

from app.database.models import Operation
from app.services.operations import events as op_events


class _Manager:
    def __init__(self):
        self.calls = []

    async def broadcast_event(self, event_type, data, user_id=None):
        self.calls.append((event_type, data))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_broadcast_updated_serializes_datetimes(monkeypatch):
    manager = _Manager()
    monkeypatch.setattr(op_events, "event_manager", manager)
    op = Operation(
        id=7,
        repository_id=None,
        kind="stats",
        category="index",
        run_id="r",
        status="completed",
        started_at=datetime(2026, 9, 3, 12, 0, 0),
        created_at=datetime(2026, 9, 3, 11, 59, 0),
    )
    await op_events.broadcast_operation_updated(op)
    event_type, data = manager.calls[0]
    assert event_type == "operation.updated"
    assert data["id"] == 7
    assert data["kind"] == "stats"
    assert isinstance(data["started_at"], str)
    assert data["completed_at"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_broadcast_progress_payload(monkeypatch):
    manager = _Manager()
    monkeypatch.setattr(op_events, "event_manager", manager)
    op = Operation(
        id=3,
        kind="archive_sync",
        category="index",
        run_id="r",
        progress_current=2,
        progress_total=5,
        progress_message="x",
    )
    await op_events.broadcast_operation_progress(op)
    assert manager.calls == [
        (
            "operation.progress",
            {
                "id": 3,
                "progress_percent": None,
                "progress_current": 2,
                "progress_total": 5,
                "progress_message": "x",
            },
        )
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_broadcast_errors_are_swallowed(monkeypatch):
    class Broken:
        async def broadcast_event(self, *a, **k):
            raise RuntimeError("no clients")

    monkeypatch.setattr(op_events, "event_manager", Broken())
    op = Operation(id=1, kind="stats", category="index", run_id="r")
    await op_events.broadcast_operation_updated(op)
    await op_events.broadcast_operation_progress(op)
