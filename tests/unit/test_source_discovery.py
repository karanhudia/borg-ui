from types import SimpleNamespace

import pytest

from app.api import source_discovery
from app.core.security import encrypt_secret
from app.database.models import SSHConnection, SSHKey


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
        assert source_types["container"]["status"] == "planned"
        assert source_types["container"]["disabled"] is True

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
        assert "SQLITE_DATABASE_PATH" in pre_backup
        assert "/var/tmp/borg-ui/database-dumps/sqlite" in pre_backup
        assert "/var/tmp/borg-ui/database-dumps/sqlite" in post_backup

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
