"""merge repository size source with SSH host keys

Revision ID: c3d5e7f9a1b2
Revises: 8f2a4c6e1d3b, b7e1a3c95d84
Create Date: 2026-09-06

8f2a4c6e1d3b and the SSH host-key revisions (a1c9f4d27b60, b7e1a3c95d84)
were written against the same parent. 8f2a4c6e1d3b keeps that parent
because installs have applied it under it: moving an applied revision's
parent makes Alembic treat such an install as up to date and silently
skip the other branch's DDL. This merge revision joins the two heads
instead, so an install at 8f2a4c6e1d3b upgrades through the host-key
revisions and a fresh install applies both branches in order.
"""

revision = "c3d5e7f9a1b2"
down_revision = ("8f2a4c6e1d3b", "b7e1a3c95d84")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
