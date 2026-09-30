import json
import os
import shlex
from types import SimpleNamespace

import pytest

from app.api import source_discovery
from app.app_templates import (
    APP_ROOT_PLACEHOLDER,
    load_app_templates,
    match_app_template,
)
from app.database.models import LicensingState


def _immich_container(
    host_path: str, image: str = "ghcr.io/immich-app/immich-server:release"
):
    return json.dumps(
        {
            "Id": "a" * 64,
            "Name": "/immich_server",
            "Config": {"Image": image},
            "State": {"Status": "running"},
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": "/etc/localtime",
                    "Destination": "/etc/localtime",
                },
                {"Type": "bind", "Source": host_path, "Destination": "/data"},
            ],
        }
    )


def _fake_scan(stdout: str):
    def fake(**kwargs):
        del kwargs
        return SimpleNamespace(returncode=0, stdout=stdout + "\n", stderr="")

    return fake


@pytest.mark.unit
class TestAppTemplates:
    def test_every_template_loads_with_unique_ids(self):
        templates = load_app_templates()
        ids = [template.id for template in templates]
        assert "immich" in ids
        assert len(ids) == len(set(ids))
        for template in templates:
            if template.pre_backup_script:
                # The frontend fills the app's root folder into this placeholder.
                assert APP_ROOT_PLACEHOLDER in template.pre_backup_script.content

    def test_immich_keeps_the_database_dumps_and_skips_rebuildable_folders(self):
        immich = next(t for t in load_app_templates() if t.id == "immich")
        roles = {folder.path: folder.role for folder in immich.folders}
        assert roles["backups"] == "database"
        assert {p for p, role in roles.items() if role == "rebuildable"} == {
            "thumbs",
            "encoded-video",
        }

    def test_match_by_image_prefix(self):
        templates = load_app_templates()
        assert (
            match_app_template("ghcr.io/immich-app/immich-server:v3.2.4", templates).id
            == "immich"
        )
        assert (
            match_app_template(
                "ghcr.io/immich-app/immich-machine-learning:release", templates
            )
            is None
        )
        assert match_app_template(None, templates) is None

    def test_list_endpoint_is_free(self, test_client, admin_headers, test_db):
        state = test_db.query(LicensingState).first() or LicensingState(instance_id="t")
        state.plan = "community"
        test_db.add(state)
        test_db.commit()

        response = test_client.get("/api/source-discovery/apps", headers=admin_headers)

        assert response.status_code == 200
        immich = next(t for t in response.json()["templates"] if t["id"] == "immich")
        assert immich["pre_backup_script"]["content"].startswith("#!/usr/bin/env bash")
        assert "<svg" in immich["logo_svg"]

    def test_detect_finds_immich_and_reports_readable_folder(
        self, test_client, admin_headers, monkeypatch, tmp_path
    ):
        library = tmp_path / "immich"
        library.mkdir()
        monkeypatch.setattr(
            source_discovery,
            "_run_local_container_scan",
            _fake_scan(_immich_container(str(library))),
        )

        response = test_client.post(
            "/api/source-discovery/apps/detect",
            json={"source_type": "local"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["detections"] == [
            {
                "template_id": "immich",
                "container_name": "immich_server",
                "state": "running",
                "path": str(library),
                "host_path": str(library),
                "readable": True,
                "extra_mounts": [],
            }
        ]

    def test_detect_flags_a_folder_borg_ui_cannot_see(
        self, test_client, admin_headers, monkeypatch
    ):
        monkeypatch.setattr(
            source_discovery,
            "_run_local_container_scan",
            _fake_scan(_immich_container("/srv/not-mounted-into-borg-ui")),
        )

        response = test_client.post(
            "/api/source-discovery/apps/detect",
            json={"source_type": "local"},
            headers=admin_headers,
        )

        [detection] = response.json()["detections"]
        assert detection["readable"] is False
        assert detection["host_path"] == "/srv/not-mounted-into-borg-ui"

    def test_detect_returns_warning_when_docker_fails(
        self, test_client, admin_headers, monkeypatch
    ):
        def failing(**kwargs):
            del kwargs
            return SimpleNamespace(
                returncode=1, stdout="", stderr="sh: docker: not found"
            )

        monkeypatch.setattr(source_discovery, "_run_local_container_scan", failing)

        response = test_client.post(
            "/api/source-discovery/apps/detect",
            json={"source_type": "local"},
            headers=admin_headers,
        )

        body = response.json()
        assert response.status_code == 200
        assert body["detections"] == []
        assert body["warnings"][0]["code"] == "DOCKER_CLI_MISSING"


@pytest.mark.unit
class TestAppInspect:
    def test_inspect_reports_size_and_newest_dump_per_folder(
        self, test_client, admin_headers, tmp_path
    ):
        root = tmp_path / "immich"
        (root / "upload").mkdir(parents=True)
        (root / "upload" / "photo.jpg").write_bytes(b"x" * 5000)
        (root / "backups").mkdir()
        (root / "backups" / "immich-db-backup-1.sql.gz").write_bytes(b"db")

        response = test_client.post(
            "/api/source-discovery/apps/inspect",
            json={"template_id": "immich", "source_type": "local", "path": str(root)},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["root_status"] == "ok"
        folders = {f["path"]: f for f in response.json()["folders"]}
        assert folders["upload"]["exists"] is True
        assert folders["upload"]["size_bytes"] >= 5000
        assert folders["backups"]["latest_name"] == "immich-db-backup-1.sql.gz"
        assert folders["backups"]["latest_modified_at"] is not None
        assert folders["thumbs"] == {
            "path": "thumbs",
            "exists": False,
            "readable": False,
            "size_bytes": None,
            "latest_name": None,
            "latest_modified_at": None,
        }

    def test_inspect_quotes_paths(self):
        root = "/srv/it's; rm -rf /"
        script = source_discovery._build_app_inspect_script(root, ["upload"])
        assert f"ROOT={shlex.quote(root)}\n" in script

    def test_inspect_rejects_unknown_template_and_relative_path(
        self, test_client, admin_headers
    ):
        unknown = test_client.post(
            "/api/source-discovery/apps/inspect",
            json={"template_id": "nope", "source_type": "local", "path": "/srv"},
            headers=admin_headers,
        )
        relative = test_client.post(
            "/api/source-discovery/apps/inspect",
            json={"template_id": "immich", "source_type": "local", "path": "srv"},
            headers=admin_headers,
        )
        assert unknown.status_code == 404
        assert relative.status_code == 400

    def test_inspect_tells_missing_from_unreadable(
        self, test_client, admin_headers, tmp_path
    ):
        def inspect(path):
            return test_client.post(
                "/api/source-discovery/apps/inspect",
                json={"template_id": "immich", "source_type": "local", "path": path},
                headers=admin_headers,
            ).json()

        missing = inspect(str(tmp_path / "nope"))
        assert missing["root_status"] == "missing"
        assert missing["folders"] == []

        # Like Docker's volumes dir: the parent can't be entered.
        locked = tmp_path / "volumes"
        (locked / "abc" / "_data").mkdir(parents=True)
        locked.chmod(0o000)
        try:
            denied = inspect(str(locked / "abc" / "_data"))
        finally:
            locked.chmod(0o755)
        if os.geteuid() != 0:  # root reads anything
            assert denied["root_status"] == "denied"
            assert denied["folders"] == []
        assert denied["user"]


def _mount(type_, source, destination, name=None):
    return {"Type": type_, "Source": source, "Destination": destination, "Name": name}


@pytest.mark.unit
class TestAppDetectMounts:
    def _detect(self, test_client, admin_headers, monkeypatch, mounts):
        container = json.dumps(
            {
                "Id": "b" * 64,
                "Name": "/immich_server",
                "Config": {"Image": "ghcr.io/immich-app/immich-server:release"},
                "State": {"Status": "running"},
                "Mounts": mounts,
            }
        )
        monkeypatch.setattr(
            source_discovery, "_run_local_container_scan", _fake_scan(container)
        )
        response = test_client.post(
            "/api/source-discovery/apps/detect",
            json={"source_type": "local"},
            headers=admin_headers,
        )
        [detection] = response.json()["detections"]
        return detection

    def test_legacy_upload_mount_beats_anonymous_data_volume(
        self, test_client, admin_headers, monkeypatch
    ):
        # An install upgraded from before /data: its media is still mounted at
        # /usr/src/app/upload and the image gets an empty anonymous /data.
        anonymous = "f4" * 32
        detection = self._detect(
            test_client,
            admin_headers,
            monkeypatch,
            [
                _mount("bind", "/srv/photos-lib", "/srv/photos-lib"),
                _mount("bind", "/srv/immich-media", "/usr/src/app/upload"),
                _mount(
                    "volume",
                    f"/var/lib/docker/volumes/{anonymous}/_data",
                    "/data",
                    anonymous,
                ),
                _mount("bind", "/etc/localtime", "/etc/localtime"),
            ],
        )

        assert detection["host_path"] == "/srv/immich-media"
        assert [extra["host_path"] for extra in detection["extra_mounts"]] == [
            "/srv/photos-lib"
        ]

    def test_data_mount_preferred_when_both_are_real(
        self, test_client, admin_headers, monkeypatch
    ):
        detection = self._detect(
            test_client,
            admin_headers,
            monkeypatch,
            [
                _mount("bind", "/srv/old", "/usr/src/app/upload"),
                _mount("bind", "/srv/new", "/data"),
            ],
        )
        assert detection["host_path"] == "/srv/new"
        assert detection["extra_mounts"] == []


@pytest.mark.unit
class TestAppInspectExtras:
    def test_extra_paths_are_measured_and_permission_checked(
        self, test_client, admin_headers, tmp_path
    ):
        root = tmp_path / "immich"
        root.mkdir()
        library = tmp_path / "library"
        library.mkdir()
        (library / "a.jpg").write_bytes(b"x" * 3000)
        locked = tmp_path / "locked"
        (locked / "inner").mkdir(parents=True)
        locked.chmod(0o000)
        try:
            body = test_client.post(
                "/api/source-discovery/apps/inspect",
                json={
                    "template_id": "immich",
                    "source_type": "local",
                    "path": str(root),
                    "extra_paths": [str(library), str(locked / "inner")],
                },
                headers=admin_headers,
            ).json()
        finally:
            locked.chmod(0o755)

        stats = {item["path"]: item for item in body["folders"]}
        assert stats[str(library)]["readable"] is True
        assert stats[str(library)]["size_bytes"] >= 3000
        if os.geteuid() != 0:
            assert stats[str(locked / "inner")]["exists"] is True
            assert stats[str(locked / "inner")]["readable"] is False


@pytest.mark.unit
class TestAppAccessAndMatching:
    def test_viewers_cannot_detect_or_inspect(self, test_client, auth_headers):
        detect = test_client.post(
            "/api/source-discovery/apps/detect",
            json={"source_type": "local"},
            headers=auth_headers,
        )
        inspect = test_client.post(
            "/api/source-discovery/apps/inspect",
            json={"template_id": "immich", "source_type": "local", "path": "/srv"},
            headers=auth_headers,
        )
        assert detect.status_code == 403
        assert inspect.status_code == 403

    def test_operators_stay_inside_local_mount_points(
        self, test_client, operator_headers, tmp_path, monkeypatch
    ):
        mount = tmp_path / "local"
        (mount / "immich").mkdir(parents=True)
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        monkeypatch.setattr(
            source_discovery.settings, "local_mount_points", str(mount), raising=False
        )

        def inspect(path, extra_paths=()):
            return test_client.post(
                "/api/source-discovery/apps/inspect",
                json={
                    "template_id": "immich",
                    "source_type": "local",
                    "path": path,
                    "extra_paths": list(extra_paths),
                },
                headers=operator_headers,
            )

        assert inspect(str(mount / "immich")).status_code == 200
        assert inspect(str(outside)).status_code == 403
        assert inspect(str(mount / "immich"), [str(outside)]).status_code == 403

    def test_a_newer_unrelated_file_does_not_pass_for_a_fresh_dump(
        self, test_client, admin_headers, tmp_path
    ):
        backups = tmp_path / "immich" / "backups"
        backups.mkdir(parents=True)
        dump = backups / "immich-db-backup-1 old.sql.gz"
        dump.write_bytes(b"db")
        os.utime(dump, (1_000_000_000, 1_000_000_000))
        (backups / "notes.txt").write_text("newer, but not a dump")
        (backups / "immich-db-backup-dir").mkdir()  # matches the name, not a file

        body = test_client.post(
            "/api/source-discovery/apps/inspect",
            json={
                "template_id": "immich",
                "source_type": "local",
                "path": str(tmp_path / "immich"),
            },
            headers=admin_headers,
        ).json()

        backups_stats = next(f for f in body["folders"] if f["path"] == "backups")
        assert backups_stats["latest_name"] == "immich-db-backup-1 old.sql.gz"
        assert backups_stats["latest_modified_at"].startswith("2001-09-09")

    def test_image_matches_by_repository_not_prefix(self):
        templates = load_app_templates()
        for image in [
            "ghcr.io/immich-app/immich-server",
            "ghcr.io/immich-app/immich-server:v3.2.4",
            "ghcr.io/immich-app/immich-server:release@sha256:abc",
        ]:
            assert match_app_template(image, templates).id == "immich"
        assert (
            match_app_template("ghcr.io/immich-app/immich-server-foo:1", templates)
            is None
        )
