"""Causal restore diagnostics stay inspectable without progress noise or secrets."""

import json

import pytest

from app.utils.restore_errors import restore_diagnostic, zero_file_restore_detail


@pytest.mark.unit
def test_borg_progress_and_info_do_not_replace_failure_cause():
    output = "\n".join(
        [
            json.dumps({"type": "progress_percent", "info": ["/restore/large-file"]}),
            json.dumps(
                {
                    "type": "log_message",
                    "levelname": "WARNING",
                    "message": "Permission denied password=private-secret",
                }
            ),
            json.dumps(
                {"type": "log_message", "levelname": "INFO", "message": "finished"}
            ),
            json.dumps({"type": "progress_percent", "finished": True}),
        ]
    )
    detail = zero_file_restore_detail(105, output)
    assert detail["params"]["error"] == "Permission denied password=***"
    assert "private-secret" not in json.dumps(detail)


@pytest.mark.unit
def test_long_quoted_secret_is_redacted_before_bounding():
    output = 'failure password="' + "secret " * 500 + '" final storage error'
    diagnostic = restore_diagnostic(output)
    assert diagnostic == 'failure password="***" final storage error'


@pytest.mark.unit
@pytest.mark.parametrize(
    "code,output,key",
    [
        (
            104,
            '{"type":"progress_percent","finished":true}',
            "restoreFailedZeroFilesNoOutput",
        ),
        (107, "requested archive item absent", "restoreFailedZeroFilesPathNotFound"),
        (1, "No such file or directory", "restoreFailedZeroFilesPathNotFound"),
    ],
)
def test_zero_file_failure_uses_actionable_existing_translation(code, output, key):
    detail = zero_file_restore_detail(code, output)
    assert detail["key"] == f"backend.errors.service.{key}" + (
        "Details" if "error" in detail["params"] else ""
    )
    assert detail["params"]["exitCode"] == code
