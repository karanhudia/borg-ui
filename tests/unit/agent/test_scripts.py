from pathlib import Path

import pytest

from agent.borg_ui_agent.scripts import (
    ScriptNotAllowed,
    execute_script_run_job,
    list_allowed_scripts,
    resolve_allowed_script,
)


def _write_script(path: Path, body: str = "exit 0", mode: int = 0o755) -> Path:
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(mode)
    return path


class RecordingClient:
    """Captures the terminal/log calls the handler makes."""

    def __init__(self):
        self.logs: list[tuple[str, str]] = []
        self.calls: list[tuple] = []

    def send_log(self, job_id, *, sequence, stream, message):
        self.logs.append((stream, message))

    def send_progress(self, job_id, progress):
        self.calls.append(("progress", progress))

    def complete_job(self, job_id, *, result):
        self.calls.append(("complete", result))

    def fail_job(self, job_id, *, error_message, return_code=None):
        self.calls.append(("fail", error_message, return_code))

    def cancel_job(self, job_id):
        self.calls.append(("cancel",))


@pytest.fixture
def scripts_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BORG_UI_AGENT_SCRIPTS_DIR", str(tmp_path))
    return tmp_path


# --- listing ---------------------------------------------------------------


def test_list_allowed_scripts_only_executables_sorted(scripts_dir):
    _write_script(scripts_dir / "b-script.sh")
    _write_script(scripts_dir / "a-script.sh")
    _write_script(scripts_dir / "not-exec.sh", mode=0o644)
    (scripts_dir / "subdir").mkdir()

    names = [item["name"] for item in list_allowed_scripts()]

    assert names == ["a-script.sh", "b-script.sh"]


def test_list_allowed_scripts_parses_description(scripts_dir):
    _write_script(
        scripts_dir / "dump.sh",
        body="# borg-ui: Quiesce and dump the database\nexit 0",
    )

    [item] = list_allowed_scripts()

    assert item == {"name": "dump.sh", "description": "Quiesce and dump the database"}


def test_list_allowed_scripts_absent_dir_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("BORG_UI_AGENT_SCRIPTS_DIR", str(tmp_path / "missing"))
    assert list_allowed_scripts() == []


def test_list_allowed_scripts_handles_configmap_symlink_layout(scripts_dir):
    # Mimic a Kubernetes projected volume: real files under ..data snapshot,
    # each key a symlink through ..data.
    snapshot = scripts_dir / "..2026_07_08_data"
    snapshot.mkdir()
    _write_script(snapshot / "hook.sh")
    (scripts_dir / "..data").symlink_to(snapshot.name)
    (scripts_dir / "hook.sh").symlink_to(Path("..data") / "hook.sh")

    names = [item["name"] for item in list_allowed_scripts()]

    assert names == ["hook.sh"]  # ..data / ..2026_… snapshot are skipped


# --- resolution (the security boundary) ------------------------------------


def test_resolve_allowed_script_accepts_valid(scripts_dir):
    _write_script(scripts_dir / "ok.sh")
    resolved = resolve_allowed_script("ok.sh")
    assert resolved == (scripts_dir / "ok.sh").resolve()


def test_resolve_allowed_script_accepts_configmap_symlink(scripts_dir):
    snapshot = scripts_dir / "..2026_07_08_data"
    snapshot.mkdir()
    _write_script(snapshot / "hook.sh")
    (scripts_dir / "..data").symlink_to(snapshot.name)
    (scripts_dir / "hook.sh").symlink_to(Path("..data") / "hook.sh")

    resolved = resolve_allowed_script("hook.sh")
    assert resolved == (snapshot / "hook.sh").resolve()


@pytest.mark.parametrize(
    "name",
    [
        "../etc/passwd",
        "sub/script.sh",
        "..",
        ".",
        ".hidden",
        "",
        "   ",
    ],
)
def test_resolve_allowed_script_rejects_bad_names(scripts_dir, name):
    with pytest.raises(ScriptNotAllowed):
        resolve_allowed_script(name)


def test_resolve_allowed_script_rejects_absolute_path(scripts_dir):
    with pytest.raises(ScriptNotAllowed):
        resolve_allowed_script("/etc/passwd")


def test_resolve_allowed_script_rejects_symlink_escape(scripts_dir):
    outside = scripts_dir.parent / "outside.sh"
    _write_script(outside)
    (scripts_dir / "evil.sh").symlink_to(outside)

    with pytest.raises(ScriptNotAllowed):
        resolve_allowed_script("evil.sh")


def test_resolve_allowed_script_rejects_non_executable(scripts_dir):
    _write_script(scripts_dir / "plain.sh", mode=0o644)
    with pytest.raises(ScriptNotAllowed):
        resolve_allowed_script("plain.sh")


def test_resolve_allowed_script_rejects_missing(scripts_dir):
    with pytest.raises(ScriptNotAllowed):
        resolve_allowed_script("nope.sh")


# --- execution -------------------------------------------------------------


@pytest.mark.parametrize("rc", [0, 1, 2, 42])
def test_execute_reports_return_code_and_streams(scripts_dir, rc):
    _write_script(
        scripts_dir / "run.sh",
        body=f"echo out-line\necho err-line >&2\nexit {rc}",
    )
    client = RecordingClient()

    result = execute_script_run_job(
        {"id": 7, "payload": {"script": {"name": "run.sh"}}}, client
    )

    assert result.status == "completed"
    assert result.return_code == rc
    kind, payload = client.calls[-1][0], client.calls[-1][1]
    assert kind == "complete"
    assert payload["return_code"] == rc
    # stdout and stderr are kept strictly separate.
    assert "out-line" in payload["stdout"]
    assert "err-line" not in payload["stdout"]
    assert "err-line" in payload["stderr"]
    assert "out-line" not in payload["stderr"]


def test_execute_rejects_disallowed_name(scripts_dir):
    client = RecordingClient()

    result = execute_script_run_job(
        {"id": 9, "payload": {"script": {"name": "../escape.sh"}}}, client
    )

    assert result.status == "failed"
    assert client.calls[-1][0] == "fail"


def test_execute_passes_agent_env_and_context(scripts_dir, monkeypatch):
    # Allow-listed scripts are trusted and need the agent's own environment to do
    # their job (e.g. cluster DB dumps read DB_BACKUP_LOCATION), plus the server's
    # BORG_UI_* context layered on top.
    monkeypatch.setenv("DB_BACKUP_LOCATION", "/mnt/nfs/db-backup")
    _write_script(
        scripts_dir / "env.sh",
        body='echo "LOC=${DB_BACKUP_LOCATION:-none}"\necho "CTX=${BORG_UI_BACKUP_PLAN_ID:-none}"',
    )
    client = RecordingClient()

    execute_script_run_job(
        {
            "id": 11,
            "payload": {
                "script": {"name": "env.sh"},
                "env": {"BORG_UI_BACKUP_PLAN_ID": "42"},
            },
        },
        client,
    )

    stdout = client.calls[-1][1]["stdout"]
    assert "LOC=/mnt/nfs/db-backup" in stdout
    assert "CTX=42" in stdout


def test_execute_cancellation_terminates(scripts_dir):
    _write_script(scripts_dir / "sleep.sh", body="sleep 30")
    client = RecordingClient()

    result = execute_script_run_job(
        {"id": 13, "payload": {"script": {"name": "sleep.sh"}}},
        client,
        should_cancel=lambda: True,
    )

    assert result.status == "canceled"
    assert client.calls[-1][0] == "cancel"
