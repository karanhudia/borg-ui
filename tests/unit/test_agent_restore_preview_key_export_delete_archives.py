"""#1425: the restore preview, the key export and a wipe's deletes on the agent.

The agent half runs its jobs against a stand-in Borg (a shell script that
records its command lines), so each job's own process handling is what is
tested. The server half queues the jobs, reads their answers and keeps the
refusals and the per-archive wipe of #1393 for agents without them.
"""

import asyncio
import json
import os
import stat
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from agent.borg_ui_agent.cancel import SELF_CANCELLING_JOB_KINDS
from agent.borg_ui_agent.repository_ops import (
    RepositoryOperationPayload,
    execute_repository_operation_job,
)
from agent.borg_ui_agent.runtime import JOB_HANDLERS, get_capabilities
from app.database.models import AgentJob, AgentJobLog, Repository
from app.services.agent_artifact_relay import agent_artifact_relay
from app.services.job_admission import (
    OPERATION_CLASS_REPOSITORY_READ,
    OPERATION_CLASS_REPOSITORY_WRITE,
    operation_class_for,
    operation_for_agent_job_kind,
)
from app.services.repository_executor import (
    REPOSITORY_OPERATION_CAPABILITIES,
    agent_failure_result,
)
from tests.unit.test_agent_repository_server_borg import (
    _admin,
    _agent,
    _agent_answers,
    _agent_jobs,
    _completed,
    _repo,
    _run_agent_wipe,
    _seed_agent_wipe,
)

NEW_KINDS = (
    "repository.restore_dry_run",
    "repository.key_export",
    "repository.delete_archives",
)
KEY = b"BORG_KEY 0123abcd\nhqlhbGdvcml0aG2mc2hhMjU2\n"


@pytest.fixture
def server_borg(monkeypatch):
    """Every Borg command the server starts itself (as in #1393's tests)."""
    calls: list[list[str]] = []

    async def record(*args, **kwargs):
        argv = [str(arg) for arg in args]
        if argv and "borg" in os.path.basename(argv[0]):
            calls.append(argv)
        raise OSError("no subprocesses in this test")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", record)
    return calls


# -- agent: command lines ----------------------------------------------------------


def _payload(job_kind, borg_version, operation=None):
    return RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": job_kind,
            "repository": {"path": "/agent/repo", "borg_version": borg_version},
            "operation": operation,
        }
    )


@pytest.mark.unit
class TestAgentCommands:
    def test_restore_dry_run_borg2(self):
        payload = _payload(
            "repository.restore_dry_run",
            2,
            {"archive": "daily", "paths": ["home/a", "folder with spaces"]},
        )

        assert payload.build_command() == [
            "borg2",
            "-r",
            "/agent/repo",
            "extract",
            "--dry-run",
            "--",
            "daily",
            "home/a",
            "folder with spaces",
        ]

    @pytest.mark.parametrize(
        "operation",
        [
            {"archive": "--help", "paths": ["home/a"]},
            {"archive": "daily", "paths": ["-odd"]},
        ],
    )
    def test_restore_dry_run_rejects_option_shaped_operands(self, operation):
        with pytest.raises(ValueError):
            _payload("repository.restore_dry_run", 2, operation).build_command()

    def test_restore_dry_run_borg1_without_paths(self):
        payload = _payload("repository.restore_dry_run", 1, {"archive": "a1"})

        assert payload.build_command() == [
            "borg",
            "--lock-wait",
            "180",
            "extract",
            "--dry-run",
            "--",
            "/agent/repo::a1",
        ]

    @pytest.mark.parametrize(
        "borg_version, expected",
        [
            (2, ["borg2", "-r", "/agent/repo", "key", "export"]),
            (1, ["borg", "key", "export", "--lock-wait", "180", "/agent/repo"]),
        ],
    )
    def test_key_export_writes_to_stdout(self, borg_version, expected):
        # no path argument: Borg writes the key to stdout
        assert _payload("repository.key_export", borg_version).build_command() == (
            expected
        )

    def test_borg1_key_export_takes_the_remote_path_after_the_subcommand(self):
        payload = RepositoryOperationPayload.from_job_payload(
            {
                "job_kind": "repository.key_export",
                "repository": {
                    "path": "ssh://host/./repo",
                    "borg_version": 1,
                    "remote_path": "borg1",
                },
            }
        )

        assert payload.build_command() == [
            "borg",
            "key",
            "export",
            "--lock-wait",
            "180",
            "--remote-path",
            "borg1",
            "ssh://host/./repo",
        ]

    @pytest.mark.parametrize(
        "borg_version, archives, expected",
        [
            (
                2,
                ["aid:11", "aid:22"],
                [
                    ["borg2", "-r", "/agent/repo", "delete", "--", "aid:11"],
                    ["borg2", "-r", "/agent/repo", "delete", "--", "aid:22"],
                ],
            ),
            (
                1,
                ["first", "second"],
                [
                    [
                        "borg",
                        "--lock-wait",
                        "180",
                        "delete",
                        "--",
                        "/agent/repo::first",
                    ],
                    [
                        "borg",
                        "--lock-wait",
                        "180",
                        "delete",
                        "--",
                        "/agent/repo::second",
                    ],
                ],
            ),
        ],
    )
    def test_delete_archives_runs_one_delete_per_archive(
        self, borg_version, archives, expected
    ):
        payload = _payload(
            "repository.delete_archives", borg_version, {"archives": archives}
        )

        assert [cmd for _, cmd in payload.delete_archives_commands()] == expected
        assert payload.build_command() == expected[0]

    @pytest.mark.parametrize(
        "operation",
        [
            None,
            {"archives": []},
            {"archives": "aid:11"},
            {"archives": ["aid:11", ""]},
            {"archives": ["aid:11", 7]},
            {"archives": ["aid:11", "aid:11"]},
        ],
    )
    def test_delete_archives_refuses_a_payload_without_a_clear_list(self, operation):
        client = _Client()

        result = execute_repository_operation_job(
            {
                "id": 5,
                "payload": {
                    "job_kind": "repository.delete_archives",
                    "repository": {"path": "/agent/repo", "borg_version": 2},
                    "operation": operation,
                },
            },
            client,
        )

        assert result.status == "failed"
        assert "Invalid repository operation payload" in result.message
        assert client.kinds() == ["send_log", "fail_job"]


@pytest.mark.unit
class TestAgentRegistries:
    def test_the_agent_offers_and_handles_the_new_kinds(self):
        capabilities = get_capabilities()
        for kind in NEW_KINDS:
            assert kind in capabilities
            assert JOB_HANDLERS[kind] is execute_repository_operation_job

    def test_the_long_kinds_report_their_own_cancel(self):
        assert "repository.restore_dry_run" in SELF_CANCELLING_JOB_KINDS
        assert "repository.delete_archives" in SELF_CANCELLING_JOB_KINDS
        assert "repository.key_export" in SELF_CANCELLING_JOB_KINDS


# -- agent: running the jobs -------------------------------------------------------


FAKE_BORG = """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_BORG_LOG"
case " $* " in
  *" key export"*)
    printf 'BORG_KEY 0123abcd\\nhqlhbGdvcml0aG2mc2hhMjU2\\n'
    if [ -n "$FAKE_BORG_KEY_RC" ]; then echo "key export broke" >&2; exit "$FAKE_BORG_KEY_RC"; fi
    exit 0 ;;
  *" --dry-run "*)
    echo "Include pattern 'nope' never matched." >&2
    exit "${FAKE_BORG_DRY_RC:-0}" ;;
  *" delete "*)
    for arg in "$@"; do last="$arg"; done
    if [ "$last" = "$FAKE_BORG_FAIL_ON" ] || [ "${last##*::}" = "$FAKE_BORG_FAIL_ON" ]; then
      echo "Archive $last does not exist" >&2; exit 2
    fi
    if [ "$last" = "$FAKE_BORG_WARN_ON" ] || [ "${last##*::}" = "$FAKE_BORG_WARN_ON" ]; then
      echo "warning: could not reclaim" >&2; exit 1
    fi
    exit 0 ;;
esac
exit 9
"""


@pytest.fixture
def fake_borg(tmp_path, monkeypatch):
    script = tmp_path / "borg"
    script.write_text(FAKE_BORG)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.log"
    log.write_text("")
    monkeypatch.setenv("FAKE_BORG_LOG", str(log))
    for name in (
        "FAKE_BORG_KEY_RC",
        "FAKE_BORG_DRY_RC",
        "FAKE_BORG_FAIL_ON",
        "FAKE_BORG_WARN_ON",
    ):
        monkeypatch.delenv(name, raising=False)
    return SimpleNamespace(
        path=str(script),
        calls=lambda: [line for line in log.read_text().splitlines() if line],
    )


class _Client:
    """Records every report with all of its fields."""

    def __init__(self, *, upload=None, cancel_after=None):
        self.calls = []
        self._upload = upload
        self._cancel_after = cancel_after

    def kinds(self):
        return [call[0] for call in self.calls]

    def send_log(self, job_id, *, sequence, message, stream="stdout"):
        self.calls.append(("send_log", stream, message))
        return {"accepted": True}

    def send_progress(self, job_id, progress):
        self.calls.append(("send_progress", progress))
        return {}

    def complete_job(self, job_id, *, result):
        self.calls.append(("complete_job", result))
        return {}

    def fail_job(self, job_id, *, error_message, **report):
        self.calls.append(("fail_job", error_message, report))
        return {}

    def cancel_job(self, job_id):
        self.calls.append(("cancel_job",))
        return {}

    def upload_artifact(self, job_id, data):
        body = b""
        while True:
            chunk = data.read(65536)
            if not chunk:
                break
            body += chunk
        self.calls.append(("upload_artifact", body))
        return self._upload if self._upload is not None else {"accepted": True}


def _run(fake_borg, job_kind, operation=None, *, client=None, borg_version=1, **kw):
    client = client or _Client()
    result = execute_repository_operation_job(
        {
            "id": 7,
            "payload": {
                "job_kind": job_kind,
                "repository": {
                    "path": "/agent/repo",
                    "borg_version": borg_version,
                    "borg_binary": fake_borg.path,
                },
                "operation": operation or {},
            },
        },
        client,
        **kw,
    )
    return result, client


def _everything_but_the_upload(client):
    return repr([call for call in client.calls if call[0] != "upload_artifact"])


@pytest.mark.unit
class TestAgentKeyExport:
    def test_the_key_goes_out_as_the_upload_only(self, fake_borg):
        result, client = _run(fake_borg, "repository.key_export")

        assert result.status == "completed"
        assert ("upload_artifact", KEY) in client.calls
        # no log line, no completion report carries any of it
        assert "BORG_KEY" not in _everything_but_the_upload(client)
        assert "hqlhbG" not in _everything_but_the_upload(client)
        (complete,) = [c for c in client.calls if c[0] == "complete_job"]
        assert complete[1]["artifact"] is True
        assert set(complete[1]) == {"return_code", "command", "artifact"}
        assert fake_borg.calls() == ["key export --lock-wait 180 /agent/repo"]

    def test_a_failed_export_fails_and_leaks_nothing(self, fake_borg, monkeypatch):
        monkeypatch.setenv("FAKE_BORG_KEY_RC", "2")

        result, client = _run(fake_borg, "repository.key_export")

        assert result.status == "failed"
        (fail,) = [c for c in client.calls if c[0] == "fail_job"]
        assert "exited with code 2" in fail[1]
        assert "key export broke" in fail[2]["stderr_tail"]
        assert "BORG_KEY" not in _everything_but_the_upload(client)


@pytest.mark.unit
class TestAgentRestoreDryRun:
    def test_reports_borg_output_and_completes_on_a_warning(
        self, fake_borg, monkeypatch
    ):
        monkeypatch.setenv("FAKE_BORG_DRY_RC", "1")

        result, client = _run(
            fake_borg,
            "repository.restore_dry_run",
            {"archive": "a1", "paths": ["nope"]},
        )

        assert result.status == "completed_with_warnings"
        (complete,) = [c for c in client.calls if c[0] == "complete_job"]
        assert complete[1]["return_code"] == 1
        assert complete[1]["output"] == "Include pattern 'nope' never matched."
        assert fake_borg.calls() == [
            "--lock-wait 180 extract --dry-run -- /agent/repo::a1 nope"
        ]

    def test_an_error_fails_the_preview(self, fake_borg, monkeypatch):
        monkeypatch.setenv("FAKE_BORG_DRY_RC", "2")

        result, client = _run(
            fake_borg, "repository.restore_dry_run", {"archive": "a1"}
        )

        assert result.status == "failed"
        assert "complete_job" not in client.kinds()

    def test_a_cancel_before_the_start_runs_nothing(self, fake_borg):
        result, client = _run(
            fake_borg,
            "repository.restore_dry_run",
            {"archive": "a1"},
            should_cancel=lambda: True,
        )

        assert result.status == "canceled"
        assert fake_borg.calls() == []


@pytest.mark.unit
class TestAgentDeleteArchives:
    def test_deletes_every_archive_and_notes_a_warning(self, fake_borg, monkeypatch):
        monkeypatch.setenv("FAKE_BORG_WARN_ON", "second")

        result, client = _run(
            fake_borg,
            "repository.delete_archives",
            {"archives": ["first", "second", "third"]},
        )

        assert result.status == "completed_with_warnings"
        assert fake_borg.calls() == [
            "--lock-wait 180 delete -- /agent/repo::first",
            "--lock-wait 180 delete -- /agent/repo::second",
            "--lock-wait 180 delete -- /agent/repo::third",
        ]
        (complete,) = [c for c in client.calls if c[0] == "complete_job"]
        assert complete[1]["return_code"] == 1
        assert complete[1]["deleted_archives"] == 3
        assert complete[1]["warnings"] == [
            {
                "archive": "second",
                "return_code": 1,
                "stderr": "warning: could not reclaim",
            }
        ]
        logs = [c[2] for c in client.calls if c[0] == "send_log"]
        assert "Deleted archive third (3/3)" in logs

    def test_stops_at_the_first_failure_and_says_how_many_went(
        self, fake_borg, monkeypatch
    ):
        monkeypatch.setenv("FAKE_BORG_FAIL_ON", "aid:22")

        result, client = _run(
            fake_borg,
            "repository.delete_archives",
            {"archives": ["aid:11", "aid:22", "aid:33"]},
            borg_version=2,
        )

        assert result.status == "failed"
        # the third archive is never touched
        assert fake_borg.calls() == [
            "-r /agent/repo delete -- aid:11",
            "-r /agent/repo delete -- aid:22",
        ]
        (fail,) = [c for c in client.calls if c[0] == "fail_job"]
        assert "deleting archive aid:22 exited with code 2" in fail[1]
        assert "1 of 3 archives were deleted" in fail[1]
        assert fail[2]["deleted_archives"] == 1
        assert fail[2]["return_code"] == 2
        assert "does not exist" in fail[2]["stderr_tail"]

    def test_a_cancel_between_archives_starts_no_other(self, fake_borg):
        asked = []

        def should_cancel():
            # the start check, then the first archive's checks; then cancel
            asked.append(True)
            return len(fake_borg.calls()) >= 1

        result, client = _run(
            fake_borg,
            "repository.delete_archives",
            {"archives": ["first", "second"]},
            should_cancel=should_cancel,
        )

        assert result.status == "canceled"
        assert fake_borg.calls() == ["--lock-wait 180 delete -- /agent/repo::first"]
        assert client.kinds()[-1] == "cancel_job"
        assert "1 of 2" in result.message


@pytest.mark.unit
def test_the_failure_report_carries_the_deleted_count():
    from agent.borg_ui_agent.client import AgentClient

    sent = {}
    client = AgentClient("https://borgui.example.com", agent_token="t")
    client._request = lambda method, path, json=None: sent.update(json) or {}

    client.fail_job(1, error_message="x", return_code=2, deleted_archives=4)

    assert sent["deleted_archives"] == 4


@pytest.mark.unit
def test_the_session_transport_carries_the_deleted_count():
    import queue

    from agent.borg_ui_agent.session import SessionCommandClient

    sent = []

    class Http:
        def fail_job(self, job_id, **report):
            sent.append(report)

    client = SessionCommandClient(
        command_id="cmd-1", job_id=7, outbox=queue.Queue(), http_client=Http()
    )

    client.fail_job(7, error_message="boom", return_code=2, deleted_archives=1)
    client.fail_job(7, error_message="boom", return_code=2)

    assert sent[0]["deleted_archives"] == 1
    # a failure that counts nothing reports as before
    assert "deleted_archives" not in sent[1]


# -- server: registries ------------------------------------------------------------


@pytest.mark.unit
class TestServerRegistries:
    def test_the_kinds_are_queueable(self):
        for kind in NEW_KINDS:
            assert kind in REPOSITORY_OPERATION_CAPABILITIES

    def test_admission_classes(self):
        def cls(kind):
            return operation_class_for(operation_for_agent_job_kind(kind))

        # the deletes hold the repository like one archive's delete
        assert cls("repository.delete_archives") == OPERATION_CLASS_REPOSITORY_WRITE
        assert cls("repository.restore_dry_run") == OPERATION_CLASS_REPOSITORY_READ
        assert cls("repository.key_export") == OPERATION_CLASS_REPOSITORY_READ

    def test_the_request_scoped_kinds_are_not_rerun(self):
        from app.api.agents import REQUEST_SCOPED_REPOSITORY_JOB_KINDS

        # the dry run and the key export answer a request; a rerun of a
        # wipe's deletes would start over at archives already deleted
        for kind in NEW_KINDS:
            assert kind in REQUEST_SCOPED_REPOSITORY_JOB_KINDS

    def test_a_failure_keeps_a_deleted_count(self):
        assert agent_failure_result(2, deleted_archives=3) == {
            "return_code": 2,
            "deleted_archives": 3,
        }
        assert "deleted_archives" not in agent_failure_result(2, deleted_archives=-1)


def _with_capabilities(db, agent, *kinds):
    agent.capabilities = [*agent.capabilities, *kinds]
    db.commit()
    return agent


@pytest.mark.unit
def test_the_fail_route_stores_the_deleted_count(test_client, test_db):
    from app.core.security import get_password_hash

    agent = _agent(test_db)
    agent.token_hash = get_password_hash("borgui_agent_secret")
    test_db.commit()
    repo = _repo(test_db, agent)
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="repository",
        status="running",
        payload={"job_kind": "repository.delete_archives", "repository": {}},
    )
    test_db.add(job)
    test_db.commit()

    response = test_client.post(
        f"/api/agents/jobs/{job.id}/fail",
        json={"error_message": "x", "return_code": 2, "deleted_archives": 1},
        headers={"X-Borg-Agent-Authorization": "Bearer borgui_agent_secret"},
    )

    assert response.status_code == 200, response.text
    test_db.expire_all()
    assert test_db.get(AgentJob, job.id).result["deleted_archives"] == 1
    assert repo.id


# -- server: restore preview --------------------------------------------------------


def _preview(
    test_client,
    admin_headers,
    repo,
    paths=("data",),
    archive=None,
    destination="/restore",
):
    return test_client.post(
        "/api/restore/preview",
        json={
            "repository": repo.path,
            "repository_id": repo.id,
            "archive": archive or "aid:" + "a" * 64,
            "paths": list(paths),
            "destination": destination,
        },
        headers=admin_headers,
    )


@pytest.mark.unit
class TestRestorePreview:
    @pytest.mark.parametrize("archive", ["aid:" + "a" * 64, "a" * 64])
    def test_runs_the_dry_run_on_the_agent(
        self, test_client, admin_headers, test_db, server_borg, archive
    ):
        agent = _with_capabilities(
            test_db, _agent(test_db), "repository.restore_dry_run"
        )
        repo = _repo(test_db, agent)

        with (
            patch("app.api.restore.dispatch_agent_job_best_effort", new=AsyncMock()),
            patch(
                "app.api.restore.wait_for_agent_repository_operation_job",
                new=AsyncMock(
                    return_value={"return_code": 1, "output": "never matched"}
                ),
            ),
        ):
            response = _preview(test_client, admin_headers, repo, archive=archive)

        assert server_borg == []
        assert response.status_code == 200, response.text
        assert response.json() == {"preview": "never matched"}
        (job,) = _agent_jobs(test_db, "repository.restore_dry_run")
        # a bare Borg 2 id is addressed as `aid:`, as for a download
        assert job.payload["operation"]["archive"] == "aid:" + "a" * 64
        assert job.payload["operation"]["paths"] == ["data"]
        assert job.agent_machine_id == agent.id

    def test_an_older_agent_keeps_the_refusal(
        self, test_client, admin_headers, test_db, server_borg
    ):
        repo = _repo(test_db, _agent(test_db))

        response = _preview(test_client, admin_headers, repo)

        assert server_borg == []
        assert response.status_code == 400, response.text
        assert response.json()["detail"]["key"] == (
            "backend.errors.restore.agentPreviewUnsupported"
        )
        assert _agent_jobs(test_db) == []

    def test_a_failed_dry_run_answers_with_borgs_reason(
        self, test_client, admin_headers, test_db, server_borg
    ):
        agent = _with_capabilities(
            test_db, _agent(test_db), "repository.restore_dry_run"
        )
        repo = _repo(test_db, agent)
        failure = HTTPException(
            status_code=502,
            detail={
                "key": "backend.errors.agents.repositoryOperationFailedWithReason",
                "params": {"reason": "Archive does not exist"},
            },
        )

        with (
            patch("app.api.restore.dispatch_agent_job_best_effort", new=AsyncMock()),
            patch(
                "app.api.restore.wait_for_agent_repository_operation_job",
                new=_agent_answers(test_db, failure),
            ),
        ):
            response = _preview(test_client, admin_headers, repo)

        assert response.status_code == 502, response.text
        assert response.json()["detail"]["params"]["reason"] == (
            "Archive does not exist"
        )

    def test_a_wait_that_gives_up_takes_the_job_back(
        self, test_client, admin_headers, test_db, server_borg
    ):
        agent = _with_capabilities(
            test_db, _agent(test_db), "repository.restore_dry_run"
        )
        repo = _repo(test_db, agent)
        timeout = HTTPException(
            status_code=504,
            detail={"key": "backend.errors.agents.repositoryOperationTimeout"},
        )

        with (
            patch("app.api.restore.dispatch_agent_job_best_effort", new=AsyncMock()),
            patch(
                "app.api.restore.wait_for_agent_repository_operation_job",
                new=AsyncMock(side_effect=timeout),
            ),
        ):
            response = _preview(test_client, admin_headers, repo)

        assert response.status_code == 504, response.text
        (job,) = _agent_jobs(test_db, "repository.restore_dry_run")
        # never claimed: cancelled, so it blocks nothing and never runs
        assert job.status == "canceled"


# -- server repository: restore preview --------------------------------------------


@pytest.fixture
def server_runs_fake_borg(fake_borg, monkeypatch):
    """The server's own Borg 1 and Borg 2 are the stand-in Borg."""
    from app.core.borg import borg
    from app.core.borg2 import borg2

    monkeypatch.setattr(borg, "borg_cmd", fake_borg.path)
    monkeypatch.setattr(borg2, "borg_cmd", fake_borg.path)
    return fake_borg


def _server_repo(db, borg_version):
    repo = Repository(
        name=f"server-v{borg_version}",
        path=f"/repos/server-v{borg_version}",
        encryption="none",
        repository_type="local",
        borg_version=borg_version,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


def _agent_preview_answer(fake_borg, borg_version):
    """What the preview route answers for an agent repository after the
    agent's dry run against the same stand-in Borg."""
    result, client = _run(
        fake_borg,
        "repository.restore_dry_run",
        {"archive": "a1", "paths": ["nope"]},
        borg_version=borg_version,
    )
    (complete,) = [c for c in client.calls if c[0] == "complete_job"]
    return result, {"preview": complete[1].get("output") or ""}


@pytest.mark.unit
class TestServerRestorePreview:
    # Borg 1 warns with the legacy rc 1, Borg 2 with a modern warning code
    @pytest.mark.parametrize("borg_version, warning_rc", [(1, "1"), (2, "101")])
    def test_a_warning_answers_as_the_agent_path_does(
        self,
        test_client,
        admin_headers,
        test_db,
        server_runs_fake_borg,
        tmp_path,
        monkeypatch,
        borg_version,
        warning_rc,
    ):
        monkeypatch.setenv("FAKE_BORG_DRY_RC", warning_rc)
        agent_result, agent_answer = _agent_preview_answer(
            server_runs_fake_borg, borg_version
        )
        repo = _server_repo(test_db, borg_version)
        destination = tmp_path / "not-there-yet"

        response = _preview(
            test_client,
            admin_headers,
            repo,
            paths=["nope"],
            archive="a1",
            destination=str(destination),
        )

        assert agent_result.status == "completed_with_warnings"
        assert response.status_code == 200, response.text
        assert response.json() == agent_answer
        assert response.json() == {"preview": "Include pattern 'nope' never matched."}
        # a dry run writes nothing, and needs no destination
        assert not destination.exists()

    @pytest.mark.parametrize("borg_version", [1, 2])
    def test_a_missing_destination_does_not_stop_the_dry_run(
        self,
        test_client,
        admin_headers,
        test_db,
        server_runs_fake_borg,
        tmp_path,
        borg_version,
    ):
        _, agent_answer = _agent_preview_answer(server_runs_fake_borg, borg_version)
        repo = _server_repo(test_db, borg_version)
        destination = tmp_path / "not-there-yet"

        response = _preview(
            test_client,
            admin_headers,
            repo,
            paths=["nope"],
            archive="a1",
            destination=str(destination),
        )

        assert response.status_code == 200, response.text
        assert response.json() == agent_answer
        # the agent's run and the server's
        assert len(server_runs_fake_borg.calls()) == 2
        assert not destination.exists()

    @pytest.mark.parametrize("borg_version", [1, 2])
    def test_an_error_fails_the_preview_with_borgs_reason(
        self,
        test_client,
        admin_headers,
        test_db,
        server_runs_fake_borg,
        monkeypatch,
        borg_version,
    ):
        monkeypatch.setenv("FAKE_BORG_DRY_RC", "2")
        agent_result, _ = _run(
            server_runs_fake_borg,
            "repository.restore_dry_run",
            {"archive": "a1", "paths": ["nope"]},
            borg_version=borg_version,
        )
        repo = _server_repo(test_db, borg_version)

        response = _preview(
            test_client, admin_headers, repo, paths=["nope"], archive="a1"
        )

        assert agent_result.status == "failed"
        assert response.status_code == 500, response.text
        assert response.json()["detail"] == {
            "key": "backend.errors.restore.failedPreviewRestoreWithReason",
            "params": {"reason": "Include pattern 'nope' never matched."},
        }

    @pytest.mark.parametrize("borg_version", [1, 2])
    def test_a_borg_that_cannot_start_fails_the_preview(
        self, test_client, admin_headers, test_db, tmp_path, monkeypatch, borg_version
    ):
        from app.core.borg import borg
        from app.core.borg2 import borg2

        missing = str(tmp_path / "no-borg-here")
        monkeypatch.setattr(borg, "borg_cmd", missing)
        monkeypatch.setattr(borg2, "borg_cmd", missing)
        repo = _server_repo(test_db, borg_version)

        response = _preview(test_client, admin_headers, repo, archive="a1")

        assert response.status_code == 500, response.text
        detail = response.json()["detail"]
        assert detail["key"] == "backend.errors.restore.failedPreviewRestoreWithReason"
        assert "no-borg-here" in detail["params"]["reason"]


# -- server: key export -------------------------------------------------------------


def _keyed_repo(db, *, capable=True, **kw):
    agent = _agent(db)
    if capable:
        _with_capabilities(db, agent, "repository.key_export")
    kw.setdefault("has_keyfile", True)
    return _repo(db, agent, path="/repos/keyed", **kw)


def _agent_streams(db, chunks, *, outcome="completed"):
    """A dispatch that plays the agent: it uploads `chunks` through the
    relay, then reports the job's outcome."""

    async def dispatch(_db, agent_job, **_kwargs):
        for chunk in chunks:
            await agent_artifact_relay.push(agent_job.id, chunk)
        await agent_artifact_relay.close(agent_job.id)
        job = db.get(AgentJob, agent_job.id)
        job.status = outcome
        job.result = {"return_code": 0 if outcome == "completed" else 2}
        if outcome == "failed":
            job.error_message = "repository.key_export exited with code 2"
        db.commit()

    return AsyncMock(side_effect=dispatch)


@pytest.mark.unit
class TestKeyExport:
    def test_the_key_comes_from_the_agent_and_stays_off_the_record(
        self, test_client, admin_headers, test_db, server_borg, tmp_path, monkeypatch
    ):
        import tempfile

        repo = _keyed_repo(test_db)
        # the server's own export goes through a temporary file; this one
        # must not, so every temporary file lands where it is watched
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
        before = set(os.listdir(tmp_path))

        with patch(
            "app.services.agent_key_export.dispatch_agent_job_best_effort",
            new=_agent_streams(test_db, [KEY[:10], KEY[10:]]),
        ):
            response = test_client.get(
                f"/api/repositories/{repo.id}/keyfile", headers=admin_headers
            )

        assert server_borg == []
        assert response.status_code == 200, response.text
        assert response.content == KEY
        assert response.headers["content-type"].startswith("text/plain")
        assert 'filename="repos_keyed"' in response.headers["content-disposition"]
        (job,) = _agent_jobs(test_db, "repository.key_export")
        assert "BORG_KEY" not in json.dumps(job.payload)
        assert "BORG_KEY" not in json.dumps(job.result)
        assert test_db.query(AgentJobLog).count() == 0
        assert set(os.listdir(tmp_path)) == before
        assert not agent_artifact_relay.is_registered(job.id)

    @pytest.mark.parametrize(
        "encryption", ["keyfile", "keyfile-blake2", "keyfile-chacha20-poly1305"]
    )
    def test_an_agent_keyfile_repository_offers_its_key(
        self, test_client, admin_headers, test_db, server_borg, encryption
    ):
        # created through the agent: the server holds no keyfile, the
        # encryption mode says there is one on the agent's machine
        repo = _keyed_repo(test_db, has_keyfile=False)
        repo.encryption = encryption
        test_db.commit()

        listed = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)
        with patch(
            "app.services.agent_key_export.dispatch_agent_job_best_effort",
            new=_agent_streams(test_db, [KEY]),
        ):
            response = test_client.get(
                f"/api/repositories/{repo.id}/keyfile", headers=admin_headers
            )

        assert listed.json()["repository"]["has_keyfile"] is True
        assert response.status_code == 200, response.text
        assert response.content == KEY

    @pytest.mark.parametrize("route", ["detail", "list"])
    def test_an_older_agent_offers_no_key_download(
        self, test_client, admin_headers, test_db, server_borg, route
    ):
        # the info dialog shows its button by `has_keyfile`; an agent that
        # cannot export the key would only answer it with a refusal
        old = _keyed_repo(test_db, capable=False, has_keyfile=True)
        old.encryption = "keyfile"
        test_db.commit()

        if route == "detail":
            response = test_client.get(
                f"/api/repositories/{old.id}", headers=admin_headers
            )
            payload = response.json()["repository"]
        else:
            response = test_client.get("/api/repositories/", headers=admin_headers)
            (payload,) = [
                r for r in response.json()["repositories"] if r["id"] == old.id
            ]

        assert response.status_code == 200, response.text
        assert payload["has_keyfile"] is False

    def test_the_list_offers_the_key_of_a_capable_agent(
        self, test_client, admin_headers, test_db, server_borg
    ):
        repo = _keyed_repo(test_db, has_keyfile=False)
        repo.encryption = "keyfile-aes-ocb"
        test_db.commit()

        response = test_client.get("/api/repositories/", headers=admin_headers)

        assert response.status_code == 200, response.text
        (payload,) = [r for r in response.json()["repositories"] if r["id"] == repo.id]
        assert payload["has_keyfile"] is True

    def test_an_agent_repokey_repository_has_no_keyfile(
        self, test_client, admin_headers, test_db, server_borg
    ):
        repo = _keyed_repo(test_db, has_keyfile=False)
        repo.encryption = "repokey-blake2"
        test_db.commit()

        response = test_client.get(
            f"/api/repositories/{repo.id}/keyfile", headers=admin_headers
        )

        assert response.status_code == 404, response.text
        assert _agent_jobs(test_db) == []

    def test_a_job_that_fails_before_uploading_answers_at_once(
        self, test_client, admin_headers, test_db, server_borg
    ):
        repo = _keyed_repo(test_db)

        async def fails_to_start(_db, agent_job, **_kwargs):
            job = test_db.get(AgentJob, agent_job.id)
            job.status = "failed"
            job.error_message = "Failed to start repository.key_export: no borg"
            test_db.commit()

        with patch(
            "app.services.agent_key_export.dispatch_agent_job_best_effort",
            new=AsyncMock(side_effect=fails_to_start),
        ):
            response = test_client.get(
                f"/api/repositories/{repo.id}/keyfile", headers=admin_headers
            )

        # the reason, not a timeout after the first-byte wait
        assert response.status_code == 502, response.text
        assert "no borg" in response.json()["detail"]["params"]["reason"]
        (job,) = _agent_jobs(test_db, "repository.key_export")
        assert not agent_artifact_relay.is_registered(job.id)

    def test_an_older_agent_keeps_the_refusal(
        self, test_client, admin_headers, test_db, server_borg
    ):
        repo = _keyed_repo(test_db, capable=False)

        response = test_client.get(
            f"/api/repositories/{repo.id}/keyfile", headers=admin_headers
        )

        assert server_borg == []
        assert response.status_code == 400, response.text
        assert response.json()["detail"]["key"] == (
            "backend.errors.repo.agentKeyfileExportUnsupported"
        )
        assert _agent_jobs(test_db) == []

    def test_a_failed_job_hands_out_nothing(
        self, test_client, admin_headers, test_db, server_borg
    ):
        repo = _keyed_repo(test_db)

        with patch(
            "app.services.agent_key_export.dispatch_agent_job_best_effort",
            # the bytes Borg wrote before it failed are no key
            new=_agent_streams(test_db, [KEY[:10]], outcome="failed"),
        ):
            response = test_client.get(
                f"/api/repositories/{repo.id}/keyfile", headers=admin_headers
            )

        assert response.status_code == 502, response.text
        assert b"BORG_KEY" not in response.content

    def test_an_upload_larger_than_a_key_is_refused(
        self, test_client, admin_headers, test_db, server_borg
    ):
        from app.services.agent_key_export import MAX_KEY_EXPORT_BYTES

        repo = _keyed_repo(test_db)

        with patch(
            "app.services.agent_key_export.dispatch_agent_job_best_effort",
            new=_agent_streams(test_db, [b"x" * (MAX_KEY_EXPORT_BYTES + 1)]),
        ):
            response = test_client.get(
                f"/api/repositories/{repo.id}/keyfile", headers=admin_headers
            )

        assert response.status_code == 502, response.text
        (job,) = _agent_jobs(test_db, "repository.key_export")
        assert not agent_artifact_relay.is_registered(job.id)

    def test_no_first_byte_takes_the_job_back(
        self, test_client, admin_headers, test_db, server_borg
    ):
        repo = _keyed_repo(test_db)

        with (
            patch(
                "app.services.agent_key_export.dispatch_agent_job_best_effort",
                new=AsyncMock(),
            ),
            patch(
                "app.api.repositories.get_operation_timeouts",
                return_value={"info_timeout": 0.05},
            ),
        ):
            response = test_client.get(
                f"/api/repositories/{repo.id}/keyfile", headers=admin_headers
            )

        assert response.status_code == 504, response.text
        (job,) = _agent_jobs(test_db, "repository.key_export")
        assert job.status == "canceled"
        assert not agent_artifact_relay.is_registered(job.id)


# -- server: the wipe's deletes in one job ---------------------------------------------


@pytest.mark.unit
class TestWipeInOneJob:
    @pytest.mark.asyncio
    async def test_one_job_names_every_confirmed_archive(self, test_db, server_borg):
        from app.services.operations.wipe_facade import resolve_wipe_job

        agent = _with_capabilities(
            test_db, _agent(test_db), "repository.delete_archives"
        )
        repo = _repo(test_db, agent)
        wipe = _seed_agent_wipe(test_db, repo, _admin(test_db), archive_count=3)
        wait = _agent_answers(test_db, _completed())

        await _run_agent_wipe(test_db, wipe, repo, wait)

        assert server_borg == []
        jobs = _agent_jobs(test_db)
        assert [j.payload["job_kind"] for j in jobs] == [
            "repository.delete_archives",
            "repository.compact",
        ]
        assert jobs[0].payload["operation"]["archives"] == [
            f"aid:{n * 64}" for n in "123"
        ]
        assert jobs[0].payload["operation"]["maintenance_job"]["id"] == wipe.id
        # the budget a job per archive had, in all
        waits = wait.await_args_list
        assert waits[0].kwargs["timeout_seconds"] == (
            3 * waits[1].kwargs["timeout_seconds"]
        )
        job = resolve_wipe_job(test_db, wipe.id)
        assert job.status == "completed"
        assert job.phase == "completed"

    @pytest.mark.asyncio
    async def test_warnings_end_the_wipe_with_warnings(self, test_db, server_borg):
        from app.services.operations.wipe_facade import resolve_wipe_job

        agent = _with_capabilities(
            test_db, _agent(test_db), "repository.delete_archives"
        )
        repo = _repo(test_db, agent)
        wipe = _seed_agent_wipe(test_db, repo, _admin(test_db))
        warned = {
            "return_code": 1,
            "deleted_archives": 2,
            "warnings": [
                {"archive": f"aid:{'2' * 64}", "return_code": 1, "stderr": "odd"}
            ],
        }

        await _run_agent_wipe(
            test_db, wipe, repo, _agent_answers(test_db, warned, _completed())
        )

        job = resolve_wipe_job(test_db, wipe.id)
        assert job.status == "completed_with_warnings"
        assert "archive-2 ended with a warning (exit 1): odd" in job.error_message

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "deleted, status",
        [(1, "failed_partial"), (0, "failed"), (None, "failed_partial")],
    )
    async def test_a_failure_is_partial_when_archives_went(
        self, test_db, server_borg, deleted, status
    ):
        from app.services.operations.wipe_facade import resolve_wipe_job

        agent = _with_capabilities(
            test_db, _agent(test_db), "repository.delete_archives"
        )
        repo = _repo(test_db, agent)
        wipe = _seed_agent_wipe(test_db, repo, _admin(test_db))

        def failed():
            (agent_job,) = _agent_jobs(test_db, "repository.delete_archives")
            agent_job.claimed_at = agent_job.created_at
            if deleted is not None:
                agent_job.result = {"return_code": 2, "deleted_archives": deleted}
            test_db.commit()
            return HTTPException(
                status_code=502,
                detail={
                    "key": "backend.errors.agents.jobFailed",
                    "params": {"reason": "lock timeout"},
                },
            )

        await _run_agent_wipe(test_db, wipe, repo, _agent_answers(test_db, failed))

        assert [j.payload["job_kind"] for j in _agent_jobs(test_db)] == [
            "repository.delete_archives"
        ]
        job = resolve_wipe_job(test_db, wipe.id)
        assert job.status == status
        assert "lock timeout" in job.error_message

    @pytest.mark.asyncio
    async def test_a_job_no_agent_claimed_deleted_nothing(self, test_db, server_borg):
        from app.services.operations.wipe_facade import resolve_wipe_job

        agent = _with_capabilities(
            test_db, _agent(test_db), "repository.delete_archives"
        )
        repo = _repo(test_db, agent)
        wipe = _seed_agent_wipe(test_db, repo, _admin(test_db))
        timeout = HTTPException(
            status_code=504,
            detail={"key": "backend.errors.agents.repositoryOperationTimeout"},
        )

        await _run_agent_wipe(test_db, wipe, repo, _agent_answers(test_db, timeout))

        (agent_job,) = _agent_jobs(test_db, "repository.delete_archives")
        assert agent_job.status == "canceled"
        job = resolve_wipe_job(test_db, wipe.id)
        assert job.status == "failed"
        assert job.phase == "delete_failed"
