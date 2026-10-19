"""Custom flags and the upload limit follow the Borg major that runs them (#1263).

Borg 2 has no --upload-ratelimit, --upload-buffer, --numeric-owner,
--noatime, --nobsdflags, --exclude-nodump or --checkpoint-interval for
create, nor --save-space, --prefix or --glob-archives for check; Borg 1 has none of check's --find-lost-archives,
--match-archives, --oldest, --newest, --older and --newer. Measured on Borg
1.4.5 and 2.0.0b25: the other major stops at argument parsing ("unrecognized
arguments", exit 2), so a backup or check carrying one never starts.
"""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from agent.borg_ui_agent import borg_flags as agent_borg_flags
from agent.borg_ui_agent.backup import BackupCreatePayload
from agent.borg_ui_agent.repository_ops import RepositoryOperationPayload
from app.utils import borg_flags
from app.utils.borg_flags import parse_borg_flags

BORG1_ONLY = [
    ("create", "--numeric-owner"),
    ("create", "--noatime"),
    ("create", "--nobsdflags"),
    ("create", "--exclude-nodump"),
    ("create", "--checkpoint-interval=600"),
    ("create", "--upload-ratelimit=1024"),
    ("create", "--upload-buffer=100"),
    ("check", "--save-space"),
    ("check", "--prefix=web-"),
    ("check", "--glob-archives=web-*"),
]
BORG2_ONLY = [
    ("check", "--find-lost-archives"),
    ("check", "--match-archives=sh:web-*"),
    ("check", "--oldest=7d"),
    ("check", "--newest=7d"),
    ("check", "--older=7d"),
    ("check", "--newer=7d"),
]


@pytest.mark.unit
@pytest.mark.parametrize("parser", [borg_flags, agent_borg_flags])
@pytest.mark.parametrize("command,text", BORG1_ONLY)
def test_borg2_refuses_borg1_only_flags(parser, command, text):
    name = text.split("=")[0]
    with pytest.raises(ValueError, match=f"Borg 2 {command} has no option {name}"):
        parser.parse_borg_flags(text, command, 2)
    assert parser.parse_borg_flags(text, command, 1) == [text]


@pytest.mark.unit
@pytest.mark.parametrize("parser", [borg_flags, agent_borg_flags])
@pytest.mark.parametrize("command,text", BORG2_ONLY)
def test_borg1_refuses_borg2_only_flags(parser, command, text):
    name = text.split("=")[0]
    with pytest.raises(ValueError, match=f"Borg 1 {command} has no option {name}"):
        parser.parse_borg_flags(text, command, 1)
    assert parser.parse_borg_flags(text, command, 2) == [text]


@pytest.mark.unit
@pytest.mark.parametrize("command,text", BORG1_ONLY + BORG2_ONLY)
def test_without_a_major_either_spelling_passes(command, text):
    assert parse_borg_flags(text, command) == [text]


@pytest.mark.unit
@pytest.mark.parametrize("borg_version", [None, 1, 2])
def test_undelete_archives_is_refused_everywhere(borg_version):
    """Neither Borg 1.4.5 nor 2.0.0b25 has the option."""
    with pytest.raises(ValueError, match="not allowed"):
        parse_borg_flags("--undelete-archives", "check", borg_version)


@pytest.mark.unit
@pytest.mark.parametrize("borg_version", [0, False, "", 3, -1, "x", 2.5, True])
def test_an_agent_job_with_an_unknown_major_is_refused(borg_version):
    """The two job decoders read the major through one gate; an unknown one
    must not be built as a Borg 1 command, with or without custom flags."""
    with pytest.raises(ValueError, match="Unsupported Borg major"):
        BackupCreatePayload.from_job_payload(_agent_backup(borg_version))
    with pytest.raises(ValueError, match="Unsupported Borg major"):
        RepositoryOperationPayload.from_job_payload(
            {
                "job_kind": "repository.check",
                "repository": {"path": "/backup/repo", "borg_version": borg_version},
            }
        )


@pytest.mark.unit
@pytest.mark.parametrize(("value", "major"), [(None, 1), (1, 1), (2, 2), ("2", 2)])
def test_an_agent_job_names_its_major_or_runs_on_borg1(value, major):
    from agent.borg_ui_agent.backup import job_borg_major

    assert job_borg_major({"borg_version": value}, {}) == major


@pytest.mark.unit
def test_agent_copy_matches_the_per_major_table():
    assert agent_borg_flags.BORG_MAJOR_ONLY_FLAGS == borg_flags.BORG_MAJOR_ONLY_FLAGS
    for command, majors in borg_flags.BORG_MAJOR_ONLY_FLAGS.items():
        for names in majors.values():
            assert names <= set(borg_flags.ALLOWED_BORG_FLAGS[command])


# -- the commands -------------------------------------------------------------


@pytest.mark.unit
def test_borg2_create_command_leaves_the_upload_limit_out():
    from app.services.v2.backup_service import backup_v2_service

    cmd = backup_v2_service.build_backup_create_command(
        repository_path="/repos/v2",
        archive_name="a",
        compression="lz4",
        exclude_patterns=[],
        custom_flags=[],
        upload_ratelimit_kib=512,
    )

    assert "--upload-ratelimit" not in cmd


@pytest.mark.unit
def test_borg2_create_command_refuses_a_borg1_custom_flag():
    from app.services.v2.backup_service import backup_v2_service

    with pytest.raises(ValueError, match="--upload-ratelimit"):
        backup_v2_service.build_backup_create_command(
            repository_path="/repos/v2",
            archive_name="a",
            compression="lz4",
            exclude_patterns=[],
            custom_flags=["--upload-ratelimit=512"],
        )


@pytest.mark.unit
def test_borg1_create_command_keeps_its_options():
    from app.core.borg_router import BorgRouter

    cmd = BorgRouter(SimpleNamespace(borg_version=1)).build_backup_create_command(
        repository_path="/repos/v1",
        archive_name="a",
        compression="lz4",
        exclude_patterns=[],
        custom_flags=["--checkpoint-interval=600"],
        upload_ratelimit_kib=512,
    )

    assert cmd[cmd.index("--upload-ratelimit") + 1] == "512"
    assert "--checkpoint-interval=600" in cmd


def _repository(borg_version, **fields):
    return SimpleNamespace(
        id=1,
        path="/backup/repo",
        borg_version=borg_version,
        remote_path=None,
        compression="lz4",
        exclude_patterns="[]",
        custom_flags=None,
        upload_ratelimit_kib=512,
        passphrase=None,
        **fields,
    )


@pytest.mark.unit
def test_agent_payload_leaves_the_upload_limit_out_of_a_local_borg2_repository():
    from app.services.repository_executor import build_agent_backup_payload

    borg1 = build_agent_backup_payload(_repository(1), "a", source_directories=["/s"])
    borg2 = build_agent_backup_payload(_repository(2), "a", source_directories=["/s"])

    assert borg1["backup"]["upload_ratelimit_kib"] == 512
    assert "upload_ratelimit_kib" not in borg2["backup"]


@pytest.mark.unit
def test_agent_payload_refuses_a_flag_the_repository_major_lacks():
    from app.services.repository_executor import build_agent_backup_payload

    with pytest.raises(ValueError, match="--checkpoint-interval"):
        build_agent_backup_payload(
            _repository(2),
            "a",
            source_directories=["/s"],
            custom_flags="--checkpoint-interval=600",
        )


def _agent_backup(borg_version, **backup):
    return {
        "job_kind": "backup.create",
        "repository": {"path": "/backup/repo", "borg_version": borg_version},
        "backup": {"archive_name": "a", "source_paths": ["/src"], **backup},
    }


@pytest.mark.unit
def test_agent_borg2_backup_ignores_an_upload_limit_an_older_server_sends():
    payload = BackupCreatePayload.from_job_payload(
        _agent_backup(2, upload_ratelimit_kib=512)
    )

    assert "--upload-ratelimit" not in payload.build_command()


@pytest.mark.unit
def test_agent_borg1_backup_keeps_the_upload_limit():
    payload = BackupCreatePayload.from_job_payload(
        _agent_backup(1, upload_ratelimit_kib=512)
    )

    cmd = payload.build_command()
    assert cmd[cmd.index("--upload-ratelimit") + 1] == "512"


@pytest.mark.unit
def test_agent_backup_refuses_a_flag_its_borg_major_lacks():
    with pytest.raises(ValueError, match="Borg 2 create has no option --noatime"):
        BackupCreatePayload.from_job_payload(_agent_backup(2, custom_flags="--noatime"))
    assert BackupCreatePayload.from_job_payload(
        _agent_backup(1, custom_flags="--noatime")
    ).custom_flags == ["--noatime"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "borg_version,flags",
    [(2, "--save-space"), (2, "--prefix=web-"), (1, "--match-archives=sh:web-*")],
)
def test_agent_check_refuses_a_flag_its_borg_major_lacks(borg_version, flags):
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.check",
            "repository": {"path": "/backup/repo", "borg_version": borg_version},
            "operation": {"check_extra_flags": flags},
        }
    )

    with pytest.raises(ValueError, match="has no option"):
        payload.build_command()


# -- where a flag is entered ----------------------------------------------------


@pytest.mark.unit
def test_repository_create_and_import_check_flags_against_their_major():
    from app.api.repositories import RepositoryCreate, RepositoryImport
    from app.api.v2.repositories import RepositoryV2Create, RepositoryV2Import

    repo = {"name": "r", "path": "/r"}
    for model in (RepositoryCreate, RepositoryImport):
        assert model(**repo, custom_flags="--noatime").custom_flags == "--noatime"
        with pytest.raises(ValidationError, match="--noatime"):
            model(**repo, borg_version=2, custom_flags="--noatime")
        # the route takes a Borg-2-only encryption for Borg 2, and so does this
        with pytest.raises(ValidationError, match="--noatime"):
            model(**repo, encryption="repokey-aes-ocb", custom_flags="--noatime")
    for model in (RepositoryV2Create, RepositoryV2Import):
        with pytest.raises(ValidationError, match="--upload-ratelimit"):
            model(**repo, custom_flags="--upload-ratelimit 512")


@pytest.mark.unit
def test_borg2_check_request_refuses_a_borg1_flag():
    from app.api.v2.backups import CheckV2Request

    with pytest.raises(ValidationError, match="--save-space"):
        CheckV2Request(repository_id=1, check_extra_flags="--save-space")
    assert CheckV2Request(repository_id=1, check_extra_flags="--find-lost-archives")


@pytest.mark.unit
def test_agent_backup_job_request_checks_flags_against_its_major():
    from app.api.managed_machines import AgentBackupJobCreate

    base = {"repository_path": "/r", "archive_name": "a", "source_paths": ["/s"]}
    assert AgentBackupJobCreate(**base, custom_flags=["--upload-buffer=10"])
    with pytest.raises(ValidationError, match="--upload-buffer"):
        AgentBackupJobCreate(
            **base, borg_version=2, custom_flags=["--upload-buffer=10"]
        )
