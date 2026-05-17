import pytest


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
        assert set(templates) == {"mongodb", "mysql", "postgresql", "redis"}

        postgresql = templates["postgresql"]
        assert postgresql["engine"] == "PostgreSQL"
        assert postgresql["source_directories"] == [
            "/var/tmp/borg-ui/database-dumps/postgresql"
        ]
        assert postgresql["backup_strategy"] == "logical_dump"
        assert postgresql["documentation_url"].startswith("https://www.postgresql.org/")

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
