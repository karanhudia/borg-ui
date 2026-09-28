"""Observe the SQL statements one session issues."""

from contextlib import contextmanager

from sqlalchemy import event


@contextmanager
def session_cursor_listener(session, listener):
    """Run `listener` as a `before_cursor_execute` hook for the statements
    `session` sends while the block runs, and for no other connection.

    An engine listener alone also sees every other session on the engine. The
    test client's lifespan loops (operations runner, schedule checker,
    reconcile scheduler) open theirs on this test's engine through the
    patched `SessionLocal` aliases, and a tick that overlaps the measurement
    would land in the count."""
    engine = session.get_bind()
    connections = set()
    if session.in_transaction():
        connections.add(session.connection())

    def began(session_, transaction, connection):
        connections.add(connection)

    def filtered(conn, *args):
        if conn in connections:
            listener(conn, *args)

    event.listen(session, "after_begin", began)
    event.listen(engine, "before_cursor_execute", filtered)
    try:
        yield
    finally:
        event.remove(engine, "before_cursor_execute", filtered)
        event.remove(session, "after_begin", began)


def count_statements(db, request):
    """`(response, count)` for `request()`, a call on the test client that
    runs on the `db` session."""
    statements = []

    def count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    with session_cursor_listener(db, count):
        response = request()
    assert response.status_code == 200
    return response, len(statements)
