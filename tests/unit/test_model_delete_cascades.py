"""An ORM delete must remove what the schema's foreign keys say goes with it.

A one-to-many relationship without a delete cascade makes the ORM null the
children's foreign key before it deletes the parent, so an `ON DELETE CASCADE`
in the schema never fires and the children stay behind as orphans."""

import pytest
from sqlalchemy.orm import ONETOMANY, configure_mappers

from app.database.models import (
    Base,
    BackupPlan,
    BackupPlanRun,
    BackupPlanRunRepository,
    ScriptExecution,
)


def _one_to_many_relationships():
    configure_mappers()
    for mapper in Base.registry.mappers:
        for rel in mapper.relationships:
            if rel.direction is ONETOMANY and not rel.viewonly:
                ondelete = {
                    fk.ondelete
                    for column in rel.remote_side
                    for fk in column.foreign_keys
                }
                yield f"{mapper.class_.__name__}.{rel.key}", rel, ondelete


@pytest.mark.unit
def test_orm_deletes_follow_the_schemas_foreign_keys():
    """Every relationship over an `ON DELETE CASCADE` key deletes its children
    (or leaves them to the database), and none over an `ON DELETE SET NULL`
    key deletes what the schema keeps."""
    mismatched = []
    for name, rel, ondelete in _one_to_many_relationships():
        if "CASCADE" in ondelete and not (rel.cascade.delete or rel.passive_deletes):
            mismatched.append(f"{name}: ON DELETE CASCADE, but the ORM nulls it")
        if "SET NULL" in ondelete and rel.cascade.delete:
            mismatched.append(f"{name}: ON DELETE SET NULL, but the ORM deletes it")
    assert mismatched == []


@pytest.mark.unit
def test_deleting_a_plan_run_deletes_its_hooks_and_repository_rows(test_db):
    """The plan run's children go with it through the ORM."""
    plan = BackupPlan(name="nightly", enabled=True, source_directories="[]")
    test_db.add(plan)
    test_db.commit()
    run = BackupPlanRun(backup_plan_id=plan.id, trigger="schedule", status="failed")
    test_db.add(run)
    test_db.commit()
    test_db.add(
        ScriptExecution(
            backup_plan_id=plan.id,
            backup_plan_run_id=run.id,
            hook_type="pre-backup",
            status="failed",
        )
    )
    test_db.add(BackupPlanRunRepository(backup_plan_run_id=run.id, status="failed"))
    test_db.commit()
    test_db.expire_all()

    test_db.delete(test_db.get(BackupPlanRun, run.id))
    test_db.commit()

    assert test_db.query(ScriptExecution).count() == 0
    assert test_db.query(BackupPlanRunRepository).count() == 0
