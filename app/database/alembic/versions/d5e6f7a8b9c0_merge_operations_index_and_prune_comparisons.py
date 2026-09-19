"""merge the operations (kind, started_at) index with prune comparisons

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9, b4c5d6e7f8a9
Create Date: 2026-09-18

c4d5e6f7a8b9 (operations index) and b4c5d6e7f8a9 (prune comparisons)
were written against the same parent, a3b4c5d6e7f8. c4d5e6f7a8b9 keeps
that parent because installs have applied it under it: moving an applied
revision's parent makes Alembic treat such an install as up to date and
silently skip the other branch's DDL. This merge revision joins the two
heads instead, so an install at c4d5e6f7a8b9 upgrades through the prune
comparisons and a fresh install applies both branches in order.
"""

revision = "d5e6f7a8b9c0"
down_revision = ("c4d5e6f7a8b9", "b4c5d6e7f8a9")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
