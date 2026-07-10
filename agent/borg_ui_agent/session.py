from __future__ import annotations

import json
import logging
import os
import socket as socket_module
import threading
import time
from collections.abc import Callable
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

from agent.borg_ui_agent import __version__
from agent.borg_ui_agent.borg import detect_borg_binaries, detect_platform
from agent.borg_ui_agent.client import AGENT_AUTH_HEADER, AgentClient
from agent.borg_ui_agent.config import AgentConfig
from agent.borg_ui_agent.filesystem import FilesystemBrowseError, browse_filesystem
from agent.borg_ui_agent.runtime import get_capabilities, get_job_handler

logger = logging.getLogger(__name__)

try:
    from websocket import WebSocketTimeoutException
except Exception:  # pragma: no cover - only used when optional dep is unavailable.
    WebSocketTimeoutException = TimeoutError


def _default_connect(url: str, *, header: list[str], timeout: int):
    from websocket import create_connection

    return create_connection(url, header=header, timeout=timeout)


def _session_url(server_url: str) -> str:
    parsed = urlparse(server_url.rstrip("/"))
    scheme = {"http": "ws", "https": "wss"}.get(parsed.scheme, parsed.scheme)
    path = f"{parsed.path.rstrip('/')}/api/agents/session"
    return urlunparse(
        parsed._replace(scheme=scheme, path=path, params="", query="", fragment="")
    )


def _elapsed_ms(started_at: float) -> int:
    return int(round((time.monotonic() - started_at) * 1000))


def _normalize_tcp_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, TimeoutError):
        return "timeout", "Connection timed out"
    if isinstance(exc, ConnectionRefusedError):
        return "connection_refused", "Connection refused"
    if isinstance(exc, OSError):
        return "network_error", str(exc) or exc.__class__.__name__
    return "tcp_check_failed", str(exc) or exc.__class__.__name__


def _open_tcp_connection(host: str, port: int, timeout_seconds: float) -> None:
    connection = socket_module.create_connection((host, port), timeout=timeout_seconds)
    connection.close()


class SessionCommandClient:
    def __init__(
        self,
        socket,
        *,
        command_id: str,
        job_id: Optional[int],
        send_lock: Optional[threading.Lock] = None,
        closing: Optional[threading.Event] = None,
        artifact_uploader: Optional[Callable[[int, Any], dict[str, Any]]] = None,
    ):
        self.socket = socket
        self.command_id = command_id
        self.job_id = job_id
        self.finished = False
        self.started = False
        self._send_lock = send_lock or threading.Lock()
        self._closing = closing
        self._artifact_uploader = artifact_uploader

    def upload_artifact(self, job_id: int, data: Any) -> dict[str, Any]:
        """Stream a binary job artifact to the server over HTTP (not the WS)."""
        if self._artifact_uploader is None:
            raise RuntimeError("artifact upload is not available in this session")
        return self._artifact_uploader(job_id, data)

    def start_job(self, job_id: int) -> dict[str, Any]:
        self.started = True
        self._send({"type": "job_started", "job_id": job_id})
        return {"id": job_id, "status": "running"}

    def send_log(
        self,
        job_id: int,
        *,
        sequence: int,
        message: str,
        stream: str = "stdout",
    ) -> dict[str, Any]:
        self._ensure_started(job_id)
        self._send(
            {
                "type": "log",
                "job_id": job_id,
                "sequence": sequence,
                "stream": stream,
                "message": message,
            }
        )
        return {"accepted": True}

    def send_progress(self, job_id: int, progress: dict[str, Any]) -> dict[str, Any]:
        self._ensure_started(job_id)
        self._send({"type": "progress", "job_id": job_id, **progress})
        return {"id": job_id, "status": "running"}

    def complete_job(self, job_id: int, *, result: dict[str, Any]) -> dict[str, Any]:
        self._ensure_started(job_id)
        self.finished = True
        self._send(
            {
                "type": "command_result",
                "job_id": job_id,
                "result": result,
            }
        )
        return {"id": job_id, "status": "completed"}

    def fail_job(
        self, job_id: int, *, error_message: str, return_code: Optional[int] = None
    ) -> dict[str, Any]:
        self._ensure_started(job_id)
        self.finished = True
        error: dict[str, Any] = {"message": error_message}
        if return_code is not None:
            error["return_code"] = return_code
        self._send({"type": "command_error", "job_id": job_id, "error": error})
        return {"id": job_id, "status": "failed"}

    def cancel_job(self, job_id: int) -> dict[str, Any]:
        self._ensure_started(job_id)
        self.finished = True
        self._send({"type": "job_canceled", "job_id": job_id})
        return {"id": job_id, "status": "canceled"}

    def send_result(self, result: dict[str, Any]) -> None:
        self.finished = True
        self._send({"type": "command_result", "job_id": self.job_id, "result": result})

    def send_error(
        self,
        message: str,
        *,
        code: str = "command_failed",
        return_code: Optional[int] = None,
    ) -> None:
        self.finished = True
        error: dict[str, Any] = {"code": code, "message": message}
        if return_code is not None:
            error["return_code"] = return_code
        self._send({"type": "command_error", "job_id": self.job_id, "error": error})

    def _send(self, payload: dict[str, Any]) -> None:
        """Serialize one frame onto the socket under the shared send lock, but
        skip the write once the session is closing, so a worker never touches a
        connection the drop handler has already torn down."""
        if self._closing is not None and self._closing.is_set():
            return
        message = json.dumps({"command_id": self.command_id, **payload})
        with self._send_lock:
            if self._closing is not None and self._closing.is_set():
                return
            self.socket.send(message)

    def _ensure_started(self, job_id: int) -> None:
        if not self.started:
            self.start_job(job_id)


class AgentSessionRuntime:
    def __init__(
        self,
        config: AgentConfig,
        *,
        connect: Optional[Callable[..., Any]] = None,
        sleep: Callable[[float], None] = time.sleep,
        timeout_seconds: int = 30,
    ):
        self.config = config
        self.connect = connect or _default_connect
        self.sleep = sleep
        self.timeout_seconds = timeout_seconds
        # HTTP client used to stream binary artifacts (e.g. extracted files) to
        # the server out-of-band, so they never go through the WebSocket.
        self._artifact_client = AgentClient.from_config(config)
        self._send_lock = threading.Lock()
        self._registry_lock = threading.Lock()
        self._cancel_events: dict[int, threading.Event] = {}
        self._pending_cancels: set[int] = set()

    def run_forever(
        self,
        *,
        max_iterations: Optional[int] = None,
        initial_backoff_seconds: float = 1,
        max_backoff_seconds: float = 60,
    ) -> None:
        iterations = 0
        backoff_seconds = initial_backoff_seconds
        while True:
            started_at = time.monotonic()
            healthy_session = False
            try:
                self.run_session()
                healthy_session = True
            except Exception as exc:
                logger.warning("Agent session connection failed: %s", exc)
            if healthy_session or time.monotonic() - started_at >= max_backoff_seconds:
                backoff_seconds = initial_backoff_seconds
            iterations += 1
            self.sleep(backoff_seconds)
            if max_iterations is not None and iterations >= max_iterations:
                return
            backoff_seconds = min(backoff_seconds * 2, max_backoff_seconds)

    def run_session(self, *, max_messages: Optional[int] = None) -> None:
        """Open a session and dispatch each server command to a worker thread,
        keeping the main loop in ``recv()`` so the library auto-pongs the
        server's keepalive pings and the session survives long-running jobs."""
        socket = self.connect(
            _session_url(self.config.server_url),
            header=[f"{AGENT_AUTH_HEADER}: Bearer {self.config.agent_token}"],
            timeout=self.timeout_seconds,
        )
        workers: list[threading.Thread] = []
        # Per-session guard: once set, in-flight workers stop sending, so they
        # never write to a socket the drop handler has already torn down.
        closing = threading.Event()
        clean_exit = False
        try:
            self._send_hello(socket)
            handled = 0
            while max_messages is None or handled < max_messages:
                try:
                    raw_message = socket.recv()
                except (TimeoutError, WebSocketTimeoutException):
                    # Idle keep-alive. The key property of this loop is that it
                    # stays in recv() *even while a job runs in a worker thread*,
                    # so websocket-client keeps auto-ponging the server's pings
                    # and the session survives long backups/checks.
                    #
                    # The protocol ping keeps the socket alive but never reaches
                    # application code, so it cannot refresh the server's
                    # last_seen_at. Send an application-level heartbeat too so an
                    # idle-but-healthy agent stays "live" server-side.
                    with self._send_lock:
                        try:
                            socket.send(json.dumps({"type": "heartbeat"}))
                        except Exception:
                            pass
                        ping = getattr(socket, "ping", None)
                        if callable(ping):
                            ping()
                    continue
                message = json.loads(raw_message)
                if isinstance(message, dict) and message.get("type") == "command":
                    worker = threading.Thread(
                        target=self._handle_command,
                        args=(socket, message, closing),
                        daemon=True,
                    )
                    worker.start()
                    workers.append(worker)
                    workers = [w for w in workers if w.is_alive()]
                handled += 1
            clean_exit = True
        finally:
            if clean_exit:
                # Orderly shutdown (e.g. max_messages reached): let in-flight jobs
                # finish so their final results are sent before the socket closes.
                for worker in workers:
                    worker.join()
            else:
                # The session dropped. Suppress any further frames so daemon
                # workers don't write to the dead socket, signal cancellation,
                # and return *without* joining -- so run_forever reconnects right
                # away instead of blocking on a possibly-slow job. The cancelled
                # daemon workers wind down on their own.
                closing.set()
                with self._registry_lock:
                    for event in self._cancel_events.values():
                        event.set()
            try:
                socket.close()
            except Exception:
                pass

    def _send_hello(self, socket) -> None:
        """Announce this agent (id, host, borg versions, capabilities) to the server."""
        machine = detect_platform()
        borg_versions = [binary.to_api_payload() for binary in detect_borg_binaries()]
        message = json.dumps(
            {
                "type": "hello",
                "agent_id": self.config.agent_id,
                "hostname": machine["hostname"],
                "agent_version": __version__,
                "borg_versions": borg_versions,
                "capabilities": get_capabilities(),
                "running_job_ids": [],
            }
        )
        with self._send_lock:
            socket.send(message)

    def _handle_command(
        self, socket, message: dict[str, Any], closing: Optional[threading.Event] = None
    ) -> None:
        """Handle one server command (runs in a worker thread): ack it, then run
        the matching handler with cooperative cancellation wired in. ``closing``
        suppresses sends once the owning session has been torn down."""
        command_id = str(message.get("command_id") or "")
        command = str(message.get("command") or "")
        raw_job_id = message.get("job_id")
        job_id = int(raw_job_id) if raw_job_id is not None else None
        payload = (
            message.get("payload") if isinstance(message.get("payload"), dict) else {}
        )
        client = SessionCommandClient(
            socket,
            command_id=command_id,
            job_id=job_id,
            send_lock=self._send_lock,
            closing=closing,
            artifact_uploader=self._artifact_client.upload_artifact,
        )

        ack = json.dumps(
            {
                "type": "command_ack",
                "command_id": command_id,
                "job_id": job_id,
            }
        )
        if closing is None or not closing.is_set():
            with self._send_lock:
                socket.send(ack)

        if command == "filesystem.browse":
            self._handle_filesystem_browse(client, payload)
            return

        if command == "diagnostics.run":
            self._handle_diagnostics(client, payload)
            return

        if command == "agent.repository_defaults":
            self._handle_repository_defaults(client, payload)
            return

        if command == "cancel":
            # Signal the worker running this job so it actually stops; the worker
            # emits the job_canceled frame itself as it unwinds.
            if job_id is not None:
                self._signal_cancel(job_id)
            client.send_result({"success": True})
            return

        handler = get_job_handler(command)
        if handler is None or job_id is None:
            client.send_error(
                f"Unsupported agent session command: {command}",
                code="unsupported_command",
            )
            return

        cancel_event = self._register_cancel(job_id)
        try:
            result = handler(
                {"id": job_id, "type": command, "payload": payload},
                client,
                should_cancel=cancel_event.is_set,
            )
        except Exception as exc:
            logger.exception("Agent session command failed", extra={"command": command})
            client.send_error(f"{command} failed: {exc}")
            return
        finally:
            self._unregister_cancel(job_id)

        if client.finished:
            return
        status = getattr(result, "status", "")
        message_text = getattr(result, "message", "") or f"{command} finished"
        return_code = getattr(result, "return_code", None)
        if status == "completed":
            client.complete_job(job_id, result={"message": message_text})
        elif status == "canceled":
            client.cancel_job(job_id)
        else:
            client.fail_job(
                job_id,
                error_message=message_text,
                return_code=return_code,
            )

    def _register_cancel(self, job_id: int) -> threading.Event:
        """Register a cancel Event for ``job_id`` — already set if a cancel for it
        arrived before the worker thread got here (start-up race)."""
        event = threading.Event()
        with self._registry_lock:
            if job_id in self._pending_cancels:
                self._pending_cancels.discard(job_id)
                event.set()
            self._cancel_events[job_id] = event
        return event

    def _signal_cancel(self, job_id: int) -> None:
        """Request cancellation of ``job_id``; if its worker hasn't registered
        yet, remember the request so it isn't lost."""
        with self._registry_lock:
            event = self._cancel_events.get(job_id)
            if event is not None:
                event.set()
            else:
                self._pending_cancels.add(job_id)

    def _unregister_cancel(self, job_id: int) -> None:
        """Drop the cancel Event (and any pending flag) for a finished job."""
        with self._registry_lock:
            self._cancel_events.pop(job_id, None)
            self._pending_cancels.discard(job_id)

    def _handle_repository_defaults(
        self, client: SessionCommandClient, payload: dict[str, Any]
    ) -> None:
        """Report the agent's own environment-configured repository target
        (``$BORG_REPO`` / ``$BORG_REMOTE_PATH``) so the UI can pre-fill the
        repository form, plus whether a ``$BORG_PASSPHRASE`` is set — a boolean,
        never the passphrase value itself."""
        client.send_result(
            {
                "repo": os.environ.get("BORG_REPO"),
                "remote_path": os.environ.get("BORG_REMOTE_PATH"),
                "has_passphrase": bool(os.environ.get("BORG_PASSPHRASE")),
            }
        )

    def _handle_filesystem_browse(
        self, client: SessionCommandClient, payload: dict[str, Any]
    ) -> None:
        path = str(payload.get("path") or "/")
        include_hidden = bool(payload.get("include_hidden", False))
        max_items = int(payload.get("max_items") or 0)
        try:
            result = browse_filesystem(path, include_hidden=include_hidden)
        except FilesystemBrowseError as exc:
            client.send_result(exc.to_result())
            return
        except Exception as exc:
            client.send_error(f"Filesystem browse failed: {exc}")
            return

        items = result.get("items")
        if max_items > 0 and isinstance(items, list) and len(items) > max_items:
            result = {
                **result,
                "items": items[:max_items],
                "items_truncated": True,
            }
        client.send_result(result)

    def _handle_diagnostics(
        self, client: SessionCommandClient, payload: dict[str, Any]
    ) -> None:
        started_at = time.monotonic()
        result: dict[str, Any] = {"success": True}
        target = (
            payload.get("target") if isinstance(payload.get("target"), dict) else None
        )

        if target is not None:
            host = str(target.get("host") or "")
            port = int(target.get("port") or 0)
            timeout_seconds = float(target.get("timeout_seconds") or 3.0)
            tcp_started_at = time.monotonic()
            tcp_result: dict[str, Any] = {
                "target": {
                    "host": host,
                    "port": port,
                    "timeout_seconds": timeout_seconds,
                }
            }
            try:
                _open_tcp_connection(host, port, timeout_seconds)
            except Exception as exc:
                error_code, message = _normalize_tcp_error(exc)
                tcp_result.update(
                    {
                        "status": "failed",
                        "elapsed_ms": _elapsed_ms(tcp_started_at),
                        "error": error_code,
                        "message": message,
                    }
                )
            else:
                tcp_result.update(
                    {
                        "status": "success",
                        "elapsed_ms": _elapsed_ms(tcp_started_at),
                    }
                )
            result["tcp"] = tcp_result

        result["session"] = {"status": "success", "elapsed_ms": _elapsed_ms(started_at)}
        client.send_result(result)
