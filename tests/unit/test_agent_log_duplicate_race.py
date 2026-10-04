from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from sqlalchemy.exc import IntegrityError

from app.api import agents
from app.api.agents import AgentJobLogRequest


def _assert_lookup_key(db, *, job_id, sequence):
    """The post-rollback lookup (the second query) filters on this job and
    sequence, not just any stored row."""
    assert db.query.return_value.filter.call_count == 2
    conditions = db.query.return_value.filter.call_args_list[1].args
    assert [c.right.value for c in conditions] == [job_id, sequence]


def test_log_upload_losing_the_insert_race_is_a_duplicate():
    """The (job, sequence) pre-check passed, then the other request committed
    first: the unique constraint rejects this insert and the report is a
    redelivery, not a server error."""
    db = MagicMock()
    # Pre-check finds nothing; after the failed insert the other copy exists.
    db.query.return_value.filter.return_value.first.side_effect = [
        None,
        SimpleNamespace(id=9),
    ]
    db.commit.side_effect = IntegrityError("insert", {}, Exception("unique"))
    job = SimpleNamespace(id=1, payload={}, updated_at=None)

    with patch.object(agents, "_get_agent_job", return_value=job):
        response = agents.upload_job_log(
            1,
            AgentJobLogRequest(sequence=3, stream="stderr", message="x"),
            current_agent=SimpleNamespace(id=1),
            db=db,
        )

    assert response.accepted is True
    assert response.duplicate is True
    db.rollback.assert_called_once()
    _assert_lookup_key(db, job_id=1, sequence=3)


def test_integrity_error_without_a_stored_copy_is_not_acknowledged():
    """A foreign-key failure (job deleted meanwhile) must not be reported to
    the agent as a stored log."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [None, None]
    db.commit.side_effect = IntegrityError("insert", {}, Exception("fk"))
    job = SimpleNamespace(id=1, payload={}, updated_at=None)

    with patch.object(agents, "_get_agent_job", return_value=job):
        with pytest.raises(IntegrityError):
            agents.upload_job_log(
                1,
                AgentJobLogRequest(sequence=3, stream="stderr", message="x"),
                current_agent=SimpleNamespace(id=1),
                db=db,
            )
    _assert_lookup_key(db, job_id=1, sequence=3)
