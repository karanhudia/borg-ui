"""The Borgmatic import records the Borg major a repository is for.

A borgmatic configuration does not name the major, but its entries tell it in
places: a URL only one major can open, a Borg 2 encryption name or option, or
the ``borg_ui_borg_version`` a Borg UI export writes. Without any of them the
import keeps Borg 1. An entry that contradicts itself is refused.
"""

import io
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

from app.core.borg2 import (
    BORG2_REMOVED_ENCRYPTION_MODES,
    REMOVED_REPOSITORY_URL_MESSAGE,
)
from app.database.models import LicensingState, Repository
from app.services.borgmatic_service import (
    BorgmaticExportService,
    BorgmaticImportService,
)


@pytest.fixture
def borg2_plan(db_session):
    state = LicensingState(instance_id="test-instance-borgmatic-borg-major")
    state.plan = "pro"
    state.status = "active"
    state.is_trial = False
    db_session.add(state)
    db_session.commit()


def _import(db_session, repository, **top_level):
    config = {
        "repositories": [repository],
        "source_directories": ["/data"],
        "encryption_passphrase": "x",
        **top_level,
    }
    return BorgmaticImportService(db_session).import_from_yaml(yaml.safe_dump(config))


def _only_row(db_session) -> Repository:
    return db_session.query(Repository).one()


BORG2_ONLY_URLS = [
    "sftp://borg@backup.example.com:22/srv/repo",
    "http://backup.example.com:8080/repo",
    "https://backup.example.com/repo",
    "s3:profile@/bucket/repo",
    "b2:bucket/repo",
    "rclone:remote:repo",
]


@pytest.mark.unit
@pytest.mark.parametrize("url", BORG2_ONLY_URLS)
def test_borg2_only_url_is_imported_as_borg2(db_session, borg2_plan, url):
    result = _import(db_session, url)

    assert result["errors"] == []
    assert result["repositories_created"] == 1
    row = _only_row(db_session)
    assert (row.path, row.borg_version, row.encryption) == (
        url,
        2,
        "repokey-aes-ocb",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        "/srv/backups/repo",
        "file:///srv/backups/repo",
        "ssh://borg@backup.example.com:22/./repo",
        "borg@backup.example.com:repo",
    ],
)
def test_path_without_a_hint_stays_borg1(db_session, path):
    result = _import(db_session, path)

    assert result["errors"] == []
    row = _only_row(db_session)
    assert (row.path, row.borg_version, row.encryption) == (path, 1, "repokey")


@pytest.mark.unit
@pytest.mark.parametrize("value", ["rest://borg@backup.example.com/srv/repo"])
def test_rest_url_is_refused(db_session, borg2_plan, value):
    result = _import(db_session, value)

    assert result["repositories_created"] == 0
    assert result["errors"] == [
        f"Failed to import repository {value}: {REMOVED_REPOSITORY_URL_MESSAGE}"
    ]
    assert db_session.query(Repository).count() == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("entry", "encryption"),
    [
        # Borg UI's own names for the Borg 2 modes.
        ({"encryption": "repokey-aes-ocb"}, "repokey-aes-ocb"),
        ({"encryption": "keyfile-chacha20-poly1305"}, "keyfile-chacha20-poly1305"),
        # Borg 2's `--encryption` names, with borgmatic's key_location.
        ({"encryption": "aes256-ocb"}, "repokey-aes-ocb"),
        ({"encryption": "aes256-ocb", "key_location": "keyfile"}, "keyfile-aes-ocb"),
        ({"encryption": "chacha20-poly1305"}, "repokey-chacha20-poly1305"),
        (
            {"encryption": "chacha20-poly1305", "key_location": "keyfile"},
            "keyfile-chacha20-poly1305",
        ),
        ({"encryption": "authenticated-sha256"}, "authenticated"),
        # borgmatic's Borg 2 only options.
        ({"key_location": "keyfile"}, "keyfile-aes-ocb"),
        ({"id_hash": "sha256"}, "repokey-aes-ocb"),
    ],
)
@pytest.mark.parametrize(
    "path", ["/srv/backups/repo", "ssh://borg@backup.example.com/./repo"]
)
def test_borg2_entry_options_import_a_path_as_borg2(
    db_session, borg2_plan, path, entry, encryption
):
    result = _import(db_session, {"path": path, **entry})

    assert result["errors"] == []
    row = _only_row(db_session)
    assert (row.path, row.borg_version, row.encryption) == (path, 2, encryption)


@pytest.mark.unit
@pytest.mark.parametrize(
    "encryption", ["repokey", "keyfile", "repokey-blake2", "keyfile-blake2", "none"]
)
def test_borg1_encryption_is_kept(db_session, encryption):
    result = _import(
        db_session, {"path": "/srv/backups/repo", "encryption": encryption}
    )

    assert result["errors"] == []
    row = _only_row(db_session)
    assert (row.borg_version, row.encryption) == (1, encryption)


@pytest.mark.unit
def test_authenticated_tells_no_major(db_session):
    """Borg 1 and Borg UI's Borg 2 both call a mode `authenticated`."""
    result = _import(
        db_session, {"path": "/srv/backups/repo", "encryption": "authenticated"}
    )

    assert result["errors"] == []
    assert _only_row(db_session).borg_version == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    ("entry", "top_level", "message"),
    [
        (
            {"path": "b2:bucket/repo", "encryption": "repokey"},
            {},
            "the b2: URL needs Borg 2, but encryption repokey needs Borg 1",
        ),
        (
            {"path": "borg@backup.example.com:repo", "encryption": "aes256-ocb"},
            {},
            "encryption aes256-ocb needs Borg 2, "
            "but the [user@]host:path address needs Borg 1",
        ),
        (
            {"path": "sftp://borg@backup.example.com/srv/repo"},
            {"borg_ui_borg_version": 1},
            "the sftp:// URL needs Borg 2, but borg_ui_borg_version 1 needs Borg 1",
        ),
        (
            {"path": "/srv/backups/repo", "key_location": "keyfile"},
            {"borg_ui_borg_version": 1},
            "key_location (Borg 2 only) needs Borg 2, "
            "but borg_ui_borg_version 1 needs Borg 1",
        ),
    ],
)
def test_entry_that_contradicts_itself_is_refused(
    db_session, borg2_plan, entry, top_level, message
):
    result = _import(db_session, entry, **top_level)

    assert result["repositories_created"] == 0
    assert result["errors"] == [
        f"Failed to import repository {entry['path']}: {message}"
    ]
    assert db_session.query(Repository).count() == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("encryption", "message"),
    [
        ("none", BORG2_REMOVED_ENCRYPTION_MODES["none"]),
        ("bogus", "unknown Borg 2 encryption mode 'bogus'"),
    ],
)
def test_borg2_entry_with_a_mode_borg2_lacks_is_refused(
    db_session, borg2_plan, encryption, message
):
    path = "/srv/backups/repo"
    result = _import(
        db_session,
        {"path": path, "encryption": encryption},
        **{"borg_ui_borg_version": 2},
    )

    assert result["errors"] == [f"Failed to import repository {path}: {message}"]
    assert db_session.query(Repository).count() == 0


@pytest.mark.unit
@pytest.mark.parametrize("declared", [0, 3, "2"])
def test_unknown_declared_major_is_refused(db_session, declared):
    path = "/srv/backups/repo"
    result = _import(db_session, path, borg_ui_borg_version=declared)

    assert result["errors"] == [
        f"Failed to import repository {path}: "
        f"borg_ui_borg_version must be 1 or 2, not {declared!r}"
    ]


@pytest.mark.unit
def test_borg2_needs_the_plan_feature(db_session):
    url = "b2:bucket/repo"
    result = _import(db_session, url)

    assert result["errors"] == [
        f"Failed to import repository {url}: "
        "Borg 2 repositories are not included in the current plan"
    ]
    assert db_session.query(Repository).count() == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("borg_version", "encryption", "entry"),
    [
        (1, "repokey", None),
        (2, "repokey-aes-ocb", {"encryption": "aes256-ocb"}),
        (
            2,
            "keyfile-aes-ocb",
            {"encryption": "aes256-ocb", "key_location": "keyfile"},
        ),
        (2, "repokey-chacha20-poly1305", {"encryption": "chacha20-poly1305"}),
        (
            2,
            "keyfile-chacha20-poly1305",
            {"encryption": "chacha20-poly1305", "key_location": "keyfile"},
        ),
        (2, "authenticated", {"encryption": "authenticated-sha256"}),
    ],
)
@pytest.mark.parametrize(
    "path", ["/srv/backups/repo", "ssh://borg@backup.example.com/./repo"]
)
def test_borg_ui_export_round_trip_keeps_the_major_and_mode(
    db_session, borg2_plan, borg_version, encryption, entry, path
):
    original = Repository(
        name="Round Trip",
        path=path,
        encryption=encryption,
        compression="lz4",
        borg_version=borg_version,
    )
    db_session.add(original)
    db_session.commit()
    config = BorgmaticExportService(db_session).export_repository(
        original, include_schedule=False
    )
    # A Borg 2 entry says what borgmatic for Borg 2 needs to know about it.
    assert config["repositories"] == [{"path": path, **entry} if entry else path]
    assert config.get("borg_ui_borg_version") == (2 if borg_version == 2 else None)
    db_session.delete(original)
    db_session.commit()

    result = BorgmaticImportService(db_session).import_from_yaml(yaml.safe_dump(config))

    assert result["errors"] == []
    row = _only_row(db_session)
    assert (row.name, row.path, row.borg_version, row.encryption) == (
        "Round Trip",
        path,
        borg_version,
        encryption,
    )


def test_export_cli_does_not_load_borg2(tmp_path):
    """Loading app.core.borg2 probes the Borg 2 binary and logs the result to
    stdout, where `export_config --output -` writes its YAML."""
    code = (
        "import sys, app.scripts.export_config; print('app.core.borg2' in sys.modules)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "DATA_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout.strip().splitlines()[-1] == "False"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stored", "entry", "stated"),
    [
        (1, {"path": "/srv/backups/repo", "encryption": "aes256-ocb"}, 2),
        (2, {"path": "/srv/backups/repo", "encryption": "repokey"}, 1),
        # Borg 1 reads b2:path as an SSH host named b2; the row says which.
        (1, {"path": "b2:daily/repo"}, 2),
    ],
)
def test_replace_does_not_change_the_major(
    db_session, borg2_plan, stored, entry, stated
):
    """A repository's format, flags and plans belong to its major."""
    db_session.add(
        Repository(
            name="repo",
            path=entry["path"],
            encryption="repokey" if stored == 1 else "repokey-aes-ocb",
            borg_version=stored,
        )
    )
    db_session.commit()

    config = {"repositories": [entry], "source_directories": ["/data"]}
    result = BorgmaticImportService(db_session).import_from_yaml(
        yaml.safe_dump(config), merge_strategy="replace"
    )
    db_session.rollback()

    assert result["repositories_updated"] == 0
    assert result["errors"] == [
        f"Failed to import repository {entry['path']}: it is recorded as a Borg "
        f"{stored} repository and the configuration describes Borg {stated}; "
        "delete it and import it again to change its Borg version"
    ]
    assert _only_row(db_session).borg_version == stored


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stored", "key_location", "expected"),
    [
        ("repokey-aes-ocb", "keyfile", "keyfile-aes-ocb"),
        ("keyfile-chacha20-poly1305", "repokey", "repokey-chacha20-poly1305"),
        ("authenticated", "keyfile", "authenticated"),
    ],
)
def test_replace_moves_the_key_location_of_the_stored_mode(
    db_session, borg2_plan, stored, key_location, expected
):
    path = "/srv/backups/repo"
    db_session.add(
        Repository(name="repo", path=path, encryption=stored, borg_version=2)
    )
    db_session.commit()

    config = {"repositories": [{"path": path, "key_location": key_location}]}
    result = BorgmaticImportService(db_session).import_from_yaml(
        yaml.safe_dump(config), merge_strategy="replace"
    )

    assert result["errors"] == []
    assert _only_row(db_session).encryption == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "path", ["/srv/backups/a@b:c", "/srv/backups/repo", "b2:bucket@x/repo"]
)
def test_path_with_at_and_colon_is_not_taken_for_an_ssh_host(
    db_session, borg2_plan, path
):
    """Only `user@host:path` with no slash before the colon is scp style."""
    result = _import(db_session, path)

    assert result["errors"] == []
    assert _only_row(db_session).path == path


@pytest.mark.unit
@pytest.mark.parametrize(
    ("borg_version", "encryption"),
    [(1, "keyfile-blake2"), (2, "keyfile-chacha20-poly1305")],
)
def test_replace_without_a_hint_keeps_the_stored_major(
    db_session, borg_version, encryption
):
    """No hint means the configuration does not know; the row does."""
    path = "/srv/backups/repo"
    db_session.add(
        Repository(
            name="repo", path=path, encryption=encryption, borg_version=borg_version
        )
    )
    db_session.commit()

    config = {"repositories": [path], "source_directories": ["/data"]}
    result = BorgmaticImportService(db_session).import_from_yaml(
        yaml.safe_dump(config), merge_strategy="replace"
    )

    assert result["errors"] == []
    assert result["repositories_updated"] == 1
    row = _only_row(db_session)
    assert (row.borg_version, row.encryption) == (borg_version, encryption)


@pytest.mark.unit
@pytest.mark.parametrize("entry", [{}, {"path": ""}, {"path": 42}, {"label": "x"}])
def test_entry_without_a_path_is_refused(db_session, entry):
    result = BorgmaticImportService(db_session).import_from_yaml(
        yaml.safe_dump({"repositories": [entry], "source_directories": ["/data"]})
    )

    assert result["repositories_created"] == 0
    assert len(result["errors"]) == 1
    assert result["errors"][0].endswith("Repository entry has no path")
    assert db_session.query(Repository).count() == 0


@pytest.mark.unit
def test_zip_import_reports_the_repositories_it_refused(
    test_client, admin_headers, test_db
):
    """A multi-repository export is a ZIP; its refusals reach the summary."""
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            "borg2.yaml",
            yaml.safe_dump(
                {"repositories": ["b2:bucket/repo"], "borg_ui_borg_version": 2}
            ),
        )
        zip_file.writestr(
            "borg1.yaml", yaml.safe_dump({"repositories": ["/srv/backups/repo"]})
        )

    response = test_client.post(
        "/api/config/import/borgmatic",
        files={"file": ("export.zip", archive.getvalue(), "application/zip")},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["repositories_created"] == 1
    assert body["errors"] == [
        "borg2.yaml: Failed to import repository b2:bucket/repo: "
        "Borg 2 repositories are not included in the current plan"
    ]
    assert [row.path for row in test_db.query(Repository).all()] == [
        "/srv/backups/repo"
    ]


@pytest.mark.unit
def test_declared_major_holds_for_every_repository_of_the_file(db_session, borg2_plan):
    config = {
        "repositories": ["/srv/backups/a", "/srv/backups/b"],
        "source_directories": ["/data"],
        "borg_ui_borg_version": 2,
    }
    result = BorgmaticImportService(db_session).import_from_yaml(yaml.safe_dump(config))

    assert result["errors"] == []
    rows = db_session.query(Repository).order_by(Repository.path).all()
    assert [(row.path, row.borg_version) for row in rows] == [
        ("/srv/backups/a", 2),
        ("/srv/backups/b", 2),
    ]


@pytest.mark.unit
def test_dry_run_replace_saves_nothing_when_a_later_entry_needs_the_plan(db_session):
    """The plan lookup can commit; it runs before the first entry changes a row."""
    assert db_session.query(LicensingState).count() == 0
    db_session.add(
        Repository(
            name="a", path="/srv/backups/a", encryption="repokey", compression="lz4"
        )
    )
    db_session.commit()

    config = {
        "repositories": ["/srv/backups/a", "b2:bucket/repo"],
        "source_directories": ["/data"],
        "compression": "zstd",
    }
    result = BorgmaticImportService(db_session).import_from_yaml(
        yaml.safe_dump(config), merge_strategy="replace", dry_run=True
    )
    db_session.rollback()

    assert result["repositories_updated"] == 1
    assert db_session.query(Repository).one().compression == "lz4"


@pytest.mark.unit
@pytest.mark.parametrize(
    "entry",
    [
        {"encryption": "authenticated-blake3"},
        {"encryption": "aes256-ocb", "id_hash": "blake3"},
        {"id_hash": "blake3"},
    ],
)
def test_borg2_entry_with_the_blake3_id_hash_is_refused(db_session, borg2_plan, entry):
    """Borg UI's mode names leave the id hash out; recording such a repository
    would make it a sha256 one on export and on a re-create."""
    path = "/srv/backups/repo"
    result = _import(db_session, {"path": path, **entry})

    assert result["errors"] == [
        f"Failed to import repository {path}: "
        "Borg UI has no encryption mode for the blake3 id hash"
    ]
    assert db_session.query(Repository).count() == 0


@pytest.mark.unit
@pytest.mark.parametrize("path", ["b2:daily/repo", "s3:archive", "rclone:host:repo"])
def test_borg1_repository_on_an_ssh_host_named_like_a_store_is_not_re_imported_as_borg2(
    db_session, borg2_plan, path
):
    """Borg 1 reads b2:path as an SSH host named b2; the export says Borg 1,
    so the import refuses the entry instead of sending it to the store."""
    original = Repository(
        name="Alias", path=path, encryption="repokey", compression="lz4", borg_version=1
    )
    db_session.add(original)
    db_session.commit()
    config = BorgmaticExportService(db_session).export_repository(
        original, include_schedule=False
    )
    assert config["borg_ui_borg_version"] == 1
    db_session.delete(original)
    db_session.commit()

    result = BorgmaticImportService(db_session).import_from_yaml(yaml.safe_dump(config))

    assert result["repositories_created"] == 0
    assert len(result["errors"]) == 1
    assert "but borg_ui_borg_version 1 needs Borg 1" in result["errors"][0]
    assert db_session.query(Repository).count() == 0
