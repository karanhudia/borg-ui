from __future__ import annotations

import json
import logging
import os
import queue
import socket as socket_module
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

from agent.borg_ui_agent import __version__
from agent.borg_ui_agent.borg import detect_borg_binaries, detect_platform
from agent.borg_ui_agent.client import AGENT_AUTH_HEADER, AgentClient
from agent.borg_ui_agent.config import AgentConfig
from agent.borg_ui_agent.filesystem import FilesystemBrowseError, browse_filesystem
from agent.borg_ui_agent.runtime import get_capabilities, get_job_handler
from agent.borg_ui_agent.scripts import list_allowed_scripts

logger = logging.getLogger(__name__)

try:
    from websocket import WebSocketTimeoutException
except Exception:  # pragma: no cover - only used when optional dep is unavailable.
    WebSocketTimeoutException = TimeoutError


# How long the session thread blocks in recv() before it looks at the outbox
# again; also the worst-case delay before a worker's frame reaches the server.
OUTBOX_POLL_SECONDS = 1.0
# How often an idle session emits its application heartbeat + protocol ping.
KEEPALIVE_INTERVAL_SECONDS = 30.0
# Outbox capacity. Frames are drained once per poll interval, so this only fills
# up if the socket has stopped accepting writes; frames are then dropped rather
# than growing without bound.
OUTBOX_MAX_FRAMES = 1000


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
    """Command-scoped client handed to a job handler in a worker thread.

    It deliberately has no socket handle: worker threads never write to the
    WebSocket, they hand frames to the session thread through ``outbox``. See
    the single-writer invariant on :meth:`AgentSessionRuntime.run_session`.
    """

    def __init__(
        self,
        *,
        command_id: str,
        job_id: Optional[int],
        outbox: "queue.Queue[str]",
        closing: Optional[threading.Event] = None,
        artifact_uploader: Optional[Callable[[int, Any], dict[str, Any]]] = None,
        http_client: Optional[AgentClient] = None,
        http_lock: Optional[threading.Lock] = None,
    ):
        self.command_id = command_id
        self.job_id = job_id
        self.finished = False
        self.started = False
        # Required, deliberately without a default: a client built without the
        # session's outbox would queue frames nobody drains, i.e. drop them
        # silently. Forgetting it must fail loudly at construction.
        self._outbox = outbox
        self._closing = closing
        self._artifact_uploader = artifact_uploader
        # Terminal job outcomes (result/error/canceled) are delivered over the
        # REST job API, not the WebSocket — see _deliver_terminal. The client
        # wraps one requests.Session shared by all worker threads, so calls are
        # serialized under http_lock.
        self._http_client = http_client
        self._http_lock = http_lock or threading.Lock()

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
        self._deliver_terminal(
            {"type": "command_result", "job_id": job_id, "result": result},
            lambda c: c.complete_job(job_id, result=result),
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
        self._deliver_terminal(
            {"type": "command_error", "job_id": job_id, "error": error},
            lambda c: c.fail_job(
                job_id, error_message=error_message, return_code=return_code
            ),
        )
        return {"id": job_id, "status": "failed"}

    def cancel_job(self, job_id: int) -> dict[str, Any]:
        self.finished = True
        self._deliver_terminal(
            {"type": "job_canceled", "job_id": job_id},
            lambda c: c.cancel_job(job_id),
        )
        return {"id": job_id, "status": "canceled"}

    def send_result(self, result: dict[str, Any]) -> None:
        self.finished = True
        self._deliver_terminal(
            {"type": "command_result", "job_id": self.job_id, "result": result},
            lambda c: c.complete_job(self.job_id, result=result),
        )

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
        self._deliver_terminal(
            {"type": "command_error", "job_id": self.job_id, "error": error},
            lambda c: c.fail_job(
                self.job_id, error_message=message, return_code=return_code
            ),
        )

    def _deliver_terminal(
        self,
        ws_payload: dict[str, Any],
        http_call: Callable[[AgentClient], Any],
    ) -> None:
        """Deliver a terminal outcome (result/error/canceled).

        A **persisted** job (``job_id`` set) is reported over the REST job API,
        NOT the WebSocket. A job result can be large (an archive listing is
        hundreds of KB), and REST keeps the socket free for small control frames
        and keepalive. It also survives a session drop: /complete, /fail and
        /cancel are idempotent, so a retry or late delivery is a no-op, whereas a
        WebSocket frame lost with the session orphans the job until the reaper
        cleans it up 15 minutes later. The client wraps one requests.Session
        shared by all worker threads, so calls are serialized under _http_lock.

        An **ephemeral** command (``job_id`` is None, e.g. an interactive
        filesystem browse) has no job row, so its result is correlated by
        command_id and must come back over the same session that carries the
        pending request. It is queued for the session thread like any other frame.
        """
        if self.job_id is not None and self._http_client is not None:
            with self._http_lock:
                try:
                    http_call(self._http_client)
                except Exception:
                    # Outcome is dropped until the server-side reaper reconciles
                    # it (~15 min); log the job id + traceback so that window is
                    # diagnosable.
                    logger.warning(
                        "Failed to deliver terminal job outcome over REST for job %s",
                        self.job_id,
                        exc_info=True,
                    )
            return
        self.enqueue(ws_payload)

    def _send(self, payload: dict[str, Any]) -> None:
        """Best-effort telemetry send (job_started/progress/log/cancel). Losing
        one is harmless; terminal results go through _deliver_terminal instead."""
        self.enqueue(payload)

    def enqueue(self, payload: dict[str, Any]) -> bool:
        """Hand one frame to the session thread, which owns the socket.

        Returns False when the frame was not queued: the session is already
        closing (nothing queued now can still be delivered), or the outbox is
        full because the socket has stopped draining.
        """
        if self._closing is not None and self._closing.is_set():
            return False
        message = json.dumps({"command_id": self.command_id, **payload})
        try:
            self._outbox.put_nowait(message)
        except queue.Full:
            logger.warning(
                "Agent session outbox is full; dropping %s frame for command %s",
                payload.get("type"),
                self.command_id,
            )
            return False
        return True

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
        http_client: Optional[AgentClient] = None,
    ):
        self.config = config
        self.connect = connect or _default_connect
        self.sleep = sleep
        self.timeout_seconds = timeout_seconds
        # HTTP client used to stream binary artifacts (e.g. extracted files) to
        # the server out-of-band, so they never go through the WebSocket.
        self._artifact_client = AgentClient.from_config(config)
        # REST client used to re-deliver terminal job frames if the WebSocket
        # drops mid-command (see SessionCommandClient._deliver_terminal).
        self._http_client = http_client or AgentClient.from_config(config)
        # Serializes REST terminal deliveries across worker threads (the client
        # wraps one requests.Session).
        self._http_lock = threading.Lock()
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
        """Open a session and dispatch each server command to a worker thread.

        **Single-writer invariant: this thread is the only one that ever touches
        the socket.** Worker threads hand outgoing frames to ``outbox`` and this
        loop drains them between ``recv()`` calls. The socket may be a TLS
        connection (``wss://``), and an ``ssl.SSLSocket`` is not thread-safe:
        websocket-client guards send and recv with two *different* locks, so a
        worker sending while this loop reads corrupts the OpenSSL state and the
        session dies mid-write. A single lock over both is not an option either —
        the blocking ``recv()`` would lock every sender out.

        The loop also stays in ``recv()`` while a job runs, so websocket-client
        keeps auto-ponging the server's keepalive pings and the session survives
        long backups and checks.
        """
        socket = self.connect(
            _session_url(self.config.server_url),
            header=[f"{AGENT_AUTH_HEADER}: Bearer {self.config.agent_token}"],
            timeout=self.timeout_seconds,
        )
        # The connect timeout covers the TCP/TLS handshake; once established the
        # loop wants a short recv timeout so queued frames are not held back.
        self._set_socket_timeout(socket, OUTBOX_POLL_SECONDS)
        outbox: "queue.Queue[str]" = queue.Queue(maxsize=OUTBOX_MAX_FRAMES)
        workers: list[threading.Thread] = []
        # Per-session guard: once set, in-flight workers stop queueing frames
        # that this loop will never get to deliver.
        closing = threading.Event()
        clean_exit = False
        try:
            self._send_hello(socket)
            handled = 0
            last_keepalive_at = None
            while max_messages is None or handled < max_messages:
                self._flush_outbox(socket, outbox)
                try:
                    raw_message = socket.recv()
                except (TimeoutError, WebSocketTimeoutException):
                    now = time.monotonic()
                    if (
                        last_keepalive_at is None
                        or now - last_keepalive_at >= KEEPALIVE_INTERVAL_SECONDS
                    ):
                        last_keepalive_at = now
                        self._send_keepalive(socket)
                    continue
                message = json.loads(raw_message)
                if isinstance(message, dict) and message.get("type") == "command":
                    worker = threading.Thread(
                        target=self._handle_command,
                        args=(outbox, message, closing),
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
                # finish, then flush what they queued before the socket closes.
                for worker in workers:
                    worker.join()
                try:
                    self._flush_outbox(socket, outbox)
                except Exception:
                    pass
            else:
                # The session dropped. Suppress any further frames, signal
                # cancellation, and return *without* joining -- so run_forever
                # reconnects right away instead of blocking on a possibly-slow
                # job. The cancelled daemon workers wind down on their own.
                closing.set()
                with self._registry_lock:
                    for event in self._cancel_events.values():
                        event.set()
            try:
                socket.close()
            except Exception:
                pass

    @contextmanager
    def _writing(self, socket):
        """Raise the socket timeout to the full session timeout for the duration
        of a write, then drop back to the recv poll interval.

        ``settimeout`` bounds writes as well as reads, so every write has to run
        under it: a frame can be hundreds of KB, and on a slow link the poll
        interval would abort it. Wrap *all* writes, not just the large ones —
        a one-second budget is a session-killer wherever it applies.
        """
        self._set_socket_timeout(socket, self.timeout_seconds)
        try:
            yield
        finally:
            self._set_socket_timeout(socket, OUTBOX_POLL_SECONDS)

    def _flush_outbox(self, socket, outbox: "queue.Queue[str]") -> None:
        """Write every queued worker frame. Session thread only — see the
        single-writer invariant on run_session. A failing write propagates so
        the loop tears the session down and run_forever reconnects."""
        try:
            message = outbox.get_nowait()
        except queue.Empty:
            return
        with self._writing(socket):
            while True:
                socket.send(message)
                try:
                    message = outbox.get_nowait()
                except queue.Empty:
                    return

    @staticmethod
    def _set_socket_timeout(socket, timeout_seconds: float) -> None:
        settimeout = getattr(socket, "settimeout", None)
        if callable(settimeout):
            settimeout(timeout_seconds)

    def _send_keepalive(self, socket) -> None:
        """Keep an idle session alive. The protocol ping keeps the socket open
        but never reaches application code, so it cannot refresh the server's
        last_seen_at — send an application-level heartbeat too, otherwise an
        idle-but-healthy agent looks stale."""
        with self._writing(socket):
            try:
                socket.send(json.dumps({"type": "heartbeat"}))
            except Exception:
                pass
            ping = getattr(socket, "ping", None)
            if callable(ping):
                ping()

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
        with self._writing(socket):
            socket.send(message)

    def _handle_command(
        self,
        outbox: "queue.Queue[str]",
        message: dict[str, Any],
        closing: Optional[threading.Event] = None,
    ) -> None:
        """Handle one server command (runs in a worker thread): ack it, then run
        the matching handler with cooperative cancellation wired in. Outgoing
        frames go to ``outbox`` for the session thread to write; ``closing``
        suppresses them once the owning session has been torn down."""
        command_id = str(message.get("command_id") or "")
        command = str(message.get("command") or "")
        raw_job_id = message.get("job_id")
        job_id = int(raw_job_id) if raw_job_id is not None else None
        payload = (
            message.get("payload") if isinstance(message.get("payload"), dict) else {}
        )
        client = SessionCommandClient(
            command_id=command_id,
            job_id=job_id,
            outbox=outbox,
            closing=closing,
            artifact_uploader=self._artifact_client.upload_artifact,
            http_client=self._http_client,
            http_lock=self._http_lock,
        )

        client.enqueue({"type": "command_ack", "job_id": job_id})

        if command == "filesystem.browse":
            self._handle_filesystem_browse(client, payload)
            return

        if command == "diagnostics.run":
            self._handle_diagnostics(client, payload)
            return

        if command == "agent.repository_defaults":
            self._handle_repository_defaults(client, payload)
            return

        if command == "agent.list_scripts":
            self._handle_list_scripts(client, payload)
            return

        if command == "cancel":
            # Signal the worker running this job so it actually stops; it emits
            # its own job_canceled as it unwinds. Also record the cancel here via
            # the cancel path (idempotent /cancel) so the outcome is captured even
            # if no worker is running. NOT send_result — that routes through
            # complete_job and would wrongly finalize the target job as completed,
            # racing the worker's cancel. The server dispatches cancel
            # fire-and-forget (wait_for_result=False), so no response is expected.
            if job_id is not None:
                self._signal_cancel(job_id)
                client.cancel_job(job_id)
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

    def _handle_list_scripts(
        self, client: SessionCommandClient, payload: dict[str, Any]
    ) -> None:
        """Report the scripts the agent publishes (its allow-list) so the UI can
        offer them for pre/post-backup hooks. Never exposes paths — names only."""
        try:
            scripts = list_allowed_scripts()
        except Exception as exc:  # defensive: listing must never drop the session
            client.send_error(f"Listing agent scripts failed: {exc}")
            return
        client.send_result({"scripts": scripts})

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
