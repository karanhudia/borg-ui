import json
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
        excluded = {exclude.path for exclude in immich.excludes}
        assert excluded == {"thumbs", "encoded-video"}
        assert "backups" not in excluded

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
