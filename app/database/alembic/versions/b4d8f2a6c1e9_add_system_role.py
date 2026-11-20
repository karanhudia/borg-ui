"""add system_role to backup_plans and repositories

Revision ID: b4d8f2a6c1e9
Revises: a9e3c7b1d5f2
Create Date: 2026-11-20

Marks the plan and repository Borg UI creates to protect its own host
("This machine", spec 2026-11-20-this-machine). One of each per role.
"""

from alembic import op
import sqlalchemy as sa

revision = "b4d8f2a6c1e9"
down_revision = "a9e3c7b1d5f2"
branch_labels = None
depends_on = None

TABLES = ("backup_plans", "repositories")


def upgrade() -> None:
    # Re-runnable statement by statement: SQLite DDL is not transactional
    # under Alembic, so each step checks what an interrupted run left.
    for table in TABLES:
        inspector = sa.inspect(op.get_bind())
        if "system_role" not in {c["name"] for c in inspector.get_columns(table)}:
            with op.batch_alter_table(table) as batch:
                batch.add_column(sa.Column("system_role", sa.String(), nullable=True))
        index = f"uq_{table}_system_role"
        inspector = sa.inspect(op.get_bind())
        if index not in {i["name"] for i in inspector.get_indexes(table)}:
            op.create_index(index, table, ["system_role"], unique=True)


def downgrade() -> None:
    for table in TABLES:
        op.drop_index(f"uq_{table}_system_role", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_column("system_role")
