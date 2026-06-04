import json
import os
import shutil
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app.api import source_discovery
from app.core.security import encrypt_secret
from app.database.models import SSHConnection, SSHKey
from app.utils.script_params import parse_script_parameters


@pytest.mark.unit
class TestSourceDiscovery:
    def test_database_discovery_returns_extensible_source_types(
        self, test_client, admin_headers
    ):
        response = test_client.get(
            "/api/source-discovery/databases", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()

        source_types = {
            source_type["id"]: source_type for source_type in body["source_types"]
        }
        assert source_types["paths"]["status"] == "enabled"
        assert source_types["database"]["status"] == "enabled"
        assert source_types["container"]["status"] == "enabled"
        assert source_types["container"]["disabled"] is False

    def test_database_discovery_returns_supported_templates(
        self, test_client, admin_headers
    ):
        response = test_client.get(
            "/api/source-discovery/databases", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()

        templates = {template["id"]: template for template in body["templates"]}
        assert set(templates) == {"mongodb", "mysql", "postgresql", "redis", "sqlite"}

        postgresql = templates["postgresql"]
        assert postgresql["engine"] == "PostgreSQL"
        assert postgresql["source_directories"] == [
            "/var/tmp/borg-ui/database-dumps/postgresql"
        ]
        assert postgresql["backup_strategy"] == "logical_dump"
        assert postgresql["documentation_url"].startswith("https://www.postgresql.org/")

    def test_container_scan_detects_local_containers_with_mount_coverage(
        self, test_client, admin_headers, monkeypatch
    ):
        def fake_local_container_scan(**kwargs):
            del kwargs
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "Id": (
                            "5ad07b8f01d2f9fef1b6ee4e8cc2d7ce"
                            "2b6f0fc3f3ef024a23f1e3a0d5f0c3c1"
                        ),
                        "Name": "/postgres",
                        "Config": {"Image": "postgres:17"},
                        "State": {"Status": "running"},
                        "Mounts": [
                            {
                                "Type": "volume",
                                "Name": "postgres-data",
                                "Source": "/var/lib/docker/volumes/postgres-data/_data",
                                "Destination": "/var/lib/postgresql/data",
                            },
                            {
                                "Type": "bind",
                                "Source": "/srv/postgres/conf",
                                "Destination": "/etc/postgresql/conf.d",
                            },
                        ],
                    }
                )
                + "\n",
                stderr="",
            )

        monkeypatch.setattr(
            source_discovery,
            "_run_local_container_scan",
            fake_local_container_scan,
            raising=False,
        )

        response = test_client.post(
            "/api/source-discovery/containers/scan",
            json={"source_type": "local", "source_ssh_connection_id": None},
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["scan_target"] == {
            "source_type": "local",
            "source_ssh_connection_id": None,
            "label": "This Borg UI server",
        }
        assert body["warnings"] == []
        assert len(body["containers"]) == 1

        container = body["containers"][0]
        assert (
            container["id"]
            == "5ad07b8f01d2f9fef1b6ee4e8cc2d7ce2b6f0fc3f3ef024a23f1e3a0d5f0c3c1"
        )
        assert container["name"] == "postgres"
        assert container["image"] == "postgres:17"
        assert container["status"] == "running"
        assert container["backup_mode"] == "export"
        assert container["export_path"] == "/var/tmp/borg-ui/container-exports/postgres"
        assert any("container filesystem" in note for note in container["notes"])
        assert any("not included" in note for note in container["notes"])
        assert container["mounts"] == [
            {
                "type": "volume",
                "name": "postgres-data",
                "source": "/var/lib/docker/volumes/postgres-data/_data",
                "destination": "/var/lib/postgresql/data",
                "backed_up": False,
                "reason": "Not included in docker export; add this path separately from Files if needed.",
            },
            {
                "type": "bind",
                "name": None,
                "source": "/srv/postgres/conf",
                "destination": "/etc/postgresql/conf.d",
                "backed_up": False,
                "reason": "Not included in docker export; add this path separately from Files if needed.",
            },
        ]

    def test_container_scan_detects_remote_containers(
        self, test_client, admin_headers, test_db, monkeypatch
    ):
        ssh_key = SSHKey(
            name="container-scan-key",
            public_key="ssh-ed25519 AAAATEST container-scan-key",
            private_key=encrypt_secret("fake private key"),
            key_type="ed25519",
        )
        test_db.add(ssh_key)
        test_db.commit()
        test_db.refresh(ssh_key)
        connection = SSHConnection(
            ssh_key_id=ssh_key.id,
            host="docker-host.test",
            username="backup",
            port=2222,
            is_backup_source=True,
        )
        test_db.add(connection)
        test_db.commit()
        test_db.refresh(connection)

        def fake_remote_container_scan(**kwargs):
            assert kwargs["connection"].id == connection.id
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "Id": "93b3f8a1c2d4",
                        "Name": "/nginx",
                        "Config": {"Image": "nginx:1.27"},
                        "State": {"Status": "running"},
                        "Mounts": [],
                    }
                )
                + "\n",
                stderr="",
            )

        monkeypatch.setattr(
            source_discovery,
            "_run_remote_container_scan",
            fake_remote_container_scan,
            raising=False,
        )

        response = test_client.post(
            "/api/source-discovery/containers/scan",
            json={
                "source_type": "remote",
                "source_ssh_connection_id": connection.id,
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["scan_target"] == {
            "source_type": "remote",
            "source_ssh_connection_id": connection.id,
            "label": "backup@docker-host.test",
        }
        assert body["warnings"] == []
        assert body["containers"][0]["name"] == "nginx"
        assert body["containers"][0]["image"] == "nginx:1.27"

    def test_remote_container_scan_preserves_ssh_host_key_verification(
        self, monkeypatch
    ):
        captured: dict[str, list[str]] = {}

        def fake_run(cmd, **kwargs):
            del kwargs
            captured["cmd"] = cmd
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(source_discovery.subprocess, "run", fake_run)

        source_discovery._run_remote_container_scan(
            connection=SimpleNamespace(
                host="docker-host.test",
                username="backup",
                port=2222,
            ),
            key_file_path="/tmp/borg-ui-test-key",
            include_stopped=True,
            timeout_seconds=15,
        )

        assert "StrictHostKeyChecking=accept-new" in captured["cmd"]
        assert "StrictHostKeyChecking=no" not in captured["cmd"]
        assert "UserKnownHostsFile=/dev/null" not in captured["cmd"]

    def test_sqlite_template_stages_backup_with_parameters(
        self, test_client, admin_headers
    ):
        response = test_client.get(
            "/api/source-discovery/databases", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()

        sqlite = next(
            template for template in body["templates"] if template["id"] == "sqlite"
        )
        assert sqlite["engine"] == "SQLite"
        assert sqlite["source_directories"] == [
            "/var/tmp/borg-ui/database-dumps/sqlite"
        ]
        assert sqlite["client_commands"] == ["sqlite3"]
        assert sqlite["backup_strategy"] == "online_backup"

        pre_backup = sqlite["script_drafts"]["pre_backup"]["content"]
        post_backup = sqlite["script_drafts"]["post_backup"]["content"]
        assert "sqlite3" in pre_backup
        assert "python3" in pre_backup
        assert "BORG_UI_DB_SOURCE_PATH" in pre_backup
        assert "SQLITE_DATABASE_PATH" in pre_backup
        assert "SQLITE_DATABASE_NAME" not in pre_backup
        assert parse_script_parameters(pre_backup) == []
        assert "/var/tmp/borg-ui/database-dumps/sqlite" in pre_backup
        assert "/var/tmp/borg-ui/database-dumps/sqlite" in post_backup

    def test_sqlite_backup_script_uses_python_fallback_without_sqlite_cli(
        self, test_client, admin_headers, tmp_path
    ):
        response = test_client.get(
            "/api/source-discovery/databases", headers=admin_headers
        )

        sqlite_template = next(
            template
            for template in response.json()["templates"]
            if template["id"] == "sqlite"
        )
        pre_backup = sqlite_template["script_drafts"]["pre_backup"]["content"]

        source_db = tmp_path / "source.sqlite3"
        with sqlite3.connect(source_db) as connection:
            connection.execute("CREATE TABLE items (name TEXT NOT NULL)")
            connection.execute("INSERT INTO items (name) VALUES ('alpha')")

        script_path = tmp_path / "prepare-sqlite.sh"
        script_path.write_text(pre_backup)
        script_path.chmod(0o700)

        temp_bin = tmp_path / "bin"
        temp_bin.mkdir()
        for command in ("mkdir", "rm"):
            command_path = shutil.which(command)
            assert command_path
            (temp_bin / command).symlink_to(command_path)
        (temp_bin / "python3").symlink_to(sys.executable)

        result = subprocess.run(
            ["/bin/bash", str(script_path)],
            env={
                **os.environ,
                "PATH": str(temp_bin),
                "BORG_UI_DB_SOURCE_PATH": str(source_db),
                "BORG_UI_DB_DUMP_DIR": str(tmp_path / "dump"),
            },
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, result.stderr
        with sqlite3.connect(tmp_path / "dump" / "database.sqlite3") as connection:
            assert connection.execute("SELECT name FROM items").fetchone() == ("alpha",)

    def test_database_templates_include_editable_script_drafts(
        self, test_client, admin_headers
    ):
        response = test_client.get(
            "/api/source-discovery/databases", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()

        for template in body["templates"]:
            drafts = template["script_drafts"]
            assert set(drafts) == {"pre_backup", "post_backup"}

            pre_backup = drafts["pre_backup"]
            post_backup = drafts["post_backup"]

            assert pre_backup["name"]
            assert pre_backup["description"]
            assert pre_backup["timeout"] >= 60
            assert "set -euo pipefail" in pre_backup["content"]
            assert template["source_directories"][0] in pre_backup["content"]

            assert post_backup["name"]
            assert post_backup["description"]
            assert post_backup["timeout"] >= 60
            assert "set -euo pipefail" in post_backup["content"]
            assert template["source_directories"][0] in post_backup["content"]

    def test_filesystem_snapshot_capabilities_report_host_tools(
        self, test_client, admin_headers, monkeypatch
    ):
        monkeypatch.setattr(
            source_discovery,
            "which",
            lambda command: f"/usr/sbin/{command}" if command == "btrfs" else None,
        )

        response = test_client.get(
            "/api/source-discovery/filesystem-snapshots", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()
        providers = {provider["id"]: provider for provider in body["providers"]}
        assert providers["btrfs"]["available"] is True
        assert providers["btrfs"]["command"] == "btrfs"
        assert providers["zfs"]["available"] is False
        assert providers["zfs"]["command"] == "zfs"
        assert body["supported_source_types"] == ["local"]
        assert "Remote SSH" in body["unsupported_source_targets"][0]

    def test_database_scan_rejects_empty_paths(self, test_client, admin_headers):
        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": [],
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert "paths" in str(response.json()["detail"])

    def test_database_scan_rejects_remote_without_connection_id(
        self, test_client, admin_headers
    ):
        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "remote",
                "source_ssh_connection_id": None,
                "paths": ["/var/lib/postgresql"],
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert "source_ssh_connection_id" in str(response.json()["detail"])

    def test_database_scan_rejects_non_absolute_path(self, test_client, admin_headers):
        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": ["var/lib/postgresql"],
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert "PATH_NOT_ABSOLUTE" in str(response.json()["detail"])

    def test_database_scan_rejects_shell_metacharacters(
        self, test_client, admin_headers
    ):
        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": ["/var/lib/postgresql;rm -rf /"],
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert "shell metacharacters" in str(response.json()["detail"])

    def test_database_scan_detects_local_signature_path(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(source_discovery, "which", lambda command: None)
        postgresql_data_dir = tmp_path / "custom-pgdata"
        postgresql_data_dir.mkdir()
        (postgresql_data_dir / "PG_VERSION").write_text("17\n")

        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": [str(postgresql_data_dir)],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["scan_target"] == {
            "source_type": "local",
            "source_ssh_connection_id": None,
            "label": "This Borg UI server",
        }
        assert body["scanned_paths"] == [str(postgresql_data_dir)]
        assert body["warnings"] == []
        assert len(body["detections"]) == 1
        assert body["detections"][0]["id"] == "postgresql"
        assert body["detections"][0]["detected"] is True
        assert body["detections"][0]["detection_source"] == str(postgresql_data_dir)

    def test_database_scan_detects_local_sqlite_file(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(source_discovery, "which", lambda command: None)
        sqlite_db = tmp_path / "app.sqlite3"
        sqlite_db.write_bytes(b"SQLite format 3\x00")

        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": [str(sqlite_db)],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        detections = response.json()["detections"]
        assert [detection["id"] for detection in detections] == ["sqlite"]
        assert detections[0]["detection_source"] == str(sqlite_db)

    def test_database_scan_detects_multiple_local_sqlite_files(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(source_discovery, "which", lambda command: None)
        first_db = tmp_path / "app.sqlite3"
        second_db = tmp_path / "cache.db"
        first_db.write_bytes(b"SQLite format 3\x00")
        second_db.write_bytes(b"SQLite format 3\x00")

        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": [str(tmp_path)],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        sqlite_sources = [
            detection["detection_source"]
            for detection in response.json()["detections"]
            if detection["id"] == "sqlite"
        ]
        assert len(sqlite_sources) == 2
        assert set(sqlite_sources) == {str(first_db), str(second_db)}

    def test_database_scan_detects_cli_when_path_probe_is_negative(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        missing_path = tmp_path / "missing-postgres"
        monkeypatch.setattr(
            source_discovery,
            "which",
            lambda command: f"/usr/bin/{command}" if command == "pg_dump" else None,
        )

        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": [str(missing_path)],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        detections = response.json()["detections"]
        assert [detection["id"] for detection in detections] == ["postgresql"]
        assert detections[0]["detection_source"] == "pg_dump available on PATH"

    def test_database_scan_does_not_detect_sqlite_from_cli_only(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.setattr(
            source_discovery,
            "which",
            lambda command: "/usr/bin/sqlite3" if command == "sqlite3" else None,
        )

        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": [str(empty_dir)],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["detections"] == []
        assert "sqlite" in {template["id"] for template in body["templates"]}

    def test_database_scan_returns_empty_detections_with_templates(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(source_discovery, "which", lambda command: None)
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": [str(empty_dir)],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["detections"] == []
        assert {template["id"] for template in body["templates"]} == {
            "mongodb",
            "mysql",
            "postgresql",
            "redis",
            "sqlite",
        }
        assert all(template["detected"] is False for template in body["templates"])

    def test_database_scan_detects_remote_probe_output(
        self, test_client, admin_headers, test_db, monkeypatch
    ):
        ssh_key = SSHKey(
            name="source-scan-key",
            public_key="ssh-ed25519 AAAATEST source-scan-key",
            private_key=encrypt_secret("fake private key"),
            key_type="ed25519",
        )
        test_db.add(ssh_key)
        test_db.commit()
        test_db.refresh(ssh_key)
        connection = SSHConnection(
            ssh_key_id=ssh_key.id,
            host="example.test",
            username="backup",
            port=2222,
            is_backup_source=True,
        )
        test_db.add(connection)
        test_db.commit()
        test_db.refresh(connection)

        def fake_remote_probe(**kwargs):
            return SimpleNamespace(
                returncode=0,
                stdout="\n".join(
                    [
                        "PATH\t/srv/postgresql\t1",
                        "FILE\t/srv/postgresql\tPG_VERSION\t1",
                        "PATH\t/srv/cache\t1",
                        "FILE\t/srv/cache\tdump.rdb\t1",
                        "PATH\t/srv/app.db\t1",
                        "FILE\t/srv/app.db\tSQLITE_DB\t1",
                        "COMMAND\tpg_dump\t0",
                        "COMMAND\tmysqldump\t0",
                        "COMMAND\tmongodump\t0",
                        "COMMAND\tredis-cli\t0",
                        "COMMAND\tsqlite3\t0",
                    ]
                ),
                stderr="",
            )

        monkeypatch.setattr(
            source_discovery,
            "_run_remote_database_probe",
            fake_remote_probe,
            raising=False,
        )

        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "remote",
                "source_ssh_connection_id": connection.id,
                "paths": ["/srv/postgresql", "/srv/cache", "/srv/app.db"],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["scan_target"] == {
            "source_type": "remote",
            "source_ssh_connection_id": connection.id,
            "label": "backup@example.test",
        }
        assert body["scanned_paths"] == [
            "/srv/postgresql",
            "/srv/cache",
            "/srv/app.db",
        ]
        assert body["warnings"] == []
        detections = {detection["id"]: detection for detection in body["detections"]}
        assert set(detections) == {"postgresql", "redis", "sqlite"}
        assert detections["postgresql"]["detection_source"] == "/srv/postgresql"
        assert detections["redis"]["detection_source"] == "/srv/cache"
        assert detections["sqlite"]["detection_source"] == "/srv/app.db"

    def test_database_scan_remote_connection_failure_returns_warning_body(
        self, test_client, admin_headers, test_db, monkeypatch
    ):
        ssh_key = SSHKey(
            name="source-scan-failed-key",
            public_key="ssh-ed25519 AAAATEST source-scan-failed-key",
            private_key=encrypt_secret("fake private key"),
            key_type="ed25519",
        )
        test_db.add(ssh_key)
        test_db.commit()
        test_db.refresh(ssh_key)
        connection = SSHConnection(
            ssh_key_id=ssh_key.id,
            host="example.test",
            username="backup",
            port=22,
            is_backup_source=True,
        )
        test_db.add(connection)
        test_db.commit()
        test_db.refresh(connection)

        def fake_remote_probe(**kwargs):
            return SimpleNamespace(
                returncode=255,
                stdout="",
                stderr="ssh: connect to host example.test port 22: Connection refused",
            )

        monkeypatch.setattr(
            source_discovery,
            "_run_remote_database_probe",
            fake_remote_probe,
            raising=False,
        )

        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "remote",
                "source_ssh_connection_id": connection.id,
                "paths": ["/srv/postgresql"],
            },
            headers=admin_headers,
        )

        assert response.status_code == 502
        body = response.json()
        assert body["detections"] == []
        assert body["warnings"][0]["code"] == "SSH_HOST_UNREACHABLE"
        assert "backup@example.test" in body["warnings"][0]["message"]
        assert {template["id"] for template in body["templates"]} == {
            "mongodb",
            "mysql",
            "postgresql",
            "redis",
            "sqlite",
        }

    def test_database_scan_walks_recursively_to_find_nested_db(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        # PG_VERSION lives 3 levels below the scan root. Default depth (6)
        # should discover it.
        monkeypatch.setattr(source_discovery, "which", lambda command: None)
        nested_pg = tmp_path / "var" / "lib" / "postgresql" / "16" / "main"
        nested_pg.mkdir(parents=True)
        (nested_pg / "PG_VERSION").write_text("16\n")

        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": [str(tmp_path)],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        detections = body["detections"]
        assert [d["id"] for d in detections] == ["postgresql"]
        assert detections[0]["detection_source"] == str(nested_pg)

    def test_database_scan_respects_max_depth(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        # PG_VERSION sits 4 levels below the scan root. max_depth=2 means
        # the walk stops before reaching it, so nothing is detected.
        monkeypatch.setattr(source_discovery, "which", lambda command: None)
        nested_pg = tmp_path / "a" / "b" / "c" / "d"
        nested_pg.mkdir(parents=True)
        (nested_pg / "PG_VERSION").write_text("16\n")

        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": [str(tmp_path)],
                "max_depth": 2,
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["detections"] == []

    def test_database_scan_skips_ignored_directories(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        # A PG signature inside an ignored dir should be missed. The same
        # signature outside it should be picked up.
        monkeypatch.setattr(source_discovery, "which", lambda command: None)
        ignored_pg = tmp_path / "node_modules" / "fixture-pg"
        ignored_pg.mkdir(parents=True)
        (ignored_pg / "PG_VERSION").write_text("16\n")

        kept_mysql = tmp_path / "data" / "mysql"
        kept_mysql.mkdir(parents=True)

        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": [str(tmp_path)],
                "ignore_patterns": ["node_modules"],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        ids = [d["id"] for d in response.json()["detections"]]
        assert "mysql" in ids
        assert "postgresql" not in ids

    def test_database_scan_default_prunes_system_dirs_for_broad_scan(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(source_discovery, "which", lambda command: None)
        noisy_sqlite = tmp_path / "usr" / "bin" / "tool.db"
        noisy_sqlite.parent.mkdir(parents=True)
        noisy_sqlite.write_bytes(b"SQLite format 3\x00")
        app_sqlite = tmp_path / "etc" / "pihole" / "gravity.db"
        app_sqlite.parent.mkdir(parents=True)
        app_sqlite.write_bytes(b"SQLite format 3\x00")

        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": [str(tmp_path)],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        sqlite_sources = [
            detection["detection_source"]
            for detection in response.json()["detections"]
            if detection["id"] == "sqlite"
        ]
        assert str(app_sqlite) in sqlite_sources
        assert str(noisy_sqlite) not in sqlite_sources

    def test_database_scan_rejects_out_of_range_max_depth(
        self, test_client, admin_headers
    ):
        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": ["/tmp"],
                "max_depth": 999,
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert "max_depth" in str(response.json()["detail"])

    def test_database_scan_rejects_ignore_pattern_with_shell_chars(
        self, test_client, admin_headers
    ):
        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": ["/tmp"],
                "ignore_patterns": ["nope; rm -rf /"],
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert "ignore pattern" in str(response.json()["detail"])

    def test_database_scan_keeps_pre_script_generic_for_detected_path(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        # Detected paths are stored on the source selection, not baked into
        # script drafts. That keeps engine scripts reusable across databases.
        monkeypatch.setattr(source_discovery, "which", lambda command: None)
        pg_dir = tmp_path / "custom-pg"
        pg_dir.mkdir()
        (pg_dir / "PG_VERSION").write_text("16\n")

        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": [str(pg_dir)],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        detections = response.json()["detections"]
        assert len(detections) == 1
        assert detections[0]["detection_source"] == str(pg_dir)
        script_content = detections[0]["script_drafts"]["pre_backup"]["content"]
        assert "Discovered by Borg UI at:" not in script_content
        assert str(pg_dir) not in script_content

    def test_database_scan_does_not_inject_path_for_command_only_detection(
        self, test_client, admin_headers, tmp_path, monkeypatch
    ):
        # When detection happens only because the client CLI is on PATH (no
        # data dir found), the script should remain unmodified.
        missing_path = tmp_path / "no-pg-here"
        monkeypatch.setattr(
            source_discovery,
            "which",
            lambda command: f"/usr/bin/{command}" if command == "pg_dump" else None,
        )

        response = test_client.post(
            "/api/source-discovery/databases/scan",
            json={
                "source_type": "local",
                "source_ssh_connection_id": None,
                "paths": [str(missing_path)],
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        detections = response.json()["detections"]
        assert detections[0]["detection_source"] == "pg_dump available on PATH"
        assert (
            "BORG_UI_DETECTED_PATH"
            not in detections[0]["script_drafts"]["pre_backup"]["content"]
        )
