"""The agent keeps a job's outcome until the server has it (#1377).

`_deliver_terminal` used to try /complete, /fail or /cancel three times,
0.1 s apart, and then drop the outcome. The job left running_job_ids with it,
so the next hello reported it as gone, and the server ran it again: a second
archive, a script hook's side effects twice.
"""

import json
import queue
import threading
import time

import pytest

from agent.borg_ui_agent.client import AgentClientError
from agent.borg_ui_agent.config import AgentConfig


class FakeWebSocket:
    def __init__(self, incoming):
        self.incoming = list(incoming)
        self.sent = []
        self.closed = False

    def settimeout(self, timeout):
        pass

    def send(self, payload):
        self.sent.append(json.loads(payload))

    def recv(self):
        if not self.incoming:
            raise EOFError("closed")
        return json.dumps(self.incoming.pop(0))

    def ping(self):
        pass

    def close(self):
        self.closed = True


class FlakyHttpClient:
    """A job API that refuses every report until `reachable` is set."""

    def __init__(self):
        self.reachable = threading.Event()
        self.completed = []
        self.failed = []
        self.canceled = []
        self.attempts = 0

    def _check(self):
        self.attempts += 1
        if not self.reachable.is_set():
            raise AgentClientError("POST /api/agents/jobs/42/complete failed: refused")

    def complete_job(self, job_id, *, result):
        self._check()
        self.completed.append((job_id, result))
        return {"id": job_id, "status": "completed"}

    def fail_job(self, job_id, *, error_message, return_code=None, **report):
        self._check()
        self.failed.append((job_id, error_message, return_code))
        return {"id": job_id, "status": "failed"}

    def cancel_job(self, job_id):
        self._check()
        self.canceled.append(job_id)
        return {"id": job_id, "status": "canceled"}


@pytest.fixture
def patch_session_platform(monkeypatch):
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.detect_platform",
        lambda: {"hostname": "host.local", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.session.detect_borg_binaries", lambda: [])


def _command(job_id=42, command="repository.check"):
    return {
        "type": "command",
        "command_id": f"cmd-{job_id}",
        "command": command,
        "job_id": job_id,
        "payload": {},
    }


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


@pytest.mark.unit
def test_an_outcome_the_server_did_not_take_keeps_the_job_in_the_next_hello(
    patch_session_platform, monkeypatch
):
    from agent.borg_ui_agent.session import AgentSessionRuntime

    def handler(job, client, *, should_cancel):
        client.complete_job(job["id"], result={"return_code": 0})

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.get_job_handler", lambda command: handler
    )
    http = FlakyHttpClient()
    sockets = [FakeWebSocket([_command()]), FakeWebSocket([])]
    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: sockets.pop(0),
        http_client=http,
    )

    runtime.run_session(max_messages=1)
    second = sockets[0]
    runtime.run_session(max_messages=0)

    assert http.completed == []
    assert second.sent[0]["type"] == "hello"
    assert second.sent[0]["running_job_ids"] == [42]

    # Once the server answers again the outcome is delivered, and the job
    # leaves the list.
    http.reachable.set()
    assert _wait_for(lambda: http.completed == [(42, {"return_code": 0})])
    assert _wait_for(lambda: runtime._running_job_ids() == [])


def _runtime(http, sockets, **kwargs):
    from agent.borg_ui_agent.session import AgentSessionRuntime

    kwargs.setdefault("outcome_retry_seconds", (0.05, 0.2))
    return AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kw: sockets.pop(0),
        http_client=http,
        **kwargs,
    )


def _completing_handler(monkeypatch, result=None):
    def handler(job, client, *, should_cancel):
        client.complete_job(job["id"], result=result or {"return_code": 0})

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.get_job_handler", lambda command: handler
    )


@pytest.mark.unit
def test_an_outcome_reachable_before_the_hello_is_delivered_first(
    patch_session_platform, monkeypatch
):
    """The kept outcome goes out before the next hello, so the hello already
    finds the job finished."""
    _completing_handler(monkeypatch)
    http = FlakyHttpClient()
    hello_socket = FakeWebSocket([])
    runtime = _runtime(http, [FakeWebSocket([_command()]), hello_socket])
    runtime.run_session(max_messages=1)
    assert http.completed == []

    http.reachable.set()
    runtime.run_session(max_messages=0)

    assert http.completed == [(42, {"return_code": 0})]
    assert hello_socket.sent[0]["running_job_ids"] == []


@pytest.mark.unit
def test_an_outcome_the_server_answered_with_a_refusal_is_not_kept(
    patch_session_platform, monkeypatch
):
    """A 404 (the job is gone) settles the report."""

    class RefusingHttpClient(FlakyHttpClient):
        def complete_job(self, job_id, *, result):
            raise AgentClientError("gone", status_code=404)

    _completing_handler(monkeypatch)
    runtime = _runtime(RefusingHttpClient(), [FakeWebSocket([_command()])])
    runtime.run_session(max_messages=1)

    assert runtime._kept_outcomes.pending() == []
    assert runtime._running_job_ids() == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status_code", "answer"),
    [
        (None, "unanswered"),
        (404, "settled"),
        (409, "settled"),
        (400, "refused"),
        (413, "refused"),
        (422, "refused"),
        (401, "retry"),
        (403, "retry"),
        (408, "retry"),
        (429, "retry"),
        (500, "retry"),
        (503, "retry"),
    ],
)
def test_what_an_answer_means_for_a_kept_outcome(status_code, answer):
    from agent.borg_ui_agent.client import report_answer

    assert report_answer(AgentClientError("x", status_code=status_code)) == answer
    assert report_answer(RuntimeError("connection refused")) == "unanswered"


@pytest.mark.unit
def test_a_report_refused_for_good_is_replaced_by_a_failure(
    patch_session_platform, monkeypatch
):
    """A proxy that refuses a large result (413) will never take it: the
    job is reported failed instead of being dropped, which would let the
    server run it again."""

    class TooLarge(FlakyHttpClient):
        def complete_job(self, job_id, *, result):
            raise AgentClientError("HTTP 413: too large", status_code=413)

    _completing_handler(monkeypatch)
    http = TooLarge()
    http.reachable.set()
    runtime = _runtime(http, [FakeWebSocket([_command()])])
    runtime.run_session(max_messages=1)

    assert _wait_for(lambda: len(http.failed) == 1)
    job_id, message, return_code = http.failed[0]
    assert job_id == 42
    assert "refused the agent's report" in message and "413" in message
    assert _wait_for(lambda: runtime._running_job_ids() == [])


@pytest.mark.unit
def test_one_outcome_the_server_errors_on_does_not_hold_up_the_others(
    patch_session_platform,
):
    from agent.borg_ui_agent.client import AgentClient

    class OneBroken(FlakyHttpClient):
        def complete_job(self, job_id, *, result):
            if job_id == 1:
                raise AgentClientError("HTTP 500", status_code=500)
            return super().complete_job(job_id, result=result)

    http = OneBroken()
    http.reachable.set()
    runtime = _runtime(http, [])
    runtime._kept_outcomes.keep(1, "complete", {"result": {}})
    runtime._kept_outcomes.keep(2, "complete", {"result": {}})
    assert isinstance(runtime._http_client, (AgentClient, OneBroken))

    assert runtime._deliver_pending_outcomes() == 1
    assert http.completed == [(2, {})]
    assert runtime._kept_outcomes.pending() == [(1, "complete", {"result": {}})]


@pytest.mark.unit
def test_the_client_error_carries_the_http_status():
    from agent.borg_ui_agent.client import AgentClient

    class Response:
        status_code = 404
        text = "not found"
        content = b""

    class Session:
        def request(self, *args, **kwargs):
            return Response()

    client = AgentClient("https://borgui.example.com", "secret", session=Session())

    with pytest.raises(AgentClientError) as raised:
        client.complete_job(7, result={})

    assert raised.value.status_code == 404


@pytest.mark.unit
def test_a_cancel_for_a_job_with_a_kept_outcome_does_not_replace_it(
    patch_session_platform, monkeypatch
):
    _completing_handler(monkeypatch)
    http = FlakyHttpClient()
    runtime = _runtime(
        http,
        [
            FakeWebSocket(
                [
                    _command(),
                    {
                        "type": "command",
                        "command_id": "cancel-42",
                        "command": "cancel",
                        "job_id": 42,
                        "payload": {"job_id": 42},
                    },
                ]
            )
        ],
    )

    runtime.run_session(max_messages=2)
    http.reachable.set()

    assert _wait_for(lambda: http.completed == [(42, {"return_code": 0})])
    assert http.canceled == []


@pytest.mark.unit
def test_log_lines_carry_the_attempt_the_server_dispatched(
    patch_session_platform, monkeypatch
):
    """On the socket and over REST once the session has closed (#1383)."""

    def handler(job, client, *, should_cancel):
        client.send_log(job["id"], sequence=0, message="first")
        client.complete_job(job["id"], result={})

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.get_job_handler", lambda command: handler
    )
    http = FlakyHttpClient()
    http.reachable.set()
    socket = FakeWebSocket([{**_command(), "attempt": 1712345678901234}])
    runtime = _runtime(http, [socket])

    runtime.run_session(max_messages=1)

    logs = [frame for frame in socket.sent if frame.get("type") == "log"]
    assert logs[0]["attempt"] == 1712345678901234

    from agent.borg_ui_agent.session import SessionCommandClient

    class RestClient:
        def __init__(self):
            self.logs = []

        def send_log(self, job_id, **fields):
            self.logs.append(fields)

    closing = threading.Event()
    closing.set()
    rest = RestClient()
    client = SessionCommandClient(
        command_id="cmd-1",
        job_id=42,
        outbox=queue.Queue(),
        closing=closing,
        http_client=rest,
        attempt=1712345678901234,
    )
    client.started = True
    client.send_log(42, sequence=1, message="after the drop")

    assert rest.logs == [
        {
            "sequence": 1,
            "stream": "stdout",
            "message": "after the drop",
            "attempt": 1712345678901234,
        }
    ]


@pytest.mark.unit
def test_a_server_before_attempts_sends_none_and_none_is_echoed(
    patch_session_platform, monkeypatch
):
    def handler(job, client, *, should_cancel):
        client.send_log(job["id"], sequence=0, message="first")
        client.complete_job(job["id"], result={})

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.get_job_handler", lambda command: handler
    )
    http = FlakyHttpClient()
    http.reachable.set()
    socket = FakeWebSocket([{**_command(), "attempt": "1712345678901234"}])

    _runtime(http, [socket]).run_session(max_messages=1)

    logs = [frame for frame in socket.sent if frame.get("type") == "log"]
    assert "attempt" not in logs[0]


@pytest.mark.unit
def test_the_heartbeat_lists_the_jobs_with_a_kept_outcome(
    patch_session_platform, monkeypatch
):
    _completing_handler(monkeypatch)
    http = FlakyHttpClient()
    runtime = _runtime(http, [FakeWebSocket([_command()])])
    runtime.run_session(max_messages=1)

    heartbeat_socket = FakeWebSocket([])
    runtime._send_keepalive(heartbeat_socket)

    assert heartbeat_socket.sent == [{"type": "heartbeat", "running_job_ids": [42]}]


class AlwaysFailing(FlakyHttpClient):
    """A server that answers every report with a 500."""

    def complete_job(self, job_id, *, result):
        self.attempts += 1
        raise AgentClientError("HTTP 500", status_code=500)

    def fail_job(self, job_id, *, error_message, return_code=None, **report):
        self.attempts += 1
        self.failed_attempts = getattr(self, "failed_attempts", []) + [error_message]
        raise AgentClientError("HTTP 500", status_code=500)


@pytest.mark.unit
def test_an_outcome_the_server_errors_on_is_kept_inside_the_limit():
    runtime = _runtime(AlwaysFailing(), [])
    runtime._kept_outcomes.keep(1, "complete", {"result": {}})

    assert runtime._deliver_pending_outcomes() == 1
    first = runtime._kept_outcomes.retrying_since(1, now=0.0)
    assert first > 0.0
    assert runtime._deliver_pending_outcomes() == 1
    # The clock started at the first error answer and does not restart.
    assert runtime._kept_outcomes.retrying_since(1, now=0.0) == first
    assert runtime._kept_outcomes.pending() == [(1, "complete", {"result": {}})]


@pytest.mark.unit
def test_an_outcome_the_server_errors_on_past_the_limit_ends_the_job(monkeypatch):
    """Kept for good, the report would keep its job listed, and so active
    with its repository held: past the limit a plain failure takes its
    place, and if that is not taken either, it is dropped."""
    from agent.borg_ui_agent import session

    monkeypatch.setattr(session, "OUTCOME_RETRY_LIMIT_SECONDS", 0)
    http = AlwaysFailing()
    runtime = _runtime(http, [])
    runtime._kept_outcomes.keep(1, "complete", {"result": {}})

    runtime._deliver_pending_outcomes()
    assert runtime._kept_outcomes.pending()[0][1] == "refused"
    assert (
        "did not take the agent's report"
        in (runtime._kept_outcomes.pending()[0][2]["error_message"])
    )

    runtime._deliver_pending_outcomes()
    assert runtime._kept_outcomes.pending() == []
    assert runtime._running_job_ids() == []


@pytest.mark.unit
def test_an_unreachable_server_is_waited_for_without_a_limit(monkeypatch):
    from agent.borg_ui_agent import session

    monkeypatch.setattr(session, "OUTCOME_RETRY_LIMIT_SECONDS", 0)
    runtime = _runtime(FlakyHttpClient(), [])
    runtime._kept_outcomes.keep(1, "complete", {"result": {}})

    assert runtime._deliver_pending_outcomes() == 1
    assert runtime._kept_outcomes.pending() == [(1, "complete", {"result": {}})]
