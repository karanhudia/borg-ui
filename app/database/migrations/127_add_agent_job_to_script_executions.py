"""Link agent-executed script hooks to their AgentJob for live log streaming.

Adds a nullable ``agent_job_id`` to ``script_executions``. For an agent-executed
hook, the agent streams its output line-by-line into ``agent_job_logs`` (keyed by
``agent_job_id``) while it runs; storing that id lets the log endpoint serve those
lines live before the terminal stdout/stderr are captured at completion.

Purely additive and idempotent: the column is nullable (NULL for every existing
row and for server-side executions) and added only if missing.
"""

from sqlalchemy import text


def _columns(connection, table):
    return connection.execute(text(f"PRAGMA table_info({table})")).fetchall()


def _has_table(connection, table):
    return bool(_columns(connection, table))


def _add_column_if_missing(connection, table, column, ddl_type):
    names = {row[1] for row in _columns(connection, table)}
    if column not in names:
        connection.execute(
            text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
        )


def upgrade(connection):
    if _has_table(connection, "script_executions"):
        _add_column_if_missing(
            connection, "script_executions", "agent_job_id", "INTEGER"
        )
        # Match the model's index=True so a DB provisioned via migrations has the
        # same schema as one built from Base.metadata.create_all. SQLAlchemy's
        # default name for an index=True column is ix_<table>_<column>.
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_script_executions_agent_job_id"
                " ON script_executions (agent_job_id)"
            )
        )


def downgrade(connection):
    # No downgrade: the column is nullable and additive.
    print("✓ Downgrade skipped for migration 127 (additive, non-destructive)")
