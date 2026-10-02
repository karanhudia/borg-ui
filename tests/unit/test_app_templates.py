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

    def test_match_by_image_with_or_without_docker_hub_registry(self):
        templates = load_app_templates()
        for image in (
            "vaultwarden/server:latest",
            "docker.io/vaultwarden/server:1.37.3",
            "ghcr.io/dani-garcia/vaultwarden@sha256:" + "0" * 64,
        ):
            assert match_app_template(image, templates).id == "vaultwarden"
        assert match_app_template("lscr.io/linuxserver/plex", templates).id == "plex"
        assert match_app_template("someone/vaultwarden-fork", templates) is None

    def test_folder_paths_may_nest_but_not_leave_the_app_folder(self):
        from pydantic import ValidationError

        from app.app_templates import AppTemplateFolder

        nested = "Library/Application Support/Plex Media Server/Cache"
        assert AppTemplateFolder(path=nested, label="", description="", role="data")
        for bad in ("../etc", "a/../b", "/abs", "a//b", "a/ b"):
            with pytest.raises(ValidationError):
                AppTemplateFolder(path=bad, label="", description="", role="data")

    def test_npm_certificates_mounted_under_etc_count_as_extra_mount(
        self, test_client, admin_headers, monkeypatch, tmp_path
    ):
        data, certs = tmp_path / "data", tmp_path / "letsencrypt"
        data.mkdir()
        certs.mkdir()
        container = {
            "Id": "b" * 64,
            "Name": "/npm",
            "Config": {"Image": "jc21/nginx-proxy-manager:latest"},
            "State": {"Status": "running"},
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": "/etc/localtime",
                    "Destination": "/etc/localtime",
                },
                {"Type": "bind", "Source": str(data), "Destination": "/data"},
                {
                    "Type": "bind",
                    "Source": str(certs),
                    "Destination": "/etc/letsencrypt",
                },
            ],
        }
        monkeypatch.setattr(
            source_discovery,
            "_run_local_container_scan",
            _fake_scan(json.dumps(container)),
        )

        response = test_client.post(
            "/api/source-discovery/apps/detect",
            json={"source_type": "local"},
            headers=admin_headers,
        )

        [detection] = response.json()["detections"]
        assert detection["template_id"] == "nginx-proxy-manager"
        assert detection["container_name"] == "npm"
        assert [extra["destination"] for extra in detection["extra_mounts"]] == [
            "/etc/letsencrypt"
        ]

    def test_plex_root_follows_each_images_layout(
        self, test_client, admin_headers, monkeypatch, tmp_path
    ):
        nested = tmp_path / "lsio/Library/Application Support/Plex Media Server"
        nested.mkdir(parents=True)
        (tmp_path / "hotio").mkdir()

        def plex(name, image, source):
            return {
                "Id": name * 64,
                "Name": f"/{name}",
                "Config": {"Image": image},
                "State": {"Status": "running"},
                "Mounts": [
                    {"Type": "bind", "Source": source, "Destination": "/config"}
                ],
            }

        monkeypatch.setattr(
            source_discovery,
            "_run_local_container_scan",
            _fake_scan(
                json.dumps(
                    plex("a", "lscr.io/linuxserver/plex:latest", str(tmp_path / "lsio"))
                )
                + "\n"
                + json.dumps(
                    plex("b", "ghcr.io/hotio/plex:latest", str(tmp_path / "hotio"))
                )
            ),
        )

        response = test_client.post(
            "/api/source-discovery/apps/detect",
            json={"source_type": "local"},
            headers=admin_headers,
        )

        paths = {d["container_name"]: d for d in response.json()["detections"]}
        assert paths["a"]["path"] == str(nested)
        assert paths["a"]["readable"] is True
        assert paths["b"]["path"] == str(tmp_path / "hotio")

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


def _render(template_id: str, root, container: str) -> str:
    from app.app_templates import CONTAINER_PLACEHOLDER

    template = next(t for t in load_app_templates() if t.id == template_id)
    return template.pre_backup_script.content.replace(
        APP_ROOT_PLACEHOLDER, shlex.quote(str(root))
    ).replace(CONTAINER_PLACEHOLDER, shlex.quote(container))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("template_id", "dump"),
    [
        ("vaultwarden", "db_20261001_030000.sqlite3"),
        ("paperless-ngx", "manifest.json"),
    ],
)
def test_container_scripts_make_a_dump_or_fail(tmp_path, template_id, dump):
    import subprocess

    root = tmp_path / "app"
    root.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Stands in for `docker exec`: the app writes its dump into its own folder.
    fake_docker = bin_dir / "docker"
    fake_docker.write_text(f"#!/bin/sh\ntouch {shlex.quote(str(root / dump))}\n")
    fake_docker.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}

    def run(container: str):
        return subprocess.run(
            ["bash", "-c", _render(template_id, root, container)],
            env=env,
            capture_output=True,
            text=True,
        )

    # Picked by hand and nothing dumped yet: the backup must not go ahead.
    assert run("").returncode == 1
    assert run("app_container").returncode == 0
    assert (root / dump).exists()


@pytest.mark.unit
def test_plex_check_finds_dated_copies_under_paths_with_spaces(tmp_path):
    import subprocess

    databases = tmp_path / "Plug-in Support/Databases"
    databases.mkdir(parents=True)
    script = _render("plex", tmp_path, "")

    # The live database and its -wal/-shm files are always fresh: not a backup.
    for live in ("", "-wal", "-shm"):
        (databases / f"com.plexapp.plugins.library.db{live}").touch()
    assert subprocess.run(["bash", "-c", script], capture_output=True).returncode == 1
    (databases / "com.plexapp.plugins.library.db-2026-09-30").touch()
    assert subprocess.run(["bash", "-c", script], capture_output=True).returncode == 0


@pytest.mark.unit
def test_jellyfin_is_started_again_when_the_copy_fails(tmp_path):
    import subprocess

    calls = tmp_path / "calls"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # stop/start succeed; cp fails, as when the database is not where expected.
    fake_docker = bin_dir / "docker"
    fake_docker.write_text(
        f'#!/bin/sh\necho "$1" >> {shlex.quote(str(calls))}\n'
        '[ "$1" = cp ] && exit 1\nexit 0\n'
    )
    fake_docker.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}

    result = subprocess.run(
        ["bash", "-c", _render("jellyfin", tmp_path, "jellyfin")],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert calls.read_text().split() == ["stop", "cp", "start"]
