"""Upgrade test for revision f7a4417c5d4d (run_repository_scripts kept).

`run_repository_scripts` off used to run a multi-repository schedule's
repository scripts anyway; now off means off. From every release before the
revision, a schedule whose repositories have scripts gets the flag turned on,
so it keeps running them; every other schedule keeps the value it had.
"""

import pytest
from sqlalchemy.orm import Session

from app.database.models import ScheduledJob
from tests.migrations import upgrade_paths
from tests.migrations.conftest import DIALECTS, require_releases

REVISION = "f7a4417c5d4d"
RELEASES = upgrade_paths.releases_before(REVISION) or ["no-release-tags"]

INLINE, NONE, HOOK, DISABLED_HOOK, BLANK_INLINE = 701, 702, 703, 704, 705
SCRIPT = 710
# schedule id: (its repository, run_repository_scripts before, after)
SCHEDULES = {
    720: (INLINE, False, True),
    721: (NONE, False, False),
    722: (HOOK, False, True),
    723: (DISABLED_HOOK, False, False),
    724: (BLANK_INLINE, False, False),
    725: (NONE, True, True),
    726: (None, False, False),
}
ROWS = {
    "repositories": [
        {"id": INLINE, "pre_backup_script": "pg_dump app > /tmp/app.sql"},
        {"id": NONE, "pre_backup_script": None, "post_backup_script": None},
        {"id": HOOK, "pre_backup_script": None, "post_backup_script": None},
        {"id": DISABLED_HOOK, "pre_backup_script": None, "post_backup_script": None},
        {"id": BLANK_INLINE, "pre_backup_script": "  ", "post_backup_script": ""},
    ],
    "scripts": [{"id": SCRIPT}],
    "repository_scripts": [
        {
            "id": 711,
            "repository_id": HOOK,
            "script_id": SCRIPT,
            "hook_type": "post-backup",
            "enabled": True,
        },
        {
            "id": 712,
            "repository_id": DISABLED_HOOK,
            "script_id": SCRIPT,
            "hook_type": "pre-backup",
            "enabled": False,
        },
    ],
    "scheduled_jobs": [
        {"id": job_id, "name": f"schedule-{job_id}", "run_repository_scripts": before}
        for job_id, (_, before, _) in SCHEDULES.items()
    ],
    "scheduled_job_repositories": [
        {"scheduled_job_id": job_id, "repository_id": repo_id, "execution_order": 0}
        for job_id, (repo_id, _, _) in SCHEDULES.items()
        if repo_id is not None
    ],
}


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("release", RELEASES)
def test_schedules_whose_repositories_have_scripts_keep_running_them(
    release, dialect, upgraded_from
):
    require_releases()
    db = upgraded_from(release, dialect=dialect, rows=ROWS)

    with Session(db.engine) as session:
        flags = {
            job_id: session.get(ScheduledJob, job_id).run_repository_scripts
            for job_id in SCHEDULES
        }
    assert flags == {job_id: after for job_id, (_, _, after) in SCHEDULES.items()}
