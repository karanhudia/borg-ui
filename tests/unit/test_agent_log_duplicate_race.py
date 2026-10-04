from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import IntegrityError

from app.api import agents
from app.api.agents import AgentJobLogRequest


def test_log_upload_losing_the_insert_race_is_a_duplicate():
    """The (job, sequence) pre-check passed, then the other request committed
    first: the unique constraint rejects this insert and the report is a
    redelivery, not a server error."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.commit.side_effect = IntegrityError("insert", {}, Exception("unique"))
    job = SimpleNamespace(id=1, payload={}, updated_at=None)

    with patch.object(agents, "_get_agent_job", return_value=job):
        response = agents.upload_job_log(
            1,
            AgentJobLogRequest(sequence=1, stream="stderr", message="x"),
            current_agent=SimpleNamespace(id=1),
            db=db,
        )

    assert response.accepted is True
    assert response.duplicate is True
    db.rollback.assert_called_once()
