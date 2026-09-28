"""User supplied borg flags go through one allowlist before reaching argv.

Backup plan ``custom_flags``, per-link ``custom_flags_override``, repository
``custom_flags`` and ``check_extra_flags`` are editable by operators, so every
token must be a known safe option for the borg command it is appended to.
"""

import shlex

import pytest

from agent.borg_ui_agent import borg_flags as agent_borg_flags
from app.utils import borg_flags
from app.utils.borg_flags import parse_borg_flags

MALICIOUS_CREATE_FLAGS = [
    "--rsh=sh -c id",
    "--rsh 'sh -c id'",
    "--stats --rsh=sh\\ -c\\ id",
    "--remote-path=/tmp/evil",
    "--remote-path /tmp/evil",
    "--content-from-command -- id",
    "--paths-from-command -- id",
    "--stats; id",
    "; id",
    "--stats && id",
    "--stats | id",
    "$(id)",
    "`id`",
    "--stats\nid",
    "--comment=ok\nid",
    "--stats id",
    "/etc/shadow",
    "--patterns-from=/etc/shadow",
    "--exclude-from=/etc/shadow",
    "--exclude",
    "--exclude --rsh=id",
    "--stats=1",
    "-e",
    "--one-file-system=yes",
    "'unbalanced",
]


@pytest.mark.parametrize("text", MALICIOUS_CREATE_FLAGS)
def test_create_rejects_injection_payloads(text):
    with pytest.raises(ValueError):
        parse_borg_flags(text, "create")


@pytest.mark.parametrize(
    "text",
    [
        "--rsh=sh -c id",
        "--remote-path=/tmp/evil",
        "--verify-data; id",
        "--verify-data id",
        "--repair\nid",
        "--one-file-system",
        "--first",
    ],
)
def test_check_rejects_injection_payloads(text):
    with pytest.raises(ValueError):
        parse_borg_flags(text, "check")


def test_rejection_message_names_the_flag():
    with pytest.raises(ValueError, match="--rsh"):
        parse_borg_flags("--stats --rsh=sh", "create")
    with pytest.raises(ValueError, match="Positional"):
        parse_borg_flags("--stats id", "create")


@pytest.mark.parametrize(
    "text,expected",
    [
        (None, []),
        ("", []),
        ("   ", []),
        ("--stats", ["--stats"]),
        ("--one-file-system", ["--one-file-system"]),
        ("--stats --list --filter AME", ["--stats", "--list", "--filter=AME"]),
        ("--stats --list --filter=AME", ["--stats", "--list", "--filter=AME"]),
        ("-x -s", ["-x", "-s"]),
        ("--exclude-caches --keep-exclude-tags", None),
        ("--exclude-if-present=.nobackup", None),
        ("--exclude '*.tmp'", ["--exclude=*.tmp"]),
        ("-e '*.tmp'", ["-e", "*.tmp"]),
        ("--comment='nightly run'", ["--comment=nightly run"]),
        ("--numeric-ids --noatime --noctime --nobirthtime", None),
        ("--noflags --noacls --noxattrs --sparse", None),
        ("--files-cache=ctime,size --checkpoint-interval=600", None),
        ("--chunker-params=buzhash,19,23,21,4095 --lock-wait=600", None),
        ("--pattern='- **/.cache'", ["--pattern=- **/.cache"]),
    ],
)
def test_create_accepts_legitimate_flags(text, expected):
    result = parse_borg_flags(text, "create")
    if expected is None:
        expected = shlex.split(text)
    assert result == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        (" --verify-data ", ["--verify-data"]),
        ("--repair --verify-data", ["--repair", "--verify-data"]),
        ("--repair --save-space", ["--repair", "--save-space"]),
        ("--repository-only --max-duration=3600", None),
        ("--archives-only --last=3", None),
        ("--first 2", ["--first=2"]),
        ("-a 'web-*'", ["-a", "web-*"]),
        ("--match-archives=sh:web-*", None),
        ("--glob-archives='web-*'", ["--glob-archives=web-*"]),
    ],
)
def test_check_accepts_legitimate_flags(text, expected):
    result = parse_borg_flags(text, "check")
    if expected is None:
        expected = shlex.split(text)
    assert result == expected


def test_token_lists_are_validated_too():
    assert parse_borg_flags(["--stats"], "create") == ["--stats"]
    with pytest.raises(ValueError):
        parse_borg_flags(["--rsh=sh -c id"], "create")
    with pytest.raises(ValueError):
        parse_borg_flags(["--stats", "id"], "create")


def test_unknown_command_is_rejected():
    with pytest.raises(ValueError):
        parse_borg_flags("--stats", "delete")


def test_agent_copy_matches_server_allowlist():
    """The agent package cannot import app/, so it carries its own copy."""
    assert agent_borg_flags.ALLOWED_BORG_FLAGS == borg_flags.ALLOWED_BORG_FLAGS
    for text in MALICIOUS_CREATE_FLAGS:
        with pytest.raises(ValueError):
            agent_borg_flags.parse_borg_flags(text, "create")
    assert agent_borg_flags.parse_borg_flags("--filter AME", "create") == [
        "--filter=AME"
    ]


def _agent_repository(custom_flags):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=1,
        path="/backup/repo",
        borg_version=1,
        remote_path=None,
        compression="lz4",
        exclude_patterns="[]",
        custom_flags=custom_flags,
        upload_ratelimit_kib=None,
        passphrase=None,
    )


@pytest.mark.parametrize("stored", ["--rsh='sh -c id'", "--stats; id", "--stats id"])
def test_agent_backup_payload_rejects_poisoned_repository_flags(stored):
    from app.services.repository_executor import build_agent_backup_payload

    with pytest.raises(ValueError):
        build_agent_backup_payload(
            _agent_repository(stored), "a", source_directories=["/src"]
        )
    with pytest.raises(ValueError):
        build_agent_backup_payload(
            _agent_repository(None),
            "a",
            source_directories=["/src"],
            custom_flags=stored,
        )


def test_agent_backup_payload_sends_normalized_flags():
    from app.services.repository_executor import build_agent_backup_payload

    payload = build_agent_backup_payload(
        _agent_repository("--one-file-system --filter AME"),
        "a",
        source_directories=["/src"],
    )

    assert payload["backup"]["custom_flags"] == "--one-file-system --filter=AME"


def _schema_cases():
    from app.api.backup_plans import BackupPlanPayload, BackupPlanRepositoryPayload
    from app.api.managed_machines import AgentBackupJobCreate
    from app.api.repositories import (
        RepositoryCreate,
        RepositoryImport,
        RepositoryUpdate,
    )
    from app.api.v2.backups import CheckV2Request
    from app.api.v2.repositories import RepositoryV2Create, RepositoryV2Import

    repo = {"name": "r", "path": "/r"}
    plan = {"name": "p", "source_directories": ["/s"], "repositories": []}
    return [
        (RepositoryCreate, repo, "custom_flags", "--stats"),
        (RepositoryImport, repo, "custom_flags", "--stats"),
        (RepositoryUpdate, {}, "custom_flags", "--stats"),
        (RepositoryV2Create, repo, "custom_flags", "--stats"),
        (RepositoryV2Import, repo, "custom_flags", "--stats"),
        (
            AgentBackupJobCreate,
            {"repository_path": "/r", "archive_name": "a", "source_paths": ["/s"]},
            "custom_flags",
            ["--stats"],
        ),
        (BackupPlanPayload, plan, "custom_flags", "--stats"),
        (BackupPlanPayload, plan, "check_extra_flags", "--verify-data"),
        (
            BackupPlanRepositoryPayload,
            {"repository_id": 1, "execution_order": 1},
            "custom_flags_override",
            "--stats",
        ),
        (CheckV2Request, {"repository_id": 1}, "check_extra_flags", "--verify-data"),
    ]


def test_every_flag_schema_validates_on_write():
    from pydantic import ValidationError

    for model, base, field, good in _schema_cases():
        assert getattr(model(**base, **{field: good}), field) == good
        bad = ["--rsh=sh -c id"] if isinstance(good, list) else "--rsh='sh -c id'"
        with pytest.raises(ValidationError, match="--rsh"):
            model(**base, **{field: bad})
        positional = [good[0], "id"] if isinstance(good, list) else f"{good}; id"
        with pytest.raises(ValidationError):
            model(**base, **{field: positional})


# Every flag example the UI (placeholders, helper text) and docs suggest.
SUGGESTED_EXAMPLES = [
    ("create", "--stats --list --filter AME"),  # AdvancedRepositoryOptions
    ("create", "--stats --list"),  # backup plan SettingsStep
    ("create", "--stats --progress --list"),  # customFlagsHint helper text
    ("create", "--files-cache=mtime,size"),  # docs/troubleshooting.md
    ("check", "--repair --verify-data"),  # check dialogs and schedules
    ("check", "--repair"),
    ("check", "--verify-data"),
]


@pytest.mark.parametrize("command,text", SUGGESTED_EXAMPLES)
def test_every_suggested_example_passes(command, text):
    assert parse_borg_flags(text, command)


@pytest.mark.parametrize(
    "command,text,expected",
    [
        ("create", "--compression=zstd,3", ["--compression=zstd,3"]),
        ("create", "--upload-ratelimit=1024", ["--upload-ratelimit=1024"]),
        ("create", "--upload-buffer=100", ["--upload-buffer=100"]),
        ("create", "--timestamp=2026-01-01T00:00:00", None),
        ("create", "--dry-run -n --debug", ["--dry-run", "-n", "--debug"]),
        ("create", "--log-json --show-rc", ["--log-json", "--show-rc"]),
        ("check", "--debug --log-json --show-rc", None),
        ("create", "-xs", ["-x", "-s"]),
        ("create", "-vp -xs", ["-v", "-p", "-x", "-s"]),
        ("check", "-vp", ["-v", "-p"]),
    ],
)
def test_harmless_flags_and_combined_short_flags(command, text, expected):
    if expected is None:
        expected = shlex.split(text)
    assert parse_borg_flags(text, command) == expected
    assert agent_borg_flags.parse_borg_flags(text, command) == expected


@pytest.mark.parametrize(
    "command,text",
    [
        ("create", "-xe"),  # -e takes a value
        ("create", "-xz"),  # unknown letter
        ("create", "-x=s"),
        ("check", "-xs"),  # -x and -s are create-only
        ("create", "--exclude xs"),  # a value is never expanded into flags
    ],
)
def test_combined_short_flags_reject_unknown_or_value_letters(command, text):
    if text == "--exclude xs":
        assert parse_borg_flags(text, command) == ["--exclude=xs"]
        return
    with pytest.raises(ValueError):
        parse_borg_flags(text, command)
