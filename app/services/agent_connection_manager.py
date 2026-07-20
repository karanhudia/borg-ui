from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Optional
from uuid import uuid4

from fastapi import WebSocket


class AgentConnectionUnavailable(RuntimeError):
    pass


class AgentCommandTimeout(RuntimeError):
    pass


class AgentCommandError(RuntimeError):
    def __init__(self, message: str, payload: Optional[dict[str, Any]] = None):
        self.payload = payload or {}
        super().__init__(message)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentConnection:
    agent_machine_id: int
    agent_id: str
    websocket: WebSocket
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
    pending_commands: dict[str, asyncio.Future] = field(default_factory=dict)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send_command(
        self,
        *,
        command: str,
        payload: dict[str, Any],
        timeout_seconds: float,
        job_id: Optional[int] = None,
        wait_for_result: bool = True,
    ) -> dict[str, Any]:
        command_id = str(uuid4())
        future: Optional[asyncio.Future] = None
        if wait_for_result:
            future = asyncio.get_running_loop().create_future()
            self.pending_commands[command_id] = future

        try:
            async with self.send_lock:
                await self.websocket.send_json(
                    {
                        "type": "command",
                        "command_id": command_id,
                        "command": command,
                        "job_id": job_id,
                        "payload": payload,
                    }
                )
        except Exception:
            if future is not None:
                self.pending_commands.pop(command_id, None)
            raise

        if future is None:
            return {"command_id": command_id}

        try:
            result = await asyncio.wait_for(future, timeout=timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise AgentCommandTimeout(command) from exc
        finally:
            self.pending_commands.pop(command_id, None)

        if isinstance(result, AgentCommandError):
            raise result
        return result

    def resolve_command(self, command_id: str, result: dict[str, Any]) -> bool:
        future = self.pending_commands.get(command_id)
        if not future or future.done():
            return False
        future.set_result(result)
        return True

    def reject_command(self, command_id: str, error: AgentCommandError) -> bool:
        future = self.pending_commands.get(command_id)
        if not future or future.done():
            return False
        future.set_result(error)
        return True

    def reject_pending(self, message: str) -> None:
        error = AgentCommandError(message)
        for future in list(self.pending_commands.values()):
            if not future.done():
                future.set_result(error)
        self.pending_commands.clear()


class AgentConnectionManager:
    """Registry of live agent WebSocket sessions and their pending commands.

    State is process-local: both the socket and the Future a caller waits on live
    in the *process* that accepted the session, so a request needing an agent
    must be served by that same process. Any request handled elsewhere sees the
    agent as unconnected (``AgentConnectionUnavailable``) even though the session
    is healthy.

    Today this holds because entrypoint.sh pins gunicorn to ``--workers 1`` and
    deployments run a single replica — note that raising either one breaks it,
    not just adding replicas. Serving agent requests from more than one process
    needs process-level sticky routing or a shared broker (e.g. Redis pub/sub
    keyed by command_id).
    """

    def __init__(self, *, max_log_entries_per_agent: int = 200):
        self._connections: dict[int, AgentConnection] = {}
        self._logs: dict[int, Deque[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        self.max_log_entries_per_agent = max_log_entries_per_agent

    async def register(self, connection: AgentConnection) -> None:
        async with self._lock:
            previous = self._connections.get(connection.agent_machine_id)
            self._connections[connection.agent_machine_id] = connection
        if previous is not None and previous is not connection:
            previous.reject_pending("Agent session was replaced by a new connection")
            try:
                await previous.websocket.close(code=1012)
            except Exception:
                pass
        self.append_log(
            connection.agent_machine_id,
            level="info",
            message="Agent session connected",
            stream="session",
        )

    async def disconnect(
        self, agent_machine_id: int, connection: AgentConnection
    ) -> bool:
        async with self._lock:
            current = self._connections.get(agent_machine_id)
            if current is not connection:
                return False
            self._connections.pop(agent_machine_id, None)
        connection.reject_pending("Agent session disconnected")
        self.append_log(
            agent_machine_id,
            level="warning",
            message="Agent session disconnected",
            stream="session",
        )
        return True

    def get(self, agent_machine_id: int) -> Optional[AgentConnection]:
        return self._connections.get(agent_machine_id)

    def is_connected(self, agent_machine_id: int) -> bool:
        return agent_machine_id in self._connections

    async def send_command(
        self,
        agent_machine_id: int,
        *,
        command: str,
        payload: dict[str, Any],
        timeout_seconds: float,
        job_id: Optional[int] = None,
        wait_for_result: bool = True,
    ) -> dict[str, Any]:
        connection = self.get(agent_machine_id)
        if connection is None:
            raise AgentConnectionUnavailable("Agent does not have an active session")
        return await connection.send_command(
            command=command,
            payload=payload,
            timeout_seconds=timeout_seconds,
            job_id=job_id,
            wait_for_result=wait_for_result,
        )

    def resolve_command(
        self, agent_machine_id: int, command_id: str, result: dict[str, Any]
    ) -> bool:
        connection = self.get(agent_machine_id)
        if connection is None:
            return False
        return connection.resolve_command(command_id, result)

    def reject_command(
        self,
        agent_machine_id: int,
        command_id: str,
        *,
        message: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> bool:
        connection = self.get(agent_machine_id)
        if connection is None:
            return False
        return connection.reject_command(
            command_id, AgentCommandError(message, payload)
        )

    def append_log(
        self,
        agent_machine_id: int,
        *,
        message: str,
        level: str = "info",
        stream: str = "session",
        command_id: Optional[str] = None,
        job_id: Optional[int] = None,
    ) -> None:
        entries = self._logs.setdefault(
            agent_machine_id, deque(maxlen=self.max_log_entries_per_agent)
        )
        entries.append(
            {
                "id": (
                    f"session-{agent_machine_id}-{len(entries)}-"
                    f"{datetime.now(timezone.utc).timestamp()}"
                ),
                "agent_machine_id": agent_machine_id,
                "job_id": job_id,
                "command_id": command_id,
                "stream": stream,
                "level": level,
                "message": message,
                "created_at": _now_iso(),
            }
        )

    def list_logs(self, agent_machine_id: int) -> list[dict[str, Any]]:
        return list(self._logs.get(agent_machine_id, ()))


agent_connection_manager = AgentConnectionManager()
