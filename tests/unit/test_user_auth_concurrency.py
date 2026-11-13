"""Concurrent requests must authenticate as the user named by their credentials."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.schema import CreateSchema, DropSchema

from app.config import settings
from app.core.security import get_password_hash
from app.database.models import ApiToken, Base, User


@pytest.fixture(params=["sqlite", "postgresql"])
def auth_sessions(request, session_per_request):
    if request.param == "sqlite":
        yield session_per_request
        return

    url = os.getenv("BORG_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("BORG_TEST_POSTGRES_URL is not set")

    schema = f"auth_test_{uuid4().hex}"
    engine = create_engine(
        url, execution_options={"schema_translate_map": {None: schema}}
    )
    try:
        with engine.begin() as conn:
            conn.execute(CreateSchema(schema))
            Base.metadata.create_all(conn)
        session_per_request.configure(bind=engine)
        yield session_per_request
    finally:
        with engine.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True, if_exists=True))
        engine.dispose()


@pytest.mark.unit
@pytest.mark.parametrize(
    "second_username,second_email",
    [("alice", "other@example.org"), ("bob", "shared@example.org")],
    ids=["same-username", "same-email"],
)
def test_concurrent_proxy_first_login(
    test_client, auth_sessions, monkeypatch, second_username, second_email
):
    monkeypatch.setattr(settings, "disable_authentication", True)
    monkeypatch.setattr(settings, "proxy_auth_email_header", "X-Proxy-Email")
    emails = ["shared@example.org", second_email]
    both_inserting = Barrier(2, timeout=10)

    def meet_before_insert(session, flush_context, instances):
        # Only the first attempts use the supplied emails. A retry that
        # creates a different user with its fallback email proceeds directly.
        if any(isinstance(user, User) and user.email in emails for user in session.new):
            both_inserting.wait()

    def login(username, email):
        response = test_client.get(
            "/api/auth/me",
            headers={"X-Forwarded-User": username, "X-Proxy-Email": email},
        )
        assert response.status_code == 200
        return response.json()

    event.listen(auth_sessions, "before_flush", meet_before_insert)
    try:
        usernames = ["alice", second_username]
        with ThreadPoolExecutor(max_workers=2) as workers:
            responses = list(workers.map(login, usernames, emails))
    finally:
        event.remove(auth_sessions, "before_flush", meet_before_insert)

    assert [user["username"] for user in responses] == usernames
    with auth_sessions() as db:
        users = db.query(User).filter(User.username.in_(usernames)).all()
        assert {user.id for user in users} == {user["id"] for user in responses}
        assert len(users) == len(set(usernames))
        assert sum(user.email in emails for user in users) == 1
        for user in users:
            assert user.email in emails or user.email == f"{user.username}@proxy.local"


@pytest.mark.unit
def test_two_requests_can_stamp_the_same_personal_token(test_client, auth_sessions):
    raw_token = "borgui_" + "t" * 32
    with auth_sessions() as db:
        user = User(username="token-owner")
        db.add(user)
        db.flush()
        db.add(
            ApiToken(
                user_id=user.id,
                name="shared",
                prefix=raw_token[:12],
                token_hash=get_password_hash(raw_token),
            )
        )
        db.commit()

    both_stamping = Barrier(2, timeout=10)

    def meet_before_update(session, flush_context, instances):
        if any(isinstance(obj, ApiToken) for obj in session.dirty):
            both_stamping.wait()

    def list_tokens():
        response = test_client.get(
            "/api/settings/tokens", headers={"Authorization": f"Bearer {raw_token}"}
        )
        assert response.status_code == 200
        (token,) = response.json()
        assert token["last_used_at"] is not None

    commits = []

    def record_commit(session):
        commits.append(session)

    event.listen(auth_sessions, "after_commit", record_commit)
    event.listen(auth_sessions, "before_flush", meet_before_update)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            requests = [workers.submit(list_tokens) for _ in range(2)]
            for request in requests:
                request.result()
    finally:
        event.remove(auth_sessions, "before_flush", meet_before_update)
        event.remove(auth_sessions, "after_commit", record_commit)
    assert len(set(commits)) == 2
