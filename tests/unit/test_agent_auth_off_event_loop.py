"""Authenticating an agent must not hold the event loop.

The token check is a bcrypt comparison plus a query. In an `async def`
dependency both run on the loop for every agent request, also for a route that
is a plain `def`, and every other request of the process waits behind them.
"""

import asyncio
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database.models import AgentMachine

RAW_TOKEN = "borgui_agent_" + "t" * 43
# Long enough for a request to arrive, short enough that a check held on the
# loop fails the test instead of hanging it.
HOLD_SECONDS = 5


def _create_agent(test_db) -> None:
    test_db.add(
        AgentMachine(
            name="Polling Agent",
            agent_id="agt_polling",
            token_hash="checked by the test's stand-in",
            token_prefix=RAW_TOKEN[:20],
            status="online",
            capabilities=[],
        )
    )
    test_db.commit()


def _poll(client: TestClient, outcomes: list) -> None:
    try:
        response = client.get(
            "/api/agents/jobs/poll",
            headers={"X-Borg-Agent-Authorization": f"Bearer {RAW_TOKEN}"},
        )
        outcomes.append(response.status_code)
    except Exception as exc:
        outcomes.append(repr(exc))


@pytest.mark.unit
def test_the_loop_answers_while_an_agent_token_is_checked(
    test_client, test_db, session_per_request, monkeypatch
):
    _create_agent(test_db)
    checking = threading.Event()
    release = threading.Event()
    released_in_time = []

    def held_check(token, token_hash):
        checking.set()
        released_in_time.append(release.wait(HOLD_SECONDS))
        return True

    monkeypatch.setattr("app.core.agent_auth.verify_password", held_check)

    outcomes: list = []
    poll = threading.Thread(target=_poll, args=(test_client, outcomes))
    poll.start()
    assert checking.wait(HOLD_SECONDS), "the poll never reached its token check"

    health = test_client.get("/health")
    release.set()
    poll.join(HOLD_SECONDS * 2)
    assert not poll.is_alive()

    assert health.status_code == 200
    # The check was still held when /health came back: it did not need the
    # check to end first.
    assert released_in_time == [True]
    assert outcomes == [200]


@pytest.mark.unit
def test_agent_tokens_are_checked_concurrently(
    test_client, test_db, session_per_request, monkeypatch
):
    _create_agent(test_db)
    both_checking = threading.Barrier(2, timeout=HOLD_SECONDS)

    def meeting_check(token, token_hash):
        both_checking.wait()
        return True

    monkeypatch.setattr("app.core.agent_auth.verify_password", meeting_check)

    outcomes: list = []
    polls = [
        threading.Thread(target=_poll, args=(test_client, outcomes)) for _ in range(2)
    ]
    for poll in polls:
        poll.start()
    for poll in polls:
        poll.join(HOLD_SECONDS * 2)
        assert not poll.is_alive()

    assert outcomes == [200, 200]


@pytest.mark.unit
def test_the_agent_lookup_runs_off_the_loop(
    test_client, test_db, session_per_request, monkeypatch
):
    """The query counts as well: moving only the bcrypt comparison off the loop
    would leave the database wait on it."""
    _create_agent(test_db)
    monkeypatch.setattr(
        "app.core.agent_auth.verify_password", lambda token, token_hash: True
    )
    lookups_on_the_loop = []

    def record_lookup(conn, cursor, statement, parameters, context, executemany):
        if "agent_machines.token_prefix =" not in statement:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            lookups_on_the_loop.append(False)
        else:
            lookups_on_the_loop.append(True)

    engine = test_db.get_bind()
    event.listen(engine, "before_cursor_execute", record_lookup)
    try:
        outcomes: list = []
        _poll(test_client, outcomes)
    finally:
        event.remove(engine, "before_cursor_execute", record_lookup)

    assert outcomes == [200]
    assert lookups_on_the_loop == [False]
