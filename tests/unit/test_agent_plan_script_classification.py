"""The agent pre/post-script outcome contract: rc 0 ok, 1 warning, >1 fail."""

from app.services.backup_plan_execution_service import (
    _classify_agent_script_outcome,
)


def _classify(status, rc=None, error_message=None):
    outcome = {"status": status, "result": {} if rc is None else {"return_code": rc}}
    if error_message is not None:
        outcome["error_message"] = error_message
    return _classify_agent_script_outcome(
        outcome, hook_type="pre-backup", script_name="hook.sh"
    )


def test_return_code_zero_is_success():
    hook_ok, exec_status, message = _classify("completed", rc=0)
    assert hook_ok is True
    assert exec_status == "completed"
    assert message is None


def test_return_code_one_is_warning_but_not_fatal():
    hook_ok, exec_status, message = _classify("completed", rc=1)
    assert hook_ok is True  # backup still proceeds
    assert exec_status == "warning"
    assert "warning" in message


def test_return_code_two_is_failure():
    hook_ok, exec_status, message = _classify("completed", rc=2)
    assert hook_ok is False
    assert exec_status == "failed"
    assert "exit code 2" in message


def test_agent_failure_without_return_code_is_failure():
    hook_ok, exec_status, message = _classify("failed", error_message="agent offline")
    assert hook_ok is False
    assert exec_status == "failed"
    assert "agent offline" in message


def test_timeout_is_failure():
    hook_ok, exec_status, message = _classify("timeout")
    assert hook_ok is False
    assert exec_status == "failed"
    assert "timeout" in message
