import json

import pytest
from fastapi import HTTPException

from app.services.restore_service import refusal_error_message
from app.utils.http_detail import detail_text

REFUSAL = {
    "key": "backend.errors.agents.capabilityMissing",
    "params": {"capability": "repository.restore"},
}


@pytest.mark.unit
def test_detail_text_keeps_the_params_of_a_refusal():
    text = detail_text(REFUSAL)
    assert "backend.errors.agents.capabilityMissing" in text
    assert "repository.restore" in text


@pytest.mark.unit
def test_detail_text_leaves_a_key_without_params_alone():
    assert detail_text({"key": "backend.errors.agents.agentOffline"}) == (
        "backend.errors.agents.agentOffline"
    )


@pytest.mark.unit
def test_detail_text_prefers_a_message_and_reads_plain_strings():
    assert detail_text({"message": "boom", "key": "k"}) == "boom"
    assert detail_text("plain") == "plain"


@pytest.mark.unit
def test_restore_stores_the_refusal_itself_so_the_ui_translates_its_params():
    stored = json.loads(refusal_error_message(HTTPException(409, detail=REFUSAL)))
    assert stored == REFUSAL


@pytest.mark.unit
def test_restore_wraps_a_refusal_that_is_only_text():
    stored = json.loads(refusal_error_message(HTTPException(500, detail="disk full")))
    assert stored == {
        "key": "backend.errors.restore.failedStartRestore",
        "params": {"error": "disk full"},
    }
