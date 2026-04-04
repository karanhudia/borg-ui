"""
Unit tests for events API endpoints
"""
import asyncio

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestEventsEndpoints:
    """Test events/SSE API endpoints"""

    def test_events_stream_unauthorized(self, test_client: TestClient):
        """Test SSE events stream without authentication"""
        response = test_client.get("/api/events/stream")

        assert response.status_code == 401
        assert response.json()["detail"]["key"] == "backend.errors.events.notAuthenticated"

    def test_events_stream_rejects_invalid_token(self, test_client: TestClient, monkeypatch):
        """Test SSE events stream rejects invalid tokens."""
        monkeypatch.setattr("app.core.security.verify_token", lambda token: None)

        response = test_client.get("/api/events/stream?token=invalid-token")

        assert response.status_code == 401
        assert response.json()["detail"]["key"] == "backend.errors.events.invalidAuthCredentials"

    def test_events_stream_returns_streaming_response_for_valid_token(
        self,
        test_client: TestClient,
        test_db,
        monkeypatch
    ):
        """Test SSE stream returns the expected response contract for a valid token."""
        from app.database.models import User

        user = User(
            username="stream-user",
            email="stream-user@example.com",
            password_hash="hash",
            is_active=True,
            role="viewer",
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        monkeypatch.setattr("app.core.security.verify_token", lambda token: user.username)

        async def fake_event_generator(user_id: str):
            assert user_id == str(user.id)
            yield 'data: {"type": "hello"}\n\n'

        monkeypatch.setattr("app.api.events.event_generator", fake_event_generator)

        response = test_client.get("/api/events/stream?token=valid-token")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert 'data: {"type": "hello"}' in response.text

    def test_backup_logs_stream_unauthorized(self, test_client: TestClient):
        """Test backup logs stream without authentication"""
        response = test_client.get("/api/events/backup/1/logs")

        assert response.status_code in [401, 403, 404]

    def test_backup_logs_stream_nonexistent(self, test_client: TestClient, admin_headers):
        """Test backup logs stream for non-existent job"""
        response = test_client.get("/api/events/backup/99999/logs", headers=admin_headers)

        # Should handle gracefully (might return 404 or empty stream)
        assert response.status_code in [200, 404, 422, 500]

    def test_restore_logs_stream_nonexistent(self, test_client: TestClient, admin_headers):
        """Test restore logs stream for non-existent job"""
        response = test_client.get("/api/events/restore/99999/logs", headers=admin_headers)

        assert response.status_code in [200, 404, 422, 500]

    def test_job_progress_nonexistent(self, test_client: TestClient, admin_headers):
        """Test job progress for non-existent job"""
        response = test_client.get("/api/events/job/99999/progress", headers=admin_headers)

        assert response.status_code in [200, 404, 422, 500]


@pytest.mark.unit
@pytest.mark.asyncio
class TestEventManagerInternals:
    """Test event manager and generator helpers."""

    async def test_event_manager_broadcast_and_connection_lifecycle(self):
        from app.api import events

        manager = events.EventManager()
        queue_one = await manager.add_connection("1")
        queue_two = await manager.add_connection("2")

        assert await manager.get_connection_count() == 2

        await manager.broadcast_event("backup_started", {"repository": "/repo"})

        event_one = await queue_one.get()
        event_two = await queue_two.get()

        assert event_one["type"] == "backup_started"
        assert event_one["data"]["repository"] == "/repo"
        assert event_two["type"] == "backup_started"

        await manager.broadcast_event("backup_finished", {"ok": True}, user_id="1")

        targeted = await queue_one.get()
        assert targeted["type"] == "backup_finished"
        assert targeted["data"]["ok"] is True
        assert queue_two.empty()

        await manager.remove_connection("1")
        await manager.remove_connection("2")
        assert await manager.get_connection_count() == 0

    async def test_event_generator_emits_initial_event_keepalive_and_cleans_up(self, monkeypatch):
        from app.api import events

        manager = events.EventManager()
        monkeypatch.setattr(events, "event_manager", manager)

        wait_for_calls = 0

        async def fake_wait_for(awaitable, timeout=None):
            nonlocal wait_for_calls
            wait_for_calls += 1
            if wait_for_calls == 1:
                awaitable.close()
                raise asyncio.TimeoutError
            awaitable.close()
            raise RuntimeError("stop generator")

        monkeypatch.setattr(events.asyncio, "wait_for", fake_wait_for)

        generator = events.event_generator("42")

        first_event = await generator.__anext__()
        second_event = await generator.__anext__()

        assert "connection_established" in first_event
        assert second_event == ":\n\n"

        with pytest.raises(StopAsyncIteration):
            await generator.__anext__()

        assert await manager.get_connection_count() == 0

    async def test_startup_event_schedules_background_monitor(self, monkeypatch):
        from app.api import events

        scheduled = []

        async def fake_monitor_backup_jobs():
            return None

        def fake_create_task(coro):
            scheduled.append(coro)
            coro.close()
            return object()

        monkeypatch.setattr(events, "monitor_backup_jobs", fake_monitor_backup_jobs)
        monkeypatch.setattr(events.asyncio, "create_task", fake_create_task)

        await events.startup_event()

        assert len(scheduled) == 1
