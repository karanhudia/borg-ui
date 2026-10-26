"""keep repository scripts running on existing multi-repository schedules

Revision ID: f7a4417c5d4d
Revises: c4e532c20d7b
Create Date: 2026-10-25

A multi-repository schedule with `run_repository_scripts` off ran its
repositories' own pre/post-backup scripts anyway: the backup ran them when
the schedule did not. That flag now means what it says, so off no longer
runs them. The schedule wizard defaults it to off, so existing schedules
whose repositories have scripts get it turned on here and keep running them.

A repository has scripts when it has an enabled pre- or post-backup hook
(library or agent script) or an inline pre- or post-backup script.

The downgrade leaves the flag as it is: with the older code, on runs the same
scripts that off did.
"""

import sqlalchemy as sa
from alembic import op

revision = "f7a4417c5d4d"
down_revision = "c4e532c20d7b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schedules = sa.table(
        "scheduled_jobs",
        sa.column("id", sa.Integer),
        sa.column("run_repository_scripts", sa.Boolean),
    )
    links = sa.table(
        "scheduled_job_repositories",
        sa.column("scheduled_job_id", sa.Integer),
        sa.column("repository_id", sa.Integer),
    )
    repositories = sa.table(
        "repositories",
        sa.column("id", sa.Integer),
        sa.column("pre_backup_script", sa.Text),
        sa.column("post_backup_script", sa.Text),
    )
    hooks = sa.table(
        "repository_scripts",
        sa.column("repository_id", sa.Integer),
        sa.column("hook_type", sa.String),
        sa.column("enabled", sa.Boolean),
    )

    def has_text(column):
        return sa.func.length(sa.func.trim(sa.func.coalesce(column, ""))) > 0

    has_hook = (
        sa.select(hooks.c.repository_id)
        .where(
            hooks.c.repository_id == repositories.c.id,
            hooks.c.enabled == sa.true(),
            hooks.c.hook_type.in_(("pre-backup", "post-backup")),
        )
        .exists()
    )
    with_scripts = (
        sa.select(links.c.scheduled_job_id)
        .join(repositories, repositories.c.id == links.c.repository_id)
        .where(
            sa.or_(
                has_hook,
                has_text(repositories.c.pre_backup_script),
                has_text(repositories.c.post_backup_script),
            )
        )
    )
    op.execute(
        schedules.update()
        .where(
            sa.or_(
                schedules.c.run_repository_scripts.is_(None),
                schedules.c.run_repository_scripts == sa.false(),
            ),
            schedules.c.id.in_(with_scripts),
        )
        .values(run_repository_scripts=True)
    )


def downgrade() -> None:
    pass
