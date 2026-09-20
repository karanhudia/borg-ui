"""Count the SQL statements one request issues."""

from sqlalchemy import event


def count_statements(db, request):
    """`(response, count)` for `request()`, a call on the test client.

    The client runs the app's background loops on the same engine (the
    operations runner ticks every 5 s), and the in-memory engine has one
    connection, so the listener cannot tell their statements from the
    request's. A tick that falls into a measurement can only add statements,
    so the request runs twice and the smaller count is its own."""
    counts = []
    engine = db.get_bind()
    for _ in range(2):
        statements = []

        def count(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", count)
        try:
            response = request()
        finally:
            event.remove(engine, "before_cursor_execute", count)
        assert response.status_code == 200
        counts.append(len(statements))
    return response, min(counts)
