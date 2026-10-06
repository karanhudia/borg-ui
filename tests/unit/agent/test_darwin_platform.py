"""What changes when the agent runs on macOS (#1151).

Every test fakes the platform; nothing here needs a Mac. The Linux behaviour is
asserted alongside so that each Darwin branch is visibly a branch.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

import pytest

from agent.borg_ui_agent import (
    borg,
    config,
    paths,
    repository_ops,
    scripts,
    self_upgrade,
)
from agent.borg_ui_agent import storage_usage


@pytest.fixture
def darwin(monkeypatch, tmp_path: Path) -> Path:
    """A Darwin platform with a fresh home directory."""
    monkeypatch.setattr(paths.platform, "system", lambda: "Darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def linux(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(paths.platform, "system", lambda: "Linux")
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


# --- defaults ----------------------------------------------------------------


def test_the_agent_root_and_config_share_the_user_directory_on_darwin(darwin):
    root = darwin / "Library" / "Application Support" / "borg-ui-agent"

    assert paths.default_agent_root() == root
    assert paths.default_config_dir() == root
    assert config.default_config_path() == root / "config.toml"


def test_the_linux_defaults_are_unchanged(linux):
    assert paths.default_agent_root() == Path("/opt/borg-ui-agent")
    assert (
        config.default_config_path()
        == linux / ".config" / "borg-ui-agent" / "config.toml"
    )


def test_the_scripts_allow_list_sits_beside_the_config_on_darwin(darwin, monkeypatch):
    monkeypatch.delenv("BORG_UI_AGENT_SCRIPTS_DIR", raising=False)

    assert (
        scripts.scripts_dir()
        == (
            darwin / "Library" / "Application Support" / "borg-ui-agent" / "scripts.d"
        ).resolve()
    )


def test_the_scripts_allow_list_stays_under_etc_on_linux(linux, monkeypatch):
    monkeypatch.delenv("BORG_UI_AGENT_SCRIPTS_DIR", raising=False)

    assert scripts.default_scripts_dir() == "/etc/borg-ui-agent/scripts.d"


def test_the_scripts_override_still_wins_on_darwin(darwin, monkeypatch, tmp_path):
    override = tmp_path / "elsewhere"
    override.mkdir()
    monkeypatch.setenv("BORG_UI_AGENT_SCRIPTS_DIR", str(override))

    assert scripts.scripts_dir() == override.resolve()


# --- install source ----------------------------------------------------------


def test_a_borg_under_the_user_agent_root_is_installer_managed(darwin):
    binary = (
        darwin / "Library" / "Application Support" / "borg-ui-agent" / "bin" / "borg"
    )

    assert borg._classify_install_source(str(binary)) == "borg-ui-installer"


@pytest.mark.parametrize("prefix", ["opt/homebrew", "usr/local"])
def test_a_homebrew_borg_is_told_by_its_cellar(darwin, tmp_path, prefix):
    cellar = tmp_path / prefix / "Cellar" / "borgbackup" / "1.4.5" / "bin"
    cellar.mkdir(parents=True)
    (cellar / "borg").write_text("", encoding="utf-8")
    link = tmp_path / prefix / "bin" / "borg"
    link.parent.mkdir(parents=True)
    link.symlink_to(cellar / "borg")

    assert borg._classify_install_source(str(link)) == "homebrew"


def test_a_macports_borg_is_labelled(darwin):
    assert borg._classify_install_source("/opt/local/bin/borg") == "macports"


def test_the_linux_labels_are_unchanged(linux):
    assert (
        borg._classify_install_source("/opt/borg-ui-agent/bin/borg")
        == "borg-ui-installer"
    )
    assert borg._classify_install_source("/usr/bin/borg") == "system-package"
    assert borg._classify_install_source("/usr/local/bin/borg") == "custom-path"


# --- du ----------------------------------------------------------------------


def test_du_reports_apparent_kib_on_darwin(darwin, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="166\t/repo\n", stderr="")

    monkeypatch.setattr(storage_usage, "_run", fake_run)

    assert storage_usage.du_storage_used("/repo", timeout=5) == 166 * 1024
    assert calls == [["du", "-A", "-sk", "--", "/repo"]]


def test_du_reports_apparent_bytes_on_linux(linux, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout="169984\t/repo\n", stderr=""
        )

    monkeypatch.setattr(storage_usage, "_run", fake_run)

    assert storage_usage.du_storage_used("/repo", timeout=5) == 169984
    assert calls == [["du", "-sb", "--", "/repo"]]


class _CompletionClient:
    def __init__(self):
        self.result = None

    def send_log(self, job_id, **kwargs):
        pass

    def complete_job(self, job_id, *, result):
        self.result = result


def _disk_usage(monkeypatch, du_stdout: str) -> dict:
    """Run a `repository.disk_usage` job against a faked du; the result the
    server receives. The server reads the first stdout field as bytes (#1291)."""
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=du_stdout, stderr="")

    monkeypatch.setattr(repository_ops.subprocess, "run", fake_run)
    client = _CompletionClient()
    repository_ops.execute_repository_operation_job(
        {
            "id": 1,
            "payload": {
                "schema_version": 1,
                "job_kind": "repository.disk_usage",
                "repository": {"path": "/repo", "borg_version": 1},
            },
        },
        client,
    )
    return {"calls": calls, "stdout": client.result["stdout"]}


def test_disk_usage_job_reports_bytes_on_darwin(darwin, monkeypatch):
    ran = _disk_usage(monkeypatch, "166\t/repo\n")

    assert ran["calls"] == [["du", "-A", "-sk", "--", "/repo"]]
    assert ran["stdout"] == f"{166 * 1024}\t/repo\n"


def test_disk_usage_job_reports_bytes_on_linux(linux, monkeypatch):
    ran = _disk_usage(monkeypatch, "169984\t/repo\n")

    assert ran["calls"] == [["du", "-sb", "--", "/repo"]]
    assert ran["stdout"] == "169984\t/repo\n"


# --- remote upgrade readiness ----------------------------------------------


def _write_plist(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump(content, handle)


@pytest.fixture
def darwin_ready(darwin):
    """A complete per-user install: conf and helper under the agent root, one
    job that names the helper and watches the trigger."""
    root = darwin / "Library" / "Application Support" / "borg-ui-agent"
    helper = root / "bin" / "borg-ui-agent-upgrade"
    helper.parent.mkdir(parents=True)
    helper.write_text("#!/bin/sh\n", encoding="utf-8")
    helper.chmod(0o755)
    (root / "upgrade.conf").write_text(
        "\n".join(
            [
                'SERVER="https://borg.example"',
                'AGENT_ID="agent-1"',
                'BORG_INSTALL_MODE="1"',
                'SERVICE_USER="me"',
                f'AGENT_ROOT="{root}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "config.toml").write_text(
        'server_url = "https://borg.example"\nagent_id = "agent-1"\n'
        'agent_token = "secret"\n',
        encoding="utf-8",
    )
    job = darwin / "Library" / "LaunchAgents" / "com.borg-ui.agent-upgrade.plist"
    _write_plist(
        job,
        {
            "Label": "com.borg-ui.agent-upgrade",
            "ProgramArguments": [str(helper)],
            "KeepAlive": {"PathState": {str(root / "upgrade-requested"): True}},
        },
    )
    return {"root": root, "job": job, "helper": helper}


def test_the_darwin_defaults_point_into_the_user_directory(darwin):
    root = darwin / "Library" / "Application Support" / "borg-ui-agent"
    defaults = self_upgrade.default_upgrade_paths()

    assert defaults.conf_path == root / "upgrade.conf"
    assert defaults.trigger_path == root / "upgrade-requested"
    assert defaults.unit_path == defaults.path_unit_path
    assert defaults.unit_path.name == "com.borg-ui.agent-upgrade.plist"


def test_the_linux_defaults_are_the_systemd_files(linux):
    defaults = self_upgrade.default_upgrade_paths()

    assert defaults.conf_path == Path("/etc/borg-ui-agent-upgrade.conf")
    assert defaults.unit_path == Path(
        "/etc/systemd/system/borg-ui-agent-upgrade.service"
    )
    assert defaults.path_unit_path == Path(
        "/etc/systemd/system/borg-ui-agent-upgrade.path"
    )
    assert defaults.trigger_path == Path("/etc/borg-ui-agent/upgrade-requested")


def test_a_complete_per_user_install_can_upgrade_itself(darwin_ready):
    readiness = self_upgrade.check_self_upgrade()

    assert readiness.supported is True
    assert readiness.trigger == darwin_ready["root"] / "upgrade-requested"


def test_a_per_user_install_moved_to_another_server_cannot_upgrade_itself(
    darwin_ready,
):
    config = darwin_ready["root"] / "config.toml"
    config.write_text(
        config.read_text().replace("https://borg.example", "https://new.example"),
        encoding="utf-8",
    )

    assert self_upgrade.check_self_upgrade().reason == "server_mismatch"
    assert self_upgrade.can_self_upgrade() is False


def test_an_upgrade_record_that_is_not_text_is_no_capability_not_a_crash(
    darwin_ready,
):
    (darwin_ready["root"] / "upgrade.conf").write_bytes(b'SERVER="\xff\xfe"\n')

    assert self_upgrade.can_self_upgrade() is False


def test_a_job_that_names_no_helper_is_reported_as_missing(darwin_ready):
    _write_plist(darwin_ready["job"], {"Label": "com.borg-ui.agent-upgrade"})

    assert self_upgrade.check_self_upgrade().reason == "helper_missing"


def test_a_job_without_the_watch_condition_is_not_armed(darwin_ready):
    _write_plist(
        darwin_ready["job"],
        {
            "Label": "x",
            "ProgramArguments": [str(darwin_ready["helper"])],
            "KeepAlive": True,
        },
    )

    assert self_upgrade.check_self_upgrade().reason == "path_unit_missing"


def test_a_job_watching_another_path_is_not_armed(darwin_ready):
    _write_plist(
        darwin_ready["job"],
        {
            "Label": "x",
            "ProgramArguments": [str(darwin_ready["helper"])],
            "KeepAlive": {"PathState": {"/somewhere/else": True}},
        },
    )

    assert self_upgrade.check_self_upgrade().reason == "path_unit_missing"


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads everything")
def test_an_unreadable_job_is_a_missing_helper_not_a_crash(darwin_ready):
    darwin_ready["job"].chmod(0)

    assert self_upgrade.check_self_upgrade().reason == "helper_missing"


def test_a_missing_job_is_reported_as_such(darwin_ready):
    darwin_ready["job"].unlink()

    assert self_upgrade.check_self_upgrade().reason == "unit_missing"


@pytest.mark.parametrize(
    "content",
    [
        b"not a plist",
        b'<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>La',
        b'<?xml version="1.0"?><plist version="1.0"><string>not a job</string></plist>',
    ],
)
def test_a_malformed_job_is_a_missing_helper_not_a_crash(darwin_ready, content):
    """A truncated or foreign plist must not raise out of the capability
    report: launchd could not load it either, so the job is as good as absent."""
    darwin_ready["job"].write_bytes(content)

    assert self_upgrade.check_self_upgrade().reason == "helper_missing"
    assert self_upgrade.can_self_upgrade() is False
