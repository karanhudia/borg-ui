"""drop archive_changes raw-path indexes

The `path` column is unbounded Text. PostgreSQL caps a B-tree entry at about
a third of a page (~2.7 KB, measured after compressing the value), so indexing
the raw path makes the INSERT of a change row fail outright for a long archived
path that does not compress well - hash-heavy names, for example. archive_id
keeps its own index for per-archive reads; the repository-wide exact-path
lookup drives off that FK index and filters path.

The downgrade does not recreate the indexes. Once this revision has run the
table may hold paths beyond that limit, and CREATE INDEX over such rows fails
on PostgreSQL - a downgrade that can abort halfway is worse than one that
leaves two performance-only indexes absent. A reverted deployment stays
correct without them (exact-path lookups just lose their dedicated index).

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-09-04
"""

from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("archive_changes") as batch:
        batch.drop_index("ix_archive_changes_archive_path")
        batch.drop_index("ix_archive_changes_path")


def downgrade() -> None:
    # Deliberately no-op: rows with paths past the B-tree entry limit may exist
    # by now, and recreating either index over them fails on PostgreSQL.
    # See the module docstring.
    pass
