"""Friendly error text (plan Task 5)."""

import subprocess
import sys
from pathlib import Path

import pytest

from app.mcp.client import ApiError
from app.mcp.errors import backend_message, outcome_for, render_error

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.unit
def test_backend_message_fills_placeholders():
    assert backend_message("backend.errors.mcp.levelAboveCap", {"max": "operate"}) == (
        "Your administrator allows MCP connections up to operate access."
    )
    assert backend_message("backend.errors.nope.never", {}) is None


@pytest.mark.unit
def test_plan_refusal():
    exc = ApiError(
        403,
        "backend.errors.plan.featureNotAvailable",
        {"feature": "archive_history", "required": "pro", "current": "community"},
    )
    result = render_error(exc, tool="search_files")
    assert result.is_error
    assert (
        result.text
        == "Archive history is part of Borg UI Pro. This install is on Community."
    )


@pytest.mark.unit
def test_keyed_error_uses_backend_text():
    exc = ApiError(422, "backend.errors.mcp.skipNeedsFull")
    assert (
        render_error(exc, tool="x").text == "Skipping confirmations needs Full access."
    )
    unknown = ApiError(409, "backend.errors.repo.somethingNew")
    assert (
        render_error(unknown, tool="x").text
        == "Borg UI refused that (backend.errors.repo.somethingNew)."
    )


@pytest.mark.unit
def test_permission_and_not_found():
    assert "permission" in render_error(ApiError(403), tool="x").text
    assert (
        render_error(ApiError(404), tool="x").text
        == "I could not find that. It may have been removed."
    )


@pytest.mark.unit
def test_unexpected_errors_reveal_nothing(monkeypatch):
    reported = []
    monkeypatch.setattr(
        "app.mcp.errors.report_exception", lambda exc, **kw: reported.append(kw)
    )
    result = render_error(
        RuntimeError("db password=hunter2 exploded"), tool="get_overview"
    )
    assert "hunter2" not in result.text and "exploded" not in result.text
    assert result.text.startswith("Something went wrong inside Borg UI")
    assert reported == [{"kind": "request", "component": "mcp:get_overview"}]
    result = render_error(ApiError(500, message="Traceback..."), tool="x")
    assert "Traceback" not in result.text


@pytest.mark.unit
def test_outcomes():
    assert outcome_for(ApiError(403)) == ("denied_rbac", None)
    assert outcome_for(ApiError(403, "backend.errors.plan.featureNotAvailable")) == (
        "error",
        "backend.errors.plan.featureNotAvailable",
    )
    assert outcome_for(RuntimeError()) == ("error", None)


@pytest.mark.unit
def test_backend_strings_are_in_sync(tmp_path):
    script = ROOT / "scripts" / "extract_backend_strings.py"
    ok = subprocess.run(
        [sys.executable, str(script), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    stale = tmp_path / "strings.json"
    stale.write_text("{}")
    bad = subprocess.run(
        [sys.executable, str(script), "--check", "--output", str(stale)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert bad.returncode != 0
    assert "run scripts/extract_backend_strings.py" in bad.stdout + bad.stderr


@pytest.mark.unit
def test_keyed_server_errors_use_their_message(monkeypatch):
    monkeypatch.setattr("app.mcp.errors.report_exception", lambda exc, **kw: None)
    exc = ApiError(500, "backend.errors.repo.failedToListArchives")
    text = render_error(exc, tool="list_archives").text
    assert text == backend_message("backend.errors.repo.failedToListArchives", {})
    assert text and not text.startswith("Something went wrong")
